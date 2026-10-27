"""
Notification Service
Handles creation and management of in-app notifications
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_, event
from sqlalchemy.orm import Session

from app.extensions import db

logger = logging.getLogger(__name__)


@event.listens_for(Session, 'after_commit')
def _on_session_after_commit(session):
    if session.in_nested_transaction():
        tx = session.get_nested_transaction()
        parent_tx = tx.parent if (tx and tx.parent and tx.parent.nested) else None
        pending_by_tx = session.info.get('_pending_email_by_tx', {})
        items = pending_by_tx.pop(tx, [])
        if items:
            parent_items = pending_by_tx.setdefault(parent_tx, [])
            for item in items:
                if item not in parent_items:
                    parent_items.append(item)
        return

    pending_by_tx = session.info.pop('_pending_email_by_tx', {})
    pending_notifications = pending_by_tx.pop(None, [])
    if not pending_notifications:
        return
    for notification_id in pending_notifications:
        try:
            from app.tasks.notification_dispatcher import dispatch_notification_email
            dispatch_notification_email.delay(notification_id)
        except Exception as exc:
            logger.warning(
                "Failed to enqueue email for notification %s after commit: %s",
                notification_id,
                exc,
            )


@event.listens_for(Session, 'after_rollback')
def _on_session_after_rollback(session):
    if session.in_nested_transaction():
        tx = session.get_nested_transaction()
        pending_by_tx = session.info.get('_pending_email_by_tx', {})
        pending_by_tx.pop(tx, None)
        return
    session.info.pop('_pending_email_by_tx', None)
from app.models import (
    Notification,
    NotificationDelivery,
    UserNotificationPreference,
    User,
    UserScopeAssignment,
    LguProfile,
    Project,
    ProjectRequirement,
)
from app.utils.datetime import to_iso_utc
from app.services.email_service import _format_requirement_status_label


class NotificationError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def notify_staff_on_field_upload(*, submission_id, project_requirement_id, uploaded_by_user_id):
    """
    Notify staff members and admins when a field officer uploads a document.
    Compatibility wrapper that delegates to the canonical notify_workflow_transition pipeline.
    """
    return notify_workflow_transition(
        project_requirement_id=project_requirement_id,
        event='submitted',
        actor_user_id=uploaded_by_user_id,
    )


def notify_field_officer_on_status_change(*, project_requirement_id, old_status, new_status, reviewer_user_id):
    """
    Notify the field officer and admins when staff changes document review status.
    Uses the unified create_notification pipeline with proper event types, delivery records,
    and post-commit email dispatch.
    
    Args:
        project_requirement_id: ID of the project requirement
        old_status: Previous status (for comparison)
        new_status: New status after change
        reviewer_user_id: ID of the staff user who made the change
    
    Returns:
        List of created notification IDs
    """
    requirement = db.session.get(ProjectRequirement, project_requirement_id)
    if not requirement:
        raise NotificationError('Project requirement not found', 404)
    
    project = db.session.get(Project, requirement.project_id)
    if not project:
        raise NotificationError('Project not found', 404)
    
    lgu = db.session.get(LguProfile, project.lgu_id)
    reviewer = db.session.get(User, reviewer_user_id) if reviewer_user_id else None
    reviewer_name = reviewer.full_name if reviewer else 'Staff'
    
    notification_ids = []
    project_name = project.project_name
    requirement_name = requirement.requirement_name
    action_url = f'/dashboard/projects/{project.id}?tab=requirements&req={requirement.id}'
    
    # Determine notification type, title, and priority based on status change
    if new_status == 'under_review' and old_status in ('compliant', 'non_compliant', 'submitted', 'resubmitted'):
        fo_notif_type = 'workflow_document_returned'
        fo_title = 'Document Returned for Revision'
        fo_message = f'Your uploaded document "{requirement_name}" for {project_name} has been returned for revision by {reviewer_name}. Please review the deficiency findings and upload the updated document.'
        priority = 'high'
    elif new_status == 'compliant':
        fo_notif_type = 'workflow_document_approved'
        fo_title = 'Document Approved'
        fo_message = f'Your uploaded document "{requirement_name}" for {project_name} has been approved by {reviewer_name}. This requirement is now fully compliant.'
        priority = 'normal'
    elif new_status == 'non_compliant':
        fo_notif_type = 'compliance_breach'
        fo_title = 'Document Marked Non-Compliant'
        fo_message = f'Your uploaded document "{requirement_name}" for {project_name} has been marked as non-compliant by {reviewer_name}. Please view the recorded findings and coordinate with the review team.'
        priority = 'high'
    elif new_status == 'waived':
        # Waived status represents an administrative exemption, not an approval or submission.
        # No canonical notification type currently exists in the schema for waived requirements.
        # Marked as OPEN per Phase 2A audit mandate. Notification dispatch is intentionally suppressed.
        logger.info(
            "Requirement %s for project %s marked waived; notification suppressed (mapping OPEN).",
            project_requirement_id,
            project.id,
        )
        fo_notif_type = None
    else:
        fo_notif_type = None

    if not fo_notif_type:
        return []
    
    # Notify the field officer assigned to this LGU
    if lgu:
        field_officer_assignment = (
            UserScopeAssignment.query
            .join(User, UserScopeAssignment.user_id == User.id)
            .filter(
                and_(
                    UserScopeAssignment.scope_type == 'lgu',
                    UserScopeAssignment.lgu_id == lgu.id,
                    UserScopeAssignment.is_active == True,
                    User.role == 'field_officer',
                    User.is_active == True,
                )
            )
            .first()
        )
        
        if field_officer_assignment:
            notif = create_notification(
                user_id=field_officer_assignment.user_id,
                project_id=project.id,
                notification_type=fo_notif_type,
                title=fo_title,
                message=fo_message,
                priority=priority,
                action_url=action_url,
                related_entity_type='project_requirement',
                related_entity_id=project_requirement_id,
                auto_commit=False,
            )
            if notif:
                notification_ids.append(notif.id)
    
    # Determine notification content for admins
    status_label = _format_requirement_status_label(new_status) or (new_status or 'Updated')
    admin_title = f'Document Review Status Updated: {requirement_name}'
    admin_message = f'Staff reviewer {reviewer_name} changed the status of "{requirement_name}" for {project_name} to {status_label}.'
    admin_notif_type = fo_notif_type
    
    admin_users = User.query.filter(
        and_(
            User.role == 'admin',
            User.is_active == True,
        )
    ).all()
    
    for admin in admin_users:
        if reviewer_user_id and admin.id == reviewer_user_id:
            continue
        notif = create_notification(
            user_id=admin.id,
            project_id=project.id,
            notification_type=admin_notif_type,
            title=admin_title,
            message=admin_message,
            priority='normal',
            action_url=action_url,
            related_entity_type='project_requirement',
            related_entity_id=project_requirement_id,
            auto_commit=False,
        )
        if notif:
            notification_ids.append(notif.id)
    
    db.session.commit()
    return notification_ids


_WORKFLOW_EVENT_COPY = {
    'submitted': {
        'notification_type': 'workflow_document_submitted',
        'recipient_roles': ('staff',),
        'title': 'New Document Submitted for Verification',
        'message_template': '{actor_name} submitted "{requirement_name}" for {project_name}. It is now ready for staff review and verification. Please review the submitted files.',
    },
    'resubmitted': {
        'notification_type': 'workflow_document_submitted',
        'recipient_roles': ('staff',),
        'title': 'Revised Document Resubmitted for Verification',
        'message_template': '{actor_name} resubmitted revised files for "{requirement_name}" under {project_name}. It is ready for staff review and verification.',
    },
    'returned': {
        'notification_type': 'workflow_document_returned',
        'recipient_roles': ('field_officer', 'staff'),
        'title': 'Document Returned for Revision',
        'message_template': '{actor_name} returned "{requirement_name}" for {project_name} for revision. Please review the deficiency findings and upload the updated document.',
    },
    'staff_approved': {
        'notification_type': 'workflow_staff_approved',
        'recipient_roles': ('field_officer',),
        'title': 'Document Approved by Staff',
        'message_template': '{actor_name} approved "{requirement_name}" for {project_name} at the staff review stage. The document has advanced to Provincial Admin approval.',
    },
    'pending_provincial_approval': {
        'notification_type': 'workflow_pending_provincial_approval',
        'recipient_roles': ('admin',),
        'title': 'Document Pending Provincial Admin Approval',
        'message_template': '"{requirement_name}" for {project_name} has cleared staff review and is awaiting final Provincial Admin authorization.',
    },
    'approved': {
        'notification_type': 'workflow_document_approved',
        'recipient_roles': ('field_officer', 'staff'),
        'title': 'Document Approved',
        'message_template': '{actor_name} gave final approval to "{requirement_name}" for {project_name}. This requirement is now fully compliant.',
    },
}


def notify_workflow_transition(*, project_requirement_id, event, actor_user_id=None):
    """
    Notify the relevant roles when a shared document workflow transition occurs
    (submitted, returned, staff_approved, pending_provincial_approval, approved).

    Recipient resolution reuses the same UserScopeAssignment pattern as the
    existing field-upload / status-change notifications:
      - 'staff' recipients are scoped to the project's LGU cluster.
      - 'field_officer' recipients are scoped to the project's LGU.
      - 'admin' (Provincial Admin) recipients are notified globally.
    """
    copy = _WORKFLOW_EVENT_COPY.get(event)
    if not copy:
        raise NotificationError(f'Unknown workflow notification event: {event}', 422)

    requirement = db.session.get(ProjectRequirement, project_requirement_id)
    if not requirement:
        raise NotificationError('Project requirement not found', 404)

    project = db.session.get(Project, requirement.project_id)
    if not project:
        raise NotificationError('Project not found', 404)

    lgu = db.session.get(LguProfile, project.lgu_id)
    actor = db.session.get(User, actor_user_id) if actor_user_id else None
    actor_name = actor.full_name if actor else 'A reviewer'

    message = copy['message_template'].format(
        actor_name=actor_name,
        requirement_name=requirement.requirement_name,
        project_name=project.project_name,
    )

    priority = 'high' if event in ('returned', 'pending_provincial_approval') else 'normal'
    action_url = f'/dashboard/projects/{project.id}?tab=requirements&req={requirement.id}'

    notification_ids = []
    for role in copy['recipient_roles']:
        for recipient_id in _resolve_workflow_recipients(role=role, lgu=lgu):
            if actor_user_id is not None and recipient_id == actor_user_id:
                continue
            notif = create_notification(
                user_id=recipient_id,
                project_id=project.id,
                notification_type=copy['notification_type'],
                title=copy['title'],
                message=message,
                priority=priority,
                action_url=action_url,
                related_entity_type='project_requirement',
                related_entity_id=requirement.id,
                auto_commit=False,
            )
            if notif:
                notification_ids.append(notif.id)

    db.session.commit()
    return notification_ids


def _resolve_workflow_recipients(*, role, lgu):
    if role == 'admin':
        # Provincial Admin has global scope; notify every active admin user.
        return [
            user.id
            for user in User.query.filter(and_(User.role == 'admin', User.is_active == True)).all()
        ]
    if role == 'staff':
        if not lgu or not lgu.cluster_id:
            return []
        assignments = (
            UserScopeAssignment.query
            .join(User, UserScopeAssignment.user_id == User.id)
            .filter(
                and_(
                    UserScopeAssignment.scope_type == 'cluster',
                    UserScopeAssignment.cluster_id == lgu.cluster_id,
                    UserScopeAssignment.is_active == True,
                    User.role == 'staff',
                    User.is_active == True,
                )
            )
            .all()
        )
        return [assignment.user_id for assignment in assignments]
    if role == 'field_officer':
        if not lgu:
            return []
        assignments = (
            UserScopeAssignment.query
            .join(User, UserScopeAssignment.user_id == User.id)
            .filter(
                and_(
                    UserScopeAssignment.scope_type == 'lgu',
                    UserScopeAssignment.lgu_id == lgu.id,
                    UserScopeAssignment.is_active == True,
                    User.role == 'field_officer',
                    User.is_active == True,
                )
            )
            .all()
        )
        return [assignment.user_id for assignment in assignments]
    return []


_MANAGEMENT_ACTION_EVENT_COPY = {
    'generated': {
        'notification_type': 'mar_generated',
        'recipient_roles': ('staff', 'admin'),
        'title': 'Management Action Report Generated',
        'message_template': 'A Management Action Report was automatically generated for {project_name} ({cycle_month}) due to {risk_level} risk slippage. Staff review and proposed actions are required.',
    },
    'submitted': {
        'notification_type': 'mar_submitted',
        'recipient_roles': ('admin',),
        'title': 'Management Action Report Submitted for Decision',
        'message_template': '{actor_name} submitted proposed actions in the Management Action Report for {project_name} ({cycle_month}). Provincial Admin decision is required.',
    },
    'acted': {
        'notification_type': 'mar_acted',
        'recipient_roles': ('staff',),
        'title': 'Management Action Report Directives Recorded',
        'message_template': '{actor_name} recorded executive decisions on the Management Action Report for {project_name} ({cycle_month}). Directives are now available for implementation.',
    },
    'closed': {
        'notification_type': 'mar_closed',
        'recipient_roles': ('staff', 'admin'),
        'title': 'Management Action Report Closed',
        'message_template': '{actor_name} verified resolution and closed the Management Action Report for {project_name} ({cycle_month}). Corrective actions are complete.',
    },
}


def notify_management_action_event(*, management_action_id, event, actor_user_id=None):
    """Notify relevant roles on Management Action Report lifecycle events
    (generated, submitted, acted, closed). Reuses the same recipient
    resolution pattern as `notify_workflow_transition`.
    """
    from app.models import ManagementActionReport

    copy = _MANAGEMENT_ACTION_EVENT_COPY.get(event)
    if not copy:
        raise NotificationError(f'Unknown management action notification event: {event}', 422)

    management_action = ManagementActionReport.query.get(management_action_id)
    if not management_action:
        raise NotificationError('Management Action Report not found', 404)

    project = Project.query.get(management_action.project_id) if management_action.project_id else None
    lgu = LguProfile.query.get(project.lgu_id) if project else None
    actor = User.query.get(actor_user_id) if actor_user_id else None
    actor_name = actor.full_name if actor else 'A reviewer'

    message = copy['message_template'].format(
        actor_name=actor_name,
        project_name=project.project_name if project else 'an unassigned project',
        cycle_month=management_action.cycle_month,
        risk_level=management_action.risk_level,
    )

    action_url = f'/dashboard/projects/{project.id}?tab=mar' if project else None

    notification_ids = []
    for role in copy['recipient_roles']:
        for recipient_id in _resolve_workflow_recipients(role=role, lgu=lgu):
            if actor_user_id is not None and recipient_id == actor_user_id:
                continue
            notif = create_notification(
                user_id=recipient_id,
                project_id=project.id if project else None,
                notification_type=copy['notification_type'],
                title=copy['title'],
                message=message,
                priority='high',
                action_url=action_url,
                related_entity_type='management_action_report',
                related_entity_id=management_action.id,
                auto_commit=False,
            )
            if notif:
                notification_ids.append(notif.id)

    db.session.commit()
    return notification_ids


def get_user_notifications(*, user_id, include_read=False, limit=50):
    """
    Get notifications for a user that were delivered to the in-app channel.
    
    Args:
        user_id: ID of the user
        include_read: Whether to include read notifications
        limit: Maximum number of notifications to return
    
    Returns:
        List of serialized notifications
    """
    query = (
        Notification.query
        .join(NotificationDelivery, NotificationDelivery.notification_id == Notification.id)
        .filter(
            Notification.user_id == user_id,
            NotificationDelivery.channel == 'in_app',
        )
    )
    
    if not include_read:
        query = query.filter(Notification.is_read == False)
    
    notifications = (
        query.order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    
    return [_serialize_notification(n) for n in notifications]


def get_unread_count(*, user_id):
    """
    Get count of unread notifications for a user delivered to the in-app channel.
    
    Args:
        user_id: ID of the user
    
    Returns:
        Integer count of unread notifications
    """
    return (
        Notification.query
        .join(NotificationDelivery, NotificationDelivery.notification_id == Notification.id)
        .filter(
            and_(
                Notification.user_id == user_id,
                NotificationDelivery.channel == 'in_app',
                Notification.is_read == False,
            )
        )
        .count()
    )


def mark_read(*, user_id, notification_ids=None):
    """
    Mark specific or all notifications as read for a user.
    
    Args:
        user_id: ID of the user
        notification_ids: Optional list of notification IDs. If None, marks all.
    
    Returns:
        Number of notifications marked as read
    """
    now = datetime.now(timezone.utc)
    
    filters = [
        Notification.user_id == user_id,
        Notification.is_read == False,
    ]
    if notification_ids is not None:
        filters.append(Notification.id.in_(notification_ids))
        
    updated_count = (
        Notification.query
        .filter(and_(*filters))
        .update(
            {
                'is_read': True,
                'read_at': now,
            },
            synchronize_session='fetch',
        )
    )
    db.session.commit()
    return updated_count


def _serialize_notification(notification):
    """Serialize a notification for API response."""
    return {
        'id': notification.id,
        'notification_type': notification.notification_type,
        'title': notification.title,
        'message': notification.message,
        'priority': getattr(notification, 'priority', 'normal') or 'normal',
        'action_url': getattr(notification, 'action_url', None),
        'is_read': notification.is_read,
        'read_at': to_iso_utc(notification.read_at),
        'created_at': to_iso_utc(notification.created_at),
        'project_id': notification.project_id,
        'related_entity_type': notification.related_entity_type,
        'related_entity_id': notification.related_entity_id,
    }


def create_notification(
    *,
    user_id,
    notification_type,
    title,
    message,
    project_id=None,
    related_entity_type=None,
    related_entity_id=None,
    priority='normal',
    action_url=None,
    dedup_key=None,
    auto_commit=True,
):
    """
    Unified entry point for creating in-app notifications and enqueuing email dispatches.

    Guarantees:
    - Database-backed deduplication (if dedup_key exists, suppresses duplicate and returns existing)
    - Active recipient verification (filters out inactive users and excludes system_admin from operational notices)
    - In-app delivery record created with status 'sent'
    - Asynchronous email delivery enqueued via Celery if priority/preferences warrant email
    - Fault isolation: Celery/email failure never aborts or rolls back the notification
    """
    if dedup_key:
        existing = Notification.query.filter_by(dedup_key=dedup_key).first()
        if existing:
            setattr(existing, '_is_new', False)
            return existing

    recipient = db.session.get(User, user_id)
    if not recipient or not recipient.is_active:
        return None

    # Do not send System Admin users operational project notifications unless technical/security
    if recipient.role == 'system_admin' and notification_type not in ('security_alert',):
        return None

    notification = Notification(
        user_id=user_id,
        project_id=project_id,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority or 'normal',
        action_url=action_url,
        dedup_key=dedup_key,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    setattr(notification, '_is_new', True)
    db.session.add(notification)
    db.session.flush()

    # Create in-app delivery record if eligible
    if _is_in_app_eligible(recipient, notification):
        in_app = NotificationDelivery(
            notification_id=notification.id,
            channel='in_app',
            status='sent',
            sent_at=datetime.now(timezone.utc),
        )
        db.session.add(in_app)

    # Check email eligibility
    should_dispatch_email = False
    if recipient.email and _is_email_eligible(recipient, notification):
        email_delivery = NotificationDelivery(
            notification_id=notification.id,
            channel='email',
            status='pending',
        )
        db.session.add(email_delivery)
        should_dispatch_email = True

    if should_dispatch_email:
        session = db.session()
        nested_tx = session.get_nested_transaction()
        pending_by_tx = session.info.setdefault('_pending_email_by_tx', {})
        tx_pending = pending_by_tx.setdefault(nested_tx, [])
        if notification.id not in tx_pending:
            tx_pending.append(notification.id)

    if auto_commit:
        db.session.commit()

    return notification


def _is_in_app_eligible(recipient, notification):
    """Check if recipient's preferences permit in-app notification delivery."""
    pref = UserNotificationPreference.query.filter_by(user_id=recipient.id).first()
    priority = (notification.priority or 'normal').lower()
    ntype = notification.notification_type or ''

    # 1. Critical: Always eligible (policy enforces in_app_critical_alerts cannot be disabled)
    if priority == 'critical' or ntype in ('security_alert', 'compliance_breach'):
        return getattr(pref, 'in_app_critical_alerts', True) if pref else True

    # 2. High priority events
    if priority == 'high':
        # Deadline-related high priority
        if ntype in (
            'sla_warning',
            'sla_breached',
            'notice_pending_release',
            'notice_pending_receipt',
            'notice_follow_up_due',
            'requirement_missing_reminder',
        ):
            return getattr(pref, 'in_app_deadline_reminders', True) if pref else True
        # Review-related high priority
        if ntype in (
            'submission_unreviewed_reminder',
            'revision_pending_reminder',
            'resubmission_unreviewed_reminder',
            'provincial_approval_reminder',
            'workflow_document_returned',
            'workflow_pending_provincial_approval',
            'requirement_privilege_override',
            'mar_privilege_override',
        ):
            return getattr(pref, 'in_app_review_reminders', True) if pref else True
        return True

    # 3. Workflow notifications
    if ntype.startswith('workflow_') or ntype in ('submission_received', 'mar_submitted', 'mar_acted', 'mar_closed', 'project_reopened'):
        return getattr(pref, 'in_app_workflow_notifications', True) if pref else True

    return True


