from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, false, func, or_

from app.extensions import db
from app.models import DocumentFile, LguProfile, Project, ProjectRequirement, SlaDeadline, Submission
from app.services import access_service, audit_service, working_day_service
from app.services.working_day_service import WorkingCalendarUnavailableError
from app.services.fiscal_year_scope import apply_sla_project_fiscal_year

VALID_DEADLINE_TYPES = ('notice_of_eligibility_5day', 'standard_15day', 'custom_sla', 'rectification_period')

DEADLINE_TYPE_LABELS = {
    'standard_15day': '15-Working-Day Notice Window',
    'notice_of_eligibility_5day': 'Notice of Eligibility (5 Working Days)',
    'rectification_period': 'Rectification Period',
    'custom_sla': 'Internal Tracking Timer',
}


def format_deadline_type(deadline_type: str | None, fallback: str = 'Compliance Deadline') -> str:
    """Format an SLA deadline type into COMET canonical human-readable presentation."""
    if not deadline_type:
        return fallback
    clean_type = str(deadline_type).strip()
    if not clean_type:
        return fallback
    if clean_type in DEADLINE_TYPE_LABELS:
        return DEADLINE_TYPE_LABELS[clean_type]
    lower_type = clean_type.lower()
    if lower_type in DEADLINE_TYPE_LABELS:
        return DEADLINE_TYPE_LABELS[lower_type]
    return clean_type.replace('_', ' ').title()


class SlaError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code


def filter_active_compliance_deadlines(query):
    """Exclude SLA deadlines whose linked requirement is already compliant or validly waived."""
    suppressed_condition = and_(
        SlaDeadline.project_requirement_id.isnot(None),
        SlaDeadline.project_requirement.has(
            or_(
                ProjectRequirement.applicability == 'not_applicable',
                ProjectRequirement.status == 'compliant',
                and_(
                    ProjectRequirement.status == 'waived',
                    ProjectRequirement.waived_reason.isnot(None),
                    func.length(func.trim(ProjectRequirement.waived_reason)) > 0,
                    or_(
                        ProjectRequirement.document_category.is_(None),
                        ProjectRequirement.workflow_status.in_(['approved']),
                        ProjectRequirement.workflow_status.is_(None),
                    ),
                ),
            )
        ),
    )
    return query.filter(~suppressed_condition)


def resolve_deadlines_for_requirement(requirement_id, reason=None, user_id=None, commit=True):
    """Resolve all active SLA deadlines for a requirement when it becomes compliant or validly waived."""
    active_deadlines = SlaDeadline.query.filter(
        SlaDeadline.project_requirement_id == requirement_id,
        SlaDeadline.is_resolved == False,
    ).all()

    if not active_deadlines:
        return []

    now = datetime.now(timezone.utc)
    resolved = []
    for dl in active_deadlines:
        before = _serialize_sla_deadline(dl)
        dl.is_resolved = True
        dl.resolved_at = now
        default_reason = 'Resolved automatically upon requirement satisfaction.'
        note_text = reason or default_reason
        if dl.notes:
            dl.notes = f"{dl.notes} | {note_text}"
        else:
            dl.notes = note_text
        resolved.append((dl, before))

    if commit:
        db.session.commit()

    for dl, before in resolved:
        audit_service.log_action(
            user_id=user_id,
            action='resolve',
            entity_type='sla_deadline',
            entity_id=dl.id,
            old_value=before,
            new_value=_serialize_sla_deadline(dl),
            commit=commit,
        )

    return [dl for dl, _ in resolved]


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


def _get_project_with_access(project_id, user_id=None):
    try:
        if user_id is not None:
            return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise SlaError(exc.message, exc.status_code)

    project = db.session.get(Project, project_id)
    if not project:
        raise SlaError('Project not found', 404)
    return project


