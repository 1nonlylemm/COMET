"""Validation schemas for Audit Trail API endpoints."""

from datetime import datetime, timezone


VALID_ENTITY_TYPES = [
    "user", "lgu_profile", "lgu_cluster", "program", "program_phase",
    "requirement", "project", "project_requirement", "submission",
    "requirement_deficiency", "requirement_workflow_transition",
    "sla_deadline", "escalation_notice", "change_status_request",
    "generated_report", "system_config", "beneficiary_record",
    "qaar_inspection", "completion_milestone", "staff_lgu_assignment",
    "user_scope_assignment",
]

VALID_ACTIONS = [
    "create", "update", "delete", "status_change", "resolve",
    "approve", "reject", "escalate", "login", "logout",
    "generate_report", "upload", "download",
    "change_password", "toggle_active", "change_role",
    "workflow_submit", "workflow_verify", "workflow_staff_approve",
    "workflow_provincial_approve", "workflow_return_for_revision",
    "workflow_resubmit", "deficiency_resolved", "deficiency_waived",
]


def validate_audit_log_list(params):
    """Validate query parameters for listing audit logs."""
    errors = {}

    if params.get("entity_type") and params["entity_type"] not in VALID_ENTITY_TYPES:
        # Allow partial matches / custom types — don't block, just note
        pass

    if params.get("action") and params["action"] not in VALID_ACTIONS:
        pass  # same: allow pass-through

    page = params.get("page", 1)
    per_page = params.get("per_page", 20)

    try:
        page = int(page)
        if page < 1:
            errors["page"] = "Page must be >= 1"
    except (ValueError, TypeError):
        errors["page"] = "Page must be a positive integer"

    try:
        per_page = int(per_page)
        if per_page < 1 or per_page > 100:
            errors["per_page"] = "Per page must be between 1 and 100"
    except (ValueError, TypeError):
        errors["per_page"] = "Per page must be a positive integer"

    if params.get("start_date"):
        try:
            datetime.fromisoformat(params["start_date"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            errors["start_date"] = "Invalid start_date format. Use ISO 8601."

    if params.get("end_date"):
        try:
            datetime.fromisoformat(params["end_date"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            errors["end_date"] = "Invalid end_date format. Use ISO 8601."

    return errors if errors else None


def validate_audit_log_create(data):
    """Validate data for creating an audit log entry."""
    errors = {}

    if not data:
        errors["data"] = "No data provided"
        return errors

    if not data.get("action"):
        errors["action"] = "Action is required"
    elif data["action"] not in VALID_ACTIONS:
        # Allow custom actions too, but warn
        pass

    if not data.get("entity_type"):
        errors["entity_type"] = "Entity type is required"

    if data.get("entity_id") is None:
        errors["entity_id"] = "Entity ID is required"
    else:
        try:
            int(data["entity_id"])
        except (ValueError, TypeError):
            errors["entity_id"] = "Entity ID must be an integer"

    return errors if errors else None


def validate_integrity_incident_open(data):
    """Validate optional investigation notes when opening an integrity incident."""
    errors = {}
    data = data or {}
    notes = data.get("notes")
    if notes is not None and len(str(notes)) > 4000:
        errors["notes"] = "Notes must be 4000 characters or fewer"
    return errors if errors else None


def validate_integrity_rebaseline(data):
    """Validate required rebaseline notes."""
    errors = {}
    if not data:
        return {"notes": "Rebaseline notes are required"}
    notes = str(data.get("notes") or "").strip()
    if not notes:
        errors["notes"] = "Rebaseline notes are required"
    elif len(notes) > 4000:
        errors["notes"] = "Notes must be 4000 characters or fewer"
    return errors if errors else None
