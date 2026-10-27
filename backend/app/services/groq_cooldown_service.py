"""Share credential cooldowns across web and Celery processes, without secrets."""
import hashlib
import math

from flask import current_app


# A later failure must never shorten a cooldown another process has recorded.
_EXTEND = '''
local ttl = redis.call('PTTL', KEYS[1])
local duration = tonumber(ARGV[1])
if ttl < duration then redis.call('PSETEX', KEYS[1], duration, '1') end
return redis.call('PTTL', KEYS[1])
'''


def _client():
    if not current_app.config.get('GROQ_SHARED_COOLDOWNS_ENABLED', True):
        return None
    if current_app.config.get('TESTING'):
        return None
    url = current_app.config.get('CELERY_BROKER_URL', '')
    if not url.startswith(('redis://', 'rediss://')):
        return None
    if 'groq_cooldown_redis' not in current_app.extensions:
        import redis
        current_app.extensions['groq_cooldown_redis'] = redis.Redis.from_url(
            url, socket_connect_timeout=.2, socket_timeout=.2,
        )
    return current_app.extensions['groq_cooldown_redis']


def _key(api_key, model, base_url):
    identity = '\0'.join((api_key, model, base_url)).encode()
    return 'comet:groq:cooldown:v1:' + hashlib.sha256(identity).hexdigest()


def remaining(api_key, model, base_url):
    try:
        client = _client()
        if client is not None:
            return max(0, client.pttl(_key(api_key, model, base_url))) / 1000
    except Exception:
        # Redis outages must retain the existing local failover path.
        pass
    return 0.0


def extend(api_key, model, base_url, seconds):
    try:
        client = _client()
        if client is not None:
            client.eval(_EXTEND, 1, _key(api_key, model, base_url), max(1, math.ceil(seconds*1000)))
    except Exception:
        pass