def _get_requirement_with_access(requirement_id, user_id=None):
    try:
        if user_id is not None:
            return access_service.ensure_project_requirement_access(requirement_id, user_id)
    except access_service.AccessError as exc:
        raise SlaError(exc.message, exc.status_code)

    requirement = db.session.get(ProjectRequirement, requirement_id)
    if not requirement:
        raise SlaError('Project requirement not found', 404)
    return requirement


def _get_sla_deadline_with_access(sla_id, user_id=None):
    deadline = db.session.get(SlaDeadline, sla_id)
    if not deadline:
        raise SlaError('Working-day deadline not found', 404)

    _get_project_with_access(deadline.project_id, user_id=user_id)
    return deadline


def get_sla_dashboard(user_id=None, fiscal_year=None):
    now = datetime.now(timezone.utc)
    now_db = _to_db_datetime(now)
    base_query = _restrict_deadline_query(SlaDeadline.query, user_id=user_id)
    base_query = apply_sla_project_fiscal_year(base_query, fiscal_year)

    total = base_query.count()
    resolved = base_query.filter(SlaDeadline.is_resolved.is_(True)).count()
    unresolved = total - resolved
    overdue = filter_active_compliance_deadlines(base_query.filter(
        SlaDeadline.is_resolved == False,
        SlaDeadline.deadline_date < now_db,
    )).count()
    seven_working_days = _to_db_datetime(_add_working_days(now, 7, is_formal_deadline=False))
    upcoming = filter_active_compliance_deadlines(base_query.filter(
        SlaDeadline.is_resolved == False,
        SlaDeadline.deadline_date >= now_db,
        SlaDeadline.deadline_date <= seven_working_days,
    )).count()
    escalated = base_query.filter(SlaDeadline.escalation_triggered.is_(True)).count()

    type_counts = {}
    for deadline_type in VALID_DEADLINE_TYPES:
        type_counts[deadline_type] = base_query.filter(SlaDeadline.deadline_type == deadline_type).count()

    return {
        'total': total,
        'active': unresolved,
        'unresolved': unresolved,
        'resolved': resolved,
        'overdue': overdue,
        'upcoming': upcoming,
        'escalated': escalated,
        'by_type': type_counts,
    }


