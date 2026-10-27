from datetime import datetime, timezone

from sqlalchemy import false

from app.extensions import db
from app.models import (
    LguProfile,
    Project,
    ProjectRequirement,
    SlaDeadline,
    User,
    WorkflowComment,
)
from app.services import access_service, audit_service, monitoring_service, project_service, sla_service
from app.services.fiscal_year_scope import (
    apply_project_fiscal_year,
    apply_requirement_project_fiscal_year,
    apply_sla_project_fiscal_year,
)


VALID_COMMENT_TYPES = (
    'comment',
    'field_follow_up',
    'submission_update',
    'clarification',
    'acknowledgement',
)
VALID_VISIBILITIES = ('internal', 'field_visible')


class FieldOfficerError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def get_field_summary(user_id, fiscal_year=None):
    _require_field_officer(user_id)
    assigned_lgus = _assigned_lgu_scope(user_id)
    lgu_query = _assigned_lgu_query(user_id)
    project_query = _assigned_project_query(user_id)
    project_query = apply_project_fiscal_year(project_query, fiscal_year)
    requirement_query = _assigned_requirement_query(user_id)
    requirement_query = apply_requirement_project_fiscal_year(requirement_query, fiscal_year)

    ongoing_projects = project_query.filter(Project.overall_status == 'ongoing').count()
    requirement_counts = _requirement_status_counts(requirement_query)
    returned_requirements = _returned_requirements(requirement_query, limit=25)
    sla_dashboard = sla_service.get_sla_dashboard(user_id=user_id, fiscal_year=fiscal_year)
    monitoring_summary = _monitoring_summary(user_id, fiscal_year=fiscal_year)
    recent_comments = list_recent_comments(user_id=user_id, limit=5, fiscal_year=fiscal_year)

    return {
        'scope': {
            'lgus': assigned_lgus,
            'lgu_count': lgu_query.count(),
            'project_count': project_query.count(),
            'fiscal_year': fiscal_year,
        },
        'summary': {
            'assigned_lgus': lgu_query.count(),
            'total_projects': project_query.count(),
            'active_projects': ongoing_projects,
            'ongoing_projects': ongoing_projects,
            'pending_requirements': requirement_counts.get('pending', 0),
            'under_review_requirements': requirement_counts.get('under_review', 0),
            'compliant_requirements': requirement_counts.get('compliant', 0),
            'non_compliant_requirements': requirement_counts.get('non_compliant', 0),
            'not_applicable_requirements': requirement_counts.get('not_applicable', 0),
            'not_applicable': requirement_counts.get('not_applicable', 0),
            'returned_requirements': len(returned_requirements),
            'overdue_deadlines': sla_dashboard.get('overdue', 0),
            'upcoming_deadlines': sla_dashboard.get('upcoming', 0),
            'monitoring_action_projects': monitoring_summary['action_projects'],
        },
        'returned_requirements': returned_requirements,
        'monitoring': monitoring_summary,
        'recent_comments': recent_comments,
    }


def list_assigned_lgus(user_id, fiscal_year=None):
    _require_field_officer(user_id)
    lgus = _assigned_lgu_query(user_id).order_by(LguProfile.name.asc()).all()
    project_counts = _project_counts_by_lgu(user_id, fiscal_year=fiscal_year)
    open_requirement_counts = _open_requirement_counts_by_lgu(user_id, fiscal_year=fiscal_year)
    overdue_counts = _overdue_counts_by_lgu(user_id, fiscal_year=fiscal_year)

    return [
        {
            'id': lgu.id,
            'name': lgu.name,
            'municipality': lgu.municipality,
            'province': lgu.province,
            'cluster_id': lgu.cluster_id,
            'cluster_name': lgu.cluster.name if lgu.cluster else None,
            'contact_person': lgu.contact_person,
            'contact_email': lgu.contact_email,
            'contact_phone': lgu.contact_phone,
            'is_active': lgu.is_active,
            'project_count': project_counts.get(lgu.id, 0),
            'open_requirement_count': open_requirement_counts.get(lgu.id, 0),
            'overdue_deadline_count': overdue_counts.get(lgu.id, 0),
        }
        for lgu in lgus
    ]


