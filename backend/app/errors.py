import re
import time
import uuid

from flask import g, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.extensions import db
from app.services.operational_event_service import record_operational_event
from app.utils.response import error_response


HTTP_ERROR_MESSAGES = {
    400: 'Malformed request. Check the request body and parameters.',
    404: 'Resource not found',
    405: 'Method not allowed',
    413: 'Request payload is too large.',
    415: 'Unsupported media type. Use application/json or multipart/form-data as required.',
}

SAFE_REQUEST_ID_REGEX = re.compile(r'^[a-zA-Z0-9_\-\.]{1,64}$')


def register_error_handlers(app):
    @app.before_request
    def attach_request_id():
        g.request_start_time = time.perf_counter()
        incoming_request_id = request.headers.get('X-Request-ID')
        g.request_id = _clean_request_id(incoming_request_id) or uuid.uuid4().hex

    @app.after_request
    def add_request_id_header(response):
        if hasattr(g, 'request_start_time'):
            g.request_duration_ms = round((time.perf_counter() - g.request_start_time) * 1000, 2)
        request_id = getattr(g, 'request_id', None)
        if request_id:
            response.headers['X-Request-ID'] = request_id
        return response

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        status_code = exc.code or 500
        message = HTTP_ERROR_MESSAGES.get(status_code) or exc.description or exc.name
        _log_handled_error(app, exc, status_code=status_code)
        return error_response(message=message, status_code=status_code)

    from app.services.access_service import AccessError

    @app.errorhandler(AccessError)
    def handle_access_error(exc):
        _rollback_session()
        _log_handled_error(app, exc, status_code=exc.status_code)
        return error_response(message=exc.message, status_code=exc.status_code)

    from app.services.object_storage_service import ObjectStorageError

    ALLOWED_STORAGE_STATUS_CODES = {400, 404, 409, 502, 503, 504}
    SAFE_STORAGE_MESSAGES = {
        404: 'Requested stored file or object was not found.',
        502: 'External object storage service is temporarily unavailable. Please retry shortly.',
        503: 'External object storage service is temporarily unavailable. Please retry shortly.',
        504: 'External object storage request timed out. Please retry shortly.',
    }

    @app.errorhandler(ObjectStorageError)
    def handle_object_storage_error(exc):
        _rollback_session()
        raw_code = getattr(exc, 'status_code', 502)
        status_code = raw_code if raw_code in ALLOWED_STORAGE_STATUS_CODES else 502
        safe_message = SAFE_STORAGE_MESSAGES.get(status_code, 'External object storage service failure.')
        _log_handled_error(app, exc, status_code=status_code)
        if status_code >= 500:
            record_operational_event(
                severity='ERROR',
                component='storage',
                event_name='object_storage_error',
                message=f"Object storage error ({status_code}): {exc}",
                request_id=getattr(g, 'request_id', None),
                context_data={
                    'method': request.method,
                    'path': request.path,
                    'status_code': status_code,
                },
                exc_info=exc,
                emit_log=False,
            )
        return error_response(message=safe_message, status_code=status_code)

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(exc):
        _rollback_session()
        app.logger.warning(
            'Database integrity error request_id=%s path=%s method=%s error=%s',
            getattr(g, 'request_id', None),
            request.path,
            request.method,
            exc,
            exc_info=True,
            extra={
                'event': 'database_integrity_error',
                'component': 'database',
            },
        )
        record_operational_event(
            severity='WARNING',
            component='database',
            event_name='database_integrity_error',
            message=f"Database integrity error: {exc}",
            request_id=getattr(g, 'request_id', None),
            context_data={
                'method': request.method,
                'path': request.path,
                'status_code': 500,
            },
            exc_info=exc,
            emit_log=False,
        )
        return error_response(
            message='Database operation failed.',
            status_code=500,
        )

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(exc):
        _rollback_session()
        app.logger.exception(
            'Unhandled database error request_id=%s path=%s method=%s',
            getattr(g, 'request_id', None),
            request.path,
            request.method,
            exc_info=True,
            extra={
                'event': 'database_error',
                'component': 'database',
            },
        )
        record_operational_event(
            severity='ERROR',
            component='database',
            event_name='database_error',
            message=f"Unhandled database error: {exc}",
            request_id=getattr(g, 'request_id', None),
            context_data={
                'method': request.method,
                'path': request.path,
                'status_code': 500,
            },
            exc_info=exc,
            emit_log=False,
        )
        return error_response(message='Database operation failed.', status_code=500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        _rollback_session()
        app.logger.exception(
            'Unhandled application error request_id=%s path=%s method=%s',
            getattr(g, 'request_id', None),
            request.path,
            request.method,
            exc_info=True,
            extra={
                'event': 'unhandled_application_error',
                'component': 'api',
            },
        )
        record_operational_event(
            severity='ERROR',
            component='api',
            event_name='unhandled_application_error',
            message=f"Unhandled application error ({type(exc).__name__}): {exc}",
            request_id=getattr(g, 'request_id', None),
            context_data={
                'method': request.method,
                'path': request.path,
                'status_code': 500,
                'exception_type': type(exc).__name__,
            },
            exc_info=exc,
            emit_log=False,
        )
        return error_response(message='Internal server error', status_code=500)


def _clean_request_id(value):
    if not value:
        return None
    text = str(value).strip()
    if not text or len(text) > 64:
        return None
    if not SAFE_REQUEST_ID_REGEX.match(text):
        return None
    return text


def _rollback_session():
    try:
        db.session.rollback()
    except Exception:
        db.session.remove()


def _log_handled_error(app, exc, status_code):
    request_id = getattr(g, 'request_id', None)
    if status_code < 500:
        app.logger.info(
            'Handled API error status=%s request_id=%s path=%s method=%s error=%s',
            status_code,
            request_id,
            request.path,
            request.method,
            exc,
            extra={
                'event': 'handled_api_error',
                'component': 'api',
                'status_code': status_code,
            },
        )
        return

    app.logger.exception(
        'Handled server error status=%s request_id=%s path=%s method=%s',
        status_code,
        request_id,
        request.path,
        request.method,
        exc_info=True,
        extra={
            'event': 'handled_server_error',
            'component': 'api',
            'status_code': status_code,
        },
    )
    record_operational_event(
        severity='ERROR',
        component='api',
        event_name='server_error',
        message=f"Server error ({status_code}): {exc}",
        request_id=request_id,
        context_data={
            'method': request.method,
            'path': request.path,
            'status_code': status_code,
        },
        exc_info=exc,
        emit_log=False,
    )
