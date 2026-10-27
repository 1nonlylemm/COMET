import hashlib
import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Response, current_app
from sqlalchemy.engine import make_url

from app.extensions import db
from app.models.backup import DbBackupRecord
from app.services import audit_service, maintenance_service, object_storage_service

logger = logging.getLogger(__name__)

REQUIRED_RESTORE_CONFIRMATION_PHRASE = 'CONFIRM-RESTORE-OVERWRITE'


class BackupError(Exception):
    def __init__(self, message, status_code=500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _format_timestamp(dt=None):
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime('%Y%m%d_%H%M%S')


def create_backup(user_id=None, trigger_type='manual', db_uri=None):
    start_time = time.time()
    db_uri = db_uri or current_app.config.get('SQLALCHEMY_DATABASE_URI') or os.environ.get('DATABASE_URL')
    if not db_uri:
        raise BackupError('Database connection string is not configured.', 500)

    parsed_url = make_url(db_uri)
    backend_name = parsed_url.get_backend_name()
    timestamp_str = _format_timestamp()
    prefix = 'pre_restore_' if trigger_type == 'pre_restore_safety' else 'comet_backup_'
    filename = f"{prefix}{timestamp_str}.dump"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = os.path.join(temp_dir, filename)

        try:
            with object_storage_service.storage_transaction() as storage_tx:
                if backend_name in ('postgresql', 'postgres'):
                    _run_postgres_dump(parsed_url, temp_file_path)
                elif backend_name == 'sqlite':
                    _run_sqlite_dump(parsed_url, temp_file_path)
                else:
                    raise BackupError(f"Unsupported database engine for backup: {backend_name}", 400)

                # Validate generated file
                if not os.path.exists(temp_file_path) or os.path.getsize(temp_file_path) == 0:
                    raise BackupError('Generated backup file is empty or missing.', 500)

                byte_size = os.path.getsize(temp_file_path)
                sha256_checksum = _compute_sha256(temp_file_path)

                # Store in object storage (Cloudflare R2 with local fallback)
                stored_object = object_storage_service.store_file(
                    temp_file_path,
                    source_module='db_backup',
                    original_filename=filename,
                    content_type='application/octet-stream',
                    uploaded_by=user_id,
                    metadata={
                        'trigger_type': trigger_type,
                        'database_backend': backend_name,
                        'sha256_checksum': sha256_checksum,
                    },
                    tracker=storage_tx,
                )

                duration = time.time() - start_time
                record = DbBackupRecord(
                    filename=filename,
                    stored_object_id=stored_object.id,
                    status='completed',
                    byte_size=byte_size,
                    sha256_checksum=sha256_checksum,
                    trigger_type=trigger_type,
                    storage_provider=stored_object.storage_provider,
                    created_by_user_id=user_id,
                    duration_seconds=duration,
                )
                db.session.add(record)
                db.session.commit()
                storage_tx.commit()

            # Audit trail
            try:
                audit_service.log_action(
                    user_id=user_id,
                    action='db_backup_created',
                    entity_type='db_backup',
                    entity_id=record.id,
                    new_value=record.to_dict(),
                )
                db.session.commit()
            except Exception:
                pass

            return record.to_dict()

        except Exception as exc:
            duration = time.time() - start_time
            err_msg = str(exc)
            failed_record = DbBackupRecord(
                filename=filename,
                status='failed',
                byte_size=0,
                trigger_type=trigger_type,
                created_by_user_id=user_id,
                duration_seconds=duration,
                error_message=err_msg,
            )
            db.session.add(failed_record)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            if isinstance(exc, BackupError):
                raise
            if isinstance(exc, object_storage_service.ObjectStorageError):
                raise BackupError(f"Backup storage failed: {exc.message}", exc.status_code) from exc
            raise BackupError(f"Backup failed: {err_msg}", 500) from exc


def _run_postgres_dump(parsed_url, output_path):
    env = os.environ.copy()
    if parsed_url.password:
        env['PGPASSWORD'] = str(parsed_url.password)

    cmd = [
        'pg_dump',
        '-Fc',
        '--no-owner',
        '--no-acl',
    ]

    if parsed_url.host:
        cmd.extend(['-h', str(parsed_url.host)])
    if parsed_url.port:
        cmd.extend(['-p', str(parsed_url.port)])
    if parsed_url.username:
        cmd.extend(['-U', str(parsed_url.username)])
    if parsed_url.database:
        cmd.extend(['-d', str(parsed_url.database)])

    cmd.extend(['-f', output_path])

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise BackupError(f"pg_dump error (code {res.returncode}): {res.stderr.strip() or res.stdout.strip()}")


def _run_sqlite_dump(parsed_url, output_path):
    db_file = parsed_url.database
    if not db_file or db_file == ':memory:':
        con = db.session.connection().connection
        with open(output_path, 'w', encoding='utf-8') as f:
            for line in con.iterdump():
                f.write(f"{line}\n")
    else:
        src = sqlite3.connect(db_file)
        dst = sqlite3.connect(output_path)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()


def _compute_sha256(path):
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def list_backups(page=1, per_page=20):
    page = max(int(page or 1), 1)
    per_page = min(max(int(per_page or 20), 1), 100)

    query = DbBackupRecord.query.order_by(DbBackupRecord.created_at.desc())
    total = query.count()
    records = query.offset((page - 1) * per_page).limit(per_page).all()

    # Calculate summary KPIs
    total_bytes = db.session.query(db.func.coalesce(db.func.sum(DbBackupRecord.byte_size), 0)).filter(
        DbBackupRecord.status == 'completed'
    ).scalar() or 0

    last_record = DbBackupRecord.query.filter_by(status='completed').order_by(DbBackupRecord.created_at.desc()).first()

    provider_status, provider_msg = object_storage_service.provider_ready()
    provider_name = object_storage_service._provider()

    return {
        'backups': [r.to_dict() for r in records],
        'meta': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page if total > 0 else 1,
        },
        'summary': {
            'total_count': total,
            'completed_count': DbBackupRecord.query.filter_by(status='completed').count(),
            'failed_count': DbBackupRecord.query.filter_by(status='failed').count(),
            'total_bytes': int(total_bytes),
            'last_backup_at': last_record.created_at.isoformat() if last_record else None,
            'storage_provider': provider_name,
            'provider_ready': provider_status,
            'provider_message': provider_msg,
        },
    }