def list_action_items(user_id, fiscal_year=None, limit=50):
    _require_field_officer(user_id)
    requirement_query = _assigned_requirement_query(user_id)
    requirement_query = apply_requirement_project_fiscal_year(requirement_query, fiscal_year)
    deadline_query = _assigned_deadline_query(user_id)
    deadline_query = apply_sla_project_fiscal_year(deadline_query, fiscal_year)

    items = []
    items.extend(_requirement_action_items(requirement_query, limit=limit))
    items.extend(_deadline_action_items(deadline_query, limit=limit))
    items.extend(_monitoring_action_items(user_id=user_id, fiscal_year=fiscal_year, limit=limit))

    priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    items.sort(key=lambda item: (priority_order.get(item['priority'], 9), item.get('due_at') or '', item['title']))
    return items[:limit]


def list_requirement_comments(requirement_id, user_id):
    _require_field_officer(user_id)
    requirement = _get_requirement_with_access(requirement_id, user_id=user_id)
    comments = (
        WorkflowComment.query
        .filter_by(entity_type='project_requirement', entity_id=requirement.id)
        .filter(WorkflowComment.visibility.in_(VALID_VISIBILITIES))
        .order_by(WorkflowComment.created_at.asc(), WorkflowComment.id.asc())
        .all()
    )
    return [_serialize_comment(comment) for comment in comments]


def create_requirement_comment(requirement_id, data, user_id):
    _require_field_officer(user_id)
    requirement = _get_requirement_with_access(requirement_id, user_id=user_id)
    try:
        access_service.assert_project_requirement_movement_allowed(requirement)
    except access_service.AccessError as exc:
        raise FieldOfficerError(exc.message, exc.status_code) from exc
    body = str((data or {}).get('body') or '').strip()
    if not body:
        raise FieldOfficerError('Comment body is required.', 422)
    if len(body) > 5000:
        raise FieldOfficerError('Comment body must not exceed 5000 characters.', 422)

    comment_type = (data or {}).get('comment_type') or 'comment'
    if comment_type not in VALID_COMMENT_TYPES:
        raise FieldOfficerError(
            f'comment_type must be one of: {", ".join(VALID_COMMENT_TYPES)}',
            422,
        )

    visibility = (data or {}).get('visibility') or 'internal'
    if visibility not in VALID_VISIBILITIES:
        raise FieldOfficerError(
            f'visibility must be one of: {", ".join(VALID_VISIBILITIES)}',
            422,
        )

    project = requirement.project
    comment = WorkflowComment(
        entity_type='project_requirement',
        entity_id=requirement.id,
        project_id=requirement.project_id,
        project_requirement_id=requirement.id,
        lgu_id=project.lgu_id if project else None,
        author_id=int(user_id),
        visibility=visibility,
        comment_type=comment_type,
        body=body,
    )
    db.session.add(comment)
    db.session.commit()

    serialized = _serialize_comment(comment)
    audit_service.log_action(
        user_id=user_id,
        action='comment',
        entity_type='workflow_comment',
        entity_id=comment.id,
        old_value=None,
        new_value=serialized,
    )
    return serialized


def list_recent_comments(user_id, limit=10, fiscal_year=None):
    _require_field_officer(user_id)
    query = _assigned_comment_query(user_id)
    query = query.filter(WorkflowComment.visibility.in_(VALID_VISIBILITIES))
    if fiscal_year is not None:
        query = query.filter(WorkflowComment.project.has(Project.fiscal_year == fiscal_year))
    comments = query.order_by(WorkflowComment.created_at.desc(), WorkflowComment.id.desc()).limit(limit).all()
    return [_serialize_comment(comment) for comment in comments]


def _require_field_officer(user_id):
    try:
        user = access_service.get_user(user_id)
    except access_service.AccessError as exc:
        raise FieldOfficerError(exc.message, exc.status_code) from exc

    if user.role != 'field_officer':
        raise FieldOfficerError('This workspace is only available to field officers.', 403)
    return user


