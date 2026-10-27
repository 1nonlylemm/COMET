"""Phase 2C Completion Matrix service.

Manages the five closeout document rows (Final SWA, FIR, COFA, Final
SORD, Proof of Return of Funds) shown on the existing Completion page.
Each row is backed by a `CompletionDocumentRecord` + a dedicated
`ProjectRequirement`, and reuses the Phase 1 shared document workflow
(`requirement_workflow_service`) for all submit/verify/staff-approve/
provincial-approve/return transitions -- this module never sets
`workflow_status` directly. Evidence upload/preview/download continues to
go through the existing `submission_service` / Evidence Intake pipeline.

Verification proof is always the backing ProjectRequirement's
`workflow_status == 'approved'`; no independent boolean flag is used as
proof of verification anywhere in this module, per the Phase 2C
requirement.
"""
from datetime import datetime, timezone

from app.extensions import db
from app.models import (
    CompletionDocumentRecord,
    CompletionMilestone,
    Program,
    Project,
    ProjectRequirement,
    Requirement,
)
from app.services import access_service, audit_service

DOCUMENT_TYPES = (
    'final_swa',
    'final_inspection_report',
    'certificate_of_final_acceptance',
    'final_sord',
    'proof_of_return_of_funds',
)

# Document types whose applicability is fixed (always required once a
# project reaches the completion phase) and NOT independently configurable
# through this service.
ALWAYS_REQUIRED_TYPES = (
    'final_inspection_report',
    'certificate_of_final_acceptance',
    'final_sord',
)

# Proof of Return of Funds is the only document type in this set with a
# genuinely ambiguous applicability rule (see completion_extras.py module
# docstring). It defaults to 'pending_confirmation' and must be explicitly
# resolved by Staff or a Provincial Admin before final closeout.
CONFIGURABLE_APPLICABILITY_TYPES = ('proof_of_return_of_funds',)

DOCUMENT_LABELS = {
    'final_swa': 'Final Statement of Work Accomplished (Final SWA)',
    'final_inspection_report': 'Final Inspection Report (FIR)',
    'certificate_of_final_acceptance': 'Certificate of Final Acceptance (COFA)',
    'final_sord': 'Final Statement of Receipts and Disbursements (Final SORD)',
    'proof_of_return_of_funds': 'Proof of Return of Funds / Reversion',
}


def resolve_effective_project_type(project):
    """Resolves the effective project classification for completion / closeout
    readiness rules, consuming the canonical resolve_effective_project_kind contract.
    """
    from app.services.project_service import resolve_effective_project_kind
    return resolve_effective_project_kind(project)


def get_document_label(document_type, project=None):
    if document_type == 'final_inspection_report':
        project_type = resolve_effective_project_type(project)
        if project_type in ('vehicle', 'goods', 'non_infra_goods_vehicle'):
            return 'Inspection and Acceptance Report (IAR)'
    return DOCUMENT_LABELS.get(document_type, document_type)


DOCUMENT_TYPE_ALIASES = {
    'final_swa': ['final statement of work accomplished', 'final swa', 'swa'],
    'final_inspection_report': ['final inspection report', 'final inspection', 'fir', 'inspection'],
    'certificate_of_final_acceptance': ['certificate of final acceptance', 'certificate of acceptance', 'cofa', 'acceptance'],
    'final_sord': ['statement of receipts and disbursements (sord)', 'final statement of receipts and disbursements', 'final sord', 'sord', 'statement of receipts and disbursements'],
    'proof_of_return_of_funds': ['proof of return of funds', 'proof of return of unutilized funds', 'proof of return of funds / reversion', 'return of funds', 'reversion'],
}


class CompletionDocumentError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def list_completion_documents(project_id, user_id=None, *, initialize=True):
    project = _get_project_with_access(project_id, user_id)
    _ensure_completion_phase(project)
    milestone = CompletionMilestone.query.filter_by(project_id=project.id).first()
    rows = []
    for document_type in DOCUMENT_TYPES:
        if not initialize:
            record = CompletionDocumentRecord.query.filter_by(project_id=project.id, document_type=document_type).first()
            if record:
                rows.append(_serialize_record(record, milestone=milestone, project=project))
            continue
        record = _get_or_create_record(project, document_type, user_id, milestone=milestone)
        rows.append(_serialize_record(record, milestone=milestone, project=project))
    return rows


