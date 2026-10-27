import logging
import re
import smtplib
import socket
import time
from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models.audit import SystemConfig
from app.models.storage import StoredObject
from app.services import audit_service, settings_service
from app.services.matcher_runtime_settings import normalize_refinement_updates, parse_refinement_boolean

logger = logging.getLogger(__name__)

# ── Canonical Configuration Keys ─────────────────────────────────────────────

APPROVED_AI_SETTING_KEYS = {
    'GEMINI_API_KEY',
    'GROQ_API_KEY',
    'OPENROUTER_API_KEY',
    'GEMINI_MODEL',
    'GROQ_MODEL',
    'OPENROUTER_MODEL',
    'AI_PROVIDER_ORDER',
    'AI_REQUEST_TIMEOUT_SECONDS',
    'AI_TEMPERATURE',
    'AI_MAX_OUTPUT_TOKENS',
    'AI_MAX_PROMPT_CHARS',
    'AI_DOCUMENT_CLASSIFICATION_ENABLED',
}

APPROVED_AI_SECRET_KEYS = {
    'GEMINI_API_KEY',
    'GROQ_API_KEY',
    'OPENROUTER_API_KEY',
}

APPROVED_STORAGE_SETTING_KEYS = {
    'OBJECT_STORAGE_PROVIDER',
    'R2_BUCKET_NAME',
    'R2_ENDPOINT_URL',
    'R2_ACCESS_KEY_ID',
    'R2_SECRET_ACCESS_KEY',
    'R2_REGION',
    'OBJECT_STORAGE_BUCKET_PREFIX',
}

APPROVED_STORAGE_SECRET_KEYS = {
    'R2_ACCESS_KEY_ID',
    'R2_SECRET_ACCESS_KEY',
}

STORAGE_DEPLOYMENT_ONLY_KEYS = {
    'OBJECT_STORAGE_LOCAL_DIR',
    'OBJECT_STORAGE_TEMP_DIR',
    'OBJECT_STORAGE_ENV',
    'OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS',
}

STORAGE_DEFAULT_FALLBACKS = {
    'OBJECT_STORAGE_PROVIDER': 'local',
    'OBJECT_STORAGE_BUCKET_PREFIX': 'comet',
    'R2_REGION': 'auto',
}

APPROVED_EMAIL_SETTING_KEYS = {
    'SMTP_HOST',
    'SMTP_PORT',
    'SMTP_USERNAME',
    'SMTP_PASSWORD',
    'SMTP_USE_TLS',
    'MAIL_FROM',
}

APPROVED_EMAIL_SECRET_KEYS = {
    'SMTP_USERNAME',
    'SMTP_PASSWORD',
}

EMAIL_DEFAULT_FALLBACKS = {
    'SMTP_PORT': 587,
    'SMTP_USE_TLS': True,
    'MAIL_FROM': 'no-reply@example.local',
}

APPROVED_DRIVE_SETTING_KEYS = {
    'google_drive_root_folder_id',
    'GOOGLE_DRIVE_SHARED_DRIVE_ID',
}

DRIVE_DEPLOYMENT_ONLY_KEYS = {
    'GOOGLE_DRIVE_ENABLED',
    'GOOGLE_OAUTH_CLIENT_ID',
    'GOOGLE_OAUTH_CLIENT_SECRET',
    'GOOGLE_DRIVE_OAUTH_REDIRECT_URI',
    'GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE',
    'GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON',
}

ALL_APPROVED_TECHNICAL_SETTING_KEYS = (
    APPROVED_AI_SETTING_KEYS
    | APPROVED_STORAGE_SETTING_KEYS
    | APPROVED_EMAIL_SETTING_KEYS
    | APPROVED_DRIVE_SETTING_KEYS
)

ALL_APPROVED_TECHNICAL_SECRET_KEYS = (
    APPROVED_AI_SECRET_KEYS
    | APPROVED_STORAGE_SECRET_KEYS
    | APPROVED_EMAIL_SECRET_KEYS
)

_unreadable_warned_at = {}


def _warn_unreadable_override_bounded(key):
    now = time.time()
    last_warn = _unreadable_warned_at.get(key, 0)
    if now - last_warn > 300:
        _unreadable_warned_at[key] = now
        logger.warning(
            f"Database override for technical setting '{key}' is invalid or unreadable; "
            "falling back to environment or default configuration."
        )


