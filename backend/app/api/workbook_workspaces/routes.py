from io import BytesIO

from flask import request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import access_service, project_service, workbook_workspace_service
from app.utils.auth import admin_or_staff_or_field_required, admin_or_staff_required, admin_required
from app.utils.response import error_response, success_response, validation_error
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg

from . import workbook_workspaces_bp


@workbook_workspaces_bp.route('', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_workspaces():
    try:
        workspaces = workbook_workspace_service.list_workspaces(
            program_id=request.args.get('program_id', type=int),
            program_cycle_id=request.args.get('program_cycle_id', type=int),
            fiscal_year=parse_fiscal_year_arg(request.args),
            user_id=get_jwt_identity(),
        )
        return success_response(data=workspaces)
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except workbook_workspace_service.WorkbookWorkspaceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@workbook_workspaces_bp.route('/<int:workspace_id>/sheets', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_sheets(workspace_id):
    try:
        return success_response(
            data=workbook_workspace_service.list_sheets(
                workspace_id,
                user_id=get_jwt_identity(),
            )
        )
    except workbook_workspace_service.WorkbookWorkspaceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@workbook_workspaces_bp.route('/<int:workspace_id>/sheets/<int:sheet_id>/grid', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_sheet_grid(workspace_id, sheet_id):
    try:
        return success_response(
            data=workbook_workspace_service.get_sheet_grid(
                workspace_id,
                sheet_id,
                user_id=get_jwt_identity(),
                page=request.args.get('page', 1, type=int),
                per_page=request.args.get('per_page', 100, type=int),
            )
        )
    except workbook_workspace_service.WorkbookWorkspaceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@workbook_workspaces_bp.route('/<int:workspace_id>/conflicts', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def list_conflicts(workspace_id):
    try:
        return success_response(
            data=workbook_workspace_service.list_conflicts(
                workspace_id,
                user_id=get_jwt_identity(),
                status=request.args.get('status', 'open'),
                page=request.args.get('page', 1, type=int),
                per_page=request.args.get('per_page', 50, type=int),
            )
        )
    except workbook_workspace_service.WorkbookWorkspaceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@workbook_workspaces_bp.route('/<int:workspace_id>/conflicts/<int:conflict_id>/resolve', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def resolve_conflict(workspace_id, conflict_id):
    data = request.get_json(silent=True) or {}
    if 'decision' not in data:
        return validation_error({'decision': 'Conflict decision is required'})

    try:
        return success_response(
            data=workbook_workspace_service.resolve_conflict(
                workspace_id,
                conflict_id,
                decision=data.get('decision'),
                user_id=get_jwt_identity(),
            ),
            message='Workbook conflict resolved successfully',
        )
    except workbook_workspace_service.WorkbookWorkspaceError as exc:
        return error_response(exc.message, status_code=exc.status_code)
    except project_service.ProjectError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@workbook_workspaces_bp.route('/<int:workspace_id>/cells/<int:cell_id>/history', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_cell_history(workspace_id, cell_id):
    try:
        return success_response(
            data=workbook_workspace_service.list_cell_history(
                workspace_id,
                cell_id,
                user_id=get_jwt_identity(),
                page=request.args.get('page', 1, type=int),
                per_page=request.args.get('per_page', 20, type=int),
            )
        )
    except workbook_workspace_service.WorkbookWorkspaceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@workbook_workspaces_bp.route('/<int:workspace_id>/export', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def export_workspace(workspace_id):
    try:
        export = workbook_workspace_service.export_workspace(
            workspace_id,
            user_id=get_jwt_identity(),
        )
        return send_file(
            BytesIO(export['content']),
            as_attachment=True,
            download_name=export['file_name'],
            mimetype=export['mimetype'],
        )
    except (workbook_workspace_service.WorkbookWorkspaceError, access_service.AccessError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@workbook_workspaces_bp.route('/<int:workspace_id>/columns/<int:column_id>', methods=['PATCH'])
@jwt_required()
@admin_required
def update_column(workspace_id, column_id):
    data = request.get_json(silent=True) or {}
    allowed_fields = {
        'is_editable',
        'display_format',
        'display_label',
        'data_type',
        'number_format',
        'binding_target',
        'binding_config',
        'validation_rules',
        'validation_options',
        'is_required',
        'is_formula',
        'formula_policy',
    }
    if not any(field in data for field in allowed_fields):
        return validation_error({'column': 'At least one column setting is required'})

    try:
        return success_response(
            data=workbook_workspace_service.update_column_settings(
                workspace_id,
                column_id,
                data=data,
                user_id=get_jwt_identity(),
            ),
            message='Workbook column updated successfully',
        )
    except workbook_workspace_service.WorkbookWorkspaceError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@workbook_workspaces_bp.route('/<int:workspace_id>/cells/<int:cell_id>', methods=['PATCH'])
@jwt_required()
@admin_or_staff_required
def update_cell(workspace_id, cell_id):
    data = request.get_json(silent=True) or {}
    if 'value' not in data:
        return validation_error({'value': 'Cell value is required'})

    try:
        cell = workbook_workspace_service.update_cell(
            workspace_id,
            cell_id,
            data.get('value'),
            user_id=get_jwt_identity(),
            reason=data.get('reason'),
        )
        return success_response(data=cell, message='Workbook cell updated successfully')
    except workbook_workspace_service.WorkbookWorkspaceError as exc:
        return error_response(exc.message, status_code=exc.status_code)
    except project_service.ProjectError as exc:
        return error_response(exc.message, status_code=exc.status_code)