def get_backup(backup_id):
    record = db.session.get(DbBackupRecord, int(backup_id))
    if not record:
        raise BackupError('Backup record not found.', 404)
    return record


def download_backup(backup_id):
    record = get_backup(backup_id)
    if record.status != 'completed' or not record.stored_object_id:
        raise BackupError('Cannot download incomplete or failed backup archive.', 400)

    stored_obj = record.stored_object
    if not stored_obj:
        raise BackupError('Associated backup stored object is missing.', 404)

    return object_storage_service.download_response(
        stored_obj,
        download_name=record.filename,
    )


ALLOWED_RESTORE_TARGET_HOSTS = {'comet-throwaway-db', 'comet-clone-db'}
DISALLOWED_RESTORE_DATABASES = {'workspace_db', 'comet_prod', 'comet_staging', 'pdmu'}


def _validate_restore_target_safety(target_uri):
    if not target_uri:
        raise BackupError(
            "Safety Violation: Restore target database URL must be explicitly provided during testing.",
            403,
        )

    parsed = make_url(target_uri)
    host = (parsed.host or '').lower()
    dbname = (parsed.database or '').lower()
    backend = parsed.get_backend_name()

    if backend == 'sqlite':
        return

    if dbname in DISALLOWED_RESTORE_DATABASES or 'workspace' in dbname or 'prod' in dbname or 'staging' in dbname or host in ('db', 'comet-db-1'):
        raise BackupError(
            f"Safety Guard Blocked: Database '{parsed.database}' at host '{parsed.host}' is protected from restore operations. Restores are restricted to approved sandbox/throwaway targets only.",
            403,
        )

    if host not in ALLOWED_RESTORE_TARGET_HOSTS:
        raise BackupError(
            f"Safety Guard Blocked: Host '{parsed.host}' is not on the approved restore target allowlist. Only approved sandbox/throwaway instances are permitted.",
            403,
        )


