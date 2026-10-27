"""
Compliance Reminder Service
Centralized engine for statutory and operational compliance reminders across COMET.
Implements Reminders A through G with working-day arithmetic, strict scoping, and deduplication.
"""
import logging
from datetime import datetime, timezone

from app.extensions import db
from app.models import (
    EscalationNotice,
    LguProfile,
    Project,
    ProjectRequirement,
    SlaDeadline,
)
from app.services import notification_service, sla_service, working_day_service
from app.services.notification_service import _resolve_workflow_recipients

logger = logging.getLogger(__name__)


def evaluate_compliance_reminders(now=None, reference_now=None):
    """
    Evaluate compliance reminders across all active projects and requirements.
    
    Scheduled to run hourly in Celery Beat.
    Fully idempotent: deterministic dedup_keys guarantee at most one notification per cycle.
    """
    ref_now = reference_now or now or datetime.now(timezone.utc)
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)
    reference_now = ref_now

    stats = {
        'evaluated_at': reference_now.isoformat(),
        'missing_requirements_created': 0,
        'unreviewed_submissions_created': 0,
        'returned_revisions_created': 0,
        'resubmitted_unreviewed_created': 0,
        'pending_provincial_approval_created': 0,
        'approaching_sla_created': 0,
        'overdue_sla_created': 0,
        'total_created': 0,
    }

    # 1. Type A: Missing Mandatory Requirements
    stats['missing_requirements_created'] = _eval_missing_requirements(reference_now)

    # 2. Type B & D: Submitted Unreviewed & Resubmitted Unreviewed
    unreviewed_res, resubmitted_res = _eval_unreviewed_submissions(reference_now)
    stats['unreviewed_submissions_created'] = unreviewed_res
    stats['resubmitted_unreviewed_created'] = resubmitted_res

    # 3. Type C: Returned for Revision
    stats['returned_revisions_created'] = _eval_returned_for_revision(reference_now)

    # 4. Type E: Pending Provincial Approval
    stats['pending_provincial_approval_created'] = _eval_pending_provincial_approval(reference_now)

    # 5. Type F: Approaching SLA Deadlines (T-3, T-1)
    stats['approaching_sla_created'] = _eval_approaching_deadlines(reference_now)

    # 6. Type G: Overdue SLA Deadlines
    stats['overdue_sla_created'] = _eval_overdue_deadlines(reference_now)

    stats['total_created'] = sum(
        v for k, v in stats.items() if k.endswith('_created')
    )

    logger.info("Compliance reminders evaluated at %s: created=%s", reference_now.isoformat(), stats['total_created'])
    return stats


def _eval_missing_requirements(reference_now):
    created = 0
    # Active projects only
    active_projects = Project.query.filter(
        Project.overall_status.in_(['not_yet_started', 'ongoing'])
    ).all()

    for project in active_projects:
        lgu = db.session.get(LguProfile, project.lgu_id)
        if not lgu:
            continue

        field_officers = _resolve_workflow_recipients(role='field_officer', lgu=lgu)
        if not field_officers:
            continue

        reqs = ProjectRequirement.query.filter(
            ProjectRequirement.project_id == project.id,
            ProjectRequirement.is_active == True,
            ProjectRequirement.is_mandatory == True,
            ProjectRequirement.status == 'pending',
            ProjectRequirement.applicability == 'applicable',
            ProjectRequirement.workflow_status.is_(None) | (ProjectRequirement.workflow_status == 'draft'),
        ).all()

        for req in reqs:
            start_date = req.created_at or project.created_at
            if not start_date:
                continue
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)

            wd = working_day_service.count_working_days_between(
                start_date, reference_now, lgu_id=project.lgu_id, is_formal_deadline=False
            )

            # Schedule: first reminder at 10 working days, subsequent every 5 working days (15, 20, 25...)
            if wd >= 10 and (wd - 10) % 5 == 0:
                stage_wd = wd
                for fo_id in field_officers:
                    dedup_key = f'rem_a:{req.id}:{fo_id}:wd{stage_wd}'
                    notif = notification_service.create_notification(
                        user_id=fo_id,
                        project_id=project.id,
                        notification_type='requirement_missing_reminder',
                        title=f'Mandatory Requirement Not Yet Submitted: {req.requirement_name}',
                        message=f'The mandatory requirement "{req.requirement_name}" for {project.project_name} has not been submitted after {stage_wd} working days. Please upload the required documents.',
                        priority='high',
                        action_url=f'/dashboard/projects/{project.id}?tab=requirements&req={req.id}',
                        dedup_key=dedup_key,
                        related_entity_type='project_requirement',
                        related_entity_id=req.id,
                        auto_commit=True,
                    )
                    if notif and getattr(notif, '_is_new', True):
                        created += 1

    return created


