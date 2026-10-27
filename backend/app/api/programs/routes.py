from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.utils.auth import admin_required
from app.services import program_service
from app.utils.response import (
    success_response, error_response, not_found_error, validation_error
)
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg
from app.api.programs.schemas import (
    validate_program_create, validate_program_update,
    validate_cycle_create, validate_cycle_update, validate_cycle_clone,
    validate_phase_create, validate_phase_update,
    validate_requirement_create, validate_requirement_update,
)

from . import programs_bp


def _parse_bool_arg(name):
    value = request.args.get(name)
    if value is None:
        return None, None

    normalized = value.strip().lower()
    if normalized == 'true':
        return True, None
    if normalized == 'false':
        return False, None
    return None, {name: f'{name} must be true or false'}


def _parse_positive_int_arg(name):
    value = request.args.get(name)
    if value in (None, ''):
        return None, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, {name: f'{name} must be an integer'}
    if parsed < 1:
        return None, {name: f'{name} must be a positive integer'}
    return parsed, None


# ── Program Endpoints ─────────────────────────────────────────────────────

@programs_bp.route('', methods=['POST'])
@jwt_required()
@admin_required
def create_program():
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_program_create(data)
    if errors:
        return validation_error(errors)

    try:
        user_id = get_jwt_identity()
        program = program_service.create_program(
            name=data['name'],
            code=data['code'],
            program_type=data['program_type'],
            description=data.get('description'),
            funding_agency=data.get('funding_agency'),
            project_custom_field_schema=data.get('project_custom_field_schema'),
            user_id=user_id,
        )
        return success_response(
            data=program_service._serialize_program(program),
            message='Program created successfully',
            status_code=201,
        )
    except program_service.ProgramError as e:
        return error_response(e.message, errors=getattr(e, 'errors', None), status_code=e.status_code)


