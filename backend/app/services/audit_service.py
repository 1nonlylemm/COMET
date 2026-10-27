"""Audit Trail service layer.

Provides CRUD, filtering, chain integrity verification, and statistics
for the hash-linked AuditLog entries.
"""

from datetime import datetime, timedelta, timezone
from flask import request as flask_request
from app.extensions import db
from app.models import AuditIntegrityCheckpoint, AuditIntegrityIncident, AuditLog
from app.utils.datetime import to_iso_utc
from app.utils.hash_audit import build_audit_entry, compute_record_hash, verify_chain_integrity


class AuditError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Serialisation ────────────────────────────────────────────────────────────

REDACTED_AUDIT_VALUE = "[redacted]"

SENSITIVE_AUDIT_KEY_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "authorization",
    "authorization_header",
    "bearer_token",
    "client_secret",
    "credential",
    "credentials",
    "csrf_token",
    "current_password",
    "jwt",
    "jwt_secret",
    "new_password",
    "oauth_state",
    "oauth_token",
    "password",
    "password_hash",
    "private_key",
    "refresh_token",
    "secret",
    "secret_key",
    "smtp_password",
    "state",
    "temporary_password",
    "token",
}

SENSITIVE_AUDIT_KEY_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_auth_token",
    "_client_secret",
    "_credential",
    "_credentials",
    "_password",
    "_private_key",
    "_refresh_token",
    "_secret",
    "_secret_key",
    "_token",
)

TOKEN_URL_KEYS = {"url", "magic_link_url", "public_url"}


def _normalize_audit_key(key):
    return str(key or "").strip().lower().replace("-", "_")


def _is_sensitive_audit_key(key):
    normalized = _normalize_audit_key(key)
    compact = normalized.replace("_", "")
    return (
        normalized in SENSITIVE_AUDIT_KEY_NAMES
        or compact in SENSITIVE_AUDIT_KEY_NAMES
        or any(normalized.endswith(suffix) for suffix in SENSITIVE_AUDIT_KEY_SUFFIXES)
    )


def _redact_sensitive_audit_value(value):
    if isinstance(value, dict):
        has_direct_token = any(_normalize_audit_key(key) == "token" for key in value.keys())
        redacted = {}
        for key, item in value.items():
            normalized_key = _normalize_audit_key(key)
            if _is_sensitive_audit_key(key) or (has_direct_token and normalized_key in TOKEN_URL_KEYS):
                redacted[key] = REDACTED_AUDIT_VALUE
            else:
                redacted[key] = _redact_sensitive_audit_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_audit_value(item) for item in value]
    return value


def _serialize_audit_log(log):
    return {
        "id": log.id,
        "user_id": log.user_id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "old_value": _redact_sensitive_audit_value(log.old_value),
        "new_value": _redact_sensitive_audit_value(log.new_value),
        "record_hash": log.record_hash,
        "previous_hash": log.previous_hash,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "created_at": to_iso_utc(log.created_at),
        "user_email": log.actor.email if log.actor else None,
        "user_name": f"{log.actor.first_name} {log.actor.last_name}".strip() if log.actor else None,
    }


def _mismatch_type_from_broken_at(broken_at):
    if not broken_at:
        return "unknown"
    if "expected_hash" in broken_at or "actual_hash" in broken_at:
        return "record_hash_mismatch"
    if "expected_previous_hash" in broken_at or "actual_previous_hash" in broken_at:
        return "previous_hash_mismatch"
    return "unknown"


def _serialize_integrity_checkpoint(checkpoint):
    if not checkpoint:
        return None
    creator = checkpoint.creator
    return {
        "id": checkpoint.id,
        "incident_id": checkpoint.incident_id,
        "checkpoint_audit_log_id": checkpoint.checkpoint_audit_log_id,
        "checkpoint_hash": checkpoint.checkpoint_hash,
        "reason": checkpoint.reason,
        "created_by": checkpoint.created_by,
        "created_by_name": creator.full_name if creator else None,
        "created_at": to_iso_utc(checkpoint.created_at),
    }


