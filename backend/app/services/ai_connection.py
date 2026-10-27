import json
import os
import re
import socket
import hashlib
import math
import threading
import time
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from flask import current_app

from app.services import ai_guardrails, groq_cooldown_service


RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
DEFAULT_AI_USER_AGENT = 'COMET/1.0'
ALLOWED_AI_URL_SCHEMES = {'https'}

_REAL_URLOPEN = urllib.request.urlopen
_GROQ_POOL_LOCK = threading.Lock()


def _is_testing_environment():
    try:
        if current_app:
            return bool(current_app.config.get('TESTING'))
    except RuntimeError:
        pass
    return bool(os.environ.get('PYTEST_CURRENT_TEST') or os.environ.get('TESTING'))


def _safe_urlopen(request, timeout=30):
    if _is_testing_environment():
        live_enabled = False
        try:
            if current_app:
                live_enabled = bool(current_app.config.get('AI_LIVE_PROVIDERS_ENABLED_FOR_TESTING'))
        except RuntimeError:
            pass
        if not live_enabled:
            active_urlopen = urllib.request.urlopen
            if active_urlopen is _REAL_URLOPEN:
                raise AiProviderFailure(
                    'Live AI provider network requests are disabled during automated testing.',
                    status_code=503,
                    retryable=False,
                )
    return urllib.request.urlopen(request, timeout=timeout)


class AiConnectionError(Exception):
    def __init__(self, message, status_code=502, attempts=None):
        self.message = message
        self.status_code = status_code
        self.attempts = attempts or []
        super().__init__(message)


class AiProviderFailure(Exception):
    def __init__(self, message, status_code=502, retryable=True, retry_after_seconds=None):
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


@dataclass
class AiGenerationResult:
    payload: dict
    provider: str
    model: str
    attempts: list


def generate_json(messages, validator, purpose='general'):
    attempts = []
    providers = _get_provider_clients()
    if not providers:
        raise AiConnectionError(
            'No AI providers are configured. Set at least one provider API key.',
            status_code=503,
            attempts=attempts,
        )

    for provider in providers:
        try:
            response_text = provider.generate_text(messages, purpose=purpose)
            attempts.extend(getattr(provider, 'key_attempts', []))
            parsed = ai_guardrails.extract_json_object(response_text)
            payload = validator(parsed)
            attempts.append(_attempt(provider, 'success', 'ok'))
            return AiGenerationResult(
                payload=payload,
                provider=provider.name,
                model=provider.model,
                attempts=attempts,
            )
        except ai_guardrails.AiGuardrailError as exc:
            attempts.append(_attempt(provider, 'invalid_response', exc.message, retryable=True))
        except (ValueError, TypeError) as exc:
            # Answer validators also reject malformed JSON schemas with these
            # exceptions. Give the next provider a chance instead of aborting.
            attempts.append(_attempt(provider, 'invalid_response', _safe_exception_message(exc), retryable=True))
        except AiProviderFailure as exc:
            key_attempts = getattr(provider, 'key_attempts', [])
            attempts.extend(key_attempts)
            if not key_attempts:
                attempts.append(_attempt(provider, 'failed', exc.message, status_code=exc.status_code, retryable=exc.retryable))

    failure_message = _build_failure_message(attempts)
    try:
        from app.services.operational_event_service import record_operational_event
        record_operational_event(
            severity='ERROR',
            component='ai',
            event_name='ai_providers_exhausted',
            message=failure_message,
            context_data={'attempts': attempts, 'purpose': purpose},
            emit_log=True,
        )
    except Exception:
        pass

    raise AiConnectionError(
        failure_message,
        status_code=_final_status_code(attempts),
        attempts=attempts,
    )


