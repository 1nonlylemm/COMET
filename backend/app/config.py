import os
import secrets
from datetime import timedelta

try:
    from celery.schedules import crontab
except ImportError:
    crontab = None

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def _first_non_empty(*values):
    for value in values:
        if value:
            return value
    return None


def _env_list(name, default):
    value = os.environ.get(name, default)
    return tuple(item.strip().lower() for item in value.split(',') if item.strip())


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name, default=False):
    fallback = 'true' if default else 'false'
    return os.environ.get(name, fallback).strip().lower() in {'1', 'true', 'yes', 'on'}


def _strip_outer_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _normalize_database_url(value):
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    normalized = _strip_outer_quotes(normalized)

    for prefix in ('DATABASE_URL=', 'DATABASE_PRIVATE_URL='):
        if normalized.upper().startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break

    normalized = _strip_outer_quotes(normalized)

    if normalized.startswith('postgres://'):
        normalized = f"postgresql://{normalized[len('postgres://'):]}"

    return normalized


def _database_url_from_env(default=None):
    return _normalize_database_url(
        _first_non_empty(
            os.environ.get('DATABASE_URL'),
            os.environ.get('DATABASE_PRIVATE_URL'),
            default,
        )
    )


def _validate_database_url(value):
    if not value:
        return
    try:
        make_url(value)
    except ArgumentError as exc:
        raise RuntimeError(
            'DATABASE_URL is not a valid SQLAlchemy database URL. Set only the URL value, '
            'without surrounding quotes or a leading DATABASE_URL= assignment.'
        ) from exc


