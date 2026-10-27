import hashlib
import secrets
import string

from flask import current_app, has_request_context, request
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, create_refresh_token
from app.extensions import db
from app.constants.roles import (
    FIELD_OFFICER,
    INTERNAL_USER_ROLES,
    OPERATIONAL_ADMIN,
    OPERATIONAL_ADMIN_MANAGED_ROLES,
    STAFF,
    SYSTEM_ADMIN,
    SYSTEM_ADMIN_MANAGED_ROLES,
)
from app.models import AuditLog, LguCluster, LguProfile, MfaRecoveryCode, PasswordReset, User, UserScopeAssignment
from app.services import audit_service, email_service, settings_service
from app.utils import totp as totp_util
from app.api.auth.schemas import validate_password_strength
from datetime import datetime, timezone, timedelta
import uuid

TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits
FAILED_LOGIN_ACTION = 'login_failed'
FAILED_PASSWORD_CHANGE_ACTION = 'password_change_failed'

ROLE_LABELS = {
    SYSTEM_ADMIN: 'System Administrator',
    OPERATIONAL_ADMIN: 'Operational Admin',
    STAFF: 'Staff',
    FIELD_OFFICER: 'Field Officer',
    'validator': 'Provincial Validator',
    'implementer': 'LGU Implementer',
    'viewer': 'Viewer / Guest',
}


def format_role(role: str | None, fallback: str | None = None) -> str:
    """Format a user role into COMET canonical human-readable presentation."""
    if not role:
        return fallback or 'User'
    clean_role = str(role).strip()
    if not clean_role:
        return fallback or 'User'
    if clean_role in ROLE_LABELS:
        return ROLE_LABELS[clean_role]
    lower_role = clean_role.lower()
    if lower_role in ROLE_LABELS:
        return ROLE_LABELS[lower_role]
    return fallback or clean_role.replace('_', ' ').title()


class AuthError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code


def _normalize_email(email):
    return (email or '').strip().lower()


def _coerce_user_id(user_id):
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise AuthError('Invalid user identity', 422)


def _generate_temporary_password(length=14):
    return ''.join(secrets.choice(TEMP_PASSWORD_ALPHABET) for _ in range(length))


def _find_user_by_normalized_email(email, exclude_user_id=None):
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return None

    query = User.query.filter(
        func.lower(func.trim(User.email)) == normalized_email,
    )
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.first()


def _ensure_internal_dashboard_user(user):
    if user.role not in INTERNAL_USER_ROLES:
        app_name = settings_service.get_app_name()
        raise AuthError(
            f'This account does not have access to the internal {app_name} dashboard.',
            403,
        )


def _lock_and_count_active_role(role):
    """
    Acquire pessimistic row-level locks on all currently active users with the
    specified role in deterministic ID order, and return the count of locked rows.

    Under PostgreSQL READ COMMITTED, any concurrent transaction attempting a role
    demotion or deactivation on a user of this role will block on the row locks.
    Once the first transaction commits, the second transaction re-evaluates the updated
    row versions, observing whether only 1 active administrator remains.
    """
    locked_users = (
        User.query.filter_by(role=role, is_active=True)
        .order_by(User.id)
        .with_for_update()
        .all()
    )
    return len(locked_users)


def _count_active_admins(for_update=True):
    if for_update:
        return _lock_and_count_active_role(OPERATIONAL_ADMIN)
    return _count_active_role(OPERATIONAL_ADMIN)


def _count_active_system_admins(for_update=True):
    if for_update:
        return _lock_and_count_active_role(SYSTEM_ADMIN)
    return _count_active_role(SYSTEM_ADMIN)


def _count_active_role(role):
    return User.query.filter_by(role=role, is_active=True).count()


def _is_email_uniqueness_conflict(exc):
    """
    Identify whether an IntegrityError was caused by a duplicate email unique constraint.
    Inspects PostgreSQL diagnostics when available (exc.orig.diag.constraint_name),
    or uses exact narrow SQLite constraint messages when running under SQLite.
    Never matches generic substrings or unrelated field names.
    """
    orig = getattr(exc, 'orig', None)
    if orig is not None:
        diag = getattr(orig, 'diag', None)
        if diag is not None:
            constraint_name = getattr(diag, 'constraint_name', None)
            if constraint_name in {'ix_users_email', 'users_email_key'}:
                return True

    msg = str(orig if orig is not None else exc).lower()
    if 'ix_users_email' in msg or 'users_email_key' in msg:
        return True
    if 'unique constraint failed:' in msg and 'users.email' in msg:
        return True
    return False


