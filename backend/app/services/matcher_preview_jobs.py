"""Durable, owner-scoped preview jobs; originals live in shared object storage."""
import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from flask import current_app
from redis import Redis
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import MatcherPreviewJob, StoredObject
from app.services import document_intelligence_service as matcher, object_storage_service as storage
from app.services.upload_validation import validate_upload_filename

TTL_SECONDS = 7200
LEASE_SECONDS = 120
HEARTBEAT_SECONDS = 20
REDISPATCH_SECONDS = 300
PREFIX = 'comet:matcher-preview:'  # Read-only compatibility for pre-migration results.
TERMINAL = ('completed', 'failed')


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _redis():
    return Redis.from_url(current_app.config['CELERY_RESULT_BACKEND'],
                          socket_connect_timeout=3, socket_timeout=3, decode_responses=True)


def _public(job):
    return {key: job.get(key) for key in ('job_id', 'status', 'stage', 'completed_pages', 'total_pages', 'result', 'error')}


def _dispatch(job_id):
    from app.tasks import celery_app
    celery_app.send_task('app.tasks.matcher_preview.run', args=[job_id],
                         expires=TTL_SECONDS, soft_time_limit=1200, time_limit=1260,
                         retry=False)


def start(upload, user_id, project_id=None, requirement_id=None):
    matcher._ensure_upload(upload)
    if project_id is not None:
        matcher._project_with_access(project_id, user_id)
    if requirement_id is not None:
        destination = matcher._project_requirement_with_access(requirement_id, user_id)
        if project_id is not None and destination.project_id != project_id:
            raise matcher.DocumentIntelligenceError('Selected requirement does not belong to the selected project.', 422)
    name = validate_upload_filename(upload.filename,
        error_factory=lambda message, code: matcher.DocumentIntelligenceError(message, code), label='File')
    mime = matcher._validate_upload(name, upload)
    identifier = uuid.uuid4().hex
    payload = dict(job_id=identifier, owner_id=str(user_id), status='queued', stage='queued',
                   completed_pages=0, total_pages=None, result=None, filename=name,
                   project_id=project_id, requirement_id=requirement_id)
    tracker = storage.StorageCompensationTracker()
    try:
        obj = storage.store_upload(upload, source_module='matcher_preview', original_filename=name,
            content_type=mime, uploaded_by=user_id, metadata={'job_id': identifier}, tracker=tracker)
        row = MatcherPreviewJob(id=identifier, owner_id=int(user_id), object_id=obj.id,
            status='queued', payload=payload, expires_at=_now() + timedelta(seconds=TTL_SECONDS))
        db.session.add(row)
        db.session.commit()
        tracker.commit()
    except Exception as exc:
        db.session.rollback()
        tracker.compensate()
        raise matcher.DocumentIntelligenceError('Unable to stage document processing. Please try again.', 503) from exc
    try:
        _dispatch(identifier)
    except Exception as exc:
        db.session.rollback()
        row = db.session.get(MatcherPreviewJob, identifier)
        # A publisher can fail after delivery. Never overwrite a worker that has claimed it.
        if row and row.status == 'queued':
            if _fail_if_current(row, 'queued', 'Unable to queue document processing. Please try again.'):
                _cleanup_input(identifier)
                raise matcher.DocumentIntelligenceError('Unable to queue document processing. Please try again.', 503) from exc
            row = db.session.get(MatcherPreviewJob, identifier)
        if row and row.status != 'queued':
            return _public(dict(row.payload, status=row.status))
        raise matcher.DocumentIntelligenceError('Unable to queue document processing. Please try again.', 503) from exc
    return _public(payload)