def to_iso_utc(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def mask_secret(value):
    if not value:
        return None
    return '••••••••'


def _has_real_secret(value):
    if not value:
        return False
    text_val = str(value).strip().lower()
    return bool(text_val and text_val not in {'changeme', 'change-me', 'placeholder', 'none', 'null'})


# ── Runtime Resolution ───────────────────────────────────────────────────────

def resolve_storage_runtime_value(key):
    """Resolve storage configuration using 3-tier precedence:
    (1) SystemConfig database override
    (2) current_app.config / os.environ
    (3) Established default fallback
    """
    if key not in APPROVED_STORAGE_SETTING_KEYS:
        return current_app.config.get(key) if current_app else None

    raw_val = None
    try:
        entry = SystemConfig.query.filter_by(key=key).first()
        if entry and entry.value not in (None, ''):
            if entry.is_encrypted:
                try:
                    raw_val = settings_service._decrypt_secret_value(entry.value)
                except Exception:
                    _warn_unreadable_override_bounded(key)
            else:
                raw_val = entry.value
    except Exception:
        _warn_unreadable_override_bounded(key)

    if raw_val in (None, ''):
        env_val = current_app.config.get(key) if current_app else None
        if env_val not in (None, ''):
            raw_val = env_val

    if raw_val in (None, ''):
        raw_val = STORAGE_DEFAULT_FALLBACKS.get(key)

    return raw_val


def resolve_email_runtime_value(key):
    """Resolve email/SMTP configuration using 3-tier precedence:
    (1) SystemConfig database override
    (2) current_app.config / os.environ
    (3) Established default fallback
    """
    if key not in APPROVED_EMAIL_SETTING_KEYS:
        return current_app.config.get(key) if current_app else None

    raw_val = None
    try:
        entry = SystemConfig.query.filter_by(key=key).first()
        if entry and entry.value not in (None, ''):
            if entry.is_encrypted:
                try:
                    raw_val = settings_service._decrypt_secret_value(entry.value)
                except Exception:
                    _warn_unreadable_override_bounded(key)
            else:
                raw_val = entry.value
    except Exception:
        _warn_unreadable_override_bounded(key)

    if raw_val in (None, ''):
        env_val = current_app.config.get(key) if current_app else None
        if env_val in (None, ''):
            # Also check os.environ directly for standalone email execution
            env_val = current_app.config.get('MAIL_SERVER') if key == 'SMTP_HOST' else None
        if env_val in (None, ''):
            import os
            env_val = os.environ.get(key)
        if env_val not in (None, ''):
            raw_val = env_val

    if raw_val in (None, ''):
        raw_val = EMAIL_DEFAULT_FALLBACKS.get(key)

    if key == 'SMTP_PORT':
        try:
            return int(raw_val) if raw_val is not None else 587
        except (TypeError, ValueError):
            return 587
    elif key == 'SMTP_USE_TLS':
        if isinstance(raw_val, bool):
            return raw_val
        return str(raw_val or 'true').strip().lower() in {'true', '1', 'yes', 'on'}

    return raw_val


def resolve_drive_runtime_value(key):
    """Resolve Google Drive configuration using 3-tier precedence:
    (1) SystemConfig database override
    (2) current_app.config / os.environ
    (3) Established default fallback
    """
    if key not in APPROVED_DRIVE_SETTING_KEYS:
        return current_app.config.get(key) if current_app else None

    raw_val = None
    try:
        entry = SystemConfig.query.filter_by(key=key).first()
        if entry and entry.value not in (None, ''):
            raw_val = entry.value
    except Exception:
        _warn_unreadable_override_bounded(key)

    if raw_val in (None, ''):
        env_val = current_app.config.get(key) if current_app else None
        if env_val in (None, ''):
            if key == 'google_drive_root_folder_id':
                env_val = current_app.config.get('GOOGLE_DRIVE_ROOT_FOLDER_ID') if current_app else None
        if env_val in (None, ''):
            import os
            env_val = os.environ.get(key)
        if env_val not in (None, ''):
            raw_val = env_val

    return raw_val


def resolve_all_storage_runtime_config():
    return {k: resolve_storage_runtime_value(k) for k in APPROVED_STORAGE_SETTING_KEYS}


def resolve_all_email_runtime_config():
    return {k: resolve_email_runtime_value(k) for k in APPROVED_EMAIL_SETTING_KEYS}


def get_storage_runtime_settings():
    """Return dictionary of Object Storage settings with masked secrets, sources, and metadata."""
    configs = {c.key: c for c in SystemConfig.query.filter(SystemConfig.key.in_(APPROVED_STORAGE_SETTING_KEYS)).all()}
    result = {}

    for key in sorted(APPROVED_STORAGE_SETTING_KEYS):
        is_secret = key in APPROVED_STORAGE_SECRET_KEYS
        has_override = key in configs and configs[key].value not in (None, '')
        db_entry = configs.get(key)

        override_status = 'none'
        override_error = None
        fallback_active = False
        effective_val = None

        if has_override:
            if is_secret and db_entry.is_encrypted:
                try:
                    effective_val = settings_service._decrypt_secret_value(db_entry.value)
                    override_status = 'active'
                    source = 'database'
                except Exception:
                    override_status = 'invalid_or_unreadable'
                    fallback_active = True
                    env_val = current_app.config.get(key) if current_app else None
                    if env_val not in (None, ''):
                        source = 'environment'
                        effective_val = env_val
                    else:
                        source = 'default'
                        effective_val = STORAGE_DEFAULT_FALLBACKS.get(key)
                    override_error = f"Database override could not be decrypted; fallback to {source} is active."
                    _warn_unreadable_override_bounded(key)
            else:
                effective_val = db_entry.value
                override_status = 'active'
                source = 'database'
        elif current_app and current_app.config.get(key) not in (None, ''):
            source = 'environment'
            effective_val = current_app.config.get(key)
        else:
            source = 'default'
            effective_val = STORAGE_DEFAULT_FALLBACKS.get(key)

        has_val = bool(effective_val and _has_real_secret(effective_val) if is_secret else effective_val not in (None, ''))
        masked = mask_secret(effective_val) if (is_secret and has_val) else None
        public_val = None if is_secret else effective_val

        result[key] = {
            'key': key,
            'is_secret': is_secret,
            'has_value': has_val,
            'has_override': has_override,
            'override_status': override_status,
            'override_error': override_error,
            'fallback_active': fallback_active,
            'source': source,
            'value': public_val,
            'masked_preview': masked,
            'updated_at': to_iso_utc(db_entry.updated_at) if (has_override and db_entry.updated_at) else None,
        }

    return result


def get_email_runtime_settings():
    """Return dictionary of Transactional Email settings with masked secrets, sources, and metadata."""
    configs = {c.key: c for c in SystemConfig.query.filter(SystemConfig.key.in_(APPROVED_EMAIL_SETTING_KEYS)).all()}
    result = {}

    for key in sorted(APPROVED_EMAIL_SETTING_KEYS):
        is_secret = key in APPROVED_EMAIL_SECRET_KEYS
        has_override = key in configs and configs[key].value not in (None, '')
        db_entry = configs.get(key)

        override_status = 'none'
        override_error = None
        fallback_active = False
        effective_val = None

        if has_override:
            if is_secret and db_entry.is_encrypted:
                try:
                    effective_val = settings_service._decrypt_secret_value(db_entry.value)
                    override_status = 'active'
                    source = 'database'
                except Exception:
                    override_status = 'invalid_or_unreadable'
                    fallback_active = True
                    env_val = current_app.config.get(key) if current_app else None
                    if env_val not in (None, ''):
                        source = 'environment'
                        effective_val = env_val
                    else:
                        source = 'default'
                        effective_val = EMAIL_DEFAULT_FALLBACKS.get(key)
                    override_error = f"Database override could not be decrypted; fallback to {source} is active."
                    _warn_unreadable_override_bounded(key)
            else:
                effective_val = db_entry.value
                override_status = 'active'
                source = 'database'
        elif current_app and current_app.config.get(key) not in (None, ''):
            source = 'environment'
            effective_val = current_app.config.get(key)
        else:
            source = 'default'
            effective_val = EMAIL_DEFAULT_FALLBACKS.get(key)

        has_val = bool(effective_val and _has_real_secret(effective_val) if is_secret else effective_val not in (None, ''))
        masked = mask_secret(effective_val) if (is_secret and has_val) else None
        public_val = None if is_secret else effective_val

        if not is_secret and key == 'SMTP_PORT':
            try:
                public_val = int(public_val) if public_val is not None else 587
            except (TypeError, ValueError):
                public_val = 587
        elif not is_secret and key == 'SMTP_USE_TLS':
            if isinstance(public_val, bool):
                pass
            else:
                public_val = str(public_val or 'true').strip().lower() in {'true', '1', 'yes', 'on'}

        result[key] = {
            'key': key,
            'is_secret': is_secret,
            'has_value': has_val,
            'has_override': has_override,
            'override_status': override_status,
            'override_error': override_error,
            'fallback_active': fallback_active,
            'source': source,
            'value': public_val,
            'masked_preview': masked,
            'updated_at': to_iso_utc(db_entry.updated_at) if (has_override and db_entry.updated_at) else None,
        }

    return result


def get_drive_runtime_settings():
    """Return dictionary of Drive settings with sources and metadata."""
    configs = {c.key: c for c in SystemConfig.query.filter(SystemConfig.key.in_(APPROVED_DRIVE_SETTING_KEYS)).all()}
    result = {}

    for key in sorted(APPROVED_DRIVE_SETTING_KEYS):
        has_override = key in configs and configs[key].value not in (None, '')
        db_entry = configs.get(key)
        effective_val = resolve_drive_runtime_value(key)
        source = 'database' if has_override else ('environment' if current_app and current_app.config.get(key) not in (None, '') else 'default')

        result[key] = {
            'key': key,
            'is_secret': False,
            'has_value': bool(effective_val),
            'has_override': has_override,
            'override_status': 'active' if has_override else 'none',
            'override_error': None,
            'fallback_active': False,
            'source': source,
            'value': effective_val,
            'masked_preview': None,
            'updated_at': to_iso_utc(db_entry.updated_at) if (has_override and db_entry.updated_at) else None,
        }

    return result


# ── Candidate Validation Functions ───────────────────────────────────────────

def validate_object_storage_credentials(
    provider=None,
    bucket_name=None,
    endpoint_url=None,
    access_key_id=None,
    secret_access_key=None,
    region=None,
):
    """Validate candidate or current object storage configuration using a bounded, read-only probe.
    Does not upload, overwrite, or delete any object.
    """
    effective_provider = str(provider or resolve_storage_runtime_value('OBJECT_STORAGE_PROVIDER') or 'local').strip().lower()
    if effective_provider not in {'local', 'r2'}:
        raise settings_service.SettingsError(f"Unsupported storage provider '{effective_provider}'. Must be 'local' or 'r2'.", 422)

    if effective_provider == 'local':
        return {
            'provider': 'local',
            'valid': True,
            'latency_ms': 0.1,
            'message': 'Local durable object storage directory is ready.',
        }

    effective_bucket = bucket_name if (bucket_name and str(bucket_name).strip()) else resolve_storage_runtime_value('R2_BUCKET_NAME')
    effective_endpoint = endpoint_url if (endpoint_url and str(endpoint_url).strip()) else resolve_storage_runtime_value('R2_ENDPOINT_URL')
    effective_access_key = access_key_id if (access_key_id and str(access_key_id).strip()) else resolve_storage_runtime_value('R2_ACCESS_KEY_ID')
    effective_secret_key = secret_access_key if (secret_access_key and str(secret_access_key).strip()) else resolve_storage_runtime_value('R2_SECRET_ACCESS_KEY')
    effective_region = region if (region and str(region).strip()) else (resolve_storage_runtime_value('R2_REGION') or 'auto')

    missing = []
    if not effective_bucket or not str(effective_bucket).strip():
        missing.append('R2_BUCKET_NAME')
    if not effective_endpoint or not str(effective_endpoint).strip():
        missing.append('R2_ENDPOINT_URL')
    if not effective_access_key or not _has_real_secret(effective_access_key):
        missing.append('R2_ACCESS_KEY_ID')
    if not effective_secret_key or not _has_real_secret(effective_secret_key):
        missing.append('R2_SECRET_ACCESS_KEY')

    if missing:
        return {
            'provider': 'r2',
            'valid': False,
            'latency_ms': None,
            'message': f"Cannot validate Cloudflare R2: missing required configuration: {', '.join(missing)}.",
        }

    t0 = time.perf_counter()
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        probe_config = BotoConfig(
            signature_version='s3v4',
            connect_timeout=3,
            read_timeout=3,
            retries={'max_attempts': 1, 'mode': 'standard'},
        )
        s3 = boto3.client(
            's3',
            endpoint_url=str(effective_endpoint).strip(),
            aws_access_key_id=str(effective_access_key).strip(),
            aws_secret_access_key=str(effective_secret_key).strip(),
            region_name=str(effective_region).strip(),
            config=probe_config,
        )
        s3.list_objects_v2(Bucket=str(effective_bucket).strip(), MaxKeys=1)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            'provider': 'r2',
            'valid': True,
            'latency_ms': latency_ms,
            'message': f"Cloudflare R2 bucket '{effective_bucket}' is reachable and credentials are valid ({latency_ms}ms).",
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        # Sanitize error message to prevent leaking credentials or signatures
        err_msg = str(exc)
        # Remove any access keys or signatures if present in exception
        err_msg = re.sub(r'AWSAccessKeyId=[^&\s]+', 'AWSAccessKeyId=[redacted]', err_msg)
        err_msg = re.sub(r'Signature=[^&\s]+', 'Signature=[redacted]', err_msg)
        return {
            'provider': 'r2',
            'valid': False,
            'latency_ms': latency_ms,
            'message': f"Cloudflare R2 connectivity failed: {err_msg[:200]}",
        }


def validate_smtp_credentials(
    host=None,
    port=None,
    username=None,
    password=None,
    use_tls=None,
):
    """Validate candidate or current SMTP configuration using a non-sending probe.
    Connects, establishes TLS if configured, authenticates, and issues a harmless NOOP.
    Never sends an email.
    """
    effective_host = host if (host and str(host).strip()) else resolve_email_runtime_value('SMTP_HOST')
    effective_port = port if port is not None else resolve_email_runtime_value('SMTP_PORT')
    effective_username = username if (username and str(username).strip()) else resolve_email_runtime_value('SMTP_USERNAME')
    effective_password = password if (password and str(password).strip()) else resolve_email_runtime_value('SMTP_PASSWORD')

    if use_tls is not None:
        effective_use_tls = use_tls is True or str(use_tls).strip().lower() in {'true', '1', 'yes', 'on'}
    else:
        effective_use_tls = resolve_email_runtime_value('SMTP_USE_TLS')

    if not effective_host or not str(effective_host).strip():
        return {
            'valid': False,
            'latency_ms': None,
            'message': 'Cannot validate SMTP: no SMTP host is configured or provided.',
        }

    try:
        port_int = int(effective_port) if effective_port is not None else 587
        if not (1 <= port_int <= 65535):
            raise ValueError()
    except (TypeError, ValueError):
        return {
            'valid': False,
            'latency_ms': None,
            'message': 'SMTP port must be an integer between 1 and 65535.',
        }

    host_str = str(effective_host).strip()
    t0 = time.perf_counter()

    try:
        server = smtplib.SMTP(timeout=5)
        server.connect(host_str, port_int)
        if effective_use_tls:
            server.starttls()
        if effective_username and effective_password and _has_real_secret(effective_username) and _has_real_secret(effective_password):
            server.login(str(effective_username).strip(), str(effective_password).strip())
        server.noop()
        try:
            server.quit()
        except Exception:
            pass

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            'valid': True,
            'latency_ms': latency_ms,
            'message': f"SMTP server '{host_str}:{port_int}' connected and authenticated successfully ({latency_ms}ms).",
        }
    except smtplib.SMTPAuthenticationError as auth_err:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            'valid': False,
            'latency_ms': latency_ms,
            'message': f"SMTP authentication failed on '{host_str}:{port_int}': invalid username or password.",
        }
    except (smtplib.SMTPConnectError, socket.timeout, TimeoutError, OSError) as conn_err:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            'valid': False,
            'latency_ms': latency_ms,
            'message': f"SMTP connection to '{host_str}:{port_int}' timed out or failed: {str(conn_err)[:150]}",
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        sanitized = re.sub(r'password[:=]\s*\S+', 'password=[redacted]', str(exc), flags=re.IGNORECASE)
        return {
            'valid': False,
            'latency_ms': latency_ms,
            'message': f"SMTP validation failed: {sanitized[:180]}",
        }


