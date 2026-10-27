from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import EscalationNotice, Notification, StaffLguAssignment, User
from app.services import working_day_service


PENDING_RELEASE_DAYS = 1
PENDING_RECEIPT_DAYS = 2
FOLLOW_UP_WORKING_DAYS = 15


def notify_pending_notice_actions(now=None):
    reference_now = _to_aware_datetime(now or datetime.now(timezone.utc))
    created = 0
    checked = 0

    for notice in _pending_release_notices(reference_now):
        checked += 1
        project_name = (
            notice.project.project_name
            if (notice.project and getattr(notice.project, 'project_name', None))
            else "Assigned Project"
        )
        created += _notify_notice_users(
            notice,
            notification_type='notice_pending_release',
            title='Action Required: Formal Notice Awaiting Release',
            message=f'{notice.title} for {project_name} has been finalized and approved but has not been marked as released. Please complete the transmittal.',
        )

    for notice in _pending_receipt_notices(reference_now):
        checked += 1
        project_name = (
            notice.project.project_name
            if (notice.project and getattr(notice.project, 'project_name', None))
            else "Assigned Project"
        )
        created += _notify_notice_users(
            notice,
            notification_type='notice_pending_receipt',
            title='Action Required: Record Notice Receipt Date',
            message=f'{notice.title} for {project_name} was released to the LGU, but no acknowledgment receipt date has been logged. Please record receipt.',
        )

    for notice in _follow_up_due_notices(reference_now):
        checked += 1
        project_name = (
            notice.project.project_name
            if (notice.project and getattr(notice.project, 'project_name', None))
            else "Assigned Project"
        )
        created += _notify_notice_users(
            notice,
            notification_type='notice_follow_up_due',
            title='Follow-Up Due: Escalation Notice Response Window Expired',
            message=f'{notice.title} for {project_name} has reached its 15 working-day response window following receipt. Next escalation step is required.',
        )

    if created:
        db.session.commit()

    return {
        'checked': checked,
        'created': created,
    }


def _pending_release_notices(reference_now):
    cutoff = reference_now - timedelta(days=PENDING_RELEASE_DAYS)
    return (
        EscalationNotice.query
        .filter(EscalationNotice.status == 'reviewed')
        .filter(EscalationNotice.sent_at.is_(None))
        .filter(EscalationNotice.generated_at <= cutoff)
        .order_by(EscalationNotice.generated_at.asc(), EscalationNotice.id.asc())
        .all()
    )


def _pending_receipt_notices(reference_now):
    cutoff = reference_now - timedelta(days=PENDING_RECEIPT_DAYS)
    return (
        EscalationNotice.query
        .filter(EscalationNotice.status == 'sent')
        .filter(EscalationNotice.sent_at.is_not(None))
        .filter(EscalationNotice.acknowledged_at.is_(None))
        .filter(EscalationNotice.sent_at <= cutoff)
        .order_by(EscalationNotice.sent_at.asc(), EscalationNotice.id.asc())
        .all()
    )


def _follow_up_due_notices(reference_now):
    candidates = (
        EscalationNotice.query
        .filter(EscalationNotice.notice_type.in_(('annex_m', 'annex_n')))
        .filter(EscalationNotice.acknowledged_at.is_not(None))
        .order_by(EscalationNotice.acknowledged_at.asc(), EscalationNotice.id.asc())
        .all()
    )
    due = []
    for notice in candidates:
        if notice.child_notices:
            continue
        lgu_id = notice.project.lgu_id if notice.project else None
        due_at = _add_working_days(
            _to_aware_datetime(notice.acknowledged_at),
            FOLLOW_UP_WORKING_DAYS,
            lgu_id=lgu_id,
            is_formal_deadline=True,
        )
        if due_at <= reference_now:
            due.append(notice)
    return due


def _notify_notice_users(notice, notification_type, title, message):
    from app.services import notification_service
    created = 0
    action_url = f'/dashboard/escalation/notices/{notice.id}'
    for user in _notice_operator_users(notice):
        dedup_key = f'notice:{notice.id}:{notification_type}:{user.id}'
        notif = notification_service.create_notification(
            user_id=user.id,
            project_id=notice.project_id,
            notification_type=notification_type,
            title=title,
            message=message,
            priority='high',
            action_url=action_url,
            dedup_key=dedup_key,
            related_entity_type='escalation_notice',
            related_entity_id=notice.id,
            auto_commit=False,
        )
        if notif and getattr(notif, '_is_new', True):
            created += 1
    return created


def _notice_operator_users(notice):
    users_by_id = {}
    for user in User.query.filter(User.is_active.is_(True), User.role == 'admin').all():
        users_by_id[user.id] = user

    lgu = notice.project.lgu if notice.project else None
    if lgu and lgu.cluster_id:
        assignments = (
            StaffLguAssignment.query
            .join(User, User.id == StaffLguAssignment.user_id)
            .filter(StaffLguAssignment.scope_type == 'cluster')
            .filter(StaffLguAssignment.cluster_id == lgu.cluster_id)
            .filter(StaffLguAssignment.is_active.is_(True))
            .filter(User.is_active.is_(True))
            .filter(User.role == 'staff')
            .all()
        )
        for assignment in assignments:
            users_by_id[assignment.user_id] = assignment.user

    return list(users_by_id.values())


def _notification_exists(user_id, notice_id, notification_type):
    return db.session.query(Notification.id).filter_by(
        user_id=user_id,
        notification_type=notification_type,
        related_entity_type='escalation_notice',
        related_entity_id=notice_id,
    ).first() is not None


def _add_working_days(start_date, days, lgu_id=None, is_formal_deadline=True):
    return working_day_service.add_working_days(
        start_date, days, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline
    )


def _to_aware_datetime(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