def list_sla_deadlines(project_id=None, project_requirement_id=None, program_id=None, lgu_id=None,
                       deadline_type=None, phase_name=None, requirement_status=None,
                       has_requirement=None, due_bucket=None, is_resolved=None, overdue_only=False,
                       page=1, per_page=20, fiscal_year=None, user_id=None, search=None, project_status=None):
    query = _restrict_deadline_query(SlaDeadline.query, user_id=user_id)
    query = apply_sla_project_fiscal_year(query, fiscal_year)

    if project_status:
        from app.services.project_status import CANONICAL_PROJECT_STATUSES
        if project_status not in CANONICAL_PROJECT_STATUSES:
            raise SlaError('Invalid project implementation status.', 422)
        query = query.filter(SlaDeadline.project.has(Project.overall_status == project_status))
    if project_id is not None:
        query = query.filter(SlaDeadline.project_id == project_id)
    if project_requirement_id is not None:
        query = query.filter(SlaDeadline.project_requirement_id == project_requirement_id)
    if program_id is not None:
        query = query.filter(SlaDeadline.project.has(Project.program_id == program_id))
    if lgu_id is not None:
        query = query.filter(SlaDeadline.project.has(Project.lgu_id == lgu_id))
    if deadline_type:
        query = query.filter(SlaDeadline.deadline_type == deadline_type)
    if phase_name:
        query = query.filter(SlaDeadline.project_requirement.has(ProjectRequirement.phase_name == phase_name))
    if requirement_status:
        query = query.filter(SlaDeadline.project_requirement.has(ProjectRequirement.status == requirement_status))
    if has_requirement is not None:
        if has_requirement:
            query = query.filter(SlaDeadline.project_requirement_id.isnot(None))
        else:
            query = query.filter(SlaDeadline.project_requirement_id.is_(None))
    if is_resolved is not None:
        query = query.filter(SlaDeadline.is_resolved.is_(is_resolved))
    if overdue_only:
        query = query.filter(
            SlaDeadline.is_resolved == False,
            SlaDeadline.deadline_date < _to_db_datetime(datetime.now(timezone.utc)),
        )
        query = filter_active_compliance_deadlines(query)
    query = _filter_due_bucket(query, due_bucket)
    query = _filter_deadline_search(query, search)

    pagination = query.order_by(SlaDeadline.deadline_date.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        'deadlines': [_serialize_sla_deadline(item) for item in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def get_sla_deadline(sla_id, user_id=None):
    return _get_sla_deadline_with_access(sla_id, user_id=user_id)


def get_sla_deadline_detail(sla_id, user_id=None):
    return _serialize_sla_deadline(_get_sla_deadline_with_access(sla_id, user_id=user_id), include_detail=True)


def create_sla_deadline(project_id, deadline_type, trigger_date, deadline_date,
                        sla_working_days=None, project_requirement_id=None,
                        notes=None, user_id=None):
    project = _get_project_with_access(project_id, user_id=user_id)
    try:
        access_service.assert_project_movement_allowed(project_id)
    except access_service.AccessError as exc:
        raise SlaError(exc.message, exc.status_code) from exc

    if deadline_type not in VALID_DEADLINE_TYPES:
        raise SlaError(f'Invalid deadline_type. Must be one of: {", ".join(VALID_DEADLINE_TYPES)}', 422)

    if project_requirement_id:
        requirement = _get_requirement_with_access(project_requirement_id, user_id=user_id)
        if requirement.project_id != project_id:
            raise SlaError('Project requirement does not belong to this project', 422)
        if requirement.status == 'compliant':
            raise SlaError('Cannot create SLA deadline for a compliant requirement', 422)
        from app.services.project_service import is_valid_waived_requirement
        if is_valid_waived_requirement(requirement):
            raise SlaError('Cannot create SLA deadline for a waived requirement', 422)
        existing = SlaDeadline.query.filter(
            SlaDeadline.project_requirement_id == project_requirement_id,
            SlaDeadline.is_resolved == False,
        ).first()
        if existing:
            raise SlaError('An unresolved working-day deadline already exists for this requirement', 409)
    else:
        existing = SlaDeadline.query.filter(
            SlaDeadline.project_id == project_id,
            SlaDeadline.project_requirement_id.is_(None),
            SlaDeadline.deadline_type == deadline_type,
            SlaDeadline.is_resolved == False,
        ).first()
        if existing:
            raise SlaError('An unresolved project-level deadline of this type already exists for this project', 409)

    trigger_dt = _parse_datetime(trigger_date) if isinstance(trigger_date, str) else trigger_date
    deadline_dt = _parse_datetime(deadline_date) if isinstance(deadline_date, str) else deadline_date
    if _to_aware_datetime(deadline_dt) <= _to_aware_datetime(trigger_dt):
        raise SlaError('Deadline date must be after trigger date', 422)

    now_utc = datetime.now(timezone.utc)
    if _to_aware_datetime(deadline_dt) <= now_utc and user_id is not None:
        if not notes or len(notes.strip()) < 10:
            raise SlaError('Recording a backdated deadline that is already overdue requires explanatory notes documenting the transmittal or procedural basis.', 422)

    is_formal = deadline_type in ('standard_15day', 'rectification_period')
    lgu_id = project.lgu_id if project else None
    if sla_working_days is None:
        sla_working_days = _count_working_days_between(trigger_dt, deadline_dt, lgu_id=lgu_id, is_formal_deadline=is_formal)

    deadline = SlaDeadline(
        project_id=project_id,
        project_requirement_id=project_requirement_id,
        deadline_type=deadline_type,
        trigger_date=trigger_dt,
        deadline_date=deadline_dt,
        sla_working_days=sla_working_days,
        notes=notes,
    )
    db.session.add(deadline)
    db.session.flush()

    try:
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='create',
                entity_type='sla_deadline',
                entity_id=deadline.id,
                old_value=None,
                new_value=_serialize_sla_deadline(deadline),
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return deadline


def update_sla_deadline(sla_id, data, user_id=None):
    deadline = _get_sla_deadline_with_access(sla_id, user_id=user_id)
    try:
        access_service.assert_project_movement_allowed(deadline.project_id)
    except access_service.AccessError as exc:
        raise SlaError(exc.message, exc.status_code) from exc
    before = _serialize_sla_deadline(deadline)

    new_deadline_date = deadline.deadline_date
    if 'deadline_type' in data:
        if data['deadline_type'] not in VALID_DEADLINE_TYPES:
            raise SlaError(f'Invalid deadline_type. Must be one of: {", ".join(VALID_DEADLINE_TYPES)}', 422)
        deadline.deadline_type = data['deadline_type']
    if 'deadline_date' in data and data['deadline_date']:
        new_deadline_date = _parse_datetime(data['deadline_date'])
        if _to_aware_datetime(new_deadline_date) <= _to_aware_datetime(deadline.trigger_date):
            raise SlaError('Deadline date must be after trigger date', 422)
        deadline.deadline_date = new_deadline_date
    if 'sla_working_days' in data:
        deadline.sla_working_days = data['sla_working_days']
    elif 'deadline_date' in data and data['deadline_date']:
        is_formal = deadline.deadline_type in ('standard_15day', 'rectification_period')
        lgu_id = deadline.project.lgu_id if deadline.project else None
        deadline.sla_working_days = _count_working_days_between(
            deadline.trigger_date, new_deadline_date, lgu_id=lgu_id, is_formal_deadline=is_formal
        )
    if 'notes' in data:
        deadline.notes = data['notes']
    if 'escalation_triggered' in data:
        deadline.escalation_triggered = _require_bool(data['escalation_triggered'], 'escalation_triggered')

    try:
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='update',
                entity_type='sla_deadline',
                entity_id=deadline.id,
                old_value=before,
                new_value=_serialize_sla_deadline(deadline),
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return deadline


def _require_bool(value, field_name):
    if isinstance(value, bool):
        return value
    raise SlaError(f'{field_name} must be true or false', 422)


def _requirement_has_unresolved_overdue_deadline(requirement_id):
    return (
        SlaDeadline.query
        .filter(
            SlaDeadline.project_requirement_id == requirement_id,
            SlaDeadline.is_resolved == False,
            SlaDeadline.deadline_date < _to_db_datetime(datetime.now(timezone.utc)),
        )
        .first()
        is not None
    )


def _requirement_has_documentary_evidence(requirement_id):
    return (
        db.session.query(DocumentFile.id)
        .join(Submission, DocumentFile.submission_id == Submission.id)
        .filter(Submission.project_requirement_id == requirement_id)
        .first()
        is not None
    )


def _serialize_requirement_status(requirement):
    return {
        'id': requirement.id,
        'project_id': requirement.project_id,
        'requirement_name': requirement.requirement_name,
        'status': requirement.status,
        'reviewed_at': requirement.reviewed_at.isoformat() if requirement.reviewed_at else None,
        'last_action_by': requirement.last_action_by,
        'custom_fields': requirement.custom_fields or {},
    }


def resolve_sla_deadline(sla_id, notes=None, user_id=None):
    deadline = _get_sla_deadline_with_access(sla_id, user_id=user_id)
    try:
        access_service.assert_project_movement_allowed(deadline.project_id)
    except access_service.AccessError as exc:
        raise SlaError(exc.message, exc.status_code) from exc
    if deadline.is_resolved:
        raise SlaError('Working-day deadline is already resolved', 409)

    before = _serialize_sla_deadline(deadline)
    deadline.is_resolved = True
    deadline.resolved_at = datetime.now(timezone.utc)
    if notes:
        deadline.notes = notes

    try:
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='resolve',
                entity_type='sla_deadline',
                entity_id=deadline.id,
                old_value=before,
                new_value=_serialize_sla_deadline(deadline),
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return deadline


def get_overdue_deadlines(project_id=None, fiscal_year=None, user_id=None, lgu_id=None):
    query = _restrict_deadline_query(SlaDeadline.query, user_id=user_id).filter(
        SlaDeadline.is_resolved == False,
        SlaDeadline.deadline_date < _to_db_datetime(datetime.now(timezone.utc)),
    )
    query = apply_sla_project_fiscal_year(query, fiscal_year)
    query = filter_active_compliance_deadlines(query)
    if project_id is not None:
        query = query.filter(SlaDeadline.project_id == project_id)
    if lgu_id is not None:
        query = query.filter(SlaDeadline.project.has(Project.lgu_id == lgu_id))
    return [_serialize_sla_deadline(item) for item in query.order_by(SlaDeadline.deadline_date.asc()).all()]


def auto_create_sla_for_requirement(project_requirement_id, trigger_date=None, user_id=None):
    requirement = _get_requirement_with_access(project_requirement_id, user_id=user_id)
    try:
        access_service.assert_project_requirement_movement_allowed(requirement)
    except access_service.AccessError as exc:
        raise SlaError(exc.message, exc.status_code) from exc
    if not requirement.has_sla:
        raise SlaError('This requirement does not have an SLA working-day deadline', 422)
    if not requirement.sla_days:
        raise SlaError('Working days are not specified for this requirement', 422)
    if requirement.status == 'compliant':
        raise SlaError('Cannot create SLA deadline for a compliant requirement', 422)
    if getattr(requirement, 'applicability', 'applicable') == 'not_applicable':
        raise SlaError('Cannot create SLA deadline for a requirement marked Not Applicable', 422)
    from app.services.project_service import is_valid_waived_requirement
    if is_valid_waived_requirement(requirement):
        raise SlaError('Cannot create SLA deadline for a waived requirement', 422)

    existing = SlaDeadline.query.filter(
        SlaDeadline.project_requirement_id == project_requirement_id,
        SlaDeadline.is_resolved == False,
    ).first()
    if existing:
        raise SlaError('An unresolved working-day deadline already exists for this requirement', 409)

    reference_time = datetime.now(timezone.utc) if trigger_date is None else (
        _parse_datetime(trigger_date) if isinstance(trigger_date, str) else trigger_date
    )
    lgu_id = requirement.project.lgu_id if requirement.project else None
    deadline_date = _add_working_days(reference_time, requirement.sla_days, lgu_id=lgu_id, is_formal_deadline=True)
    deadline_type = (
        'standard_15day' if requirement.sla_days >= 15 else
        'notice_of_eligibility_5day' if requirement.sla_days <= 5 else
        'custom_sla'
    )

    deadline = SlaDeadline(
        project_id=requirement.project_id,
        project_requirement_id=requirement.id,
        deadline_type=deadline_type,
        trigger_date=reference_time,
        deadline_date=deadline_date,
        sla_working_days=requirement.sla_days,
        notes=f'Auto-created from requirement: {requirement.requirement_name}',
    )
    db.session.add(deadline)
    db.session.flush()

    try:
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='create',
                entity_type='sla_deadline',
                entity_id=deadline.id,
                old_value=None,
                new_value=_serialize_sla_deadline(deadline),
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return deadline


def monitor_overdue_deadlines(now=None):
    reference_now = now or datetime.now(timezone.utc)
    query = SlaDeadline.query.filter(
        SlaDeadline.is_resolved == False,
        SlaDeadline.escalation_triggered == False,
        SlaDeadline.deadline_date < _to_db_datetime(reference_now),
    )
    query = filter_active_compliance_deadlines(query)
    overdue_deadlines = query.order_by(SlaDeadline.deadline_date.asc()).all()

    if not overdue_deadlines:
        return {'flagged_count': 0, 'flagged_ids': [], 'evaluated_at': _to_aware_datetime(reference_now).isoformat()}

    changes = []
    flagged_ids = []
    for deadline in overdue_deadlines:
        before = _serialize_sla_deadline(deadline)
        deadline.escalation_triggered = True
        changes.append((deadline, before))
        flagged_ids.append(deadline.id)

    try:
        for deadline, before in changes:
            audit_service.log_action(
                user_id=None,
                action='escalate',
                entity_type='sla_deadline',
                entity_id=deadline.id,
                old_value=before,
                new_value=_serialize_sla_deadline(deadline),
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        'flagged_count': len(flagged_ids),
        'flagged_ids': flagged_ids,
        'evaluated_at': _to_aware_datetime(reference_now).isoformat(),
    }


def _serialize_sla_deadline(deadline, include_detail=False):
    project = db.session.get(Project, deadline.project_id)
    requirement = db.session.get(ProjectRequirement, deadline.project_requirement_id) if deadline.project_requirement_id else None
    lgu = project.lgu if project else None
    program = project.program if project else None
    cluster = lgu.cluster if lgu else None
    now = datetime.now(timezone.utc)
    deadline_at = _to_aware_datetime(deadline.deadline_date)
    days_remaining = None if deadline.is_resolved else _working_days_delta(now, deadline_at, is_formal_deadline=False)
    is_overdue = False if deadline.is_resolved else deadline_at < now

    result = {
        'id': deadline.id,
        'project_id': deadline.project_id,
        'project_requirement_id': deadline.project_requirement_id,
        'deadline_type': deadline.deadline_type,
        'trigger_date': deadline.trigger_date.isoformat() if deadline.trigger_date else None,
        'deadline_date': deadline.deadline_date.isoformat() if deadline.deadline_date else None,
        'sla_working_days': deadline.sla_working_days,
        'is_resolved': deadline.is_resolved,
        'resolved_at': deadline.resolved_at.isoformat() if deadline.resolved_at else None,
        'escalation_triggered': deadline.escalation_triggered,
        'notes': deadline.notes,
        'created_at': deadline.created_at.isoformat() if deadline.created_at else None,
        'project_name': project.project_name if project else None,
        'project_fiscal_year': project.fiscal_year if project else None,
        'project_source_code': project.source_project_code if project else None,
        'program_id': project.program_id if project else None,
        'program_name': program.name if program else None,
        'program_code': program.code if program else None,
        'lgu_id': project.lgu_id if project else None,
        'lgu_name': lgu.name if lgu else None,
        'lgu_municipality': lgu.municipality if lgu else None,
        'cluster_id': lgu.cluster_id if lgu else None,
        'cluster_name': cluster.name if cluster else None,
        'requirement_name': requirement.requirement_name if requirement else None,
        'requirement_phase_name': requirement.phase_name if requirement else None,
        'requirement_status': requirement.status if requirement else None,
        'requirement_type': requirement.requirement_type if requirement else None,
        'requirement_annex_reference': requirement.annex_reference if requirement else None,
        'requirement_is_mandatory': requirement.is_mandatory if requirement else None,
        'requirement_has_sla': requirement.has_sla if requirement else None,
        'requirement_sla_days': requirement.sla_days if requirement else None,
        'timer_scope': 'requirement' if requirement else 'project',
        'days_remaining': days_remaining,
        'is_overdue': is_overdue,
    }

    if include_detail and project:
        result['project'] = {
            'id': project.id,
            'project_name': project.project_name,
            'current_phase': project.current_phase,
            'overall_status': project.overall_status,
        }
    if include_detail and requirement:
        result['requirement'] = {
            'id': requirement.id,
            'requirement_name': requirement.requirement_name,
            'status': requirement.status,
            'has_sla': requirement.has_sla,
            'sla_days': requirement.sla_days,
        }
    return result


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


def _filter_due_bucket(query, due_bucket=None):
    due_bucket = (due_bucket or '').strip().lower()
    if not due_bucket:
        return query

    now = datetime.now(timezone.utc)
    now_db = _to_db_datetime(now)
    if due_bucket in ('report_due_3', 'report_due_7', 'report_future'):
        # Report charts partition active deadlines into disjoint ranges. Keep
        # existing cumulative tracker filters backward compatible.
        day_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        day_3 = _add_working_days(now, 3, is_formal_deadline=False)
        day_7 = _add_working_days(now, 7, is_formal_deadline=False)
        lower = day_end if due_bucket == 'report_due_3' else day_3 if due_bucket == 'report_due_7' else day_7
        query = query.filter(SlaDeadline.is_resolved.is_(False), SlaDeadline.deadline_date > _to_db_datetime(lower))
        if due_bucket != 'report_future':
            query = query.filter(SlaDeadline.deadline_date <= _to_db_datetime(day_3 if due_bucket == 'report_due_3' else day_7))
        return query
    if due_bucket == 'overdue':
        return query.filter(
            SlaDeadline.is_resolved == False,
            SlaDeadline.deadline_date < now_db,
        )
    if due_bucket == 'due_today':
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        return query.filter(
            SlaDeadline.is_resolved == False,
            SlaDeadline.deadline_date >= now_db,
            SlaDeadline.deadline_date <= _to_db_datetime(end_of_day),
        )
    if due_bucket in ('due_3', 'due_in_3'):
        return query.filter(
            SlaDeadline.is_resolved == False,
            SlaDeadline.deadline_date >= now_db,
            SlaDeadline.deadline_date <= _to_db_datetime(_add_working_days(now, 3, is_formal_deadline=False)),
        )
    if due_bucket in ('due_7', 'due_in_7', 'upcoming'):
        return query.filter(
            SlaDeadline.is_resolved == False,
            SlaDeadline.deadline_date >= now_db,
            SlaDeadline.deadline_date <= _to_db_datetime(_add_working_days(now, 7, is_formal_deadline=False)),
        )
    if due_bucket == 'future':
        return query.filter(
            SlaDeadline.is_resolved == False,
            SlaDeadline.deadline_date >= now_db,
        )
    if due_bucket == 'resolved':
        return query.filter(SlaDeadline.is_resolved.is_(True))
    raise SlaError('Invalid due_bucket. Must be one of: overdue, due_today, due_3, due_7, future, resolved', 422)


def _parse_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            raise SlaError(f'Invalid datetime format: {value}. Use ISO 8601 format.', 422)
    return None


def _to_aware_datetime(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_db_datetime(value):
    return _to_aware_datetime(value).replace(tzinfo=None)


def _is_working_day(value, lgu_id=None, is_formal_deadline=True):
    try:
        return working_day_service.is_working_day(value, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline)
    except WorkingCalendarUnavailableError as exc:
        raise SlaError(exc.message, exc.status_code) from exc


def _add_working_days(start_dt, working_days, lgu_id=None, is_formal_deadline=True):
    if working_days is None:
        return start_dt
    if working_days < 0:
        raise SlaError('Working days must be zero or positive', 422)
    try:
        return working_day_service.add_working_days(
            start_dt, working_days, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline
        )
    except WorkingCalendarUnavailableError as exc:
        raise SlaError(exc.message, exc.status_code) from exc
    except ValueError as exc:
        raise SlaError(str(exc), 422) from exc


def _count_working_days_between(start_dt, end_dt, lgu_id=None, is_formal_deadline=True):
    try:
        return working_day_service.count_working_days_between(
            start_dt, end_dt, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline
        )
    except WorkingCalendarUnavailableError as exc:
        raise SlaError(exc.message, exc.status_code) from exc


def _working_days_delta(from_dt, to_dt, lgu_id=None, is_formal_deadline=True):
    try:
        return working_day_service.working_days_delta(
            from_dt, to_dt, lgu_id=lgu_id, is_formal_deadline=is_formal_deadline
        )
    except WorkingCalendarUnavailableError as exc:
        raise SlaError(exc.message, exc.status_code) from exc
