import concurrent.futures
import errno
import logging
import os
import re
import time
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from app.services.matcher_runtime_settings import normalize_refinement_updates, parse_refinement_boolean

logger = logging.getLogger(__name__)

_unreadable_override_warned_at = {}


def _warn_unreadable_override_bounded(key):
    now = time.time()
    last_warn = _unreadable_override_warned_at.get(key, 0)
    if now - last_warn > 300:
        _unreadable_override_warned_at[key] = now
        logger.warning(
            f"Database override for technical setting '{key}' is invalid or unreadable; "
            "falling back to environment or default configuration."
        )


# Authoritative baseline allowlists grounded in COMET configuration and provider support
APPROVED_AI_MODELS_BY_PROVIDER = {
    'gemini': {
        'gemini-3.5-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.5-pro',
        'gemini-3.1-flash-lite',
        'gemini-2.5-flash',
        'gemini-2.5-pro',
        'gemini-2.0-flash',
        'gemini-2.0-flash-lite',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-flash-latest',
    },
    'groq': {
        'llama-3.1-8b-instant',
        'llama-3.3-70b-versatile',
        'llama-3.1-70b-versatile',
        'mixtral-8x7b-32768',
        'gemma2-9b-it',
        'qwen-2.5-32b',
        'deepseek-r1-distill-llama-70b',
    },
    'openrouter': {
        'openai/gpt-4o-mini',
        'openai/gpt-4o',
        'anthropic/claude-3-5-sonnet',
        'anthropic/claude-sonnet-4',
        'meta-llama/llama-3.1-8b-instruct',
        'google/gemini-2.0-flash-001',
        'google/gemini-flash-1.5',
        'qwen/qwen-2.5-72b-instruct',
    },
}


def fetch_remote_model_catalog(provider, api_key=None, timeout=5):
    """Fetch available model IDs from provider's authenticated read-only endpoint,

    filtered by compatibility with COMET's text generation requirements.
    Returns a set of normalized model identifiers available with the candidate or configured key.
    Raises SettingsError if the network call times out, upstream returns an error,
    or if no credential is provided or configured.
    """
    provider_name = str(provider or '').strip().lower()
    if provider_name not in {'gemini', 'groq', 'openrouter'}:
        raise settings_service.SettingsError(f"Unsupported provider '{provider}'.", 422)

    key_name = f"{provider_name.upper()}_API_KEY"
    resolved_key = api_key if (api_key and str(api_key).strip()) else resolve_ai_runtime_value(key_name)
    if not resolved_key or not _has_real_secret(resolved_key):
        raise settings_service.SettingsError(
            f"Cannot validate model availability for {provider_name}: no API key is configured or provided. "
            f"Please supply a valid {key_name} to verify model access.",
            422,
        )

    key_str = str(resolved_key).strip()
    if provider_name == 'groq' and ',' in key_str:
        from app.services.ai_connection import groq_api_keys
        keys = groq_api_keys(key_str)
        if not keys:
            raise settings_service.SettingsError('No Groq API keys are configured.', 422)
        for key in keys:
            try:
                return fetch_remote_model_catalog(provider_name, api_key=key, timeout=timeout)
            except settings_service.SettingsError:
                continue
        raise settings_service.SettingsError('Unable to fetch the model catalog with any configured Groq key.', 422)
    from app.services.ai_connection import _safe_urlopen, _sanitize_upstream_error_body

    try:
        if provider_name == 'gemini':
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={urllib.parse.quote(key_str)}"
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'COMET/1.0', 'Accept': 'application/json'},
                method='GET',
            )
            with _safe_urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            models = set()
            for item in data.get('models', []):
                # Filter by capability: must support generateContent
                methods = item.get('supportedGenerationMethods') or []
                if methods and 'generateContent' not in methods:
                    continue
                name = item.get('name', '')
                if name.startswith('models/'):
                    name = name[7:]
                if name:
                    models.add(name)
            return models

        elif provider_name == 'groq':
            url = 'https://api.groq.com/openai/v1/models'
            req = urllib.request.Request(
                url,
                headers={
                    'Authorization': f'Bearer {key_str}',
                    'User-Agent': 'COMET/1.0',
                    'Accept': 'application/json',
                },
                method='GET',
            )
            with _safe_urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            models = set()
            # Non-chat / non-text-generation models in Groq:
            # - Speech-to-text / Audio transcription (e.g. whisper-*, distil-whisper-*)
            # - Text-to-speech / Audio generation (e.g. canopylabs/orpheus-*, playht/*)
            # - Guardrail / classification-only or embedding models
            unsupported_groq_prefixes = (
                'whisper-',
                'distil-whisper-',
                'canopylabs/',
                'playht/',
                'tts-',
            )
            known_compatible_groq_models = APPROVED_AI_MODELS_BY_PROVIDER.get('groq', set())
            for item in data.get('data', []):
                mid = str(item.get('id') or '').strip()
                if not mid:
                    continue
                # Exclude transcription, speech synthesis, and audio models
                if any(mid.lower().startswith(prefix) for prefix in unsupported_groq_prefixes):
                    continue
                if 'whisper' in mid.lower() or 'orpheus' in mid.lower() or 'tts' in mid.lower():
                    continue

                # Check if item exposes capability or chat metadata
                # If explicit chat compatibility or metadata is absent, combine catalog presence
                # with compatibility rule for COMET's chat-completion API
                is_explicitly_chat = False
                if item.get('chat_completion') is True:
                    is_explicitly_chat = True
                elif item.get('type') == 'chat':
                    is_explicitly_chat = True
                elif mid in known_compatible_groq_models:
                    is_explicitly_chat = True

                if is_explicitly_chat:
                    models.add(mid)
            return models

        elif provider_name == 'openrouter':
            url = 'https://openrouter.ai/api/v1/models'
            req = urllib.request.Request(
                url,
                headers={
                    'Authorization': f'Bearer {key_str}',
                    'User-Agent': 'COMET/1.0',
                    'Accept': 'application/json',
                },
                method='GET',
            )
            with _safe_urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            models = set()
            for item in data.get('data', []):
                mid = str(item.get('id') or '').strip()
                if not mid:
                    continue

                architecture = item.get('architecture') or {}
                input_modalities = architecture.get('input_modalities')
                output_modalities = architecture.get('output_modalities')
                modality = str(architecture.get('modality') or '').lower()

                # If structured input_modalities / output_modalities are provided:
                if input_modalities is not None or output_modalities is not None:
                    norm_inputs = [str(m).strip().lower() for m in (input_modalities or [])]
                    norm_outputs = [str(m).strip().lower() for m in (output_modalities or [])]
                    # Must support text input
                    if 'text' not in norm_inputs:
                        continue
                    # Must support text output (exclude audio-only, image-only, embedding-only)
                    if 'text' not in norm_outputs:
                        continue
                else:
                    # Fallback to modality string if list modalities are absent
                    if '->' in modality:
                        inp, out = modality.split('->', 1)
                        if 'text' not in inp or 'text' not in out:
                            continue
                    elif modality and 'text' not in modality:
                        continue

                models.add(mid)
            return models

    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode('utf-8', errors='replace')[:300]
        sanitized = _sanitize_upstream_error_body(raw_body)
        raise settings_service.SettingsError(
            f"Failed to query {provider_name} model catalog: upstream returned HTTP {exc.code} ({sanitized or exc.reason}).",
            422,
        )
    except urllib.error.URLError as exc:
        sanitized = _sanitize_upstream_error_body(str(exc.reason if hasattr(exc, 'reason') else exc))
        raise settings_service.SettingsError(
            f"Failed to query {provider_name} model catalog: network error or timeout ({sanitized}).",
            422,
        )
    except settings_service.SettingsError:
        raise
    except Exception as exc:
        sanitized = _sanitize_upstream_error_body(str(exc))
        raise settings_service.SettingsError(
            f"Failed to query {provider_name} model catalog: {sanitized}.",
            422,
        )


