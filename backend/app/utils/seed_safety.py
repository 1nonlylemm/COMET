"""Centralized Seed and Database Reset Safety Guard for COMET.

Enforces strict isolation rules to prevent accidental modification, truncation,
or dropping of tables on protected databases, while allowing explicit, authorized
resets of the designated demo database ('workspace_db') or disposable seed databases.
"""

import logging
import os
from typing import Optional, Dict, Any, Union
from flask import current_app, Flask
from sqlalchemy.engine.url import make_url, URL
from sqlalchemy.exc import ArgumentError

logger = logging.getLogger("app.utils.seed_safety")

PROTECTED_DATABASE_NAMES = frozenset({"workspace_db"})
DEFAULT_DISPOSABLE_SEED_DATABASE = "seed_disposable_db"
DEFAULT_DEMO_DATABASE = "workspace_db"

TARGET_MODE_ENV = "COMET_SEED_TARGET_MODE"
ALLOW_DISPOSABLE_RESET_ENV = "COMET_ALLOW_DISPOSABLE_SEED_RESET"
ALLOW_DEMO_RESET_ENV = "COMET_ALLOW_DEMO_DATABASE_RESET"
DISPOSABLE_DB_ENV = "COMET_DISPOSABLE_SEED_DATABASE_NAME"
DEMO_DB_ENV = "COMET_DEMO_DATABASE_NAME"
ISOLATED_SEED_ENV = "COMET_ISOLATED_SEED_ENV"


class SeedDatabaseSafetyError(RuntimeError):
    """Raised when a seed or database reset operation violates safety rules."""
    pass


def _format_target_info(url_obj: Union[URL, Any]) -> Dict[str, Any]:
    """Extract and sanitize connection metadata from a SQLAlchemy URL object."""
    database_name = (url_obj.database or "").strip()
    driver = url_obj.drivername or ""
    host = url_obj.host or ""
    port = url_obj.port

    try:
        sanitized_url = url_obj.render_as_string(hide_password=True)
    except Exception:
        masked_host = f"***@{host}" if host else "***"
        sanitized_url = f"{driver}://{masked_host}:{port or ''}/{database_name}"

    return {
        "driver": driver,
        "host": host,
        "port": port,
        "database": database_name,
        "sanitized_url": sanitized_url,
    }