# ── Existing-Objects Safety Protection ────────────────────────────────────────

def check_storage_existing_objects_safety(new_provider=None, new_bucket=None, new_endpoint=None):
    """Ensure that modifying storage configuration does not silently strand existing stored files.
    If existing StoredObject records depend on the current Cloudflare R2 bucket or endpoint,
    modifying them requires data migration and is rejected with HTTP 422.
    """
    try:
        existing_r2_count = StoredObject.query.filter_by(storage_provider='r2').count()
    except Exception:
        existing_r2_count = 0

    if existing_r2_count > 0:
        current_bucket = resolve_storage_runtime_value('R2_BUCKET_NAME')
        if not current_bucket:
            first_obj = StoredObject.query.filter_by(storage_provider='r2').filter(StoredObject.bucket_name.isnot(None)).first()
            if first_obj:
                current_bucket = first_obj.bucket_name

        if new_bucket is not None:
            cleaned_new_bucket = str(new_bucket).strip()
            cleaned_curr_bucket = str(current_bucket).strip() if current_bucket else ''
            if cleaned_new_bucket and (not cleaned_curr_bucket or cleaned_new_bucket != cleaned_curr_bucket):
                raise settings_service.SettingsError(
                    f"Cannot modify R2_BUCKET_NAME: {existing_r2_count} existing file(s) depend on bucket '{cleaned_curr_bucket or cleaned_new_bucket}'. "
                    "Changing the bucket would make existing files inaccessible. Storage migration is required before changing buckets.",
                    422,
                )

        current_endpoint = resolve_storage_runtime_value('R2_ENDPOINT_URL')
        if new_endpoint is not None:
            cleaned_new_ep = str(new_endpoint).strip().rstrip('/')
            cleaned_curr_ep = str(current_endpoint).strip().rstrip('/') if current_endpoint else ''
            if cleaned_new_ep and (not cleaned_curr_ep or cleaned_new_ep != cleaned_curr_ep):
                raise settings_service.SettingsError(
                    f"Cannot modify R2_ENDPOINT_URL: {existing_r2_count} existing file(s) depend on endpoint '{cleaned_curr_ep or cleaned_new_ep}'. "
                    "Changing the endpoint would make existing files inaccessible. Storage migration is required before changing endpoints.",
                    422,
                )

        if new_provider is not None:
            cleaned_prov = str(new_provider).strip().lower()
            if cleaned_prov == 'local':
                raise settings_service.SettingsError(
                    f"Cannot switch OBJECT_STORAGE_PROVIDER to 'local': {existing_r2_count} existing file(s) are stored in Cloudflare R2. "
                    "Data migration is required before switching back to local storage.",
                    422,
                )


