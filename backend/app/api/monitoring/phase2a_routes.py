"""Phase 2A monitoring API routes.

Exposes Monthly Progress Report, Form 3, Project Exception Report, the
Management Action Report lifecycle, the shared V&V Queue, and configurable
risk thresholds. Workflow transitions (submit/verify/staff-approve/
provincial-approve/return) for Monthly Progress Report, Form 3, and
Project Exception Report reuse the existing Phase 1 endpoints under
`/api/projects/requirements/<id>/workflow/*` via each record's
`project_requirement_id` -- no duplicate transition routes are added here.
"""
from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import (
    form3_service,
    monitoring_service,
    monthly_progress_service,
    project_exception_service,
    requirement_workflow_service,
    settings_service,
)
from app.utils.auth import admin_or_staff_or_field_required, admin_or_staff_required, admin_required
from app.utils.response import error_response, success_response, validation_error

from . import monitoring_bp


def _error(exc):
    return error_response(exc.message, status_code=exc.status_code)


# ---------------------------------------------------------------------------
# Monthly Progress Report
# ---------------------------------------------------------------------------

@monitoring_bp.route('/monthly-progress-reports', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_monthly_progress_reports():
    try:
        return success_response(data=monthly_progress_service.list_reports(
            project_id=request.args.get('project_id', type=int),
            reporting_period=request.args.get('reporting_period'),
            workflow_status=request.args.get('workflow_status'),
            user_id=get_jwt_identity(),
        ))
    except monthly_progress_service.MonthlyProgressError as exc:
        return _error(exc)


@monitoring_bp.route('/monthly-progress-reports', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def create_monthly_progress_report():
    data = request.get_json() if request.is_json else request.form.to_dict()
    data = data or {}
    upload = request.files.get('file')
    try:
        report = monthly_progress_service.create_report(
            data,
            user_id=get_jwt_identity(),
            upload=upload,
        )
        return success_response(
            data=monthly_progress_service._serialize_report(report),
            message='Monthly Progress Report created successfully.',
            status_code=201,
        )
    except monthly_progress_service.MonthlyProgressError as exc:
        return _error(exc)


@monitoring_bp.route('/monthly-progress-reports/<int:report_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_monthly_progress_report(report_id):
    try:
        report = monthly_progress_service.get_report(report_id, user_id=get_jwt_identity())
        return success_response(data=monthly_progress_service._serialize_report(report))
    except monthly_progress_service.MonthlyProgressError as exc:
        return _error(exc)


@monitoring_bp.route('/monthly-progress-reports/<int:report_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_or_field_required
def update_monthly_progress_report(report_id):
    data = request.get_json() or {}
    try:
        report = monthly_progress_service.update_report(report_id, data, user_id=get_jwt_identity())
        return success_response(
            data=monthly_progress_service._serialize_report(report),
            message='Monthly Progress Report updated successfully.',
        )
    except monthly_progress_service.MonthlyProgressError as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Form 3 - Justification for Project Delay
# ---------------------------------------------------------------------------

@monitoring_bp.route('/form3-requests', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_form3_requests():
    try:
        return success_response(data=form3_service.list_requests(
            project_id=request.args.get('project_id', type=int),
            reporting_period=request.args.get('reporting_period'),
            workflow_status=request.args.get('workflow_status'),
            user_id=get_jwt_identity(),
        ))
    except form3_service.Form3Error as exc:
        return _error(exc)


@monitoring_bp.route('/form3-requests', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def create_form3_request():
    data = request.get_json() if request.is_json else request.form.to_dict()
    data = data or {}
    upload = request.files.get('file')
    try:
        item = form3_service.create_request(
            data,
            user_id=get_jwt_identity(),
            upload=upload,
        )
        return success_response(
            data=form3_service._serialize_request(item),
            message='Form 3 request created successfully.',
            status_code=201,
        )
    except form3_service.Form3Error as exc:
        return _error(exc)


@monitoring_bp.route('/form3-requests/<int:request_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_form3_request(request_id):
    try:
        item = form3_service.get_request(request_id, user_id=get_jwt_identity())
        return success_response(data=form3_service._serialize_request(item))
    except form3_service.Form3Error as exc:
        return _error(exc)


@monitoring_bp.route('/form3-requests/<int:request_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_or_field_required
def update_form3_request(request_id):
    data = request.get_json() or {}
    try:
        item = form3_service.update_request(request_id, data, user_id=get_jwt_identity())
        return success_response(
            data=form3_service._serialize_request(item),
            message='Form 3 request updated successfully.',
        )
    except form3_service.Form3Error as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Project Exception Report
# ---------------------------------------------------------------------------

@monitoring_bp.route('/exception-reports', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_exception_reports():
    try:
        return success_response(data=project_exception_service.list_reports(
            project_id=request.args.get('project_id', type=int),
            reporting_period=request.args.get('reporting_period'),
            workflow_status=request.args.get('workflow_status'),
            user_id=get_jwt_identity(),
        ))
    except project_exception_service.ProjectExceptionError as exc:
        return _error(exc)


@monitoring_bp.route('/exception-reports', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def create_exception_report():
    data = request.get_json() if request.is_json else request.form.to_dict()
    data = data or {}
    upload = request.files.get('file')
    try:
        item = project_exception_service.create_report(
            data,
            user_id=get_jwt_identity(),
            upload=upload,
        )
        return success_response(
            data=project_exception_service._serialize_report(item),
            message='Project Exception Report created successfully.',
            status_code=201,
        )
    except project_exception_service.ProjectExceptionError as exc:
        return _error(exc)


@monitoring_bp.route('/exception-reports/<int:report_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_exception_report(report_id):
    try:
        item = project_exception_service.get_report(report_id, user_id=get_jwt_identity())
        return success_response(data=project_exception_service._serialize_report(item))
    except project_exception_service.ProjectExceptionError as exc:
        return _error(exc)


@monitoring_bp.route('/exception-reports/<int:report_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_or_field_required
def update_exception_report(report_id):
    data = request.get_json() or {}
    try:
        item = project_exception_service.update_report(report_id, data, user_id=get_jwt_identity())
        return success_response(
            data=project_exception_service._serialize_report(item),
            message='Project Exception Report updated successfully.',
        )
    except project_exception_service.ProjectExceptionError as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Management Action Report lifecycle
# ---------------------------------------------------------------------------

@monitoring_bp.route('/management-actions/<int:management_action_id>/submit', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def submit_management_action(management_action_id):
    data = request.get_json(silent=True) or {}
    try:
        action = monitoring_service.submit_management_action(
            management_action_id, user_id=get_jwt_identity(), note=data.get('note'),
        )
        return success_response(
            data=monitoring_service._serialize_management_action(action),
            message='Management Action Report submitted.',
        )
    except monitoring_service.MonitoringError as exc:
        return _error(exc)


@monitoring_bp.route('/management-actions/<int:management_action_id>/acknowledge', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def acknowledge_management_action(management_action_id):
    data = request.get_json(silent=True) or {}
    try:
        action = monitoring_service.acknowledge_management_action(
            management_action_id, user_id=get_jwt_identity(), note=data.get('note'),
        )
        return success_response(
            data=monitoring_service._serialize_management_action(action),
            message='Management Action Report acknowledged.',
        )
    except monitoring_service.MonitoringError as exc:
        return _error(exc)


@monitoring_bp.route('/management-actions/<int:management_action_id>/close', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def close_management_action(management_action_id):
    data = request.get_json(silent=True) or {}
    try:
        action = monitoring_service.close_management_action(
            management_action_id, user_id=get_jwt_identity(), note=data.get('note'),
        )
        return success_response(
            data=monitoring_service._serialize_management_action(action),
            message='Management Action Report closed.',
        )
    except monitoring_service.MonitoringError as exc:
        return _error(exc)


@monitoring_bp.route('/management-actions/cycle/<string:cycle_month>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def management_actions_for_cycle(cycle_month):
    try:
        return success_response(data=monitoring_service.list_management_actions_for_cycle(
            cycle_month, user_id=get_jwt_identity(),
        ))
    except monitoring_service.MonitoringError as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# V&V Queue (shared workflow queue)
# ---------------------------------------------------------------------------

@monitoring_bp.route('/workflow-queue', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def workflow_queue():
    role_view = request.args.get('role_view', 'staff')
    document_categories = request.args.getlist('document_category') or None
    try:
        return success_response(data=requirement_workflow_service.list_workflow_queue(
            role_view=role_view,
            document_categories=document_categories,
            user_id=get_jwt_identity(),
        ))
    except requirement_workflow_service.WorkflowError as exc:
        return _error(exc)


@monitoring_bp.route('/workflow-queue/counts', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def workflow_queue_counts():
    try:
        return success_response(data=requirement_workflow_service.get_workflow_queue_counts(
            user_id=get_jwt_identity(),
        ))
    except requirement_workflow_service.WorkflowError as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Configurable risk thresholds
# ---------------------------------------------------------------------------

@monitoring_bp.route('/risk-thresholds', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_risk_thresholds():
    return success_response(data=settings_service.get_risk_thresholds())


@monitoring_bp.route('/risk-thresholds', methods=['PUT'])
@jwt_required()
@admin_required
def update_risk_thresholds():
    data = request.get_json() or {}
    try:
        thresholds = settings_service.update_risk_thresholds(data, user_id=get_jwt_identity())
        return success_response(data=thresholds, message='Risk thresholds updated successfully.')
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)