def _eval_unreviewed_submissions(reference_now):
    unreviewed_created = 0
    resubmitted_created = 0

    candidates = ProjectRequirement.query.filter(
        ProjectRequirement.is_active == True,
        ProjectRequirement.applicability == 'applicable',
        ProjectRequirement.workflow_status.in_(['submitted', 'under_review']),
        ProjectRequirement.workflow_submitted_at.is_not(None),
    ).all()

    for req in candidates:
        project = db.session.get(Project, req.project_id)
        if not project or project.overall_status in ('completed', 'cancelled'):
            continue

        lgu = db.session.get(LguProfile, project.lgu_id)
        if not lgu or not lgu.cluster_id:
            continue

        staff_recipients = _resolve_workflow_recipients(role='staff', lgu=lgu)
        if not staff_recipients:
            continue

        sub_date = req.workflow_submitted_at
        if sub_date.tzinfo is None:
            sub_date = sub_date.replace(tzinfo=timezone.utc)

        wd = working_day_service.count_working_days_between(
            sub_date, reference_now, lgu_id=project.lgu_id, is_formal_deadline=False
        )

        # Distinguish Resubmitted (Type D) vs Initial Submission (Type B)
        is_resubmission = bool(req.workflow_returned_at and req.workflow_returned_at < sub_date)

        if is_resubmission:
            # Type D: Initial 2 working days, subsequent daily (wd >= 2)
            if wd >= 2:
                for staff_id in staff_recipients:
                    dedup_key = f'rem_d:{req.id}:{staff_id}:wd{wd}:{reference_now.date().isoformat()}'
                    notif = notification_service.create_notification(
                        user_id=staff_id,
                        project_id=project.id,
                        notification_type='resubmission_unreviewed_reminder',
                        title=f'Resubmitted Document Awaiting Review: {req.requirement_name}',
                        message=f'Revised submission for "{req.requirement_name}" under {project.project_name} has been awaiting staff review for {wd} working days. Please complete verification.',
                        priority='high',
                        action_url=f'/dashboard/projects/{project.id}?tab=requirements&req={req.id}',
                        dedup_key=dedup_key,
                        related_entity_type='project_requirement',
                        related_entity_id=req.id,
                        auto_commit=True,
                    )
                    if notif and getattr(notif, '_is_new', True):
                        resubmitted_created += 1
        else:
            # Type B: Initial 3 working days, subsequent every 2 working days (3, 5, 7, 9...)
            if wd >= 3 and (wd - 3) % 2 == 0:
                stage_wd = wd
                for staff_id in staff_recipients:
                    dedup_key = f'rem_b:{req.id}:{staff_id}:wd{stage_wd}'
                    notif = notification_service.create_notification(
                        user_id=staff_id,
                        project_id=project.id,
                        notification_type='submission_unreviewed_reminder',
                        title=f'Document Awaiting Staff Review: {req.requirement_name}',
                        message=f'Submission for "{req.requirement_name}" under {project.project_name} has been awaiting review for {stage_wd} working days. Please complete verification.',
                        priority='high',
                        action_url=f'/dashboard/projects/{project.id}?tab=requirements&req={req.id}',
                        dedup_key=dedup_key,
                        related_entity_type='project_requirement',
                        related_entity_id=req.id,
                        auto_commit=True,
                    )
                    if notif and getattr(notif, '_is_new', True):
                        unreviewed_created += 1

    return unreviewed_created, resubmitted_created


