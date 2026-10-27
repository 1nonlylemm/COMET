from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import field_officer_service
from app.utils.auth import role_required
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg
from app.utils.response import error_response, success_response, validation_error

from . import field_officer_bp


def _field_error_response(exc):
    return error_response(exc.message, status_code=exc.status_code)


@field_officer_bp.route('/summary', methods=['GET'])
@jwt_required()
@role_required('field_officer')
def field_summary():
    try:
        data = field_officer_service.get_field_summary(
            user_id=get_jwt_identity(),
            fiscal_year=parse_fiscal_year_arg(request.args),
        )
        return success_response(data=data)
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except field_officer_service.FieldOfficerError as exc:
        return _field_error_response(exc)


@field_officer_bp.route('/lgus', methods=['GET'])
@jwt_required()
@role_required('field_officer')
def assigned_lgus():
    try:
        data = field_officer_service.list_assigned_lgus(
            user_id=get_jwt_identity(),
            fiscal_year=parse_fiscal_year_arg(request.args),
        )
        return success_response(data=data)
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except field_officer_service.FieldOfficerError as exc:
        return _field_error_response(exc)


@field_officer_bp.route('/action-items', methods=['GET'])
@jwt_required()
@role_required('field_officer')
def action_items():
    limit = request.args.get('limit', 50, type=int)
    limit = max(1, min(limit, 100))
    try:
        data = field_officer_service.list_action_items(
            user_id=get_jwt_identity(),
            fiscal_year=parse_fiscal_year_arg(request.args),
            limit=limit,
        )
        return success_response(data=data)
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except field_officer_service.FieldOfficerError as exc:
        return _field_error_response(exc)


@field_officer_bp.route('/requirements/<int:requirement_id>/comments', methods=['GET'])
@jwt_required()
@role_required('field_officer')
def list_requirement_comments(requirement_id):
    try:
        data = field_officer_service.list_requirement_comments(
            requirement_id=requirement_id,
            user_id=get_jwt_identity(),
        )
        return success_response(data=data)
    except field_officer_service.FieldOfficerError as exc:
        return _field_error_response(exc)


@field_officer_bp.route('/requirements/<int:requirement_id>/comments', methods=['POST'])
@jwt_required()
@role_required('field_officer')
def create_requirement_comment(requirement_id):
    payload = request.get_json(silent=True) or {}
    try:
        data = field_officer_service.create_requirement_comment(
            requirement_id=requirement_id,
            data=payload,
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=data,
            message='Field officer comment recorded.',
            status_code=201,
        )
    except field_officer_service.FieldOfficerError as exc:
        return _field_error_response(exc)
