from flask import request
from flask_jwt_extended import get_jwt_identity

from app.api.magic_links.schemas import validate_magic_link_create
from app.services import email_service
from app.utils.auth import admin_or_staff_required
from app.utils.response import error_response, success_response, validation_error

from . import magic_links_bp


@magic_links_bp.route('', methods=['POST'])
@admin_or_staff_required
def create_magic_link():
    data = request.get_json() or {}
    errors = validate_magic_link_create(data)
    if errors:
        return validation_error(errors)

    try:
        link = email_service.create_magic_link(
            notice_id=data.get('notice_id'),
            project_id=data.get('project_id'),
            expires_in_days=data.get('expires_in_days'),
            intended_recipient_name=data.get('intended_recipient_name'),
            intended_recipient_role=data.get('intended_recipient_role'),
            user_id=get_jwt_identity(),
        )
        return success_response(data=link, message='Magic link generated successfully', status_code=201)
    except email_service.DispatchError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@magic_links_bp.route('/<string:token>', methods=['GET'])
def get_magic_link(token):
    try:
        payload = email_service.get_magic_link_view(token)
        return success_response(data=payload)
    except email_service.DispatchError as exc:
        return error_response(exc.message, status_code=exc.status_code)
