from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import and_, false, or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import CommunicationLog, EscalationNotice, LegalFinding, LguProfile, MagicLink, NoticeRecipient, Project, ProjectRequirement, SlaDeadline
from app.services import access_service, audit_service, settings_service, working_day_service
from app.services.working_day_service import WorkingCalendarUnavailableError
from app.services.fiscal_year_scope import apply_notice_project_fiscal_year, apply_sla_project_fiscal_year


FOLLOW_UP_WORKING_DAYS = 15
AUTO_NOTICE_TYPES = ('annex_m', 'annex_n', 'annex_o')
VALID_NOTICE_TYPES = ('annex_e', 'annex_m', 'annex_n', 'annex_o', 'annex_l', 'reminder_letter')
BLOCKING_REASON_MESSAGES = {
    'missing_annex_e': 'An Annex E notice must exist before Annex M can be generated.',
    'awaiting_annex_m_dispatch': 'Annex M must be dispatched before the Annex N follow-up window can start.',
    'awaiting_annex_m_receipt': 'Annex M receipt must be recorded before the Annex N follow-up window can start.',
    'awaiting_annex_n_dispatch': 'Annex N must be dispatched before the Annex O follow-up window can start.',
    'awaiting_annex_n_receipt': 'Annex N receipt must be recorded before the Annex O follow-up window can start.',
    'awaiting_annex_n_window': 'Annex N is not due yet; the 15-working-day follow-up window is still running.',
    'awaiting_annex_o_window': 'Annex O is not due yet; the 15-working-day follow-up window is still running.',
    'final_notice_already_generated': 'Annex O has already been generated for this breach.',
    'deadline_not_overdue': 'This SLA deadline has not breached its working-day window yet.',
    'deadline_resolved': 'This SLA deadline has already been resolved.',
    'requirement_compliant': 'The linked requirement is already compliant.',
    'requirement_waived': 'The linked requirement has been validly waived.',
}
NOTICE_LABELS = {
    'annex_e': 'Annex E Notice of Deficiency',
    'annex_m': 'Annex M First Warning Notice',
    'annex_n': 'Annex N Second Warning Notice',
    'annex_o': 'Annex O Final Escalation Notice',
}


class EscalationError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def get_escalation_dashboard(user_id=None, now=None, fiscal_year=None):
    summaries = _build_breach_summaries(user_id=user_id, now=now, fiscal_year=fiscal_year)
    return {
        'breached_deadlines': len(summaries),
        'ready_to_generate': sum(1 for item in summaries if item['state'] == 'ready'),
        'blocked': sum(1 for item in summaries if item['state'] == 'blocked'),
        'waiting': sum(1 for item in summaries if item['state'] == 'waiting'),
        'completed': sum(1 for item in summaries if item['state'] == 'complete'),
        'with_notice_history': sum(1 for item in summaries if item['notice_count'] > 0),
        'escalation_flagged': sum(1 for item in summaries if item['escalation_triggered']),
        'annex_m_ready': sum(1 for item in summaries if item['state'] == 'ready' and item['next_notice_type'] == 'annex_m'),
        'annex_n_ready': sum(1 for item in summaries if item['state'] == 'ready' and item['next_notice_type'] == 'annex_n'),
        'annex_o_ready': sum(1 for item in summaries if item['state'] == 'ready' and item['next_notice_type'] == 'annex_o'),
    }


def list_breach_candidates(
    page=1,
    per_page=20,
    user_id=None,
    now=None,
    fiscal_year=None,
    search=None,
    state=None,
    next_notice_type=None,
    blocking_reason=None,
    lgu_id=None,
    program_id=None,
):
    reference_now = _to_aware_datetime(now or datetime.now(timezone.utc))
    query = _get_overdue_deadline_query(reference_now, user_id=user_id, fiscal_year=fiscal_year)
    if lgu_id is not None:
        query = query.filter(SlaDeadline.project.has(Project.lgu_id == lgu_id))
    if program_id is not None:
        query = query.filter(SlaDeadline.project.has(Project.program_id == program_id))
    query = _filter_deadline_search(query, search)

    summaries = [_build_breach_summary(deadline, reference_now) for deadline in query.all()]
    if state:
        summaries = [item for item in summaries if item['state'] == state]
    if next_notice_type:
        summaries = [item for item in summaries if item.get('next_notice_type') == next_notice_type]
    if blocking_reason:
        summaries = [item for item in summaries if item.get('blocking_reason') == blocking_reason]

    total = len(summaries)
    per_page = per_page or 20
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_items = summaries[start:end]

    return {
        'breaches': paginated_items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': pages,
    }


