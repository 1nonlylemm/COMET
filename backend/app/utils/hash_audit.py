import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal


GENESIS_HASH = "0" * 64


def _canonicalize_timestamp(created_at):
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)
    return created_at.isoformat()


def _normalize_value(value):
    if isinstance(value, datetime):
        return _canonicalize_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, set):
        normalized_items = [_normalize_value(item) for item in value]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    return value


def _build_hash_payload(
    user_id,
    action,
    entity_type,
    entity_id,
    previous_hash,
    created_at,
    old_value=None,
    new_value=None,
    ip_address=None,
    user_agent=None,
):
    payload = {
        "user_id": user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "old_value": _normalize_value(old_value),
        "new_value": _normalize_value(new_value),
        "previous_hash": previous_hash,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": _canonicalize_timestamp(created_at),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_record_hash(
    user_id,
    action,
    entity_type,
    entity_id,
    previous_hash,
    created_at,
    old_value=None,
    new_value=None,
    ip_address=None,
    user_agent=None,
):
    payload = _build_hash_payload(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_hash=previous_hash,
        created_at=created_at,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_audit_entry(
    user_id,
    action,
    entity_type,
    entity_id,
    old_value=None,
    new_value=None,
    ip_address=None,
    user_agent=None,
):
    created_at = datetime.now(timezone.utc)
    from app.extensions import db
    from app.models import AuditLog

    _lock_audit_tail(db)
    last_log = AuditLog.query.order_by(AuditLog.id.desc()).with_for_update().first()
    previous_hash = last_log.record_hash if last_log else GENESIS_HASH
    record_hash = compute_record_hash(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        previous_hash=previous_hash,
        created_at=created_at,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {
        "user_id": user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "old_value": old_value,
        "new_value": new_value,
        "record_hash": record_hash,
        "previous_hash": previous_hash,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": created_at,
    }


def _lock_audit_tail(db):
    bind = db.session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ''
    if dialect_name == 'postgresql':
        db.session.execute(db.text("LOCK TABLE audit_logs IN EXCLUSIVE MODE"))


def verify_chain_integrity(audit_logs):
    if not audit_logs:
        return True, None

    expected_prev = GENESIS_HASH
    for log in audit_logs:
        if log.previous_hash != expected_prev:
            return False, {
                "broken_at_id": log.id,
                "expected_previous_hash": expected_prev,
                "actual_previous_hash": log.previous_hash,
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
            return False, {
                "broken_at_id": log.id,
                "expected_hash": expected_hash,
                "actual_hash": log.record_hash,
            }

        expected_prev = log.record_hash

    return True, None
