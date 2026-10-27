import contextlib
import hashlib
import mimetypes
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Response, current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.storage import StoredObject


class ObjectStorageError(Exception):
    def __init__(self, message, status_code=500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class StorageCompensationTracker:
    """Tracks newly created storage objects and local staging files to provide
    best-effort compensation (cleanup) if an operation fails prior to DB commit.
    """

    def __init__(self):
        self.created_stored_objects = []
        self.created_local_paths = []
        self._committed = False
        self._compensated = False

    def track_stored_object(self, stored_object):
        """Track a newly created StoredObject for potential compensation."""
        if stored_object:
            self.created_stored_objects.append({
                'id': getattr(stored_object, 'id', None),
                'storage_provider': getattr(stored_object, 'storage_provider', None),
                'bucket_name': getattr(stored_object, 'bucket_name', None),
                'object_key': getattr(stored_object, 'object_key', None),
                'legacy_file_path': getattr(stored_object, 'legacy_file_path', None),
            })
        return stored_object

    def track_local_path(self, path):
        """Track a local staging file for potential compensation."""
        if path:
            self.created_local_paths.append(Path(path))
        return path

    track_staging_file = track_local_path

    @property
    def committed(self):
        return self._committed

    @property
    def compensated(self):
        return self._compensated

    def commit(self):
        """Mark the transaction as committed so compensation will not run."""
        self._committed = True

    def compensate(self):
        """Best-effort compensation. Deletes newly created R2 objects and local files.
        Never raises exceptions so that original application errors are not masked.
        Idempotent: multiple invocations safely return without duplicating actions.
        """
        if self._committed or self._compensated:
            return
        self._compensated = True

        from flask import g, has_request_context
        request_id = getattr(g, 'request_id', None) if has_request_context() else None

        # 1. Rollback SQLAlchemy session if pending
        try:
            db.session.rollback()
        except Exception as exc:
            current_app.logger.warning(
                'DB session rollback during storage compensation encountered error request_id=%s: %s',
                request_id, exc
            )

        # 2. Compensate stored objects (Cloudflare R2 or local durable store)
        for obj in self.created_stored_objects:
            provider = obj.get('storage_provider')
            bucket = obj.get('bucket_name')
            key = obj.get('object_key')
            legacy_path = obj.get('legacy_file_path')

            if provider == 'r2' and bucket and key:
                try:
                    _s3_client().delete_object(Bucket=bucket, Key=key)
                except Exception as exc:
                    current_app.logger.error(
                        'Storage compensation failed to delete R2 object request_id=%s key=%s: %s',
                        request_id, key, exc
                    )
                    try:
                        from app.services.operational_event_service import record_operational_event
                        record_operational_event(
                            severity='ERROR',
                            component='storage',
                            event_name='storage_compensation_failure',
                            message=f'Storage compensation failed to delete R2 object ({key}): {exc}',
                            request_id=request_id,
                            context_data={'provider': provider, 'key': key, 'bucket': bucket},
                            exc_info=exc,
                            emit_log=False,
                        )
                    except Exception:
                        pass
            elif provider == 'local' and key:
                local_path = _local_root() / key
                try:
                    local_path.unlink(missing_ok=True)
                except OSError as exc:
                    current_app.logger.error(
                        'Storage compensation failed to delete local object file request_id=%s key=%s: %s',
                        request_id, key, exc
                    )
                    try:
                        from app.services.operational_event_service import record_operational_event
                        record_operational_event(
                            severity='ERROR',
                            component='storage',
                            event_name='storage_compensation_failure',
                            message=f'Storage compensation failed to delete local object file ({key}): {exc}',
                            request_id=request_id,
                            context_data={'provider': provider, 'key': key},
                            exc_info=exc,
                            emit_log=False,
                        )
                    except Exception:
                        pass

            if legacy_path:
                try:
                    lp = Path(legacy_path)
                    if _legacy_file_path_is_allowed(lp):
                        lp.unlink(missing_ok=True)
                except OSError as exc:
                    current_app.logger.warning(
                        'Storage compensation failed to delete legacy file request_id=%s path=%s: %s',
                        request_id, legacy_path, exc
                    )

        # 3. Compensate staged local files
        for path in self.created_local_paths:
            try:
                if path.exists() and path.is_file():
                    path.unlink(missing_ok=True)
            except OSError as exc:
                current_app.logger.error(
                    'Storage compensation failed to delete staged local file request_id=%s path=%s: %s',
                    request_id, str(path), exc
                )


@contextlib.contextmanager
def storage_transaction():
    """Context manager for storage-writing operations.
    Yields a StorageCompensationTracker. If an exception occurs within the block,
    the tracker compensates all registered artifacts and rolls back the DB session.
    When caller completes successfully and commits the DB transaction, caller calls tracker.commit().
    """
    tracker = StorageCompensationTracker()
    try:
        yield tracker
    except Exception:
        tracker.compensate()
        raise


def is_enabled():
    return _provider() != 'local' or bool(current_app.config.get('OBJECT_STORAGE_LOCAL_DIR'))


def provider_ready():
    provider = _provider()
    if provider == 'local':
        root = _local_root()
        root.mkdir(parents=True, exist_ok=True)
        return True, f'Object storage is using local durable directory {root}.'
    if provider == 'r2':
        from app.services.integration_config_service import resolve_storage_runtime_value
        missing = [
            key for key in (
                'R2_BUCKET_NAME',
                'R2_ENDPOINT_URL',
                'R2_ACCESS_KEY_ID',
                'R2_SECRET_ACCESS_KEY',
            )
            if not resolve_storage_runtime_value(key)
        ]
        if missing:
            return False, f"Cloudflare R2 is missing configuration: {', '.join(missing)}."
        try:
            from botocore.config import Config as BotoConfig
            probe_config = BotoConfig(
                signature_version='s3v4',
                connect_timeout=3,
                read_timeout=3,
                retries={'max_attempts': 1, 'mode': 'standard'},
            )
            bucket_name = resolve_storage_runtime_value('R2_BUCKET_NAME')
            _s3_client(config=probe_config).list_objects_v2(
                Bucket=bucket_name,
                MaxKeys=1,
            )
        except Exception as exc:  # pragma: no cover - network/client detail varies.
            return False, f'Cloudflare R2 is configured but not reachable: {exc}'
        return True, f"Cloudflare R2 bucket {bucket_name} is reachable."
    return False, f'Unsupported object storage provider: {provider}.'


def store_upload(
    upload,
    *,
    source_module,
    original_filename=None,
    content_type=None,
    uploaded_by=None,
    legacy_file_path=None,
    metadata=None,
    tracker=None,
):
    original_filename = secure_filename(original_filename or getattr(upload, 'filename', '') or '') or 'file.bin'
    stream = getattr(upload, 'stream', upload)
    try:
        stream.seek(0)
    except (AttributeError, OSError):
        pass
    payload = stream.read()
    try:
        stream.seek(0)
    except (AttributeError, OSError):
        pass
    return store_bytes(
        payload,
        source_module=source_module,
        original_filename=original_filename,
        content_type=content_type,
        uploaded_by=uploaded_by,
        legacy_file_path=legacy_file_path,
        metadata=metadata,
        tracker=tracker,
    )


def store_file(
    path,
    *,
    source_module,
    original_filename=None,
    content_type=None,
    uploaded_by=None,
    metadata=None,
    tracker=None,
):
    file_path = Path(path)
    try:
        payload = file_path.read_bytes()
    except OSError as exc:
        raise ObjectStorageError('Stored file could not be read for object upload.', 500) from exc
    return store_bytes(
        payload,
        source_module=source_module,
        original_filename=original_filename or file_path.name,
        content_type=content_type,
        uploaded_by=uploaded_by,
        legacy_file_path=str(file_path),
        metadata=metadata,
        tracker=tracker,
    )


def store_bytes(
    payload,
    *,
    source_module,
    original_filename,
    content_type=None,
    uploaded_by=None,
    legacy_file_path=None,
    metadata=None,
    tracker=None,
):
    payload = payload or b''
    filename = secure_filename(original_filename or '') or 'file.bin'
    object_key = _object_key(source_module, filename)
    content_type = content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    sha256_hash = hashlib.sha256(payload).hexdigest()
    provider = _provider()
    bucket_name = _bucket_name(provider)
    etag = None

    if provider == 'r2':
        try:
            response = _s3_client().put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=payload,
                ContentType=content_type,
                Metadata={
                    'sha256': sha256_hash,
                    'source-module': str(source_module or ''),
                },
            )
            etag = str(response.get('ETag') or '').strip('"') or None
        except Exception as exc:  # pragma: no cover - exercised in integration.
            raise ObjectStorageError(f'Cloudflare R2 upload failed: {exc}', 502) from exc
    elif provider == 'local':
        destination = _local_root() / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        legacy_file_path = legacy_file_path or str(destination)
    else:
        raise ObjectStorageError(f'Unsupported object storage provider: {provider}.', 500)

    stored_object = StoredObject(
        storage_provider=provider,
        bucket_name=bucket_name,
        object_key=object_key,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(payload),
        sha256_hash=sha256_hash,
        etag=etag,
        source_module=source_module,
        legacy_file_path=legacy_file_path,
        object_metadata=metadata or {},
        uploaded_by=int(uploaded_by) if uploaded_by is not None else None,
    )
    db.session.add(stored_object)
    db.session.flush()
    if tracker is not None:
        tracker.track_stored_object(stored_object)
    return stored_object


