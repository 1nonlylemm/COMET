import logging
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.extensions import db
from app.logging_config import (
    get_current_operation_id,
    get_current_request_id,
    redact_sensitive_data,
    sanitize_text,
    sanitize_traceback,
)
from app.models.operational_event import SystemOperationalEvent

logger = logging.getLogger('comet.operational_events')

# Reentrancy guard to prevent recursive recording loops
_recorder_active: ContextVar[bool] = ContextVar('recorder_active', default=False)

# Common connection failure indicators for database fail-open
DB_CONNECTION_FAILURE_PHRASES = (
    'could not connect to server',
    'connection refused',
    'server closed the connection',
    'terminating connection',
    'connection timed out',
    'no route to host',
    'is the server running',
    'connection reset',
    'remaining connection slots are reserved',
    'too many connections',
)


def is_database_connection_failure(exc: Any) -> bool:
    """Determine whether an exception indicates the database is unreachable."""
    if not exc:
        return False
    if isinstance(exc, tuple) and len(exc) >= 2 and exc[1] is not None:
        exc = exc[1]
    msg = str(exc).lower()
    if any(phrase in msg for phrase in DB_CONNECTION_FAILURE_PHRASES):
        return True
    orig = getattr(exc, 'orig', None)
    if orig and any(phrase in str(orig).lower() for phrase in DB_CONNECTION_FAILURE_PHRASES):
        return True
    cause = getattr(exc, '__cause__', None)
    if cause and any(phrase in str(cause).lower() for phrase in DB_CONNECTION_FAILURE_PHRASES):
        return True
    return False


def extract_user_id() -> Optional[int]:
    """Extract authenticated user ID if inside an active Flask request with JWT identity."""
    try:
        from flask import has_request_context
        from flask_jwt_extended import get_jwt_identity
        if has_request_context():
            identity = get_jwt_identity()
            if identity is not None:
                return int(identity)
    except Exception:
        pass
    return None


def _get_engine():
    """Retrieve SQLAlchemy engine safely."""
    try:
        return getattr(db, 'engine', None)
    except Exception:
        return None