def list_escalation_notices(
    page=1,
    per_page=20,
    user_id=None,
    notice_type=None,
    status=None,
    project_id=None,
    lgu_id=None,
    program_id=None,
    trigger_sla_id=None,
    fiscal_year=None,
    search=None,
):
    query = _restrict_notice_query(EscalationNotice.query, user_id=user_id)
    query = apply_notice_project_fiscal_year(query, fiscal_year)
    if notice_type:
        query = query.filter(EscalationNotice.notice_type == notice_type)
    if status:
        query = query.filter(EscalationNotice.status == status)
    if project_id is not None:
        query = query.filter(EscalationNotice.project_id == project_id)
    if lgu_id is not None:
        query = query.filter(EscalationNotice.project.has(Project.lgu_id == lgu_id))
    if program_id is not None:
        query = query.filter(EscalationNotice.project.has(Project.program_id == program_id))
    if trigger_sla_id is not None:
        query = query.filter(EscalationNotice.trigger_sla_id == trigger_sla_id)
    query = _filter_notice_search(query, search)

    pagination = query.order_by(EscalationNotice.generated_at.desc(), EscalationNotice.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        'notices': [_serialize_notice(notice) for notice in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def get_escalation_notice_detail(notice_id, user_id=None):
    notice = _get_notice_with_access(notice_id, user_id=user_id)
    return _serialize_notice(notice, include_detail=True)


def process_auto_escalations(now=None, user_id=None, sla_id=None):
    reference_now = _to_aware_datetime(now or datetime.now(timezone.utc))
    deadlines = _get_overdue_deadlines(reference_now, user_id=user_id, sla_id=sla_id)
    _flag_deadlines_for_escalation(deadlines)

    generated_notice_ids = []
    blocked = []
    skipped = []
    failed = []

    for deadline in deadlines:
        try:
            if deadline.project and deadline.project.program and not deadline.project.program.is_active:
                skipped.append({
                    'sla_id': deadline.id,
                    'reason': 'program_inactive',
                    'message': f"Program '{deadline.project.program.name}' is deactivated.",
                })
                continue
            summary = _build_breach_summary(deadline, reference_now)
            if summary['state'] == 'ready':
                notice = _create_next_notice(deadline, summary, generated_by=user_id, generated_at=reference_now)
                generated_notice_ids.append(notice.id)
            elif summary['state'] == 'blocked':
                blocked.append({
                    'sla_id': deadline.id,
                    'reason': summary['blocking_reason'],
                    'message': summary['blocking_message'],
                })
            else:
                skipped.append({
                    'sla_id': deadline.id,
                    'reason': summary['blocking_reason'],
                    'message': summary['blocking_message'],
                })
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception(f"Error processing auto-escalation for SLA deadline {deadline.id}: {exc}")
            failed.append({
                'sla_id': deadline.id,
                'error': str(exc),
            })

    return {
        'evaluated_at': reference_now.isoformat(),
        'candidate_count': len(deadlines),
        'generated_count': len(generated_notice_ids),
        'generated_notice_ids': generated_notice_ids,
        'blocked_count': len(blocked),
        'blocked': blocked,
        'skipped_count': len(skipped),
        'skipped': skipped,
        'failed_count': len(failed),
        'failed': failed,
    }


def generate_next_notice_for_sla(sla_id, user_id=None, now=None):
    reference_now = _to_aware_datetime(now or datetime.now(timezone.utc))
    deadline = _get_deadline_with_access(sla_id, user_id=user_id)
    try:
        access_service.assert_project_movement_allowed(deadline.project_id)
    except access_service.AccessError as exc:
        raise EscalationError(exc.message, exc.status_code) from exc
    if deadline.is_resolved:
        raise EscalationError('Resolved SLA deadlines cannot be escalated further.', 409)
    if deadline.project_requirement_id:
        req = db.session.get(ProjectRequirement, deadline.project_requirement_id)
        if req:
            if req.status == 'compliant':
                raise EscalationError('Compliant requirements cannot be escalated.', 409)
            from app.services.project_service import is_valid_waived_requirement
            if is_valid_waived_requirement(req):
                raise EscalationError('Waived requirements cannot be escalated.', 409)
    if _to_aware_datetime(deadline.deadline_date) >= reference_now:
        raise EscalationError(BLOCKING_REASON_MESSAGES['deadline_not_overdue'], 409)

    _flag_deadlines_for_escalation([deadline])
    summary = _build_breach_summary(deadline, reference_now)
    if summary['state'] != 'ready':
        draft_notice = EscalationNotice.query.filter_by(
            trigger_sla_id=deadline.id,
            status='draft',
        ).first()
        if draft_notice:
            return draft_notice
        message = summary['blocking_message'] or 'This SLA deadline is not ready for automatic escalation.'
        raise EscalationError(message, 409)

    return _create_next_notice(deadline, summary, generated_by=user_id, generated_at=reference_now)


def _get_overdue_deadline_query(reference_now, user_id=None, fiscal_year=None):
    from app.services.sla_service import filter_active_compliance_deadlines
    query = _restrict_deadline_query(SlaDeadline.query, user_id=user_id)
    query = apply_sla_project_fiscal_year(query, fiscal_year)
    query = query.filter(
        SlaDeadline.is_resolved == False,
        SlaDeadline.deadline_date < _to_db_datetime(reference_now),
    )
    query = filter_active_compliance_deadlines(query)
    return query.order_by(SlaDeadline.deadline_date.asc(), SlaDeadline.id.asc())


def _filter_deadline_search(query, search=None):
    search = (search or '').strip()
    if not search:
        return query
    term = f'%{search}%'
    return query.filter(or_(
        SlaDeadline.deadline_type.ilike(term),
        SlaDeadline.notes.ilike(term),
        SlaDeadline.project.has(or_(
            Project.project_name.ilike(term),
            Project.source_project_code.ilike(term),
            Project.lgu.has(or_(
                LguProfile.name.ilike(term),
                LguProfile.municipality.ilike(term),
            )),
        )),
        SlaDeadline.project_requirement_id.in_(
            ProjectRequirement.query.with_entities(ProjectRequirement.id).filter(or_(
                ProjectRequirement.requirement_name.ilike(term),
                ProjectRequirement.phase_name.ilike(term),
                ProjectRequirement.annex_reference.ilike(term),
            ))
        ),
    ))


def _filter_notice_search(query, search=None):
    search = (search or '').strip()
    if not search:
        return query
    term = f'%{search}%'
    return query.filter(or_(
        EscalationNotice.title.ilike(term),
        EscalationNotice.body_text.ilike(term),
        EscalationNotice.final_text.ilike(term),
        EscalationNotice.notice_type.ilike(term),
        EscalationNotice.status.ilike(term),
        EscalationNotice.project.has(or_(
            Project.project_name.ilike(term),
            Project.source_project_code.ilike(term),
            Project.lgu.has(or_(
                LguProfile.name.ilike(term),
                LguProfile.municipality.ilike(term),
            )),
        )),
        EscalationNotice.trigger_requirement.has(or_(
            ProjectRequirement.requirement_name.ilike(term),
            ProjectRequirement.phase_name.ilike(term),
            ProjectRequirement.annex_reference.ilike(term),
        )),
    ))


def _get_overdue_deadlines(reference_now, user_id=None, sla_id=None, fiscal_year=None):
    if sla_id is not None:
        deadline = _get_deadline_with_access(sla_id, user_id=user_id)
        if deadline.is_resolved:
            return []
        if _to_aware_datetime(deadline.deadline_date) >= reference_now:
            return []
        if deadline.project_requirement_id:
            req = db.session.get(ProjectRequirement, deadline.project_requirement_id)
            if req:
                if req.status == 'compliant':
                    return []
                from app.services.project_service import is_valid_waived_requirement
                if is_valid_waived_requirement(req):
                    return []
        return [deadline]

    return _get_overdue_deadline_query(reference_now, user_id=user_id, fiscal_year=fiscal_year).all()


def _build_breach_summaries(user_id=None, now=None, fiscal_year=None):
    reference_now = _to_aware_datetime(now or datetime.now(timezone.utc))
    deadlines = _get_overdue_deadlines(reference_now, user_id=user_id, fiscal_year=fiscal_year)
    return [_build_breach_summary(deadline, reference_now) for deadline in deadlines]


def _build_breach_summary(deadline, reference_now):
    from app.services.project_service import is_valid_waived_requirement

    project = db.session.get(Project, deadline.project_id)
    lgu = db.session.get(LguProfile, project.lgu_id) if project else None
    requirement = (
        db.session.get(ProjectRequirement, deadline.project_requirement_id)
        if deadline.project_requirement_id else None
    )
    notices = _get_notice_chain(deadline)
    notice_map = {notice.notice_type: notice for notice in notices}
    latest_notice = _get_latest_notice(notices)

    next_notice_type = None
    parent_notice = None
    next_notice_due_at = None
    state = 'blocked'
    blocking_reason = None

    if deadline.is_resolved:
        state = 'blocked'
        blocking_reason = 'deadline_resolved'
    elif requirement and requirement.status == 'compliant':
        state = 'blocked'
        blocking_reason = 'requirement_compliant'
    elif requirement and is_valid_waived_requirement(requirement):
        state = 'blocked'
        blocking_reason = 'requirement_waived'
    elif notice_map.get('annex_o'):
        state = 'complete'
        blocking_reason = 'final_notice_already_generated'
        latest_notice = notice_map['annex_o']
    elif notice_map.get('annex_n'):
        latest_notice = notice_map['annex_n']
        next_notice_type = 'annex_o'
        parent_notice = latest_notice
        follow_up_anchor = _get_follow_up_anchor(latest_notice)
        if follow_up_anchor is None:
            state = 'waiting'
            blocking_reason = _get_follow_up_blocking_reason(latest_notice)
        else:
            next_notice_due_at = _add_working_days(
                follow_up_anchor, FOLLOW_UP_WORKING_DAYS, lgu_id=lgu.id if lgu else None, is_formal_deadline=True
            )
            if _to_aware_datetime(next_notice_due_at) <= reference_now:
                state = 'ready'
            else:
                state = 'waiting'
                blocking_reason = 'awaiting_annex_o_window'
    elif notice_map.get('annex_m'):
        latest_notice = notice_map['annex_m']
        next_notice_type = 'annex_n'
        parent_notice = latest_notice
        follow_up_anchor = _get_follow_up_anchor(latest_notice)
        if follow_up_anchor is None:
            state = 'waiting'
            blocking_reason = _get_follow_up_blocking_reason(latest_notice)
        else:
            next_notice_due_at = _add_working_days(
                follow_up_anchor, FOLLOW_UP_WORKING_DAYS, lgu_id=lgu.id if lgu else None, is_formal_deadline=True
            )
            if _to_aware_datetime(next_notice_due_at) <= reference_now:
                state = 'ready'
            else:
                state = 'waiting'
                blocking_reason = 'awaiting_annex_n_window'
    else:
        next_notice_type = 'annex_m'
        parent_notice = notice_map.get('annex_e')
        if parent_notice:
            state = 'ready'
        else:
            state = 'blocked'
            blocking_reason = 'missing_annex_e'

    if state == 'ready' and latest_notice is None and _to_aware_datetime(deadline.deadline_date) >= reference_now:
        state = 'blocked'
        blocking_reason = 'deadline_not_overdue'

    blocking_message = BLOCKING_REASON_MESSAGES.get(blocking_reason)

    return {
        'sla_id': deadline.id,
        'project_id': deadline.project_id,
        'project_name': project.project_name if project else None,
        'program_id': project.program_id if project else None,
        'program_code': project.program.code if (project and project.program) else None,
        'program_name': project.program.name if (project and project.program) else None,
        'lgu_id': lgu.id if lgu else None,
        'lgu_name': lgu.name if lgu else None,
        'project_requirement_id': deadline.project_requirement_id,
        'requirement_name': requirement.requirement_name if requirement else None,
        'deadline_type': deadline.deadline_type,
        'deadline_date': deadline.deadline_date.isoformat() if deadline.deadline_date else None,
        'days_overdue': _working_days_delta(
            _to_aware_datetime(deadline.deadline_date), reference_now, lgu_id=lgu.id if lgu else None, is_formal_deadline=False
        ),
        'escalation_triggered': deadline.escalation_triggered,
        'state': state,
        'next_notice_type': next_notice_type,
        'next_notice_due_at': next_notice_due_at.isoformat() if next_notice_due_at else None,
        'latest_notice_id': latest_notice.id if latest_notice else None,
        'latest_notice_type': latest_notice.notice_type if latest_notice else None,
        'latest_notice_generated_at': latest_notice.generated_at.isoformat() if latest_notice and latest_notice.generated_at else None,
        'notice_count': len(notices),
        'notices': [
            {
                'id': n.id,
                'notice_type': n.notice_type,
                'notice_number': n.notice_number,
                'title': n.title,
                'status': n.status,
                'generated_at': n.generated_at.isoformat() if n.generated_at else None,
                'sent_at': n.sent_at.isoformat() if n.sent_at else None,
                'acknowledged_at': n.acknowledged_at.isoformat() if n.acknowledged_at else None,
            }
            for n in notices
        ],
        'is_ready': state == 'ready',
        'blocking_reason': blocking_reason,
        'blocking_message': blocking_message,
        'parent_notice_id': parent_notice.id if parent_notice else None,
    }


def _create_next_notice(deadline, summary, generated_by=None, generated_at=None):
    from app.services import notice_service

    notice_type = summary['next_notice_type']
    existing = EscalationNotice.query.filter_by(
        trigger_sla_id=deadline.id,
        notice_type=notice_type,
    ).first()
    if existing:
        return existing

    project = db.session.get(Project, deadline.project_id)
    lgu = db.session.get(LguProfile, project.lgu_id) if project else None
    requirement = (
        db.session.get(ProjectRequirement, deadline.project_requirement_id)
        if deadline.project_requirement_id else None
    )
    parent_notice = db.session.get(EscalationNotice, summary['parent_notice_id']) if summary['parent_notice_id'] else None
    notice = EscalationNotice(
        project_id=deadline.project_id,
        parent_notice_id=parent_notice.id if parent_notice else None,
        trigger_sla_id=deadline.id,
        trigger_project_requirement_id=deadline.project_requirement_id,
        generated_by=_coerce_optional_user_id(generated_by),
        notice_type=notice_type,
        notice_number=_next_notice_number(deadline.project_id, notice_type),
        title=NOTICE_LABELS.get(notice_type, notice_type.replace('_', ' ').title()),
        body_text=notice_service.build_default_body_text(
            notice_type=notice_type,
            project=project,
            lgu=lgu,
            requirement=requirement,
            deadline=deadline,
            parent_notice=parent_notice,
        ),
        status='draft',
        generated_at=generated_at or datetime.now(timezone.utc),
    )

    try:
        db.session.add(notice)
        db.session.flush()

        recipient = _build_recipient(notice.id, lgu)
        if recipient:
            db.session.add(recipient)

        audit_service.log_action(
            user_id=_coerce_optional_user_id(generated_by),
            action='generate',
            entity_type='escalation_notice',
            entity_id=notice.id,
            old_value=None,
            new_value=_serialize_notice(notice, include_detail=True),
            commit=False,
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = EscalationNotice.query.filter_by(
            trigger_sla_id=deadline.id,
            notice_type=notice_type,
        ).first()
        if existing:
            return existing
        raise
    except Exception:
        db.session.rollback()
        raise

    return notice


def _build_notice_body(notice_type, project, lgu, requirement, deadline):
    label = NOTICE_LABELS.get(notice_type, notice_type.replace('_', ' ').title())
    lgu_name = lgu.name if lgu else 'the LGU'
    project_name = project.project_name if project else f'project #{deadline.project_id}'
    requirement_name = requirement.requirement_name if requirement else 'the unresolved compliance requirement'
    deadline_text = deadline.deadline_date.date().isoformat() if deadline.deadline_date else 'the recorded deadline'
    app_name = settings_service.get_app_name()
    return (
        f'{label} was auto-generated by {app_name} because {lgu_name} remains non-compliant on '
        f'"{project_name}" for "{requirement_name}" beyond the SLA breach dated {deadline_text}.'
    )


def _build_recipient(notice_id, lgu):
    if not lgu:
        return None

    recipient_name = lgu.mayor_name or lgu.contact_person or lgu.name
    recipient_role = 'Mayor' if (lgu.mayor_name or lgu.mayor_email) else 'LGU Contact'
    return NoticeRecipient(
        notice_id=notice_id,
        lgu_id=lgu.id,
        recipient_name=recipient_name,
        recipient_email=lgu.mayor_email or lgu.contact_email,
        recipient_role=recipient_role,
        delivery_method='pending_dispatch',
        delivery_status='pending',
    )


def _flag_deadlines_for_escalation(deadlines):
    changed = []
    for deadline in deadlines:
        if deadline.escalation_triggered:
            continue
        before = _serialize_deadline_flag(deadline)
        deadline.escalation_triggered = True
        changed.append((deadline, before))

    if not changed:
        return

    try:
        for deadline, before in changed:
            audit_service.log_action(
                user_id=None,
                action='escalate',
                entity_type='sla_deadline',
                entity_id=deadline.id,
                old_value=before,
                new_value=_serialize_deadline_flag(deadline),
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _get_notice_chain(deadline):
    query = EscalationNotice.query.filter(EscalationNotice.project_id == deadline.project_id)
    if deadline.project_requirement_id is not None:
        query = query.filter(
            or_(
                EscalationNotice.trigger_sla_id == deadline.id,
                and_(
                    EscalationNotice.trigger_sla_id.is_(None),
                    EscalationNotice.trigger_project_requirement_id == deadline.project_requirement_id,
                ),
            )
        )
    else:
        query = query.filter(EscalationNotice.trigger_sla_id == deadline.id)

    return query.filter(EscalationNotice.notice_type.in_(VALID_NOTICE_TYPES)).order_by(
        EscalationNotice.generated_at.asc(), EscalationNotice.id.asc()
    ).all()


def _get_latest_notice(notices):
    if not notices:
        return None

    precedence = {'annex_e': 0, 'annex_m': 1, 'annex_n': 2, 'annex_o': 3}
    return sorted(
        notices,
        key=lambda item: (precedence.get(item.notice_type, -1), item.generated_at or datetime.min.replace(tzinfo=timezone.utc), item.id),
    )[-1]


def _get_follow_up_anchor(notice):
    if not notice:
        return None
    if notice.acknowledged_at:
        return notice.acknowledged_at
    return None


def _get_follow_up_blocking_reason(notice):
    if not notice:
        return None
    if not notice.sent_at:
        return f'awaiting_{notice.notice_type}_dispatch'
    return f'awaiting_{notice.notice_type}_receipt'


def _get_deadline_with_access(sla_id, user_id=None):
    deadline = db.session.get(SlaDeadline, sla_id)
    if not deadline:
        raise EscalationError('SLA deadline not found', 404)

    if user_id is not None:
        try:
            access_service.ensure_project_access(deadline.project_id, user_id)
        except access_service.AccessError as exc:
            raise EscalationError(exc.message, exc.status_code)
    return deadline


def _get_notice_with_access(notice_id, user_id=None):
    notice = db.session.get(EscalationNotice, notice_id)
    if not notice:
        raise EscalationError('Escalation notice not found', 404)

    if user_id is not None:
        try:
            access_service.ensure_project_access(notice.project_id, user_id)
        except access_service.AccessError as exc:
            raise EscalationError(exc.message, exc.status_code)
    return notice


def _restrict_deadline_query(query, user_id=None):
    if user_id is None:
        return query

    scope = access_service.get_access_scope(user_id)
    if scope['unrestricted']:
        return query
    lgu_ids = scope['lgu_ids']
    if lgu_ids:
        return query.filter(SlaDeadline.project.has(Project.lgu_id.in_(lgu_ids)))
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return query.filter(false())
    return query.filter(
        SlaDeadline.project.has(Project.lgu.has(LguProfile.cluster_id.in_(cluster_ids)))
    )


def _restrict_notice_query(query, user_id=None):
    if user_id is None:
        return query

    scope = access_service.get_access_scope(user_id)
    if scope['unrestricted']:
        return query
    lgu_ids = scope['lgu_ids']
    if lgu_ids:
        return query.filter(EscalationNotice.project.has(Project.lgu_id.in_(lgu_ids)))
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return query.filter(false())
    return query.filter(
        EscalationNotice.project.has(Project.lgu.has(LguProfile.cluster_id.in_(cluster_ids)))
    )


def _serialize_notice(notice, include_detail=False):
    project = db.session.get(Project, notice.project_id)
    lgu = db.session.get(LguProfile, project.lgu_id) if project else None
    requirement = (
        db.session.get(ProjectRequirement, notice.trigger_project_requirement_id)
        if notice.trigger_project_requirement_id else None
    )
    parent_notice = db.session.get(EscalationNotice, notice.parent_notice_id) if notice.parent_notice_id else None
    recipients = notice.recipients.order_by(NoticeRecipient.id.asc()).all()
    legal_findings = notice.legal_findings.order_by(LegalFinding.id.asc()).all()
    magic_links = (
        MagicLink.query
        .filter_by(notice_id=notice.id)
        .order_by(MagicLink.created_at.desc(), MagicLink.id.desc())
        .all()
    )
    communications = (
        CommunicationLog.query
        .filter_by(related_notice_id=notice.id)
        .order_by(CommunicationLog.created_at.desc(), CommunicationLog.id.desc())
        .all()
    )

    payload = {
        'id': notice.id,
        'project_id': notice.project_id,
        'project_name': project.project_name if project else None,
        'program_id': project.program_id if project else None,
        'program_code': project.program.code if (project and project.program) else None,
        'program_name': project.program.name if (project and project.program) else None,
        'lgu_id': lgu.id if lgu else None,
        'lgu_name': lgu.name if lgu else None,
        'parent_notice_id': notice.parent_notice_id,
        'trigger_sla_id': notice.trigger_sla_id,
        'trigger_project_requirement_id': notice.trigger_project_requirement_id,
        'requirement_name': requirement.requirement_name if requirement else None,
        'generated_by': notice.generated_by,
        'generator_name': notice.generator.full_name if notice.generator else None,
        'notice_type': notice.notice_type,
        'notice_number': notice.notice_number,
        'title': notice.title,
        'body_text': notice.body_text,
        'ai_generated_text': notice.ai_generated_text,
        'final_text': notice.final_text,
        'status': notice.status,
        'generated_at': notice.generated_at.isoformat() if notice.generated_at else None,
        'sent_at': notice.sent_at.isoformat() if notice.sent_at else None,
        'acknowledged_at': notice.acknowledged_at.isoformat() if notice.acknowledged_at else None,
        'created_at': notice.created_at.isoformat() if notice.created_at else None,
        'updated_at': notice.updated_at.isoformat() if notice.updated_at else None,
        'recipient_count': len(recipients),
        'legal_finding_count': len(legal_findings),
        'magic_links_enabled': bool(current_app.config.get('ENABLE_PUBLIC_MAGIC_LINKS', False)),
    }
    if include_detail:
        payload['recipients'] = [
            {
                'id': recipient.id,
                'lgu_id': recipient.lgu_id,
                'recipient_name': recipient.recipient_name,
                'recipient_email': recipient.recipient_email,
                'recipient_role': recipient.recipient_role,
                'delivery_method': recipient.delivery_method,
                'delivery_status': recipient.delivery_status,
            }
            for recipient in recipients
        ]
        payload['legal_findings'] = [
            {
                'id': finding.id,
                'informal_notes': finding.informal_notes,
                'formal_findings': finding.formal_findings,
                'recommendations': finding.recommendations,
                'agreements_timelines': finding.agreements_timelines,
                'ai_model_used': finding.ai_model_used,
                'ai_prompt_used': finding.ai_prompt_used,
                'is_edited': finding.is_edited,
            }
            for finding in legal_findings
        ]
        payload['parent_notice'] = (
            {
                'id': parent_notice.id,
                'notice_type': parent_notice.notice_type,
                'generated_at': parent_notice.generated_at.isoformat() if parent_notice.generated_at else None,
            }
            if parent_notice else None
        )
        payload['magic_links'] = [
            {
                'id': link.id,
                'token': link.token,
                'url': _public_magic_link_url(link.token),
                'expires_at': link.expires_at.isoformat() if link.expires_at else None,
                'is_used': bool(link.is_used),
                'used_at': link.used_at.isoformat() if link.used_at else None,
                'access_count': int(link.access_count or 0),
                'intended_recipient_name': link.intended_recipient_name,
                'intended_recipient_role': link.intended_recipient_role,
                'created_at': link.created_at.isoformat() if link.created_at else None,
            }
            for link in magic_links
        ]
        payload['communications'] = [
            {
                'id': communication.id,
                'communication_type': communication.communication_type,
                'channel': communication.channel,
                'subject': communication.subject,
                'body': communication.body,
                'recipient_email': communication.recipient_email,
                'recipient_name': communication.recipient_name,
                'recipient_destination': communication.recipient_destination,
                'recipient_office': communication.recipient_office,
                'reference_no': communication.reference_no,
                'magic_link_id': communication.magic_link_id,
                'delivery_status': communication.delivery_status,
                'sent_at': communication.sent_at.isoformat() if communication.sent_at else None,
                'posted_at': communication.posted_at.isoformat() if communication.posted_at else None,
                'remarks': communication.remarks,
                'created_at': communication.created_at.isoformat() if communication.created_at else None,
            }
            for communication in communications
        ]
    return payload


def _serialize_deadline_flag(deadline):
    return {
        'id': deadline.id,
        'project_id': deadline.project_id,
        'project_requirement_id': deadline.project_requirement_id,
        'escalation_triggered': deadline.escalation_triggered,
        'is_resolved': deadline.is_resolved,
    }


def _next_notice_number(project_id, notice_type):
    current = db.session.query(db.func.max(EscalationNotice.notice_number)).filter(
        EscalationNotice.project_id == project_id,
        EscalationNotice.notice_type == notice_type,
    ).scalar()
    return (current or 0) + 1


def _coerce_optional_user_id(user_id):
    if user_id in (None, ''):
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise EscalationError('Invalid user identity', 422)


def _to_aware_datetime(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_db_datetime(value):
    return _to_aware_datetime(value).replace(tzinfo=None)


def _is_working_day(value, lgu_id=None, is_formal_deadline=True):
    try:
        return working_day_service.is_working_day(value, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline)
    except WorkingCalendarUnavailableError as exc:
        raise EscalationError(exc.message, exc.status_code) from exc


def _add_working_days(start_dt, working_days, lgu_id=None, is_formal_deadline=True):
    if working_days is None:
        return start_dt
    if working_days < 0:
        raise EscalationError('Working days must be zero or positive', 422)
    try:
        return working_day_service.add_working_days(
            start_dt, working_days, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline
        )
    except WorkingCalendarUnavailableError as exc:
        raise EscalationError(exc.message, exc.status_code) from exc
    except ValueError as exc:
        raise EscalationError(str(exc), 422) from exc


def _count_working_days_between(start_dt, end_dt, lgu_id=None, is_formal_deadline=True):
    try:
        return working_day_service.count_working_days_between(
            start_dt, end_dt, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline
        )
    except WorkingCalendarUnavailableError as exc:
        raise EscalationError(exc.message, exc.status_code) from exc


def _working_days_delta(from_dt, to_dt, lgu_id=None, is_formal_deadline=True):
    try:
        return working_day_service.working_days_delta(
            from_dt, to_dt, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline
        )
    except WorkingCalendarUnavailableError as exc:
        raise EscalationError(exc.message, exc.status_code) from exc


def _public_magic_link_url(token):
    from flask import current_app

    base_url = current_app.config.get('APP_FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    return f'{base_url}/magic-links/{token}'
