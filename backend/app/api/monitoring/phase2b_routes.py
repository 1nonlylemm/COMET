"""Phase 2B monitoring API routes.

Exposes Non-Infra Monitoring / APM Template records and Beneficiary
evidence records (Signed Distribution List, Acknowledgement Receipt,
Beneficiary Tracking Record, Turnover Photos, Delivery Invoice). Workflow
transitions (submit/verify/staff-approve/provincial-approve/return) reuse
the existing Phase 1 endpoints under
`/api/projects/requirements/<id>/workflow/*` via each record's
`project_requirement_id` -- no duplicate transition routes are added here,
matching the Phase 2A pattern exactly. System Administrators have no
operational access to these routes (enforced by
`admin_or_staff_or_field_required`, which excludes `system_admin`).
"""
from flask import request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models import Project
from app.services import appendix_template_catalog, beneficiary_evidence_service, non_infra_monitoring_service
from app.utils.auth import admin_or_staff_or_field_required, admin_or_staff_required
from app.utils.response import error_response, success_response

from . import monitoring_bp


def _error(exc):
    return error_response(exc.message, status_code=exc.status_code)


# ---------------------------------------------------------------------------
# Non-Infra Monitoring / APM Template
# ---------------------------------------------------------------------------

@monitoring_bp.route('/non-infra-monitoring-records', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_non_infra_monitoring_records():
    try:
        return success_response(data=non_infra_monitoring_service.list_records(
            project_id=request.args.get('project_id', type=int),
            template_type=request.args.get('template_type'),
            reporting_period=request.args.get('reporting_period'),
            workflow_status=request.args.get('workflow_status'),
            user_id=get_jwt_identity(),
        ))
    except non_infra_monitoring_service.NonInfraMonitoringError as exc:
        return _error(exc)


@monitoring_bp.route('/non-infra-monitoring-records', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def create_non_infra_monitoring_record():
    data = request.get_json() if request.is_json else request.form.to_dict()
    data = data or {}
    upload = request.files.get('file')
    try:
        record = non_infra_monitoring_service.create_record(
            data,
            user_id=get_jwt_identity(),
            upload=upload,
        )
        return success_response(
            data=non_infra_monitoring_service._serialize_record(record),
            message='Non-Infra Monitoring record created successfully.',
            status_code=201,
        )
    except non_infra_monitoring_service.NonInfraMonitoringError as exc:
        return _error(exc)


@monitoring_bp.route('/non-infra-monitoring-records/<int:record_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_non_infra_monitoring_record(record_id):
    try:
        record = non_infra_monitoring_service.get_record(record_id, user_id=get_jwt_identity())
        return success_response(data=non_infra_monitoring_service._serialize_record(record))
    except non_infra_monitoring_service.NonInfraMonitoringError as exc:
        return _error(exc)


@monitoring_bp.route('/non-infra-monitoring-records/<int:record_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_or_field_required
def update_non_infra_monitoring_record(record_id):
    data = request.get_json() or {}
    try:
        record = non_infra_monitoring_service.update_record(record_id, data, user_id=get_jwt_identity())
        return success_response(
            data=non_infra_monitoring_service._serialize_record(record),
            message='Non-Infra Monitoring record updated successfully.',
        )
    except non_infra_monitoring_service.NonInfraMonitoringError as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Beneficiary evidence (Signed Distribution List, Acknowledgement Receipt,
# Beneficiary Tracking Record, Turnover Photos, Delivery Invoice)
# ---------------------------------------------------------------------------

@monitoring_bp.route('/beneficiary-evidence-records', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_beneficiary_evidence_records():
    try:
        return success_response(data=beneficiary_evidence_service.list_records(
            project_id=request.args.get('project_id', type=int),
            evidence_type=request.args.get('evidence_type'),
            workflow_status=request.args.get('workflow_status'),
            user_id=get_jwt_identity(),
        ))
    except beneficiary_evidence_service.BeneficiaryEvidenceError as exc:
        return _error(exc)


@monitoring_bp.route('/beneficiary-evidence-records', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def create_beneficiary_evidence_record():
    data = request.get_json() if request.is_json else request.form.to_dict()
    data = data or {}
    upload = request.files.get('file')
    try:
        record = beneficiary_evidence_service.create_record(
            data,
            user_id=get_jwt_identity(),
            upload=upload,
        )
        return success_response(
            data=beneficiary_evidence_service._serialize_record(record),
            message='Beneficiary evidence record created successfully.',
            status_code=201,
        )
    except beneficiary_evidence_service.BeneficiaryEvidenceError as exc:
        return _error(exc)


@monitoring_bp.route('/beneficiary-evidence-records/<int:record_id>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_beneficiary_evidence_record(record_id):
    try:
        record = beneficiary_evidence_service.get_record(record_id, user_id=get_jwt_identity())
        return success_response(data=beneficiary_evidence_service._serialize_record(record))
    except beneficiary_evidence_service.BeneficiaryEvidenceError as exc:
        return _error(exc)


@monitoring_bp.route('/beneficiary-evidence-records/<int:record_id>', methods=['PUT'])
@jwt_required()
@admin_or_staff_or_field_required
def update_beneficiary_evidence_record(record_id):
    data = request.get_json() or {}
    try:
        record = beneficiary_evidence_service.update_record(record_id, data, user_id=get_jwt_identity())
        return success_response(
            data=beneficiary_evidence_service._serialize_record(record),
            message='Beneficiary evidence record updated successfully.',
        )
    except beneficiary_evidence_service.BeneficiaryEvidenceError as exc:
        return _error(exc)


# ---------------------------------------------------------------------------
# Appendix Templates Catalog & Download (Appendices 1-19)
# ---------------------------------------------------------------------------

@monitoring_bp.route('/templates/appendices', methods=['GET'])
@jwt_required()
def list_appendix_templates():
    project_id = request.args.get('project_id', type=int)
    project_kind = request.args.get('project_kind')
    if project_id and not project_kind:
        project = Project.query.get(project_id)
        if project and project.project_kind:
            project_kind = project.project_kind

    templates = appendix_template_catalog.list_appendix_templates(project_kind=project_kind)
    return success_response(data=templates)


@monitoring_bp.route('/templates/appendices/<int:appendix_number>/download', methods=['GET'])
@jwt_required()
def download_appendix_template(appendix_number):
    item = appendix_template_catalog.get_appendix_by_number(appendix_number)
    if not item:
        return error_response(f'Appendix {appendix_number} template not found.', status_code=404)

    file_path = appendix_template_catalog.get_appendix_file_path(appendix_number)
    if not file_path or not file_path.exists():
        return error_response(f'Template file for Appendix {appendix_number} is not available.', status_code=404)

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=item['filename'],
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