def _eval_returned_for_revision(reference_now):
    created = 0
    candidates = ProjectRequirement.query.filter(
        ProjectRequirement.is_active == True,
        ProjectRequirement.applicability == 'applicable',
        ProjectRequirement.workflow_status == 'returned_for_revision',
        ProjectRequirement.workflow_returned_at.is_not(None),
    ).all()

    for req in candidates:
        project = db.session.get(Project, req.project_id)
        if not project or project.overall_status in ('completed', 'cancelled'):
            continue

        lgu = db.session.get(LguProfile, project.lgu_id)
        if not lgu:
            continue

        field_officers = _resolve_workflow_recipients(role='field_officer', lgu=lgu)
        if not field_officers:
            continue

        ret_date = req.workflow_returned_at
        if ret_date.tzinfo is None:
            ret_date = ret_date.replace(tzinfo=timezone.utc)

        wd = working_day_service.count_working_days_between(
            ret_date, reference_now, lgu_id=project.lgu_id, is_formal_deadline=False
        )

        # Type C: Initial 5 working days, subsequent every 3 working days (5, 8, 11, 14...)
        if wd >= 5 and (wd - 5) % 3 == 0:
            stage_wd = wd
            for fo_id in field_officers:
                dedup_key = f'rem_c:{req.id}:{fo_id}:wd{stage_wd}'
                notif = notification_service.create_notification(
                    user_id=fo_id,
                    project_id=project.id,
                    notification_type='revision_pending_reminder',
                    title=f'Revision Pending Resubmission: {req.requirement_name}',
                    message=f'"{req.requirement_name}" for {project.project_name} was returned for revision {stage_wd} working days ago and has not been resubmitted. Please review the deficiency findings and upload the updated document.',
                    priority='high',
                    action_url=f'/dashboard/projects/{project.id}?tab=requirements&req={req.id}',
                    dedup_key=dedup_key,
                    related_entity_type='project_requirement',
                    related_entity_id=req.id,
                    auto_commit=True,
                )
                if notif and getattr(notif, '_is_new', True):
                    created += 1

            # Escalation to Cluster Staff at 10 working days
            if wd >= 10:
                cluster_staff = _resolve_workflow_recipients(role='staff', lgu=lgu)
                for staff_id in cluster_staff:
                    staff_dedup = f'rem_c_staff:{req.id}:{staff_id}:wd{stage_wd}'
                    notif = notification_service.create_notification(
                        user_id=staff_id,
                        project_id=project.id,
                        notification_type='revision_pending_reminder',
                        title=f'Unresolved Revision Escalation: {req.requirement_name}',
                        message=f'"{req.requirement_name}" for {project.project_name} was returned for revision {stage_wd} working days ago without resubmission. Follow-up with the LGU is recommended.',
                        priority='high',
                        action_url=f'/dashboard/projects/{project.id}?tab=requirements&req={req.id}',
                        dedup_key=staff_dedup,
                        related_entity_type='project_requirement',
                        related_entity_id=req.id,
                        auto_commit=True,
                    )
                    if notif and getattr(notif, '_is_new', True):
                        created += 1

    return created


def _eval_pending_provincial_approval(reference_now):
    created = 0
    candidates = ProjectRequirement.query.filter(
        ProjectRequirement.is_active == True,
        ProjectRequirement.applicability == 'applicable',
        ProjectRequirement.workflow_status == 'pending_provincial_approval',
        ProjectRequirement.workflow_staff_approved_at.is_not(None),
    ).all()

    admins = _resolve_workflow_recipients(role='admin', lgu=None)
    if not admins:
        return 0

    for req in candidates:
        project = db.session.get(Project, req.project_id)
        if not project or project.overall_status in ('completed', 'cancelled'):
            continue

        app_date = req.workflow_staff_approved_at
        if app_date.tzinfo is None:
            app_date = app_date.replace(tzinfo=timezone.utc)

        wd = working_day_service.count_working_days_between(
            app_date, reference_now, lgu_id=project.lgu_id, is_formal_deadline=False
        )

        # Type E: Initial 3 working days, subsequent every 3 working days (3, 6, 9...)
        if wd >= 3 and (wd - 3) % 3 == 0:
            stage_wd = wd
            for admin_id in admins:
                dedup_key = f'rem_e:{req.id}:{admin_id}:wd{stage_wd}'
                notif = notification_service.create_notification(
                    user_id=admin_id,
                    project_id=project.id,
                    notification_type='provincial_approval_reminder',
                    title=f'Pending Provincial Approval: {req.requirement_name}',
                    message=f'"{req.requirement_name}" for {project.project_name} has cleared staff review and has been awaiting Provincial Admin approval for {stage_wd} working days.',
                    priority='high',
                    action_url=f'/dashboard/projects/{project.id}?tab=requirements&req={req.id}',
                    dedup_key=dedup_key,
                    related_entity_type='project_requirement',
                    related_entity_id=req.id,
                    auto_commit=True,
                )
                if notif and getattr(notif, '_is_new', True):
                    created += 1

    return created


