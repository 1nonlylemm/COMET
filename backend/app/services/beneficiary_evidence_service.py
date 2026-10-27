"""Beneficiary evidence service (Phase 2B).

Covers Signed Distribution Lists, Acknowledgement Receipts, Beneficiary
Tracking Records, Turnover Photos, and Delivery Invoices for
Non-Infrastructure projects, per the confirmed Phase 2B requirements'
Beneficiary Receipt Tracking / Evidence Management sections and the PDMU
Manual's Non-Infrastructure Projects completion documentary set
(Inspection and Acceptance Report / Non-Infra Monitoring Template).

Each evidence_type maps 1:1 to an already-reserved document_category on
the shared ProjectRequirement workflow (reserved since Phase 1's
migration), so no new CHECK constraint changes are required. Workflow
state (Draft -> Submitted -> Under Verification -> Staff Approved ->
Pending Provincial Approval -> Approved / Returned) is delegated entirely
to `requirement_workflow_service`, exactly like every other Phase 2A/2B
document type. Evidence upload continues to go through the existing
Evidence Intake / `submission_service` pipeline -- this service only
manages the structured tracking fields (beneficiary count, distribution
date, description), never the file itself.
"""
from datetime import date, datetime

from app.extensions import db
from app.models import BeneficiaryEvidenceRecord, Program, ProjectRequirement, Requirement
from app.services import access_service, appendix_template_catalog, audit_service, submission_service


class BeneficiaryEvidenceError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


VALID_EVIDENCE_TYPES = (
    'signed_distribution_list',
    'acknowledgement_receipt',
    'beneficiary_tracking_record',
    'turnover_photos',
    'delivery_invoice',
)

EVIDENCE_TYPE_LABELS = {
    'signed_distribution_list': 'Signed Distribution List',
    'acknowledgement_receipt': 'Acknowledgement Receipt',
    'beneficiary_tracking_record': 'Beneficiary Tracking Record',
    'turnover_photos': 'Turnover Photos',
    'delivery_invoice': 'Delivery Invoice',
}

_REQUIREMENT_NAME_BY_TYPE = EVIDENCE_TYPE_LABELS


def format_evidence_type(evidence_type: str | None, fallback: str | None = None) -> str:
    """Format a beneficiary evidence type into COMET canonical human-readable presentation."""
    if not evidence_type:
        return fallback or 'Beneficiary Evidence'
    clean_type = str(evidence_type).strip()
    if not clean_type:
        return fallback or 'Beneficiary Evidence'
    if clean_type in EVIDENCE_TYPE_LABELS:
        return EVIDENCE_TYPE_LABELS[clean_type]
    lower_type = clean_type.lower()
    if lower_type in EVIDENCE_TYPE_LABELS:
        return EVIDENCE_TYPE_LABELS[lower_type]
    if fallback is not None:
        return fallback
    return clean_type.replace('_', ' ').title()


def create_record(data, user_id, upload=None):
    project = _get_project_with_access(data.get('project_id'), user_id)
    try:
        access_service.assert_project_movement_allowed(project)
    except access_service.AccessError as exc:
        raise BeneficiaryEvidenceError(exc.message, exc.status_code) from exc

    from app.services.project_service import resolve_effective_project_kind
    effective_kind = resolve_effective_project_kind(project)
    if effective_kind != 'financial_assistance':
        raise BeneficiaryEvidenceError(
            f"Beneficiary evidence is only applicable to 'financial_assistance' projects (got '{effective_kind}').",
            422,
        )

    evidence_type = data.get('evidence_type')
    if evidence_type not in VALID_EVIDENCE_TYPES:
        raise BeneficiaryEvidenceError(
            f'evidence_type must be one of: {", ".join(VALID_EVIDENCE_TYPES)}',
            422,
        )
    appendix_reference = _validate_optional_appendix_reference(data.get('appendix_reference'))

    requirement = _get_or_create_backing_requirement(project, evidence_type)
    if appendix_reference:
        requirement.annex_reference = appendix_reference

    record = BeneficiaryEvidenceRecord(
        project_id=project.id,
        project_requirement_id=requirement.id,
        evidence_type=evidence_type,
        appendix_reference=appendix_reference,
        beneficiary_count=_optional_non_negative_int(data.get('beneficiary_count')),
        distribution_date=_parse_optional_date(data.get('distribution_date')),
        reference_number=(data.get('reference_number') or '').strip() or None,
        description=(data.get('description') or '').strip() or None,
        created_by=int(user_id),
    )
    db.session.add(record)

    has_upload = upload is not None and bool(getattr(upload, 'filename', '').strip())
    try:
        if has_upload:
            db.session.flush()
            role = access_service.get_user_role(user_id)
            source = 'field_upload' if role == 'field_officer' else 'dms_ingestion'
            submission_service.create_submission(
                requirement_id=requirement.id,
                source=source,
                description=f'Beneficiary evidence ({_REQUIREMENT_NAME_BY_TYPE.get(evidence_type, evidence_type)})',
                upload=upload,
                user_id=int(user_id),
            )
        db.session.flush()

        audit_service.log_action(
            user_id=int(user_id),
            action='create',
            entity_type='beneficiary_evidence_record',
            entity_id=record.id,
            old_value=None,
            new_value=_serialize_record(record),
            commit=False,
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, (BeneficiaryEvidenceError, access_service.AccessError)):
            raise
        if isinstance(exc, submission_service.SubmissionError):
            raise BeneficiaryEvidenceError(exc.message, exc.status_code) from exc
        raise BeneficiaryEvidenceError(str(exc), 422) from exc

    return record