def _serialize_integrity_incident(incident):
    if not incident:
        return None
    opener = incident.opener
    resolver = incident.resolver
    latest_checkpoint = (
        incident.checkpoints.order_by(AuditIntegrityCheckpoint.created_at.desc()).first()
        if incident.id else None
    )
    return {
        "id": incident.id,
        "status": incident.status,
        "broken_at_id": incident.broken_at_id,
        "mismatch_type": incident.mismatch_type,
        "expected_hash": incident.expected_hash,
        "actual_hash": incident.actual_hash,
        "expected_previous_hash": incident.expected_previous_hash,
        "actual_previous_hash": incident.actual_previous_hash,
        "opened_by": incident.opened_by,
        "opened_by_name": opener.full_name if opener else None,
        "opened_at": to_iso_utc(incident.opened_at),
        "investigation_notes": incident.investigation_notes,
        "resolution_type": incident.resolution_type,
        "resolution_notes": incident.resolution_notes,
        "resolved_by": incident.resolved_by,
        "resolved_by_name": resolver.full_name if resolver else None,
        "resolved_at": to_iso_utc(incident.resolved_at),
        "latest_checkpoint": _serialize_integrity_checkpoint(latest_checkpoint),
    }


def _coerce_user_id(user_id):
    if user_id is None:
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise AuditError("User ID must be an integer", status_code=422)


# ── Create (log an action) ──────────────────────────────────────────────────

