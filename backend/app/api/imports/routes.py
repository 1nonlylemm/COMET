from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.imports.schemas import validate_template_payload
from app.services import import_service
from app.utils.auth import admin_required
from app.utils.response import error_response, success_response, validation_error
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg

from . import imports_bp


def _optional_json_bool(data, key):
    if key not in data or data.get(key) is None:
        return False
    value = data.get(key)
    if isinstance(value, bool):
        return value
    raise ValueError(f'{key} must be a boolean value.')


@imports_bp.route('/workbooks', methods=['POST'])
@jwt_required()
@admin_required
def upload_workbook():
    program_id = request.form.get('program_id', type=int)
    program_cycle_id = request.form.get('program_cycle_id', type=int)
    import_template_id = request.form.get('import_template_id', type=int)
    if not program_id:
        return validation_error({'program_id': 'Program is required'})

    try:
        batch = import_service.upload_workbook(
            program_id=program_id,
            program_cycle_id=program_cycle_id,
            import_template_id=import_template_id,
            upload=request.files.get('file'),
            user_id=get_jwt_identity(),
        )
        return success_response(data=batch, message='Workbook profiled successfully', status_code=201)
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/workbooks', methods=['GET'])
@jwt_required()
@admin_required
def list_workbooks():
    try:
        result = import_service.list_import_batches(
            program_id=request.args.get('program_id', type=int),
            program_cycle_id=request.args.get('program_cycle_id', type=int),
            fiscal_year=parse_fiscal_year_arg(request.args),
            page=request.args.get('page', 1, type=int),
            per_page=request.args.get('per_page', 20, type=int),
        )
        return success_response(data=result['items'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/workbooks/<int:batch_id>', methods=['GET'])
@jwt_required()
@admin_required
def get_workbook(batch_id):
    try:
        return success_response(data=import_service.get_import_batch(batch_id))
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/workbooks/<int:batch_id>/map', methods=['POST'])
@jwt_required()
@admin_required
def map_workbook(batch_id):
    try:
        mapping = import_service.map_workbook(
            batch_id,
            overrides=request.get_json(silent=True) or {},
            user_id=get_jwt_identity(),
        )
        return success_response(data=mapping, message='Workbook mapping prepared')
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/workbooks/<int:batch_id>/schema-diff', methods=['GET'])
@jwt_required()
@admin_required
def workbook_schema_diff(batch_id):
    template_id = request.args.get('template_id', type=int)
    if not template_id:
        return validation_error({'template_id': 'Template ID is required'})
    try:
        return success_response(data=import_service.schema_diff(batch_id, template_id))
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/workbooks/<int:batch_id>/mapping-workshop', methods=['GET'])
@jwt_required()
@admin_required
def workbook_mapping_workshop(batch_id):
    try:
        return success_response(data=import_service.get_mapping_workshop(batch_id))
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/workbooks/<int:batch_id>/mapping-decisions', methods=['PUT'])
@jwt_required()
@admin_required
def save_workbook_mapping_decisions(batch_id):
    data = request.get_json(silent=True) or {}
    try:
        result = import_service.save_mapping_decisions(
            batch_id,
            data.get('decisions') or [],
            user_id=get_jwt_identity(),
        )
        return success_response(data=result, message='Workbook mapping decisions saved')
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/mapping-history', methods=['GET'])
@jwt_required()
@admin_required
def mapping_history():
    try:
        return success_response(data=import_service.list_mapping_history(
            program_id=request.args.get('program_id', type=int),
            program_cycle_id=request.args.get('program_cycle_id', type=int),
            source_header=request.args.get('source_header'),
            limit=request.args.get('limit', 100, type=int),
        ))
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/workbooks/<int:batch_id>/preview', methods=['POST'])
@jwt_required()
@admin_required
def preview_workbook(batch_id):
    try:
        preview = import_service.preview_workbook(
            batch_id,
            mapping_payload=request.get_json(silent=True) or None,
            user_id=get_jwt_identity(),
        )
        return success_response(data=preview, message='Workbook import preview prepared')
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/workbooks/<int:batch_id>/commit', methods=['POST'])
@jwt_required()
@admin_required
def commit_workbook(batch_id):
    data = request.get_json(silent=True) or {}
    try:
        confirm_similar_requirements = _optional_json_bool(data, 'confirm_similar_requirements')
    except ValueError as exc:
        return validation_error({'confirm_similar_requirements': str(exc)})
    try:
        result = import_service.commit_workbook(
            batch_id,
            user_id=get_jwt_identity(),
            confirm_similar_requirements=confirm_similar_requirements,
        )
        return success_response(data=result, message='Workbook import committed')
    except import_service.ImportError as e:
        return error_response(e.message, errors=getattr(e, 'errors', None), status_code=e.status_code)


@imports_bp.route('/templates', methods=['GET'])
@jwt_required()
@admin_required
def list_templates():
    try:
        templates = import_service.list_import_templates(
            program_id=request.args.get('program_id', type=int),
            program_cycle_id=request.args.get('program_cycle_id', type=int),
            fiscal_year=parse_fiscal_year_arg(request.args),
        )
        return success_response(data=templates)
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/templates', methods=['POST'])
@jwt_required()
@admin_required
def create_template():
    data = request.get_json() or {}
    errors = validate_template_payload(data, require_program=True)
    if errors:
        return validation_error(errors)
    try:
        template = import_service.create_import_template(data, user_id=get_jwt_identity())
        return success_response(data=template, message='Import template created', status_code=201)
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/templates/<int:template_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_template(template_id):
    data = request.get_json() or {}
    errors = validate_template_payload(data, require_program=False)
    if errors:
        return validation_error(errors)
    try:
        template = import_service.update_import_template(template_id, data, user_id=get_jwt_identity())
        return success_response(data=template, message='Import template updated')
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)


@imports_bp.route('/templates/<int:template_id>/clone', methods=['POST'])
@jwt_required()
@admin_required
def clone_template(template_id):
    data = request.get_json() or {}
    errors = validate_template_payload(data, require_program=False)
    if errors:
        return validation_error(errors)
    try:
        template = import_service.clone_import_template(template_id, data, user_id=get_jwt_identity())
        return success_response(data=template, message='Import template cloned', status_code=201)
    except import_service.ImportError as e:
        return error_response(e.message, status_code=e.status_code)
