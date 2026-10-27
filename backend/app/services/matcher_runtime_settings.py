"""Validation shared by both technical-settings write paths."""

REFINEMENT_KEY = 'AI_DOCUMENT_CLASSIFICATION_ENABLED'
REFINEMENT_ALIAS = 'provider_refinement_enabled'


def parse_refinement_boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes', 'on'}:
            return True
        if normalized in {'false', '0', 'no', 'off'}:
            return False
    from app.services.settings_service import SettingsError
    raise SettingsError(f'{REFINEMENT_KEY} must be a boolean or a recognized boolean string.', 422)


def normalize_refinement_updates(updates):
    if not isinstance(updates, dict):
        return updates
    normalized = dict(updates)
    if REFINEMENT_ALIAS in normalized:
        alias_value = parse_refinement_boolean(normalized.pop(REFINEMENT_ALIAS))
        if REFINEMENT_KEY in normalized and parse_refinement_boolean(normalized[REFINEMENT_KEY]) != alias_value:
            from app.services.settings_service import SettingsError
            raise SettingsError('Conflicting AI refinement settings.', 422)
        normalized[REFINEMENT_KEY] = alias_value
    if REFINEMENT_KEY in normalized:
        normalized[REFINEMENT_KEY] = parse_refinement_boolean(normalized[REFINEMENT_KEY])
    return normalized
