from app.services import notice_follow_up_service
from app.tasks import celery_app


@celery_app.task(name='app.tasks.notice_follow_up.notify_pending_notice_actions')
def notify_pending_notice_actions():
    """Create operator notifications for notices waiting on release or receipt."""
    return notice_follow_up_service.notify_pending_notice_actions()
