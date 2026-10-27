import os
import sys

from flask import Flask, abort, request, send_from_directory
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError
from werkzeug.utils import safe_join
from .extensions import db, jwt, migrate
from .config import config
from .errors import register_error_handlers
from .constants.roles import INTERNAL_USER_ROLES


def _is_testing_execution(app=None) -> bool:
    """Detect whether current execution is in a test context."""
    if sys.modules.get('pytest') is not None:
        return True
    if bool(os.environ.get('PYTEST_CURRENT_TEST')):
        return True
    if os.environ.get('TESTING', '').lower() in {'1', 'true', 'yes'}:
        return True
    if os.environ.get('FLASK_CONFIG') == 'testing':
        return True
    if os.environ.get('FLASK_ENV') == 'testing':
        return True
    if app and bool(app.config.get('TESTING')):
        return True
    return False


def _validate_test_database_safety(app):
    """Enforce central database safety gate during test execution.

    Fails closed immediately before any SQLAlchemy or database connection
    is initialized if a test process attempts to target the protected 'workspace_db'.
    """
    if not _is_testing_execution(app):
        return

    uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    if not uri:
        return

    try:
        parsed = make_url(str(uri))
        target_db = (parsed.database or '').lower()
        target_host = (parsed.host or '').lower()
        full_url = str(parsed).lower()
    except (ArgumentError, Exception):
        target_db = ''
        target_host = ''
        full_url = str(uri).lower()

    # Allow RFC 2606 example domains used purely for configuration unit testing
    is_example_host = (
        target_host in {'example.com', 'example.org', 'example.net'}
        or target_host.endswith('.example')
    )
    if is_example_host:
        return

    if 'workspace_db' in target_db or 'workspace_db' in full_url:
        raise RuntimeError(
            "FATAL: Refusing to initialize application targeting protected database 'workspace_db' during test execution."
        )


def create_app(config_name='default'):
    if config_name == 'default':
        config_name = os.environ.get('FLASK_CONFIG') or os.environ.get('APP_CONFIG') or os.environ.get('FLASK_ENV') or 'development'
    config_class = config[config_name]
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config['FLASK_CONFIG'] = config_name
    app.config['FLASK_ENV'] = os.environ.get('FLASK_ENV') or config_name
    app.config['ENV'] = app.config['FLASK_ENV']
    config_class.init_app(app)

    _validate_test_database_safety(app)

    from .logging_config import configure_logging
    configure_logging(app)

    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)

    _register_health_routes(app)
    _register_blueprints(app)
    register_error_handlers(app)
    _register_jwt_callbacks(app)
    _register_request_guards(app)
    _register_frontend_routes(app)

    return app


def _register_health_routes(app):
    @app.get('/health')
    @app.get('/api/health')
    def health_check():
        return {
            'status': 'ok',
            'success': True,
            'service': app.config.get('APP_NAME', 'DILG Operations Workspace'),
        }, 200


def _register_frontend_routes(app):
    @app.get('/')
    def serve_frontend_root():
        return _serve_frontend_asset_or_index(app)

    @app.get('/<path:path>')
    def serve_frontend_path(path):
        if path == 'api' or path.startswith('api/'):
            abort(404)
        return _serve_frontend_asset_or_index(app, path)


def _serve_frontend_asset_or_index(app, path=None):
    frontend_dist_dir = app.config.get('FRONTEND_DIST_DIR') or os.path.join(os.getcwd(), 'frontend_dist')
    index_path = safe_join(frontend_dist_dir, 'index.html')
    if not index_path or not os.path.isfile(index_path):
        abort(404)

    if path:
        asset_path = safe_join(frontend_dist_dir, path)
        if asset_path and os.path.isfile(asset_path):
            return send_from_directory(frontend_dist_dir, path)

    return send_from_directory(frontend_dist_dir, 'index.html')