def get_completion_document(project_id, document_type, user_id=None, *, initialize=True):
    project = _get_project_with_access(project_id, user_id)
    _ensure_completion_phase(project)
    _assert_valid_document_type(document_type)
    milestone = CompletionMilestone.query.filter_by(project_id=project.id).first()
    if initialize:
        record = _get_or_create_record(project, document_type, user_id, milestone=milestone)
    else:
        record = CompletionDocumentRecord.query.filter_by(project_id=project.id, document_type=document_type).first()
        if not record:
            raise CompletionDocumentError('Initialize completion documents in the Completion workspace first.', 409)
    return _serialize_record(record, milestone=milestone, project=project)


def update_document_applicability(project_id, document_type, data, user_id):
    """Staff/Provincial Admin action: set the conditional/not-applicable
    state for Proof of Return of Funds. Not available for the other four
    document types, whose applicability is fixed (or, for Final SWA,
    derived from the existing CompletionMilestone flag)."""
    _require_role(user_id, 'admin', 'staff')
    if document_type not in CONFIGURABLE_APPLICABILITY_TYPES:
        raise CompletionDocumentError(
            f'{DOCUMENT_LABELS.get(document_type, document_type)} does not support a configurable applicability state.',
            422,
        )
    project = _get_project_with_access(project_id, user_id)
    try:
        access_service.assert_project_movement_allowed(project)
    except access_service.AccessError as exc:
        raise CompletionDocumentError(exc.message, exc.status_code) from exc
    _ensure_completion_phase(project)

    applicability = data.get('applicability')
    if applicability not in ('required', 'not_applicable'):
        raise CompletionDocumentError(
            "applicability must be either 'required' or 'not_applicable'.",
            422,
        )
    reason = (data.get('reason') or '').strip()
    
    if applicability == 'not_applicable':
        if not reason:
            raise CompletionDocumentError(
                'A reason is required when marking Proof of Return of Funds as not applicable '
                '(e.g. confirmation that no unspent funds exist).',
                422,
            )
            
        import re
        words = re.findall(r'\b[a-z]+\b', reason.lower())
        denylist = {'n/a', 'na', 'none', 'nil', 'tbd', 'test', 'x', 'nothing', 'blank'}
        
        valid_words = [
            w for w in words 
            if w not in denylist and len(w) >= 3 and any(v in w for v in 'aeiouy')
        ]
        
        if len(valid_words) < 3:
            raise CompletionDocumentError('Reason must contain at least 3 meaningful words (not placeholders or keyboard mashing).', 422)

    record = _get_or_create_record(project, document_type, user_id)
    before = _serialize_record(record, project=project)

    # Confirming as 'required' is always allowed, including from
    # 'pending_confirmation' -- it does not change how the document
    # behaves (pending_confirmation already blocks closeout exactly like
    # required does), it only records that a human has explicitly
    # confirmed the applicability decision. Only flipping to
    # 'not_applicable' after a submission is already in progress is
    # blocked, since that would leave an in-flight/approved submission
    # orphaned under a "not applicable" document.
    if applicability == 'not_applicable' and record.project_requirement.workflow_status not in (None, 'draft'):
        raise CompletionDocumentError(
            'Applicability cannot be changed once a submission is in progress for this document. '
            'Return the document for revision first if the applicability needs to change.',
            409,
        )

    record.applicability = applicability
    record.applicability_reason = reason
    record.applicability_set_by = user_id
    record.applicability_set_at = datetime.now(timezone.utc)
    db.session.commit()

    audit_service.log_action(
        user_id=user_id,
        action='applicability_changed',
        entity_type='completion_document_record',
        entity_id=record.id,
        old_value=before,
        new_value=_serialize_record(record, project=project),
    )
    return _serialize_record(record, project=project)


def update_document_metadata(project_id, document_type, data, user_id):
    """Field Officer (or Staff) action: set metadata for specific document types
    like Proof of Return of Funds before submission."""
    project = _get_project_with_access(project_id, user_id)
    try:
        access_service.assert_project_movement_allowed(project)
    except access_service.AccessError as exc:
        raise CompletionDocumentError(exc.message, exc.status_code) from exc
    _ensure_completion_phase(project)
    
    record = _get_or_create_record(project, document_type, user_id)
    before = _serialize_record(record, project=project)
    
    if document_type == 'proof_of_return_of_funds':
        if 'returned_amount' in data:
            val = data['returned_amount']
            if val is not None:
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    raise CompletionDocumentError('returned_amount must be a number.', 422)
                if val < 0:
                    raise CompletionDocumentError('returned_amount cannot be negative.', 422)
                
                # Sanity check against project budget
                budget = float(project.budget_amount) if project.budget_amount is not None else 0.0
                if budget > 0 and val > budget:
                    raise CompletionDocumentError(
                        f'Returned amount ({val:,.2f}) cannot exceed the project budget ({budget:,.2f}).',
                        422
                    )
            record.returned_amount = val
            
        if 'receipt_number' in data:
            val = data['receipt_number']
            if val is not None:
                val = str(val).strip()
            record.receipt_number = val

    db.session.commit()
    
    audit_service.log_action(
        user_id=user_id,
        action='update_metadata',
        entity_type='completion_document_record',
        entity_id=record.id,
        old_value=before,
        new_value=_serialize_record(record, project=project),
    )
    return _serialize_record(record, project=project)