def get_sanitized_database_target(app_or_uri: Union[Flask, str, None] = None) -> Dict[str, Any]:
    """Resolve, verify, and sanitize the actual database connection target.

    Verifies the actual SQLAlchemy engine target when available, cross-checking
    with the configured URI to prevent execution on unexpected or mismatched engines.
    """
    raw_uri = None
    engine_url_obj = None
    flask_app = None

    if isinstance(app_or_uri, str):
        raw_uri = app_or_uri.strip()
    elif isinstance(app_or_uri, Flask):
        flask_app = app_or_uri
    elif app_or_uri is None:
        try:
            if current_app:
                flask_app = current_app._get_current_object()
        except RuntimeError:
            pass

    if flask_app is not None:
        raw_uri = flask_app.config.get("SQLALCHEMY_DATABASE_URI")
        sa_ext = flask_app.extensions.get("sqlalchemy") if hasattr(flask_app, "extensions") else None
        if sa_ext:
            engine = getattr(sa_ext, "engine", None)
            if engine is not None and hasattr(engine, "url"):
                engine_url_obj = engine.url

    if not raw_uri and not engine_url_obj:
        raw_uri = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PRIVATE_URL")

    if not raw_uri and not engine_url_obj:
        raise SeedDatabaseSafetyError(
            "FATAL: Database target URI is missing, empty, or undefined. "
            "Seed and reset operations require an explicit, valid database target."
        )

    config_info = None
    if raw_uri:
        raw_uri_str = str(raw_uri).strip()
        for prefix in ("DATABASE_URL=", "DATABASE_PRIVATE_URL="):
            if raw_uri_str.upper().startswith(prefix):
                raw_uri_str = raw_uri_str[len(prefix):].strip()
                break
        if len(raw_uri_str) >= 2 and raw_uri_str[0] == raw_uri_str[-1] and raw_uri_str[0] in {'"', "'"}:
            raw_uri_str = raw_uri_str[1:-1].strip()

        if raw_uri_str.startswith("postgres://"):
            raw_uri_str = f"postgresql://{raw_uri_str[len('postgres://'):]}"

        try:
            url_obj = make_url(raw_uri_str)
        except (ArgumentError, Exception) as exc:
            raise SeedDatabaseSafetyError(
                "FATAL: Database target URI could not be parsed as a valid SQLAlchemy database URL. "
                "Seed and reset operations aborted."
            ) from exc

        config_info = _format_target_info(url_obj)

    engine_info = None
    if engine_url_obj:
        engine_info = _format_target_info(engine_url_obj)

    # Cross-verify engine and config if both exist
    if config_info and engine_info:
        cfg_db = (config_info["database"] or "").lower()
        eng_db = (engine_info["database"] or "").lower()
        cfg_host = (config_info["host"] or "").lower()
        eng_host = (engine_info["host"] or "").lower()

        if cfg_db != eng_db:
            raise SeedDatabaseSafetyError(
                f"FATAL: Database safety check failed. Mismatch between configured database URI "
                f"('{config_info['database']}') and actual SQLAlchemy engine target ('{engine_info['database']}'). "
                f"Configured: {config_info['sanitized_url']} | Engine: {engine_info['sanitized_url']}"
            )
        if cfg_host and eng_host and cfg_host != eng_host:
            raise SeedDatabaseSafetyError(
                f"FATAL: Database safety check failed. Mismatch between configured host "
                f"('{config_info['host']}') and actual SQLAlchemy engine host ('{engine_info['host']}'). "
                f"Configured: {config_info['sanitized_url']} | Engine: {engine_info['sanitized_url']}"
            )
        result = engine_info
        result["engine_verified"] = True
        return result

    if engine_info:
        engine_info["engine_verified"] = True
        return engine_info

    if config_info:
        config_info["engine_verified"] = False
        return config_info

    raise SeedDatabaseSafetyError("FATAL: Failed to resolve database target information.")


