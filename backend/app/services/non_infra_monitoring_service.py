"""Non-Infrastructure Monitoring / APM Template service.

Implements the Phase 2B requirement to support Non-Infra Monitoring
Templates and APM Template submissions, per the PDMU Manual's
Implementation Stage step: "Non-infrastructure projects - Accomplish the
monitoring templates (Appendix 1-19), whichever is applicable." Reuses
Phase 1's shared document workflow (`requirement_workflow_service`) via a
backing `ProjectRequirement`, exactly like Phase 2A's Monthly Progress
Report / Form 3 / Project Exception Report services. No new workflow
states, no new upload path -- evidence continues to go through the
existing Evidence Intake / `submission_service` pipeline.

Unlike QAAR (`monitoring_service._ensure_monitoring_type_allowed`), this
record is intentionally project-type-agnostic and is not gated to
non-infrastructure projects only, since infrastructure projects may also
submit an APM Template or an "Other Applicable Monitoring Template" per
the confirmed Phase 2B requirements ("Supported Document Types: APM
Template, Infrastructure Monitoring Template, Non-Infrastructure
Monitoring Template, Other Applicable Monitoring Template").
"""
from datetime import datetime

from app.extensions import db
from app.models import NonInfraMonitoringRecord, Program, ProjectRequirement, Requirement
from app.services import access_service, appendix_template_catalog, audit_service, submission_service


class NonInfraMonitoringError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


REQUIREMENT_NAME = 'Non-Infra Monitoring / APM Template'
VALID_TEMPLATE_TYPES = (
    'apm_template',
    'infrastructure_monitoring_template',
    'non_infrastructure_monitoring_template',
    'other_monitoring_template',
)

TEMPLATE_TYPE_LABELS = {
    'apm_template': 'APM Template',
    'infrastructure_monitoring_template': 'Infrastructure Monitoring Template',
    'non_infrastructure_monitoring_template': 'Non-Infrastructure Monitoring Template',
    'other_monitoring_template': 'Other Applicable Monitoring Template',
}


def format_template_type(template_type: str | None, fallback: str | None = None) -> str:
    """Format a non-infrastructure monitoring template type into COMET canonical human-readable presentation."""
    if not template_type:
        return fallback or 'Non-Infra Monitoring'
    clean_type = str(template_type).strip()
    if not clean_type:
        return fallback or 'Non-Infra Monitoring'
    if clean_type in TEMPLATE_TYPE_LABELS:
        return TEMPLATE_TYPE_LABELS[clean_type]
    lower_type = clean_type.lower()
    if lower_type in TEMPLATE_TYPE_LABELS:
        return TEMPLATE_TYPE_LABELS[lower_type]
    if fallback is not None:
        return fallback
    return clean_type.replace('_', ' ').title()

# APM Template keeps its own reserved document_category (already present
# in the shared workflow's CHECK constraint since Phase 1); every other
# template type shares the generic non-infra monitoring evidence category.
_DOCUMENT_CATEGORY_BY_TEMPLATE_TYPE = {
    'apm_template': 'apm_template',
}
_DEFAULT_DOCUMENT_CATEGORY = 'non_infra_monitoring_evidence'


def _document_category_for(template_type):
    return _DOCUMENT_CATEGORY_BY_TEMPLATE_TYPE.get(template_type, _DEFAULT_DOCUMENT_CATEGORY)


def create_record(data, user_id, upload=None):
    project = _get_project_with_access(data.get('project_id'), user_id)
    try:
        access_service.assert_project_movement_allowed(project)
    except access_service.AccessError as exc:
        raise NonInfraMonitoringError(exc.message, exc.status_code) from exc

    from app.services.project_service import resolve_effective_project_kind
    effective_kind = resolve_effective_project_kind(project)
    if effective_kind == 'infrastructure':
        raise NonInfraMonitoringError(
            "Non-infrastructure monitoring records cannot be created for infrastructure projects.",
            422,
        )

    template_type = data.get('template_type')
    if template_type not in VALID_TEMPLATE_TYPES:
        raise NonInfraMonitoringError(
            f'template_type must be one of: {", ".join(VALID_TEMPLATE_TYPES)}',
            422,
        )
    if template_type == 'apm_template' and effective_kind != 'vehicle':
        raise NonInfraMonitoringError(
            "APM template (Appendix 19) is only applicable to vehicle projects.",
            422,
        )
    reporting_period = _validate_optional_reporting_period(data.get('reporting_period'))
    appendix_reference = _validate_optional_appendix_reference(data.get('appendix_reference'))

    requirement = _get_or_create_backing_requirement(project, template_type, reporting_period)
    if appendix_reference:
        requirement.annex_reference = appendix_reference

    record = NonInfraMonitoringRecord(
        project_id=project.id,
        project_requirement_id=requirement.id,
        template_type=template_type,
        appendix_reference=appendix_reference,
        reporting_period=reporting_period,
        items_verified_summary=(data.get('items_verified_summary') or '').strip() or None,
        specifications_met=_optional_bool(data.get('specifications_met')),
        remarks=(data.get('remarks') or '').strip() or None,
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
                description=f'Non-Infra Monitoring evidence ({format_template_type(template_type)})',
                upload=upload,
                user_id=int(user_id),
            )
        db.session.flush()

        audit_service.log_action(
            user_id=int(user_id),
            action='create',
            entity_type='non_infra_monitoring_record',
            entity_id=record.id,
            old_value=None,
            new_value=_serialize_record(record),
            commit=False,
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, (NonInfraMonitoringError, access_service.AccessError)):
            raise
        if isinstance(exc, submission_service.SubmissionError):
            raise NonInfraMonitoringError(exc.message, exc.status_code) from exc
        raise NonInfraMonitoringError(str(exc), 422) from exc

    return record