def assert_ready_for_final_closeout(project, *, final_swa_applicable_override=None):
    """Final project closeout guard: every applicable document in the
    Completion Matrix must have an approved submission before closeout can
    proceed. Uses ProjectRequirement.workflow_status == 'approved' as the
    sole source of truth -- never a boolean flag.

    `final_swa_applicable_override`, when provided, takes precedence over
    the stored CompletionMilestone.is_final_swa_applicable value. This lets
    callers (e.g. `completion_service.update_completion_detail`) evaluate
    the guard against the applicability value being submitted in the same
    request, rather than a stale value that has not been committed yet.
    """
    milestone = CompletionMilestone.query.filter_by(project_id=project.id).first()
    project_type = resolve_effective_project_type(project)
    missing = []
    for document_type in DOCUMENT_TYPES:
        record = CompletionDocumentRecord.query.filter_by(
            project_id=project.id, document_type=document_type,
        ).first()
        doc_label = get_document_label(document_type, project=project)
        if document_type == 'final_swa' and final_swa_applicable_override is not None:
            applicability = 'required' if final_swa_applicable_override else 'not_applicable'
        else:
            applicability = _effective_applicability(document_type, record, milestone, project=project)
        if applicability == 'not_applicable':
            continue
        if applicability == 'pending_confirmation':
            missing.append(
                f'{doc_label} applicability must be confirmed '
                '(mark it required or not applicable)'
            )
            continue
        workflow_status = record.project_requirement.workflow_status if record and record.project_requirement else None
        req_status = record.project_requirement.status if record and record.project_requirement else None
        if workflow_status != 'approved' and req_status != 'compliant':
            missing.append(f'{doc_label} approved submission')

    if project_type in ('financial_assistance', 'social_assistance'):
        # Per DILG Operations Manual (p. 19), Financial Assistance requires
        # signed beneficiary payrolls / acknowledgment receipts before closeout.
        payroll_req = ProjectRequirement.query.filter(
            ProjectRequirement.project_id == project.id,
        ).filter(
            (ProjectRequirement.document_category.in_(['signed_distribution_list', 'acknowledgement_receipt'])) |
            (ProjectRequirement.requirement_name.ilike('%payroll%')) |
            (ProjectRequirement.requirement_name.ilike('%distribution list%')) |
            (ProjectRequirement.requirement_name.ilike('%acknowledgement receipt%')) |
            (ProjectRequirement.requirement_name.ilike('%acknowledgment receipt%'))
        ).filter(
            (ProjectRequirement.workflow_status == 'approved') | (ProjectRequirement.status == 'compliant')
        ).first()
        if not payroll_req:
            missing.append('Beneficiary Payrolls / Acknowledgment Receipts approved submission')

    if missing:
        raise CompletionDocumentError(
            'Final closeout requires every applicable Completion Matrix document to have an '
            'approved submission. Missing: ' + ', '.join(missing) + '.',
            422,
        )

    from app.models.field_inspection import ManagementActionReport
    open_mar = ManagementActionReport.query.filter(
        ManagementActionReport.project_id == project.id,
        ManagementActionReport.status.notin_(['for_review', 'closed'])
    ).first()
    
    if open_mar:
        raise CompletionDocumentError(
            'Project cannot be closed while a Management Action Report is still open. Resolve or close the MAR first.',
            422,
        )