def update_record(record_id, data, user_id):
    record = _get_record_with_access(record_id, user_id)
    try:
        access_service.assert_project_movement_allowed(record.project_id)
    except access_service.AccessError as exc:
        raise BeneficiaryEvidenceError(exc.message, exc.status_code) from exc
    before = _serialize_record(record)

    if record.project_requirement.workflow_status not in (None, 'draft', 'returned_for_revision'):
        raise BeneficiaryEvidenceError(
            'This record cannot be edited once it has been submitted. Use the workflow return action first.',
            409,
        )

    if 'appendix_reference' in data:
        record.appendix_reference = _validate_optional_appendix_reference(data.get('appendix_reference'))
        if record.appendix_reference and record.project_requirement:
            record.project_requirement.annex_reference = record.appendix_reference
    if 'beneficiary_count' in data:
        record.beneficiary_count = _optional_non_negative_int(data.get('beneficiary_count'))
    if 'distribution_date' in data:
        record.distribution_date = _parse_optional_date(data.get('distribution_date'))
    if 'reference_number' in data:
        record.reference_number = (data.get('reference_number') or '').strip() or None
    if 'description' in data:
        record.description = (data.get('description') or '').strip() or None

    try:
        db.session.flush()
        audit_service.log_action(
            user_id=int(user_id),
            action='update',
            entity_type='beneficiary_evidence_record',
            entity_id=record.id,
            old_value=before,
            new_value=_serialize_record(record),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return record


def get_record(record_id, user_id=None):
    return _get_record_with_access(record_id, user_id)


def list_records(project_id=None, evidence_type=None, workflow_status=None, user_id=None):
    query = BeneficiaryEvidenceRecord.query.join(
        ProjectRequirement, BeneficiaryEvidenceRecord.project_requirement_id == ProjectRequirement.id
    )
    if user_id is not None:
        query = access_service.restrict_project_requirement_query(query, user_id)
    if project_id is not None:
        query = query.filter(BeneficiaryEvidenceRecord.project_id == project_id)
    if evidence_type:
        query = query.filter(BeneficiaryEvidenceRecord.evidence_type == evidence_type)
    if workflow_status:
        query = query.filter(ProjectRequirement.workflow_status == workflow_status)
    items = query.order_by(BeneficiaryEvidenceRecord.created_at.desc()).all()
    return [_serialize_record(item) for item in items]


def _get_or_create_backing_requirement(project, evidence_type):
    program = db.session.get(Program, project.program_id)
    catalog_requirement = None
    if program:
        catalog_requirement = (
            Requirement.query
            .join(Requirement.phase)
            .filter(
                Requirement.phase.has(program_id=program.id),
                Requirement.document_category == evidence_type,
            )
            .first()
        )

    label = _REQUIREMENT_NAME_BY_TYPE.get(evidence_type, evidence_type)
    requirement = ProjectRequirement(
        project_id=project.id,
        requirement_id=catalog_requirement.id if catalog_requirement else None,
        requirement_name=f'{label} ({datetime.now().strftime("%Y-%m-%d")})',
        requirement_type='document',
        document_category=evidence_type,
        is_mandatory=False,
        phase_name='Implementation',
        status='pending',
        workflow_status='draft',
        sort_order=0,
    )
    db.session.add(requirement)
    db.session.flush()
    return requirement


def _get_project_with_access(project_id, user_id):
    if not project_id:
        raise BeneficiaryEvidenceError('project_id is required.', 422)
    try:
        project_id = int(project_id)
    except (TypeError, ValueError) as exc:
        raise BeneficiaryEvidenceError('project_id must be an integer.', 422) from exc
    try:
        return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise BeneficiaryEvidenceError(exc.message, exc.status_code) from exc


def _get_record_with_access(record_id, user_id):
    record = db.session.get(BeneficiaryEvidenceRecord, record_id)
    if not record:
        raise BeneficiaryEvidenceError('Beneficiary evidence record not found.', 404)
    if user_id is not None:
        try:
            access_service.ensure_project_access(record.project_id, user_id)
        except access_service.AccessError as exc:
            raise BeneficiaryEvidenceError(exc.message, exc.status_code) from exc
    return record


def _optional_non_negative_int(value):
    if value in (None, ''):
        return None
    try:
        numeric_value = int(value)
    except (TypeError, ValueError) as exc:
        raise BeneficiaryEvidenceError('beneficiary_count must be an integer.', 422) from exc
    if numeric_value < 0:
        raise BeneficiaryEvidenceError('beneficiary_count must be non-negative.', 422)
    return numeric_value


def _parse_optional_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise BeneficiaryEvidenceError('distribution_date must use YYYY-MM-DD format.', 422) from exc
    raise BeneficiaryEvidenceError('distribution_date must use YYYY-MM-DD format.', 422)


def _validate_optional_appendix_reference(value):
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    item = appendix_template_catalog.get_appendix_by_reference(raw)
    if not item and raw.isdigit():
        item = appendix_template_catalog.get_appendix_by_number(int(raw))
    if not item:
        raise BeneficiaryEvidenceError(
            f"appendix_reference must be a valid Appendix between Appendix 1 and Appendix 19. Received: '{value}'",
            422,
        )
    return item['appendix_reference']


def _serialize_record(record):
    requirement = record.project_requirement
    return {
        'id': record.id,
        'project_id': record.project_id,
        'project_requirement_id': record.project_requirement_id,
        'workflow_status': requirement.workflow_status if requirement else None,
        'workflow_return_reason': requirement.workflow_return_reason if requirement else None,
        'evidence_type': record.evidence_type,
        'appendix_reference': record.appendix_reference,
        'beneficiary_count': record.beneficiary_count,
        'distribution_date': record.distribution_date.isoformat() if record.distribution_date else None,
        'reference_number': record.reference_number,
        'description': record.description,
        'created_by': record.created_by,
        'created_at': record.created_at.isoformat() if record.created_at else None,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
    }