def _validate_model_id(provider, model_name, api_key=None):
    """Validate model identifier format and availability against provider catalogs.

    Normalizes 'models/gemini-...' to 'gemini-...'.
    Performs syntax validation and validates the model against the authenticated provider
    catalog accessible with the candidate or configured API credential.
    Fail-closed: membership in a static allowlist is not used as a bypass when no credential exists.
    Note: Read-only model catalog validation confirms the model exists in the provider's active
    catalog; account-specific generation entitlement or quota exhaustion at runtime is enforced
    dynamically during inference.
    """
    m = str(model_name or '').strip()
    if not m:
        raise settings_service.SettingsError(f"Model identifier for {provider} cannot be empty.", 422)
    if any(c in m for c in ' \t\r\n\'"<>;&|$'):
        raise settings_service.SettingsError(f"Model identifier for {provider} contains invalid characters.", 422)

    # 1. Syntax & Prefix Normalization
    if provider == 'gemini':
        clean_m = m[7:] if m.startswith('models/') else m
        if not clean_m.startswith('gemini-'):
            raise settings_service.SettingsError(
                f"Invalid model '{m}' for Gemini. Gemini model identifiers must start with 'gemini-'.",
                422,
            )
        if not re.match(r'^gemini-[a-zA-Z0-9_\.\-]+$', clean_m):
            raise settings_service.SettingsError(f"Malformed Gemini model identifier '{m}'.", 422)
        target_model = clean_m

    elif provider == 'groq':
        if not re.match(r'^[a-zA-Z0-9_\.\-]+(/[a-zA-Z0-9_\.\-]+)?$', m):
            raise settings_service.SettingsError(
                f"Malformed Groq model identifier '{m}'. Expected model name format (e.g. 'llama-3.1-8b-instant').",
                422,
            )
        target_model = m

    elif provider == 'openrouter':
        if '/' not in m or not re.match(r'^[a-zA-Z0-9_\.\-]+/[a-zA-Z0-9_\.\-\:\+]+$', m):
            raise settings_service.SettingsError(
                f"Malformed OpenRouter model identifier '{m}'. OpenRouter models require 'author/model' format (e.g. 'openai/gpt-4o-mini').",
                422,
            )
        target_model = m

    else:
        raise settings_service.SettingsError(f"Unsupported AI provider '{provider}'.", 422)

    # 2. Availability Check: Authenticated live catalog retrieved using provider credential
    remote_models = fetch_remote_model_catalog(provider, api_key=api_key)
    if target_model not in remote_models:
        raise settings_service.SettingsError(
            f"Model '{target_model}' is not available in the {provider} model catalog accessible with this credential.",
            422,
        )

    return target_model

from flask import current_app
from sqlalchemy import text

from app.extensions import db
from app.logging_config import sanitize_text
from app.models import AuditLog, SystemConfig, SystemOperationalEvent
from app.models.backup import DbBackupRecord
from app.services import maintenance_service, object_storage_service, settings_service
from app.utils.datetime import to_iso_utc


def get_overview():
    """Build a comprehensive operational snapshot of system health, dependencies,
    background processing, recent incidents, database backups, and integrations.
    """
    # 1. Probe dependencies safely with bounded timeouts
    dependencies = _check_dependencies()

    # 2. Legacy readiness snapshot (retained for backward compatibility;
    # reuse precomputed object storage result to eliminate duplicate R2 round-trip)
    storage_dep = dependencies.get('object_storage')
    object_storage_check = None
    if storage_dep:
        object_storage_check = {
            'key': 'object_storage',
            'status': 'ready' if storage_dep.get('status') == 'healthy' else 'warning',
            'message': storage_dep.get('message', ''),
        }
    readiness = settings_service.get_readiness_snapshot(object_storage_check=object_storage_check)

    # 3. Overall health rollup
    health_summary = _rollup_system_health(dependencies, readiness)

    # 4. Background processing summary
    background = _get_background_processing(dependencies)

    # 5. Recent operational incidents (up to 5 ERROR/CRITICAL events)
    recent_incidents = _get_recent_operational_incidents()

    # 6. Recent administrative & security audit events (up to 5 privileged events)
    recent_admin_activity = _get_recent_admin_audit_activity()

    # 7. Database backup status summary
    backup_summary = _get_latest_backup_summary()

    # 8. Provider & runtime metadata (configuration presence only, no live AI calls)
    providers = _provider_metadata()
    runtime = _runtime_metadata()

    return {
        'system_health': health_summary,
        'dependencies': dependencies,
        'background_processing': background,
        'recent_incidents': recent_incidents,
        'recent_admin_activity': recent_admin_activity,
        'database_backup': backup_summary,
        'providers': providers,
        'runtime': runtime,
        'readiness': readiness,
    }


def get_technical_settings():
    from app.services import drive_service, integration_config_service
    return {
        'providers': _provider_metadata(),
        'runtime': _runtime_metadata(),
        'readiness': settings_service.get_readiness_snapshot(),
        'ai_settings': get_ai_runtime_settings(),
        'storage_settings': integration_config_service.get_storage_runtime_settings(),
        'email_settings': integration_config_service.get_email_runtime_settings(),
        'drive_settings': drive_service.get_connection_status(),
    }