def validate_seed_database_safety(
    app: Optional[Flask] = None,
    *,
    operation: str = "seed",
    is_destructive: bool = False,
    target_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate database safety prior to running any seed or reset operation.

    Enforces:
    1. Default Fail-Closed: Unauthorized targets or operations fail closed.
    2. Demo Database Authorization: Operations targeting 'workspace_db' require
       explicit target mode (COMET_SEED_TARGET_MODE=demo). Destructive operations
       (reset, drop, truncate) additionally require COMET_ALLOW_DEMO_DATABASE_RESET=true.
    3. Disposable Database Authorization: Operations targeting the designated disposable
       seed database ('seed_disposable_db') require COMET_ALLOW_DISPOSABLE_SEED_RESET=true
       for destructive operations.
    4. Unknown Database Protection: Any target other than the designated demo database
       or disposable seed database is rejected unconditionally.
    5. Engine Verification: Verifies actual SQLAlchemy engine targets when available.
    6. Credential Masking: Passwords are redacted in all logs and diagnostics.
    """
    target_info = get_sanitized_database_target(target_uri if target_uri is not None else app)
    db_name = target_info["database"]
    db_name_lower = db_name.lower()
    sanitized_url_lower = target_info["sanitized_url"].lower()

    if not db_name:
        raise SeedDatabaseSafetyError(
            f"FATAL: Database safety check failed for operation '{operation}'. "
            f"Database target has no database name specified. "
            f"Target: {target_info['sanitized_url']}"
        )

    expected_disposable_db = os.environ.get(
        DISPOSABLE_DB_ENV,
        DEFAULT_DISPOSABLE_SEED_DATABASE,
    ).strip().lower()

    expected_demo_db = os.environ.get(
        DEMO_DB_ENV,
        DEFAULT_DEMO_DATABASE,
    ).strip().lower()

    target_mode = os.environ.get(TARGET_MODE_ENV, "").strip().lower()
    allow_demo_reset = os.environ.get(ALLOW_DEMO_RESET_ENV, "").strip().lower() in {"1", "true", "yes"}
    allow_disposable_reset = os.environ.get(ALLOW_DISPOSABLE_RESET_ENV, "").strip().lower() in {"1", "true", "yes"}
    isolated_env_enforced = os.environ.get(ISOLATED_SEED_ENV, "").strip().lower() in {"1", "true", "yes"}

    is_workspace_target = (
        db_name_lower == expected_demo_db
        or db_name_lower in PROTECTED_DATABASE_NAMES
        or "workspace_db" in db_name_lower
        or "workspace_db" in sanitized_url_lower
    )

    is_disposable_target = (db_name_lower == expected_disposable_db)

    # Branch 1: Target is workspace_db (or designated demo database)
    if is_workspace_target:
        # Check for unexpected variant like workspace_db_replica
        if db_name_lower != expected_demo_db:
            raise SeedDatabaseSafetyError(
                f"FATAL: Database safety check failed for operation '{operation}'. "
                f"Target database '{db_name}' contains 'workspace_db' but does not match "
                f"designated demo database '{expected_demo_db}'. Target: {target_info['sanitized_url']}"
            )

        if isolated_env_enforced:
            raise SeedDatabaseSafetyError(
                f"FATAL: Seed operation '{operation}' targeting demo database '{db_name}' "
                f"is refused when {ISOLATED_SEED_ENV}=true is active. "
                f"Isolated environment strictly requires disposable target '{expected_disposable_db}'. "
                f"Target: {target_info['sanitized_url']}"
            )

        if target_mode != "demo":
            raise SeedDatabaseSafetyError(
                f"FATAL: Database safety check failed for operation '{operation}'. "
                f"Target database '{db_name}' is the protected workspace database ('workspace_db'). "
                f"Operations targeting 'workspace_db' are strictly forbidden unless "
                f"{TARGET_MODE_ENV}=demo is explicitly enabled. "
                f"Target: {target_info['sanitized_url']}"
            )

        if is_destructive and not allow_demo_reset:
            raise SeedDatabaseSafetyError(
                f"FATAL: Destructive database operation '{operation}' on demo database '{db_name}' is refused. "
                f"Explicit opt-in is required via {ALLOW_DEMO_RESET_ENV}=true. "
                f"Target: {target_info['sanitized_url']}"
            )

        target_info["target_mode"] = "demo"

    # Branch 2: Target is disposable seed database
    elif is_disposable_target:
        if target_mode == "demo":
            raise SeedDatabaseSafetyError(
                f"FATAL: Database target mismatch for operation '{operation}'. "
                f"{TARGET_MODE_ENV}=demo is configured, but target database '{db_name}' "
                f"is the disposable database (expected '{expected_demo_db}'). "
                f"Target: {target_info['sanitized_url']}"
            )

        if is_destructive and not allow_disposable_reset:
            raise SeedDatabaseSafetyError(
                f"FATAL: Destructive database operation '{operation}' is refused. "
                f"Explicit opt-in is required via {ALLOW_DISPOSABLE_RESET_ENV}=true. "
                f"Target: {target_info['sanitized_url']}"
            )

        target_info["target_mode"] = "disposable"

    # Branch 3: Unknown or unauthorized database target
    else:
        if target_mode == "demo":
            raise SeedDatabaseSafetyError(
                f"FATAL: Database safety check failed for operation '{operation}'. "
                f"Target database '{db_name}' is an unknown or unauthorized database target in demo mode "
                f"(expected '{expected_demo_db}'). Target: {target_info['sanitized_url']}"
            )
        else:
            op_prefix = "Destructive operation" if is_destructive else "Database operation"
            raise SeedDatabaseSafetyError(
                f"FATAL: {op_prefix} '{operation}' refused. "
                f"Target database '{db_name}' is not the designated disposable seed database "
                f"(expected '{expected_disposable_db}'). Target: {target_info['sanitized_url']}"
            )

    log_msg = (
        f"[SEED-SAFETY] Database safety check PASSED for operation '{operation}' "
        f"[destructive={is_destructive}, mode={target_info.get('target_mode', 'unknown')}]. "
        f"Database: '{target_info['database']}', Host: '{target_info['host']}', Port: {target_info['port']}. "
        f"Target: {target_info['sanitized_url']}"
    )
    logger.info(log_msg)
    print(log_msg)

    return target_info