def _get_provider_clients():
    from app.services.system_admin_service import resolve_all_ai_runtime_config
    runtime_config = resolve_all_ai_runtime_config()
    provider_order = runtime_config.get('AI_PROVIDER_ORDER') or ['gemini', 'groq', 'openrouter']
    timeout = runtime_config.get('AI_REQUEST_TIMEOUT_SECONDS', 30)
    temperature = runtime_config.get('AI_TEMPERATURE', 0.2)
    max_tokens = runtime_config.get('AI_MAX_OUTPUT_TOKENS')

    clients = []
    for provider_name in provider_order:
        if provider_name == 'gemini' and _has_configured_secret(runtime_config.get('GEMINI_API_KEY')):
            clients.append(GeminiProvider(
                api_key=runtime_config['GEMINI_API_KEY'],
                model=runtime_config.get('GEMINI_MODEL') or 'gemini-3.5-flash',
                timeout=timeout,
                temperature=temperature,
                max_tokens=max_tokens,
            ))
        elif provider_name == 'groq' and groq_api_keys(runtime_config.get('GROQ_API_KEY')):
            clients.append(GroqProvider(
                name='groq',
                api_key=runtime_config['GROQ_API_KEY'],
                model=runtime_config.get('GROQ_MODEL') or 'llama-3.1-8b-instant',
                base_url=current_app.config.get('GROQ_BASE_URL') or 'https://api.groq.com/openai/v1',
                timeout=timeout,
                temperature=temperature,
                max_tokens=max_tokens,
            ))
        elif provider_name == 'openrouter' and _has_configured_secret(runtime_config.get('OPENROUTER_API_KEY')):
            clients.append(OpenAICompatibleProvider(
                name='openrouter',
                api_key=runtime_config['OPENROUTER_API_KEY'],
                model=runtime_config.get('OPENROUTER_MODEL') or 'openai/gpt-4o-mini',
                base_url=current_app.config.get('OPENROUTER_BASE_URL') or 'https://openrouter.ai/api/v1',
                timeout=timeout,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_headers=_openrouter_headers(current_app.config),
            ))
            # Free model IDs may remain listed after their endpoints disappear.
            # Keep the configured model first, then try OpenRouter's free router.
            # Paid configurations never acquire a different model implicitly.
            if clients[-1].model.endswith(':free'):
                clients.append(OpenAICompatibleProvider(
                    name='openrouter', api_key=runtime_config['OPENROUTER_API_KEY'],
                    model='openrouter/free',
                    base_url=current_app.config.get('OPENROUTER_BASE_URL') or 'https://openrouter.ai/api/v1',
                    timeout=timeout, temperature=temperature, max_tokens=max_tokens,
                    extra_headers=_openrouter_headers(current_app.config),
                ))
    return clients


def _configured_provider_order(config=None):
    from app.services.system_admin_service import resolve_ai_runtime_value
    config_map = config if config is not None else (current_app.config if current_app else {})
    value = resolve_ai_runtime_value('AI_PROVIDER_ORDER') or config_map.get('AI_PROVIDER_ORDER') or ('gemini', 'groq', 'openrouter')
    if isinstance(value, str):
        items = value.split(',')
    else:
        items = value
    return [item.strip().lower() for item in items if str(item).strip()]


def _has_configured_secret(value):
    normalized = str(value or '').strip().lower()
    if not normalized:
        return False
    return normalized not in {'placeholder', 'changeme', 'change-me', 'none', 'null'} and not normalized.startswith(('your-', 'replace-with-'))


def groq_api_keys(value):
    """Normalize the existing secret setting without emitting credentials."""
    return tuple(dict.fromkeys(
        key.strip() for key in str(value or '').split(',')
        if _has_configured_secret(key)
    ))


def _retry_after_seconds(headers):
    value = headers.get('Retry-After') if headers else None
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(1.0, seconds) if math.isfinite(seconds) else None


