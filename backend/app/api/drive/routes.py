from urllib.parse import quote

from flask import current_app, redirect, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import drive_service, settings_service
from app.utils.auth import (
    admin_or_staff_required,
    system_admin_or_admin_required,
)
from app.utils.response import error_response, success_response, validation_error

from . import drive_bp


@drive_bp.route('/root', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def get_drive_root():
    try:
        return success_response(data=drive_service.get_workspace_root(user_id=get_jwt_identity()))
    except drive_service.DriveServiceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@drive_bp.route('/children', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def list_drive_children():
    try:
        return success_response(data=drive_service.list_children(
            parent_id=request.args.get('parent_id'),
            user_id=get_jwt_identity(),
        ))
    except drive_service.DriveServiceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@drive_bp.route('/folders', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def create_drive_folder():
    data = request.get_json() or {}
    if not str(data.get('name') or '').strip():
        return validation_error({'name': 'Folder name is required.'})

    try:
        folder = drive_service.create_folder(
            name=data.get('name'),
            parent_id=data.get('parent_id'),
            user_id=get_jwt_identity(),
        )
        return success_response(data=folder, message='Folder created successfully.', status_code=201)
    except drive_service.DriveServiceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@drive_bp.route('/files/<file_id>/move', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def move_drive_file(file_id):
    data = request.get_json() or {}
    if not str(data.get('target_parent_id') or '').strip():
        return validation_error({'target_parent_id': 'Target folder is required.'})

    try:
        item = drive_service.move_item(
            file_id=file_id,
            target_parent_id=data.get('target_parent_id'),
            user_id=get_jwt_identity(),
        )
        return success_response(data=item, message='Drive item moved successfully.')
    except drive_service.DriveServiceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@drive_bp.route('/readiness', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def get_drive_readiness():
    try:
        return success_response(data=settings_service.get_google_drive_handoff_readiness())
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@drive_bp.route('/connection', methods=['GET'])
@jwt_required()
@system_admin_or_admin_required
def get_drive_connection():
    try:
        return success_response(data=drive_service.get_connection_status())
    except drive_service.DriveServiceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@drive_bp.route('/connection', methods=['PUT'])
@jwt_required()
@system_admin_or_admin_required
def update_drive_connection_settings():
    data = request.get_json() or {}
    try:
        return success_response(
            data=drive_service.update_drive_settings(
                root_folder_id=data.get('root_folder_id'),
                user_id=get_jwt_identity(),
            ),
            message='Google Drive handoff settings updated.',
        )
    except drive_service.DriveServiceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@drive_bp.route('/oauth/start', methods=['POST'])
@jwt_required()
@system_admin_or_admin_required
def start_drive_oauth():
    try:
        return success_response(data=drive_service.start_oauth_connection(get_jwt_identity()))
    except drive_service.DriveServiceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@drive_bp.route('/oauth/callback', methods=['GET'])
def complete_drive_oauth():
    error = request.args.get('error')
    frontend_url = current_app.config.get('APP_FRONTEND_URL', 'http://localhost:3000').rstrip('/') + '/dashboard/settings'
    if error:
        return redirect(f'{frontend_url}?drive_oauth=error&reason={quote(error)}')
    try:
        drive_service.complete_oauth_connection(
            code=request.args.get('code'),
            state=request.args.get('state'),
        )
        return redirect(f'{frontend_url}?drive_oauth=connected')
    except drive_service.DriveServiceError as exc:
        return redirect(f'{frontend_url}?drive_oauth=error&reason={quote(exc.message)}')


@drive_bp.route('/oauth/disconnect', methods=['POST'])
@jwt_required()
@system_admin_or_admin_required
def disconnect_drive_oauth():
    try:
        return success_response(
            data=drive_service.disconnect_oauth(get_jwt_identity()),
            message='Google Drive account disconnected.',
        )
    except drive_service.DriveServiceError as exc:
        return error_response(exc.message, status_code=exc.status_code)
