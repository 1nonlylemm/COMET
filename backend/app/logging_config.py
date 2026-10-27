import json
import logging
import re
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variables for Celery / background tasks (isolated per coroutine/thread/process)
_celery_task_id: ContextVar[Optional[str]] = ContextVar('celery_task_id', default=None)
_celery_task_name: ContextVar[Optional[str]] = ContextVar('celery_task_name', default=None)
_celery_attempt: ContextVar[Optional[int]] = ContextVar('celery_attempt', default=None)

# Known sensitive key names and prefixes/suffixes
SENSITIVE_KEY_NAMES = {
    'password',
    'passwd',
    'secret',
    'token',
    'jwt',
    'authorization',
    'authorization_header',
    'cookie',
    'api_key',
    'apikey',
    'access_token',
    'refresh_token',
    'auth_token',
    'bearer_token',
    'client_secret',
    'credential',
    'credentials',
    'private_key',
    'connection_string',
    'database_url',
    'postgres_password',
    'smtp_password',
    'secret_key',
    'jwt_secret_key',
    'system_config_secret_key',
}

SENSITIVE_KEY_SUFFIXES = (
    '_password',
    '_secret',
    '_token',
    '_key',
    '_credential',
    '_credentials',
    '_api_key',
)

# Regex patterns for best-effort redaction in string messages and tracebacks
REDACTION_PATTERNS = [
    # Bearer tokens
    (re.compile(r'(?i)\bbearer\s+[a-zA-Z0-9_\-\.\~]{10,}\b'), 'Bearer [REDACTED]'),
    # Basic auth embedded in URLs
    (re.compile(r'(https?://[^:\s]+:)[^@\s]+(@)'), r'\1[REDACTED]\2'),
    # JWT tokens (three dot-separated base64-like segments)
    (re.compile(r'\beyJ[a-zA-Z0-9_\-]{8,}\.eyJ[a-zA-Z0-9_\-]{8,}\.[a-zA-Z0-9_\-]+\b'), '[REDACTED_JWT]'),
    # Key-value assignments like password=xyz, "secret": "xyz", token: xyz
    (
        re.compile(r'(?i)\b(password|passwd|secret|token|api_key|apikey|private_key)\s*[:=]\s*["\']?[^\s,"\';]+["\']?'),
        r'\1=[REDACTED]',
    ),
    # Words like 'password xyz' or 'secret abc'
    (
        re.compile(r'(?i)\b(password|passwd|secret|api_key|apikey|private_key)\s+([^\s,;]+)'),
        r'\1 [REDACTED]',
    ),
    # SQL parameter listings like [parameters: (...)] when not caught by engine options
    (re.compile(r'\[parameters:\s*\([^)]*\)\]'), '[parameters: [SQL parameters hidden]]'),
]


def set_celery_context(task_id: Optional[str], task_name: Optional[str] = None, attempt: Optional[int] = None) -> None:
    """Set Celery execution context for the current task."""
    _celery_task_id.set(str(task_id).strip()[:64] if task_id else None)
    _celery_task_name.set(str(task_name).strip()[:100] if task_name else None)
    _celery_attempt.set(int(attempt) if attempt is not None else None)


def get_celery_context() -> Dict[str, Any]:
    """Retrieve the current Celery task context."""
    return {
        'task_id': _celery_task_id.get(),
        'task_name': _celery_task_name.get(),
        'attempt': _celery_attempt.get(),
    }


def clear_celery_context() -> None:
    """Clear Celery task context to guarantee zero leakage between worker runs."""
    _celery_task_id.set(None)
    _celery_task_name.set(None)
    _celery_attempt.set(None)


def get_current_request_id() -> Optional[str]:
    """Retrieve the active HTTP request ID if inside a Flask request context."""
    try:
        from flask import g, has_request_context
        if has_request_context():
            return getattr(g, 'request_id', None)
    except Exception:
        pass
    return None


def get_current_operation_id() -> Optional[str]:
    """Retrieve the current background operation or Celery task ID."""
    celery_ctx = get_celery_context()
    if celery_ctx.get('task_id'):
        return celery_ctx['task_id']
    return None


