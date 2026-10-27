import logging
from datetime import datetime, timezone

from app.extensions import db
from app.models import Notification, NotificationDelivery, User
from app.services import email_service
from app.services.operational_event_service import record_operational_event
from app.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name='app.tasks.notification_dispatcher.dispatch_notification_email',
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def dispatch_notification_email(self, notification_id):
    """
    Asynchronously dispatch notification email.

    Guarantees:
    - Retries transient failures with exponential backoff (up to 3 times)
    - Records attempted_at, sent_at, failed_at, error_message
    - Never throws an unhandled exception to domain callers
    - Never duplicates deliveries
    """
    delivery = NotificationDelivery.query.filter_by(
        notification_id=notification_id,
        channel='email',
    ).first()

    if not delivery:
        if self.request.retries < self.max_retries:
            logger.info(
                'NotificationDelivery for notification %s not yet visible; retrying in 2s (attempt %s/%s)',
                notification_id,
                self.request.retries + 1,
                self.max_retries + 1,
            )
            raise self.retry(countdown=2)
        logger.warning('NotificationDelivery for notification %s not found; skipping', notification_id)
        return {'status': 'skipped', 'reason': 'delivery_not_found'}


    if delivery.status == 'sent':
        return {'status': 'skipped', 'reason': 'already_sent'}

    notification = db.session.get(Notification, notification_id)
    if not notification:
        delivery.status = 'failed'
        delivery.failed_at = datetime.now(timezone.utc)
        delivery.error_message = 'Notification record not found'
        db.session.commit()
        task_id = getattr(self.request, 'id', None) if getattr(self, 'request', None) else None
        record_operational_event(
            severity='ERROR',
            component='celery_worker',
            event_name='notification_delivery_failure',
            message=f"Notification email delivery failed: notification {notification_id} record not found",
            operation_id=str(task_id) if task_id else None,
            context_data={
                'notification_id': notification_id,
                'delivery_id': delivery.id,
                'reason': 'notification_not_found',
            },
        )
        return {'status': 'failed', 'reason': delivery.error_message}

    recipient = db.session.get(User, notification.user_id)
    if not recipient or not recipient.is_active or not recipient.email:
        delivery.status = 'failed'
        delivery.failed_at = datetime.now(timezone.utc)
        delivery.error_message = 'Recipient inactive or missing email'
        db.session.commit()
        task_id = getattr(self.request, 'id', None) if getattr(self, 'request', None) else None
        record_operational_event(
            severity='WARNING',
            component='celery_worker',
            event_name='notification_delivery_failure',
            message=f"Notification email delivery skipped: recipient inactive or missing email for notification {notification_id}",
            operation_id=str(task_id) if task_id else None,
            context_data={
                'notification_id': notification_id,
                'delivery_id': delivery.id,
                'user_id': notification.user_id,
                'reason': 'recipient_inactive_or_missing_email',
            },
        )
        return {'status': 'failed', 'reason': delivery.error_message}

    delivery.attempted_at = datetime.now(timezone.utc)

    try:
        result = email_service.send_notification_email(notification, recipient)
        status = result.get('status')
        if status in ('sent', 'skipped'):
            delivery.status = 'sent'
            delivery.sent_at = datetime.now(timezone.utc)
            delivery.provider_message_id = result.get('message_id')
            db.session.commit()
            return {'status': 'sent', 'recipient': recipient.email}
        else:
            raise Exception(result.get('message', 'Email dispatch failed'))
    except Exception as exc:
        logger.warning(
            'Failed to dispatch notification email for notification %s (attempt %s/%s): %s',
            notification_id,
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
        )
        if self.request.retries < self.max_retries:
            db.session.rollback()
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        else:
            delivery.status = 'failed'
            delivery.failed_at = datetime.now(timezone.utc)
            delivery.error_message = str(exc)[:1000]
            db.session.commit()
            task_id = getattr(self.request, 'id', None) if getattr(self, 'request', None) else None
            record_operational_event(
                severity='ERROR',
                component='celery_worker',
                event_name='notification_delivery_failure',
                message=f"Notification email delivery failed permanently for notification {notification_id}: {exc}",
                operation_id=str(task_id) if task_id else None,
                context_data={
                    'notification_id': notification_id,
                    'delivery_id': delivery.id,
                    'user_id': notification.user_id,
                    'retries_exhausted': True,
                    'retries': getattr(self.request, 'retries', 0) if getattr(self, 'request', None) else 0,
                    'max_retries': self.max_retries,
                    'error': str(exc)[:500],
                },
                exc_info=exc,
            )
            return {'status': 'failed', 'error': delivery.error_message}


@celery_app.task(name='app.tasks.notification_dispatcher.recover_pending_notification_deliveries')
def recover_pending_notification_deliveries(limit=100, max_age_seconds=None):
    """
    Recover orphaned pending notification deliveries whose initial dispatch enqueue failed.
    """
    from app.services import notification_service
    return notification_service.recover_pending_notification_deliveries(limit=limit, max_age_seconds=max_age_seconds)