def _is_email_eligible(recipient, notification):
    """Check if recipient's preferences permit email notification delivery."""
    pref = UserNotificationPreference.query.filter_by(user_id=recipient.id).first()
    priority = (notification.priority or 'normal').lower()
    ntype = notification.notification_type or ''

    # 1. Critical: Always eligible if critical alerts enabled (default True, policy enforced)
    if priority == 'critical' or ntype in ('security_alert', 'compliance_breach'):
        return pref.email_critical_alerts if pref else True

    # 2. High priority events
    if priority == 'high':
        # Deadline-related high priority
        if ntype in (
            'sla_warning',
            'sla_breached',
            'notice_pending_release',
            'notice_pending_receipt',
            'notice_follow_up_due',
            'requirement_missing_reminder',
        ):
            return pref.email_deadline_reminders if pref else True
        # Review-related high priority
        if ntype in (
            'submission_unreviewed_reminder',
            'revision_pending_reminder',
            'resubmission_unreviewed_reminder',
            'provincial_approval_reminder',
            'workflow_document_returned',
            'workflow_pending_provincial_approval',
            'requirement_privilege_override',
            'mar_privilege_override',
        ):
            return pref.email_review_reminders if pref else True
        return True

    # 3. Normal / Low priority: workflow notifications only if user opted in
    if pref and pref.email_workflow_notifications and (
        ntype.startswith('workflow_') or ntype in ('submission_received', 'mar_submitted', 'mar_acted', 'mar_closed', 'project_reopened')
    ):
        return True

    return False

