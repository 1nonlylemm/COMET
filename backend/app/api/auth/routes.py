from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.models.user import User
from app.utils.auth import step_up_required, system_admin_or_admin_required
from app.services import auth_service, settings_service
from app.utils.response import (
    success_response, error_response, not_found_error, forbidden_error, validation_error
)
from app.api.auth.schemas import (
    validate_admin_user_create, validate_register, validate_login,
    validate_change_password, validate_change_role, validate_toggle_active,
    validate_update_profile, validate_forgot_password, validate_reset_password,
    validate_mfa_verify, validate_step_up
)

from . import auth_bp


@auth_bp.route('/register', methods=['POST'])
def register():
    app_name = settings_service.get_app_name()
    return forbidden_error(
        f'Self-registration is disabled. Accounts are created by {app_name} administrators.',
    )


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_login(data)
    if errors:
        return validation_error(errors)

    try:
        result = auth_service.login_user(data['email'], data['password'])
        return success_response(data=result, message='Login successful')
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    try:
        result = auth_service.refresh_access(identity)
        return success_response(data=result, message='Token refreshed')
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    user_id = get_jwt_identity()
    try:
        result = auth_service.logout_user(user_id)
        return success_response(message=result['message'])
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    try:
        user = auth_service.get_current_user(user_id)
        return success_response(data=user)
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/me', methods=['PUT'])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_update_profile(data)
    if errors:
        return validation_error(errors)

    try:
        user = auth_service.update_user_profile(user_id, data)
        return success_response(data=user, message='Profile updated')
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    from app.extensions import db
    user = db.session.get(User, user_id)
    errors = validate_change_password(data, user_email=user.email if user else None)
    if errors:
        return validation_error(errors)

    try:
        result = auth_service.change_password(
            user_id, data['current_password'], data['new_password']
        )
        return success_response(message=result['message'])
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/users', methods=['GET'])
@system_admin_or_admin_required
def list_users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    role = request.args.get('role')
    is_active = request.args.get('is_active')
    must_change_password = request.args.get('must_change_password')
    search = request.args.get('search')
    if is_active is not None:
        is_active = is_active.lower() == 'true'
    if must_change_password is not None:
        must_change_password = must_change_password.lower() == 'true'

    result = auth_service.list_users(
        page=page,
        per_page=per_page,
        role=role,
        is_active=is_active,
        must_change_password=must_change_password,
        search=search,
        actor_id=get_jwt_identity(),
    )
    return success_response(data=result['users'], meta={
        'page': result['page'],
        'per_page': result['per_page'],
        'total': result['total'],
        'pages': result['pages'],
    })    


@auth_bp.route('/users/<int:user_id>', methods=['GET'])
@system_admin_or_admin_required
def get_user(user_id):
    try:
        user = auth_service.get_user_for_admin(user_id, actor_id=get_jwt_identity())
        return success_response(data=user)
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/users', methods=['POST'])
@system_admin_or_admin_required
def create_user():
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_admin_user_create(data)
    if errors:
        return validation_error(errors)

    try:
        result = auth_service.create_user_account(
            admin_id=get_jwt_identity(),
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            role=data['role'],
            cluster_ids=data.get('cluster_ids') or [],
            lgu_ids=data.get('lgu_ids') or [],
        )
        return success_response(
            data=result,
            message='User account created successfully',
            status_code=201,
        )
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
@system_admin_or_admin_required
@step_up_required
def toggle_active(user_id):
    admin_id = get_jwt_identity()
    data = request.get_json() or {}
    errors = validate_toggle_active(data)
    if errors:
        return validation_error(errors)
    is_active = data.get('is_active')

    try:
        user = auth_service.toggle_user_active(admin_id, user_id, is_active)
        return success_response(data=user, message=f'User {"activated" if is_active else "deactivated"}')
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/users/<int:user_id>/change-role', methods=['POST'])
@system_admin_or_admin_required
@step_up_required
def change_role(user_id):
    data = request.get_json()
    errors = validate_change_role(data or {})
    if errors:
        return validation_error(errors)

    try:
        user = auth_service.change_user_role(
            get_jwt_identity(),
            user_id,
            data['role'],
            cluster_ids=data.get('cluster_ids'),
            lgu_ids=data.get('lgu_ids'),
            can_approve_technical_documents=data.get('can_approve_technical_documents'),
            can_close_management_actions=data.get('can_close_management_actions'),
        )
        return success_response(data=user, message='Role updated')
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/users/<int:user_id>/revoke-sessions', methods=['POST'])
@system_admin_or_admin_required
@step_up_required
def revoke_sessions(user_id):
    admin_id = get_jwt_identity()
    try:
        result = auth_service.revoke_user_sessions(user_id, actor_id=admin_id)
        return success_response(message=result['message'])
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    errors = validate_forgot_password(data)
    if errors:
        return validation_error(errors)
    try:
        result = auth_service.request_password_reset(data['email'])
        return success_response(data=result, message=result['message'])
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/reset-password/validate', methods=['POST'])
def validate_reset_token():
    data = request.get_json() or {}
    token = data.get('token')
    if not token:
        return error_response('Reset token is required', status_code=400)
    try:
        result = auth_service.validate_password_reset_token(token)
        return success_response(data=result, message=result['message'])
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json() or {}
    errors = validate_reset_password(data)
    if errors:
        return validation_error(errors)
    try:
        result = auth_service.complete_password_reset(data['token'], data['new_password'])
        return success_response(message=result['message'])
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/mfa/enroll', methods=['POST'])
@jwt_required()
def mfa_enroll():
    user_id = get_jwt_identity()
    try:
        result = auth_service.enroll_mfa(user_id)
        return success_response(data=result, message='MFA enrollment initiated')
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/mfa/confirm', methods=['POST'])
@jwt_required()
def mfa_confirm():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    code = data.get('code')
    if not code:
        return error_response('Verification code is required', status_code=400)
    try:
        result = auth_service.confirm_mfa_enrollment(user_id, code)
        return success_response(data=result, message=result['message'])
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/mfa/verify', methods=['POST'])
@jwt_required()
def mfa_verify():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    errors = validate_mfa_verify(data)
    if errors:
        return validation_error(errors)
    try:
        result = auth_service.verify_mfa_login(
            user_id,
            code=data.get('code'),
            recovery_code=data.get('recovery_code'),
        )
        return success_response(data=result, message='MFA verification successful')
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/mfa/reset', methods=['POST'])
@jwt_required()
@step_up_required
def mfa_reset():
    actor_id = get_jwt_identity()
    data = request.get_json() or {}
    target_user_id = data.get('user_id') or actor_id
    try:
        result = auth_service.reset_mfa(actor_id, target_user_id)
        return success_response(message=result['message'])
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)


@auth_bp.route('/step-up', methods=['POST'])
@jwt_required()
def step_up():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    errors = validate_step_up(data)
    if errors:
        return validation_error(errors)
    try:
        result = auth_service.verify_step_up(
            user_id,
            password=data['password'],
            totp_code=data.get('totp_code'),
        )
        return success_response(data=result, message=result['message'])
    except auth_service.AuthError as e:
        return error_response(e.message, status_code=e.status_code)
