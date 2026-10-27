"""Project Exception Report service.

Implements phase2a-plan.md #9: contextual documentation of unusual project
conditions or deviations that affect the timeline but do not fit standard
risk tagging. Unlike Form 3, an approved Project Exception Report NEVER
suppresses risk tagging or Management Action Report escalation -- it is
purely informational. Workflow state is delegated entirely to the existing
Phase 1 `requirement_workflow_service` via the backing `ProjectRequirement`
(tagged `document_category='project_exception_report'`).
"""
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Program, ProjectExceptionReport, ProjectRequirement, Requirement
from app.services import access_service, audit_service, submission_service


class ProjectExceptionError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


REQUIREMENT_NAME = 'Project Exception Report'
DOCUMENT_CATEGORY = 'project_exception_report'
VALID_EXCEPTION_CATEGORIES = (
    'force_majeure', 'right_of_way', 'procurement_delay', 'weather',
    'funding_delay', 'design_change', 'scope_change', 'other',
)


def create_report(data, user_id, upload=None):
    project = _get_project_with_access(data.get('project_id'), user_id)
    try:
        access_service.assert_project_movement_allowed(project)
    except access_service.AccessError as exc:
        raise ProjectExceptionError(exc.message, exc.status_code) from exc
    reporting_period = _validate_reporting_period(data.get('reporting_period'))

    existing = ProjectExceptionReport.query.filter_by(
        project_id=project.id,
        reporting_period=reporting_period,
    ).first()
    if existing:
        raise ProjectExceptionError(
            f'A Project Exception Report already exists for {reporting_period}. Edit the existing report instead.',
            409,
        )

    exception_category = data.get('exception_category')
    if exception_category and exception_category not in VALID_EXCEPTION_CATEGORIES:
        raise ProjectExceptionError(
            f'exception_category must be one of: {", ".join(VALID_EXCEPTION_CATEGORIES)}',
            422,
        )

    requirement = _get_or_create_backing_requirement(project, reporting_period)

    report = ProjectExceptionReport(
        project_id=project.id,
        project_requirement_id=requirement.id,
        reporting_period=reporting_period,
        exception_category=exception_category,
        description=(data.get('description') or '').strip() or None,
        created_by=int(user_id),
    )
    db.session.add(report)

    has_upload = upload is not None and bool(getattr(upload, 'filename', '').strip())
    try:
        if has_upload:
            db.session.flush()
            role = access_service.get_user_role(user_id)
            source = 'field_upload' if role == 'field_officer' else 'dms_ingestion'
            submission_service.create_submission(
                requirement_id=requirement.id,
                source=source,
                description=f'Project Exception Report evidence for {reporting_period}',
                upload=upload,
                user_id=int(user_id),
            )
        db.session.flush()

        audit_service.log_action(
            user_id=int(user_id),
            action='create',
            entity_type='project_exception_report',
            entity_id=report.id,
            old_value=None,
            new_value=_serialize_report(report),
            commit=False,
        )
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        err_msg = str(exc).lower()
        if 'uq_project_exception_project_period' in err_msg or ('project_id' in err_msg and 'reporting_period' in err_msg):
            raise ProjectExceptionError(
                f'A Project Exception Report already exists for {reporting_period}. Edit the existing report instead.',
                409,
            ) from exc
        raise ProjectExceptionError(str(exc), 422) from exc
    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, (ProjectExceptionError, access_service.AccessError)):
            raise
        if isinstance(exc, submission_service.SubmissionError):
            raise ProjectExceptionError(exc.message, exc.status_code) from exc
        raise ProjectExceptionError(str(exc), 422) from exc

    return report


def update_report(report_id, data, user_id):
    report = _get_report_with_access(report_id, user_id)
    try:
        access_service.assert_project_movement_allowed(report.project_id)
    except access_service.AccessError as exc:
        raise ProjectExceptionError(exc.message, exc.status_code) from exc
    before = _serialize_report(report)

    if report.project_requirement.workflow_status not in (None, 'draft', 'returned_for_revision'):
        raise ProjectExceptionError(
            'This report cannot be edited once it has been submitted. Use the workflow return action first.',
            409,
        )

    if 'exception_category' in data:
        value = data.get('exception_category')
        if value and value not in VALID_EXCEPTION_CATEGORIES:
            raise ProjectExceptionError(
                f'exception_category must be one of: {", ".join(VALID_EXCEPTION_CATEGORIES)}',
                422,
            )
        report.exception_category = value
    if 'description' in data:
        report.description = (data.get('description') or '').strip() or None

    try:
        db.session.flush()
        audit_service.log_action(
            user_id=int(user_id),
            action='update',
            entity_type='project_exception_report',
            entity_id=report.id,
            old_value=before,
            new_value=_serialize_report(report),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return report


def get_report(report_id, user_id=None):
    return _get_report_with_access(report_id, user_id)


def list_reports(project_id=None, reporting_period=None, workflow_status=None, user_id=None):
    query = ProjectExceptionReport.query.join(
        ProjectRequirement, ProjectExceptionReport.project_requirement_id == ProjectRequirement.id
    )
    if user_id is not None:
        query = access_service.restrict_project_requirement_query(query, user_id)
    if project_id is not None:
        query = query.filter(ProjectExceptionReport.project_id == project_id)
    if reporting_period:
        query = query.filter(ProjectExceptionReport.reporting_period == reporting_period)
    if workflow_status:
        query = query.filter(ProjectRequirement.workflow_status == workflow_status)
    items = query.order_by(ProjectExceptionReport.reporting_period.desc()).all()
    return [_serialize_report(item) for item in items]


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
        raise ProjectExceptionError('project_id is required.', 422)
    try:
        project_id = int(project_id)
    except (TypeError, ValueError) as exc:
        raise ProjectExceptionError('project_id must be an integer.', 422) from exc
    try:
        return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise ProjectExceptionError(exc.message, exc.status_code) from exc


def _get_report_with_access(report_id, user_id):
    report = db.session.get(ProjectExceptionReport, report_id)
    if not report:
        raise ProjectExceptionError('Project Exception Report not found.', 404)
    if user_id is not None:
        try:
            access_service.ensure_project_access(report.project_id, user_id)
        except access_service.AccessError as exc:
            raise ProjectExceptionError(exc.message, exc.status_code) from exc
    return report


def _validate_reporting_period(value):
    if not value or not isinstance(value, str):
        raise ProjectExceptionError('reporting_period is required and must use YYYY-MM format.', 422)
    try:
        datetime.strptime(value, '%Y-%m')
    except ValueError as exc:
        raise ProjectExceptionError('reporting_period must use YYYY-MM format.', 422) from exc
    return value


def _serialize_report(report):
    requirement = report.project_requirement
    return {
        'id': report.id,
        'project_id': report.project_id,
        'project_requirement_id': report.project_requirement_id,
        'workflow_status': requirement.workflow_status if requirement else None,
        'workflow_return_reason': requirement.workflow_return_reason if requirement else None,
        'reporting_period': report.reporting_period,
        'exception_category': report.exception_category,
        'description': report.description,
        'created_by': report.created_by,
        'created_at': report.created_at.isoformat() if report.created_at else None,
        'updated_at': report.updated_at.isoformat() if report.updated_at else None,
    }