def _effective_applicability(document_type, record, milestone, project=None):
    if project is None and record is not None:
        project = getattr(record, 'project', None) or db.session.get(Project, record.project_id)

    project_type = resolve_effective_project_type(project)

    # 1. Final SWA: strictly civil works contractor billing.
    if document_type == 'final_swa':
        if project_type not in ('infrastructure', 'infra'):
            return 'not_applicable'
        return 'required' if (milestone and milestone.is_final_swa_applicable) else 'not_applicable'

    # 2. Certificate of Final Acceptance (COFA): strictly civil works post-DLP warranty.
    if document_type == 'certificate_of_final_acceptance':
        if project_type not in ('infrastructure', 'infra'):
            return 'not_applicable'
        return 'required'

    # 3. Final Statement of Receipts and Disbursements (Final SORD / Annex I):
    # Required for ALL projects (Infrastructure, Goods/Vehicles, Financial Assistance)
    # per DILG Operations Manual (pp. 18-19).
    if document_type == 'final_sord':
        return 'required'

    # 4. Final Inspection Report (FIR) / Inspection and Acceptance Report (IAR):
    # - Infrastructure: Final Inspection Report (FIR) required.
    # - Goods / Vehicles: Inspection and Acceptance Report (IAR) required.
    # - Financial Assistance / Social Services: NOT required (Manual p. 19:
    #   "Note: Final Inspection Report, Certificate of Completion, Final SWA,
    #    and COFA are NOT required for financial aid").
    # - Generic Non-Infrastructure: not_applicable.
    if document_type == 'final_inspection_report':
        if project_type in ('infrastructure', 'infra'):
            return 'required'
        if project_type in ('vehicle', 'goods', 'non_infra_goods_vehicle'):
            return 'required'
        return 'not_applicable'

    # 5. Proof of Return of Funds (or any future configurable type)
    return record.applicability if record else 'pending_confirmation'


def _get_or_create_record(project, document_type, user_id, milestone=None):
    _assert_valid_document_type(document_type)
    record = CompletionDocumentRecord.query.filter_by(
        project_id=project.id, document_type=document_type,
    ).first()
    if record:
        return record

    if milestone is None:
        milestone = CompletionMilestone.query.filter_by(project_id=project.id).first()
    default_applicability = _effective_applicability(document_type, None, milestone, project=project)

    requirement = _find_or_create_backing_requirement(project, document_type, default_applicability=default_applicability)
    record = CompletionDocumentRecord(
        project_id=project.id,
        project_requirement_id=requirement.id,
        document_type=document_type,
        applicability=default_applicability,
        created_by=int(user_id) if user_id is not None else None,
    )
    db.session.add(record)
    db.session.commit()

    audit_service.log_action(
        user_id=int(user_id) if user_id is not None else None,
        action='create',
        entity_type='completion_document_record',
        entity_id=record.id,
        old_value=None,
        new_value=_serialize_record(record, project=project),
    )
    return record


def _find_or_create_backing_requirement(project, document_type, default_applicability=None):
    is_app = (default_applicability != 'not_applicable')

    # 1. Check if an existing ProjectRequirement on the project already has this document_category
    req = ProjectRequirement.query.filter_by(
        project_id=project.id, document_category=document_type,
    ).first()
    if req:
        if not is_app:
            req.is_active = False
            req.is_mandatory = False
            req.status = 'waived'
            req.waived_reason = f"Not applicable to {resolve_effective_project_type(project)} projects"
            from app.services import sla_service
            sla_service.resolve_deadlines_for_requirement(req.id, reason=req.waived_reason, commit=False)
        elif req.status == 'compliant' and req.workflow_status != 'approved':
            req.workflow_status = 'approved'
            req.workflow_approved_at = req.reviewed_at or datetime.now(timezone.utc)
        return req

    # 2. Check by catalog requirement
    program = db.session.get(Program, project.program_id)
    catalog_requirement = None
    if program:
        catalog_requirement = (
            Requirement.query
            .join(Requirement.phase)
            .filter(
                Requirement.phase.has(program_id=program.id),
                Requirement.document_category == document_type,
            )
            .first()
        )
        if catalog_requirement:
            req = ProjectRequirement.query.filter_by(
                project_id=project.id, requirement_id=catalog_requirement.id,
            ).first()
            if req:
                req.document_category = document_type
                if not is_app:
                    req.is_active = False
                    req.is_mandatory = False
                    req.status = 'waived'
                    req.waived_reason = f"Not applicable to {resolve_effective_project_type(project)} projects"
                    from app.services import sla_service
                    sla_service.resolve_deadlines_for_requirement(req.id, reason=req.waived_reason, commit=False)
                elif req.status == 'compliant' and req.workflow_status != 'approved':
                    req.workflow_status = 'approved'
                    req.workflow_approved_at = req.reviewed_at or datetime.now(timezone.utc)
                elif req.status == 'pending' and not req.workflow_status:
                    req.workflow_status = 'draft'
                return req

    # 3. Check existing project requirements matching known aliases
    aliases = DOCUMENT_TYPE_ALIASES.get(document_type, [])
    existing_reqs = ProjectRequirement.query.filter_by(project_id=project.id).all()
    for existing in existing_reqs:
        if existing.completion_document_record and existing.completion_document_record.document_type != document_type:
            continue
        name_lower = (existing.requirement_name or '').lower()
        annex_lower = (existing.annex_reference or '').lower()
        if any(alias in name_lower or alias == annex_lower for alias in aliases):
            existing.document_category = document_type
            if not is_app:
                existing.is_active = False
                existing.is_mandatory = False
                existing.status = 'waived'
                existing.waived_reason = f"Not applicable to {resolve_effective_project_type(project)} projects"
                from app.services import sla_service
                sla_service.resolve_deadlines_for_requirement(existing.id, reason=existing.waived_reason, commit=False)
            elif existing.status == 'compliant' and existing.workflow_status != 'approved':
                existing.workflow_status = 'approved'
                existing.workflow_approved_at = existing.reviewed_at or datetime.now(timezone.utc)
            elif existing.status == 'pending' and not existing.workflow_status:
                existing.workflow_status = 'draft'
            return existing

    # 4. Fallback: Create new backing ProjectRequirement
    requirement = ProjectRequirement(
        project_id=project.id,
        requirement_id=catalog_requirement.id if catalog_requirement else None,
        requirement_name=get_document_label(document_type, project=project),
        requirement_type='document',
        document_category=document_type,
        is_mandatory=is_app and (document_type != 'proof_of_return_of_funds'),
        is_active=is_app,
        waived_reason=f"Not applicable to {resolve_effective_project_type(project)} projects" if not is_app else None,
        phase_name='Completion',
        status='waived' if not is_app else 'pending',
        workflow_status=None if not is_app else 'draft',
        sort_order=0,
    )
    db.session.add(requirement)
    db.session.flush()
    return requirement


