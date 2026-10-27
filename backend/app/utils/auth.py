from datetime import datetime, timezone
from functools import wraps

from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models import User
from app.utils.response import forbidden_error, unauthorized_error
from app.constants.roles import FIELD_OFFICER, INTERNAL_USER_ROLES, OPERATIONAL_ADMIN, STAFF, SYSTEM_ADMIN


def _get_live_authenticated_user():
    claims = get_jwt()
    if claims.get('type') == 'mfa_challenge':
        return None, unauthorized_error(message='MFA verification required')

    identity = get_jwt_identity()
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return None, unauthorized_error(message='Invalid user identity')

    user = db.session.get(User, user_id)
    if not user:
        return None, unauthorized_error(message='User not found or deactivated')
    if not user.is_active:
        return None, forbidden_error(message='Account is deactivated')

    token_version = claims.get('token_version')
    if token_version is not None and token_version != user.token_version:
        return None, unauthorized_error(message='Session expired or revoked. Please log in again.')

    return user, None


def step_up_required(fn_or_max_age=None, max_age_seconds=900):
    """
    Decorator for high-risk operations requiring fresh re-authentication.
    Supports both @step_up_required and @step_up_required(max_age_seconds=900).
    """
    def make_decorator(max_age):
        def wrapper(fn):
            @wraps(fn)
            def decorator(*args, **kwargs):
                from flask import request
                verify_jwt_in_request()
                user, error = _get_live_authenticated_user()
                if error is not None:
                    return error

                now = datetime.now(timezone.utc)
                recent_timestamp = user.last_step_up_at or user.last_mfa_verified_at
                if recent_timestamp:
                    if recent_timestamp.tzinfo is None:
                        recent_timestamp = recent_timestamp.replace(tzinfo=timezone.utc)
                    if (now - recent_timestamp).total_seconds() <= max_age:
                        return fn(*args, **kwargs)

                body = request.get_json(silent=True) or {}
                confirm_pwd = (
                    body.get('confirm_password') or
                    body.get('step_up_password') or
                    request.headers.get('X-Step-Up-Password')
                )
                if confirm_pwd:
                    if user.check_password(confirm_pwd):
                        user.last_step_up_at = now
                        db.session.commit()
                        return fn(*args, **kwargs)
                    return unauthorized_error(message='Incorrect password for step-up authentication.')

                return forbidden_error(
                    message='Fresh authentication required for high-risk operation. Please provide confirmation password.'
                )
            return decorator
        return wrapper

    if callable(fn_or_max_age):
        return make_decorator(max_age_seconds)(fn_or_max_age)
    actual_max_age = fn_or_max_age if isinstance(fn_or_max_age, (int, float)) else max_age_seconds
    return make_decorator(actual_max_age)


def role_required(*allowed_roles):
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            user, error = _get_live_authenticated_user()
            if error is not None:
                return error

            user_role = user.role
            if user_role not in allowed_roles:
                reason = f"Role '{user_role}' is not authorized. Requires one of: {', '.join(allowed_roles)}"
                try:
                    from flask import g, request as flask_request
                    from app.services import audit_service
                    if not getattr(g, '_security_event_logged', False):
                        g._security_event_logged = True
                        audit_service.log_security_event(
                            user_id=user.id,
                            action='unauthorized_role_access',
                            entity_type='route',
                            entity_id=None,
                            details={
                                'role': user_role,
                                'allowed_roles': list(allowed_roles),
                                'endpoint': flask_request.endpoint if flask_request else None,
                                'path': flask_request.path if flask_request else None,
                                'method': flask_request.method if flask_request else None,
                                'reason': reason,
                            },
                        )
                except Exception:
                    pass
                return forbidden_error(
                    message=reason
                )
            return fn(*args, **kwargs)
        return decorator
    return wrapper


def admin_required(fn):
    return role_required(OPERATIONAL_ADMIN)(fn)


def admin_or_staff_required(fn):
    return role_required(OPERATIONAL_ADMIN, STAFF)(fn)


def admin_or_staff_or_field_required(fn):
    return role_required(OPERATIONAL_ADMIN, STAFF, FIELD_OFFICER)(fn)


def system_admin_required(fn):
    return role_required(SYSTEM_ADMIN)(fn)


def field_officer_required(fn):
    return role_required(FIELD_OFFICER)(fn)

def system_admin_or_admin_required(fn):
    return role_required(SYSTEM_ADMIN, OPERATIONAL_ADMIN)(fn)


def system_admin_or_admin_or_staff_required(fn):
    return role_required(SYSTEM_ADMIN, OPERATIONAL_ADMIN, STAFF)(fn)


def checker_accuracy_report_reader_required(fn):
    return role_required(SYSTEM_ADMIN, OPERATIONAL_ADMIN, STAFF)(fn)


def internal_user_required(fn):
    return role_required(*INTERNAL_USER_ROLES)(fn)

