"""Shared document workflow service.

Implements the Phase 1 shared state machine that every new document type
(Monthly Progress Report, Form 3, Form 3 MOV, Project Exception Report,
APM Template, Non-Infra Monitoring Evidence, Signed Distribution List,
Acknowledgement Receipt, Beneficiary Tracking Record, Turnover Photos,
Delivery Invoice, Final SWA, FIR, COFA, Final SORD, Proof of Return of
Funds) reuses on top of the existing `ProjectRequirement` / Evidence
Intake architecture:

    Draft -> Submitted -> Under Verification -> Staff Approved ->
    Pending Provincial Approval -> Approved

    Under Verification -> Returned for Revision -> Resubmitted

Roles:
    - Field Officer: create/edit draft, submit, resubmit returned documents
      (own assigned LGU/project scope only).
    - Staff: verify, approve (staff_approve), return (assigned LGUs only).
    - Provincial Admin (the existing operational `admin` role, which already
      has province-wide authority): global approve/return.
    - System Administrator: no operational access to this workflow.

This module intentionally does not duplicate the DMS upload pipeline. It
only governs the `workflow_status` field on `ProjectRequirement` (used for
requirements tagged with a `document_category`) and records transition
history in `RequirementWorkflowTransition`. Evidence upload continues to
go through `submission_service.create_submission`.
"""
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models import (
    DEFICIENCY_CATEGORIES,
    DEFICIENCY_RESOLUTION_STATES,
    ProjectRequirement,
    RequirementDeficiency,
    RequirementWorkflowTransition,
    Submission,
    SubmissionVersion,
)
from app.services import access_service, audit_service, submission_service, workbook_sync_service


class WorkflowError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# Roles allowed to act as the "Provincial Admin" global approver in this
# shared workflow. COMET's existing 'admin' role already matches the
# Provincial Admin responsibilities (global scope, user/LGU management,
# final approve/return authority), so it is reused rather than duplicated.
PROVINCIAL_APPROVER_ROLES = ('admin',)
STAFF_ROLES = ('staff',)
FIELD_OFFICER_ROLES = ('field_officer',)
# Roles allowed to submit/resubmit documentary requirements into the shared review pipeline.
# Field Officers submit from the field; Staff and Provincial Admin submit DMS/PDMU intake.
SUBMITTER_ROLES = FIELD_OFFICER_ROLES + STAFF_ROLES + PROVINCIAL_APPROVER_ROLES
# Roles allowed to move submitted/resubmitted documents to Under Verification.
VERIFIER_ROLES = STAFF_ROLES + PROVINCIAL_APPROVER_ROLES
# Roles allowed to perform preliminary approval (Under Verification -> Pending Provincial Approval).
PRELIMINARY_APPROVER_ROLES = STAFF_ROLES + PROVINCIAL_APPROVER_ROLES

DRAFT = 'draft'
SUBMITTED = 'submitted'
UNDER_VERIFICATION = 'under_verification'
STAFF_APPROVED = 'staff_approved'
PENDING_PROVINCIAL_APPROVAL = 'pending_provincial_approval'
APPROVED = 'approved'
RETURNED_FOR_REVISION = 'returned_for_revision'
RESUBMITTED = 'resubmitted'

ALL_STATES = (
    DRAFT,
    SUBMITTED,
    UNDER_VERIFICATION,
    STAFF_APPROVED,
    PENDING_PROVINCIAL_APPROVAL,
    APPROVED,
    RETURNED_FOR_REVISION,
    RESUBMITTED,
)

# Terminal/active states from which a Field Officer may (re)submit.
SUBMITTABLE_FROM = {DRAFT, None}
RESUBMITTABLE_FROM = {RETURNED_FOR_REVISION}
VERIFIABLE_FROM = {SUBMITTED, RESUBMITTED}
STAFF_APPROVABLE_FROM = {UNDER_VERIFICATION}
PROVINCIAL_APPROVABLE_FROM = {PENDING_PROVINCIAL_APPROVAL, STAFF_APPROVED}
RETURNABLE_FROM = {SUBMITTED, UNDER_VERIFICATION, STAFF_APPROVED, PENDING_PROVINCIAL_APPROVAL, RESUBMITTED}

DEFICIENCY_CATEGORY_LABELS = {
    'missing_attachment': 'Missing Required Attachment',
    'missing_signature_notarization': 'Missing Signature or Notarization',
    'cross_document_inconsistency': 'Cross-Document Inconsistency',
    'costing_dupa_defect': 'Costing / DUPA Defect',
    'missing_statutory_clearance': 'Missing Statutory Clearance',
    'program_specific_non_conformity': 'Program Guidelines Non-Conformity',
    'financial_reconciliation_defect': 'Financial Reconciliation Discrepancy',
    'scan_quality_defect': 'Scan Quality / Legibility Defect',
    'other_documented_defect': 'Other Documented Technical Defect',
}