def _get_provincial_admins_for_project(project):
    return _resolve_workflow_recipients(role='admin', lgu=None)

def notify_project_reopened(project, actor_user_id, reopen_reason):
    from app.models.user import User
    from app.models.communication import Notification
    
    recipients = _get_provincial_admins_for_project(project)
    actor = db.session.get(User, actor_user_id)
    actor_name = actor.full_name if actor else 'Unknown Staff'
    
    for recipient_id in recipients:
        create_notification(
            user_id=recipient_id,
            notification_type='project_reopened',
            title='Project Reopened',
            message=f"{actor_name} reopened project {project.project_name}. Reason: {reopen_reason}. The project has returned to active monitoring.",
            priority='high',
            action_url=f'/dashboard/projects/{project.id}',
            project_id=project.id,
            related_entity_type='project',
            related_entity_id=project.id,
            auto_commit=False,
        )
    db.session.commit()


def notify_requirement_privilege_override(requirement, actor_user_id):
    from app.models.project import Project
    from app.models.user import User
    project = db.session.get(Project, requirement.project_id)
    if not project: return
    recipients = _get_provincial_admins_for_project(project)
    actor = db.session.get(User, actor_user_id)
    actor_name = actor.full_name if actor else 'Unknown Staff'
    for recipient_id in recipients:
        create_notification(
            user_id=recipient_id,
            notification_type='requirement_privilege_override',
            title='Administrative Override: Technical Document Approved',
            message=f"{actor_name} approved \"{requirement.requirement_name}\" for {project.project_name} under an administrative privilege override. Please review the audit record.",
            priority='high',
            action_url=f'/dashboard/projects/{project.id}?tab=requirements&req={requirement.id}',
            project_id=project.id,
            related_entity_type='project_requirement',
            related_entity_id=requirement.id,
            auto_commit=False,
        )
    db.session.commit()