def _assigned_lgu_scope(user_id):
    lgu_ids = access_service.get_assigned_lgu_ids(user_id)
    if not lgu_ids:
        return []
    lgus = LguProfile.query.filter(LguProfile.id.in_(lgu_ids)).order_by(LguProfile.name.asc()).all()
    return [
        {
            'id': lgu.id,
            'name': lgu.name,
            'municipality': lgu.municipality,
            'province': lgu.province,
            'cluster_id': lgu.cluster_id,
            'cluster_name': lgu.cluster.name if lgu.cluster else None,
        }
        for lgu in lgus
    ]


def _assigned_lgu_query(user_id):
    return access_service.restrict_lgu_query(LguProfile.query, user_id)


def _assigned_project_query(user_id):
    return access_service.restrict_project_query(Project.query, user_id)


def _assigned_requirement_query(user_id):
    return access_service.restrict_project_requirement_query(ProjectRequirement.query, user_id)


def _assigned_deadline_query(user_id):
    scope = access_service.get_access_scope(user_id)
    if scope['unrestricted']:
        return SlaDeadline.query
    lgu_ids = scope['lgu_ids']
    if lgu_ids:
        return SlaDeadline.query.filter(SlaDeadline.project.has(Project.lgu_id.in_(lgu_ids)))
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return SlaDeadline.query.filter(false())
    return SlaDeadline.query.filter(
        SlaDeadline.project.has(Project.lgu.has(LguProfile.cluster_id.in_(cluster_ids)))
    )


def _assigned_comment_query(user_id):
    scope = access_service.get_access_scope(user_id)
    if scope['unrestricted']:
        return WorkflowComment.query
    lgu_ids = scope['lgu_ids']
    if lgu_ids:
        return WorkflowComment.query.filter(WorkflowComment.project.has(Project.lgu_id.in_(lgu_ids)))
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return WorkflowComment.query.filter(false())
    return WorkflowComment.query.filter(
        WorkflowComment.project.has(Project.lgu.has(LguProfile.cluster_id.in_(cluster_ids)))
    )


def _get_requirement_with_access(requirement_id, user_id):
    try:
        return access_service.ensure_project_requirement_access(requirement_id, user_id)
    except access_service.AccessError as exc:
        raise FieldOfficerError(exc.message, exc.status_code) from exc


def _requirement_status_counts(query):
    counts = {}
    for status in ('pending', 'under_review', 'compliant', 'non_compliant', 'waived'):
        counts[status] = query.filter(
            ProjectRequirement.status == status,
            ProjectRequirement.applicability == 'applicable',
        ).count()
    counts['not_applicable'] = query.filter(
        ProjectRequirement.applicability == 'not_applicable'
    ).count()
    return counts


def _returned_requirements(query, limit=10):
    requirements = (
        query
        .filter(
            ProjectRequirement.status.in_(('pending', 'under_review', 'non_compliant')),
            ProjectRequirement.applicability == 'applicable',
        )
        .order_by(ProjectRequirement.updated_at.desc())
        .limit(200)
        .all()
    )
    returned = [item for item in requirements if item.workflow_status == 'returned_for_revision']
    return [_serialize_requirement_card(item, item_type='returned_requirement') for item in returned[:limit]]