def _get_management_actor(actor_id):
    actor_id = _coerce_user_id(actor_id)
    actor = db.session.get(User, actor_id)
    if not actor or not actor.is_active:
        raise AuthError('Managing account not found or deactivated', 401)
    _ensure_internal_dashboard_user(actor)
    if actor.role not in {SYSTEM_ADMIN, OPERATIONAL_ADMIN}:
        raise AuthError('Only administrators can manage user accounts', 403)
    return actor


def _managed_roles_for_actor(actor):
    if actor.role == SYSTEM_ADMIN:
        return SYSTEM_ADMIN_MANAGED_ROLES
    if actor.role == OPERATIONAL_ADMIN:
        return OPERATIONAL_ADMIN_MANAGED_ROLES
    return ()


def _ensure_actor_can_assign_role(actor, role):
    if role not in INTERNAL_USER_ROLES:
        raise AuthError(f'Invalid role. Must be one of: {", ".join(INTERNAL_USER_ROLES)}', 422)
    if role not in _managed_roles_for_actor(actor):
        raise AuthError('Operational Admins cannot manage System Administrator (System Admin) accounts', 403)


def _ensure_actor_can_manage_target(actor, target):
    if target.role == SYSTEM_ADMIN and actor.role != SYSTEM_ADMIN:
        raise AuthError('Operational Admins cannot manage System Administrator (System Admin) accounts', 403)


def _validate_scoped_role_assignments(role, cluster_ids, lgu_ids):
    if role == SYSTEM_ADMIN:
        if cluster_ids or lgu_ids:
            raise AuthError('System Admin accounts are technical and cannot be LGU- or cluster-scoped', 422)
        return

    if role == OPERATIONAL_ADMIN:
        if lgu_ids:
            raise AuthError('Admins can be province-wide or cluster-scoped, but not LGU-scoped', 422)
        return

    if role == STAFF:
        if lgu_ids:
            raise AuthError('Staff accounts must be scoped by cluster, not by specific LGUs', 422)
        if not cluster_ids:
            raise AuthError('Staff accounts must be assigned to at least one LGU cluster', 422)
        return

    if role == FIELD_OFFICER:
        if cluster_ids:
            raise AuthError('Field officer accounts must be assigned to specific LGUs, not clusters', 422)
        if not lgu_ids:
            raise AuthError('Field officer accounts must be assigned to at least one LGU', 422)
        return

    if role not in INTERNAL_USER_ROLES:
        raise AuthError(
            f'Invalid role. Must be one of: {", ".join(INTERNAL_USER_ROLES)}',
            422,
        )


def register_user(email, password, first_name, last_name, role='staff',
                  must_change_password=False, created_by=None):
    email = _normalize_email(email)

    if _find_user_by_normalized_email(email):
        raise AuthError('Email already registered', 409)

    if role not in INTERNAL_USER_ROLES:
        raise AuthError(f'Invalid role. Must be one of: {", ".join(INTERNAL_USER_ROLES)}', 422)

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=True,
        must_change_password=must_change_password,
    )
    db.session.add(user)
    db.session.commit()

    audit_service.log_action(
        user_id=created_by,
        action='create',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value=_serialize_user(user),
    )

    return user


def create_user_account(admin_id, email, first_name, last_name, role, cluster_ids=None, lgu_ids=None):
    actor = _get_management_actor(admin_id)
    _ensure_actor_can_assign_role(actor, role)

    cluster_ids = _normalize_scope_ids(cluster_ids, 'Cluster')
    lgu_ids = _normalize_scope_ids(lgu_ids, 'LGU')
    normalized_email = _normalize_email(email)
    if _find_user_by_normalized_email(normalized_email):
        raise AuthError('Email already registered', 409)

    _validate_scoped_role_assignments(role, cluster_ids, lgu_ids)

    temporary_password = _generate_temporary_password()
    user = User(
        email=normalized_email,
        password_hash=generate_password_hash(temporary_password),
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=True,
        must_change_password=True,
    )
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError as exc:
        db.session.rollback()
        if _is_email_uniqueness_conflict(exc):
            raise AuthError('Email already registered', 409) from exc
        raise

    assignments = []
    for cluster_id in cluster_ids:
        cluster = db.session.get(LguCluster, cluster_id)
        if not cluster:
            raise AuthError(f'Cluster {cluster_id} not found', 404)
        assignment = UserScopeAssignment(
            user_id=user.id,
            scope_type='cluster',
            cluster_id=cluster_id,
            is_active=True,
        )
        db.session.add(assignment)
        assignments.append(assignment)

    for lgu_id in lgu_ids:
        lgu = db.session.get(LguProfile, lgu_id)
        if not lgu:
            raise AuthError(f'LGU {lgu_id} not found', 404)
        assignment = UserScopeAssignment(
            user_id=user.id,
            scope_type='lgu',
            lgu_id=lgu_id,
            is_active=True,
        )
        db.session.add(assignment)
        assignments.append(assignment)

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if _is_email_uniqueness_conflict(exc):
            raise AuthError('Email already registered', 409) from exc
        raise

    audit_service.log_action(
        user_id=admin_id,
        action='create',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value=_serialize_user(user),
    )

    for assignment in assignments:
        audit_service.log_action(
            user_id=admin_id,
            action='create',
            entity_type='user_scope_assignment',
            entity_id=assignment.id,
            old_value=None,
            new_value={
                'user_id': assignment.user_id,
                'scope_type': assignment.scope_type,
                'cluster_id': assignment.cluster_id,
                'lgu_id': assignment.lgu_id,
                'is_active': assignment.is_active,
            },
        )

    delivery = email_service.send_user_provisioning_email(
        email=user.email,
        first_name=user.first_name,
        temporary_password=temporary_password,
    )
    if delivery.get('status') != 'sent':
        delivery = {
            **delivery,
            'temporary_password': temporary_password,
            'manual_handoff_required': True,
        }

    return {
        'user': _serialize_user(user),
        'delivery': delivery,
    }