def record_operational_event(
    severity: str,
    component: str,
    event_name: str,
    message: str,
    request_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    user_id: Optional[int] = None,
    context_data: Optional[Dict[str, Any]] = None,
    exc_info: Any = None,
    emit_log: bool = True,
) -> Optional[SystemOperationalEvent]:
    """
    Best-effort recording of meaningful operational and diagnostic events.

    Guarantees:
    1. Always emits structured log to stdout/stderr independently of DB success.
    2. Zero interference: DB insert failure NEVER replaces the original application error.
    3. Reentrancy guard: Prevents recursive recording loops.
    4. Session isolation: Uses an independent SQLAlchemy session to avoid dirtying business transactions.
    5. DB down fail-open: If the original error indicates DB connection failure, skips DB insert safely.
    6. Strict size limits and secret redaction on messages, contexts, and tracebacks.
    """
    # 1. Normalize parameters and apply strict size/redaction bounds
    severity = str(severity or 'ERROR').upper().strip()[:20]
    component = str(component or 'api').lower().strip()[:50]
    event_name = str(event_name or 'operational_event').strip()[:100]
    clean_message = sanitize_text(message, max_length=2000)

    clean_request_id = str(request_id or get_current_request_id() or '').strip()[:64] or None
    clean_operation_id = str(operation_id or get_current_operation_id() or '').strip()[:64] or None
    clean_user_id = user_id if user_id is not None else extract_user_id()

    # Format and sanitize traceback if exc_info provided
    tb_string = None
    if exc_info:
        if isinstance(exc_info, BaseException):
            tb_string = ''.join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__))
        elif isinstance(exc_info, tuple) and len(exc_info) == 3 and exc_info[0] is not None:
            tb_string = ''.join(traceback.format_exception(*exc_info))
        elif exc_info is True:
            tb_string = traceback.format_exc()

    clean_traceback = sanitize_traceback(tb_string, max_length=8000) if tb_string else None

    # Sanitize context data dictionary
    clean_context = redact_sensitive_data(context_data or {}, max_depth=3)
    if not isinstance(clean_context, dict):
        clean_context = {'data': str(clean_context)[:500]}

    # 2. Unconditionally emit structured log to stdout/stderr via Python logging
    if emit_log:
        try:
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL,
            }
            log_level = level_map.get(severity, logging.ERROR)

            # Log with extra context so StructuredJsonFormatter formats it completely
            logger.log(
                log_level,
                '%s: %s',
                event_name,
                clean_message,
                extra={
                    'component': component,
                    'event_name': event_name,
                    'request_id': clean_request_id,
                    'operation_id': clean_operation_id,
                    'context': clean_context,
                },
                exc_info=exc_info,
            )
        except Exception as log_exc:
            safe_log_exc = sanitize_text(str(log_exc), max_length=500)
            sys.stderr.write(
                f"[COMET LOGGING FAILURE] Could not emit operational log: {safe_log_exc} | Message: {clean_message}\n"
            )

    # 3. Check reentrancy guard
    if _recorder_active.get():
        return None

    # 4. If the original error or underlying cause indicates database is unreachable, skip DB persistence
    if is_database_connection_failure(exc_info) or is_database_connection_failure(clean_message):
        sys.stderr.write(
            f"[COMET OPERATIONAL RECORDER] Database connection failure detected; skipping DB persistence for event '{event_name}'.\n"
        )
        return None

    # 5. Best-effort persistence using an isolated SQLAlchemy Session
    _recorder_active.set(True)
    try:
        # Verify db.engine exists
        engine = _get_engine()
        if engine is None:
            return None

        # Fail closed: Enforce test isolation if in testing environment
        try:
            import os
            from flask import current_app, has_app_context
            is_testing_mode = (
                sys.modules.get('pytest') is not None
                or bool(os.environ.get('PYTEST_CURRENT_TEST'))
                or (has_app_context() and bool(current_app.config.get('TESTING')))
                or os.environ.get('FLASK_CONFIG') == 'testing'
                or os.environ.get('FLASK_ENV') == 'testing'
                or os.environ.get('TESTING') == 'true'
            )
            if is_testing_mode:
                engine_url_str = str(engine.url)
                db_name = str(getattr(engine.url, 'database', '') or '')
                if 'workspace_db' in engine_url_str or 'workspace_db' in db_name:
                    sys.stderr.write(
                        f"[COMET OPERATIONAL RECORDER] FATAL: Prevented attempt to persist operational event '{event_name}' to production 'workspace_db' during testing.\n"
                    )
                    return None
        except Exception:
            pass

        # In SQLite in-memory (testing), Session(engine) opens a distinct empty connection.
        # Use db.session for SQLite to preserve in-memory tables, and isolated Session(engine) for PostgreSQL.
        if engine.dialect.name == 'sqlite':
            event = SystemOperationalEvent(
                timestamp=datetime.now(timezone.utc),
                severity=severity,
                component=component,
                event_name=event_name,
                message=clean_message,
                request_id=clean_request_id,
                operation_id=clean_operation_id,
                user_id=clean_user_id,
                context_data=clean_context,
                traceback=clean_traceback,
            )
            db.session.add(event)
            db.session.commit()
            return event
        else:
            with Session(engine) as isolated_session:
                event = SystemOperationalEvent(
                    timestamp=datetime.now(timezone.utc),
                    severity=severity,
                    component=component,
                    event_name=event_name,
                    message=clean_message,
                    request_id=clean_request_id,
                    operation_id=clean_operation_id,
                    user_id=clean_user_id,
                    context_data=clean_context,
                    traceback=clean_traceback,
                )
                isolated_session.add(event)
                isolated_session.commit()
                return event
    except Exception as db_exc:
        # Fails open: Write diagnostic notice to stderr and never raise
        try:
            if engine and getattr(engine, 'dialect', None) and engine.dialect.name == 'sqlite':
                db.session.rollback()
        except Exception:
            pass
        safe_db_exc = sanitize_text(str(db_exc), max_length=500)
        sys.stderr.write(
            f"[COMET OPERATIONAL RECORDER] Failed to persist operational event '{event_name}' to database: {safe_db_exc}\n"
        )
        return None
    finally:
        _recorder_active.set(False)