# ── Unified Technical Settings Mutation ───────────────────────────────────────

def update_technical_settings(updates, user_id):
    """Atomically validate and persist technical settings across AI, Storage, Email, and Drive.
    Enforces format constraints and existing-files protection before writing to SystemConfig.
    Rolls back entirely on failure.
    """
    if not isinstance(updates, dict) or not updates:
        from app.services.system_admin_service import get_technical_settings
        return get_technical_settings()

    updates = normalize_refinement_updates(updates)

    # 1. Allowlist enforcement
    unauthorized = [k for k in updates.keys() if k not in ALL_APPROVED_TECHNICAL_SETTING_KEYS]
    if unauthorized:
        raise settings_service.SettingsError(f"Cannot configure unauthorized setting '{unauthorized[0]}'.", 422)

    coerced_updates = {}

    # 2. Separation and validation by provider subsystem
    # A. Storage validation
    has_storage_updates = any(k in APPROVED_STORAGE_SETTING_KEYS for k in updates)
    if has_storage_updates:
        storage_provider = updates.get('OBJECT_STORAGE_PROVIDER')
        target_bucket = updates.get('R2_BUCKET_NAME')
        target_endpoint = updates.get('R2_ENDPOINT_URL')
        target_access = updates.get('R2_ACCESS_KEY_ID')
        target_secret = updates.get('R2_SECRET_ACCESS_KEY')
        target_region = updates.get('R2_REGION')
        target_prefix = updates.get('OBJECT_STORAGE_BUCKET_PREFIX')

        # Check existing-files safety
        check_storage_existing_objects_safety(
            new_provider=storage_provider,
            new_bucket=target_bucket,
            new_endpoint=target_endpoint,
        )

        if storage_provider is not None:
            prov_str = str(storage_provider).strip().lower()
            if prov_str not in {'local', 'r2'}:
                raise settings_service.SettingsError(f"OBJECT_STORAGE_PROVIDER must be 'local' or 'r2', got '{prov_str}'.", 422)
            coerced_updates['OBJECT_STORAGE_PROVIDER'] = prov_str

        if target_prefix is not None:
            prefix_str = str(target_prefix).strip().strip('/')
            if prefix_str and not re.match(r'^[a-zA-Z0-9_\-]+$', prefix_str):
                raise settings_service.SettingsError("OBJECT_STORAGE_BUCKET_PREFIX must be a valid alphanumeric slug.", 422)
            coerced_updates['OBJECT_STORAGE_BUCKET_PREFIX'] = prefix_str

        if target_region is not None:
            coerced_updates['R2_REGION'] = str(target_region).strip() or 'auto'

        if target_bucket is not None:
            coerced_updates['R2_BUCKET_NAME'] = str(target_bucket).strip()

        if target_endpoint is not None:
            coerced_updates['R2_ENDPOINT_URL'] = str(target_endpoint).strip()

        if target_access is not None:
            coerced_updates['R2_ACCESS_KEY_ID'] = str(target_access).strip()

        if target_secret is not None:
            coerced_updates['R2_SECRET_ACCESS_KEY'] = str(target_secret).strip()

    # B. Email/SMTP validation
    has_email_updates = any(k in APPROVED_EMAIL_SETTING_KEYS for k in updates)
    if has_email_updates:
        target_host = updates.get('SMTP_HOST')
        target_port = updates.get('SMTP_PORT')
        target_user = updates.get('SMTP_USERNAME')
        target_pass = updates.get('SMTP_PASSWORD')
        target_tls = updates.get('SMTP_USE_TLS')
        target_from = updates.get('MAIL_FROM')

        if target_host is not None:
            coerced_updates['SMTP_HOST'] = str(target_host).strip()

        if target_port is not None:
            try:
                p_int = int(target_port)
                if not (1 <= p_int <= 65535):
                    raise ValueError()
                coerced_updates['SMTP_PORT'] = str(p_int)
            except (TypeError, ValueError):
                raise settings_service.SettingsError("SMTP_PORT must be an integer between 1 and 65535.", 422)

        if target_user is not None:
            coerced_updates['SMTP_USERNAME'] = str(target_user).strip()

        if target_pass is not None:
            coerced_updates['SMTP_PASSWORD'] = str(target_pass).strip()

        if target_tls is not None:
            tls_bool = target_tls is True or str(target_tls).strip().lower() in {'true', '1', 'yes', 'on'}
            coerced_updates['SMTP_USE_TLS'] = 'true' if tls_bool else 'false'

        if target_from is not None:
            from_str = str(target_from).strip()
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', from_str):
                raise settings_service.SettingsError("MAIL_FROM must be a valid email address.", 422)
            coerced_updates['MAIL_FROM'] = from_str

    # C. Google Drive settings
    if 'google_drive_root_folder_id' in updates:
        val = updates['google_drive_root_folder_id']
        coerced_updates['google_drive_root_folder_id'] = str(val).strip() if val else ''

    if 'GOOGLE_DRIVE_SHARED_DRIVE_ID' in updates:
        val = updates['GOOGLE_DRIVE_SHARED_DRIVE_ID']
        coerced_updates['GOOGLE_DRIVE_SHARED_DRIVE_ID'] = str(val).strip() if val else ''

    # D. AI Provider validation (delegated to existing Phase 3 logic)
    has_ai_updates = any(k in APPROVED_AI_SETTING_KEYS for k in updates)
    if has_ai_updates:
        from app.services.system_admin_service import _validate_model_id
        for key in APPROVED_AI_SETTING_KEYS:
            if key not in updates:
                continue
            val = updates[key]
            if key in ('GEMINI_API_KEY', 'GROQ_API_KEY', 'OPENROUTER_API_KEY'):
                if val is not None and not str(val).strip():
                    raise settings_service.SettingsError(f"{key} cannot be empty.", 422)
                coerced_updates[key] = str(val).strip() if val else ''
            elif key in ('GEMINI_MODEL', 'GROQ_MODEL', 'OPENROUTER_MODEL'):
                model_str = str(val).strip()
                if not model_str:
                    raise settings_service.SettingsError(f"{key} cannot be empty.", 422)
                provider_name = key.split('_')[0].lower()
                key_name = f"{provider_name.upper()}_API_KEY"
                candidate_key = coerced_updates.get(key_name)
                normalized_model = _validate_model_id(provider_name, model_str, api_key=candidate_key)
                coerced_updates[key] = normalized_model
            elif key == 'AI_PROVIDER_ORDER':
                if isinstance(val, str):
                    order = [item.strip().lower() for item in val.split(',') if item.strip()]
                elif isinstance(val, (list, tuple)):
                    order = [str(item).strip().lower() for item in val if str(item).strip()]
                else:
                    raise settings_service.SettingsError('AI_PROVIDER_ORDER must be a list or comma-separated string.', 422)
                valid_providers = {'gemini', 'groq', 'openrouter'}
                invalid = [p for p in order if p not in valid_providers]
                if invalid:
                    raise settings_service.SettingsError(f"Invalid provider(s) in AI_PROVIDER_ORDER: {', '.join(invalid)}.", 422)
                if not order:
                    raise settings_service.SettingsError('AI_PROVIDER_ORDER must contain at least one provider.', 422)
                coerced_updates[key] = ','.join(order)
            elif key == 'AI_REQUEST_TIMEOUT_SECONDS':
                try:
                    timeout_int = int(val)
                    if not (5 <= timeout_int <= 120):
                        raise ValueError()
                    coerced_updates[key] = str(timeout_int)
                except (TypeError, ValueError):
                    raise settings_service.SettingsError('AI_REQUEST_TIMEOUT_SECONDS must be an integer between 5 and 120.', 422)
            elif key == 'AI_TEMPERATURE':
                try:
                    temp_float = float(val)
                    if not (0.0 <= temp_float <= 2.0):
                        raise ValueError()
                    coerced_updates[key] = str(temp_float)
                except (TypeError, ValueError):
                    raise settings_service.SettingsError('AI_TEMPERATURE must be a float between 0.0 and 2.0.', 422)
            elif key == 'AI_MAX_OUTPUT_TOKENS':
                try:
                    tokens_int = int(val)
                    if not (100 <= tokens_int <= 16000):
                        raise ValueError()
                    coerced_updates[key] = str(tokens_int)
                except (TypeError, ValueError):
                    raise settings_service.SettingsError('AI_MAX_OUTPUT_TOKENS must be an integer between 100 and 16000.', 422)
            elif key == 'AI_MAX_PROMPT_CHARS':
                try:
                    chars_int = int(val)
                    if not (500 <= chars_int <= 100000):
                        raise ValueError()
                    coerced_updates[key] = str(chars_int)
                except (TypeError, ValueError):
                    raise settings_service.SettingsError('AI_MAX_PROMPT_CHARS must be an integer between 500 and 100000.', 422)
            elif key == 'AI_DOCUMENT_CLASSIFICATION_ENABLED':
                bool_val = parse_refinement_boolean(val)
                coerced_updates[key] = 'true' if bool_val else 'false'

    if not coerced_updates:
        from app.services.system_admin_service import get_technical_settings
        return get_technical_settings()

    # 3. Pre-encrypt secrets before beginning database mutation
    prepared_records = []
    for key, value_to_store in coerced_updates.items():
        is_secret = key in ALL_APPROVED_TECHNICAL_SECRET_KEYS
        val_type = 'secret' if is_secret else 'string'
        desc = f'Technical setting for {key}'
        stored_val = settings_service._encrypt_secret_value(value_to_store) if is_secret else value_to_store
        prepared_records.append((key, val_type, desc, is_secret, stored_val))

    # 4. Atomic database persistence
    try:
        for key, val_type, desc, is_secret, stored_val in prepared_records:
            config_entry = SystemConfig.query.filter_by(key=key).first()
            if not config_entry:
                config_entry = SystemConfig(
                    key=key,
                    value_type=val_type,
                    description=desc,
                    is_encrypted=is_secret,
                    updated_by=int(user_id) if user_id else None,
                )
                db.session.add(config_entry)

            config_entry.value = stored_val
            config_entry.is_encrypted = is_secret
            config_entry.value_type = val_type
            config_entry.updated_by = int(user_id) if user_id else None

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to atomically persist technical settings: %s", exc)
        raise settings_service.SettingsError(f"Database error saving settings: {exc}", 500)

    # 5. Audit logging with sanitized secrets
    sanitized_audit_data = {}
    for k, v in coerced_updates.items():
        if k in ALL_APPROVED_TECHNICAL_SECRET_KEYS:
            sanitized_audit_data[k] = '[redacted]'
        else:
            sanitized_audit_data[k] = v

    try:
        audit_service.log_action(
            user_id=int(user_id) if user_id else 0,
            action='update',
            entity_type='system_config',
            entity_id=0,
            old_value=None,
            new_value=sanitized_audit_data,
        )
    except Exception:
        pass

    from app.services.system_admin_service import get_technical_settings, get_ai_runtime_settings
    # For compatibility with existing callers expecting a flat settings dict containing updated keys:
    flat_result = {}
    flat_result.update(get_ai_runtime_settings())
    flat_result.update(get_storage_runtime_settings())
    flat_result.update(get_email_runtime_settings())
    flat_result.update(get_drive_runtime_settings())
    return flat_result