def is_sensitive_key(key: Any) -> bool:
    """Determine whether a dictionary key corresponds to sensitive data."""
    norm = str(key or '').strip().lower().replace('-', '_')
    if norm in SENSITIVE_KEY_NAMES:
        return True
    if any(norm.endswith(suffix) for suffix in SENSITIVE_KEY_SUFFIXES):
        return True
    return False


def redact_sensitive_string(text: str) -> str:
    """Apply regex redaction patterns to a text string."""
    if not text:
        return ''
    result = str(text)
    for pattern, replacement in REDACTION_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_sensitive_data(value: Any, max_depth: int = 4) -> Any:
    """Recursively scrub sensitive keys and text from data structures."""
    if max_depth <= 0:
        return '[TRUNCATED_DEPTH]'

    if isinstance(value, dict):
        scrubbed = {}
        for k, v in value.items():
            if is_sensitive_key(k):
                scrubbed[str(k)] = '[REDACTED]'
            else:
                scrubbed[str(k)] = redact_sensitive_data(v, max_depth=max_depth - 1)
        return scrubbed

    if isinstance(value, (list, tuple)):
        return [redact_sensitive_data(item, max_depth=max_depth - 1) for item in value]

    if isinstance(value, str):
        return redact_sensitive_string(value)

    if not isinstance(value, (int, float, bool)) and value is not None:
        return redact_sensitive_string(str(value))

    return value


def sanitize_text(text: Any, max_length: int = 2000) -> str:
    """Sanitize, scrub, and truncate a text message."""
    if text is None:
        return ''
    cleaned = redact_sensitive_string(str(text))
    if len(cleaned) > max_length:
        return cleaned[:max_length] + '... [truncated]'
    return cleaned


def sanitize_traceback(tb_str: Any, max_length: int = 8000) -> Optional[str]:
    """Sanitize and truncate a traceback string."""
    if not tb_str:
        return None
    cleaned = redact_sensitive_string(str(tb_str))
    if len(cleaned) > max_length:
        return cleaned[:max_length] + '\n... [traceback truncated]'
    return cleaned