def read_bytes(stored_object):
    if not stored_object:
        raise ObjectStorageError('Stored object is not linked.', 404)
    provider = stored_object.storage_provider
    if provider == 'r2':
        try:
            response = _s3_client().get_object(
                Bucket=stored_object.bucket_name,
                Key=stored_object.object_key,
            )
            return response['Body'].read()
        except Exception as exc:  # pragma: no cover - exercised in integration.
            error_code = ''
            if hasattr(exc, 'response') and isinstance(getattr(exc, 'response', None), dict):
                error_code = str(exc.response.get('Error', {}).get('Code') or '')
            exc_str = str(exc).lower()
            if error_code in ('NoSuchKey', 'NotFound', '404') or 'nosuchkey' in exc_str:
                raise ObjectStorageError('Requested Cloudflare R2 object was not found.', 404) from exc
            raise ObjectStorageError(f'Cloudflare R2 object is not available: {exc}', 502) from exc
    if provider == 'local':
        path = _local_root() / stored_object.object_key
        if not path.exists() and stored_object.legacy_file_path:
            legacy_path = Path(stored_object.legacy_file_path)
            if _legacy_file_path_is_allowed(legacy_path):
                path = legacy_path
        try:
            return path.read_bytes()
        except OSError as exc:
            raise ObjectStorageError('Stored object is not available on disk.', 404) from exc
    raise ObjectStorageError(f'Unsupported object storage provider: {provider}.', 500)