def delete_technical_setting_override(key, user_id):
    """Delete a database override in SystemConfig to revert to environment fallback."""
    if key == 'provider_refinement_enabled':
        key = 'AI_DOCUMENT_CLASSIFICATION_ENABLED'
    if key not in ALL_APPROVED_TECHNICAL_SETTING_KEYS:
        raise settings_service.SettingsError(f"Cannot reset unauthorized setting '{key}'.", 422)

    # If deleting an R2 bucket or endpoint override, check if existing files depend on it
    if key in ('R2_BUCKET_NAME', 'R2_ENDPOINT_URL', 'OBJECT_STORAGE_PROVIDER'):
        check_storage_existing_objects_safety()

    config_entry = SystemConfig.query.filter_by(key=key).first()
    if config_entry:
        db.session.delete(config_entry)
        db.session.commit()

        try:
            audit_service.log_action(
                user_id=int(user_id) if user_id else 0,
                action='delete',
                entity_type='system_config',
                entity_id=config_entry.id or 0,
                old_value={'key': key},
                new_value=None,
            )
        except Exception:
            pass

    from app.services.system_admin_service import get_ai_runtime_settings
    flat_result = {}
    flat_result.update(get_ai_runtime_settings())
    flat_result.update(get_storage_runtime_settings())
    flat_result.update(get_email_runtime_settings())
    flat_result.update(get_drive_runtime_settings())
    return flat_result