def update_technical_settings(updates, user_id):
    from app.services import integration_config_service
    updates = normalize_refinement_updates(updates)
    if isinstance(updates, dict) and updates and all(k in APPROVED_AI_SETTING_KEYS for k in updates.keys() if k not in ('confirm_password', 'step_up_password')):
        return update_ai_runtime_settings(updates, user_id=user_id)
    return integration_config_service.update_technical_settings(updates, user_id=user_id)


def delete_technical_setting_override(key, user_id):
    from app.services import integration_config_service
    if key == 'provider_refinement_enabled':
        key = 'AI_DOCUMENT_CLASSIFICATION_ENABLED'
    if key in APPROVED_AI_SETTING_KEYS:
        return delete_ai_runtime_setting_override(key, user_id=user_id)
    return integration_config_service.delete_technical_setting_override(key, user_id=user_id)


# ── Dependency Probes ────────────────────────────────────────────────────────

def _check_dependencies():
    return {
        'postgres': _check_postgres(),
        'redis': _check_redis(),
        'celery_workers': _check_celery_workers(),
        'celery_beat': _check_celery_beat(),
        'object_storage': _check_object_storage(),
    }


def _check_postgres():
    t0 = time.perf_counter()
    checked_at = datetime.now(timezone.utc).isoformat()
    probe_engine = None
    try:
        # Avoid waiting for the shared application pool (QueuePool) and bound
        # both TCP connection establishment and query execution using NullPool
        # with isolated driver parameters.
        from sqlalchemy import create_engine, pool
        url = db.engine.url
        dialect_name = db.engine.dialect.name
        connect_args = {}
        if dialect_name == 'postgresql':
            connect_args['connect_timeout'] = 2
            connect_args['options'] = '-c statement_timeout=2000'

        probe_engine = create_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
        with probe_engine.connect() as conn:
            conn.execute(text("SELECT 1")).scalar()

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            'name': 'PostgreSQL Database',
            'key': 'postgres',
            'status': 'healthy',
            'status_label': 'Healthy',
            'latency_ms': latency_ms,
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': f'Database responsive (query completed in {latency_ms}ms).',
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            'name': 'PostgreSQL Database',
            'key': 'postgres',
            'status': 'unavailable',
            'status_label': 'Unavailable',
            'latency_ms': latency_ms,
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': f'Database probe failed ({sanitize_text(str(exc))[:200]}).',
        }
    finally:
        if probe_engine is not None:
            try:
                probe_engine.dispose()
            except Exception:
                pass


def _check_redis():
    t0 = time.perf_counter()
    checked_at = datetime.now(timezone.utc).isoformat()
    broker_url = current_app.config.get('CELERY_BROKER_URL', '')
    if broker_url.startswith('memory://'):
        return {
            'name': 'Redis Broker & Cache',
            'key': 'redis',
            'status': 'not_verified',
            'status_label': 'Not Verified',
            'latency_ms': None,
            'checked_at': checked_at,
            'is_live_probe': False,
            'message': 'In-memory broker configured (probe skipped in test environment).',
        }
    try:
        client = maintenance_service._redis_client(socket_timeout=2)
        if client is None:
            return {
                'name': 'Redis Broker & Cache',
                'key': 'redis',
                'status': 'unavailable',
                'status_label': 'Unavailable',
                'latency_ms': None,
                'checked_at': checked_at,
                'is_live_probe': True,
                'message': 'Redis connection client could not be initialized.',
            }
        pong = client.ping()
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if pong:
            return {
                'name': 'Redis Broker & Cache',
                'key': 'redis',
                'status': 'healthy',
                'status_label': 'Healthy',
                'latency_ms': latency_ms,
                'checked_at': checked_at,
                'is_live_probe': True,
                'message': f'Redis responsive (ping completed in {latency_ms}ms).',
            }
        return {
            'name': 'Redis Broker & Cache',
            'key': 'redis',
            'status': 'degraded',
            'status_label': 'Degraded',
            'latency_ms': latency_ms,
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': 'Redis ping returned unexpected non-truthy response.',
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            'name': 'Redis Broker & Cache',
            'key': 'redis',
            'status': 'unavailable',
            'status_label': 'Unavailable',
            'latency_ms': latency_ms,
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': f'Redis ping failed ({sanitize_text(str(exc))[:200]}).',
        }


def _check_celery_workers():
    t0 = time.perf_counter()
    checked_at = datetime.now(timezone.utc).isoformat()
    broker_url = current_app.config.get('CELERY_BROKER_URL', '')
    if not broker_url or broker_url.startswith('memory://'):
        return {
            'name': 'Celery Background Workers',
            'key': 'celery_workers',
            'status': 'not_verified',
            'status_label': 'Not Verified',
            'worker_count': 0,
            'active_workers': [],
            'latency_ms': None,
            'checked_at': checked_at,
            'is_live_probe': False,
            'message': 'Worker inspection skipped for in-memory broker in test environment.',
        }
    try:
        from app.tasks import celery_app
        pings = celery_app.control.ping(timeout=0.5)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        active_workers = []
        if pings:
            for node_resp in pings:
                for node_name, resp in node_resp.items():
                    if isinstance(resp, dict) and resp.get('ok') == 'pong':
                        active_workers.append(node_name)
                    elif resp == 'pong' or resp == {'ok': 'pong'}:
                        active_workers.append(node_name)
        if active_workers:
            return {
                'name': 'Celery Background Workers',
                'key': 'celery_workers',
                'status': 'healthy',
                'status_label': 'Healthy',
                'worker_count': len(active_workers),
                'active_workers': active_workers,
                'latency_ms': latency_ms,
                'checked_at': checked_at,
                'is_live_probe': True,
                'message': f'{len(active_workers)} background worker(s) active and responsive.',
            }
        return {
            'name': 'Celery Background Workers',
            'key': 'celery_workers',
            'status': 'unavailable',
            'status_label': 'Unavailable',
            'worker_count': 0,
            'active_workers': [],
            'latency_ms': latency_ms,
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': 'No Celery background workers responded within timeout (500ms).',
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            'name': 'Celery Background Workers',
            'key': 'celery_workers',
            'status': 'unavailable',
            'status_label': 'Unavailable',
            'worker_count': 0,
            'active_workers': [],
            'latency_ms': latency_ms,
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': f'Worker inspection failed ({sanitize_text(str(exc))[:200]}).',
        }


