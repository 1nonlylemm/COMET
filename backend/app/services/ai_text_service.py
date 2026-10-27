from app.extensions import db
from app.models import User
from app.services import ai_connection, ai_guardrails, audit_service, settings_service


AI_ALLOWED_ROLES = {'admin', 'staff', 'field_officer'}
VALID_REWRITE_MODES = set(ai_guardrails.TEXT_REWRITE_MODE_INSTRUCTIONS.keys())
MAX_REWRITE_CHARS = 4000


class AiTextRewriteError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def rewrite_text(text, mode='polish', context_label=None, user_id=None):
    user = _require_ai_user(user_id)
    normalized_text = _normalize_text(text)
    normalized_mode = str(mode or 'polish').strip().lower()
    if normalized_mode not in VALID_REWRITE_MODES:
        raise AiTextRewriteError(
            f'mode must be one of: {", ".join(sorted(VALID_REWRITE_MODES))}',
            422,
        )
    if not normalized_text:
        raise AiTextRewriteError('Text is required for AI rewrite.', 422)
    if len(normalized_text) < 3:
        raise AiTextRewriteError('Text is too short to rewrite.', 422)
    if len(normalized_text) > MAX_REWRITE_CHARS:
        raise AiTextRewriteError(f'Text must be {MAX_REWRITE_CHARS} characters or fewer.', 413)

    decision = ai_guardrails.evaluate_text_rewrite_request(normalized_text, user)
    if not decision.allowed:
        event = ai_guardrails.record_conversational_guardrail_event(
            decision,
            normalized_text,
            user_id=user.id,
            provider_called=False,
            metadata={
                'feature': 'text_rewrite',
                'mode': normalized_mode,
                'context_label': _safe_context_label(context_label),
            },
        )
        _audit_text_rewrite(
            user,
            decision,
            event.id,
            provider='local',
            model='local:guardrail-router',
            text_length=len(normalized_text),
        )
        db.session.commit()
        raise AiTextRewriteError(decision.safe_reply, decision.status_code)

    messages = ai_guardrails.build_text_rewrite_messages(
        text=normalized_text,
        mode=normalized_mode,
        context_label=context_label,
    )

    try:
        generation = ai_connection.generate_json(
            messages=messages,
            validator=ai_guardrails.validate_text_rewrite_payload,
            purpose='workspace_text_rewrite',
        )
        rewritten_text = _clean_rewritten_text(generation.payload['rewritten_text'])
        if not rewritten_text:
            rewritten_text = _local_rewrite(normalized_text, normalized_mode)
        provider = generation.provider
        model = f'{generation.provider}:{generation.model}'
        attempts = generation.attempts
    except ai_connection.AiConnectionError:
        rewritten_text = _local_rewrite(normalized_text, normalized_mode)
        provider = 'local'
        model = 'local:text-rewrite-fallback'
        attempts = []

    event = ai_guardrails.record_conversational_guardrail_event(
        decision,
        normalized_text,
        user_id=user.id,
        provider_called=provider != 'local',
        metadata={
            'feature': 'text_rewrite',
            'mode': normalized_mode,
            'context_label': _safe_context_label(context_label),
            'ai_provider_used': provider,
            'ai_model_used': model,
        },
    )
    _audit_text_rewrite(
        user,
        decision,
        event.id,
        provider=provider,
        model=model,
        text_length=len(normalized_text),
    )
    db.session.commit()

    return {
        'rewritten_text': rewritten_text,
        'mode': normalized_mode,
        'context_label': _safe_context_label(context_label),
        'ai_provider_used': provider,
        'ai_model_used': model,
    }


def _require_ai_user(user_id):
    try:
        coerced_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise AiTextRewriteError('Invalid or missing assistant user identity.', 401) from exc

    user = db.session.get(User, coerced_user_id)
    if not user:
        raise AiTextRewriteError('User not found or deactivated.', 401)
    if not user.is_active:
        raise AiTextRewriteError('Account is deactivated.', 403)
    if user.role not in AI_ALLOWED_ROLES:
        raise AiTextRewriteError(f'This account is not authorized to use {_assistant_name()}.', 403)
    return user


def _normalize_text(value):
    return ' '.join(str(value or '').strip().split())


def _safe_context_label(value):
    label = ' '.join(str(value or '').strip().split())
    return label[:120] if label else f'{_app_name()} note'


def _local_rewrite(text, mode):
    cleaned = _normalize_text(text)
    cleaned = cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
    if cleaned and cleaned[-1] not in '.!?':
        cleaned = f'{cleaned}.'

    if mode == 'concise':
        return cleaned
    if mode == 'formal':
        return f'Please review and address the following: {cleaned}'
    if mode == 'expand':
        return f'Please review and address the following item: {cleaned} Submit the corrected document for re-evaluation.'
    if mode == 'paraphrase':
        return f'The following item requires attention: {cleaned}'
    return cleaned


def _clean_rewritten_text(value):
    cleaned = _normalize_text(value)
    prefixes = (
        'rewritten text:',
        'rewrite:',
        'formal rewrite:',
        'polished text:',
        'paraphrase:',
        'revision note:',
        'revised note:',
    )

    for _ in range(2):
        lowered = cleaned.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        else:
            break

    return cleaned.lstrip(' "\':;,-')


def _audit_text_rewrite(user, decision, event_id, provider, model, text_length):
    audit_service.log_action(
        user_id=user.id,
        action='ai_text_rewrite',
        entity_type='ai_guardrail_event',
        entity_id=event_id,
        old_value=None,
        new_value={
            'decision': decision.decision,
            'category': decision.category,
            'severity': decision.severity,
            'provider': provider,
            'model': model,
            'text_length': text_length,
        },
    )


def _app_name():
    try:
        return settings_service.get_app_name()
    except Exception:
        return 'DILG Operations Workspace'


def _assistant_name():
    try:
        return settings_service.get_assistant_name()
    except Exception:
        return 'DILG Operations Workspace Assistant'