def _fail_if_current(row, status, error, *, stale=False):
    payload = dict(row.payload, status='failed', stage='failed', result=None, error=error)
    query = MatcherPreviewJob.query.filter_by(id=row.id, status=status)
    if stale:
        query = query.filter(MatcherPreviewJob.lease_expires_at <= _now())
    changed = query.update(dict(status='failed', payload=payload, lease_token=None,
        lease_expires_at=None, updated_at=_now(), expires_at=_now() + timedelta(seconds=TTL_SECONDS)),
        synchronize_session=False)
    db.session.commit()
    return bool(changed)


def get(job_id, user_id):
    if len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
        raise matcher.DocumentIntelligenceError('Scan job not found.', 404)
    row = db.session.get(MatcherPreviewJob, job_id)
    if row is None:
        # Already-completed previews from the previous release remain readable until Redis expiry.
        try:
            raw = _redis().get(PREFIX + job_id)
        except Exception:
            raw = None
        legacy = json.loads(raw) if raw else None
        if legacy and legacy.get('owner_id') == str(user_id):
            if legacy.get('status') not in TERMINAL:
                legacy.update(status='failed', stage='failed', result=None,
                    error='This scan predates the processing update. Please upload the document again.')
            return _public(legacy)
        raise matcher.DocumentIntelligenceError('Scan job expired or not found. Please upload the document again.', 404)
    if row.owner_id != int(user_id):
        raise matcher.DocumentIntelligenceError('Scan job not found.', 404)
    if row.status == 'processing' and row.lease_expires_at <= _now():
        _fail_if_current(row, 'processing', 'Document processing stopped unexpectedly. Please upload the document again.', stale=True)
        row = db.session.get(MatcherPreviewJob, job_id)
    if row.expires_at <= _now():
        raise matcher.DocumentIntelligenceError('Scan job expired or not found. Please upload the document again.', 404)
    return _public(dict(row.payload, status=row.status))


class LostLease(RuntimeError):
    pass


def _owned(job_id, token):
    return MatcherPreviewJob.query.filter_by(id=job_id, status='processing', lease_token=token).filter(
        MatcherPreviewJob.lease_expires_at > _now())


@contextmanager
def _heartbeat(job_id, token):
    app = current_app._get_current_object()
    stopped = threading.Event()
    def beat():
        with app.app_context():
            while not stopped.wait(HEARTBEAT_SECONDS):
                try:
                    changed = _owned(job_id, token).update(
                        dict(lease_expires_at=_now() + timedelta(seconds=LEASE_SECONDS)), synchronize_session=False)
                    db.session.commit()
                    if not changed:
                        return
                except Exception:
                    db.session.rollback()
                    app.logger.exception('Preview heartbeat failed: %s', job_id)
    thread = threading.Thread(target=beat, daemon=True, name='matcher-preview-heartbeat')
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=1)


def _write_owned(job_id, token, payload):
    terminal = payload['status'] in TERMINAL
    values = dict(status=payload['status'], payload=dict(payload), updated_at=_now(),
                  expires_at=_now() + timedelta(seconds=TTL_SECONDS))
    if terminal:
        values.update(lease_token=None, lease_expires_at=None)
    else:
        values['lease_expires_at'] = _now() + timedelta(seconds=LEASE_SECONDS)
    if not _owned(job_id, token).update(values, synchronize_session=False):
        db.session.rollback()
        raise LostLease('Preview worker no longer owns the job.')
    db.session.commit()