@programs_bp.route('', methods=['GET'])
@jwt_required()
def list_programs():
    search = request.args.get('search')
    program_type = request.args.get('program_type')
    is_active, bool_errors = _parse_bool_arg('is_active')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    if bool_errors:
        return validation_error(bool_errors)

    try:
        fiscal_year = parse_fiscal_year_arg(request.args)
        result = program_service.list_programs(
            search=search, program_type=program_type,
            is_active=is_active, fiscal_year=fiscal_year, page=page, per_page=per_page,
        )
        return success_response(data=result['programs'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/fiscal-years', methods=['GET'])
@jwt_required()
def list_fiscal_years():
    return success_response(data=program_service.get_available_fiscal_years())


@programs_bp.route('/<int:program_id>', methods=['GET'])
@jwt_required()
def get_program(program_id):
    try:
        program = program_service.get_program(program_id)
        return success_response(data=program_service._serialize_program(program))
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/<int:program_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_program(program_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_program_update(data)
    if errors:
        return validation_error(errors)

    try:
        program = program_service.update_program(program_id, data, user_id=get_jwt_identity())
        return success_response(
            data=program_service._serialize_program(program),
            message='Program updated successfully',
        )
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/<int:program_id>/toggle-active', methods=['POST'])
@jwt_required()
@admin_required
def toggle_program_active(program_id):
    try:
        program = program_service.toggle_program_active(program_id, user_id=get_jwt_identity())
        status = 'activated' if program.is_active else 'deactivated'
        return success_response(
            data=program_service._serialize_program(program),
            message=f'Program {status} successfully',
        )
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Requirement Matrix ─────────────────────────────────────────────────────

@programs_bp.route('/<int:program_id>/matrix', methods=['GET'])
@jwt_required()
def get_program_matrix(program_id):
    program_cycle_id, id_errors = _parse_positive_int_arg('program_cycle_id')
    if id_errors:
        return validation_error(id_errors)
    baseline_only, bool_errors = _parse_bool_arg('baseline_only')
    if bool_errors:
        return validation_error(bool_errors)

    try:
        fiscal_year = parse_fiscal_year_arg(request.args)
        matrix = program_service.get_program_matrix(
            program_id,
            program_cycle_id=program_cycle_id,
            fiscal_year=fiscal_year,
            baseline_only=bool(baseline_only),
        )
        return success_response(data=matrix)
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Program Cycle Endpoints ───────────────────────────────────────────────

@programs_bp.route('/<int:program_id>/cycles', methods=['POST'])
@jwt_required()
@admin_required
def create_program_cycle(program_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_cycle_create(data)
    if errors:
        return validation_error(errors)

    try:
        cycle = program_service.create_program_cycle(
            program_id=program_id,
            name=data['name'],
            fiscal_year=data['fiscal_year'],
            cycle_code=data['cycle_code'],
            source_template_name=data.get('source_template_name'),
            import_profile=data.get('import_profile'),
            field_schema=data.get('field_schema'),
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=program_service._serialize_program_cycle(cycle),
            message='Program cycle created successfully',
            status_code=201,
        )
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/<int:program_id>/cycles', methods=['GET'])
@jwt_required()
def list_program_cycles(program_id):
    is_active, bool_errors = _parse_bool_arg('is_active')
    if bool_errors:
        return validation_error(bool_errors)

    try:
        fiscal_year = parse_fiscal_year_arg(request.args)
        cycles = program_service.list_program_cycles(program_id, is_active=is_active, fiscal_year=fiscal_year)
        return success_response(data=cycles)
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/cycles/<int:cycle_id>', methods=['GET'])
@jwt_required()
def get_program_cycle(cycle_id):
    try:
        cycle = program_service.get_program_cycle(cycle_id)
        return success_response(data=program_service._serialize_program_cycle(cycle))
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/cycles/<int:cycle_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_program_cycle(cycle_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_cycle_update(data)
    if errors:
        return validation_error(errors)

    try:
        cycle = program_service.update_program_cycle(
            cycle_id,
            data,
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=program_service._serialize_program_cycle(cycle),
            message='Program cycle updated successfully',
        )
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/cycles/<int:cycle_id>/clone', methods=['POST'])
@jwt_required()
@admin_required
def clone_program_cycle(cycle_id):
    data = request.get_json() or {}
    errors = validate_cycle_clone(data)
    if errors:
        return validation_error(errors)

    try:
        cycle = program_service.clone_program_cycle(
            cycle_id,
            fiscal_year=data['fiscal_year'],
            cycle_code=data.get('cycle_code'),
            name=data.get('name'),
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=program_service._serialize_program_cycle(cycle),
            message='Program cycle cloned successfully',
            status_code=201,
        )
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Phase Endpoints ───────────────────────────────────────────────────────

@programs_bp.route('/<int:program_id>/phases', methods=['POST'])
@jwt_required()
@admin_required
def create_phase(program_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_phase_create(data)
    if errors:
        return validation_error(errors)

    try:
        phase = program_service.create_phase(
            program_id=program_id,
            name=data['name'],
            phase_order=data['phase_order'],
            description=data.get('description'),
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=program_service._serialize_phase(phase),
            message='Phase created successfully',
            status_code=201,
        )
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/<int:program_id>/phases', methods=['GET'])
@jwt_required()
def list_phases(program_id):
    try:
        phases = program_service.list_phases(program_id)
        return success_response(data=phases)
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/phases/<int:phase_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_phase(phase_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_phase_update(data)
    if errors:
        return validation_error(errors)

    try:
        phase = program_service.update_phase(phase_id, data, user_id=get_jwt_identity())
        return success_response(
            data=program_service._serialize_phase(phase),
            message='Phase updated successfully',
        )
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/phases/<int:phase_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_phase(phase_id):
    try:
        result = program_service.delete_phase(phase_id, user_id=get_jwt_identity())
        return success_response(message=result['message'])
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Requirement Endpoints ─────────────────────────────────────────────────

@programs_bp.route('/<int:program_id>/requirements', methods=['GET'])
@jwt_required()
def list_requirements(program_id):
    requirement_type = request.args.get('requirement_type')
    is_mandatory, bool_errors = _parse_bool_arg('is_mandatory')
    program_cycle_id, id_errors = _parse_positive_int_arg('program_cycle_id')
    if bool_errors:
        return validation_error(bool_errors)
    if id_errors:
        return validation_error(id_errors)

    try:
        fiscal_year = parse_fiscal_year_arg(request.args)
        # Verify program exists first
        program_service.get_program(program_id)
        requirements = program_service.list_requirements(
            program_id=program_id,
            requirement_type=requirement_type,
            is_mandatory=is_mandatory,
            program_cycle_id=program_cycle_id,
            fiscal_year=fiscal_year,
        )
        return success_response(data=requirements)
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)


@programs_bp.route('/phases/<int:phase_id>/requirements', methods=['POST'])
@jwt_required()
@admin_required
def create_requirement(phase_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_requirement_create(data)
    if errors:
        return validation_error(errors)

    try:
        req = program_service.create_requirement(
            phase_id=phase_id,
            name=data['name'],
            requirement_type=data.get('requirement_type', 'document'),
            description=data.get('description'),
            annex_reference=data.get('annex_reference'),
            sort_order=data.get('sort_order', 0),
            is_mandatory=data.get('is_mandatory', True),
            has_sla=data.get('has_sla', False),
            sla_days=data.get('sla_days'),
            custom_field_schema=data.get('custom_field_schema'),
            checker_configuration=data.get('checker_configuration'),
            document_category=data.get('document_category'),
            confirm_similar=data.get('confirm_similar', False),
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=program_service._serialize_requirement(req),
            message='Requirement created successfully',
            status_code=201,
        )
    except program_service.ProgramError as e:
        return error_response(e.message, errors=getattr(e, 'errors', None), status_code=e.status_code)


@programs_bp.route('/requirements/<int:requirement_id>', methods=['GET'])
@jwt_required()
def get_requirement(requirement_id):
    try:
        req = program_service.get_requirement(requirement_id)
        return success_response(data=program_service._serialize_requirement(req))
    except program_service.ProgramError as e:
        return error_response(e.message, errors=getattr(e, 'errors', None), status_code=e.status_code)


@programs_bp.route('/requirements/<int:requirement_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_requirement(requirement_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_requirement_update(data)
    if errors:
        return validation_error(errors)

    try:
        req = program_service.update_requirement(requirement_id, data, user_id=get_jwt_identity())
        return success_response(
            data=program_service._serialize_requirement(req),
            message='Requirement updated successfully',
        )
    except program_service.ProgramError as e:
        return error_response(e.message, errors=getattr(e, 'errors', None), status_code=e.status_code)


@programs_bp.route('/requirements/<int:requirement_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_requirement(requirement_id):
    try:
        result = program_service.delete_requirement(requirement_id, user_id=get_jwt_identity())
        return success_response(message=result['message'])
    except program_service.ProgramError as e:
        return error_response(e.message, status_code=e.status_code)