def notify_mar_privilege_override(management_action, actor_user_id):
    from app.models.project import Project
    from app.models.user import User
    if not management_action.project_id: return
    project = db.session.get(Project, management_action.project_id)
    if not project: return
    recipients = _get_provincial_admins_for_project(project)
    actor = db.session.get(User, actor_user_id)
    actor_name = actor.full_name if actor else 'Unknown Staff'
    for recipient_id in recipients:
        create_notification(
            user_id=recipient_id,
            notification_type='mar_privilege_override',
            title='Administrative Override: Management Action Report Closed',
            message=f"{actor_name} closed a Management Action Report for {project.project_name} under an administrative privilege override. Please review the audit record.",
            priority='high',
            action_url=f'/dashboard/projects/{project.id}?tab=mar',
            project_id=project.id,
            related_entity_type='management_action_report',
            related_entity_id=management_action.id,
            auto_commit=False,
        )
    db.session.commit()


def get_user_preferences(user_id):
    """Get or initialize user notification preferences."""
    pref = UserNotificationPreference.query.filter_by(user_id=user_id).first()
    if not pref:
        pref = UserNotificationPreference(user_id=user_id)
        db.session.add(pref)
        db.session.commit()
    return _serialize_preferences(pref)


def update_user_preferences(user_id, data):
    """Update user notification preferences."""
    pref = UserNotificationPreference.query.filter_by(user_id=user_id).first()
    if not pref:
        pref = UserNotificationPreference(user_id=user_id)
        db.session.add(pref)

    # Critical alerts cannot be disabled under compliance policy
    if ('email_critical_alerts' in data and not data['email_critical_alerts']) or ('in_app_critical_alerts' in data and not data['in_app_critical_alerts']):
        from app.services import settings_service
        app_name = settings_service.get_app_name()
        raise NotificationError(f'Critical security and compliance alerts cannot be disabled under {app_name} policy.', 422)

    if 'email_deadline_reminders' in data:
        pref.email_deadline_reminders = bool(data['email_deadline_reminders'])
    if 'email_review_reminders' in data:
        pref.email_review_reminders = bool(data['email_review_reminders'])
    if 'email_workflow_notifications' in data:
        pref.email_workflow_notifications = bool(data['email_workflow_notifications'])
    if 'email_daily_digest' in data:
        pref.email_daily_digest = bool(data['email_daily_digest'])

    if 'in_app_deadline_reminders' in data:
        pref.in_app_deadline_reminders = bool(data['in_app_deadline_reminders'])
    if 'in_app_review_reminders' in data:
        pref.in_app_review_reminders = bool(data['in_app_review_reminders'])
    if 'in_app_workflow_notifications' in data:
        pref.in_app_workflow_notifications = bool(data['in_app_workflow_notifications'])

    pref.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return _serialize_preferences(pref)


