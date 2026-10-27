from flask import Response, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from sqlalchemy.exc import IntegrityError
from app.models import GeneratedReport
from app.models.storage import StoredObject
from app.utils.auth import admin_or_staff_or_field_required, admin_or_staff_required, role_required
from app.services import access_service, document_compliance_service, document_intelligence_service, object_storage_service, project_service, settings_service, submission_service
from app.utils.response import (
    success_response, error_response, not_found_error, validation_error
)
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg
from app.api.projects.schemas import (
    validate_change_status_request_create, validate_change_status_request_review,
    validate_project_create, validate_project_update,
    validate_phase_transition, validate_project_requirement_update,
    validate_project_requirement_applicability_update,
    validate_submission_create,
)

from . import projects_bp


def _project_error_response(error):
    return error_response(
        error.message,
        errors=getattr(error, 'errors', None),
        status_code=error.status_code,
    )


def _optional_json_boolean(data, key):
    if not isinstance(data, dict):
        raise document_compliance_service.DocumentComplianceError(
            'Invalid request payload.',
            422,
            {'body': 'JSON payload must be an object.'},
        )
    if key not in data or data.get(key) is None:
        return False
    value = data.get(key)
    if isinstance(value, bool):
        return value
    raise document_compliance_service.DocumentComplianceError(
        f'{key} must be a boolean value.',
        422,
        {key: 'Must be a boolean.'},
    )


# ── Project CRUD ──────────────────────────────────────────────────────────