def _get_client_ip():
    if has_request_context() and request:
        xff = request.headers.get('X-Forwarded-For')
        if xff:
            return xff.split(',')[0].strip()
        return request.remote_addr or '127.0.0.1'
    return '127.0.0.1'


def login_user(email, password, ip_address=None):
    if not ip_address:
        ip_address = _get_client_ip()

    normalized_email = _normalize_email(email)
    _assert_login_not_rate_limited(normalized_email, ip_address)
    user = _find_user_by_normalized_email(email)
    if not user or not user.check_password(password):
        _record_failed_login(user, normalized_email, 'invalid_credentials', ip_address)
        raise AuthError('Invalid email or password', 401)

    try:
        _ensure_internal_dashboard_user(user)
    except AuthError:
        _record_failed_login(user, normalized_email, 'invalid_dashboard_role', ip_address)
        raise

    if not user.is_active:
        _record_failed_login(user, normalized_email, 'deactivated', ip_address)
        raise AuthError('Account is deactivated', 403)

    if getattr(user, 'mfa_enabled', False):
        challenge_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                'role': user.role,
                'token_version': user.token_version,
                'type': 'mfa_challenge',
            },
            expires_delta=timedelta(minutes=5),
        )
        return {
            'mfa_required': True,
            'challenge_token': challenge_token,
            'mfa_challenge_token': challenge_token,
            'user': _serialize_user(user),
        }

    token_identity = str(user.id)
    access_token = create_access_token(
        identity=token_identity,
        additional_claims={
            'role': user.role,
            'token_version': user.token_version,
        },
    )
    refresh_token = create_refresh_token(
        identity=token_identity,
        additional_claims={
            'token_version': user.token_version,
        },
    )

    user.last_step_up_at = datetime.now(timezone.utc)
    db.session.commit()

    audit_service.log_action(
        user_id=user.id,
        action='login',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value={'role': user.role, 'is_active': user.is_active, 'ip_address': ip_address},
    )

    result = {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': _serialize_user(user),
    }
    if user.role in {OPERATIONAL_ADMIN, SYSTEM_ADMIN} and not getattr(user, 'mfa_enabled', False):
        result['must_enroll_mfa'] = True
    return result


def _assert_login_not_rate_limited(normalized_email, ip_address=None):
    if not ip_address:
        ip_address = _get_client_ip()

    window_minutes = _auth_limit('AUTH_FAILURE_WINDOW_MINUTES', 15)
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    user = _find_user_by_normalized_email(normalized_email)
    entity_id = user.id if user else 0

    recent_failures = AuditLog.query.filter(
        AuditLog.action == FAILED_LOGIN_ACTION,
        AuditLog.entity_type == 'auth',
        AuditLog.created_at >= since,
    ).all()

    # 1. Per-IP limit: max 20 failed logins from this IP across all accounts
    ip_limit = _auth_limit('AUTH_IP_FAILED_LOGIN_LIMIT', 20)
    ip_failures = [f for f in recent_failures if (f.new_value or {}).get('ip_address') == ip_address]
    if len(ip_failures) >= ip_limit:
        raise AuthError('Too many failed login attempts from this IP address. Please wait before trying again.', 429)

    # 2. Per-(account, IP) limit: max 5 failed logins for this account from this IP
    account_limit = _auth_limit('AUTH_FAILED_LOGIN_LIMIT', 5)
    account_ip_failures = [
        f for f in recent_failures
        if ((entity_id > 0 and f.entity_id == entity_id) or (f.new_value or {}).get('email') == normalized_email)
        and (f.new_value or {}).get('ip_address') == ip_address
    ]
    if len(account_ip_failures) >= account_limit:
        raise AuthError('Too many failed login attempts. Please wait before trying again.', 429)