def run(job_id):
    token = uuid.uuid4().hex
    claimed = MatcherPreviewJob.query.filter_by(id=job_id, status='queued').filter(
        MatcherPreviewJob.expires_at > _now()).update(dict(status='processing', lease_token=token,
        lease_expires_at=_now() + timedelta(seconds=LEASE_SECONDS), updated_at=_now()), synchronize_session=False)
    db.session.commit()
    if not claimed:
        return  # Duplicate delivery cannot repeat OCR or AI.
    row = db.session.get(MatcherPreviewJob, job_id)
    payload = dict(row.payload)
    with _heartbeat(job_id, token):
        try:
            obj = db.session.get(StoredObject, row.object_id)
            if obj is None:
                raise RuntimeError('Staged document is unavailable.')
            def progress(update):
                payload.update(update, status='processing')
                _write_owned(job_id, token, payload)
            progress({'stage': 'extracting', 'completed_pages': 0, 'total_pages': None})
            with storage.temporary_file(obj) as path, open(path, 'rb') as stream:
                upload = FileStorage(stream=stream, filename=payload['filename'], content_type=obj.content_type)
                result = matcher.preview_document_mapping(payload['project_id'], upload, payload['owner_id'],
                    project_requirement_id=payload['requirement_id'], progress_callback=progress)
            payload.update(status='completed', stage='completed', result=result)
        except LostLease:
            return
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Matcher preview job failed: %s', job_id)
            payload.update(status='failed', stage='failed', result=None,
                error='Document processing failed. Please try again or use manual review.')
        # A failed commit propagates. Keep the input; recovery will fail the job explicitly.
        _write_owned(job_id, token, payload)
    _cleanup_input(job_id)


def _cleanup_input(job_id):
    try:
        row = db.session.get(MatcherPreviewJob, job_id)
        if row is None or row.status not in TERMINAL or row.object_id is None:
            return False
        obj = db.session.get(StoredObject, row.object_id)
        if obj:
            storage.delete_stored_object(obj, strict=True)
        row.object_id = None
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Preview upload cleanup deferred: %s', job_id)
        return False


def recover():
    """Fail abandoned execution leases; redispatch queued jobs lost by the broker."""
    recovered = 0
    stale = MatcherPreviewJob.query.filter_by(status='processing').filter(
        MatcherPreviewJob.lease_expires_at <= _now()).limit(100).all()
    for row in stale:
        if _fail_if_current(row, 'processing', 'Document processing stopped unexpectedly. Please upload the document again.', stale=True):
            _cleanup_input(row.id)
            recovered += 1
    queued = MatcherPreviewJob.query.filter_by(status='queued').filter(
        MatcherPreviewJob.updated_at < _now() - timedelta(seconds=REDISPATCH_SECONDS)).limit(100).all()
    for row in queued:
        if row.expires_at <= _now():
            _fail_if_current(row, 'queued', 'Document processing expired before it could start. Please try again.')
            _cleanup_input(row.id)
        else:
            changed = MatcherPreviewJob.query.filter_by(id=row.id, status='queued').filter(
                MatcherPreviewJob.updated_at < _now() - timedelta(seconds=REDISPATCH_SECONDS)).update(
                    dict(updated_at=_now()), synchronize_session=False)
            db.session.commit()
            if changed:
                try:
                    _dispatch(row.id)
                    recovered += 1
                except Exception:
                    current_app.logger.exception('Preview redispatch deferred: %s', row.id)
    return recovered


def cleanup():
    recover()
    count = 0
    pending = MatcherPreviewJob.query.filter(MatcherPreviewJob.status.in_(TERMINAL),
        MatcherPreviewJob.object_id.isnot(None)).limit(100).all()
    for row in pending:
        count += int(_cleanup_input(row.id))
    # Orphans include legacy previews and uploads whose queue operation failed.
    cutoff = _now() - timedelta(hours=3)
    linked = db.session.query(MatcherPreviewJob.object_id).filter(MatcherPreviewJob.object_id.isnot(None))
    for obj in StoredObject.query.filter(StoredObject.source_module == 'matcher_preview',
            StoredObject.created_at < cutoff, ~StoredObject.id.in_(linked)).limit(100).all():
        try:
            storage.delete_stored_object(obj, strict=True)
            db.session.commit()
            count += 1
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Orphan preview cleanup deferred: %s', obj.id)
    MatcherPreviewJob.query.filter(MatcherPreviewJob.expires_at <= _now(),
        MatcherPreviewJob.object_id.is_(None)).delete(synchronize_session=False)
    db.session.commit()
    return count