class GeminiProvider:
    name = 'gemini'

    def __init__(self, api_key, model, timeout=30, temperature=0.2, max_tokens=None):
        self.api_key = api_key
        fallback_chain = ['gemini-3.5-flash', 'gemini-3.1-flash-lite', 'gemini-3.5-flash-lite', 'gemini-flash-latest']
        configured_models = list(model) if isinstance(model, (list, tuple)) else [model]
        self.models = list(dict.fromkeys(
            candidate.strip() for candidate in configured_models + fallback_chain
            if isinstance(candidate, str) and candidate.strip()))
        self.model = self.models[0]
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate_text(self, messages, purpose='general'):
        last_exc = None
        for m in self.models:
            self.model = m
            request = urllib.request.Request(
                _validated_ai_endpoint(_gemini_generate_content_url(m)),
                data=json.dumps(_gemini_request_payload(messages, self.temperature, self.max_tokens)).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'x-goog-api-key': self.api_key,
                },
                method='POST',
            )
            try:
                with _safe_urlopen(request, timeout=self.timeout) as response:  # nosec B310
                    response_payload = json.loads(response.read().decode('utf-8'))
                response_text = _gemini_response_text(response_payload)
                if response_text:
                    return response_text
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 429, 408, 500, 502, 503, 504):
                    last_exc = exc
                    continue
                raw_body = exc.read().decode('utf-8', errors='replace')[:500]
                error_body = _sanitize_upstream_error_body(raw_body)
                raise AiProviderFailure(
                    f'Gemini returned HTTP {exc.code}: {error_body or exc.reason}',
                    status_code=exc.code,
                    retryable=exc.code in RETRYABLE_HTTP_STATUS,
                ) from exc
            except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
                raise AiProviderFailure(
                    f'Gemini connection failed: {_safe_exception_message(exc)}',
                    status_code=503,
                    retryable=True,
                ) from exc

        if last_exc:
            raw_body = last_exc.read().decode('utf-8', errors='replace')[:500]
            error_body = _sanitize_upstream_error_body(raw_body)
            raise AiProviderFailure(
                f'Gemini returned HTTP {last_exc.code}: {error_body or last_exc.reason}',
                status_code=last_exc.code,
                retryable=True,
            ) from last_exc
        raise AiProviderFailure('Gemini returned an empty response.', status_code=502, retryable=True)


class OpenAICompatibleProvider:
    def __init__(self, name, api_key, model, base_url, timeout=30, temperature=0.2, max_tokens=None, extra_headers=None):
        self.name = name
        self.api_key = api_key
        self.model = model
        self.base_url = str(base_url or '').strip().rstrip('/')
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_headers = extra_headers or {}

    def generate_text(self, messages, purpose='general'):
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            'response_format': {'type': 'json_object'},
        }
        if self.max_tokens:
            payload['max_tokens'] = self.max_tokens

        request = urllib.request.Request(
            _validated_ai_endpoint(f'{self.base_url}/chat/completions'),
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': DEFAULT_AI_USER_AGENT,
                **self.extra_headers,
            },
            method='POST',
        )

        try:
            with _safe_urlopen(request, timeout=self.timeout) as response:  # nosec B310
                self.rate_limit_headers = _quota_headers(getattr(response, 'headers', None))
                response_payload = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            self.rate_limit_headers = _quota_headers(exc.headers)
            raw_body = exc.read().decode('utf-8', errors='replace')[:500]
            error_body = _sanitize_upstream_error_body(raw_body)
            raise AiProviderFailure(
                f'{self.name} returned HTTP {exc.code}: {error_body or exc.reason}',
                status_code=exc.code,
                retryable=exc.code in RETRYABLE_HTTP_STATUS,
                retry_after_seconds=_retry_after_seconds(exc.headers),
            ) from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise AiProviderFailure(
                f'{self.name} connection failed: {_safe_exception_message(exc)}',
                status_code=503,
                retryable=True,
            ) from exc
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise AiProviderFailure(
                f'{self.name} returned an unreadable response.',
                status_code=502,
                retryable=True,
            ) from exc

        try:
            self.token_usage = {key: response_payload['usage'][key] for key in
                ('prompt_tokens', 'completion_tokens', 'total_tokens')
                if isinstance(response_payload.get('usage'), dict)
                and isinstance(response_payload['usage'].get(key), int)}
            text = response_payload['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise AiProviderFailure(
                f'{self.name} response did not include a chat message.',
                status_code=502,
                retryable=True,
            ) from exc

        if not text:
            raise AiProviderFailure(f'{self.name} returned an empty response.', status_code=502, retryable=True)
        return text