def download_response(stored_object, *, download_name=None, content_type=None, as_attachment=True):
    payload = read_bytes(stored_object)
    filename = download_name or stored_object.original_filename or 'download.bin'
    response = Response(payload, mimetype=content_type or stored_object.content_type or 'application/octet-stream')
    disposition = 'attachment' if as_attachment else 'inline'
    response.headers['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@contextlib.contextmanager
def temporary_file(stored_object, *, suffix=None):
    payload = read_bytes(stored_object)
    temp_dir = _temp_root()
    temp_dir.mkdir(parents=True, exist_ok=True)
    suffix = suffix if suffix is not None else Path(stored_object.original_filename or '').suffix
    handle = tempfile.NamedTemporaryFile(delete=False, dir=temp_dir, suffix=suffix)
    try:
        handle.write(payload)
        handle.close()
        yield Path(handle.name)
    finally:
        try:
            Path(handle.name).unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning('Unable to delete temporary object file: %s', handle.name)


def object_uri(stored_object):
    if not stored_object:
        return None
    if stored_object.storage_provider == 'local':
        return stored_object.legacy_file_path or str(_local_root() / stored_object.object_key)
    return f'{stored_object.storage_provider}://{stored_object.bucket_name}/{stored_object.object_key}'


def delete_stored_object(stored_object, *, strict=False):
    if not stored_object:
        return
    provider = stored_object.storage_provider
    if provider == 'r2':
        try:
            _s3_client().delete_object(
                Bucket=stored_object.bucket_name,
                Key=stored_object.object_key,
            )
        except Exception as exc:
            if strict:
                raise ObjectStorageError('Cloudflare R2 deletion failed; cleanup will be retried.', 502) from exc
            current_app.logger.warning('Failed to delete object from Cloudflare R2: %s', exc)
    elif provider == 'local':
        path = _local_root() / stored_object.object_key
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            if strict:
                raise ObjectStorageError('Local object deletion failed; cleanup will be retried.', 500) from exc
        if stored_object.legacy_file_path:
            legacy_path = Path(stored_object.legacy_file_path)
            if _legacy_file_path_is_allowed(legacy_path):
                try:
                    legacy_path.unlink(missing_ok=True)
                except OSError as exc:
                    if strict:
                        raise ObjectStorageError('Local object deletion failed; cleanup will be retried.', 500) from exc
    db.session.delete(stored_object)


def _provider():
    from app.services.integration_config_service import resolve_storage_runtime_value
    return str(resolve_storage_runtime_value('OBJECT_STORAGE_PROVIDER') or 'local').strip().lower() or 'local'


def _bucket_name(provider):
    if provider == 'r2':
        from app.services.integration_config_service import resolve_storage_runtime_value
        bucket = resolve_storage_runtime_value('R2_BUCKET_NAME')
        if not bucket:
            raise ObjectStorageError('R2_BUCKET_NAME is required for Cloudflare R2 storage.', 500)
        return bucket
    from app.services.integration_config_service import resolve_storage_runtime_value
    return resolve_storage_runtime_value('OBJECT_STORAGE_LOCAL_BUCKET') or 'local'


def _object_key(source_module, filename):
    now = datetime.now(timezone.utc)
    from app.services.integration_config_service import resolve_storage_runtime_value
    prefix = str(resolve_storage_runtime_value('OBJECT_STORAGE_BUCKET_PREFIX') or 'comet').strip().strip('/')
    environment = str(current_app.config.get('OBJECT_STORAGE_ENV') or 'local').strip().strip('/') or 'local'
    safe_source = secure_filename(str(source_module or 'files')).replace('_', '-').lower() or 'files'
    safe_filename = secure_filename(filename or 'file.bin') or 'file.bin'
    if len(safe_filename) > 180:
        ext = Path(safe_filename).suffix
        stem = Path(safe_filename).stem[:max(1, 180 - len(ext))]
        safe_filename = f'{stem}{ext}'
    return '/'.join([
        prefix,
        environment,
        safe_source,
        f'{now:%Y/%m}',
        f'{uuid.uuid4().hex}-{safe_filename}',
    ])


def _local_root():
    configured = current_app.config.get('OBJECT_STORAGE_LOCAL_DIR')
    if configured:
        return Path(configured)
    return Path(current_app.instance_path) / 'object_storage'


def _temp_root():
    configured = current_app.config.get('OBJECT_STORAGE_TEMP_DIR')
    if configured:
        return Path(configured)
    return Path(current_app.instance_path) / 'storage_tmp'


def _legacy_file_path_is_allowed(path):
    try:
        resolved = Path(path).resolve(strict=False)
    except (OSError, RuntimeError):
        return False

    roots = [_local_root(), Path(current_app.instance_path)]
    for root in roots:
        try:
            resolved.relative_to(root.resolve(strict=False))
            return True
        except (OSError, RuntimeError, ValueError):
            continue
    return False


def _s3_client(config=None):
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError as exc:  # pragma: no cover - dependency check.
        raise ObjectStorageError('boto3 is required for Cloudflare R2 storage.', 500) from exc

    from app.services.integration_config_service import resolve_storage_runtime_value
    endpoint_url = resolve_storage_runtime_value('R2_ENDPOINT_URL')
    access_key = resolve_storage_runtime_value('R2_ACCESS_KEY_ID')
    secret_key = resolve_storage_runtime_value('R2_SECRET_ACCESS_KEY')
    if not endpoint_url or not access_key or not secret_key:
        raise ObjectStorageError('Cloudflare R2 credentials are incomplete.', 500)
    return boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=resolve_storage_runtime_value('R2_REGION') or 'auto',
        config=config or BotoConfig(signature_version='s3v4'),
    )
