"""Form 3 (Justification for Project Delay) service.

Implements phase2a-plan.md #8: structured content for a Form 3 request,
plus its supporting MOV (Means of Verification) submission link. Workflow
state (Draft -> Submitted -> Under Verification -> Staff Approved ->
Pending Provincial Approval -> Approved / Returned) is delegated entirely
to the existing Phase 1 `requirement_workflow_service` via the backing
`ProjectRequirement` (tagged `document_category='form_3'`).

An approved Form 3 request suppresses MAR auto-escalation for its covered
reporting period; this suppression check lives in
`monitoring_service.evaluate_monthly_monitoring_risk_trigger`.
"""
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Form3Request, Program, ProjectRequirement, Requirement
from app.services import access_service, audit_service, submission_service


class Form3Error(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


REQUIREMENT_NAME = 'Form 3 - Justification for Project Delay'
DOCUMENT_CATEGORY = 'form_3'
VALID_DELAY_REASON_CATEGORIES = (
    'force_majeure', 'right_of_way', 'procurement_delay', 'weather',
    'funding_delay', 'design_change', 'other',
)


def _validate_mov_submission(project_id, mov_submission_id):
    from app.models import Submission, ProjectRequirement
    if mov_submission_id is None or str(mov_submission_id).strip() == '':
        return None
    try:
        sid = int(mov_submission_id)
    except (ValueError, TypeError):
        raise Form3Error('Invalid mov_submission_id.', 422)
    sub = db.session.get(Submission, sid)
    if not sub:
        raise Form3Error(f'MOV submission {sid} does not exist.', 422)
    sub_req = db.session.get(ProjectRequirement, sub.project_requirement_id)
    if not sub_req or sub_req.project_id != project_id:
        raise Form3Error('Referenced MOV submission does not belong to this project.', 422)
    return sid


def create_request(data, user_id, upload=None):
    project = _get_project_with_access(data.get('project_id'), user_id)
    try:
        access_service.assert_project_movement_allowed(project)
    except access_service.AccessError as exc:
        raise Form3Error(exc.message, exc.status_code) from exc
    reporting_period = _validate_reporting_period(data.get('reporting_period'))

    existing = Form3Request.query.filter_by(project_id=project.id, reporting_period=reporting_period).first()
    if existing:
        raise Form3Error(
            f'A Form 3 request already exists for {reporting_period}. Edit the existing request instead.',
            409,
        )

    delay_reason_category = data.get('delay_reason_category')
    if delay_reason_category and delay_reason_category not in VALID_DELAY_REASON_CATEGORIES:
        raise Form3Error(
            f'delay_reason_category must be one of: {", ".join(VALID_DELAY_REASON_CATEGORIES)}',
            422,
        )

    validated_mov_id = _validate_mov_submission(project.id, data.get('mov_submission_id'))

    requirement = _get_or_create_backing_requirement(project, reporting_period)

    request = Form3Request(
        project_id=project.id,
        project_requirement_id=requirement.id,
        reporting_period=reporting_period,
        delay_reason_category=delay_reason_category,
        justification_text=(data.get('justification_text') or '').strip() or None,
        requested_exemption_start=_parse_optional_date(data.get('requested_exemption_start')),
        requested_exemption_end=_parse_optional_date(data.get('requested_exemption_end')),
        mov_submission_id=validated_mov_id,
        created_by=int(user_id),
    )
    db.session.add(request)

    has_upload = upload is not None and bool(getattr(upload, 'filename', '').strip())
    try:
        if has_upload:
            db.session.flush()
            role = access_service.get_user_role(user_id)
            source = 'field_upload' if role == 'field_officer' else 'dms_ingestion'
            sub = submission_service.create_submission(
                requirement_id=requirement.id,
                source=source,
                description=f'Form 3 MOV evidence for {reporting_period}',
                upload=upload,
                user_id=int(user_id),
            )
            request.mov_submission_id = sub['id']
        db.session.flush()

        audit_service.log_action(
            user_id=int(user_id),
            action='create',
            entity_type='form3_request',
            entity_id=request.id,
            old_value=None,
            new_value=_serialize_request(request),
            commit=False,
        )
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        err_msg = str(exc).lower()
        if 'uq_form3_request_project_period' in err_msg or ('project_id' in err_msg and 'reporting_period' in err_msg):
            raise Form3Error(
                f'A Form 3 request already exists for {reporting_period}. Edit the existing request instead.',
                409,
            ) from exc
        raise Form3Error(str(exc), 422) from exc
    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, (Form3Error, access_service.AccessError)):
            raise
        if isinstance(exc, submission_service.SubmissionError):
            raise Form3Error(exc.message, exc.status_code) from exc
        raise Form3Error(str(exc), 422) from exc

    return request