def _requirement_action_items(query, limit=50):
    rows = (
        query
        .filter(
            ProjectRequirement.status.in_(('pending', 'under_review', 'non_compliant')),
            ProjectRequirement.applicability == 'applicable',
        )
        .order_by(ProjectRequirement.updated_at.desc())
        .limit(200)
        .all()
    )
    items = []
    for requirement in rows:
        if requirement.workflow_status == 'returned_for_revision':
            latest_revision = _latest_revision(requirement) or {}
            items.append(_serialize_requirement_action(
                requirement,
                action_type='returned_requirement',
                priority='high',
                title='Returned requirement needs LGU follow-up',
                description=latest_revision.get('notes') or 'Reviewer returned this requirement for correction.',
            ))
            continue

        if requirement.status == 'pending':
            items.append(_serialize_requirement_action(
                requirement,
                action_type='pending_evidence',
                priority='medium',
                title='Documentary requirement still pending',
                description='Follow up with the LGU and upload evidence when received.',
            ))
        elif requirement.status == 'under_review':
            items.append(_serialize_requirement_action(
                requirement,
                action_type='under_review',
                priority='low',
                title='Evidence is under PDMU review',
                description='Monitor reviewer feedback or additional correction notes.',
            ))
        elif requirement.status == 'non_compliant':
            items.append(_serialize_requirement_action(
                requirement,
                action_type='non_compliant',
                priority='critical',
                title='Requirement is non-compliant',
                description='Coordinate corrective action with the LGU and PDMU reviewer.',
            ))
    return items[:limit]


def _deadline_action_items(query, limit=50):
    deadlines = (
        query
        .filter(SlaDeadline.is_resolved.is_(False))
        .order_by(SlaDeadline.deadline_date.asc())
        .limit(limit)
        .all()
    )
    items = []
    for deadline in deadlines:
        serialized = sla_service._serialize_sla_deadline(deadline)
        days_remaining = serialized.get('days_remaining')
        is_overdue = bool(serialized.get('is_overdue'))
        if is_overdue:
            priority = 'critical'
            title = 'Working-day deadline is overdue'
        elif days_remaining is not None and days_remaining <= 7:
            priority = 'high'
            title = 'Working-day deadline is near due'
        else:
            priority = 'low'
            title = 'Working-day deadline is active'
        items.append({
            'type': 'deadline',
            'priority': priority,
            'title': title,
            'description': serialized.get('requirement_name') or serialized.get('deadline_type'),
            'project_id': serialized.get('project_id'),
            'project_requirement_id': serialized.get('project_requirement_id'),
            'lgu_id': deadline.project.lgu_id if deadline.project else None,
            'entity_id': deadline.id,
            'status': 'overdue' if is_overdue else 'active',
            'due_at': serialized.get('deadline_date'),
            'days_remaining': days_remaining,
            'payload': serialized,
        })
    return items


def _monitoring_action_items(user_id, fiscal_year=None, limit=50):
    workbench = monitoring_service.get_monitoring_workbench(user_id=user_id, fiscal_year=fiscal_year)
    projects = [
        project for project in workbench.get('projects', [])
        if project.get('monitoring_state') in ('needs_initial_record', 'flagged_follow_up', 'pending_transmittal', 'under_review')
    ]
    projects = projects[:limit]
    items = []
    for project in projects:
        state = project.get('monitoring_state')
        priority = 'high' if state in ('flagged_follow_up', 'pending_transmittal') else 'medium'
        items.append({
            'type': 'monitoring',
            'priority': priority,
            'title': _monitoring_title(state),
            'description': project.get('project_name'),
            'project_id': project.get('project_id'),
            'lgu_id': project.get('lgu_id'),
            'entity_id': project.get('latest_inspection_id') or project.get('project_id'),
            'status': state,
            'due_at': None,
            'payload': project,
        })
    return items


def _monitoring_summary(user_id, fiscal_year=None):
    workbench = monitoring_service.get_monitoring_workbench(user_id=user_id, fiscal_year=fiscal_year)
    projects = workbench.get('projects', [])
    action_states = {'needs_initial_record', 'flagged_follow_up', 'pending_transmittal', 'under_review'}
    return {
        **workbench.get('summary', {}),
        'action_projects': sum(1 for project in projects if project.get('monitoring_state') in action_states),
    }


def _project_counts_by_lgu(user_id, fiscal_year=None):
    query = _assigned_project_query(user_id)
    query = apply_project_fiscal_year(query, fiscal_year)
    rows = (
        query
        .with_entities(Project.lgu_id, db.func.count(Project.id))
        .group_by(Project.lgu_id)
        .all()
    )
    return {lgu_id: count for lgu_id, count in rows}