def _record_failed_login(user, normalized_email, reason, ip_address=None):
    if not ip_address:
        ip_address = _get_client_ip()

    audit_service.log_action(
        user_id=None,
        action=FAILED_LOGIN_ACTION,
        entity_type='auth',
        entity_id=user.id if user else 0,
        old_value=None,
        new_value={
            'email': normalized_email,
            'ip_address': ip_address,
            'reason': reason,
        },
    )


def _assert_password_change_not_rate_limited(user):
    if _recent_auth_failure_count(
        FAILED_PASSWORD_CHANGE_ACTION,
        'user',
        user.id,
    ) >= _auth_limit('AUTH_FAILED_PASSWORD_CHANGE_LIMIT', 5):
        raise AuthError('Too many failed password change attempts. Please wait before trying again.', 429)


def _record_failed_password_change(user):
    audit_service.log_action(
        user_id=user.id,
        action=FAILED_PASSWORD_CHANGE_ACTION,
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value={'reason': 'invalid_current_password'},
    )


def _recent_auth_failure_count(action, entity_type, entity_id):
    window_minutes = _auth_limit('AUTH_FAILURE_WINDOW_MINUTES', 15)
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    return AuditLog.query.filter(
        AuditLog.action == action,
        AuditLog.entity_type == entity_type,
        AuditLog.entity_id == entity_id,
        AuditLog.created_at >= since,
    ).count()


def _auth_limit(config_key, fallback):
    try:
        return max(int(current_app.config.get(config_key, fallback)), 1)
    except (TypeError, ValueError):
        return fallback


def refresh_access(identity):
    identity = _coerce_user_id(identity)
    user = db.session.get(User, identity)
    if not user or not user.is_active:
        raise AuthError('User not found or deactivated', 401)
    _ensure_internal_dashboard_user(user)

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={
            'role': user.role,
            'token_version': user.token_version,
        },
    )
    return {'access_token': access_token}


def get_current_user(user_id):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user:
        raise AuthError('User not found', 404)
    _ensure_internal_dashboard_user(user)
    return _serialize_user(user)


def update_user_profile(user_id, data):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user:
        raise AuthError('User not found', 404)
    _ensure_internal_dashboard_user(user)

    before = _serialize_user(user)

    if 'first_name' in data and data['first_name']:
        user.first_name = data['first_name']
    if 'last_name' in data and data['last_name']:
        user.last_name = data['last_name']
    if 'email' in data and data['email']:
        normalized_email = _normalize_email(data['email'])
        existing = _find_user_by_normalized_email(normalized_email, exclude_user_id=user_id)
        if existing:
            raise AuthError('Email already in use', 409)
        user.email = normalized_email

    db.session.commit()

    audit_service.log_action(
        user_id=user_id,
        action='update',
        entity_type='user',
        entity_id=user.id,
        old_value=before,
        new_value=_serialize_user(user),
    )

    return _serialize_user(user)


def change_password(user_id, current_password, new_password):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user:
        raise AuthError('User not found', 404)
    _ensure_internal_dashboard_user(user)

    _assert_password_change_not_rate_limited(user)
    if not user.check_password(current_password):
        _record_failed_password_change(user)
        raise AuthError('Current password is incorrect', 401)

    pwd_err = validate_password_strength(new_password, user_identifier=user.email)
    if pwd_err:
        raise AuthError(pwd_err, 422)

    user.password_hash = generate_password_hash(new_password)
    user.must_change_password = False
    user.token_version = (user.token_version or 1) + 1
    db.session.commit()

    audit_service.log_action(
        user_id=user_id,
        action='change_password',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value={'password_changed': True},
    )

    email_service.send_security_alert_email(user.email, user.first_name, 'password_changed')

    return {'message': 'Password changed successfully'}