def update_request(request_id, data, user_id):
    request = _get_request_with_access(request_id, user_id)
    try:
        access_service.assert_project_movement_allowed(request.project_id)
    except access_service.AccessError as exc:
        raise Form3Error(exc.message, exc.status_code) from exc
    before = _serialize_request(request)

    if request.project_requirement.workflow_status not in (None, 'draft', 'returned_for_revision'):
        raise Form3Error(
            'This request cannot be edited once it has been submitted. Use the workflow return action first.',
            409,
        )

    if 'delay_reason_category' in data:
        value = data.get('delay_reason_category')
        if value and value not in VALID_DELAY_REASON_CATEGORIES:
            raise Form3Error(
                f'delay_reason_category must be one of: {", ".join(VALID_DELAY_REASON_CATEGORIES)}',
                422,
            )
        request.delay_reason_category = value
    if 'justification_text' in data:
        request.justification_text = (data.get('justification_text') or '').strip() or None
    if 'requested_exemption_start' in data:
        request.requested_exemption_start = _parse_optional_date(data.get('requested_exemption_start'))
    if 'requested_exemption_end' in data:
        request.requested_exemption_end = _parse_optional_date(data.get('requested_exemption_end'))
    if 'mov_submission_id' in data:
        request.mov_submission_id = _validate_mov_submission(request.project_id, data.get('mov_submission_id'))

    try:
        db.session.flush()
        audit_service.log_action(
            user_id=int(user_id),
            action='update',
            entity_type='form3_request',
            entity_id=request.id,
            old_value=before,
            new_value=_serialize_request(request),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return request


def get_request(request_id, user_id=None):
    return _get_request_with_access(request_id, user_id)


def list_requests(project_id=None, reporting_period=None, workflow_status=None, user_id=None):
    query = Form3Request.query.join(
        ProjectRequirement, Form3Request.project_requirement_id == ProjectRequirement.id
    )
    if user_id is not None:
        query = access_service.restrict_project_requirement_query(query, user_id)
    if project_id is not None:
        query = query.filter(Form3Request.project_id == project_id)
    if reporting_period:
        query = query.filter(Form3Request.reporting_period == reporting_period)
    if workflow_status:
        query = query.filter(ProjectRequirement.workflow_status == workflow_status)
    items = query.order_by(Form3Request.reporting_period.desc()).all()
    return [_serialize_request(item) for item in items]


def _get_or_create_backing_requirement(project, reporting_period):
    program = db.session.get(Program, project.program_id)
    catalog_requirement = None
    if program:
        catalog_requirement = (
            Requirement.query
            .join(Requirement.phase)
            .filter(
                Requirement.phase.has(program_id=program.id),
                Requirement.document_category == DOCUMENT_CATEGORY,
            )
            .first()
        )

    requirement = ProjectRequirement(
        project_id=project.id,
        requirement_id=catalog_requirement.id if catalog_requirement else None,
        requirement_name=f'{REQUIREMENT_NAME} ({reporting_period})',
        requirement_type='document',
        document_category=DOCUMENT_CATEGORY,
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
        raise Form3Error('project_id is required.', 422)
    try:
        project_id = int(project_id)
    except (TypeError, ValueError) as exc:
        raise Form3Error('project_id must be an integer.', 422) from exc
    try:
        return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise Form3Error(exc.message, exc.status_code) from exc


def _get_request_with_access(request_id, user_id):
    request = db.session.get(Form3Request, request_id)
    if not request:
        raise Form3Error('Form 3 request not found.', 404)
    if user_id is not None:
        try:
            access_service.ensure_project_access(request.project_id, user_id)
        except access_service.AccessError as exc:
            raise Form3Error(exc.message, exc.status_code) from exc
    return request


def _validate_reporting_period(value):
    if not value or not isinstance(value, str):
        raise Form3Error('reporting_period is required and must use YYYY-MM format.', 422)
    try:
        datetime.strptime(value, '%Y-%m')
    except ValueError as exc:
        raise Form3Error('reporting_period must use YYYY-MM format.', 422) from exc
    return value


def _parse_optional_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise Form3Error('Date fields must use YYYY-MM-DD format.', 422) from exc
    raise Form3Error('Date fields must use YYYY-MM-DD format.', 422)


def _serialize_request(request):
    requirement = request.project_requirement
    return {
        'id': request.id,
        'project_id': request.project_id,
        'project_requirement_id': request.project_requirement_id,
        'workflow_status': requirement.workflow_status if requirement else None,
        'workflow_return_reason': requirement.workflow_return_reason if requirement else None,
        'mov_submission_id': request.mov_submission_id,
        'reporting_period': request.reporting_period,
        'delay_reason_category': request.delay_reason_category,
        'justification_text': request.justification_text,
        'requested_exemption_start': request.requested_exemption_start.isoformat() if request.requested_exemption_start else None,
        'requested_exemption_end': request.requested_exemption_end.isoformat() if request.requested_exemption_end else None,
        'is_approved_exemption': requirement.workflow_status == 'approved' if requirement else False,
        'created_by': request.created_by,
        'created_at': request.created_at.isoformat() if request.created_at else None,
        'updated_at': request.updated_at.isoformat() if request.updated_at else None,
    }