class Config:
    APP_NAME = os.environ.get('APP_NAME', 'DILG Operations Workspace')
    APP_TAGLINE = os.environ.get('APP_TAGLINE', 'DILG Laguna PDMU Operations System')
    FRONTEND_DIST_DIR = os.environ.get('FRONTEND_DIST_DIR', os.path.join(os.getcwd(), 'frontend_dist'))
    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_env_int('JWT_ACCESS_TOKEN_EXPIRES_MINUTES', 15))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_env_int('JWT_REFRESH_TOKEN_EXPIRES_DAYS', 7))
    AI_PROVIDER_ORDER = _env_list('AI_PROVIDER_ORDER', 'gemini,groq,openrouter')
    AI_REQUEST_TIMEOUT_SECONDS = _env_int('AI_REQUEST_TIMEOUT_SECONDS', 30)
    AI_TEMPERATURE = _env_float('AI_TEMPERATURE', 0.2)
    AI_MAX_OUTPUT_TOKENS = _env_int('AI_MAX_OUTPUT_TOKENS', 1200)
    AI_MAX_PROMPT_CHARS = _env_int('AI_MAX_PROMPT_CHARS', 4000)
    AI_RATE_LIMIT_MESSAGES_PER_15_MIN = _env_int('AI_RATE_LIMIT_MESSAGES_PER_15_MIN', 30)
    AI_RATE_LIMIT_BLOCKED_PER_10_MIN = _env_int('AI_RATE_LIMIT_BLOCKED_PER_10_MIN', 5)
    AI_RATE_LIMIT_HIGH_RISK_PER_10_MIN = _env_int('AI_RATE_LIMIT_HIGH_RISK_PER_10_MIN', 8)
    AI_RATE_LIMIT_CRITICAL_RISK_PER_10_MIN = _env_int('AI_RATE_LIMIT_CRITICAL_RISK_PER_10_MIN', 2)
    AI_OFF_TOPIC_AUTO_REFUSE_THRESHOLD = _env_float('AI_OFF_TOPIC_AUTO_REFUSE_THRESHOLD', 0.85)
    AI_DOCUMENT_CLASSIFICATION_ENABLED = os.environ.get('AI_DOCUMENT_CLASSIFICATION_ENABLED', 'false').lower() == 'true'
    MATCHER_POLICY_PROFILES_ENABLED = _env_bool('MATCHER_POLICY_PROFILES_ENABLED', False)
    MATCHER_EVIDENCE_SELECTION_ENABLED = _env_bool('MATCHER_EVIDENCE_SELECTION_ENABLED', True)
    GROQ_SHARED_COOLDOWNS_ENABLED = _env_bool('GROQ_SHARED_COOLDOWNS_ENABLED', True)
    DOCUMENT_OCR_MAX_PAGES = _env_int('DOCUMENT_OCR_MAX_PAGES', 5)
    DOCUMENT_OCR_MAX_SECONDS = _env_int('DOCUMENT_OCR_MAX_SECONDS', 600)
    DOCUMENT_OCR_WORKERS = _env_int('DOCUMENT_OCR_WORKERS', 2)
    DOCUMENT_OCR_ADAPTIVE_ORIENTATION = _env_bool('DOCUMENT_OCR_ADAPTIVE_ORIENTATION', True)
    DOCUMENT_MAX_EXTRACTED_TEXT_CHARS = _env_int('DOCUMENT_MAX_EXTRACTED_TEXT_CHARS', 12000)
    DOCUMENT_AWS_TEXTRACT_MAX_PAGES = _env_int('DOCUMENT_AWS_TEXTRACT_MAX_PAGES', 5)
    DOCUMENT_LANGUAGE_TOOL_ENABLED = _env_bool('DOCUMENT_LANGUAGE_TOOL_ENABLED', False)
    DOCUMENT_LANGUAGE_TOOL_URL = os.environ.get('DOCUMENT_LANGUAGE_TOOL_URL', 'http://languagetool:8010/v2/check')
    DOCUMENT_LANGUAGE_TOOL_LANGUAGE = os.environ.get('DOCUMENT_LANGUAGE_TOOL_LANGUAGE', 'en-US')
    DOCUMENT_LANGUAGE_TOOL_TIMEOUT_SECONDS = _env_int('DOCUMENT_LANGUAGE_TOOL_TIMEOUT_SECONDS', 8)
    DOCUMENT_LANGUAGE_TOOL_MAX_CHARS = _env_int('DOCUMENT_LANGUAGE_TOOL_MAX_CHARS', 12000)
    DOCUMENT_LANGUAGE_TOOL_MIN_CONFIDENCE = _env_float('DOCUMENT_LANGUAGE_TOOL_MIN_CONFIDENCE', 0.6)
    DOCUMENT_LANGUAGE_TOOL_IGNORE_TERMS = os.environ.get('DOCUMENT_LANGUAGE_TOOL_IGNORE_TERMS', '')
    DOCUMENT_AWS_ENABLED = _env_bool('DOCUMENT_AWS_ENABLED', False)
    DOCUMENT_AWS_REGION = os.environ.get('DOCUMENT_AWS_REGION', 'ap-southeast-1')
    DOCUMENT_AWS_PROFILE_NAME = os.environ.get('DOCUMENT_AWS_PROFILE_NAME', '')
    DOCUMENT_AWS_MAX_SYNC_BYTES = _env_int('DOCUMENT_AWS_MAX_SYNC_BYTES', 10 * 1024 * 1024)
    DOCUMENT_AWS_TEXTRACT_ENABLED = _env_bool('DOCUMENT_AWS_TEXTRACT_ENABLED', True)
    DOCUMENT_AWS_REKOGNITION_ENABLED = _env_bool('DOCUMENT_AWS_REKOGNITION_ENABLED', True)
    DOCUMENT_AWS_TEXTRACT_FEATURE_TYPES = tuple(
        item.strip().upper()
        for item in os.environ.get('DOCUMENT_AWS_TEXTRACT_FEATURE_TYPES', 'TABLES,FORMS,SIGNATURES,LAYOUT').split(',')
        if item.strip()
    )
    DOCUMENT_AWS_REKOGNITION_MAX_LABELS = _env_int('DOCUMENT_AWS_REKOGNITION_MAX_LABELS', 20)
    DOCUMENT_AWS_REKOGNITION_MIN_CONFIDENCE = _env_float('DOCUMENT_AWS_REKOGNITION_MIN_CONFIDENCE', 70.0)
    DOCUMENT_AWS_LOCATION_ENABLED = _env_bool('DOCUMENT_AWS_LOCATION_ENABLED', False)
    DOCUMENT_AWS_LOCATION_PLACE_INDEX = os.environ.get('DOCUMENT_AWS_LOCATION_PLACE_INDEX', '')
    DOCUMENT_AWS_LOCATION_LANGUAGE = os.environ.get('DOCUMENT_AWS_LOCATION_LANGUAGE', 'en')
    DOCUMENT_AWS_CONNECT_TIMEOUT_SECONDS = _env_int('DOCUMENT_AWS_CONNECT_TIMEOUT_SECONDS', 5)
    DOCUMENT_AWS_READ_TIMEOUT_SECONDS = _env_int('DOCUMENT_AWS_READ_TIMEOUT_SECONDS', 20)
    DOCUMENT_AWS_MAX_ATTEMPTS = _env_int('DOCUMENT_AWS_MAX_ATTEMPTS', 2)
    DOCUMENT_AWS_ENABLED_FOR_TESTING = _env_bool('DOCUMENT_AWS_ENABLED_FOR_TESTING', False)
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3.5-flash')
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.1-8b-instant')
    GROQ_BASE_URL = os.environ.get('GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
    OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini')
    OPENROUTER_BASE_URL = os.environ.get('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    OPENROUTER_SITE_URL = os.environ.get('OPENROUTER_SITE_URL')
    OPENROUTER_APP_NAME = os.environ.get('OPENROUTER_APP_NAME', APP_NAME)
    AI_LIVE_PROVIDERS_ENABLED_FOR_TESTING = _env_bool('AI_LIVE_PROVIDERS_ENABLED_FOR_TESTING', False)
    APP_FRONTEND_URL = os.environ.get('APP_FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    ENABLE_PUBLIC_MAGIC_LINKS = os.environ.get('ENABLE_PUBLIC_MAGIC_LINKS', 'false').lower() == 'true'
    MAGIC_LINK_EXPIRY_DAYS = int(os.environ.get('MAGIC_LINK_EXPIRY_DAYS', '15'))
    SUBMISSION_UPLOAD_DIR = os.environ.get('SUBMISSION_UPLOAD_DIR')
    GUIDELINE_UPLOAD_DIR = os.environ.get('GUIDELINE_UPLOAD_DIR')
    IMPORT_UPLOAD_DIR = os.environ.get('IMPORT_UPLOAD_DIR')
    REPORT_TEMPLATE_UPLOAD_DIR = os.environ.get('REPORT_TEMPLATE_UPLOAD_DIR')
    BRANDING_UPLOAD_DIR = os.environ.get('BRANDING_UPLOAD_DIR')
    OBJECT_STORAGE_PROVIDER = os.environ.get('OBJECT_STORAGE_PROVIDER', 'local').strip().lower() or 'local'
    OBJECT_STORAGE_ENV = os.environ.get('OBJECT_STORAGE_ENV', os.environ.get('FLASK_ENV', 'local')).strip().lower() or 'local'
    OBJECT_STORAGE_BUCKET_PREFIX = os.environ.get('OBJECT_STORAGE_BUCKET_PREFIX', 'comet').strip().strip('/') or 'comet'
    OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS = _env_int('OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS', 300)
    OBJECT_STORAGE_TEMP_DIR = os.environ.get('OBJECT_STORAGE_TEMP_DIR')
    OBJECT_STORAGE_LOCAL_DIR = os.environ.get('OBJECT_STORAGE_LOCAL_DIR')
    R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
    R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')
    R2_ENDPOINT_URL = os.environ.get('R2_ENDPOINT_URL')
    R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
    R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
    R2_REGION = os.environ.get('R2_REGION', 'auto')
    MAX_CONTENT_LENGTH = _env_int('MAX_CONTENT_LENGTH', 32 * 1024 * 1024)
    MAX_BRANDING_FILE_BYTES = int(os.environ.get('MAX_BRANDING_FILE_BYTES', str(1024 * 1024)))
    BRANDING_ALLOWED_EXTENSIONS = tuple(
        item.strip().lower().lstrip('.')
        for item in os.environ.get('BRANDING_ALLOWED_EXTENSIONS', 'png,jpg,jpeg,webp').split(',')
        if item.strip()
    )
    BRANDING_ALLOWED_MIME_TYPES = tuple(
        item.strip().lower()
        for item in os.environ.get(
            'BRANDING_ALLOWED_MIME_TYPES',
            'image/png,image/jpeg,image/webp',
        ).split(',')
        if item.strip()
    )
    MAX_SUBMISSION_FILE_BYTES = int(os.environ.get('MAX_SUBMISSION_FILE_BYTES', str(25 * 1024 * 1024)))
    MAX_IMPORT_FILE_BYTES = _env_int('MAX_IMPORT_FILE_BYTES', 25 * 1024 * 1024)
    MAX_IMPORT_PROFILE_ROWS = _env_int('MAX_IMPORT_PROFILE_ROWS', 5000)
    MAX_IMPORT_PROFILE_COLUMNS = _env_int('MAX_IMPORT_PROFILE_COLUMNS', 200)
    SUBMISSION_ALLOWED_EXTENSIONS = tuple(
        item.strip().lower().lstrip('.')
        for item in os.environ.get(
            'SUBMISSION_ALLOWED_EXTENSIONS',
            'pdf,doc,docx,xls,xlsx,ppt,pptx,jpg,jpeg,png,csv',
        ).split(',')
        if item.strip()
    )
    SUBMISSION_ALLOWED_MIME_TYPES = tuple(
        item.strip().lower()
        for item in os.environ.get(
            'SUBMISSION_ALLOWED_MIME_TYPES',
            ','.join([
                'application/pdf',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.ms-powerpoint',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                'image/jpeg',
                'image/png',
                'text/csv',
            ]),
        ).split(',')
        if item.strip()
    )
    GOOGLE_DRIVE_ENABLED = os.environ.get('GOOGLE_DRIVE_ENABLED', 'true').lower() == 'true'
    GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE = os.environ.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE')
    GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON = os.environ.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON')
    GOOGLE_DRIVE_ROOT_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_ROOT_FOLDER_ID')
    GOOGLE_DRIVE_SHARED_DRIVE_ID = os.environ.get('GOOGLE_DRIVE_SHARED_DRIVE_ID')
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    SYSTEM_CONFIG_SECRET_KEY = os.environ.get('SYSTEM_CONFIG_SECRET_KEY') or JWT_SECRET_KEY or SECRET_KEY
    GOOGLE_DRIVE_OAUTH_REDIRECT_URI = os.environ.get(
        'GOOGLE_DRIVE_OAUTH_REDIRECT_URI',
        'http://localhost:5000/api/drive/oauth/callback',
    )
    AUTH_FAILED_LOGIN_LIMIT = _env_int('AUTH_FAILED_LOGIN_LIMIT', 5)
    AUTH_FAILED_PASSWORD_CHANGE_LIMIT = _env_int('AUTH_FAILED_PASSWORD_CHANGE_LIMIT', 5)
    AUTH_FAILURE_WINDOW_MINUTES = _env_int('AUTH_FAILURE_WINDOW_MINUTES', 15)
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'hide_parameters': True,
    }
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
    CELERY_BEAT_SCHEDULE = {
        'monitor-sla-deadlines-hourly': {
            'task': 'app.tasks.sla_monitor.monitor_overdue_deadlines',
            'schedule': 3600.0,
        },
        'process-auto-escalations-hourly': {
            'task': 'app.tasks.escalation_engine.process_auto_escalations',
            'schedule': 3600.0,
        },
        'notify-notice-follow-ups-hourly': {
            'task': 'app.tasks.notice_follow_up.notify_pending_notice_actions',
            'schedule': 3600.0,
        },
        'backup-database-daily': {
            'task': 'app.tasks.db_backup.run_scheduled_backup',
            'schedule': 86400.0,
        },
        'evaluate-compliance-reminders-hourly': {
            'task': 'app.tasks.compliance_reminders.evaluate_compliance_reminders',
            'schedule': 3600.0,
        },
        'recover-pending-notifications-hourly': {
            'task': 'app.tasks.notification_dispatcher.recover_pending_notification_deliveries',
            'schedule': 3600.0,
        },
        'cleanup-operational-events-daily': {
            'task': 'app.tasks.operational_event_cleanup.cleanup_operational_events',
            'schedule': crontab(hour=3, minute=15) if crontab is not None else 86400.0,
        },
    }

    @classmethod
    def init_app(cls, app):
        secret_key = os.environ.get('SECRET_KEY') or app.config.get('SECRET_KEY')
        jwt_secret_key = os.environ.get('JWT_SECRET_KEY') or app.config.get('JWT_SECRET_KEY') or secret_key
        system_config_secret_key = (
            os.environ.get('SYSTEM_CONFIG_SECRET_KEY')
            or app.config.get('SYSTEM_CONFIG_SECRET_KEY')
            or jwt_secret_key
            or secret_key
        )

        app.config['SECRET_KEY'] = secret_key or jwt_secret_key or secrets.token_urlsafe(48)
        app.config['JWT_SECRET_KEY'] = jwt_secret_key or app.config['SECRET_KEY']
        app.config['SYSTEM_CONFIG_SECRET_KEY'] = system_config_secret_key or app.config['JWT_SECRET_KEY']


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = 'development'
    FLASK_ENV = 'development'
    FLASK_CONFIG = 'development'
    SQLALCHEMY_DATABASE_URI = _database_url_from_env('postgresql://postgres:postgres@localhost:5432/workspace_db')


class ProductionConfig(Config):
    DEBUG = False
    ENV = 'production'
    FLASK_ENV = 'production'
    FLASK_CONFIG = 'production'
    SQLALCHEMY_DATABASE_URI = _database_url_from_env()

    @classmethod
    def init_app(cls, app):
        super().init_app(app)

        database_url = _database_url_from_env()
        if database_url:
            _validate_database_url(database_url)
            app.config['SQLALCHEMY_DATABASE_URI'] = database_url

        missing = []
        if not database_url:
            missing.append('DATABASE_URL')
        if not _first_non_empty(os.environ.get('SECRET_KEY'), os.environ.get('JWT_SECRET_KEY')):
            missing.append('SECRET_KEY or JWT_SECRET_KEY')
        if missing:
            raise RuntimeError(f"Missing required production configuration: {', '.join(missing)}")

        for key in ('SECRET_KEY', 'JWT_SECRET_KEY', 'SYSTEM_CONFIG_SECRET_KEY'):
            if len(app.config[key]) < 32:
                raise RuntimeError(f'{key} must be at least 32 characters in production')


class TestingConfig(Config):
    TESTING = True
    ENV = 'testing'
    FLASK_ENV = 'testing'
    FLASK_CONFIG = 'testing'
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL', 'sqlite:///:memory:')
    SECRET_KEY = 'test-secret-key-for-app-suite-1234567890'
    JWT_SECRET_KEY = 'test-jwt-secret-key-for-app-suite-1234567890'
    ENABLE_PUBLIC_MAGIC_LINKS = True
    CELERY_BROKER_URL = 'memory://'
    CELERY_RESULT_BACKEND = 'cache+memory://'
    CELERY_BEAT_SCHEDULE = {}
    OBJECT_STORAGE_PROVIDER = 'local'
    OBJECT_STORAGE_ENV = 'testing'
    AI_LIVE_PROVIDERS_ENABLED_FOR_TESTING = False
    GEMINI_API_KEY = None
    GROQ_API_KEY = None
    OPENROUTER_API_KEY = None

    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        live_enabled = _env_bool('AI_LIVE_PROVIDERS_ENABLED_FOR_TESTING', False)
        app.config['AI_LIVE_PROVIDERS_ENABLED_FOR_TESTING'] = live_enabled
        if not live_enabled:
            app.config['GEMINI_API_KEY'] = None
            app.config['GROQ_API_KEY'] = None
            app.config['OPENROUTER_API_KEY'] = None


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