def list_users(page=1, per_page=20, role=None, is_active=None, must_change_password=None, search=None, actor_id=None):
    query = User.query
    if actor_id is not None:
        actor = _get_management_actor(actor_id)
        if actor.role != SYSTEM_ADMIN:
            query = query.filter(User.role != SYSTEM_ADMIN)
    if role:
        query = query.filter_by(role=role)
    if is_active is not None:
        query = query.filter_by(is_active=is_active)
    if must_change_password is not None:
        query = query.filter_by(must_change_password=must_change_password)
    search = (search or '').strip()
    if search:
        term = f'%{search}%'
        query = query.filter(or_(
            User.first_name.ilike(term),
            User.last_name.ilike(term),
            User.email.ilike(term),
            User.role.ilike(term),
        ))

    pagination = query.order_by(User.last_name, User.first_name).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        'users': [_serialize_user(u) for u in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def get_user_for_admin(user_id, actor_id=None):
    target = db.session.get(User, user_id)
    if not target:
        raise AuthError('User not found', 404)
    if actor_id is not None:
        actor = _get_management_actor(actor_id)
        _ensure_actor_can_manage_target(actor, target)
    return _serialize_user(target)


def toggle_user_active(admin_id, target_user_id, is_active):
    actor = _get_management_actor(admin_id)
    admin_id = actor.id
    target = db.session.get(User, target_user_id)
    if not target:
        raise AuthError('User not found', 404)
    _ensure_actor_can_manage_target(actor, target)

    if target.id == admin_id:
        raise AuthError('Cannot deactivate your own account', 422)
    if target.role == OPERATIONAL_ADMIN and target.is_active and not is_active and _count_active_admins() <= 1:
        raise AuthError(f'{settings_service.get_app_name()} must always have at least one active administrator', 422)
    if target.role == SYSTEM_ADMIN and target.is_active and not is_active and _count_active_system_admins() <= 1:
        raise AuthError(f'{settings_service.get_app_name()} must always have at least one active System Admin', 422)

    before = _serialize_user(target)
    target.is_active = is_active
    if not is_active:
        target.token_version = (target.token_version or 1) + 1
    db.session.commit()

    audit_service.log_action(
        user_id=admin_id,
        action='toggle_active',
        entity_type='user',
        entity_id=target.id,
        old_value=before,
        new_value=_serialize_user(target),
    )

    return _serialize_user(target)


def _normalize_scope_ids(values, label):
    normalized = []
    for value in values or []:
        try:
            normalized.append(int(value))
        except (TypeError, ValueError):
            raise AuthError(f'{label} IDs must be integers', 422)
    return list(dict.fromkeys(normalized))


def _active_scope_ids(user, scope_type):
    target_attr = 'cluster_id' if scope_type == 'cluster' else 'lgu_id'
    return [
        getattr(assignment, target_attr)
        for assignment in user.lgu_assignments
        if assignment.is_active and assignment.scope_type == scope_type
    ]


def _sync_scope_assignments(user, scope_type, target_ids):
    target_attr = 'cluster_id' if scope_type == 'cluster' else 'lgu_id'
    model = LguCluster if scope_type == 'cluster' else LguProfile
    missing_label = 'Cluster' if scope_type == 'cluster' else 'LGU'
    target_ids = list(dict.fromkeys(target_ids or []))
    target_id_set = set(target_ids)

    for target_id in target_ids:
        if not db.session.get(model, target_id):
            raise AuthError(f'{missing_label} {target_id} not found', 404)

    existing_by_target = {
        getattr(assignment, target_attr): assignment
        for assignment in user.lgu_assignments
        if assignment.scope_type == scope_type
    }
    for assignment in user.lgu_assignments:
        if assignment.scope_type == scope_type:
            assignment.is_active = getattr(assignment, target_attr) in target_id_set

    for target_id in target_ids:
        existing = existing_by_target.get(target_id)
        if existing:
            existing.is_active = True
            continue
        db.session.add(UserScopeAssignment(
            user_id=user.id,
            scope_type=scope_type,
            **{target_attr: target_id},
            is_active=True,
        ))


def change_user_role(admin_id, target_user_id, new_role, cluster_ids=None, lgu_ids=None, can_approve_technical_documents=None, can_close_management_actions=None):
    actor = _get_management_actor(admin_id)
    admin_id = actor.id
    _ensure_actor_can_assign_role(actor, new_role)

    target = db.session.get(User, target_user_id)
    if not target:
        raise AuthError('User not found', 404)
    _ensure_actor_can_manage_target(actor, target)

    if target.role == OPERATIONAL_ADMIN and new_role != OPERATIONAL_ADMIN and target.is_active and _count_active_admins() <= 1:
        raise AuthError(f'{settings_service.get_app_name()} must always have at least one active administrator', 422)
    if target.role == SYSTEM_ADMIN and new_role != SYSTEM_ADMIN and target.is_active and _count_active_system_admins() <= 1:
        raise AuthError(f'{settings_service.get_app_name()} must always have at least one active System Admin', 422)
    cluster_ids_provided = cluster_ids is not None
    lgu_ids_provided = lgu_ids is not None
    target_cluster_ids = (
        _normalize_scope_ids(cluster_ids, 'Cluster')
        if cluster_ids_provided
        else _active_scope_ids(target, 'cluster')
    )
    target_lgu_ids = (
        _normalize_scope_ids(lgu_ids, 'LGU')
        if lgu_ids_provided
        else _active_scope_ids(target, 'lgu')
    )

    if new_role == SYSTEM_ADMIN:
        effective_cluster_ids = []
        effective_lgu_ids = []
    elif new_role == OPERATIONAL_ADMIN:
        effective_cluster_ids = target_cluster_ids if cluster_ids_provided else _active_scope_ids(target, 'cluster')
        effective_lgu_ids = target_lgu_ids if lgu_ids_provided else []
    elif new_role == STAFF:
        effective_cluster_ids = target_cluster_ids
        effective_lgu_ids = target_lgu_ids if lgu_ids_provided else []
    else:
        effective_cluster_ids = target_cluster_ids if cluster_ids_provided else []
        effective_lgu_ids = target_lgu_ids

    _validate_scoped_role_assignments(new_role, effective_cluster_ids, effective_lgu_ids)

    before = _serialize_user(target)
    target.role = new_role
    if new_role == SYSTEM_ADMIN:
        for assignment in target.lgu_assignments:
            assignment.is_active = False
    elif new_role == OPERATIONAL_ADMIN:
        _sync_scope_assignments(target, 'cluster', effective_cluster_ids)
        for assignment in target.lgu_assignments:
            if assignment.scope_type == 'lgu':
                assignment.is_active = False
    elif new_role == STAFF:
        _sync_scope_assignments(target, 'cluster', effective_cluster_ids)
        for assignment in target.lgu_assignments:
            if assignment.scope_type == 'lgu':
                assignment.is_active = False
    elif new_role == FIELD_OFFICER:
        _sync_scope_assignments(target, 'lgu', effective_lgu_ids)
        for assignment in target.lgu_assignments:
            if assignment.scope_type == 'cluster':
                assignment.is_active = False
    target.token_version = (target.token_version or 1) + 1
    db.session.commit()

    audit_service.log_action(
        user_id=admin_id,
        action='change_role',
        entity_type='user',
        entity_id=target.id,
        old_value=before,
        new_value=_serialize_user(target),
    )

    email_service.send_security_alert_email(target.email, target.first_name, 'role_changed', {'new_role': format_role(new_role)})

    return _serialize_user(target)


def _serialize_user(user):
    assigned_clusters = [
        {
            'assignment_id': assignment.id,
            'cluster_id': assignment.cluster_id,
            'cluster_name': assignment.cluster.name if assignment.cluster else None,
            'is_active': assignment.is_active,
        }
        for assignment in user.lgu_assignments
        if assignment.is_active and assignment.scope_type == 'cluster'
    ]
    assigned_lgus = [
        {
            'assignment_id': assignment.id,
            'lgu_id': assignment.lgu_id,
            'lgu_name': assignment.lgu.name if assignment.lgu else None,
            'municipality': assignment.lgu.municipality if assignment.lgu else None,
            'province': assignment.lgu.province if assignment.lgu else None,
            'cluster_id': assignment.lgu.cluster_id if assignment.lgu else None,
            'cluster_name': assignment.lgu.cluster.name if assignment.lgu and assignment.lgu.cluster else None,
            'is_active': assignment.is_active,
        }
        for assignment in user.lgu_assignments
        if assignment.is_active and assignment.scope_type == 'lgu'
    ]
    return {
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.full_name,
        'role': user.role,
        'is_active': user.is_active,
        'must_change_password': user.must_change_password,
        'token_version': getattr(user, 'token_version', 1),
        'mfa_enabled': getattr(user, 'mfa_enabled', False),
        'mfa_type': getattr(user, 'mfa_type', 'totp'),
        'last_mfa_verified_at': user.last_mfa_verified_at.isoformat() if getattr(user, 'last_mfa_verified_at', None) else None,
        'must_enroll_mfa': (user.role in {'system_admin', 'admin'}) and not getattr(user, 'mfa_enabled', False),
        'can_approve_technical_documents': getattr(user, 'can_approve_technical_documents', False),
        'can_close_management_actions': getattr(user, 'can_close_management_actions', False),
        'assigned_clusters': assigned_clusters,
        'assigned_lgus': assigned_lgus,
        'created_at': user.created_at.isoformat() if user.created_at else None,
    }


def logout_user(user_id):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user:
        raise AuthError('User not found', 404)

    user.token_version = (user.token_version or 1) + 1
    db.session.commit()

    audit_service.log_action(
        user_id=user.id,
        action='logout',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value={'token_version': user.token_version},
    )

    return {'success': True, 'message': 'Logged out successfully'}


def revoke_user_sessions(user_id, actor_id=None):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user:
        raise AuthError('User not found', 404)

    user.token_version = (user.token_version or 1) + 1
    db.session.commit()

    audit_service.log_action(
        user_id=_coerce_user_id(actor_id) if actor_id else user.id,
        action='session_revoked',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value={'revoked_all_sessions': True, 'new_token_version': user.token_version},
    )

    return {'success': True, 'message': 'All sessions revoked'}


def request_password_reset(email, ip_address=None):
    if not ip_address:
        ip_address = _get_client_ip()

    normalized_email = _normalize_email(email)
    now = datetime.now(timezone.utc)
    window_since = now - timedelta(minutes=15)

    recent_ip_resets = AuditLog.query.filter(
        AuditLog.action == 'password_reset_requested',
        AuditLog.created_at >= window_since,
    ).all()
    ip_count = sum(1 for log in recent_ip_resets if (log.new_value or {}).get('ip_address') == ip_address)
    if ip_count >= 5:
        raise AuthError('Too many password reset requests from this IP address. Please wait before trying again.', 429)

    user = _find_user_by_normalized_email(normalized_email)
    response_msg = 'If the email is registered, password reset instructions have been sent.'

    if not user or not user.is_active:
        audit_service.log_action(
            user_id=None,
            action='password_reset_requested',
            entity_type='auth',
            entity_id=0,
            old_value=None,
            new_value={'email': normalized_email, 'ip_address': ip_address},
        )
        import time
        _ = hashlib.sha256(b'dummy-entropy-for-timing-mitigation').hexdigest()
        time.sleep(0.05)
        return {'success': True, 'message': response_msg}

    user_recent_resets = PasswordReset.query.filter(
        PasswordReset.user_id == user.id,
        PasswordReset.created_at >= window_since,
    ).count()
    if user_recent_resets >= 3:
        return {'success': True, 'message': response_msg}

    for pending in PasswordReset.query.filter_by(user_id=user.id, used_at=None).all():
        pending.used_at = now

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
    reset_record = PasswordReset(
        user_id=user.id,
        token=token_hash,
        expires_at=now + timedelta(minutes=15),
    )
    db.session.add(reset_record)
    db.session.commit()

    audit_service.log_action(
        user_id=None,
        action='password_reset_requested',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value={'email': user.email, 'ip_address': ip_address},
    )

    email_service.send_password_reset_email(user.email, raw_token, user.first_name)

    result = {'success': True, 'message': response_msg}
    if current_app.config.get('TESTING'):
        result['token'] = raw_token
    return result


def validate_password_reset_token(raw_token):
    if not raw_token:
        raise AuthError('Reset token is required', 400)

    token_hash = hashlib.sha256(raw_token.strip().encode('utf-8')).hexdigest()
    reset_record = PasswordReset.query.filter_by(token=token_hash).first()
    if not reset_record:
        raise AuthError('Invalid or expired password reset token', 400)

    now = datetime.now(timezone.utc)
    if reset_record.used_at is not None:
        raise AuthError('Password reset token has already been used', 400)

    expires_at = reset_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise AuthError('Password reset token has expired', 400)

    user = reset_record.user
    if not user or not user.is_active:
        raise AuthError('User account is inactive or not found', 400)

    return {'success': True, 'message': 'Token is valid', 'user_id': user.id}


def complete_password_reset(raw_token, new_password):
    validated = validate_password_reset_token(raw_token)
    user = db.session.get(User, validated['user_id'])

    pwd_err = validate_password_strength(new_password, user_identifier=user.email)
    if pwd_err:
        raise AuthError(pwd_err, 422)

    token_hash = hashlib.sha256(raw_token.strip().encode('utf-8')).hexdigest()
    reset_record = PasswordReset.query.filter_by(token=token_hash).first()

    now = datetime.now(timezone.utc)
    reset_record.used_at = now

    user.password_hash = generate_password_hash(new_password)
    user.must_change_password = False
    user.token_version = (user.token_version or 1) + 1
    db.session.commit()

    audit_service.log_action(
        user_id=user.id,
        action='password_reset_completed',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value={'email': user.email, 'reset_completed': True},
    )

    email_service.send_security_alert_email(user.email, user.first_name, 'password_reset_completed')

    return {'success': True, 'message': 'Password has been successfully reset. Please log in with your new password.'}


def enroll_mfa(user_id):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user:
        raise AuthError('User not found', 404)

    secret = totp_util.generate_secret()
    app_name = settings_service.get_app_name()
    otpauth_url = totp_util.get_provisioning_uri(secret, user.email, issuer=app_name)
    qr_code_svg = totp_util.generate_qr_code_svg(otpauth_url)

    user.mfa_secret = secret
    db.session.commit()

    return {
        'secret': secret,
        'otpauth_url': otpauth_url,
        'qr_code': qr_code_svg,
        'issuer': app_name,
    }


def confirm_mfa_enrollment(user_id, code):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user or not user.mfa_secret:
        raise AuthError('MFA enrollment not initiated. Please start enrollment first.', 400)

    if not totp_util.verify_totp(user.mfa_secret, code):
        raise AuthError('Invalid verification code. Please try again.', 400)

    user.mfa_enabled = True
    user.mfa_type = 'totp'
    now = datetime.now(timezone.utc)
    user.last_mfa_verified_at = now
    user.last_step_up_at = now

    MfaRecoveryCode.query.filter_by(user_id=user.id).delete()

    raw_codes = totp_util.generate_recovery_codes(8)
    for rc in raw_codes:
        code_hash = totp_util.hash_recovery_code(rc)
        db.session.add(MfaRecoveryCode(user_id=user.id, code_hash=code_hash))

    db.session.commit()

    audit_service.log_action(
        user_id=user.id,
        action='mfa_enabled',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value={'mfa_type': 'totp'},
    )

    email_service.send_security_alert_email(user.email, user.first_name, 'mfa_enabled')

    return {
        'success': True,
        'message': 'Two-factor authentication has been successfully enabled.',
        'recovery_codes': raw_codes,
    }


def verify_mfa_login(user_id, code=None, recovery_code=None):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        raise AuthError('User not found or deactivated', 401)
    if not user.mfa_enabled or not user.mfa_secret:
        raise AuthError('MFA is not enabled for this account', 400)

    now = datetime.now(timezone.utc)
    method_used = None
    warning_msg = None

    if code:
        if not totp_util.verify_totp(user.mfa_secret, code):
            raise AuthError('Invalid MFA verification code', 401)
        method_used = 'totp'
    elif recovery_code:
        code_hash = totp_util.hash_recovery_code(recovery_code)
        rec_record = MfaRecoveryCode.query.filter_by(
            user_id=user.id,
            code_hash=code_hash,
            used_at=None,
        ).first()
        if not rec_record:
            raise AuthError('Invalid or already used recovery code', 401)
        rec_record.used_at = now
        method_used = 'recovery_code'
        remaining = MfaRecoveryCode.query.filter_by(user_id=user.id, used_at=None).count()
        if remaining <= 2:
            warning_msg = f'Warning: Only {remaining} recovery code(s) remaining. Consider regenerating them.'
    else:
        raise AuthError('Verification code or recovery code is required', 400)

    user.last_mfa_verified_at = now
    user.last_step_up_at = now
    db.session.commit()

    token_identity = str(user.id)
    access_token = create_access_token(
        identity=token_identity,
        additional_claims={
            'role': user.role,
            'token_version': user.token_version,
        },
    )
    refresh_token = create_refresh_token(
        identity=token_identity,
        additional_claims={
            'token_version': user.token_version,
        },
    )

    audit_service.log_action(
        user_id=user.id,
        action='mfa_verified',
        entity_type='user',
        entity_id=user.id,
        old_value=None,
        new_value={'method': method_used},
    )

    result = {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': _serialize_user(user),
    }
    if warning_msg:
        result['warning'] = warning_msg
    return result


def reset_mfa(actor_id, target_user_id):
    actor = _get_management_actor(actor_id)
    target = db.session.get(User, target_user_id)
    if not target:
        raise AuthError('User not found', 404)

    if actor.id != target.id:
        _ensure_actor_can_manage_target(actor, target)

    target.mfa_enabled = False
    target.mfa_secret = None
    target.last_mfa_verified_at = None
    MfaRecoveryCode.query.filter_by(user_id=target.id).delete()
    target.token_version = (target.token_version or 1) + 1
    db.session.commit()

    audit_service.log_action(
        user_id=actor.id,
        action='mfa_disabled',
        entity_type='user',
        entity_id=target.id,
        old_value=None,
        new_value={'mfa_enabled': False},
    )

    email_service.send_security_alert_email(target.email, target.first_name, 'mfa_disabled')

    return {'success': True, 'message': 'MFA has been disabled'}


def verify_step_up(user_id, password, totp_code=None):
    user_id = _coerce_user_id(user_id)
    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        raise AuthError('User not found or deactivated', 401)

    if not user.check_password(password):
        raise AuthError('Incorrect password for step-up authentication', 401)

    if user.mfa_enabled and user.mfa_secret and totp_code:
        if not totp_util.verify_totp(user.mfa_secret, totp_code):
            raise AuthError('Invalid TOTP code for step-up authentication', 401)

    now = datetime.now(timezone.utc)
    user.last_step_up_at = now
    db.session.commit()

    return {
        'success': True,
        'message': 'Step-up authentication confirmed',
        'valid_until': (now + timedelta(minutes=15)).isoformat(),
    }
