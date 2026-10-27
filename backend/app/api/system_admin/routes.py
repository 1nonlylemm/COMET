from flask import request
from flask_jwt_extended import get_jwt_identity

from app.services import backup_service, operational_event_service, settings_service, system_admin_service
from app.services.backup_service import BackupError
from app.services.object_storage_service import ObjectStorageError
from app.utils.auth import step_up_required, system_admin_required
from app.utils.response import error_response, success_response

from . import system_admin_bp


@system_admin_bp.route('/overview', methods=['GET'])
@system_admin_required
def overview():
    return success_response(data=system_admin_service.get_overview())


@system_admin_bp.route('/technical-settings', methods=['GET'])
@system_admin_required
def technical_settings():
    return success_response(data=system_admin_service.get_technical_settings())


@system_admin_bp.route('/technical-settings', methods=['PUT'])
@system_admin_required
@step_up_required
def update_technical_settings():
    user_id = get_jwt_identity()
    body = dict(request.get_json(silent=True) or {})
    body.pop('confirm_password', None)
    body.pop('step_up_password', None)
    try:
        updated = system_admin_service.update_technical_settings(body, user_id=user_id)
        return success_response(
            data=updated,
            message='Technical settings updated successfully.',
        )
    except settings_service.SettingsError as exc:
        return error_response(message=exc.message, status_code=exc.status_code)


@system_admin_bp.route('/technical-settings/<key>', methods=['DELETE'])
@system_admin_required
@step_up_required
def delete_technical_setting_override(key):
    user_id = get_jwt_identity()
    try:
        updated = system_admin_service.delete_technical_setting_override(key, user_id=user_id)
        return success_response(
            data=updated,
            message=f"Configuration override for '{key}' removed; reverted to deployment fallback.",
        )
    except settings_service.SettingsError as exc:
        return error_response(message=exc.message, status_code=exc.status_code)


@system_admin_bp.route('/technical-settings/validate-credential', methods=['POST'])
@system_admin_required
@step_up_required
def validate_credential():
    body = request.get_json(silent=True) or {}
    provider = body.get('provider')
    api_key = body.get('api_key')
    try:
        result = system_admin_service.validate_ai_provider_credential(provider=provider, api_key=api_key)
        return success_response(data=result)
    except settings_service.SettingsError as exc:
        return error_response(message=exc.message, status_code=exc.status_code)


@system_admin_bp.route('/technical-settings/validate-storage', methods=['POST'])
@system_admin_required
@step_up_required
def validate_storage():
    from app.services import integration_config_service
    body = request.get_json(silent=True) or {}
    try:
        result = integration_config_service.validate_object_storage_credentials(
            provider=body.get('provider') or body.get('storage_provider') or body.get('OBJECT_STORAGE_PROVIDER'),
            bucket_name=body.get('bucket_name') or body.get('R2_BUCKET_NAME'),
            endpoint_url=body.get('endpoint_url') or body.get('R2_ENDPOINT_URL'),
            access_key_id=body.get('access_key_id') or body.get('R2_ACCESS_KEY_ID'),
            secret_access_key=body.get('secret_access_key') or body.get('R2_SECRET_ACCESS_KEY'),
            region=body.get('region') or body.get('R2_REGION'),
        )
        return success_response(data=result)
    except settings_service.SettingsError as exc:
        return error_response(message=exc.message, status_code=exc.status_code)


@system_admin_bp.route('/technical-settings/validate-email', methods=['POST'])
@system_admin_required
@step_up_required
def validate_email():
    from app.services import integration_config_service
    body = request.get_json(silent=True) or {}
    try:
        result = integration_config_service.validate_smtp_credentials(
            host=body.get('host') or body.get('smtp_host') or body.get('SMTP_HOST'),
            port=body.get('port') or body.get('smtp_port') or body.get('SMTP_PORT'),
            username=body.get('username') or body.get('smtp_username') or body.get('SMTP_USERNAME'),
            password=body.get('password') or body.get('smtp_password') or body.get('SMTP_PASSWORD'),
            use_tls=body.get('use_tls') if 'use_tls' in body else (body.get('smtp_use_tls') if 'smtp_use_tls' in body else body.get('SMTP_USE_TLS')),
        )
        return success_response(data=result)
    except settings_service.SettingsError as exc:
        return error_response(message=exc.message, status_code=exc.status_code)


@system_admin_bp.route('/backups', methods=['GET'])
@system_admin_required
def list_backups():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    data = backup_service.list_backups(page=page, per_page=per_page)
    return success_response(data=data)


@system_admin_bp.route('/backups', methods=['POST'])
@system_admin_required
def trigger_backup():
    user_id = get_jwt_identity()
    try:
        data = backup_service.create_backup(user_id=user_id, trigger_type='manual')
        return success_response(data=data, message='Database backup created successfully.')
    except BackupError as exc:
        return error_response(message=exc.message, status_code=exc.status_code)


@system_admin_bp.route('/backups/<int:backup_id>/download', methods=['GET'])
@system_admin_required
def download_backup(backup_id):
    try:
        return backup_service.download_backup(backup_id)
    except BackupError as exc:
        return error_response(message=exc.message, status_code=exc.status_code)


@system_admin_bp.route('/backups/<int:backup_id>/restore', methods=['POST'])
@system_admin_required
@step_up_required
def restore_backup(backup_id):
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}
    confirmation_phrase = body.get('confirmation_phrase', '')
    target_db_url = body.get('target_db_url')

    try:
        result = backup_service.restore_backup(
            backup_id=backup_id,
            confirmation_phrase=confirmation_phrase,
            target_db_url=target_db_url,
            user_id=user_id,
        )
        return success_response(data=result, message='Database restore completed successfully.')
    except BackupError as exc:
        return error_response(message=exc.message, status_code=exc.status_code)


@system_admin_bp.route('/operational-events', methods=['GET'])
@system_admin_bp.route('/diagnostics/events', methods=['GET'])
@system_admin_required
def list_operational_events():
    try:
        severity = request.args.get('severity')
        component = request.args.get('component')
        request_id = request.args.get('request_id')
        operation_id = request.args.get('operation_id')
        search = request.args.get('search')
        start_time_str = request.args.get('start_time') or request.args.get('from_date')
        end_time_str = request.args.get('end_time') or request.args.get('to_date')

        page_raw = request.args.get('page', 1)
        try:
            page = int(page_raw)
        except (ValueError, TypeError):
            return error_response("Invalid 'page' parameter. Must be an integer.", status_code=400)

        per_page_raw = request.args.get('per_page', 20)
        try:
            per_page = int(per_page_raw)
        except (ValueError, TypeError):
            return error_response("Invalid 'per_page' parameter. Must be an integer.", status_code=400)

        data = operational_event_service.query_operational_events(
            severity=severity,
            component=component,
            request_id=request_id,
            operation_id=operation_id,
            search=search,
            start_time_str=start_time_str,
            end_time_str=end_time_str,
            page=page,
            per_page=per_page,
        )
        return success_response(
            data=data['items'],
            meta=data['meta'],
            message='Operational events retrieved successfully.',
        )
    except ValueError as val_err:
        return error_response(str(val_err), status_code=400)


@system_admin_bp.route('/operational-events/<int:event_id>', methods=['GET'])
@system_admin_bp.route('/diagnostics/events/<int:event_id>', methods=['GET'])
@system_admin_required
def get_operational_event(event_id):
    event_data = operational_event_service.get_operational_event(event_id)
    if not event_data:
        return error_response(f'Operational event {event_id} not found.', status_code=404)
    return success_response(data=event_data, message='Operational event retrieved successfully.')