def format_deficiency_category(category: str | None, fallback: str | None = None) -> str:
    """Format a requirement deficiency category into COMET canonical human-readable presentation."""
    if not category:
        return fallback or 'Documented Defect'
    clean_cat = str(category).strip()
    if not clean_cat:
        return fallback or 'Documented Defect'
    if clean_cat in DEFICIENCY_CATEGORY_LABELS:
        return DEFICIENCY_CATEGORY_LABELS[clean_cat]
    lower_cat = clean_cat.lower()
    if lower_cat in DEFICIENCY_CATEGORY_LABELS:
        return DEFICIENCY_CATEGORY_LABELS[lower_cat]
    if fallback is not None:
        return fallback
    return clean_cat.replace('_', ' ').title()


def _get_requirement_with_access(requirement_id, user_id, for_update=False):
    if for_update:
        requirement = ProjectRequirement.query.filter_by(id=requirement_id).with_for_update().populate_existing().first()
        if not requirement:
            raise WorkflowError('Project requirement not found.', 404)
        try:
            requirement = access_service.ensure_project_requirement_access(requirement, user_id)
        except access_service.AccessError as exc:
            raise WorkflowError(exc.message, exc.status_code) from exc
    else:
        try:
            requirement = access_service.ensure_project_requirement_access(requirement_id, user_id)
        except access_service.AccessError as exc:
            raise WorkflowError(exc.message, exc.status_code) from exc

    if not requirement.document_category:
        raise WorkflowError(
            'This requirement is not part of the shared document workflow (no document_category set).',
            422,
        )
    return requirement


def _require_role(user_id, allowed_roles, message=None):
    role = access_service.get_user_role(user_id)
    if role not in allowed_roles:
        raise WorkflowError(
            message or f"Role '{role}' is not authorized for this action. Requires one of: {', '.join(allowed_roles)}",
            403,
        )
    return role


def _record_transition(requirement, *, from_status, to_status, action, actor_id, reason=None):
    transition = RequirementWorkflowTransition(
        project_requirement_id=requirement.id,
        from_status=from_status,
        to_status=to_status,
        action=action,
        actor_id=actor_id,
        reason=reason,
    )
    db.session.add(transition)
    return transition


def _serialize_requirement_snapshot(requirement):
    active_deficiencies = RequirementDeficiency.query.filter_by(
        project_requirement_id=requirement.id,
        resolution_state='open',
    ).count()
    return {
        'id': requirement.id,
        'project_id': requirement.project_id,
        'requirement_name': requirement.requirement_name,
        'document_category': requirement.document_category,
        'workflow_status': requirement.workflow_status,
        'status': requirement.status,
        'workflow_submitted_by': requirement.workflow_submitted_by,
        'workflow_staff_reviewer_id': requirement.workflow_staff_reviewer_id,
        'workflow_provincial_reviewer_id': requirement.workflow_provincial_reviewer_id,
        'workflow_return_reason': requirement.workflow_return_reason,
        'active_deficiencies_count': active_deficiencies,
    }


def _notify_best_effort(fn, **kwargs):
    try:
        fn(**kwargs)
    except Exception as exc:  # pragma: no cover - defensive, workflow must survive notification failures.
        current_app.logger.warning('Workflow notification failed: %s', exc)


def _validate_robust_text(text, field_name):
    import re
    desc = (text or '').strip().lower()
    if not desc:
        raise WorkflowError(f'{field_name.capitalize()} is required.', 422)
    
    words = re.findall(r'\b[a-z]+\b', desc)
    denylist = {'n/a', 'na', 'none', 'nil', 'tbd', 'test', 'x', 'nothing', 'blank'}
    
    valid_words = [
        w for w in words 
        if w not in denylist and len(w) >= 3 and any(v in w for v in 'aeiouy')
    ]
    
    if len(valid_words) < 3:
        raise WorkflowError(f'{field_name.capitalize()} must contain at least 3 meaningful words (not placeholders or keyboard mashing).', 422)


