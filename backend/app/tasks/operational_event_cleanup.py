import logging
from app.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name='app.tasks.operational_event_cleanup.cleanup_operational_events')
def cleanup_operational_events(retention_days=30, max_events=10000):
    """
    Automated scheduled operational event cleanup task.
    Prunes events older than retention_days (default 30) and bounds
    total stored events to the newest max_events (default 10,000).
    """
    from app.services.operational_event_service import cleanup_operational_events as run_cleanup

    logger.info(
        'Starting scheduled operational event cleanup (retention_days=%d, max_events=%d)...',
        retention_days,
        max_events,
    )
    result = run_cleanup(retention_days=retention_days, max_events=max_events)
    if result.get('status') == 'success':
        logger.info(
            'Scheduled operational event cleanup completed: %d total deleted (%d by age, %d by row limit).',
            result.get('total_deleted', 0),
            result.get('deleted_by_age', 0),
            result.get('deleted_by_limit', 0),
        )
    else:
        logger.warning('Scheduled operational event cleanup failed: %s', result.get('error'))
    return result
