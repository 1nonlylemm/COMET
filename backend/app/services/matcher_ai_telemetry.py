"""Allowlisted provider diagnostics and per-execution public verification metadata."""

import math
import re
import uuid
from datetime import datetime, timezone

from flask import has_request_context, request

ATTEMPT_STATUSES = {'success', 'failed', 'invalid_response', 'rate_limited', 'skipped'}
USAGE_KEYS = {'input_tokens', 'output_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens'}


def _identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_./:@+\-]{1,200}', value) else None


def sanitized_attempts(attempts):
    result = []
    if not isinstance(attempts, list):
        return result
    for attempt in attempts[:100]:
        if not isinstance(attempt, dict):
            continue
        status = attempt.get('status')
        item = {'status': status if isinstance(status, str) and status in ATTEMPT_STATUSES else 'unknown'}
        for key in ('provider', 'model'):
            value = _identifier(attempt.get(key))
            if value:
                item[key] = value
        code = attempt.get('status_code')
        if type(code) is int and 100 <= code <= 599:
            item['status_code'] = code
        if isinstance(attempt.get('retryable'), bool):
            item['retryable'] = attempt['retryable']
        usage = attempt.get('token_usage')
        if isinstance(usage, dict):
            item['token_usage'] = {k: v for k, v in usage.items() if k in USAGE_KEYS and type(v) is int and v >= 0}
        latency = attempt.get('latency_ms')
        if type(latency) in (int, float) and math.isfinite(latency) and latency >= 0:
            item['latency_ms'] = latency
        result.append(item)
    return result


def live_execution_metadata(generation):
    verification_id = None
    if has_request_context():
        try:
            verification_id = str(uuid.UUID(request.headers.get('X-Comet-Verification-ID', '')))
        except (ValueError, AttributeError):
            pass
    return {
        'refinement_status': 'live',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'verification_request_id': verification_id,
        'cache_only': False,
        'attempts': sanitized_attempts(generation.attempts),
    }


def unavailable_metadata(error=None):
    return {
        'project_requirement_id': None,
        'confidence': 0,
        'refinement_status': 'unavailable',
        'error_category': 'provider_unavailable' if error is not None else 'internal_error',
        'attempts': sanitized_attempts(getattr(error, 'attempts', [])),
    }