def submit_requirement(requirement_id, *, user_id, note=None):
    """Submitter action: Draft -> Submitted (or Returned -> Resubmitted).
    Allowed for Field Officer (field upload), Staff (DMS intake), and Provincial Admin (PDMU intake).
    """
    _require_role(user_id, SUBMITTER_ROLES)
    requirement = _get_requirement_with_access(requirement_id, user_id, for_update=True)
    try:
        access_service.assert_project_requirement_movement_allowed(requirement, require_applicable=True)
    except access_service.AccessError as exc:
        raise WorkflowError(exc.message, exc.status_code) from exc

    current = requirement.workflow_status
    if current in RESUBMITTABLE_FROM:
        target = RESUBMITTED
        action = 'resubmit'
    elif current in SUBMITTABLE_FROM:
        target = SUBMITTED
        action = 'submit'
    elif current == RESUBMITTED:
        return requirement
    else:
        raise WorkflowError(
            f'Cannot submit a requirement from workflow status "{current}". '
            'Only draft or returned-for-revision documents can be submitted.',
            409,
        )

    if not submission_service.has_documentary_evidence(requirement.id):
        raise WorkflowError(
            'A documentary file must be uploaded through Evidence Intake before this document can be submitted.',
            422,
        )

    if requirement.document_category == 'project_exception_report':
        from app.models.monitoring_extras import ProjectExceptionReport
        report = ProjectExceptionReport.query.filter_by(project_requirement_id=requirement.id).first()
        if report:
            if not report.exception_category:
                raise WorkflowError('An exception category is required before this report can be submitted.', 422)
            
            _validate_robust_text(report.description, 'description')

    if requirement.document_category in ('apm_template', 'non_infra_monitoring_evidence'):
        from app.models.monitoring_extras import NonInfraMonitoringRecord
        record = NonInfraMonitoringRecord.query.filter_by(project_requirement_id=requirement.id).first()
        if record:
            if record.specifications_met is None:
                raise WorkflowError('Specifications met indicator (Yes/No) is required before this record can be submitted.', 422)
            
            _validate_robust_text(record.items_verified_summary, 'items verified summary')
            
            if record.specifications_met is False:
                _validate_robust_text(record.remarks, 'remarks explaining failed specifications')
            elif record.remarks and record.remarks.strip():
                # If true and they provided remarks, validate them to ensure they aren't garbage
                _validate_robust_text(record.remarks, 'remarks')

    BENEFICIARY_EVIDENCE_CATEGORIES = (
        'signed_distribution_list', 'acknowledgement_receipt',
        'beneficiary_tracking_record', 'turnover_photos', 'delivery_invoice'
    )
    if requirement.document_category in BENEFICIARY_EVIDENCE_CATEGORIES:
        from app.models.monitoring_extras import BeneficiaryEvidenceRecord
        record = BeneficiaryEvidenceRecord.query.filter_by(project_requirement_id=requirement.id).first()
        if record:
            if record.beneficiary_count is None or record.beneficiary_count <= 0:
                raise WorkflowError('A strictly positive beneficiary count is required before this record can be submitted.', 422)
            
            if record.distribution_date is None:
                raise WorkflowError('A distribution date is required before this record can be submitted.', 422)
            
            today = datetime.now(timezone.utc).date()
            if record.distribution_date > today:
                raise WorkflowError('Distribution date cannot be in the future.', 422)
            
            if requirement.project and requirement.project.actual_start_date:
                if record.distribution_date < requirement.project.actual_start_date:
                    raise WorkflowError('Distribution date cannot be before the project actual start date.', 422)
            
            if requirement.document_category in ('turnover_photos', 'delivery_invoice'):
                ref_num = (record.reference_number or '').strip().lower()
                if not ref_num:
                    raise WorkflowError('A reference number is required for this evidence type.', 422)
                
                if len(ref_num) < 3:
                    raise WorkflowError('Reference number must be at least 3 characters long.', 422)
                
                denylist = {'n/a', 'na', 'none', 'nil', 'tbd', 'test', 'x', 'nothing', 'blank'}
                if ref_num in denylist:
                    raise WorkflowError(f'Reference number cannot be a placeholder value like "{ref_num}".', 422)
                    
            _validate_robust_text(record.description, 'description')

    if requirement.document_category == 'proof_of_return_of_funds':
        from app.models.completion_extras import CompletionDocumentRecord
        record = CompletionDocumentRecord.query.filter_by(project_requirement_id=requirement.id).first()
        if record:
            if record.returned_amount is not None and record.returned_amount < 0:
                raise WorkflowError('Returned amount cannot be negative.', 422)

            if record.receipt_number:
                rn = (record.receipt_number or '').strip().lower()
                if len(rn) < 3:
                    raise WorkflowError('Receipt number must be at least 3 characters long.', 422)
                
                denylist = {'n/a', 'na', 'none', 'nil', 'tbd', 'test', 'x', 'nothing', 'blank'}
                if rn in denylist:
                    raise WorkflowError(f'Receipt number cannot be a placeholder value like "{rn}".', 422)

    if requirement.document_category == 'monthly_progress_report':
        from app.models import MonthlyProgressReport
        record = MonthlyProgressReport.query.filter_by(project_requirement_id=requirement.id).first()
        if record and not record.assessment_date:
            raise WorkflowError('An assessment date is required before a Monthly Progress Report can be submitted.', 422)

    before = _serialize_requirement_snapshot(requirement)
    requirement.workflow_status = target
    requirement.workflow_submitted_by = user_id
    requirement.workflow_submitted_at = datetime.now(timezone.utc)
    if target == RESUBMITTED:
        requirement.workflow_return_reason = None
    # Keep the legacy `status` field in sync with the shared workflow so
    # that phase-transition gating (project_service._assert_phase_gate,
    # which checks `status == 'compliant'` on mandatory requirements) and
    # other status-driven code paths correctly reflect a document that is
    # now under active review, instead of staying stuck at 'pending'
    # forever for shared-workflow-backed document types.
    if requirement.status == 'pending':
        requirement.status = 'under_review'
    _record_transition(
        requirement,
        from_status=current,
        to_status=target,
        action=action,
        actor_id=user_id,
        reason=note,
    )
    try:
        audit_service.log_action(
            user_id=user_id,
            action=f'workflow_{action}',
            entity_type='project_requirement',
            entity_id=requirement.id,
            old_value=before,
            new_value=_serialize_requirement_snapshot(requirement),
            commit=False,
        )
        workbook_sync_service.sync_requirement_status(requirement, user_id=user_id, commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _notify_best_effort(
        _notify_workflow_event,
        requirement=requirement,
        event='resubmitted' if action == 'resubmit' else 'submitted',
        actor_id=user_id,
    )
    return requirement


def verify_requirement(requirement_id, *, user_id, note=None):
    """Staff or Provincial Admin action: Submitted/Resubmitted -> Under Verification."""
    _require_role(user_id, VERIFIER_ROLES)
    requirement = _get_requirement_with_access(requirement_id, user_id, for_update=True)
    try:
        access_service.assert_project_requirement_movement_allowed(requirement, require_applicable=True)
    except access_service.AccessError as exc:
        raise WorkflowError(exc.message, exc.status_code) from exc

    current = requirement.workflow_status
    if current not in VERIFIABLE_FROM:
        raise WorkflowError(
            f'Cannot move a requirement to Under Verification from workflow status "{current}".',
            409,
        )

    before = _serialize_requirement_snapshot(requirement)
    requirement.workflow_status = UNDER_VERIFICATION
    requirement.workflow_staff_reviewer_id = user_id
    _record_transition(
        requirement,
        from_status=current,
        to_status=UNDER_VERIFICATION,
        action='verify',
        actor_id=user_id,
        reason=note,
    )
    try:
        audit_service.log_action(
            user_id=user_id,
            action='workflow_verify',
            entity_type='project_requirement',
            entity_id=requirement.id,
            old_value=before,
            new_value=_serialize_requirement_snapshot(requirement),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return requirement


def staff_approve_requirement(requirement_id, *, user_id, note=None):
    """Staff or Provincial Admin action: Under Verification -> Staff Approved -> Pending Provincial Approval."""
    _require_role(user_id, PRELIMINARY_APPROVER_ROLES)
    requirement = _get_requirement_with_access(requirement_id, user_id, for_update=True)
    try:
        access_service.assert_project_requirement_movement_allowed(requirement, require_applicable=True)
    except access_service.AccessError as exc:
        raise WorkflowError(exc.message, exc.status_code) from exc

    current = requirement.workflow_status
    if current not in STAFF_APPROVABLE_FROM:
        raise WorkflowError(
            f'Cannot staff-approve a requirement from workflow status "{current}". '
            'The document must be Under Verification first.',
            409,
        )

    open_count = RequirementDeficiency.query.filter_by(
        project_requirement_id=requirement.id,
        resolution_state='open',
    ).count()
    if open_count > 0:
        raise WorkflowError(
            f'Cannot approve requirement: {open_count} open deficiency item(s) must be resolved first.',
            422,
        )

    before = _serialize_requirement_snapshot(requirement)
    from app.models.user import User
    user = db.session.get(User, user_id)
    if requirement.document_category in ('final_inspection_report', 'certificate_of_final_acceptance'):
        if user and user.role == 'staff' and not getattr(user, 'can_approve_technical_documents', False):
            requirement.has_privilege_override = True
            from app.services import notification_service
            notification_service.notify_requirement_privilege_override(requirement, user_id)

    requirement.workflow_status = PENDING_PROVINCIAL_APPROVAL
    requirement.workflow_staff_reviewer_id = user_id
    requirement.workflow_staff_approved_at = datetime.now(timezone.utc)
    _record_transition(
        requirement,
        from_status=current,
        to_status=STAFF_APPROVED,
        action='staff_approve',
        actor_id=user_id,
        reason=note,
    )
    _record_transition(
        requirement,
        from_status=STAFF_APPROVED,
        to_status=PENDING_PROVINCIAL_APPROVAL,
        action='staff_approve',
        actor_id=user_id,
        reason=note,
    )
    try:
        audit_service.log_action(
            user_id=user_id,
            action='workflow_staff_approve',
            entity_type='project_requirement',
            entity_id=requirement.id,
            old_value=before,
            new_value=_serialize_requirement_snapshot(requirement),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _notify_best_effort(
        _notify_workflow_event,
        requirement=requirement,
        event='staff_approved',
        actor_id=user_id,
    )
    _notify_best_effort(
        _notify_workflow_event,
        requirement=requirement,
        event='pending_provincial_approval',
        actor_id=user_id,
    )
    return requirement


def provincial_approve_requirement(requirement_id, *, user_id, note=None):
    """Provincial Admin action: Pending Provincial Approval -> Approved."""
    _require_role(user_id, PROVINCIAL_APPROVER_ROLES)
    requirement = _get_requirement_with_access(requirement_id, user_id, for_update=True)
    try:
        access_service.assert_project_requirement_movement_allowed(requirement, require_applicable=True)
    except access_service.AccessError as exc:
        raise WorkflowError(exc.message, exc.status_code) from exc

    current = requirement.workflow_status
    if current not in PROVINCIAL_APPROVABLE_FROM:
        raise WorkflowError(
            f'Cannot approve a requirement from workflow status "{current}". '
            'The document must be Pending Provincial Approval first.',
            409,
        )

    open_count = RequirementDeficiency.query.filter_by(
        project_requirement_id=requirement.id,
        resolution_state='open',
    ).count()
    if open_count > 0:
        raise WorkflowError(
            f'Cannot approve requirement: {open_count} open deficiency item(s) must be resolved first.',
            422,
        )

    before = _serialize_requirement_snapshot(requirement)
    requirement.workflow_status = APPROVED
    requirement.workflow_provincial_reviewer_id = user_id
    requirement.workflow_approved_at = datetime.now(timezone.utc)
    # Sync the legacy `status` field to 'compliant' so mandatory
    # shared-workflow-backed requirements correctly satisfy
    # project_service._assert_phase_gate() and other status-driven checks,
    # matching the meaning of a fully-approved document.
    requirement.status = 'compliant'
    requirement.reviewed_at = requirement.workflow_approved_at
    _record_transition(
        requirement,
        from_status=current,
        to_status=APPROVED,
        action='provincial_approve',
        actor_id=user_id,
        reason=note,
    )
    from app.services import sla_service
    sla_service.resolve_deadlines_for_requirement(
        requirement.id,
        reason='Resolved automatically upon provincial approval (compliant).',
        user_id=user_id,
        commit=False,
    )
    try:
        audit_service.log_action(
            user_id=user_id,
            action='workflow_provincial_approve',
            entity_type='project_requirement',
            entity_id=requirement.id,
            old_value=before,
            new_value=_serialize_requirement_snapshot(requirement),
            commit=False,
        )
        workbook_sync_service.sync_requirement_status(requirement, user_id=user_id, commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _notify_best_effort(
        _notify_workflow_event,
        requirement=requirement,
        event='approved',
        actor_id=user_id,
    )

    if requirement.document_category == 'form_3':
        from app.services.monitoring_service import reconcile_mar_for_approved_form3
        from app.models.monitoring_extras import Form3Request
        f3 = Form3Request.query.filter_by(project_requirement_id=requirement.id).first()
        if f3:
            reconcile_mar_for_approved_form3(f3, user_id=user_id)

    return requirement


def return_requirement(requirement_id, *, user_id, reason=None, deficiencies=None):
    """Staff or Provincial Admin action: any active review state -> Returned for Revision.

    Supports structured deficiency logging (Annex E 4-column matrix: category, finding/observation,
    corrective_instruction) and preserves backward compatibility with legacy single-string reason.
    Preserves requirement.status ('under_review' or current) - DOES NOT set 'non_compliant'.
    """
    role = _require_role(user_id, STAFF_ROLES + PROVINCIAL_APPROVER_ROLES)
    requirement = _get_requirement_with_access(requirement_id, user_id, for_update=True)
    try:
        access_service.assert_project_requirement_movement_allowed(requirement, require_applicable=True)
    except access_service.AccessError as exc:
        raise WorkflowError(exc.message, exc.status_code) from exc

    current = requirement.workflow_status
    if current not in RETURNABLE_FROM:
        raise WorkflowError(
            f'Cannot return a requirement for revision from workflow status "{current}".',
            409,
        )

    # Validate inputs: either structured deficiencies list or legacy reason string
    deficiency_items = []
    if deficiencies is not None:
        if not isinstance(deficiencies, list) or len(deficiencies) == 0:
            raise WorkflowError('At least one deficiency item is required when returning a document for revision.', 422)
        for idx, item in enumerate(deficiencies, 1):
            if not isinstance(item, dict):
                raise WorkflowError(f'Deficiency item #{idx} must be an object.', 422)
            cat = str(item.get('category') or '').strip()
            if cat not in DEFICIENCY_CATEGORIES:
                raise WorkflowError(
                    f"Invalid deficiency category '{cat}'. Must be one of: {', '.join(DEFICIENCY_CATEGORIES)}",
                    422,
                )
            finding = str(item.get('finding_observation') or item.get('finding') or '').strip()
            if not finding:
                raise WorkflowError(f'A finding observation is required for deficiency item #{idx}.', 422)
            instruction = str(item.get('corrective_instruction') or item.get('corrective_action') or '').strip()
            if not instruction:
                raise WorkflowError(f'A corrective instruction is required for deficiency item #{idx}.', 422)
            deficiency_items.append({
                'category': cat,
                'finding_observation': finding,
                'corrective_instruction': instruction,
            })
    else:
        # Legacy fallback: single reason string
        cleaned_reason = str(reason or '').strip()
        if not cleaned_reason:
            raise WorkflowError('A return reason or at least one deficiency finding is required when returning a document for revision.', 422)
        deficiency_items.append({
            'category': 'other_documented_defect',
            'finding_observation': cleaned_reason,
            'corrective_instruction': 'Please address the documented defect and resubmit revised documentary files.',
        })

    # Server-side identification of currently active submission and version for provenance
    latest_sub = requirement.submissions.order_by(Submission.id.desc()).first()
    latest_ver = None
    if latest_sub:
        latest_ver = SubmissionVersion.query.filter_by(submission_id=latest_sub.id).order_by(SubmissionVersion.id.desc()).first()

    # Create RequirementDeficiency records
    created_deficiencies = []
    for item in deficiency_items:
        deficiency = RequirementDeficiency(
            project_requirement_id=requirement.id,
            submission_id=latest_sub.id if latest_sub else None,
            submission_version_id=latest_ver.id if latest_ver else None,
            category=item['category'],
            finding_observation=item['finding_observation'],
            corrective_instruction=item['corrective_instruction'],
            resolution_state='open',
            created_by_user_id=user_id,
        )
        db.session.add(deficiency)
        created_deficiencies.append(deficiency)

    # Synthesize workflow_return_reason summary
    if reason and str(reason).strip():
        summary_reason = str(reason).strip()
    else:
        summary_reason = ' | '.join(d['finding_observation'] for d in deficiency_items)

    before = _serialize_requirement_snapshot(requirement)
    requirement.workflow_status = RETURNED_FOR_REVISION
    requirement.workflow_return_reason = summary_reason
    requirement.workflow_returned_by = user_id
    requirement.workflow_returned_at = datetime.now(timezone.utc)
    # Ensure status is 'under_review' (do NOT set 'non_compliant')
    if requirement.status != 'under_review' and requirement.status != 'compliant':
        requirement.status = 'under_review'

    transition = _record_transition(
        requirement,
        from_status=current,
        to_status=RETURNED_FOR_REVISION,
        action='return_for_revision',
        actor_id=user_id,
        reason=summary_reason,
    )
    db.session.flush()

    report_id = None
    report_file_name = None
    stored_object_id = None
    try:
        from app.services import project_service
        report_res = project_service.generate_requirement_correction_report(
            requirement.id,
            user_id=user_id,
            transition_id=transition.id,
            commit=False,
        )
        report_id = report_res.get('report_id')
        report_file_name = report_res.get('file_name')
        stored_object_id = report_res.get('stored_object_id')
    except Exception as exc:
        db.session.rollback()
        raise WorkflowError(f'Failed to generate correction report: {exc}', 500) from exc

    revision_entry = {
        'notes': summary_reason,
        'returned_at': datetime.now(timezone.utc).isoformat(),
        'returned_by': user_id,
        'transition_id': transition.id,
        'report_id': report_id,
        'report_file_name': report_file_name,
        'stored_object_id': stored_object_id,
        'deficiencies_count': len(created_deficiencies),
    }
    custom_fields = dict(requirement.custom_fields or {})
    revision_history = list(custom_fields.get('revision_history') or [])
    revision_history.append(revision_entry)
    custom_fields['latest_revision'] = revision_entry
    custom_fields['revision_history'] = revision_history
    requirement.custom_fields = custom_fields

    try:
        audit_service.log_action(
            user_id=user_id,
            action='workflow_return_for_revision',
            entity_type='project_requirement',
            entity_id=requirement.id,
            old_value=before,
            new_value={
                **_serialize_requirement_snapshot(requirement),
                'deficiencies_count': len(created_deficiencies),
                'categories': [d.category for d in created_deficiencies],
                'report_id': report_id,
            },
            commit=False,
        )
        workbook_sync_service.sync_requirement_status(requirement, user_id=user_id, commit=False)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _notify_best_effort(
        _notify_workflow_event,
        requirement=requirement,
        event='returned',
        actor_id=user_id,
    )
    return requirement


def list_deficiencies(requirement_id, *, user_id, state=None):
    """Return all recorded deficiencies for a requirement, with optional state filter ('open', 'resolved', 'waived', 'all')."""
    requirement = _get_requirement_with_access(requirement_id, user_id)
    query = RequirementDeficiency.query.filter_by(project_requirement_id=requirement.id)
    if state and state != 'all':
        if state not in DEFICIENCY_RESOLUTION_STATES:
            raise WorkflowError(
                f"Invalid deficiency state '{state}'. Must be one of: {', '.join(DEFICIENCY_RESOLUTION_STATES)}, all",
                422,
            )
        query = query.filter_by(resolution_state=state)
    items = query.order_by(RequirementDeficiency.created_at.asc(), RequirementDeficiency.id.asc()).all()
    return [_serialize_deficiency(item) for item in items]


def resolve_deficiency(requirement_id, deficiency_id, *, user_id, resolution_state='resolved', resolution_notes=None):
    """Staff or Provincial Admin action: mark a deficiency as resolved or waived."""
    _require_role(user_id, STAFF_ROLES + PROVINCIAL_APPROVER_ROLES)
    requirement = _get_requirement_with_access(requirement_id, user_id, for_update=True)
    try:
        access_service.assert_project_requirement_movement_allowed(requirement, require_applicable=True)
    except access_service.AccessError as exc:
        raise WorkflowError(exc.message, exc.status_code) from exc

    deficiency = RequirementDeficiency.query.filter_by(
        id=deficiency_id,
        project_requirement_id=requirement.id,
    ).with_for_update().populate_existing().first()
    if not deficiency:
        raise WorkflowError('Deficiency record not found on this requirement.', 404)

    if resolution_state not in ('resolved', 'waived'):
        raise WorkflowError("resolution_state must be 'resolved' or 'waived'.", 422)

    notes = (resolution_notes or '').strip()
    if resolution_state == 'waived' and not notes:
        raise WorkflowError('A justification note is required when waiving a deficiency.', 422)

    # Server-side identification of latest submission version that resolved this
    latest_sub = requirement.submissions.order_by(Submission.id.desc()).first()
    latest_ver = None
    if latest_sub:
        latest_ver = SubmissionVersion.query.filter_by(submission_id=latest_sub.id).order_by(SubmissionVersion.id.desc()).first()

    old_state = deficiency.resolution_state
    deficiency.resolution_state = resolution_state
    deficiency.resolution_notes = notes or None
    deficiency.resolved_by_user_id = user_id
    deficiency.resolved_at = datetime.now(timezone.utc)
    if latest_ver and latest_ver.id != deficiency.submission_version_id:
        deficiency.resolved_submission_version_id = latest_ver.id

    audit_action = 'deficiency_resolved' if resolution_state == 'resolved' else 'deficiency_waived'
    try:
        audit_service.log_action(
            user_id=user_id,
            action=audit_action,
            entity_type='requirement_deficiency',
            entity_id=deficiency.id,
            old_value={'resolution_state': old_state},
            new_value={
                'id': deficiency.id,
                'project_requirement_id': requirement.id,
                'resolution_state': resolution_state,
                'resolution_notes': deficiency.resolution_notes,
                'resolved_by_user_id': user_id,
                'resolved_at': deficiency.resolved_at.isoformat() if deficiency.resolved_at else None,
            },
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return _serialize_deficiency(deficiency)


def _serialize_deficiency(d):
    return {
        'id': d.id,
        'project_requirement_id': d.project_requirement_id,
        'submission_id': d.submission_id,
        'submission_version_id': d.submission_version_id,
        'resolved_submission_version_id': d.resolved_submission_version_id,
        'category': d.category,
        'finding_observation': d.finding_observation,
        'corrective_instruction': d.corrective_instruction,
        'resolution_state': d.resolution_state,
        'resolution_notes': d.resolution_notes,
        'created_by_user_id': d.created_by_user_id,
        'created_by_name': d.created_by.full_name if d.created_by else None,
        'resolved_by_user_id': d.resolved_by_user_id,
        'resolved_by_name': d.resolved_by.full_name if d.resolved_by else None,
        'resolved_at': d.resolved_at.isoformat() if d.resolved_at else None,
        'created_at': d.created_at.isoformat() if d.created_at else None,
        'updated_at': d.updated_at.isoformat() if d.updated_at else None,
    }


# Workflow statuses relevant to each role's V&V Queue view.
STAFF_QUEUE_STATUSES = (SUBMITTED, UNDER_VERIFICATION, RESUBMITTED)
PROVINCIAL_QUEUE_STATUSES = (PENDING_PROVINCIAL_APPROVAL, STAFF_APPROVED)
RETURNED_QUEUE_STATUSES = (RETURNED_FOR_REVISION,)


def list_workflow_queue(*, role_view, document_categories=None, user_id):
    """Return ProjectRequirement rows relevant to the caller's V&V Queue view.

    role_view determines which workflow_status bucket is returned:
      - 'staff': items awaiting Staff verification/action within their scope.
      - 'provincial': items awaiting Provincial Admin approval (global scope).
      - 'returned': items currently returned for revision (visible to both).
    Access scope is enforced via access_service.restrict_project_requirement_query,
    identical to the existing intake/handoff queue pattern.
    """
    if role_view == 'staff':
        statuses = STAFF_QUEUE_STATUSES
    elif role_view == 'provincial':
        statuses = PROVINCIAL_QUEUE_STATUSES
    elif role_view == 'returned':
        statuses = RETURNED_QUEUE_STATUSES
    else:
        raise WorkflowError("role_view must be one of: 'staff', 'provincial', 'returned'.", 422)

    query = ProjectRequirement.query.filter(
        ProjectRequirement.document_category.isnot(None),
        ProjectRequirement.workflow_status.in_(statuses),
    )
    if document_categories:
        query = query.filter(ProjectRequirement.document_category.in_(document_categories))
    query = access_service.restrict_project_requirement_query(query, user_id)
    items = query.order_by(ProjectRequirement.updated_at.desc()).all()
    return [_serialize_queue_item(item) for item in items]


def get_workflow_queue_counts(*, user_id):
    """Return counts for each V&V Queue bucket, scoped to the caller's access."""
    return {
        'staff': len(list_workflow_queue(role_view='staff', user_id=user_id)),
        'provincial': len(list_workflow_queue(role_view='provincial', user_id=user_id)),
        'returned': len(list_workflow_queue(role_view='returned', user_id=user_id)),
    }


def _serialize_queue_item(requirement):
    project = requirement.project
    lgu = project.lgu if project else None
    
    has_data_discrepancy = False
    discrepancy_delta = None
    if requirement.document_category == 'monthly_progress_report':
        from app.models.monitoring_extras import MonthlyProgressReport
        mpr = MonthlyProgressReport.query.filter_by(project_requirement_id=requirement.id).first()
        if mpr:
            has_data_discrepancy = mpr.has_data_discrepancy
            discrepancy_delta = float(mpr.discrepancy_delta) if mpr.discrepancy_delta is not None else None

    active_count = RequirementDeficiency.query.filter_by(
        project_requirement_id=requirement.id,
        resolution_state='open',
    ).count()

    return {
        'id': requirement.id,
        'project_id': requirement.project_id,
        'project_name': project.project_name if project else None,
        'lgu_name': lgu.name if lgu else None,
        'requirement_name': requirement.requirement_name,
        'document_category': requirement.document_category,
        'workflow_status': requirement.workflow_status,
        'workflow_submitted_at': requirement.workflow_submitted_at.isoformat() if requirement.workflow_submitted_at else None,
        'workflow_return_reason': requirement.workflow_return_reason,
        'active_deficiencies_count': active_count,
        'updated_at': requirement.updated_at.isoformat() if requirement.updated_at else None,
        'has_data_discrepancy': has_data_discrepancy,
        'discrepancy_delta': discrepancy_delta,
        'has_privilege_override': getattr(requirement, 'has_privilege_override', False),
    }


def get_requirement_workflow(requirement_id, *, user_id):
    requirement = _get_requirement_with_access(requirement_id, user_id)
    transitions = (
        RequirementWorkflowTransition.query
        .filter_by(project_requirement_id=requirement.id)
        .order_by(RequirementWorkflowTransition.created_at.asc(), RequirementWorkflowTransition.id.asc())
        .all()
    )
    deficiencies = (
        RequirementDeficiency.query
        .filter_by(project_requirement_id=requirement.id)
        .order_by(RequirementDeficiency.created_at.asc(), RequirementDeficiency.id.asc())
        .all()
    )
    return {
        'requirement': _serialize_requirement_snapshot(requirement),
        'transitions': [_serialize_transition(item) for item in transitions],
        'deficiencies': [_serialize_deficiency(d) for d in deficiencies],
    }


def _serialize_transition(transition):
    return {
        'id': transition.id,
        'project_requirement_id': transition.project_requirement_id,
        'from_status': transition.from_status,
        'to_status': transition.to_status,
        'action': transition.action,
        'actor_id': transition.actor_id,
        'actor_name': transition.actor.full_name if transition.actor else None,
        'reason': transition.reason,
        'created_at': transition.created_at.isoformat() if transition.created_at else None,
    }


def _notify_workflow_event(*, requirement, event, actor_id):
    from app.services import notification_service
    notification_service.notify_workflow_transition(
        project_requirement_id=requirement.id,
        event=event,
        actor_user_id=actor_id,
    )