def _register_blueprints(app):
    from .api.auth import auth_bp
    from .api.lgus import lgu_bp
    from .api.programs import programs_bp
    from .api.projects import projects_bp
    from .api.escalation.routes import escalation_bp
    from .api.magic_links import magic_links_bp
    from .api.monitoring import monitoring_bp
    from .api.sla import sla_bp
    from .api.audit import audit_bp
    from .api.completion import completion_bp
    from .api.dashboard import dashboard_bp
    from .api.reports import reports_bp
    from .api.governance import governance_bp
    from .api.library import library_bp
    from .api.settings import settings_bp
    from .api.system_admin import system_admin_bp
    from .api.document_checker_evaluation import document_checker_evaluation_bp
    from .api.imports import imports_bp
    from .api.batch_imports import batch_imports_bp
    from .api.workbook_workspaces import workbook_workspaces_bp
    from .api.ai_assistant import ai_bp
    from .api.search import search_bp
    from .api.drive import drive_bp
    from .api.field_officer import field_officer_bp
    from .api.notifications import notifications_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(lgu_bp, url_prefix='/api/lgus')
    app.register_blueprint(programs_bp)
    app.register_blueprint(projects_bp, url_prefix='/api/projects')
    app.register_blueprint(escalation_bp, url_prefix='/api/escalation')
    app.register_blueprint(magic_links_bp, url_prefix='/api/magic-links')
    app.register_blueprint(monitoring_bp, url_prefix='/api/monitoring')
    app.register_blueprint(sla_bp, url_prefix='/api/sla')
    app.register_blueprint(audit_bp, url_prefix='/api/audit')
    app.register_blueprint(completion_bp, url_prefix='/api/completion')
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(governance_bp, url_prefix='/api/governance')
    app.register_blueprint(library_bp, url_prefix='/api/library')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    app.register_blueprint(system_admin_bp, url_prefix='/api/system-admin')
    app.register_blueprint(document_checker_evaluation_bp, url_prefix='/api/document-checker/evaluation')
    app.register_blueprint(imports_bp, url_prefix='/api/imports')
    app.register_blueprint(batch_imports_bp, url_prefix='/api/batch-imports')
    app.register_blueprint(workbook_workspaces_bp, url_prefix='/api/workbook-workspaces')
    app.register_blueprint(ai_bp, url_prefix='/api/ai')
    app.register_blueprint(search_bp, url_prefix='/api/search')
    app.register_blueprint(drive_bp, url_prefix='/api/drive')
    app.register_blueprint(field_officer_bp, url_prefix='/api/field')
    app.register_blueprint(notifications_bp, url_prefix='/api/notifications')


