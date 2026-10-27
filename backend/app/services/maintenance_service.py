import json
import logging
import os
from datetime import datetime, timezone
from flask import current_app

logger = logging.getLogger(__name__)

_IN_MEMORY_MAINTENANCE = {'active': False, 'reason': '', 'started_at': None}


def _redis_client(socket_timeout=None):
    from flask import has_app_context
    url = None
    if has_app_context():
        url = current_app.config.get('CELERY_BROKER_URL')
    url = url or os.environ.get('CELERY_BROKER_URL') or 'redis://redis:6379/0'

    if url.startswith('memory://'):
        return None
    try:
        import redis
        kwargs = {'decode_responses': True, 'socket_connect_timeout': 2}
        if socket_timeout is not None:
            kwargs['socket_timeout'] = socket_timeout
        return redis.Redis.from_url(url, **kwargs)
    except Exception as exc:
        logger.warning('Unable to connect to Redis for maintenance mode: %s', exc)
        try:
            from app.services.operational_event_service import record_operational_event
            record_operational_event(
                severity='WARNING',
                component='redis',
                event_name='redis_connection_failed',
                message=f'Unable to connect to Redis for maintenance mode: {exc}',
                exc_info=exc,
                emit_log=False,
            )
        except Exception:
            pass
        return None


def set_maintenance_mode(active=True, reason='System is currently undergoing a database restore.'):
    info = {
        'active': bool(active),
        'reason': reason or 'System is currently undergoing a database restore.',
        'started_at': datetime.now(timezone.utc).isoformat() if active else None,
    }
    client = _redis_client()
    if client:
        try:
            if active:
                client.set('comet:maintenance_mode', json.dumps(info), ex=7200)  # 2 hr safety TTL
            else:
                client.delete('comet:maintenance_mode')
        except Exception as exc:
            logger.warning('Failed to update maintenance mode in Redis: %s', exc)

    global _IN_MEMORY_MAINTENANCE
    _IN_MEMORY_MAINTENANCE = info
    return info


def get_maintenance_info():
    client = _redis_client()
    if client:
        try:
            raw = client.get('comet:maintenance_mode')
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.warning('Failed to read maintenance mode from Redis: %s', exc)

    global _IN_MEMORY_MAINTENANCE
    return _IN_MEMORY_MAINTENANCE


def is_maintenance_mode():
    return bool(get_maintenance_info().get('active'))