class GroqProvider(OpenAICompatibleProvider):
    """Bounded key failover; cursor and cooldowns persist per app/worker."""

    def __init__(self, **kwargs):
        self.keys = groq_api_keys(kwargs['api_key'])
        super().__init__(**{**kwargs, 'api_key': self.keys[0] if self.keys else ''})
        fingerprint = hashlib.sha256(json.dumps(
            [self.keys, self.model, self.base_url],
        ).encode()).hexdigest()
        with _GROQ_POOL_LOCK:
            try:
                pools = current_app.extensions
            except RuntimeError:
                pools = {}
            state = pools.get('groq_key_pool')
            if not state or state['fingerprint'] != fingerprint:
                state = {'fingerprint': fingerprint, 'next_index': 0,
                         'cooldowns': [0.0] * len(self.keys)}
                pools['groq_key_pool'] = state
            self.pool = state
        self.key_attempts = []

    def generate_text(self, messages, purpose='general'):
        self.key_attempts = []
        if not self.keys:
            raise AiProviderFailure('No Groq API keys are configured.', 503, False)
        with _GROQ_POOL_LOCK:
            start = self.pool['next_index']
        last_failure = None
        waits = []
        for offset in range(len(self.keys)):
            index = (start + offset) % len(self.keys)
            shared_wait = groq_cooldown_service.remaining(self.keys[index], self.model, self.base_url)
            with _GROQ_POOL_LOCK:
                wait = max(shared_wait, self.pool['cooldowns'][index] - time.monotonic())
                if wait > 0:
                    waits.append(wait)
                    continue
            self.api_key = self.keys[index]
            self.key_index = index + 1
            self.rate_limit_headers, self.token_usage = {}, {}
            try:
                text = super().generate_text(messages, purpose=purpose)
            except AiProviderFailure as exc:
                message = exc.message
                for key in self.keys:
                    message = message.replace(key, '[REDACTED_API_KEY]')
                exc.message = message
                exc.args = (message,)
                self.key_attempts.append(_attempt(
                    self, 'failed', message, exc.status_code, exc.retryable,
                ))
                # Request/model errors cannot be fixed by trying credentials again.
                if not exc.retryable and exc.status_code not in {401, 403}:
                    raise
                cooldown = (exc.retry_after_seconds or 60.0) if exc.status_code == 429 else (
                    300.0 if exc.status_code in {401, 403} else 5.0
                )
                with _GROQ_POOL_LOCK:
                    self.pool['cooldowns'][index] = time.monotonic() + cooldown
                    self.pool['next_index'] = (index + 1) % len(self.keys)
                groq_cooldown_service.extend(self.keys[index], self.model, self.base_url, cooldown)
                last_failure = exc
                continue
            with _GROQ_POOL_LOCK:
                self.pool['next_index'] = index
                self.pool['cooldowns'][index] = 0.0
            return text
        if last_failure:
            raise last_failure
        wait = max(1.0, min(waits)) if waits else 1.0
        raise AiProviderFailure('All Groq API keys are cooling down.', 429, True, wait)


def _quota_headers(headers):
    names = ('retry-after', 'x-ratelimit-limit-requests', 'x-ratelimit-limit-tokens',
             'x-ratelimit-remaining-requests', 'x-ratelimit-remaining-tokens',
             'x-ratelimit-reset-requests', 'x-ratelimit-reset-tokens')
    return {name: str(headers.get(name))[:80] for name in names
            if headers is not None and headers.get(name) is not None}


def _openrouter_headers(config):
    headers = {}
    if config.get('OPENROUTER_SITE_URL'):
        headers['HTTP-Referer'] = config['OPENROUTER_SITE_URL']
    if config.get('OPENROUTER_APP_NAME'):
        headers['X-Title'] = config['OPENROUTER_APP_NAME']
    return headers


def _gemini_generate_content_url(model):
    model_path = str(model or '').strip()
    if not model_path.startswith('models/'):
        model_path = f'models/{model_path}'
    quoted_model_path = urllib.parse.quote(model_path, safe='/')
    return f'https://generativelanguage.googleapis.com/v1beta/{quoted_model_path}:generateContent'


def _validated_ai_endpoint(url):
    parsed = urllib.parse.urlparse(str(url or '').strip())
    if parsed.scheme not in ALLOWED_AI_URL_SCHEMES or not parsed.netloc:
        raise AiProviderFailure('AI provider endpoint must be an HTTPS URL.', status_code=503, retryable=False)
    if parsed.username or parsed.password:
        raise AiProviderFailure('AI provider endpoint must not include credentials.', status_code=503, retryable=False)
    return urllib.parse.urlunparse(parsed)