def cleanup_operational_events(
    retention_days: int = 30,
    max_events: int = 10000,
    session: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Safely prune aged and excess records from system_operational_events.

    Retention rules:
    1. Delete records older than retention_days (default 30 days).
    2. Bound remaining rows to at most max_events (default 10,000), keeping
       the newest records ordered by (timestamp DESC, id DESC).
    3. Fails open: on any database error, rolls back safely, logs a diagnostic
       notice without recursing into record_operational_event, and returns failure status.
    4. Isolated transaction: commits only on success; leaves other sessions unaffected.
    """
    if retention_days < 0:
        retention_days = 0
    if max_events < 0:
        max_events = 0

    engine = _get_engine()
    owns_session = session is None
    s = None
    close_session_on_finish = False

    if owns_session:
        if engine is None:
            logger.error("Operational event retention cleanup failed: Database engine unavailable.")
            return {
                'status': 'failed',
                'error': 'Database engine unavailable',
                'deleted_by_age': 0,
                'deleted_by_limit': 0,
                'total_deleted': 0,
            }
        if engine.dialect.name == 'sqlite':
            s = db.session
        else:
            s = Session(engine)
            close_session_on_finish = True
    else:
        s = session

    try:
        # Step 1: Delete records older than the retention threshold
        cutoff_age = datetime.now(timezone.utc) - timedelta(days=retention_days)
        deleted_by_age = s.query(SystemOperationalEvent).filter(
            SystemOperationalEvent.timestamp < cutoff_age
        ).delete(synchronize_session=False)

        # Step 2: Enforce max_events limit on remaining records
        deleted_by_limit = 0
        if max_events == 0:
            deleted_by_limit = s.query(SystemOperationalEvent).delete(synchronize_session=False)
        else:
            boundary = (
                s.query(SystemOperationalEvent.timestamp, SystemOperationalEvent.id)
                .order_by(SystemOperationalEvent.timestamp.desc(), SystemOperationalEvent.id.desc())
                .offset(max_events)
                .first()
            )
            if boundary is not None:
                boundary_ts, boundary_id = boundary
                deleted_by_limit = (
                    s.query(SystemOperationalEvent)
                    .filter(
                        or_(
                            SystemOperationalEvent.timestamp < boundary_ts,
                            and_(
                                SystemOperationalEvent.timestamp == boundary_ts,
                                SystemOperationalEvent.id <= boundary_id,
                            ),
                        )
                    )
                    .delete(synchronize_session=False)
                )

        total_deleted = deleted_by_age + deleted_by_limit
        s.commit()

        logger.info(
            "Operational event retention cleanup succeeded: %d total removed (%d older than %d days, %d exceeding %d row limit).",
            total_deleted,
            deleted_by_age,
            retention_days,
            deleted_by_limit,
            max_events,
        )

        return {
            'status': 'success',
            'deleted_by_age': deleted_by_age,
            'deleted_by_limit': deleted_by_limit,
            'total_deleted': total_deleted,
        }
    except Exception as exc:
        try:
            if s is not None:
                s.rollback()
        except Exception:
            pass
        safe_exc = sanitize_text(str(exc), max_length=500)
        logger.error("Operational event retention cleanup failed: %s", safe_exc)
        sys.stderr.write(
            f"[COMET OPERATIONAL CLEANUP FAILURE] Operational event cleanup failed: {safe_exc}\n"
        )
        return {
            'status': 'failed',
            'error': safe_exc,
            'deleted_by_age': 0,
            'deleted_by_limit': 0,
            'total_deleted': 0,
        }
    finally:
        if close_session_on_finish and s is not None:
            try:
                s.close()
            except Exception:
                pass


ALLOWED_SEVERITIES = frozenset({'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'})


def _parse_iso_datetime(value: Any, param_name: str) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s_val = str(value).strip()
    if not s_val:
        return None
    if s_val.endswith('Z'):
        s_val = s_val[:-1] + '+00:00'
    # In HTTP query strings, '+' is decoded to a space ' ', e.g. '2026-07-31T12:00:00 00:00'
    import re
    s_val = re.sub(r' (\d{2}:\d{2})$', r'+\1', s_val)
    try:
        dt = datetime.fromisoformat(s_val)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid format for '{param_name}'. Expected ISO-8601 timestamp (e.g. 2026-10-09T00:00:00Z).") from exc


def query_operational_events(
    severity: Optional[str] = None,
    component: Optional[str] = None,
    request_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    search: Optional[str] = None,
    start_time_str: Optional[str] = None,
    end_time_str: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    """
    Query operational events with allowlisted filters and deterministic reverse chronological ordering.
    Strictly bounds pagination and search length, validating inputs.
    """
    query = SystemOperationalEvent.query

    # 1. Validate and filter severity
    if severity:
        clean_sev = str(severity).strip().upper()
        if clean_sev not in ALLOWED_SEVERITIES:
            raise ValueError(
                f"Invalid severity '{severity}'. Allowed values: {', '.join(sorted(ALLOWED_SEVERITIES))}."
            )
        query = query.filter(SystemOperationalEvent.severity == clean_sev)

    # 2. Filter component
    if component:
        clean_comp = str(component).strip().lower()[:50]
        if clean_comp:
            query = query.filter(SystemOperationalEvent.component == clean_comp)

    # 3. Filter request_id and operation_id (exact match)
    if request_id:
        clean_req = str(request_id).strip()[:64]
        if clean_req:
            query = query.filter(SystemOperationalEvent.request_id == clean_req)

    if operation_id:
        clean_op = str(operation_id).strip()[:64]
        if clean_op:
            query = query.filter(SystemOperationalEvent.operation_id == clean_op)

    # 4. Validate and filter time range
    start_dt = _parse_iso_datetime(start_time_str, 'start_time')
    if start_dt is not None:
        query = query.filter(SystemOperationalEvent.timestamp >= start_dt)

    end_dt = _parse_iso_datetime(end_time_str, 'end_time')
    if end_dt is not None:
        query = query.filter(SystemOperationalEvent.timestamp <= end_dt)

    # 5. Validate and filter search string
    if search:
        clean_search = str(search).strip()
        if len(clean_search) > 100:
            raise ValueError("Search query exceeds maximum length of 100 characters.")
        if clean_search:
            pattern = f"%{clean_search}%"
            query = query.filter(
                or_(
                    SystemOperationalEvent.message.ilike(pattern),
                    SystemOperationalEvent.event_name.ilike(pattern),
                )
            )

    # 6. Apply deterministic ordering: timestamp DESC, id DESC
    query = query.order_by(
        SystemOperationalEvent.timestamp.desc(),
        SystemOperationalEvent.id.desc(),
    )

    # 7. Clamp pagination parameters
    safe_page = max(1, page)
    safe_per_page = max(1, min(per_page, 100))

    paginated = query.paginate(page=safe_page, per_page=safe_per_page, error_out=False)

    return {
        'items': [item.to_summary_dict() for item in paginated.items],
        'meta': {
            'page': paginated.page,
            'per_page': paginated.per_page,
            'total_pages': paginated.pages,
            'total_items': paginated.total,
            'has_next': paginated.has_next,
            'has_prev': paginated.has_prev,
        },
    }


def get_operational_event(event_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve detailed operational event record with sanitized traceback and context."""
    event = db.session.get(SystemOperationalEvent, event_id)
    if not event:
        return None
    return event.to_detail_dict()