def _serialize_preferences(pref):
    return {
        'user_id': pref.user_id,
        'email_critical_alerts': pref.email_critical_alerts,
        'email_deadline_reminders': pref.email_deadline_reminders,
        'email_review_reminders': pref.email_review_reminders,
        'email_workflow_notifications': pref.email_workflow_notifications,
        'email_daily_digest': pref.email_daily_digest,
        'in_app_critical_alerts': getattr(pref, 'in_app_critical_alerts', True),
        'in_app_deadline_reminders': getattr(pref, 'in_app_deadline_reminders', True),
        'in_app_review_reminders': getattr(pref, 'in_app_review_reminders', True),
        'in_app_workflow_notifications': getattr(pref, 'in_app_workflow_notifications', True),
        'updated_at': to_iso_utc(pref.updated_at),
    }


def recover_pending_notification_deliveries(channel='email', limit=100, max_age_seconds=None):
    """
    Recover orphaned pending notification deliveries (e.g. caused by transient broker unavailability).
    Queries pending deliveries and re-enqueues their dispatch tasks.
    """
    query = NotificationDelivery.query.filter_by(channel=channel, status='pending')
    if max_age_seconds is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        query = query.filter(NotificationDelivery.created_at <= cutoff)

    pending = query.order_by(NotificationDelivery.id.asc()).limit(limit).all()
    enqueued = 0
    failed = 0
    for delivery in pending:
        try:
            from app.tasks.notification_dispatcher import dispatch_notification_email
            dispatch_notification_email.delay(delivery.notification_id)
            enqueued += 1
        except Exception as exc:
            logger.warning("Failed to recover enqueue for notification delivery %s: %s", delivery.id, exc)
            failed += 1
            break

    return {
        'found': len(pending),
        'enqueued': enqueued,
        'failed': failed,
    }
