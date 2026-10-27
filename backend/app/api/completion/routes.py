from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.completion.schemas import validate_completion_update
from app.services import completion_service
from app.utils.auth import admin_or_staff_or_field_required, admin_or_staff_required
from app.utils.response import error_response, success_response, validation_error
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg

from . import completion_bp


@completion_bp.route('/projects', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_completion_projects():
    search = request.args.get('search')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    try:
        result = completion_service.list_completion_projects(
            search=search,
            fiscal_year=parse_fiscal_year_arg(request.args),
            page=page,
            per_page=per_page,
            user_id=get_jwt_identity(),
        )
        return success_response(data=result['projects'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except completion_service.CompletionError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@completion_bp.route('/projects/<int:project_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_completion_project(project_id):
    try:
        detail = completion_service.get_completion_detail(project_id, user_id=get_jwt_identity())
        return success_response(data=detail)
    except completion_service.CompletionError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@completion_bp.route('/projects/<int:project_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_completion_project(project_id):
    data = request.get_json() or {}
    errors = validate_completion_update(data)
    if errors:
        return validation_error(errors)

    try:
        detail = completion_service.update_completion_detail(
            project_id,
            data,
            user_id=get_jwt_identity(),
        )
        return success_response(data=detail, message='Completion milestone updated successfully')
    except completion_service.CompletionError as exc:
        return error_response(exc.message, status_code=exc.status_code)
