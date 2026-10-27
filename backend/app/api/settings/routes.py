from flask import request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.settings.schemas import validate_system_config_payload
from app.services import settings_service
from app.utils.auth import admin_required
from app.utils.response import error_response, success_response, validation_error

from . import settings_bp


@settings_bp.route('/branding', methods=['GET'])
def get_branding():
    try:
        return success_response(data=settings_service.get_branding())
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/branding', methods=['PUT'])
@jwt_required()
@admin_required
def update_branding():
    data = request.get_json() or {}
    try:
        return success_response(
            data=settings_service.update_branding(data, user_id=get_jwt_identity()),
            message='Application branding updated successfully',
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/branding/<asset_type>', methods=['POST'])
@jwt_required()
@admin_required
def upload_brand_asset(asset_type):
    try:
        return success_response(
            data=settings_service.store_brand_asset(
                asset_type,
                upload=request.files.get('file'),
                user_id=get_jwt_identity(),
            ),
            message=f'Application {asset_type} uploaded successfully',
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/branding/<asset_type>', methods=['GET'])
def serve_brand_asset(asset_type):
    try:
        path, mime_type, file_name = settings_service.get_brand_asset(asset_type)
        is_svg = (mime_type == 'image/svg+xml') or str(path).lower().endswith('.svg')
        response = send_file(
            path,
            mimetype='application/octet-stream' if is_svg else mime_type,
            as_attachment=True if is_svg else False,
            download_name=file_name,
            conditional=True,
            max_age=3600,
        )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox"
        response.headers['Cache-Control'] = 'public, max-age=3600, immutable'
        return response
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/readiness', methods=['GET'])
@jwt_required()
@admin_required
def readiness():
    try:
        return success_response(data=settings_service.get_readiness_snapshot())
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/configs', methods=['GET'])
@jwt_required()
@admin_required
def list_configs():
    try:
        return success_response(data=settings_service.list_configs())
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/defaults', methods=['GET'])
@jwt_required()
@admin_required
def list_operational_defaults():
    try:
        return success_response(data=settings_service.get_defaults_catalog())
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/document-templates', methods=['GET'])
@jwt_required()
@admin_required
def list_document_templates():
    try:
        return success_response(data=settings_service.list_document_templates())
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/report-templates', methods=['GET'])
@jwt_required()
@admin_required
def list_report_templates():
    try:
        return success_response(data=settings_service.list_report_templates())
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/document-templates/<template_type>', methods=['POST'])
@jwt_required()
@admin_required
def upload_document_template(template_type):
    try:
        return success_response(
            data=settings_service.store_document_template(
                template_type,
                upload=request.files.get('file'),
                user_id=get_jwt_identity(),
                label=request.form.get('label'),
                placeholder_defaults=request.form.get('placeholder_defaults'),
                is_default=request.form.get('is_default', True),
            ),
            message='Document template uploaded and placeholders scanned successfully',
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/report-templates/<template_type>', methods=['POST'])
@jwt_required()
@admin_required
def upload_report_template(template_type):
    try:
        return success_response(
            data=settings_service.store_report_template(
                template_type,
                upload=request.files.get('file'),
                user_id=get_jwt_identity(),
                label=request.form.get('label'),
                placeholder_defaults=request.form.get('placeholder_defaults'),
                is_default=request.form.get('is_default', True),
            ),
            message='Report template uploaded successfully',
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/document-templates/<template_type>/<template_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_document_template(template_type, template_id):
    data = request.get_json() or {}
    try:
        return success_response(
            data=settings_service.update_document_template(
                template_type,
                template_id,
                data=data,
                user_id=get_jwt_identity(),
            ),
            message='Document template updated successfully',
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/document-templates/<template_type>/<template_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_document_template(template_type, template_id):
    try:
        return success_response(
            data=settings_service.delete_document_template(
                template_type,
                template_id,
                user_id=get_jwt_identity(),
            ),
            message='Document template deleted successfully',
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/report-templates/<template_type>/<template_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_report_template(template_type, template_id):
    data = request.get_json() or {}
    try:
        return success_response(
            data=settings_service.update_report_template(
                template_type,
                template_id,
                data=data,
                user_id=get_jwt_identity(),
            ),
            message='Report template updated successfully',
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/report-templates/<template_type>/<template_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_report_template(template_type, template_id):
    try:
        return success_response(
            data=settings_service.delete_report_template(
                template_type,
                template_id,
                user_id=get_jwt_identity(),
            ),
            message='Report template deleted successfully',
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/configs', methods=['POST'])
@jwt_required()
@admin_required
def create_config():
    data = request.get_json() or {}
    errors = validate_system_config_payload(data)
    if errors:
        return validation_error(errors)

    try:
        config = settings_service.create_config(data, user_id=get_jwt_identity())
        return success_response(
            data=settings_service._serialize_config(config),
            message='Operational default created successfully',
            status_code=201,
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@settings_bp.route('/configs/<int:config_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_config(config_id):
    data = request.get_json() or {}
    errors = validate_system_config_payload(data, partial=True)
    if errors:
        return validation_error(errors)

    try:
        config = settings_service.update_config(config_id, data, user_id=get_jwt_identity())
        return success_response(
            data=settings_service._serialize_config(config),
            message='Operational default updated successfully',
        )
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)