class SensitiveDataFilter(logging.Filter):
    """Logging filter that scrubs sensitive credentials from record arguments and message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_sensitive_string(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = redact_sensitive_data(record.args)
                elif isinstance(record.args, (list, tuple)):
                    record.args = tuple(redact_sensitive_data(arg) for arg in record.args)
        except Exception:
            pass  # Ensure logging filter never crashes logging pipeline
        return True


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as structured, single-line JSON with context enrichment."""

    def format(self, record: logging.LogRecord) -> str:
        # Determine UTC occurrence timestamp
        created_dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        timestamp_str = created_dt.isoformat()

        # Extract message with arguments applied safely
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        message = sanitize_text(message, max_length=4000)

        # Correlation IDs
        request_id = getattr(record, 'request_id', None) or get_current_request_id()
        operation_id = getattr(record, 'operation_id', None) or get_current_operation_id()

        # Component / Logger categorization
        component = getattr(record, 'component', None)
        if not component:
            logger_name = record.name or 'root'
            if logger_name.startswith('app.tasks') or 'celery' in logger_name:
                component = 'celery_worker'
            elif logger_name.startswith('app.api') or logger_name in {'app', 'gunicorn.error', 'werkzeug'}:
                component = 'api'
            elif 'sqlalchemy' in logger_name:
                component = 'database'
            elif 'storage' in logger_name:
                component = 'storage'
            elif 'auth' in logger_name:
                component = 'auth'
            else:
                component = logger_name.split('.')[0]

        event_name = getattr(record, 'event', None) or getattr(record, 'event_name', None)

        payload: Dict[str, Any] = {
            'timestamp': timestamp_str,
            'severity': record.levelname,
            'logger': record.name,
            'component': component,
            'message': message,
        }

        if event_name:
            payload['event'] = str(event_name)
        if request_id:
            payload['request_id'] = str(request_id)
        if operation_id:
            payload['operation_id'] = str(operation_id)

        # HTTP context if attached or present on record
        http_ctx = getattr(record, 'http', None)
        if not http_ctx:
            try:
                from flask import g, has_request_context, request
                if has_request_context():
                    http_ctx = {
                        'method': request.method,
                        'path': request.path,
                        'duration_ms': getattr(g, 'request_duration_ms', None),
                    }
            except Exception:
                pass
        if http_ctx:
            payload['http'] = redact_sensitive_data(http_ctx)

        # Celery task context if present
        celery_ctx = get_celery_context()
        if celery_ctx.get('task_name'):
            payload['task'] = {
                'name': celery_ctx['task_name'],
                'attempt': celery_ctx.get('attempt'),
            }

        # Exception formatting if exc_info present
        if record.exc_info:
            try:
                exc_type = None
                exc_val = None
                exc_tb = None
                if isinstance(record.exc_info, tuple) and len(record.exc_info) == 3:
                    exc_type, exc_val, exc_tb = record.exc_info
                elif isinstance(record.exc_info, BaseException):
                    exc_type, exc_val, exc_tb = type(record.exc_info), record.exc_info, record.exc_info.__traceback__
                elif record.exc_info is True:
                    cur_exc = sys.exc_info()
                    if cur_exc and len(cur_exc) == 3 and cur_exc[0] is not None:
                        exc_type, exc_val, exc_tb = cur_exc

                if exc_type is not None:
                    tb_formatted = ''
                    if exc_tb:
                        tb_lines = traceback.format_exception(exc_type, exc_val, exc_tb)
                        tb_formatted = ''.join(tb_lines)
                    payload['exception'] = {
                        'type': exc_type.__name__ if hasattr(exc_type, '__name__') else str(exc_type),
                        'message': sanitize_text(str(exc_val), max_length=1000),
                        'traceback': sanitize_traceback(tb_formatted, max_length=8000) if tb_formatted else None,
                    }
            except Exception:
                pass

        # Extra context attributes if explicitly provided
        extra_ctx = getattr(record, 'context', None) or getattr(record, 'context_data', None)
        if extra_ctx is not None:
            if isinstance(extra_ctx, dict):
                payload['context'] = redact_sensitive_data(extra_ctx)
            else:
                payload['context'] = sanitize_text(str(extra_ctx), max_length=1000)

        # Return single-line JSON
        try:
            return json.dumps(payload, ensure_ascii=True, default=str)
        except Exception:
            # Absolute fallback if json serialization fails on unexpected object
            fallback = {
                'timestamp': timestamp_str,
                'severity': record.levelname,
                'logger': record.name,
                'component': component,
                'message': message,
            }
            return json.dumps(fallback, ensure_ascii=True)


def configure_logging(app: Any = None, log_level: Optional[str] = None) -> None:
    """
    Centralized logging configuration for COMET.
    Sets root logger to structured JSON stream output on stdout/stderr,
    attaches SensitiveDataFilter, and ensures zero duplicate handler propagation.
    """
    if log_level is None:
        if app and hasattr(app, 'config'):
            log_level = app.config.get('LOG_LEVEL', 'INFO')
        else:
            log_level = 'INFO'

    level_num = getattr(logging, str(log_level).upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level_num)

    # Check if StructuredJsonFormatter is already configured on root logger to avoid duplicate handlers
    already_configured = any(
        isinstance(getattr(handler, 'formatter', None), StructuredJsonFormatter)
        for handler in root_logger.handlers
    )

    if not already_configured:
        # Clear existing handlers on root logger
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(level_num)
        stream_handler.setFormatter(StructuredJsonFormatter())
        stream_handler.addFilter(SensitiveDataFilter())

        root_logger.addHandler(stream_handler)

    # Ensure Flask app.logger routes through structured pipeline without duplication
    if app and hasattr(app, 'logger'):
        app.logger.setLevel(level_num)
        for h in list(app.logger.handlers):
            app.logger.removeHandler(h)
        app.logger.propagate = True

    # Suppress verbose noisy third-party loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