def _gemini_request_payload(messages, temperature, max_tokens=None):
    system_parts = []
    contents = []

    for message in messages:
        role = (message.get('role') or 'user').lower()
        content = (message.get('content') or '').strip()
        if not content:
            continue
        if role == 'system':
            system_parts.append({'text': content})
            continue
        gemini_role = 'model' if role == 'assistant' else 'user'
        contents.append({
            'role': gemini_role,
            'parts': [{'text': content}],
        })

    generation_config = {
        'temperature': temperature,
        'responseMimeType': 'application/json',
    }
    if max_tokens:
        generation_config['maxOutputTokens'] = max_tokens

    payload = {
        'contents': contents,
        'generationConfig': generation_config,
    }
    if system_parts:
        payload['system_instruction'] = {'parts': system_parts}
    return payload


def _gemini_response_text(response_payload):
    try:
        parts = response_payload['candidates'][0]['content']['parts']
    except (KeyError, IndexError, TypeError) as exc:
        raise AiProviderFailure(
            'Gemini response did not include generated content.',
            status_code=502,
            retryable=True,
        ) from exc

    if not isinstance(parts, list):
        raise AiProviderFailure('Gemini returned invalid content parts.', status_code=502, retryable=True)
    text = ''.join(part['text'] for part in parts
                   if isinstance(part, dict) and isinstance(part.get('text'), str)
                   and not part.get('thought'))
    if not text.strip():
        raise AiProviderFailure('Gemini returned an empty response.', status_code=502, retryable=True)
    return text


def _attempt(provider, status, message, status_code=None, retryable=None):
    attempt = {
        'provider': provider.name,
        'model': provider.model,
        'status': status,
        'message': _sanitize_upstream_error_body(str(message)[:500]),
        'status_code': status_code,
        'retryable': retryable,
    }
    if hasattr(provider, 'key_index'):
        attempt['key_index'] = provider.key_index
    if getattr(provider, 'rate_limit_headers', None):
        attempt['rate_limit_headers'] = provider.rate_limit_headers
    if getattr(provider, 'token_usage', None):
        attempt['token_usage'] = provider.token_usage
    return attempt


def _build_failure_message(attempts):
    provider_names = ', '.join(f"{item['provider']}:{item['status']}" for item in attempts)
    return f'All configured AI providers failed ({provider_names}).'


def _final_status_code(attempts):
    if any(item.get('status_code') == 429 for item in attempts):
        return 429
    if any(item.get('status_code') in {401, 403} for item in attempts):
        return 503
    return 502


AI_KEY_REDACTION_PATTERNS = [
    (re.compile(r'AIza[0-9A-Za-z\-_]{15,}'), '[REDACTED_API_KEY]'),
    (re.compile(r'gsk_[0-9A-Za-z\-_]{15,}'), '[REDACTED_API_KEY]'),
    (re.compile(r'sk-or-[0-9A-Za-z\-_]{10,}'), '[REDACTED_API_KEY]'),
    (re.compile(r'sk-[0-9A-Za-z\-_]{15,}'), '[REDACTED_API_KEY]'),
    (re.compile(r'(?i)([?&](?:api[_-]?key|key|token)=)[^&\s"\']+'), r'\g<1>[REDACTED_API_KEY]'),
    (re.compile(r'(?i)["\']?(?:api[_-]?key|token|access[_-]?token|key|secret)["\']?\s*[:=]\s*["\']?[^\s,"\'};&]+["\']?'), r'api_key=[REDACTED]'),
]


def _sanitize_upstream_error_body(raw_text):
    if not raw_text:
        return ''
    text = str(raw_text)
    try:
        from app.logging_config import redact_sensitive_string
        text = redact_sensitive_string(text)
    except Exception:
        pass
    for pattern, replacement in AI_KEY_REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.replace('\n', ' ').strip()[:500]


def _safe_exception_message(exc):
    return _sanitize_upstream_error_body(str(exc))
