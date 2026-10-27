import logging
from app.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name='app.tasks.db_backup.run_scheduled_backup')
def run_scheduled_backup(retention_days=30, max_retained=30):
    """
    Automated daily database backup task.
    Creates a compressed pg_dump snapshot, uploads it to object storage,
    and prunes backups older than the retention threshold.
    """
    from app.services import backup_service

    logger.info('Starting scheduled daily database backup...')
    try:
        backup_result = backup_service.create_backup(user_id=None, trigger_type='scheduled')
        logger.info('Scheduled database backup completed: %s', backup_result.get('filename'))
    except Exception as exc:
        logger.error('Scheduled database backup failed: %s', exc, exc_info=True)
        from app.services.operational_event_service import record_operational_event
        record_operational_event(
            severity='ERROR',
            component='backup',
            event_name='scheduled_backup_failure',
            message=f"Scheduled database backup failed: {exc}",
            context_data={'trigger_type': 'scheduled', 'error': str(exc)[:500]},
            exc_info=exc,
        )
        return {'status': 'failed', 'error': str(exc)}

    try:
        pruned = backup_service.prune_old_backups(retention_days=retention_days, max_retained=max_retained)
        logger.info('Pruned %d outdated backup archives (retention: %d days).', pruned, retention_days)
    except Exception as exc:
        logger.warning('Failed to prune old backups: %s', exc)

    return {'status': 'success', 'backup': backup_result}
