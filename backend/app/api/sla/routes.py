from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.utils.auth import admin_or_staff_or_field_required, admin_required, admin_or_staff_required
from app.services import sla_service
from app.utils.response import (
    success_response, error_response, not_found_error, validation_error
)
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg
from app.api.sla.schemas import (
    validate_sla_create, validate_sla_update, validate_sla_resolve,
)

from . import sla_bp


def _parse_bool_arg(name, *, default=None):
    raw = request.args.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value == 'true':
        return True
    if value == 'false':
        return False
    raise ValueError(f'{name} must be true or false')


# ── SLA Dashboard ──────────────────────────────────────────────────────────

@sla_bp.route('/dashboard', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def sla_dashboard():
    try:
        data = sla_service.get_sla_dashboard(
            user_id=get_jwt_identity(),
            fiscal_year=parse_fiscal_year_arg(request.args),
        )
        return success_response(data=data)
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except sla_service.SlaError as e:
        return error_response(e.message, status_code=e.status_code)


# ── SLA Deadline CRUD ──────────────────────────────────────────────────────

@sla_bp.route('/deadlines', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_sla_deadlines():
    project_id = request.args.get('project_id', type=int)
    project_requirement_id = request.args.get('project_requirement_id', type=int)
    program_id = request.args.get('program_id', type=int)
    lgu_id = request.args.get('lgu_id', type=int)
    deadline_type = request.args.get('deadline_type')
    phase_name = request.args.get('phase_name')
    requirement_status = request.args.get('requirement_status')
    due_bucket = request.args.get('due_bucket')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search')

    try:
        is_resolved = _parse_bool_arg('is_resolved')
        has_requirement = _parse_bool_arg('has_requirement')
        overdue_only = _parse_bool_arg('overdue_only', default=False)
        fiscal_year = parse_fiscal_year_arg(request.args)
        result = sla_service.list_sla_deadlines(
            project_id=project_id,
            project_requirement_id=project_requirement_id,
            program_id=program_id,
            lgu_id=lgu_id,
            deadline_type=deadline_type,
            phase_name=phase_name,
            requirement_status=requirement_status,
            has_requirement=has_requirement,
            due_bucket=due_bucket,
            is_resolved=is_resolved,
            overdue_only=overdue_only,
            page=page,
            per_page=per_page,
            fiscal_year=fiscal_year,
            user_id=get_jwt_identity(),
            search=search,
            project_status=request.args.get('project_status'),
        )
        return success_response(data=result['deadlines'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except ValueError as e:
        field = str(e).split(' ', 1)[0]
        return validation_error({field: str(e)})
    except sla_service.SlaError as e:
        return error_response(e.message, status_code=e.status_code)


@sla_bp.route('/deadlines/<int:sla_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_sla_deadline(sla_id):
    try:
        data = sla_service.get_sla_deadline_detail(sla_id, user_id=get_jwt_identity())
        return success_response(data=data)
    except sla_service.SlaError as e:
        return error_response(e.message, status_code=e.status_code)


@sla_bp.route('/deadlines', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def create_sla_deadline():
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_sla_create(data)
    if errors:
        return validation_error(errors)

    try:
        sla = sla_service.create_sla_deadline(
            project_id=data['project_id'],
            deadline_type=data['deadline_type'],
            trigger_date=data['trigger_date'],
            deadline_date=data['deadline_date'],
            sla_working_days=data.get('sla_working_days'),
            project_requirement_id=data.get('project_requirement_id'),
            notes=data.get('notes'),
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=sla_service._serialize_sla_deadline(sla),
            message='Compliance deadline created successfully',
            status_code=201,
        )
    except sla_service.SlaError as e:
        return error_response(e.message, status_code=e.status_code)


@sla_bp.route('/deadlines/<int:sla_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_sla_deadline(sla_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_sla_update(data)
    if errors:
        return validation_error(errors)

    try:
        sla = sla_service.update_sla_deadline(sla_id, data, user_id=get_jwt_identity())
        return success_response(
            data=sla_service._serialize_sla_deadline(sla),
            message='SLA deadline updated successfully',
        )
    except sla_service.SlaError as e:
        return error_response(e.message, status_code=e.status_code)


@sla_bp.route('/deadlines/<int:sla_id>/resolve', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def resolve_sla_deadline(sla_id):
    data = request.get_json() or {}

    errors = validate_sla_resolve(data)
    if errors:
        return validation_error(errors)

    try:
        sla = sla_service.resolve_sla_deadline(sla_id, notes=data.get('notes'), user_id=get_jwt_identity())
        return success_response(
            data=sla_service._serialize_sla_deadline(sla),
            message='SLA deadline resolved successfully',
        )
    except sla_service.SlaError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Overdue SLA Deadlines ─────────────────────────────────────────────────

@sla_bp.route('/overdue', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_overdue_deadlines():
    project_id = request.args.get('project_id', type=int)

    try:
        deadlines = sla_service.get_overdue_deadlines(
            project_id=project_id,
            fiscal_year=parse_fiscal_year_arg(request.args),
            user_id=get_jwt_identity(),
        )
        return success_response(data=deadlines)
    except FiscalYearError as e:
        return validation_error({'fiscal_year': str(e)})
    except sla_service.SlaError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Auto-create SLA from requirement ───────────────────────────────────────

@sla_bp.route('/deadlines/auto-create/<int:requirement_id>', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def auto_create_sla(requirement_id):
    data = request.get_json() or {}
    trigger_date = data.get('trigger_date')

    try:
        sla = sla_service.auto_create_sla_for_requirement(
            project_requirement_id=requirement_id,
            trigger_date=trigger_date,
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=sla_service._serialize_sla_deadline(sla),
            message='Compliance deadline auto-created from requirement',
            status_code=201,
        )
    except sla_service.SlaError as e:
        return error_response(e.message, status_code=e.status_code)