def _open_requirement_counts_by_lgu(user_id, fiscal_year=None):
    query = _assigned_requirement_query(user_id)
    query = apply_requirement_project_fiscal_year(query, fiscal_year)
    rows = (
        query
        .filter(
            ProjectRequirement.status.in_(('pending', 'under_review', 'non_compliant')),
            ProjectRequirement.applicability == 'applicable',
        )
        .join(Project, ProjectRequirement.project_id == Project.id)
        .with_entities(Project.lgu_id, db.func.count(ProjectRequirement.id))
        .group_by(Project.lgu_id)
        .all()
    )
    return {lgu_id: count for lgu_id, count in rows}


def _overdue_counts_by_lgu(user_id, fiscal_year=None):
    query = _assigned_deadline_query(user_id)
    query = apply_sla_project_fiscal_year(query, fiscal_year)
    rows = (
        query
        .filter(SlaDeadline.is_resolved.is_(False))
        .filter(SlaDeadline.deadline_date < datetime.now(timezone.utc))
        .join(Project, SlaDeadline.project_id == Project.id)
        .with_entities(Project.lgu_id, db.func.count(SlaDeadline.id))
        .group_by(Project.lgu_id)
        .all()
    )
    return {lgu_id: count for lgu_id, count in rows}


def _latest_revision(requirement):
    custom_fields = requirement.custom_fields or {}
    return custom_fields.get('latest_revision')


def _serialize_requirement_card(requirement, item_type='requirement'):
    serialized = project_service._serialize_project_requirement(requirement)
    project = requirement.project
    lgu = project.lgu if project else None
    program = project.program if project else None
    latest_revision = _latest_revision(requirement)
    return {
        **serialized,
        'type': item_type,
        'project_name': project.project_name if project else None,
        'lgu_id': project.lgu_id if project else None,
        'lgu_name': lgu.name if lgu else None,
        'program_name': program.name if program else None,
        'latest_revision': latest_revision,
    }


def _serialize_requirement_action(requirement, action_type, priority, title, description):
    card = _serialize_requirement_card(requirement, item_type=action_type)
    return {
        'type': action_type,
        'priority': priority,
        'title': title,
        'description': description,
        'project_id': requirement.project_id,
        'project_requirement_id': requirement.id,
        'lgu_id': card.get('lgu_id'),
        'entity_id': requirement.id,
        'status': requirement.status,
        'due_at': None,
        'payload': card,
    }


def _monitoring_title(state):
    titles = {
        'needs_initial_record': 'Monitoring record needed',
        'flagged_follow_up': 'Monitoring finding needs follow-up',
        'pending_transmittal': 'Monitoring transmittal is pending',
        'under_review': 'Monitoring output is under review',
    }
    return titles.get(state) or 'Monitoring action needed'


def _serialize_comment(comment):
    author = db.session.get(User, comment.author_id) if comment.author_id else None
    project = db.session.get(Project, comment.project_id) if comment.project_id else None
    requirement = db.session.get(ProjectRequirement, comment.project_requirement_id) if comment.project_requirement_id else None
    lgu = db.session.get(LguProfile, comment.lgu_id) if comment.lgu_id else None
    return {
        'id': comment.id,
        'entity_type': comment.entity_type,
        'entity_id': comment.entity_id,
        'project_id': comment.project_id,
        'project_requirement_id': comment.project_requirement_id,
        'project_name': project.project_name if project else None,
        'requirement_name': requirement.requirement_name if requirement else None,
        'lgu_name': lgu.name if lgu else None,
        'lgu_id': comment.lgu_id,
        'author_id': comment.author_id,
        'author_name': author.full_name if author else None,
        'author_role': author.role if author else None,
        'visibility': comment.visibility,
        'comment_type': comment.comment_type,
        'body': comment.body,
        'created_at': comment.created_at.isoformat() if comment.created_at else None,
        'updated_at': comment.updated_at.isoformat() if comment.updated_at else None,
    }