def restore_backup(backup_id, confirmation_phrase, target_db_url=None, user_id=None):
    """
    Executes a high-risk database restore from an existing backup archive into a target database.
    Enforces exact confirmation phrase, strict safety guard on target database,
    creates an auto pre-restore safety snapshot, and locks down non-sysadmin traffic with 503 Maintenance Mode.
    """
    if str(confirmation_phrase).strip() != REQUIRED_RESTORE_CONFIRMATION_PHRASE:
        raise BackupError(
            f"Invalid confirmation phrase. You must provide the exact phrase '{REQUIRED_RESTORE_CONFIRMATION_PHRASE}' to authorize a database restore.",
            400,
        )

    target_uri = target_db_url or current_app.config.get('SQLALCHEMY_DATABASE_URI') or os.environ.get('DATABASE_URL')
    _validate_restore_target_safety(target_uri)

    record = get_backup(backup_id)
    if record.status != 'completed' or not record.stored_object_id:
        raise BackupError('Cannot restore from an incomplete or failed backup archive.', 400)

    stored_obj = record.stored_object
    if not stored_obj:
        raise BackupError('Associated backup stored object is missing from storage.', 404)

    # 1. Download and verify backup archive integrity
    payload = object_storage_service.read_bytes(stored_obj)
    downloaded_checksum = hashlib.sha256(payload).hexdigest()
    if record.sha256_checksum and downloaded_checksum != record.sha256_checksum:
        raise BackupError(
            f"Backup integrity verification failed: computed hash {downloaded_checksum} != expected {record.sha256_checksum}",
            400,
        )

    parsed_target_url = make_url(target_uri)
    target_backend = parsed_target_url.get_backend_name()

    # 2. Auto pre-restore safety snapshot
    logger.info('Taking automated pre-restore safety snapshot of target database...')
    pre_restore_record = create_backup(
        user_id=user_id,
        trigger_type='pre_restore_safety',
        db_uri=target_uri,
    )
    logger.info('Pre-restore safety snapshot created: ID #%d (%s)', pre_restore_record['id'], pre_restore_record['filename'])

    # 3. Enter Maintenance Mode
    maintenance_service.set_maintenance_mode(
        True,
        reason='System is currently undergoing a database restore. Please try again shortly.',
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = os.path.join(temp_dir, record.filename)
        with open(temp_file_path, 'wb') as f:
            f.write(payload)

        try:
            if target_backend in ('postgresql', 'postgres'):
                _run_postgres_restore(parsed_target_url, temp_file_path)
            elif target_backend == 'sqlite':
                _run_sqlite_restore(parsed_target_url, temp_file_path)
            else:
                raise BackupError(f"Unsupported database engine for restore: {target_backend}", 400)

            # Audit trail
            try:
                audit_service.log_action(
                    user_id=user_id,
                    action='db_restore_executed',
                    entity_type='db_backup',
                    entity_id=record.id,
                    new_value={
                        'backup_id': record.id,
                        'backup_filename': record.filename,
                        'pre_restore_snapshot_id': pre_restore_record['id'],
                        'pre_restore_snapshot_filename': pre_restore_record['filename'],
                        'target_database': str(parsed_target_url.database),
                    },
                )
                db.session.commit()
            except Exception:
                pass

            return {
                'status': 'restored',
                'backup_id': record.id,
                'filename': record.filename,
                'pre_restore_snapshot_id': pre_restore_record['id'],
                'pre_restore_snapshot_filename': pre_restore_record['filename'],
                'target_database': str(parsed_target_url.database),
                'restored_at': datetime.now(timezone.utc).isoformat(),
            }

        finally:
            # Always clear maintenance mode
            maintenance_service.set_maintenance_mode(False)


def _run_postgres_restore(parsed_url, input_path):
    env = os.environ.copy()
    if parsed_url.password:
        env['PGPASSWORD'] = str(parsed_url.password)

    cmd = [
        'pg_restore',
        '--clean',
        '--if-exists',
        '--no-owner',
        '--no-acl',
    ]
    if parsed_url.host:
        cmd.extend(['-h', str(parsed_url.host)])
    if parsed_url.port:
        cmd.extend(['-p', str(parsed_url.port)])
    if parsed_url.username:
        cmd.extend(['-U', str(parsed_url.username)])
    if parsed_url.database:
        cmd.extend(['-d', str(parsed_url.database)])

    cmd.append(input_path)

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    # Return code > 1 represents fatal errors in pg_restore
    if res.returncode > 1:
        raise BackupError(f"pg_restore error (code {res.returncode}): {res.stderr.strip() or res.stdout.strip()}")


def _run_sqlite_restore(parsed_url, input_path):
    db_file = parsed_url.database
    if not db_file or db_file == ':memory:':
        with open(input_path, 'r', encoding='utf-8') as f:
            script = f.read()
        con = db.session.connection().connection
        con.executescript(script)
    else:
        shutil.copyfile(input_path, db_file)


def prune_old_backups(retention_days=30, max_retained=30):
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    all_completed = DbBackupRecord.query.filter_by(status='completed').order_by(DbBackupRecord.created_at.desc()).all()

    to_prune = []
    for idx, rec in enumerate(all_completed):
        if idx >= max_retained or rec.created_at.replace(tzinfo=timezone.utc if rec.created_at.tzinfo is None else rec.created_at.tzinfo) < cutoff:
            to_prune.append(rec)

    pruned_count = 0
    for rec in to_prune:
        if rec.stored_object:
            try:
                object_storage_service.delete_stored_object(rec.stored_object)
            except Exception:
                pass
        
        try:
            audit_service.log_action(
                user_id=None,
                action='db_backup_pruned',
                entity_type='db_backup',
                entity_id=rec.id,
                old_value=rec.to_dict(),
            )
        except Exception:
            pass

        db.session.delete(rec)
        pruned_count += 1

    if pruned_count > 0:
        db.session.commit()

    return pruned_count