def _eval_approaching_deadlines(reference_now):
    created = 0
    # Formal compliance deadlines that are unresolved and not yet overdue
    query = SlaDeadline.query.filter(
        SlaDeadline.is_resolved == False,
        SlaDeadline.deadline_date >= reference_now,
    )
    deadlines = sla_service.filter_active_compliance_deadlines(query).all()

    for deadline in deadlines:
        project = db.session.get(Project, deadline.project_id)
        if not project or project.overall_status in ('completed', 'cancelled'):
            continue

        lgu = db.session.get(LguProfile, project.lgu_id)
        if not lgu:
            continue

        d_date = deadline.deadline_date
        if d_date.tzinfo is None:
            d_date = d_date.replace(tzinfo=timezone.utc)

        # Signed working days delta between reference_now and deadline
        days_remaining = working_day_service.working_days_delta(
            reference_now, d_date, lgu_id=project.lgu_id, is_formal_deadline=False
        )

        if days_remaining in (3, 1):
            priority = 'critical' if days_remaining == 1 else 'high'
            recipients = []
            # Field Officer
            recipients.extend(_resolve_workflow_recipients(role='field_officer', lgu=lgu))
            # Cluster Staff
            recipients.extend(_resolve_workflow_recipients(role='staff', lgu=lgu))

            deadline_type_label = sla_service.format_deadline_type(deadline.deadline_type)
            title = (
                f'Urgent: Compliance Deadline in 1 Working Day: {deadline_type_label}'
                if days_remaining == 1
                else f'Compliance Deadline in 3 Working Days: {deadline_type_label}'
            )
            formatted_date = d_date.strftime("%B %d, %Y")
            message = (
                f'The statutory compliance deadline for {project.project_name} ({deadline_type_label}) '
                f'expires in {days_remaining} working day{"s" if days_remaining != 1 else ""} on {formatted_date}. '
                f'Please ensure all required documents are submitted before the deadline.'
            )

            for uid in set(recipients):
                dedup_key = f'sla:{deadline.id}:t{days_remaining}:{uid}:{d_date.date().isoformat()}'
                action_url = f'/dashboard/projects/{project.id}?tab=deadlines&sla={deadline.id}'
                notif = notification_service.create_notification(
                    user_id=uid,
                    project_id=project.id,
                    notification_type='sla_warning',
                    title=title,
                    message=message,
                    priority=priority,
                    action_url=action_url,
                    dedup_key=dedup_key,
                    related_entity_type='sla_deadline',
                    related_entity_id=deadline.id,
                    auto_commit=True,
                )
                if notif and getattr(notif, '_is_new', True):
                    created += 1

    return created


def _eval_overdue_deadlines(reference_now):
    created = 0
    # Overdue deadlines that are unresolved
    query = SlaDeadline.query.filter(
        SlaDeadline.is_resolved == False,
        SlaDeadline.deadline_date < reference_now,
    )
    deadlines = sla_service.filter_active_compliance_deadlines(query).all()

    for deadline in deadlines:
        project = db.session.get(Project, deadline.project_id)
        if not project or project.overall_status in ('completed', 'cancelled'):
            continue

        lgu = db.session.get(LguProfile, project.lgu_id)
        if not lgu:
            continue

        # Stopping condition: If formal escalation notice has already been issued for this deadline
        has_notice = EscalationNotice.query.filter_by(trigger_sla_id=deadline.id).first() is not None
        if has_notice:
            continue

        d_date = deadline.deadline_date
        if d_date.tzinfo is None:
            d_date = d_date.replace(tzinfo=timezone.utc)

        days_overdue = working_day_service.count_working_days_between(
            d_date, reference_now, lgu_id=project.lgu_id, is_formal_deadline=False
        )

        # Cadence: initial breach notification (day 0/1) + weekly (every 5 working days)
        if days_overdue in (0, 1) or (days_overdue > 0 and days_overdue % 5 == 0):
            stage_ov = days_overdue
            recipients = []
            recipients.extend(_resolve_workflow_recipients(role='staff', lgu=lgu))
            recipients.extend(_resolve_workflow_recipients(role='admin', lgu=None))

            deadline_type_label = sla_service.format_deadline_type(deadline.deadline_type)
            title = f'Compliance Deadline Overdue: {project.project_name}'
            message = (
                f'The statutory compliance deadline for {project.project_name} ({deadline_type_label}) '
                f'is overdue by {days_overdue} working day{"s" if days_overdue != 1 else ""}. '
                f'Formal administrative escalation is required.'
            )

            for uid in set(recipients):
                cycle_date = reference_now.date().isoformat()
                dedup_key = f'sla:{deadline.id}:breach_wd{stage_ov}:{uid}:{cycle_date}'
                action_url = f'/dashboard/projects/{project.id}?tab=deadlines&sla={deadline.id}'
                notif = notification_service.create_notification(
                    user_id=uid,
                    project_id=project.id,
                    notification_type='sla_breached',
                    title=title,
                    message=message,
                    priority='critical',
                    action_url=action_url,
                    dedup_key=dedup_key,
                    related_entity_type='sla_deadline',
                    related_entity_id=deadline.id,
                    auto_commit=True,
                )
                if notif and getattr(notif, '_is_new', True):
                    created += 1

    return created