@projects_bp.route('', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def create_project():
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_project_create(data)
    if errors:
        return validation_error(errors)

    try:
        user_id = get_jwt_identity()
        project = project_service.create_project(
            lgu_id=data['lgu_id'],
            program_id=data['program_id'],
            project_name=data['project_name'],
            fiscal_year=data['fiscal_year'],
            program_cycle_id=data.get('program_cycle_id'),
            source_project_code=data.get('source_project_code'),
            source_row_key=data.get('source_row_key'),
            source_sheet_name=data.get('source_sheet_name'),
            current_phase=data.get('current_phase', 'pre_implementation'),
            overall_status=data.get('overall_status', 'not_yet_started'),
            budget_amount=data.get('budget_amount'),
            target_start_date=data.get('target_start_date'),
            target_end_date=data.get('target_end_date'),
            project_kind=data.get('project_kind'),
            monitoring_applicability=data.get('monitoring_applicability'),
            qaar_category=data.get('qaar_category'),
            subaybayan_project_code=data.get('subaybayan_project_code'),
            subaybayan_url=data.get('subaybayan_url'),
            nadai_received_at=data.get('nadai_received_at'),
            subaybayan_enrolled_at=data.get('subaybayan_enrolled_at'),
            subaybayan_enrollment_status=data.get('subaybayan_enrollment_status'),
            notes=data.get('notes'),
            custom_fields=data.get('custom_fields'),
            user_id=user_id,
        )
        return success_response(
            data=project_service._serialize_project(project),
            message='Project created successfully',
            status_code=201,
        )
    except project_service.ProjectError as e:
        return _project_error_response(e)
    except IntegrityError as exc:
        db.session.rollback()
        if project_service._is_project_identity_conflict(exc):
            return _project_error_response(project_service._project_identity_error(data.get('source_project_code')))
        raise


@projects_bp.route('', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_projects():
    search = request.args.get('search')
    lgu_id = request.args.get('lgu_id', type=int)
    program_id = request.args.get('program_id', type=int)
    program_cycle_id = request.args.get('program_cycle_id', type=int)
    current_phase = request.args.get('current_phase')
    overall_status = request.args.get('overall_status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    try:
        fiscal_year = parse_fiscal_year_arg(request.args)
        result = project_service.list_projects(
            search=search, lgu_id=lgu_id, program_id=program_id,
            fiscal_year=fiscal_year, program_cycle_id=program_cycle_id,
            current_phase=current_phase,
            overall_status=overall_status, page=page, per_page=per_page,
            user_id=get_jwt_identity(),
        )
        return success_response(data=result['projects'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except project_service.ProjectError as e:
        return _project_error_response(e)


@projects_bp.route('/<int:project_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_project(project_id):
    try:
        data = project_service.get_project_detail(project_id, user_id=get_jwt_identity())
        return success_response(data=data)
    except project_service.ProjectError as e:
        return _project_error_response(e)


@projects_bp.route('/<int:project_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_project(project_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_project_update(data)
    if errors:
        return validation_error(errors)

    try:
        user_id = get_jwt_identity()
        project = project_service.update_project(project_id, data, user_id=user_id)
        return success_response(
            data=project_service._serialize_project(project),
            message='Project updated successfully',
        )
    except project_service.ProjectError as e:
        return _project_error_response(e)
    except IntegrityError as exc:
        db.session.rollback()
        if project_service._is_project_identity_conflict(exc):
            return _project_error_response(project_service._project_identity_error(data.get('source_project_code')))
        raise


# ── Phase Transitions ─────────────────────────────────────────────────────

@projects_bp.route('/<int:project_id>/transition', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def transition_phase(project_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_phase_transition(data)
    if errors:
        return validation_error(errors)

    try:
        user_id = get_jwt_identity()

        project, phase_log = project_service.transition_project_phase(
            project_id=project_id,
            to_phase=data['to_phase'],
            reason=data['reason'],
            user_id=user_id,
        )
        return success_response(
            data={
                'project': project_service._serialize_project(project),
                'phase_log': project_service._serialize_phase_log(phase_log),
            },
            message=f'Project transitioned to {data["to_phase"]} phase',
        )
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Project Requirements ──────────────────────────────────────────────────

@projects_bp.route('/<int:project_id>/requirements/init', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def initialize_requirements(project_id):
    try:
        user_id = get_jwt_identity()
        count = project_service.initialize_project_requirements(project_id, user_id=user_id)
        return success_response(
            data={'requirement_count': count},
            message=f'{count} requirements initialized from program matrix',
        )
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/<int:project_id>/requirements', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_project_requirements(project_id):
    status = request.args.get('status')
    requirement_type = request.args.get('requirement_type')
    is_mandatory = request.args.get('is_mandatory')
    applicability = request.args.get('applicability')
    if is_mandatory is not None:
        is_mandatory = is_mandatory.lower() == 'true'

    try:
        requirements = project_service.list_project_requirements(
            project_id=project_id,
            status=status,
            requirement_type=requirement_type,
            is_mandatory=is_mandatory,
            applicability=applicability,
            user_id=get_jwt_identity(),
        )
        return success_response(data=requirements)
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/<int:project_id>/activity', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_project_activity(project_id):
    try:
        data = project_service.get_project_activity(
            project_id,
            user_id=get_jwt_identity(),
            limit=request.args.get('limit', 100, type=int),
        )
        return success_response(data=data)
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/revision-report/templates', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def list_revision_report_templates():
    try:
        return success_response(data=settings_service.list_revision_report_templates())
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@projects_bp.route('/<int:project_id>/revision-report', methods=['GET', 'POST'])
@jwt_required()
@admin_or_staff_or_field_required
def download_project_revision_report(project_id):
    current_user_id = get_jwt_identity()
    try:
        access_service.ensure_project_access(project_id, current_user_id)
    except access_service.AccessError as exc:
        return error_response(exc.message, status_code=exc.status_code)

    payload = request.get_json(silent=True) if request.method == 'POST' else {}
    payload = payload or {}
    template_id = payload.get('template_id') or request.args.get('template_id')
    placeholder_overrides = payload.get('placeholder_overrides') or {}
    if request.method == 'GET':
        placeholder_overrides = {
            key.removeprefix('placeholder_'): value
            for key, value in request.args.items()
            if key.startswith('placeholder_')
        }
    if not isinstance(placeholder_overrides, dict):
        return validation_error({'placeholder_overrides': 'placeholder_overrides must be an object'})

    try:
        report = project_service.generate_revision_report(
            project_id,
            user_id=current_user_id,
            template_id=template_id,
            placeholder_overrides=placeholder_overrides,
        )
        response = Response(
            report['content'],
            mimetype=report['mimetype'],
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{report["file_name"]}"'
        return response
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/<int:project_id>/revision-report/preview', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def preview_project_revision_report(project_id):
    current_user_id = get_jwt_identity()
    try:
        access_service.ensure_project_access(project_id, current_user_id)
    except access_service.AccessError as exc:
        return error_response(exc.message, status_code=exc.status_code)

    payload = request.get_json(silent=True) or {}
    placeholder_overrides = payload.get('placeholder_overrides') or {}
    if not isinstance(placeholder_overrides, dict):
        return validation_error({'placeholder_overrides': 'placeholder_overrides must be an object'})

    try:
        preview = project_service.preview_revision_report(
            project_id,
            user_id=current_user_id,
            template_id=payload.get('template_id'),
            placeholder_overrides=placeholder_overrides,
        )
        return success_response(data=preview)
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>/correction-report', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def download_requirement_correction_report(requirement_id):
    current_user_id = get_jwt_identity()
    try:
        requirement = access_service.ensure_project_requirement_access(requirement_id, current_user_id)
    except access_service.AccessError as exc:
        return error_response(exc.message, status_code=exc.status_code)

    report_id = request.args.get('report_id', type=int)
    transition_id = request.args.get('transition_id', type=int)

    try:
        # 1. If explicit report_id given, check GeneratedReport & StoredObject
        if report_id:
            report = db.session.get(GeneratedReport, report_id)
            if not report or (report.parameters or {}).get('project_requirement_id') != requirement.id:
                return error_response('Correction report not found.', status_code=404)
            stored_object_id = (report.parameters or {}).get('stored_object_id')
            if not stored_object_id:
                return error_response('Correction report file is missing.', status_code=404)
            stored_obj = db.session.get(StoredObject, stored_object_id)
            if not stored_obj:
                return error_response('Associated correction report object not found.', status_code=404)
            return object_storage_service.download_response(
                stored_obj,
                download_name=report.file_name or f'requirement-{requirement.id}-correction-report.docx',
                content_type=project_service.DOCX_MIME_TYPE,
            )

        # 2. If explicit transition_id given, check GeneratedReport matching that transition
        if transition_id:
            candidate_reports = (
                GeneratedReport.query
                .filter(
                    GeneratedReport.report_type == 'custom',
                )
                .all()
            )
            matched = [
                r for r in candidate_reports
                if (r.parameters or {}).get('workflow_transition_id') == transition_id
                and (r.parameters or {}).get('project_requirement_id') == requirement.id
            ]
            if matched:
                target_report = matched[0]
                stored_object_id = (target_report.parameters or {}).get('stored_object_id')
                if not stored_object_id:
                    return error_response('Correction report file is missing.', status_code=404)
                stored_obj = db.session.get(StoredObject, stored_object_id)
                if not stored_obj:
                    return error_response('Associated correction report object not found.', status_code=404)
                return object_storage_service.download_response(
                    stored_obj,
                    download_name=target_report.file_name or f'requirement-{requirement.id}-correction-report.docx',
                    content_type=project_service.DOCX_MIME_TYPE,
                )

        # 3. If neither report_id nor transition_id was passed, resolve active return report
        if requirement.workflow_status != 'returned_for_revision':
            return error_response(
                'No active return for revision on this requirement. Please specify report_id or transition_id to access historical correction reports.',
                status_code=404,
            )

        # Check requirement.custom_fields latest_revision for active return
        latest_rev = (requirement.custom_fields or {}).get('latest_revision') or {}
        stored_object_id = latest_rev.get('stored_object_id')
        if stored_object_id:
            stored_obj = db.session.get(StoredObject, stored_object_id)
            if stored_obj:
                filename = latest_rev.get('report_file_name') or f'requirement-{requirement.id}-correction-report.docx'
                return object_storage_service.download_response(
                    stored_obj,
                    download_name=filename,
                    content_type=project_service.DOCX_MIME_TYPE,
                )

        # Generate on-demand if not pre-persisted
        report = project_service.generate_requirement_correction_report(
            requirement.id,
            user_id=current_user_id,
            transition_id=transition_id,
        )
        response = Response(
            report['content'],
            mimetype=report['mimetype'],
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{report["file_name"]}"'
        return response
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_project_requirement(requirement_id):
    try:
        user_id = get_jwt_identity()
        pr = project_service.get_project_requirement(requirement_id, user_id=user_id)
        user_role = access_service.get_user_role(user_id)
        return success_response(data=project_service._serialize_project_requirement(pr, user_role=user_role))
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/intake/queue', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def intake_queue():
    search = request.args.get('search')
    status = request.args.get('status')
    phase_name = request.args.get('phase_name')
    project_id = request.args.get('project_id', type=int)
    lgu_id = request.args.get('lgu_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    applicability = request.args.get('applicability')

    try:
        fiscal_year = parse_fiscal_year_arg(request.args)
        result = submission_service.list_intake_queue(
            search=search,
            status=status,
            phase_name=phase_name,
            project_id=project_id,
            lgu_id=lgu_id,
            page=page,
            per_page=per_page,
            fiscal_year=fiscal_year,
            user_id=get_jwt_identity(),
            applicability=applicability,
        )
        return success_response(data=result['items'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
            'summary': result.get('summary'),
        })
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except submission_service.SubmissionError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>/submissions', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_requirement_submissions(requirement_id):
    try:
        submissions = submission_service.list_requirement_submissions(
            requirement_id,
            user_id=get_jwt_identity(),
        )
        return success_response(data=submissions)
    except submission_service.SubmissionError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>/submissions', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def create_requirement_submission(requirement_id):
    data = request.form.to_dict()
    user_id = get_jwt_identity()

    if not data.get('source'):
        role = access_service.get_user_role(user_id)
        data['source'] = 'field_upload' if role == 'field_officer' else 'dms_ingestion'

    errors = validate_submission_create(data)
    if errors:
        return validation_error(errors)

    try:
        submission = submission_service.create_submission(
            requirement_id=requirement_id,
            source=data.get('source', 'dms_ingestion'),
            description=data.get('description'),
            upload=request.files.get('file'),
            user_id=user_id,
        )
        return success_response(
            data=submission,
            message='Documentary intake recorded successfully',
            status_code=201,
        )
    except submission_service.SubmissionError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/submission-scan/preview', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def preview_submission_scan():
    raw_project_id = request.form.get('project_id')
    project_id = request.form.get('project_id', type=int)
    if raw_project_id and project_id is None:
        return validation_error({'project_id': ['Project ID must be an integer.']})
    raw_requirement_id = request.form.get('project_requirement_id')
    project_requirement_id = request.form.get('project_requirement_id', type=int)
    if raw_requirement_id and project_requirement_id is None:
        return validation_error({'project_requirement_id': ['Requirement ID must be an integer.']})
    try:
        result = document_intelligence_service.preview_document_mapping(
            project_id=project_id,
            upload=request.files.get('file'),
            user_id=get_jwt_identity(),
            project_requirement_id=project_requirement_id,
        )
        return success_response(data=result)
    except document_intelligence_service.DocumentIntelligenceError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/submission-scan/jobs', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def start_submission_scan_job():
    from app.services import matcher_preview_jobs
    values = {}
    for name in ('project_id', 'project_requirement_id'):
        raw = request.form.get(name)
        value = request.form.get(name, type=int)
        if raw and value is None:
            return validation_error({name: ['Must be an integer.']})
        values[name] = value
    try:
        result = matcher_preview_jobs.start(request.files.get('file'), get_jwt_identity(),
            values['project_id'], values['project_requirement_id'])
        return success_response(data=result, status_code=202)
    except document_intelligence_service.DocumentIntelligenceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@projects_bp.route('/submission-scan/jobs/<job_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_submission_scan_job(job_id):
    from app.services import matcher_preview_jobs
    try:
        return success_response(data=matcher_preview_jobs.get(job_id, get_jwt_identity()))
    except document_intelligence_service.DocumentIntelligenceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@projects_bp.route('/submissions/<int:submission_id>/scan', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def scan_submission_document(submission_id):
    try:
        result = document_intelligence_service.scan_submission(
            submission_id=submission_id,
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=result,
            message='Document intelligence scan completed.',
            status_code=201,
        )
    except document_intelligence_service.DocumentIntelligenceError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/submissions/<int:submission_id>/refresh-destination', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def refresh_submission_destination(submission_id):
    try:
        result = document_intelligence_service.refresh_submission_destination_check(
            submission_id=submission_id,
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=result,
            message='Document destination check refreshed.',
            status_code=200,
        )
    except document_intelligence_service.DocumentIntelligenceError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/submissions/<int:submission_id>/scan-results', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def list_submission_scan_results(submission_id):
    try:
        results = document_intelligence_service.list_submission_scan_results(
            submission_id=submission_id,
            user_id=get_jwt_identity(),
        )
        return success_response(data=results)
    except document_intelligence_service.DocumentIntelligenceError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/submissions/<int:submission_id>/compliance-check', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def run_submission_compliance_check(submission_id):
    data = request.get_json(silent=True) or {}
    try:
        use_prior_year_reference = _optional_json_boolean(data, 'use_prior_year_reference')
        result = document_compliance_service.run_submission_check(
            submission_id,
            user_id=get_jwt_identity(),
            use_prior_year_reference=use_prior_year_reference,
        )
        return success_response(
            data=result,
            message='Documentary compliance check completed.',
            status_code=201,
        )
    except document_compliance_service.DocumentComplianceError as e:
        return error_response(e.message, errors=e.errors or None, status_code=e.status_code)


@projects_bp.route('/submissions/<int:submission_id>/compliance-results', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def list_submission_compliance_results(submission_id):
    try:
        results = document_compliance_service.list_submission_results(
            submission_id,
            user_id=get_jwt_identity(),
        )
        return success_response(data=results)
    except document_compliance_service.DocumentComplianceError as e:
        return error_response(e.message, errors=e.errors or None, status_code=e.status_code)


@projects_bp.route('/compliance-results/<int:result_id>/review', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def review_document_compliance_result(result_id):
    data = request.get_json(silent=True) or {}
    try:
        result = document_compliance_service.review_compliance_result(
            result_id,
            user_id=get_jwt_identity(),
            decision=data.get('decision'),
            reason_codes=data.get('reason_codes'),
            review_notes=data.get('review_notes') or data.get('notes'),
            finding_reviews=data.get('finding_reviews'),
        )
        return success_response(data=result, message='Documentary compliance review recorded.')
    except document_compliance_service.DocumentComplianceError as e:
        return error_response(e.message, errors=e.errors or None, status_code=e.status_code)


@projects_bp.route('/submission-scans/<int:scan_id>/review', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def review_submission_scan(scan_id):
    data = request.get_json() or {}
    try:
        result = document_intelligence_service.review_scan_result(
            scan_id=scan_id,
            user_id=get_jwt_identity(),
            decision=data.get('decision'),
            target_project_requirement_id=data.get('target_project_requirement_id'),
            review_notes=data.get('review_notes'),
        )
        return success_response(data=result, message='Document intelligence review recorded.')
    except document_intelligence_service.DocumentIntelligenceError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/files/<int:file_id>/download', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def download_submission_file(file_id):
    try:
        document_file = submission_service.get_document_file(file_id, user_id=get_jwt_identity())
        if document_file.stored_object is not None:
            return object_storage_service.download_response(
                document_file.stored_object,
                download_name=document_file.file_name,
                content_type=document_file.mime_type or 'application/octet-stream',
            )
        file_path = submission_service.resolve_document_file_path(document_file)
        return send_file(
            file_path,
            as_attachment=True,
            download_name=document_file.file_name,
            mimetype=document_file.mime_type or 'application/octet-stream',
        )
    except submission_service.SubmissionError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_project_requirement(requirement_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_project_requirement_update(data)
    if errors:
        return validation_error(errors)

    try:
        user_id = get_jwt_identity()
        pr = project_service.update_project_requirement(requirement_id, data, user_id=user_id)
        return success_response(
            data=project_service._serialize_project_requirement(pr),
            message='Project requirement updated successfully',
        )
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>/applicability', methods=['PUT', 'PATCH'])
@projects_bp.route('/<int:project_id>/requirements/<int:requirement_id>/applicability', methods=['PUT', 'PATCH'])
@jwt_required()
@admin_or_staff_required
def update_project_requirement_applicability(requirement_id, project_id=None):
    data = request.get_json(silent=True)
    if data is None:
        return error_response('Request body must be a JSON object', status_code=400)

    errors = validate_project_requirement_applicability_update(data)
    if errors:
        return validation_error(errors)

    try:
        user_id = get_jwt_identity()
        pr = project_service.update_project_requirement_applicability(
            requirement_id=requirement_id,
            applicability=data.get('applicability'),
            reason=data.get('reason') or data.get('applicability_reason'),
            project_id=project_id or data.get('project_id'),
            user_id=user_id,
        )
        return success_response(
            data=project_service._serialize_project_requirement(pr),
            message=f"Requirement applicability updated to '{pr.applicability}'.",
        )
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>/return-for-revision', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def return_project_requirement_for_revision(requirement_id):
    data = request.get_json(silent=True) or {}
    try:
        pr = project_service.return_requirement_for_revision(
            requirement_id,
            review_notes=data.get('review_notes') or data.get('notes'),
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=project_service._serialize_project_requirement(pr),
            message='Requirement returned for revision.',
        )
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/handoff/queue', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def handoff_queue():
    search = request.args.get('search')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    try:
        fiscal_year = parse_fiscal_year_arg(request.args)
        result = submission_service.list_handoff_queue(
            search=search,
            page=page,
            per_page=per_page,
            fiscal_year=fiscal_year,
            user_id=get_jwt_identity(),
        )
        return success_response(data=result['items'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except submission_service.SubmissionError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>/handoff', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def push_requirement_handoff(requirement_id):
    try:
        push_record = submission_service.push_requirement_to_drive(
            requirement_id=requirement_id,
            user_id=get_jwt_identity(),
        )
        already_handed_off = bool(push_record.get('already_handed_off'))
        return success_response(
            data=push_record,
            message='Requirement was already handed off to Google Drive'
            if already_handed_off
            else 'Requirement handed off to Google Drive successfully',
            status_code=200 if already_handed_off else 201,
        )
    except submission_service.SubmissionError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>/change-requests', methods=['POST'])
@jwt_required()
@role_required('admin', 'staff')
def create_change_status_request(requirement_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_change_status_request_create(data)
    if errors:
        return validation_error(errors)

    user_id = get_jwt_identity()
    user_role = access_service.get_user_role(user_id)
    auto_approve = (user_role == 'admin' and data.get('auto_approve', True))

    try:
        change_request = project_service.create_change_status_request(
            requirement_id=requirement_id,
            requested_status=data['requested_status'],
            justification=data['justification'],
            user_id=user_id,
            auto_approve=auto_approve,
        )
        return success_response(
            data=project_service._serialize_change_status_request(change_request),
            message='Status change request approved and requirement reopened.' if auto_approve else 'Status change request submitted successfully',
            status_code=201,
        )
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/change-requests', methods=['GET'])
@jwt_required()
@role_required('admin', 'staff')
def list_change_status_requests():
    status = request.args.get('status')
    project_id = request.args.get('project_id', type=int)

    try:
        fiscal_year = parse_fiscal_year_arg(request.args)
        requests = project_service.list_change_status_requests(
            status=status,
            project_id=project_id,
            fiscal_year=fiscal_year,
            user_id=get_jwt_identity(),
        )
        return success_response(data=requests)
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/change-requests/<int:request_id>/review', methods=['POST'])
@jwt_required()
@role_required('admin')
def review_change_status_request(request_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_change_status_request_review(data)
    if errors:
        return validation_error(errors)

    try:
        change_request = project_service.review_change_status_request(
            request_id=request_id,
            decision=data['decision'],
            review_notes=data.get('review_notes'),
            reviewer_id=get_jwt_identity(),
        )
        return success_response(
            data=project_service._serialize_change_status_request(change_request),
            message='Change status request reviewed successfully',
        )
    except project_service.ProjectError as e:
        return error_response(e.message, status_code=e.status_code)

@projects_bp.route('/submissions/<int:submission_id>/reassign', methods=['PATCH'])
@jwt_required()
def reassign_submission(submission_id):
    data = request.json or {}
    target_project_requirement_id = data.get('target_project_requirement_id')
    if not target_project_requirement_id:
        return error_response('target_project_requirement_id is required', 422)
    
    document_intelligence_service.reassign_submission_mapping(
        submission_id=submission_id,
        user_id=current_user.id,
        target_project_requirement_id=target_project_requirement_id
    )
    return success_response(message='Submission reassigned successfully.')