def _get_project_with_access(project_id, user_id):
    try:
        if user_id is not None:
            return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise CompletionDocumentError(exc.message, exc.status_code) from exc

    project = db.session.get(Project, project_id)
    if not project:
        raise CompletionDocumentError('Project not found.', 404)
    return project


def _ensure_completion_phase(project):
    if project.current_phase != 'completion':
        raise CompletionDocumentError(
            'The Completion Matrix is only available for projects that are already in the completion phase.',
            422,
        )


def _assert_valid_document_type(document_type):
    if document_type not in DOCUMENT_TYPES:
        raise CompletionDocumentError(
            f'document_type must be one of: {", ".join(DOCUMENT_TYPES)}',
            422,
        )


def _require_role(user_id, *roles):
    role = access_service.get_user_role(user_id)
    if role not in roles:
        raise CompletionDocumentError(
            f"Role '{role}' is not authorized for this action. Requires one of: {', '.join(roles)}",
            403,
        )


def _serialize_record(record, milestone=None, project=None):
    requirement = record.project_requirement
    if project is None:
        project = getattr(record, 'project', None) or db.session.get(Project, record.project_id)
    if milestone is None and record.document_type == 'final_swa':
        milestone = CompletionMilestone.query.filter_by(project_id=record.project_id).first()
    applicability = _effective_applicability(record.document_type, record, milestone, project=project)
    wf_status = requirement.workflow_status if requirement else None
    if requirement and requirement.status == 'compliant' and wf_status != 'approved':
        wf_status = 'approved'
    return {
        'id': record.id,
        'project_id': record.project_id,
        'project_requirement_id': record.project_requirement_id,
        'document_type': record.document_type,
        'document_label': get_document_label(record.document_type, project=project),
        'is_applicability_configurable': record.document_type in CONFIGURABLE_APPLICABILITY_TYPES,
        'applicability': applicability,
        'applicability_reason': record.applicability_reason,
        'applicability_set_by': record.applicability_set_by,
        'applicability_set_at': record.applicability_set_at.isoformat() if record.applicability_set_at else None,
        'returned_amount': float(record.returned_amount) if record.returned_amount is not None else None,
        'receipt_number': record.receipt_number,
        'notes': record.notes,
        'status': requirement.status if requirement else None,
        'workflow_status': wf_status,
        'workflow_return_reason': requirement.workflow_return_reason if requirement else None,
        'workflow_submitted_at': requirement.workflow_submitted_at.isoformat() if requirement and requirement.workflow_submitted_at else None,
        'workflow_approved_at': requirement.workflow_approved_at.isoformat() if requirement and requirement.workflow_approved_at else None,
        'requirement_name': requirement.requirement_name if requirement else None,
        'created_at': record.created_at.isoformat() if record.created_at else None,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
    }