def _register_jwt_callbacks(app):
    from .models import User

    @jwt.user_identity_loader
    def user_identity_lookup(identity):
        return str(identity)

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        try:
            identity = int(jwt_data["sub"])
        except (TypeError, ValueError):
            return None
        user = db.session.get(User, identity)
        if not user:
            return None
        token_version = jwt_data.get("token_version")
        if token_version is not None and token_version != user.token_version:
            return None
        if jwt_data.get("type") == "mfa_challenge":
            endpoint = request.endpoint if request else None
            if endpoint not in {'auth.mfa_verify', 'auth.logout'}:
                return None
        return user

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(_jwt_header, jwt_payload):
        try:
            identity = int(jwt_payload["sub"])
        except (TypeError, ValueError):
            return True
        user = db.session.get(User, identity)
        if not user:
            return True
        token_version = jwt_payload.get("token_version")
        if token_version is not None and token_version != user.token_version:
            return True
        if jwt_payload.get("type") == "mfa_challenge":
            endpoint = request.endpoint if request else None
            if endpoint not in {'auth.mfa_verify', 'auth.logout'}:
                return True
        return False

    @jwt.revoked_token_loader
    def revoked_token_callback(_jwt_header, _jwt_payload):
        from .utils.response import unauthorized_error
        return unauthorized_error(
            message='Session expired or revoked. Please log in again.',
            headers={'WWW-Authenticate': 'Bearer error="invalid_token", error_description="The token has been revoked"'},
        )

    @jwt.unauthorized_loader
    def unauthorized_callback(_err_str):
        from .utils.response import unauthorized_error
        return unauthorized_error(
            message='Authentication required',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    @jwt.invalid_token_loader
    def invalid_token_callback(_err_str):
        from .utils.response import unauthorized_error
        return unauthorized_error(
            message='Invalid authentication token. Please log in again.',
            headers={'WWW-Authenticate': 'Bearer error="invalid_token"'},
        )

    @jwt.expired_token_loader
    def expired_token_callback(_jwt_header, _jwt_payload):
        from .utils.response import unauthorized_error
        return unauthorized_error(
            message='Token has expired. Please log in again.',
            headers={'WWW-Authenticate': 'Bearer error="invalid_token", error_description="The token has expired"'},
        )

    @jwt.user_lookup_error_loader
    def user_lookup_error_callback(_jwt_header, _jwt_payload):
        from .utils.response import unauthorized_error
        return unauthorized_error(
            message='User associated with token not found or invalid.',
            headers={'WWW-Authenticate': 'Bearer error="invalid_token"'},
        )

    @jwt.needs_fresh_token_loader
    def needs_fresh_token_callback(_jwt_header, _jwt_payload):
        from .utils.response import unauthorized_error
        return unauthorized_error(
            message='Fresh token required. Please re-authenticate.',
            headers={'WWW-Authenticate': 'Bearer error="invalid_token"'},
        )


def _register_request_guards(app):
    from .models import User
    from .services import settings_service
    from .utils.response import error_response

    allowed_password_rotation_endpoints = {
        'auth.change_password',
        'auth.me',
        'auth.refresh',
        'auth.update_profile',
        'auth.logout',
    }

    @app.before_request
    def check_maintenance_mode():
        if request.method == 'OPTIONS':
            return None

        if not request.path.startswith('/api/'):
            return None

        from .services import maintenance_service
        if maintenance_service.is_maintenance_mode():
            # System administrators are exempt from maintenance mode lockout
            try:
                verify_jwt_in_request(optional=True)
                identity = get_jwt_identity()
                if identity is not None:
                    user = db.session.get(User, int(identity))
                    if user and user.is_active and user.role == 'system_admin':
                        return None
            except Exception:
                pass

            info = maintenance_service.get_maintenance_info()
            return error_response(
                message=info.get('reason') or 'System is currently undergoing a database restore. Please try again shortly.',
                status_code=503,
            )

    @app.before_request
    def enforce_password_rotation():
        if request.method == 'OPTIONS':
            return None

        if not request.path.startswith('/api/'):
            return None

        try:
            verify_jwt_in_request(optional=True)
        except Exception:
            return None

        identity = get_jwt_identity()
        if identity is None:
            return None

        try:
            user_id = int(identity)
        except (TypeError, ValueError):
            return None

        user = db.session.get(User, user_id)
        if not user:
            return error_response(
                message='User not found or deactivated',
                status_code=401,
            )

        if not user.is_active:
            return error_response(
                message='Account is deactivated',
                status_code=403,
            )

        claims = get_jwt()
        token_version = claims.get('token_version')
        if token_version is not None and token_version != user.token_version:
            return error_response(
                message='Session expired or revoked. Please log in again.',
                status_code=401,
            )

        if claims.get('type') == 'mfa_challenge':
            if request.endpoint not in {'auth.mfa_verify', 'auth.logout'}:
                return error_response(
                    message='MFA verification required.',
                    status_code=401,
                )

        if user.role not in INTERNAL_USER_ROLES:
            app_name = settings_service.get_app_name()
            return error_response(
                message=f'This account does not have access to the internal {app_name} dashboard.',
                status_code=403,
            )

        if not user.must_change_password:
            return None

        if request.endpoint in allowed_password_rotation_endpoints:
            return None

        app_name = settings_service.get_app_name()
        return error_response(
            message=f'You must change your password before accessing the rest of {app_name}.',
            status_code=403,
        )
