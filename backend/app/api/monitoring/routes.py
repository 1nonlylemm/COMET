from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.monitoring.schemas import validate_inspection_payload
from app.services import monitoring_service, object_storage_service
from app.utils.auth import admin_or_staff_or_field_required, admin_or_staff_required
from app.utils.response import error_response, success_response, validation_error
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg

from . import monitoring_bp


@monitoring_bp.route('/inspections', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_inspections():
    try:
        result = monitoring_service.list_inspections(
            project_id=request.args.get('project_id', type=int),
            status=request.args.get('status'),
            monitoring_type=request.args.get('monitoring_type'),
            transmittal_status=request.args.get('transmittal_status'),
            monthly_cycle_tag=request.args.get('monthly_cycle_tag'),
            search=request.args.get('search'),
            page=request.args.get('page', 1, type=int),
            per_page=request.args.get('per_page', 20, type=int),
            fiscal_year=parse_fiscal_year_arg(request.args),
            user_id=get_jwt_identity(),
        )
        return success_response(data=result['items'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/workbench', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def monitoring_workbench():
    try:
        return success_response(data=monitoring_service.get_monitoring_workbench(
            user_id=get_jwt_identity(),
            fiscal_year=parse_fiscal_year_arg(request.args),
        ))
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/qaar/catalog', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def qaar_catalog():
    return success_response(data=monitoring_service.get_qaar_catalog())


@monitoring_bp.route('/qaar/item-catalog', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def qaar_item_catalog():
    return success_response(data=monitoring_service.list_qaar_item_catalog(
        category=request.args.get('category'),
        search=request.args.get('search') or request.args.get('q'),
        limit=request.args.get('limit', 75, type=int),
    ))


@monitoring_bp.route('/qaar/finding-catalog', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def qaar_finding_catalog():
    return success_response(data=monitoring_service.list_qaar_finding_catalog(
        item_code=request.args.get('item_code'),
        search=request.args.get('search') or request.args.get('q'),
        limit=request.args.get('limit', 75, type=int),
    ))


@monitoring_bp.route('/projects/<int:project_id>/profile', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_project_monitoring_profile(project_id):
    data = request.get_json() or {}
    try:
        profile = monitoring_service.update_project_monitoring_profile(
            project_id,
            data,
            user_id=get_jwt_identity(),
        )
        return success_response(data=profile, message='Monitoring profile updated successfully')
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/subaybayan-verifications', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_subaybayan_verifications():
    try:
        return success_response(data=monitoring_service.list_subaybayan_verifications(
            project_id=request.args.get('project_id', type=int),
            cycle_month=request.args.get('cycle_month'),
            user_id=get_jwt_identity(),
        ))
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/subaybayan-verifications', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def upsert_subaybayan_verification():
    data = request.get_json() or {}
    try:
        verification = monitoring_service.upsert_subaybayan_verification(data, user_id=get_jwt_identity())
        return success_response(
            data=monitoring_service._serialize_subaybayan_verification(verification),
            message='SubayBayan verification saved successfully',
            status_code=201,
        )
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/management-actions', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_management_actions():
    try:
        return success_response(data=monitoring_service.list_management_actions(
            project_id=request.args.get('project_id', type=int),
            cycle_month=request.args.get('cycle_month'),
            user_id=get_jwt_identity(),
        ))
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/management-actions', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def upsert_management_action():
    data = request.get_json() or {}
    try:
        action = monitoring_service.upsert_management_action(data, user_id=get_jwt_identity())
        return success_response(
            data=monitoring_service._serialize_management_action(action),
            message='Management Action record saved successfully',
            status_code=201,
        )
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/inspections/<int:inspection_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_inspection(inspection_id):
    try:
        inspection = monitoring_service.get_inspection(inspection_id, user_id=get_jwt_identity())
        return success_response(data=monitoring_service._serialize_inspection(inspection))
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/inspections', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def create_inspection():
    data = request.get_json() or {}
    errors = validate_inspection_payload(data)
    if errors:
        return validation_error(errors)

    try:
        inspection = monitoring_service.create_inspection(data, user_id=get_jwt_identity())
        return success_response(
            data=monitoring_service._serialize_inspection(inspection),
            message='Inspection recorded successfully',
            status_code=201,
        )
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/inspections/<int:inspection_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_inspection(inspection_id):
    data = request.get_json() or {}
    errors = validate_inspection_payload(data, partial=True)
    if errors:
        return validation_error(errors)

    try:
        inspection = monitoring_service.update_inspection(inspection_id, data, user_id=get_jwt_identity())
        return success_response(
            data=monitoring_service._serialize_inspection(inspection),
            message='Inspection updated successfully',
        )
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/inspections/<int:inspection_id>/outputs', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def generate_inspection_outputs(inspection_id):
    data = request.get_json() or {}
    try:
        outputs = monitoring_service.generate_qaar_outputs(
            inspection_id,
            output_types=data.get('output_types'),
            user_id=get_jwt_identity(),
        )
        return success_response(data=outputs, message='QAAR outputs generated successfully', status_code=201)
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@monitoring_bp.route('/outputs/<int:output_id>/download', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def download_generated_output(output_id):
    try:
        output, stored_object = monitoring_service.get_generated_output_download(
            output_id,
            user_id=get_jwt_identity(),
        )
        return object_storage_service.download_response(
            stored_object,
            download_name=stored_object.original_filename or f'{output.title}.pdf',
            content_type=stored_object.content_type or 'application/pdf',
        )
    except monitoring_service.MonitoringError as exc:
        return error_response(exc.message, status_code=exc.status_code)
    except object_storage_service.ObjectStorageError as exc:
        return error_response(exc.message, status_code=exc.status_code)
