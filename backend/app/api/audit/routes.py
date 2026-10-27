"""Audit Trail API routes.

Endpoints:
  GET  /audit/logs           -- List/filter audit logs (paginated, admin only)
  GET  /audit/logs/<id>      -- Get single audit log entry (admin only)
  GET  /audit/stats           -- Aggregate audit statistics (admin only)
  GET  /audit/verify-chain    -- Verify hash-chain integrity (admin only)
  GET  /audit/timeline/<type>/<id>  -- Entity audit timeline (admin only)
  POST /audit/logs           -- Disabled; audit entries are system generated
"""

from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.utils.auth import (
    admin_required,
    system_admin_required,
    system_admin_or_admin_required,
    step_up_required,
    _get_live_authenticated_user,
)
from app.constants.roles import SYSTEM_ADMIN
from app.services import audit_service
from app.utils.response import (
    success_response, error_response, not_found_error, validation_error,
)
from app.api.audit.schemas import (
    validate_audit_log_list,
    validate_integrity_incident_open,
    validate_integrity_rebaseline,
)

from . import audit_bp


def _is_caller_system_admin():
    user, error = _get_live_authenticated_user()
    if error or not user:
        return False
    return user.role == SYSTEM_ADMIN


# ── Audit Statistics ─────────────────────────────────────────────────────────

@audit_bp.route('/stats', methods=['GET'])
@jwt_required()
@system_admin_or_admin_required
def audit_stats():
    try:
        data = audit_service.get_audit_stats(is_system_admin=_is_caller_system_admin())
        return success_response(data=data)
    except audit_service.AuditError as e:
        return error_response(e.message, status_code=e.status_code)


# ── List Audit Logs ─────────────────────────────────────────────────────────

@audit_bp.route('/logs', methods=['GET'])
@jwt_required()
@system_admin_or_admin_required
def list_audit_logs():
    params = {
        "entity_type": request.args.get("entity_type"),
        "entity_id": request.args.get("entity_id", type=int),
        "user_id": request.args.get("user_id", type=int),
        "action": request.args.get("action"),
        "start_date": request.args.get("start_date"),
        "end_date": request.args.get("end_date"),
        "search": request.args.get("search"),
        "page": request.args.get("page", 1),
        "per_page": request.args.get("per_page", 20),
    }

    errors = validate_audit_log_list(params)
    if errors:
        return validation_error(errors)

    try:
        result = audit_service.list_audit_logs(
            entity_type=params.get("entity_type"),
            entity_id=params.get("entity_id"),
            user_id=params.get("user_id"),
            action=params.get("action"),
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
            search=params.get("search"),
            page=int(params.get("page", 1)),
            per_page=int(params.get("per_page", 20)),
            is_system_admin=_is_caller_system_admin(),
        )
        return success_response(
            data=[audit_service._serialize_audit_log(l) for l in result["logs"]],
            meta={
                "page": result["page"],
                "per_page": result["per_page"],
                "total": result["total"],
                "pages": result["pages"],
            },
        )
    except audit_service.AuditError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Get Single Audit Log ────────────────────────────────────────────────────

@audit_bp.route('/logs/<int:log_id>', methods=['GET'])
@jwt_required()
@system_admin_or_admin_required
def get_audit_log(log_id):
    try:
        log = audit_service.get_audit_log(log_id, is_system_admin=_is_caller_system_admin())
        return success_response(data=audit_service._serialize_audit_log(log))
    except audit_service.AuditError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Create Audit Log (Manual Log) ──────────────────────────────────────────

@audit_bp.route('/logs', methods=['POST'])
@jwt_required()
@admin_required
def create_audit_log():
    return error_response("Manual audit log creation is disabled.", status_code=403)


# ── Verify Chain Integrity ─────────────────────────────────────────────────

@audit_bp.route('/verify-chain', methods=['GET'])
@jwt_required()
@system_admin_or_admin_required
def verify_chain():
    try:
        result = audit_service.verify_audit_chain()
        return success_response(data=result)
    except audit_service.AuditError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Integrity Incident Workflow ─────────────────────────────────────────────

@audit_bp.route('/integrity-incidents', methods=['GET'])
@jwt_required()
@system_admin_or_admin_required
def list_integrity_incidents():
    try:
        incidents = audit_service.list_integrity_incidents(status=request.args.get("status"))
        return success_response(
            data=[audit_service._serialize_integrity_incident(i) for i in incidents],
        )
    except audit_service.AuditError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Integrity Incident Actions (Mutations) ─────────────────────────────────

@audit_bp.route('/integrity-incidents/open', methods=['POST'])
@jwt_required()
@system_admin_required
@step_up_required
def open_integrity_incident():
    payload = request.get_json(silent=True) or {}
    errors = validate_integrity_incident_open(payload)
    if errors:
        return validation_error(errors)

    try:
        incident = audit_service.open_integrity_incident(
            user_id=get_jwt_identity(),
            notes=payload.get("notes"),
        )
        return success_response(
            data=audit_service._serialize_integrity_incident(incident),
            message="Integrity incident opened.",
            status_code=201,
        )
    except audit_service.AuditError as e:
        return error_response(e.message, status_code=e.status_code)


@audit_bp.route('/integrity-incidents/<int:incident_id>/rebaseline', methods=['POST'])
@jwt_required()
@system_admin_required
@step_up_required
def rebaseline_integrity_incident(incident_id):
    payload = request.get_json(silent=True) or {}
    errors = validate_integrity_rebaseline(payload)
    if errors:
        return validation_error(errors)

    try:
        incident, checkpoint = audit_service.rebaseline_integrity_incident(
            incident_id=incident_id,
            user_id=get_jwt_identity(),
            notes=payload.get("notes"),
        )
        return success_response(
            data={
                "incident": audit_service._serialize_integrity_incident(incident),
                "checkpoint": audit_service._serialize_integrity_checkpoint(checkpoint),
            },
            message="Integrity rebaseline checkpoint created.",
        )
    except audit_service.AuditError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Entity Timeline ────────────────────────────────────────────────────────

@audit_bp.route('/timeline/<entity_type>/<int:entity_id>', methods=['GET'])
@jwt_required()
@system_admin_or_admin_required
def entity_timeline(entity_type, entity_id):
    try:
        logs = audit_service.get_entity_timeline(
            entity_type,
            entity_id,
            is_system_admin=_is_caller_system_admin(),
        )
        return success_response(
            data=[audit_service._serialize_audit_log(l) for l in logs],
        )
    except audit_service.AuditError as e:
        return error_response(e.message, status_code=e.status_code)