def _check_celery_beat():
    checked_at = datetime.now(timezone.utc).isoformat()
    task_count = len(current_app.config.get('CELERY_BEAT_SCHEDULE') or {})
    broker_url = current_app.config.get('CELERY_BROKER_URL', '')
    if not broker_url or broker_url.startswith('memory://'):
        return {
            'name': 'Celery Beat Scheduler',
            'key': 'celery_beat',
            'status': 'not_verified',
            'status_label': 'Not Verified',
            'scheduled_tasks_count': task_count,
            'checked_at': checked_at,
            'is_live_probe': False,
            'message': 'Scheduler liveness probe skipped in in-memory test environment.',
        }

    schedule_paths = [
        'celerybeat-schedule',
        '/app/celerybeat-schedule',
        os.path.join(current_app.instance_path, 'celerybeat-schedule'),
    ]
    schedule_file = None
    for p in schedule_paths:
        if os.path.exists(p):
            schedule_file = p
            break

    if not schedule_file:
        return {
            'name': 'Celery Beat Scheduler',
            'key': 'celery_beat',
            'status': 'not_verified',
            'status_label': 'Not Verified',
            'scheduled_tasks_count': task_count,
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': 'Schedule database file not found on disk. Scheduler has not initialized.',
        }

    try:
        import fcntl
        fd = os.open(schedule_file, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return {
                'name': 'Celery Beat Scheduler',
                'key': 'celery_beat',
                'status': 'unavailable',
                'status_label': 'Unavailable',
                'scheduled_tasks_count': task_count,
                'checked_at': checked_at,
                'is_live_probe': True,
                'message': 'Schedule database file is unlocked. Celery Beat process is not running.',
            }
        except (BlockingIOError, OSError) as e:
            if getattr(e, 'errno', None) in (errno.EACCES, errno.EAGAIN):
                return {
                    'name': 'Celery Beat Scheduler',
                    'key': 'celery_beat',
                    'status': 'healthy',
                    'status_label': 'Healthy',
                    'scheduled_tasks_count': task_count,
                    'checked_at': checked_at,
                    'is_live_probe': True,
                    'message': f'Scheduler process active ({task_count} periodic tasks configured; schedule lock held).',
                }
            return {
                'name': 'Celery Beat Scheduler',
                'key': 'celery_beat',
                'status': 'degraded',
                'status_label': 'Degraded',
                'scheduled_tasks_count': task_count,
                'checked_at': checked_at,
                'is_live_probe': True,
                'message': f'Scheduler probe inconclusive ({sanitize_text(str(e))[:200]}).',
            }
        finally:
            os.close(fd)
    except Exception as exc:
        return {
            'name': 'Celery Beat Scheduler',
            'key': 'celery_beat',
            'status': 'not_verified',
            'status_label': 'Not Verified',
            'scheduled_tasks_count': task_count,
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': f'Scheduler liveness check inconclusive ({sanitize_text(str(exc))[:200]}).',
        }


def _check_object_storage():
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        provider = object_storage_service._provider()
        ready, msg = object_storage_service.provider_ready()
        status = 'healthy' if ready else 'degraded'
        return {
            'name': 'Object Storage',
            'key': 'object_storage',
            'provider': provider,
            'status': status,
            'status_label': 'Healthy' if ready else 'Degraded',
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': msg,
        }
    except Exception as exc:
        return {
            'name': 'Object Storage',
            'key': 'object_storage',
            'provider': 'unknown',
            'status': 'degraded',
            'status_label': 'Degraded',
            'checked_at': checked_at,
            'is_live_probe': True,
            'message': f'Object storage check error: {sanitize_text(str(exc))[:200]}',
        }


# ── Health Rollup ────────────────────────────────────────────────────────────

def _rollup_system_health(dependencies, readiness):
    pg_status = dependencies.get('postgres', {}).get('status', 'unknown')
    redis_status = dependencies.get('redis', {}).get('status', 'unknown')
    worker_status = dependencies.get('celery_workers', {}).get('status', 'unknown')
    beat_status = dependencies.get('celery_beat', {}).get('status', 'unknown')
    storage_status = dependencies.get('object_storage', {}).get('status', 'unknown')

    all_statuses = [pg_status, redis_status, worker_status, beat_status, storage_status]
    healthy_count = sum(1 for s in all_statuses if s == 'healthy')
    degraded_count = sum(1 for s in all_statuses if s == 'degraded')
    unavailable_count = sum(1 for s in all_statuses if s == 'unavailable')
    not_verified_count = sum(1 for s in all_statuses if s == 'not_verified')

    if pg_status == 'unavailable' or redis_status == 'unavailable':
        overall_status = 'unavailable'
    elif unavailable_count > 0 or degraded_count > 0:
        overall_status = 'degraded'
    elif healthy_count > 0:
        overall_status = 'healthy'
    else:
        overall_status = 'degraded'

    status_labels = {
        'healthy': 'Healthy',
        'degraded': 'Degraded',
        'unavailable': 'Unavailable',
        'not_verified': 'Not Verified',
    }

    return {
        'status': overall_status,
        'status_label': status_labels.get(overall_status, 'Unknown'),
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'total_checks': len(dependencies),
        'healthy_checks': healthy_count,
        'degraded_checks': degraded_count,
        'unavailable_checks': unavailable_count,
        'not_verified_checks': not_verified_count,
        # Backwards compatibility fields for existing tests:
        'ready_checks': healthy_count,
        'warning_checks': degraded_count,
        'disabled_checks': unavailable_count + not_verified_count,
    }


# ── Operational Snapshot Data ────────────────────────────────────────────────

def _get_background_processing(dependencies):
    worker_dep = dependencies.get('celery_workers', {})
    beat_dep = dependencies.get('celery_beat', {})

    task_failures = []
    try:
        failures = (
            SystemOperationalEvent.query
            .filter(
                SystemOperationalEvent.component == 'celery_worker',
                SystemOperationalEvent.severity.in_(['ERROR', 'CRITICAL']),
            )
            .order_by(SystemOperationalEvent.timestamp.desc())
            .limit(5)
            .all()
        )
        task_failures = [f.to_summary_dict() for f in failures]
    except Exception:
        pass

    beat_schedule_cfg = current_app.config.get('CELERY_BEAT_SCHEDULE') or {}
    scheduled_tasks = [
        {
            'name': name,
            'task': cfg.get('task'),
            'schedule': str(cfg.get('schedule')),
        }
        for name, cfg in beat_schedule_cfg.items()
    ]

    return {
        'workers': {
            'status': worker_dep.get('status', 'unknown'),
            'status_label': worker_dep.get('status_label', 'Unknown'),
            'count': worker_dep.get('worker_count', 0),
            'active_workers': worker_dep.get('active_workers', []),
            'message': worker_dep.get('message', ''),
        },
        'scheduler': {
            'status': beat_dep.get('status', 'unknown'),
            'status_label': beat_dep.get('status_label', 'Unknown'),
            'task_count': beat_dep.get('scheduled_tasks_count', len(scheduled_tasks)),
            'tasks': scheduled_tasks,
            'message': beat_dep.get('message', ''),
        },
        'recent_task_failures': task_failures,
    }


def _get_recent_operational_incidents():
    try:
        events = (
            SystemOperationalEvent.query
            .filter(SystemOperationalEvent.severity.in_(['ERROR', 'CRITICAL']))
            .order_by(SystemOperationalEvent.timestamp.desc())
            .limit(5)
            .all()
        )
        return [e.to_summary_dict() for e in events]
    except Exception:
        return []


def _get_recent_admin_audit_activity():
    try:
        privileged_entities = ('system_config', 'db_backup', 'audit_integrity_incident', 'route', 'security_boundary')
        privileged_actions = (
            'change_role', 'toggle_active', 'integrity_incident_opened', 'integrity_rebaseline',
            'unauthorized_role_access', 'cross_cluster_access_denied', 'cross_lgu_access_denied',
        )
        logs = (
            AuditLog.query
            .filter(
                db.or_(
                    AuditLog.entity_type.in_(privileged_entities),
                    AuditLog.action.in_(privileged_actions),
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(5)
            .all()
        )
        return [
            {
                'id': l.id,
                'action': l.action,
                'action_label': l.action.replace('_', ' ').capitalize(),
                'entity_type': l.entity_type,
                'entity_id': l.entity_id,
                'user_id': l.user_id,
                'user_email': l.actor.email if l.actor else None,
                'user_name': f"{l.actor.first_name} {l.actor.last_name}".strip() if l.actor else None,
                'created_at': to_iso_utc(l.created_at),
            }
            for l in logs
        ]
    except Exception:
        return []


def _get_latest_backup_summary():
    try:
        latest = DbBackupRecord.query.order_by(DbBackupRecord.created_at.desc()).first()
        total = DbBackupRecord.query.count()
        completed = DbBackupRecord.query.filter_by(status='completed').count()
        failed = DbBackupRecord.query.filter_by(status='failed').count()

        latest_dict = None
        if latest:
            latest_dict = {
                'id': latest.id,
                'filename': latest.filename,
                'status': latest.status,
                'status_label': 'Completed' if latest.status == 'completed' else ('Failed' if latest.status == 'failed' else latest.status.capitalize()),
                'byte_size': latest.byte_size,
                'byte_size_formatted': _format_bytes(latest.byte_size),
                'trigger_type': latest.trigger_type,
                'trigger_type_label': 'Scheduled' if latest.trigger_type == 'scheduled' else ('Manual' if latest.trigger_type == 'manual' else latest.trigger_type.capitalize()),
                'storage_provider': latest.storage_provider,
                'created_at': to_iso_utc(latest.created_at),
                'duration_seconds': round(latest.duration_seconds, 2) if latest.duration_seconds else None,
            }

        return {
            'latest': latest_dict,
            'total_count': total,
            'completed_count': completed,
            'failed_count': failed,
        }
    except Exception as exc:
        return {
            'latest': None,
            'total_count': 0,
            'completed_count': 0,
            'failed_count': 0,
            'error': sanitize_text(str(exc))[:200],
        }


def _format_bytes(size):
    if not size:
        return '0 B'
    size_float = float(size)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_float < 1024.0:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024.0
    return f"{size_float:.1f} TB"


# ── Metadata ─────────────────────────────────────────────────────────────────

def _provider_metadata():
    runtime_ai = resolve_all_ai_runtime_config()
    config = current_app.config
    ai_providers = [
        _provider('gemini', runtime_ai.get('GEMINI_MODEL'), runtime_ai.get('GEMINI_API_KEY')),
        _provider('groq', runtime_ai.get('GROQ_MODEL'), runtime_ai.get('GROQ_API_KEY')),
        _provider('openrouter', runtime_ai.get('OPENROUTER_MODEL'), runtime_ai.get('OPENROUTER_API_KEY')),
    ]
    return {
        'ai': {
            'provider_order': list(runtime_ai.get('AI_PROVIDER_ORDER') or []),
            'providers': ai_providers,
            'configured_count': sum(1 for provider in ai_providers if provider['configured']),
            'request_timeout_seconds': runtime_ai.get('AI_REQUEST_TIMEOUT_SECONDS'),
            'temperature': runtime_ai.get('AI_TEMPERATURE'),
            'max_output_tokens': runtime_ai.get('AI_MAX_OUTPUT_TOKENS'),
            'max_prompt_chars': runtime_ai.get('AI_MAX_PROMPT_CHARS'),
            'probe_mode': 'configuration_only',
            'probe_note': 'Configuration presence verified without exposing credentials; live AI prompts are never issued on dashboard load.',
        },
        'document_intelligence': {
            'ocr_max_pages': config.get('DOCUMENT_OCR_MAX_PAGES'),
            'provider_refinement_enabled': bool(resolve_ai_runtime_value('AI_DOCUMENT_CLASSIFICATION_ENABLED')),
            'aws_enabled': bool(config.get('DOCUMENT_AWS_ENABLED')),
            'textract_enabled': bool(config.get('DOCUMENT_AWS_ENABLED') and config.get('DOCUMENT_AWS_TEXTRACT_ENABLED')),
            'rekognition_enabled': bool(config.get('DOCUMENT_AWS_ENABLED') and config.get('DOCUMENT_AWS_REKOGNITION_ENABLED')),
            'aws_region': config.get('DOCUMENT_AWS_REGION'),
            'aws_max_sync_bytes': config.get('DOCUMENT_AWS_MAX_SYNC_BYTES'),
            'textract_feature_types': list(config.get('DOCUMENT_AWS_TEXTRACT_FEATURE_TYPES') or []),
            'rekognition_max_labels': config.get('DOCUMENT_AWS_REKOGNITION_MAX_LABELS'),
            'rekognition_min_confidence': config.get('DOCUMENT_AWS_REKOGNITION_MIN_CONFIDENCE'),
            'location_enabled': bool(config.get('DOCUMENT_AWS_LOCATION_ENABLED')),
            'location_language': config.get('DOCUMENT_AWS_LOCATION_LANGUAGE'),
            'language_tool_enabled': bool(config.get('DOCUMENT_LANGUAGE_TOOL_ENABLED')),
            'language_tool_language': config.get('DOCUMENT_LANGUAGE_TOOL_LANGUAGE'),
            'language_tool_timeout_seconds': config.get('DOCUMENT_LANGUAGE_TOOL_TIMEOUT_SECONDS'),
            'language_tool_max_chars': config.get('DOCUMENT_LANGUAGE_TOOL_MAX_CHARS'),
            'language_tool_min_confidence': config.get('DOCUMENT_LANGUAGE_TOOL_MIN_CONFIDENCE'),
        },
        'object_storage': {
            'provider': config.get('OBJECT_STORAGE_PROVIDER'),
            'environment': config.get('OBJECT_STORAGE_ENV'),
            'signed_url_ttl_seconds': config.get('OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS'),
            'r2_configured': all(bool(config.get(key)) for key in ('R2_ACCOUNT_ID', 'R2_BUCKET_NAME', 'R2_ENDPOINT_URL')),
        },
    }


def _runtime_metadata():
    config = current_app.config
    env = (
        config.get('ENV')
        or config.get('FLASK_ENV')
        or config.get('FLASK_CONFIG')
        or os.environ.get('FLASK_ENV')
        or os.environ.get('FLASK_CONFIG')
        or os.environ.get('APP_CONFIG')
        or 'development'
    )
    return {
        'environment': env,
        'app_name': config.get('APP_NAME'),
        'frontend_url': config.get('APP_FRONTEND_URL'),
        'public_magic_links_enabled': bool(config.get('ENABLE_PUBLIC_MAGIC_LINKS')),
        'celery_configured': bool(config.get('CELERY_BROKER_URL') and config.get('CELERY_RESULT_BACKEND')),
        'google_drive_enabled': bool(config.get('GOOGLE_DRIVE_ENABLED')),
    }


def _provider(name, model, secret):
    return {
        'name': name,
        'model': model,
        'configured': _has_real_secret(secret),
    }


def _has_real_secret(value):
    if not value:
        return False
    text_val = str(value).strip().lower()
    return bool(text_val and text_val not in {'changeme', 'change-me', 'placeholder', 'none', 'null'})


# ── AI Runtime Config Management ─────────────────────────────────────────────

APPROVED_AI_SECRET_KEYS = {
    'GEMINI_API_KEY',
    'GROQ_API_KEY',
    'OPENROUTER_API_KEY',
}

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

AI_DEFAULT_FALLBACKS = {
    'GEMINI_MODEL': 'gemini-3.5-flash',
    'GROQ_MODEL': 'llama-3.1-8b-instant',
    'OPENROUTER_MODEL': 'openai/gpt-4o-mini',
    'AI_PROVIDER_ORDER': ['gemini', 'groq', 'openrouter'],
    'AI_REQUEST_TIMEOUT_SECONDS': 30,
    'AI_TEMPERATURE': 0.2,
    'AI_MAX_OUTPUT_TOKENS': 1200,
    'AI_MAX_PROMPT_CHARS': 4000,
    'AI_DOCUMENT_CLASSIFICATION_ENABLED': False,
}


def mask_secret(value):
    """Mask a secret using masked indicator without revealing partial characters."""
    if not value:
        return None
    return '••••••••'


def resolve_ai_runtime_value(key):
    """Three-tier resolution: (1) SystemConfig, (2) current_app.config, (3) Default."""
    if key not in APPROVED_AI_SETTING_KEYS:
        return None

    raw_val = None
    try:
        config_entry = SystemConfig.query.filter_by(key=key).first()
        if config_entry and config_entry.value not in (None, ''):
            if config_entry.is_encrypted:
                try:
                    raw_val = settings_service._decrypt_secret_value(config_entry.value)
                except Exception:
                    _warn_unreadable_override_bounded(key)
            else:
                raw_val = config_entry.value
    except Exception:
        _warn_unreadable_override_bounded(key)

    if raw_val in (None, ''):
        env_val = current_app.config.get(key)
        if env_val not in (None, ''):
            raw_val = env_val

    if raw_val in (None, ''):
        raw_val = AI_DEFAULT_FALLBACKS.get(key)

    # Type coercion consistent with resolve_all_ai_runtime_config
    if key in ('AI_REQUEST_TIMEOUT_SECONDS', 'AI_MAX_OUTPUT_TOKENS', 'AI_MAX_PROMPT_CHARS'):
        try:
            return int(raw_val) if raw_val is not None else AI_DEFAULT_FALLBACKS.get(key)
        except (TypeError, ValueError):
            return AI_DEFAULT_FALLBACKS.get(key)
    elif key == 'AI_TEMPERATURE':
        try:
            return float(raw_val) if raw_val is not None else AI_DEFAULT_FALLBACKS.get(key)
        except (TypeError, ValueError):
            return AI_DEFAULT_FALLBACKS.get(key)
    elif key == 'AI_PROVIDER_ORDER':
        if isinstance(raw_val, str):
            return [item.strip().lower() for item in raw_val.split(',') if item.strip()]
        elif isinstance(raw_val, (list, tuple)):
            return [str(item).strip().lower() for item in raw_val if str(item).strip()]
        else:
            return AI_DEFAULT_FALLBACKS.get(key)
    elif key == 'AI_DOCUMENT_CLASSIFICATION_ENABLED':
        if isinstance(raw_val, bool):
            return raw_val
        if isinstance(raw_val, str):
            return raw_val.strip().lower() in {'true', '1', 'yes', 'on'}
        return bool(raw_val) if raw_val is not None else False

    return raw_val


def resolve_all_ai_runtime_config():
    """Resolve full dict of AI configuration with type coercion."""
    config_entries = {c.key: c for c in SystemConfig.query.filter(SystemConfig.key.in_(APPROVED_AI_SETTING_KEYS)).all()}

    resolved = {}
    for key in APPROVED_AI_SETTING_KEYS:
        raw_val = None
        if key in config_entries and config_entries[key].value not in (None, ''):
            entry = config_entries[key]
            if entry.is_encrypted:
                try:
                    raw_val = settings_service._decrypt_secret_value(entry.value)
                except Exception:
                    raw_val = None
                    _warn_unreadable_override_bounded(key)
            else:
                raw_val = entry.value

        if raw_val in (None, ''):
            raw_val = current_app.config.get(key)

        if raw_val in (None, ''):
            raw_val = AI_DEFAULT_FALLBACKS.get(key)

        # Type conversion
        if key in ('AI_REQUEST_TIMEOUT_SECONDS', 'AI_MAX_OUTPUT_TOKENS', 'AI_MAX_PROMPT_CHARS'):
            try:
                resolved[key] = int(raw_val) if raw_val is not None else AI_DEFAULT_FALLBACKS.get(key)
            except (TypeError, ValueError):
                resolved[key] = AI_DEFAULT_FALLBACKS.get(key)
        elif key == 'AI_TEMPERATURE':
            try:
                resolved[key] = float(raw_val) if raw_val is not None else AI_DEFAULT_FALLBACKS.get(key)
            except (TypeError, ValueError):
                resolved[key] = AI_DEFAULT_FALLBACKS.get(key)
        elif key == 'AI_PROVIDER_ORDER':
            if isinstance(raw_val, str):
                resolved[key] = [item.strip().lower() for item in raw_val.split(',') if item.strip()]
            elif isinstance(raw_val, (list, tuple)):
                resolved[key] = [str(item).strip().lower() for item in raw_val if str(item).strip()]
            else:
                resolved[key] = AI_DEFAULT_FALLBACKS.get(key)
        elif key == 'AI_DOCUMENT_CLASSIFICATION_ENABLED':
            if isinstance(raw_val, bool):
                resolved[key] = raw_val
            elif isinstance(raw_val, str):
                resolved[key] = raw_val.strip().lower() in {'true', '1', 'yes', 'on'}
            else:
                resolved[key] = bool(raw_val) if raw_val is not None else False
        else:
            resolved[key] = raw_val

    return resolved


def get_ai_runtime_settings():
    """Return dictionary of AI runtime settings with masked secrets, sources, and metadata."""
    configs = {c.key: c for c in SystemConfig.query.filter(SystemConfig.key.in_(APPROVED_AI_SETTING_KEYS)).all()}
    result = {}

    for key in APPROVED_AI_SETTING_KEYS:
        is_secret = key in APPROVED_AI_SECRET_KEYS
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
                    # Unreadable override: make observable and fall back safely
                    override_status = 'invalid_or_unreadable'
                    fallback_active = True
                    env_val = current_app.config.get(key)
                    if env_val not in (None, ''):
                        source = 'environment'
                        effective_val = env_val
                    else:
                        source = 'default'
                        effective_val = AI_DEFAULT_FALLBACKS.get(key)
                    override_error = f"Database override could not be decrypted; fallback to {source} is active."
                    _warn_unreadable_override_bounded(key)
            else:
                effective_val = db_entry.value
                override_status = 'active'
                source = 'database'
        elif current_app.config.get(key) not in (None, ''):
            source = 'environment'
            effective_val = current_app.config.get(key)
        else:
            source = 'default'
            effective_val = AI_DEFAULT_FALLBACKS.get(key)

        has_val = bool(effective_val and _has_real_secret(effective_val) if is_secret else effective_val not in (None, ''))

        masked = None
        if is_secret:
            masked = mask_secret(effective_val) if has_val else None
            public_val = None
        else:
            public_val = effective_val
            if key == 'AI_PROVIDER_ORDER':
                if isinstance(public_val, str):
                    public_val = [item.strip().lower() for item in public_val.split(',') if item.strip()]
                elif isinstance(public_val, (list, tuple)):
                    public_val = list(public_val)
            elif key in ('AI_REQUEST_TIMEOUT_SECONDS', 'AI_MAX_OUTPUT_TOKENS', 'AI_MAX_PROMPT_CHARS'):
                try:
                    public_val = int(public_val) if public_val is not None else AI_DEFAULT_FALLBACKS.get(key)
                except (TypeError, ValueError):
                    public_val = AI_DEFAULT_FALLBACKS.get(key)
            elif key == 'AI_TEMPERATURE':
                try:
                    public_val = float(public_val) if public_val is not None else AI_DEFAULT_FALLBACKS.get(key)
                except (TypeError, ValueError):
                    public_val = AI_DEFAULT_FALLBACKS.get(key)
            elif key == 'AI_DOCUMENT_CLASSIFICATION_ENABLED':
                if isinstance(public_val, bool):
                    pass
                elif isinstance(public_val, str):
                    public_val = public_val.strip().lower() in {'true', '1', 'yes', 'on'}
                else:
                    public_val = bool(public_val) if public_val is not None else False

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


def update_ai_runtime_settings(updates, user_id):
    """Validate, encrypt secrets, persist overrides in SystemConfig, and log audit."""
    if not isinstance(updates, dict):
        raise settings_service.SettingsError('Invalid settings payload: expected a dictionary.', 422)

    # Filter out auth helper fields if present
    updates = {k: v for k, v in updates.items() if k not in ('confirm_password', 'step_up_password')}
    updates = normalize_refinement_updates(updates)

    # 1. Reject unapproved keys
    unapproved = [k for k in updates.keys() if k not in APPROVED_AI_SETTING_KEYS]
    if unapproved:
        raise settings_service.SettingsError(
            f"Cannot configure unauthorized setting(s): {', '.join(unapproved)}. Only approved AI settings are configurable.",
            422,
        )

    # 2. Validate values and candidate credentials
    coerced_updates = {}
    for key, val in updates.items():
        if key in APPROVED_AI_SECRET_KEYS:
            # Empty / blank string means unchanged
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            val_str = str(val).strip()
            if len(val_str) < 8:
                raise settings_service.SettingsError(f'{key} must be at least 8 characters.', 422)

            # Enforce validation of the candidate credential before persistence
            provider_name = key.split('_')[0].lower()
            val_res = validate_ai_provider_credential(provider_name, api_key=val_str)
            if not val_res.get('valid'):
                err_msg = val_res.get('message') or f"Candidate credential for {provider_name} failed validation."
                raise settings_service.SettingsError(f"Validation failed for {key}: {err_msg}", 422)

            coerced_updates[key] = val_str
        elif key in ('GEMINI_MODEL', 'GROQ_MODEL', 'OPENROUTER_MODEL'):
            if val is None or not str(val).strip():
                raise settings_service.SettingsError(f'{key} cannot be empty.', 422)
            model_str = str(val).strip()
            provider_name = key.split('_')[0].lower()
            key_name = f"{provider_name.upper()}_API_KEY"
            # If a candidate credential was submitted in the same payload, check with candidate key
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
        return get_ai_runtime_settings()

    # 3. Apply updates to SystemConfig atomically
    # Pre-encrypt secrets before beginning database mutation to prevent partial state on encryption failure
    prepared_records = []
    for key, value_to_store in coerced_updates.items():
        is_secret = key in APPROVED_AI_SECRET_KEYS
        val_type = 'secret' if is_secret else 'string'
        desc = f'Runtime technical setting for {key}'
        stored_val = settings_service._encrypt_secret_value(value_to_store) if is_secret else value_to_store
        prepared_records.append((key, val_type, desc, is_secret, stored_val))

    try:
        # Execute batch persistence within a clean atomic block, committing only after all records succeed
        for key, val_type, desc, is_secret, stored_val in prepared_records:
            config_entry = SystemConfig.query.filter_by(key=key).first()
            if not config_entry:
                config_entry = SystemConfig(
                    key=key,
                    value_type=val_type,
                    description=desc,
                    is_encrypted=is_secret,
                    updated_by=int(user_id),
                )
                db.session.add(config_entry)

            config_entry.value = stored_val
            config_entry.is_encrypted = is_secret
            config_entry.value_type = val_type
            config_entry.updated_by = int(user_id)

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to atomically persist AI technical settings: %s", exc)
        raise settings_service.SettingsError(f"Database error saving settings: {exc}", 500)

    # 4. Audit logging with sanitized new_value
    sanitized_audit_data = {}
    for k, v in coerced_updates.items():
        if k in APPROVED_AI_SECRET_KEYS:
            sanitized_audit_data[k] = '[redacted]'
        else:
            sanitized_audit_data[k] = v

    try:
        from app.services import audit_service
        audit_service.log_action(
            user_id=int(user_id),
            action='update',
            entity_type='system_config',
            entity_id=0,
            old_value=None,
            new_value=sanitized_audit_data,
        )
    except Exception:
        pass

    return get_ai_runtime_settings()


def delete_ai_runtime_setting_override(key, user_id):
    """Delete a database override in SystemConfig to revert to environment fallback."""
    if key == 'provider_refinement_enabled':
        key = 'AI_DOCUMENT_CLASSIFICATION_ENABLED'
    if key not in APPROVED_AI_SETTING_KEYS:
        raise settings_service.SettingsError(f"Cannot reset unauthorized setting '{key}'.", 422)

    config_entry = SystemConfig.query.filter_by(key=key).first()
    if config_entry:
        db.session.delete(config_entry)
        db.session.commit()

        try:
            from app.services import audit_service
            audit_service.log_action(
                user_id=int(user_id),
                action='delete',
                entity_type='system_config',
                entity_id=config_entry.id or 0,
                old_value={'key': key},
                new_value=None,
            )
        except Exception:
            pass

    return get_ai_runtime_settings()


def validate_ai_provider_credential(provider, api_key=None):
    """Perform a bounded, low-cost probe to validate an AI provider's API key without sending prompts."""
    provider_name = str(provider or '').strip().lower()
    if provider_name not in {'gemini', 'groq', 'openrouter'}:
        raise settings_service.SettingsError(f"Unsupported provider '{provider}'. Must be one of: gemini, groq, openrouter.", 422)

    key_name = f"{provider_name.upper()}_API_KEY"
    resolved_key = api_key if (api_key and str(api_key).strip()) else resolve_ai_runtime_value(key_name)

    if not resolved_key or not _has_real_secret(resolved_key):
        return {
            'provider': provider_name,
            'valid': False,
            'latency_ms': None,
            'message': f"No API key provided or configured for {provider_name}.",
        }

    key_str = str(resolved_key).strip()
    if provider_name == 'groq' and ',' in key_str:
        from app.services.ai_connection import groq_api_keys
        keys = groq_api_keys(key_str)
        results = [
            {'key_index': index, **validate_ai_provider_credential(provider_name, api_key=key)}
            for index, key in enumerate(keys, start=1)
        ]
        valid = bool(results) and all(item['valid'] for item in results)
        return {
            'provider': 'groq', 'valid': valid,
            'latency_ms': round(sum(item['latency_ms'] or 0 for item in results), 2),
            'message': f"{sum(item['valid'] for item in results)} of {len(results)} Groq API keys verified.",
            'key_results': results,
        }
    t0 = time.perf_counter()

    try:
        if provider_name == 'gemini':
            # GET https://generativelanguage.googleapis.com/v1beta/models?key=... (bounded timeout 5s)
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={urllib.parse.quote(key_str)}"
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'COMET/1.0', 'Accept': 'application/json'},
                method='GET',
            )
            from app.services.ai_connection import _safe_urlopen
            with _safe_urlopen(req, timeout=5) as resp:
                resp.read()
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                'provider': 'gemini',
                'valid': True,
                'latency_ms': latency_ms,
                'message': f'Gemini API key verified successfully ({latency_ms}ms).',
            }

        elif provider_name == 'groq':
            # GET https://api.groq.com/openai/v1/models with Bearer token
            url = 'https://api.groq.com/openai/v1/models'
            req = urllib.request.Request(
                url,
                headers={
                    'Authorization': f'Bearer {key_str}',
                    'User-Agent': 'COMET/1.0',
                    'Accept': 'application/json',
                },
                method='GET',
            )
            from app.services.ai_connection import _safe_urlopen
            with _safe_urlopen(req, timeout=5) as resp:
                resp.read()
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                'provider': 'groq',
                'valid': True,
                'latency_ms': latency_ms,
                'message': f'Groq API key verified successfully ({latency_ms}ms).',
            }

        elif provider_name == 'openrouter':
            # GET https://openrouter.ai/api/v1/models with Bearer token
            url = 'https://openrouter.ai/api/v1/models'
            req = urllib.request.Request(
                url,
                headers={
                    'Authorization': f'Bearer {key_str}',
                    'User-Agent': 'COMET/1.0',
                    'Accept': 'application/json',
                },
                method='GET',
            )
            from app.services.ai_connection import _safe_urlopen
            with _safe_urlopen(req, timeout=5) as resp:
                resp.read()
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {
                'provider': 'openrouter',
                'valid': True,
                'latency_ms': latency_ms,
                'message': f'OpenRouter API key verified successfully ({latency_ms}ms).',
            }

    except urllib.error.HTTPError as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        raw_body = exc.read().decode('utf-8', errors='replace')[:300]
        from app.services.ai_connection import _sanitize_upstream_error_body
        sanitized = _sanitize_upstream_error_body(raw_body)
        return {
            'provider': provider_name,
            'valid': False,
            'latency_ms': latency_ms,
            'message': f'{provider_name} returned HTTP {exc.code}: {sanitized or exc.reason}',
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        from app.services.ai_connection import _sanitize_upstream_error_body
        sanitized = _sanitize_upstream_error_body(str(exc))
        return {
            'provider': provider_name,
            'valid': False,
            'latency_ms': latency_ms,
            'message': f'{provider_name} validation failed: {sanitized}',
        }