def update_record(record_id, data, user_id):
    record = _get_record_with_access(record_id, user_id)
    try:
        access_service.assert_project_movement_allowed(record.project_id)
    except access_service.AccessError as exc:
        raise NonInfraMonitoringError(exc.message, exc.status_code) from exc
    before = _serialize_record(record)

    if record.project_requirement.workflow_status not in (None, 'draft', 'returned_for_revision'):
        raise NonInfraMonitoringError(
            'This record cannot be edited once it has been submitted. Use the workflow return action first.',
            409,
        )

    if 'reporting_period' in data:
        record.reporting_period = _validate_optional_reporting_period(data.get('reporting_period'))
    if 'appendix_reference' in data:
        record.appendix_reference = _validate_optional_appendix_reference(data.get('appendix_reference'))
        if record.appendix_reference and record.project_requirement:
            record.project_requirement.annex_reference = record.appendix_reference
    if 'items_verified_summary' in data:
        record.items_verified_summary = (data.get('items_verified_summary') or '').strip() or None
    if 'specifications_met' in data:
        record.specifications_met = _optional_bool(data.get('specifications_met'))
    if 'remarks' in data:
        record.remarks = (data.get('remarks') or '').strip() or None

    try:
        db.session.flush()
        audit_service.log_action(
            user_id=int(user_id),
            action='update',
            entity_type='non_infra_monitoring_record',
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


def list_records(project_id=None, template_type=None, reporting_period=None, workflow_status=None, user_id=None):
    query = NonInfraMonitoringRecord.query.join(
        ProjectRequirement, NonInfraMonitoringRecord.project_requirement_id == ProjectRequirement.id
    )
    if user_id is not None:
        query = access_service.restrict_project_requirement_query(query, user_id)
    if project_id is not None:
        query = query.filter(NonInfraMonitoringRecord.project_id == project_id)
    if template_type:
        query = query.filter(NonInfraMonitoringRecord.template_type == template_type)
    if reporting_period:
        query = query.filter(NonInfraMonitoringRecord.reporting_period == reporting_period)
    if workflow_status:
        query = query.filter(ProjectRequirement.workflow_status == workflow_status)
    items = query.order_by(NonInfraMonitoringRecord.created_at.desc()).all()
    return [_serialize_record(item) for item in items]


def _get_or_create_backing_requirement(project, template_type, reporting_period):
    document_category = _document_category_for(template_type)
    program = db.session.get(Program, project.program_id)
    catalog_requirement = None
    if program:
        catalog_requirement = (
            Requirement.query
            .join(Requirement.phase)
            .filter(
                Requirement.phase.has(program_id=program.id),
                Requirement.document_category == document_category,
            )
            .first()
        )

    label = reporting_period or datetime.now().strftime('%Y-%m')
    requirement = ProjectRequirement(
        project_id=project.id,
        requirement_id=catalog_requirement.id if catalog_requirement else None,
        requirement_name=f'{REQUIREMENT_NAME} ({format_template_type(template_type)}, {label})',
        requirement_type='document',
        document_category=document_category,
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
        raise NonInfraMonitoringError('project_id is required.', 422)
    try:
        project_id = int(project_id)
    except (TypeError, ValueError) as exc:
        raise NonInfraMonitoringError('project_id must be an integer.', 422) from exc
    try:
        return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise NonInfraMonitoringError(exc.message, exc.status_code) from exc


def _get_record_with_access(record_id, user_id):
    record = db.session.get(NonInfraMonitoringRecord, record_id)
    if not record:
        raise NonInfraMonitoringError('Non-Infra Monitoring record not found.', 404)
    if user_id is not None:
        try:
            access_service.ensure_project_access(record.project_id, user_id)
        except access_service.AccessError as exc:
            raise NonInfraMonitoringError(exc.message, exc.status_code) from exc
    return record


def _validate_optional_reporting_period(value):
    if not value:
        return None
    if not isinstance(value, str):
        raise NonInfraMonitoringError('reporting_period must use YYYY-MM format.', 422)
    try:
        datetime.strptime(value, '%Y-%m')
    except ValueError as exc:
        raise NonInfraMonitoringError('reporting_period must use YYYY-MM format.', 422) from exc
    return value


def _optional_bool(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', '1', 'yes'):
            return True
        if lowered in ('false', '0', 'no'):
            return False
    raise NonInfraMonitoringError('specifications_met must be true or false.', 422)


def _validate_optional_appendix_reference(value):
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    item = appendix_template_catalog.get_appendix_by_reference(raw)
    if not item and raw.isdigit():
        item = appendix_template_catalog.get_appendix_by_number(int(raw))
    if not item:
        raise NonInfraMonitoringError(
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
        'document_category': requirement.document_category if requirement else None,
        'template_type': record.template_type,
        'appendix_reference': record.appendix_reference,
        'reporting_period': record.reporting_period,
        'items_verified_summary': record.items_verified_summary,
        'specifications_met': record.specifications_met,
        'remarks': record.remarks,
        'created_by': record.created_by,
        'created_at': record.created_at.isoformat() if record.created_at else None,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
    }