def log_action(user_id, action, entity_type, entity_id, old_value=None, new_value=None, commit=True):
    """Create an audit log entry with hash-chain integrity."""
    user_id = _coerce_user_id(user_id)
    ip_address = None
    user_agent = None
    try:
        ip_address = flask_request.remote_addr
        user_agent = flask_request.headers.get("User-Agent", "")[:500] if flask_request else None
    except RuntimeError:
        pass  # Outside request context

    entry_data = build_audit_entry(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    log = AuditLog(**entry_data)
    db.session.add(log)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return log


def log_security_event(user_id, action, entity_type=None, entity_id=None, details=None, commit=True):
    """Log an authorization or scope security failure to the hash-linked audit trail.

    Treated as fail-safe (fail-open for error handling) to ensure that audit logging failures
    never mask or disrupt the original authorization rejection or crash the application.
    """
    try:
        user_id = _coerce_user_id(user_id) if user_id is not None else None
        return log_action(
            user_id=user_id,
            action=action,
            entity_type=entity_type or 'security_boundary',
            entity_id=entity_id if entity_id is not None else 0,
            old_value=None,
            new_value=details or {},
            commit=commit,
        )
    except Exception as exc:
        import logging
        logging.getLogger('comet.security').warning(f"Failed to record security audit log: {exc}")
        return None


COMMON_CRUD_ACTIONS = frozenset({"create", "update", "delete", "status_change", "approve"})

APPROVED_BUSINESS_AUDIT_ACTIONS = {
    "project": COMMON_CRUD_ACTIONS | frozenset({"change_project_kind", "reconcile_requirements"}),
    "project_requirement": COMMON_CRUD_ACTIONS | frozenset({
        "return_for_revision",
        "workflow_submit",
        "workflow_resubmit",
        "workflow_verify",
        "workflow_staff_approve",
        "workflow_provincial_approve",
        "workflow_return_for_revision",
    }),
    "requirement": COMMON_CRUD_ACTIONS | frozenset({"verify"}),
    "submission": COMMON_CRUD_ACTIONS | frozenset({"reassign_submission", "workflow_submit"}),
    "requirement_deficiency": COMMON_CRUD_ACTIONS | frozenset({"deficiency_resolved", "deficiency_waived"}),
    "requirement_workflow_transition": COMMON_CRUD_ACTIONS,
    "user": frozenset({"create", "update", "login", "logout"}),
    "user_scope_assignment": COMMON_CRUD_ACTIONS | frozenset({"toggle_active"}),
    "staff_lgu_assignment": COMMON_CRUD_ACTIONS,
    "lgu": COMMON_CRUD_ACTIONS | frozenset({"toggle_active"}),
    "lgu_profile": COMMON_CRUD_ACTIONS | frozenset({"toggle_active"}),
    "lgu_cluster": COMMON_CRUD_ACTIONS,
    "program": COMMON_CRUD_ACTIONS | frozenset({"toggle_active", "archive"}),
    "program_cycle": COMMON_CRUD_ACTIONS | frozenset({"clone"}),
    "program_phase": COMMON_CRUD_ACTIONS,
    "escalation_notice": COMMON_CRUD_ACTIONS | frozenset({"generate", "release", "receipt", "dispatch"}),
    "sla_deadline": COMMON_CRUD_ACTIONS | frozenset({"resolve", "escalate"}),
    "change_status_request": COMMON_CRUD_ACTIONS | frozenset({"review"}),
    "beneficiary_record": COMMON_CRUD_ACTIONS,
    "beneficiary_evidence_record": COMMON_CRUD_ACTIONS,
    "qaar_inspection": COMMON_CRUD_ACTIONS,
    "completion_milestone": COMMON_CRUD_ACTIONS | frozenset({"final_swa_applicability_changed", "project_reopened"}),
    "completion_document_record": COMMON_CRUD_ACTIONS | frozenset({"update_metadata", "applicability_changed"}),
    "generated_report": COMMON_CRUD_ACTIONS | frozenset({"generate_report"}),
    "document": COMMON_CRUD_ACTIONS,
    "document_file": COMMON_CRUD_ACTIONS,
    "document_compliance_result": frozenset({
        "create", "update", "document_compliance_check", "review_document_compliance_result",
    }),
    "document_reference_profile": frozenset({
        "create", "update", "create_document_reference_profile", "update_document_reference_profile",
    }),
    "nlp_scan_result": frozenset({
        "create", "update", "document_intelligence_scan", "review_document_intelligence_scan",
    }),
    "notice": COMMON_CRUD_ACTIONS | frozenset({"send"}),
    "handoff": COMMON_CRUD_ACTIONS,
    "workbook": COMMON_CRUD_ACTIONS,
    "workbook_workspace": COMMON_CRUD_ACTIONS,
    "workbook_column": frozenset({"update_column_editability"}),
    "monitoring_entry": COMMON_CRUD_ACTIONS,
    "non_infra_monitoring": COMMON_CRUD_ACTIONS,
    "non_infra_monitoring_record": COMMON_CRUD_ACTIONS,
    "communication_log": COMMON_CRUD_ACTIONS,
    "workflow_comment": COMMON_CRUD_ACTIONS | frozenset({"comment"}),
    "monthly_progress_report": COMMON_CRUD_ACTIONS,
    "form3_request": COMMON_CRUD_ACTIONS,
    "project_exception_report": COMMON_CRUD_ACTIONS,
    "import_batch": frozenset({"upload", "map", "confirm_mapping_decisions", "preview", "commit"}),
    "import_template": COMMON_CRUD_ACTIONS | frozenset({"clone"}),
    "program_guideline": COMMON_CRUD_ACTIONS,
    "management_action_report": COMMON_CRUD_ACTIONS | frozenset({
        "upsert",
        "mar_auto_generated",
        "mar_submit",
        "mar_acknowledge",
        "mar_close",
    }),
    "subaybayan_verification": frozenset({"upsert"}),
    "project_monitoring_profile": frozenset({"update"}),
    "bulk_project_operation": frozenset({
        "bulk_update_project_status",
        "bulk_update_project_metadata",
        "bulk_update_project_schedule",
    }),
    "google_drive_push": frozenset({"create"}),
}

BUSINESS_AUDIT_ENTITY_TYPES = tuple(APPROVED_BUSINESS_AUDIT_ACTIONS.keys())

TECHNICAL_AUDIT_ACTIONS = (
    "unauthorized_role_access",
    "rebaseline",
    "integrity_rebaseline",
    "integrity_incident_opened",
)


def _business_audit_filter_clause():
    """Build a SQLAlchemy boolean clause matching approved (entity_type, action) pairs."""
    clauses = [
        db.and_(
            AuditLog.entity_type == entity_type,
            AuditLog.action.in_(actions),
        )
        for entity_type, actions in APPROVED_BUSINESS_AUDIT_ACTIONS.items()
    ]
    return db.or_(*clauses)


def is_business_audit_action(action):
    """Check if an action is an approved business audit action for any business entity."""
    if not action:
        return False
    return any(action in actions for actions in APPROVED_BUSINESS_AUDIT_ACTIONS.values())


def is_business_audit_entry(entity_type, action=None):
    """Check if an entity type and action represent legitimate operational business history."""
    if not entity_type or entity_type not in APPROVED_BUSINESS_AUDIT_ACTIONS:
        return False
    allowed_actions = APPROVED_BUSINESS_AUDIT_ACTIONS[entity_type]
    if action is not None:
        return action in allowed_actions
    return bool(allowed_actions)


# ── Read ─────────────────────────────────────────────────────────────────────

def get_audit_log(log_id, is_system_admin=True):
    log = db.session.get(AuditLog, log_id)
    if not log:
        raise AuditError("Audit log entry not found", status_code=404)
    if not is_system_admin and not is_business_audit_entry(log.entity_type, log.action):
        raise AuditError(
            "Access to technical administration audit records is restricted to System Admin.",
            status_code=403,
        )
    return log


def list_audit_logs(
    entity_type=None,
    entity_id=None,
    user_id=None,
    action=None,
    start_date=None,
    end_date=None,
    search=None,
    page=1,
    per_page=20,
    is_system_admin=True,
):
    """List audit logs with filtering and pagination."""
    if not is_system_admin:
        if entity_type and not is_business_audit_entry(entity_type, action):
            raise AuditError(
                "Access to technical administration audit records is restricted to System Admin.",
                status_code=403,
            )
        if action and not is_business_audit_action(action):
            raise AuditError(
                "Access to technical administration audit records is restricted to System Admin.",
                status_code=403,
            )

    query = AuditLog.query

    if not is_system_admin:
        if entity_type:
            allowed_actions = APPROVED_BUSINESS_AUDIT_ACTIONS.get(entity_type, frozenset())
            query = query.filter(
                AuditLog.entity_type == entity_type,
                AuditLog.action.in_(allowed_actions),
            )
        else:
            query = query.filter(_business_audit_filter_clause())
    elif entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(AuditLog.entity_id == entity_id)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            start_dt = None
        if start_dt:
            query = query.filter(AuditLog.created_at >= start_dt)
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            end_dt = None
        if end_dt:
            query = query.filter(AuditLog.created_at <= end_dt)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                AuditLog.action.ilike(search_term),
                AuditLog.entity_type.ilike(search_term),
            )
        )

    query = query.order_by(AuditLog.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return {
        "logs": paginated.items,
        "total": paginated.total,
        "page": paginated.page,
        "per_page": paginated.per_page,
        "pages": paginated.pages,
    }


# ── Statistics ────────────────────────────────────────────────────────────────

def get_audit_stats(is_system_admin=True):
    """Return aggregate statistics for the audit dashboard."""
    base_query = AuditLog.query
    filter_clause = None if is_system_admin else _business_audit_filter_clause()
    if filter_clause is not None:
        base_query = base_query.filter(filter_clause)

    total = base_query.count()

    # Counts by action type
    action_query = db.session.query(AuditLog.action, db.func.count(AuditLog.id))
    if filter_clause is not None:
        action_query = action_query.filter(filter_clause)
    action_counts = dict(action_query.group_by(AuditLog.action).all())

    # Counts by entity type
    entity_query = db.session.query(AuditLog.entity_type, db.func.count(AuditLog.id))
    if filter_clause is not None:
        entity_query = entity_query.filter(filter_clause)
    entity_counts = dict(entity_query.group_by(AuditLog.entity_type).all())

    # Recent activity (last 24 hours)
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_query = base_query.filter(AuditLog.created_at >= since)
    recent_count = recent_query.count()

    # Top users
    top_users_query = db.session.query(AuditLog.user_id, db.func.count(AuditLog.id))
    if filter_clause is not None:
        top_users_query = top_users_query.filter(filter_clause)
    top_users = dict(
        top_users_query.group_by(AuditLog.user_id)
        .order_by(db.func.count(AuditLog.id).desc())
        .limit(10)
        .all()
    )

    # Unique actors count
    unique_users_query = db.session.query(db.func.count(db.func.distinct(AuditLog.user_id)))
    if filter_clause is not None:
        unique_users_query = unique_users_query.filter(filter_clause)
    unique_users = unique_users_query.scalar() or 0

    return {
        "total": total,
        "action_counts": action_counts,
        "entity_counts": entity_counts,
        "recent_count_24h": recent_count,
        "unique_users": unique_users,
        "top_users": {str(k): v for k, v in top_users.items()},
    }


# ── Chain Integrity ─────────────────────────────────────────────────────────

def _latest_integrity_checkpoint():
    return (
        AuditIntegrityCheckpoint.query
        .order_by(AuditIntegrityCheckpoint.created_at.desc(), AuditIntegrityCheckpoint.id.desc())
        .first()
    )


def _verify_from_checkpoint(checkpoint):
    if not checkpoint:
        return None

    logs = (
        AuditLog.query
        .filter(AuditLog.id > (checkpoint.checkpoint_audit_log_id or 0))
        .order_by(AuditLog.id.asc())
        .all()
    )
    expected_prev = checkpoint.checkpoint_hash
    for log in logs:
        if log.previous_hash != expected_prev:
            return {
                "is_valid": False,
                "total_entries": len(logs),
                "checkpoint": _serialize_integrity_checkpoint(checkpoint),
                "broken_at": {
                    "broken_at_id": log.id,
                    "expected_previous_hash": expected_prev,
                    "actual_previous_hash": log.previous_hash,
                },
            }

        expected_hash = compute_record_hash(
            user_id=log.user_id,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            previous_hash=log.previous_hash,
            created_at=log.created_at,
            old_value=log.old_value,
            new_value=log.new_value,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
        )
        if log.record_hash != expected_hash:
            return {
                "is_valid": False,
                "total_entries": len(logs),
                "checkpoint": _serialize_integrity_checkpoint(checkpoint),
                "broken_at": {
                    "broken_at_id": log.id,
                    "expected_hash": expected_hash,
                    "actual_hash": log.record_hash,
                },
            }
        expected_prev = log.record_hash

    return {
        "is_valid": True,
        "total_entries": len(logs),
        "checkpoint": _serialize_integrity_checkpoint(checkpoint),
        "broken_at": None,
    }


def verify_audit_chain():
    """Verify the full hash-chain integrity of all audit log entries."""
    logs = AuditLog.query.order_by(AuditLog.id.asc()).all()
    is_valid, broken_at = verify_chain_integrity(logs)
    active_incident = get_active_integrity_incident()
    latest_checkpoint = _latest_integrity_checkpoint()
    return {
        "is_valid": is_valid,
        "total_entries": len(logs),
        "broken_at": broken_at,
        "active_incident": _serialize_integrity_incident(active_incident),
        "latest_checkpoint": _serialize_integrity_checkpoint(latest_checkpoint),
        "post_checkpoint": _verify_from_checkpoint(latest_checkpoint),
    }


def list_integrity_incidents(status=None):
    query = AuditIntegrityIncident.query
    if status:
        query = query.filter(AuditIntegrityIncident.status == status)
    return query.order_by(AuditIntegrityIncident.opened_at.desc(), AuditIntegrityIncident.id.desc()).all()


def get_active_integrity_incident():
    return (
        AuditIntegrityIncident.query
        .filter(AuditIntegrityIncident.status == "open")
        .order_by(AuditIntegrityIncident.opened_at.desc(), AuditIntegrityIncident.id.desc())
        .first()
    )


def open_integrity_incident(user_id, notes=None):
    """Create an operator incident for the current chain break."""
    user_id = _coerce_user_id(user_id)
    verification = verify_audit_chain()
    if verification["is_valid"]:
        raise AuditError("Audit chain is currently valid. No integrity incident is needed.", status_code=409)

    post_checkpoint = verification.get("post_checkpoint")
    if post_checkpoint:
        if post_checkpoint.get("is_valid"):
            raise AuditError(
                "The historical chain break is already covered by a rebaseline checkpoint.",
                status_code=409,
            )
        broken_at = post_checkpoint.get("broken_at") or verification.get("broken_at") or {}
    else:
        broken_at = verification.get("broken_at") or {}

    active = get_active_integrity_incident()
    if active:
        if active.broken_at_id == broken_at.get("broken_at_id"):
            raise AuditError("An open integrity incident already exists for this chain break.", status_code=409)
        raise AuditError("Resolve the existing open integrity incident before opening another one.", status_code=409)

    incident = AuditIntegrityIncident(
        status="open",
        broken_at_id=broken_at.get("broken_at_id"),
        mismatch_type=_mismatch_type_from_broken_at(broken_at),
        expected_hash=broken_at.get("expected_hash"),
        actual_hash=broken_at.get("actual_hash"),
        expected_previous_hash=broken_at.get("expected_previous_hash"),
        actual_previous_hash=broken_at.get("actual_previous_hash"),
        opened_by=user_id,
        investigation_notes=(notes or "").strip() or None,
    )
    db.session.add(incident)
    db.session.flush()

    log_action(
        user_id=user_id,
        action="integrity_incident_opened",
        entity_type="audit_integrity_incident",
        entity_id=incident.id,
        new_value=_serialize_integrity_incident(incident),
        commit=False,
    )
    db.session.commit()
    return incident


def rebaseline_integrity_incident(incident_id, user_id, notes):
    """Mark the current audit tail as the new checkpoint for future writes."""
    user_id = _coerce_user_id(user_id)
    notes = (notes or "").strip()
    if not notes:
        raise AuditError("Rebaseline notes are required.", status_code=422)

    incident = db.session.get(AuditIntegrityIncident, incident_id)
    if not incident:
        raise AuditError("Integrity incident not found", status_code=404)
    if incident.status != "open":
        raise AuditError("Only open integrity incidents can be rebaselined.", status_code=409)

    latest_log = AuditLog.query.order_by(AuditLog.id.desc()).first()
    if not latest_log:
        raise AuditError("Cannot rebaseline an empty audit log.", status_code=409)

    checkpoint = AuditIntegrityCheckpoint(
        incident_id=incident.id,
        checkpoint_audit_log_id=latest_log.id,
        checkpoint_hash=latest_log.record_hash,
        reason=notes,
        created_by=user_id,
    )
    db.session.add(checkpoint)
    incident.status = "rebaselined"
    incident.resolution_type = "rebaselined"
    incident.resolution_notes = notes
    incident.resolved_by = user_id
    incident.resolved_at = datetime.now(timezone.utc)
    db.session.flush()

    log_action(
        user_id=user_id,
        action="integrity_rebaseline",
        entity_type="audit_integrity_incident",
        entity_id=incident.id,
        old_value={
            "status": "open",
            "broken_at_id": incident.broken_at_id,
        },
        new_value={
            "status": incident.status,
            "resolution_type": incident.resolution_type,
            "checkpoint_audit_log_id": checkpoint.checkpoint_audit_log_id,
            "checkpoint_hash": checkpoint.checkpoint_hash,
            "reason": notes,
        },
        commit=False,
    )
    db.session.commit()
    return incident, checkpoint


# ── Entity Timeline ─────────────────────────────────────────────────────────

def get_entity_timeline(entity_type, entity_id, is_system_admin=True):
    """Get the full audit timeline for a specific entity."""
    if not is_system_admin and not is_business_audit_entry(entity_type):
        raise AuditError(
            "Access denied: Technical audit logs are restricted to System Administrators.",
            status_code=403,
        )
    query = AuditLog.query.filter(
        AuditLog.entity_type == entity_type,
        AuditLog.entity_id == entity_id,
    )
    if not is_system_admin:
        allowed_actions = APPROVED_BUSINESS_AUDIT_ACTIONS.get(entity_type, frozenset())
        query = query.filter(AuditLog.action.in_(allowed_actions))
    logs = query.order_by(AuditLog.created_at.asc()).all()
    return logs
