from flask import request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.governance.schemas import validate_guideline_payload
from app.services import governance_service, object_storage_service
from app.utils.auth import admin_or_staff_or_field_required, admin_or_staff_required
from app.utils.response import error_response, success_response, validation_error
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg

from . import governance_bp


def _parse_optional_bool_arg(name):
    value = request.args.get(name)
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized == '':
        return None
    if normalized in {'true', '1', 'yes', 'on'}:
        return True
    if normalized in {'false', '0', 'no', 'off'}:
        return False
    raise ValueError(f'{name} must be true or false.')


@governance_bp.route('/archive', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_archive_records():
    try:
        result = governance_service.list_archive_records(
            search=request.args.get('search'),
            lgu_id=request.args.get('lgu_id', type=int),
            program_id=request.args.get('program_id', type=int),
            fiscal_year=parse_fiscal_year_arg(request.args),
            page=request.args.get('page', 1, type=int),
            per_page=request.args.get('per_page', 20, type=int),
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
    except governance_service.GovernanceError as exc:
        return error_response(exc.message, errors=getattr(exc, 'errors', None), status_code=exc.status_code)


@governance_bp.route('/communications', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_communications():
    try:
        result = governance_service.list_communications(
            search=request.args.get('search'),
            lgu_id=request.args.get('lgu_id', type=int),
            project_id=request.args.get('project_id', type=int),
            communication_type=request.args.get('communication_type'),
            channel=request.args.get('channel'),
            fiscal_year=parse_fiscal_year_arg(request.args),
            page=request.args.get('page', 1, type=int),
            per_page=request.args.get('per_page', 20, type=int),
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
    except governance_service.GovernanceError as exc:
        return error_response(exc.message, errors=getattr(exc, 'errors', None), status_code=exc.status_code)


@governance_bp.route('/archive/<int:project_requirement_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_archive_record(project_requirement_id):
    try:
        return success_response(
            data=governance_service.get_archive_record_detail(
                project_requirement_id,
                user_id=get_jwt_identity(),
            )
        )
    except governance_service.GovernanceError as exc:
        return error_response(exc.message, errors=getattr(exc, 'errors', None), status_code=exc.status_code)


@governance_bp.route('/guidelines', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_guidelines():
    try:
        is_current = _parse_optional_bool_arg('is_current')
        result = governance_service.list_guidelines(
            search=request.args.get('search'),
            program_id=request.args.get('program_id', type=int),
            guideline_type=request.args.get('guideline_type'),
            is_current=is_current,
            page=request.args.get('page', 1, type=int),
            per_page=request.args.get('per_page', 20, type=int),
        )
        return success_response(data=result['items'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except ValueError as exc:
        return validation_error({'is_current': str(exc)})
    except governance_service.GovernanceError as exc:
        return error_response(exc.message, errors=getattr(exc, 'errors', None), status_code=exc.status_code)


@governance_bp.route('/guidelines', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def create_guideline():
    data = request.get_json() if request.is_json else request.form.to_dict()
    data = data or {}
    errors = validate_guideline_payload(data)
    if errors:
        return validation_error(errors)

    try:
        guideline = governance_service.create_guideline(
            data,
            user_id=get_jwt_identity(),
            upload=request.files.get('file'),
        )
        return success_response(
            data=governance_service._serialize_guideline(guideline),
            message='Guideline saved successfully',
            status_code=201,
        )
    except governance_service.GovernanceError as exc:
        return error_response(exc.message, errors=getattr(exc, 'errors', None), status_code=exc.status_code)


@governance_bp.route('/guidelines/<int:guideline_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_guideline(guideline_id):
    data = request.get_json() if request.is_json else request.form.to_dict()
    data = data or {}
    errors = validate_guideline_payload(data, partial=True)
    if errors:
        return validation_error(errors)

    try:
        guideline = governance_service.update_guideline(
            guideline_id,
            data,
            user_id=get_jwt_identity(),
            upload=request.files.get('file'),
        )
        return success_response(
            data=governance_service._serialize_guideline(guideline),
            message='Guideline updated successfully',
        )
    except governance_service.GovernanceError as exc:
        return error_response(exc.message, errors=getattr(exc, 'errors', None), status_code=exc.status_code)


@governance_bp.route('/guidelines/<int:guideline_id>/download', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def download_guideline(guideline_id):
    try:
        download = governance_service.get_guideline_download(guideline_id)
        guideline = download['guideline']
        if download.get('stored_object') is not None:
            return object_storage_service.download_response(
                download['stored_object'],
                download_name=guideline.file_name,
                content_type=download['stored_object'].content_type or 'application/octet-stream',
            )
        path = download['path']
        return send_file(
            path,
            as_attachment=True,
            download_name=guideline.file_name or path.name,
            mimetype='application/octet-stream',
        )
    except governance_service.GovernanceError as exc:
        return error_response(exc.message, errors=getattr(exc, 'errors', None), status_code=exc.status_code)
    except object_storage_service.ObjectStorageError as exc:
        return error_response(exc.message, status_code=exc.status_code)
