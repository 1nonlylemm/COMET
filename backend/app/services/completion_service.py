from datetime import datetime, timezone

from app.extensions import db
from app.models import CompletionMilestone, GoogleDrivePush, Project
from app.services import access_service, audit_service, completion_documents_service
from app.services.fiscal_year_scope import apply_project_fiscal_year


class CompletionError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def list_completion_projects(*, search=None, fiscal_year=None, page=1, per_page=20, user_id=None):
    query = Project.query.filter(Project.current_phase == 'completion')
    if user_id is not None:
        query = access_service.restrict_project_query(query, user_id)
    query = apply_project_fiscal_year(query, fiscal_year)
    if search:
        query = query.filter(Project.project_name.ilike(f'%{search}%'))

    pagination = query.order_by(Project.updated_at.desc(), Project.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return {
        'projects': [_serialize_completion_project(project) for project in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def get_completion_detail(project_id, user_id=None):
    project = _get_project_with_access(project_id, user_id=user_id)
    _ensure_completion_phase(project)
    return _serialize_completion_project(project, include_detail=True)


def update_completion_detail(project_id, data, user_id):
    _require_role(user_id, 'admin', 'staff')
    project = _get_project_with_access(project_id, user_id=user_id)
    try:
        access_service.assert_project_movement_allowed(project)
    except access_service.AccessError as exc:
        raise CompletionError(exc.message, exc.status_code) from exc
    _ensure_completion_phase(project)
    milestone = _get_or_create_milestone(project)
    data = _normalized_completion_update(data)
    before = _serialize_milestone(milestone, project=project)

    new_physical_completion_pct = data.get('physical_completion_pct', project.physical_completion_pct)
    new_punchlist_total = data.get('punchlist_items_total', milestone.punchlist_items_total)
    new_punchlist_resolved = data.get('punchlist_items_resolved', milestone.punchlist_items_resolved)
    new_certificate = data.get('has_certificate_of_completion', milestone.has_certificate_of_completion)
    new_final_swa = data.get('has_final_swa', milestone.has_final_swa)
    new_annex_j = data.get('has_annex_j', milestone.has_annex_j)
    new_vault_ready = data.get('is_vault_ready', milestone.is_vault_ready)
    requesting_final_approval = bool(data.get('final_approval'))
    if 'final_approval' in data:
        _require_role(user_id, 'admin')

    if requesting_final_approval and 'is_final_swa_applicable' in data:
        if bool(data['is_final_swa_applicable']) != milestone.is_final_swa_applicable:
            raise CompletionError('Applicability changes cannot be submitted in the same request as final approval.', 422)

    _assert_punchlist_consistency(new_punchlist_total, new_punchlist_resolved)
    if requesting_final_approval:
        _assert_ready_for_final_approval(
            physical_completion_pct=new_physical_completion_pct,
            has_certificate_of_completion=new_certificate,
            is_final_swa_applicable=milestone.is_final_swa_applicable,
            has_final_swa=new_final_swa,
            has_annex_j=new_annex_j,
            is_vault_ready=new_vault_ready,
            punchlist_items_total=new_punchlist_total,
            punchlist_items_resolved=new_punchlist_resolved,
            project=project,
        )
        try:
            completion_documents_service.assert_ready_for_final_closeout(project)
        except completion_documents_service.CompletionDocumentError as exc:
            raise CompletionError(exc.message, exc.status_code) from exc

    for field in ('physical_completion_pct', 'punchlist_items_total', 'punchlist_items_resolved', 'punchlist_notes'):
        if field in data:
            setattr(milestone, field, data[field])

    if 'is_final_swa_applicable' in data:
        new_val = bool(data['is_final_swa_applicable'])
        if milestone.is_final_swa_applicable != new_val:
            reason = (data.get('final_swa_applicability_reason') or '').strip()
            if not new_val:
                if not reason:
                    raise CompletionError('A detailed reason is required when marking Final SWA as not applicable.', 422)
                
                import re
                words = re.findall(r'\b[a-z]+\b', reason.lower())
                denylist = {'n/a', 'na', 'none', 'nil', 'tbd', 'test', 'x', 'nothing', 'blank'}
                valid_words = [
                    w for w in words 
                    if w not in denylist and len(w) >= 3 and any(v in w for v in 'aeiouy')
                ]
                if len(valid_words) < 3:
                    raise CompletionError('Final SWA exemption reason must contain at least 3 meaningful words.', 422)
                    
            milestone.is_final_swa_applicable = new_val
            milestone.final_swa_applicability_reason = reason if not new_val else None

        if not milestone.is_final_swa_applicable and 'has_final_swa' not in data:
            milestone.has_final_swa = False
            milestone.swa_verified_by = None
            milestone.swa_verified_at = None
    _apply_document_flag(milestone, 'has_certificate_of_completion', 'certificate_verified_by', 'certificate_verified_at', data, user_id)
    _apply_document_flag(milestone, 'has_final_swa', 'swa_verified_by', 'swa_verified_at', data, user_id)
    _apply_document_flag(milestone, 'has_annex_j', 'annex_j_verified_by', 'annex_j_verified_at', data, user_id)

    if 'is_vault_ready' in data:
        milestone.is_vault_ready = bool(data['is_vault_ready'])
        milestone.vault_locked_at = datetime.now(timezone.utc) if milestone.is_vault_ready else None
    if 'final_approval' in data:
        _require_role(user_id, 'admin')
        if data['final_approval']:
            milestone.final_approval_by = user_id
            milestone.final_approval_at = datetime.now(timezone.utc)
            project.overall_status = 'completed'
        else:
            milestone.final_approval_by = None
            milestone.final_approval_at = None
            if project.overall_status == 'completed':
                reopen_reason = (data.get('reopen_reason') or '').strip()
                if not reopen_reason:
                    raise CompletionError('A reason is required to reopen a completed project.', 422)
                project.overall_status = 'ongoing'
                # Also pass the reopen_reason to audit log manually, or maybe add it to milestone dict temporarily?
                # Actually, the requirement asks for audit_service.log_action, we'll put it in data so it's in the payload,
                # wait, data is passed below, so if we put reopen_reason in before/after, it will show up!
                
                # Notify Provincial Admin
                from app.services import notification_service
                notification_service.notify_project_reopened(project, user_id, reopen_reason)


    if 'physical_completion_pct' in data and data['physical_completion_pct'] is not None:
        project.physical_completion_pct = data['physical_completion_pct']

    action = 'update'
    if 'is_final_swa_applicable' in data and before['is_final_swa_applicable'] != milestone.is_final_swa_applicable:
        action = 'final_swa_applicability_changed'
        
    is_reopening = False
    reopen_reason = data.get('reopen_reason')
    if 'final_approval' in data and not data['final_approval'] and before.get('final_approval_by'):
        action = 'project_reopened'
        is_reopening = True

    db.session.commit()
    
    new_val_payload = _serialize_milestone(milestone, project=project)
    if is_reopening and reopen_reason:
        new_val_payload['reopen_reason'] = reopen_reason
        
    audit_service.log_action(
        user_id=user_id,
        action=action,
        entity_type='completion_milestone',
        entity_id=milestone.id,
        old_value=before,
        new_value=new_val_payload,
    )
    return _serialize_completion_project(project, include_detail=True)


def _get_project_with_access(project_id, user_id=None):
    try:
        if user_id is not None:
            return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise CompletionError(exc.message, exc.status_code) from exc

    project = db.session.get(Project, project_id)
    if not project:
        raise CompletionError('Project not found.', 404)
    return project


def _get_or_create_milestone(project):
    milestone = CompletionMilestone.query.filter_by(project_id=project.id).first()
    if milestone:
        return milestone

    milestone = CompletionMilestone(
        project_id=project.id,
        is_final_swa_applicable=_default_final_swa_applicability(project),
    )
    db.session.add(milestone)
    db.session.flush()
    return milestone


def _ensure_completion_phase(project):
    if project.current_phase != 'completion':
        raise CompletionError(
            'Completion tracking is only available for projects that are already in the completion phase.',
            422,
        )


def _require_role(user_id, *roles):
    role = access_service.get_user_role(user_id)
    if role not in roles:
        raise CompletionError(
            f"Role '{role}' is not authorized for this action. Requires one of: {', '.join(roles)}",
            403,
        )


def _apply_document_flag(milestone, flag_field, by_field, at_field, data, user_id):
    if flag_field not in data:
        return
    new_value = bool(data[flag_field])
    setattr(milestone, flag_field, new_value)
    if new_value:
        setattr(milestone, by_field, user_id)
        setattr(milestone, at_field, datetime.now(timezone.utc))
    else:
        setattr(milestone, by_field, None)
        setattr(milestone, at_field, None)


def _normalized_completion_update(data):
    normalized = dict(data or {})
    if 'physical_completion_pct' in normalized and normalized['physical_completion_pct'] is not None:
        value = normalized['physical_completion_pct']
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CompletionError('physical_completion_pct must be a JSON number.', 422)
        if value < 0 or value > 100:
            raise CompletionError('physical_completion_pct must be between 0 and 100.', 422)
        normalized['physical_completion_pct'] = float(value)

    for field in ('punchlist_items_total', 'punchlist_items_resolved'):
        if field not in normalized or normalized[field] is None:
            continue
        value = normalized[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise CompletionError(f'{field} must be a JSON integer.', 422)
        if value < 0:
            raise CompletionError(f'{field} must be non-negative.', 422)
        normalized[field] = int(value)

    return normalized


def _assert_punchlist_consistency(punchlist_items_total, punchlist_items_resolved):
    if punchlist_items_total is None or punchlist_items_resolved is None:
        return
    if int(punchlist_items_resolved) > int(punchlist_items_total):
        raise CompletionError('Resolved punchlist items cannot exceed the total.', 422)


def _assert_ready_for_final_approval(
    *,
    physical_completion_pct,
    has_certificate_of_completion,
    is_final_swa_applicable,
    has_final_swa,
    has_annex_j,
    is_vault_ready,
    punchlist_items_total,
    punchlist_items_resolved,
    project=None,
):
    missing = []
    project_type = completion_documents_service.resolve_effective_project_type(project) if project else 'infrastructure'
    is_infra = project_type in ('infrastructure', 'infra')

    # Certificate of Completion, Final SWA, and punchlists are civil-works
    # requirements and only apply to Infrastructure projects per DILG
    # PDMU Operations Manual (pp. 18-19).
    if is_infra:
        if float(physical_completion_pct or 0) < 100:
            missing.append('physical completion at 100%')
        if not has_certificate_of_completion:
            missing.append('Certificate of Completion')
        if is_final_swa_applicable and not has_final_swa:
            missing.append('Final SWA')
        if (
            punchlist_items_total is not None
            and punchlist_items_resolved is not None
            and int(punchlist_items_resolved) < int(punchlist_items_total)
        ):
            missing.append('all punchlist items resolved')
        if not has_annex_j:
            missing.append('Annex J / Project Completion Report')
    else:
        # Non-infrastructure projects (Goods, Vehicle, Financial Assistance):
        # Must have all active mandatory completion requirements compliant.
        if project:
            from app.models.project import ProjectRequirement
            from app.services.project_service import is_valid_waived_requirement
            blocking_completion_reqs = ProjectRequirement.query.filter(
                ProjectRequirement.project_id == project.id,
                ProjectRequirement.phase_name == 'Completion',
                ProjectRequirement.is_mandatory == True,
                ProjectRequirement.is_active == True,
                ProjectRequirement.status != 'compliant',
            ).all()
            for b_req in blocking_completion_reqs:
                if getattr(b_req, 'applicability', 'applicable') == 'not_applicable':
                    continue
                if is_valid_waived_requirement(b_req):
                    continue
                missing.append(b_req.requirement_name)

    if not is_vault_ready:
        missing.append('record vault readiness')

    if missing:
        raise CompletionError(
            'Final approval requires the closeout package to be complete. Missing: '
            + ', '.join(missing)
            + '.',
            422,
        )


def _serialize_completion_project(project, include_detail=False):
    milestone = CompletionMilestone.query.filter_by(project_id=project.id).first()
    payload = {
        'project_id': project.id,
        'project_name': project.project_name,
        'fiscal_year': project.fiscal_year,
        'overall_status': project.overall_status,
        'current_phase': project.current_phase,
        'physical_completion_pct': float(project.physical_completion_pct or 0),
        'completion': _serialize_milestone(milestone, project=project),
    }
    if project.lgu:
        payload['lgu'] = {
            'id': project.lgu.id,
            'name': project.lgu.name,
            'municipality': project.lgu.municipality,
            'cluster_name': project.lgu.cluster.name if project.lgu.cluster else None,
        }
    if project.program:
        payload['program'] = {
            'id': project.program.id,
            'name': project.program.name,
            'code': project.program.code,
        }
    if include_detail:
        payload['google_drive_pushes_count'] = project.google_drive_pushes.count()
        latest_push = project.google_drive_pushes.order_by(GoogleDrivePush.created_at.desc()).first()
        payload['latest_google_drive_push'] = {
            'id': latest_push.id,
            'push_status': latest_push.push_status,
            'drive_folder_url': latest_push.drive_folder_url,
            'created_at': latest_push.created_at.isoformat() if latest_push.created_at else None,
        } if latest_push else None
    return payload


def _default_final_swa_applicability(project):
    if not project:
        return False
    project_type = completion_documents_service.resolve_effective_project_type(project)
    return project_type in {'infrastructure', 'infra'}


def _serialize_milestone(milestone, project=None):
    default_swa_applicability = _default_final_swa_applicability(project)
    if milestone is None:
        return {
            'physical_completion_pct': 0,
            'has_certificate_of_completion': False,
            'is_final_swa_applicable': default_swa_applicability,
            'has_final_swa': False,
            'has_annex_j': False,
            'punchlist_items_total': None,
            'punchlist_items_resolved': None,
            'punchlist_notes': None,
            'is_vault_ready': False,
            'vault_locked_at': None,
            'final_approval_by': None,
            'final_approval_at': None,
        }

    return {
        'id': milestone.id,
        'physical_completion_pct': float(milestone.physical_completion_pct or 0),
        'has_certificate_of_completion': bool(milestone.has_certificate_of_completion),
        'is_final_swa_applicable': bool(milestone.is_final_swa_applicable),
        'has_final_swa': bool(milestone.has_final_swa),
        'has_annex_j': bool(milestone.has_annex_j),
        'certificate_verified_at': milestone.certificate_verified_at.isoformat() if milestone.certificate_verified_at else None,
        'swa_verified_at': milestone.swa_verified_at.isoformat() if milestone.swa_verified_at else None,
        'annex_j_verified_at': milestone.annex_j_verified_at.isoformat() if milestone.annex_j_verified_at else None,
        'punchlist_items_total': milestone.punchlist_items_total,
        'punchlist_items_resolved': milestone.punchlist_items_resolved,
        'punchlist_notes': milestone.punchlist_notes,
        'is_vault_ready': bool(milestone.is_vault_ready),
        'vault_locked_at': milestone.vault_locked_at.isoformat() if milestone.vault_locked_at else None,
        'final_approval_by': milestone.final_approval_by,
        'final_approval_at': milestone.final_approval_at.isoformat() if milestone.final_approval_at else None,
    }
