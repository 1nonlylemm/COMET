"""Request validators for the unified Reference Library API.

These validators mirror the shape of the existing governance validators
in ``app.api.governance.schemas``: they accept a payload dict and return a
``{field_name: human_message}`` mapping suitable for
``app.utils.response.validation_error``. An empty dict means the payload
passed validation.

Two entry points are exposed:

- ``validate_reference_payload(data, partial=False, role=None)`` is used by
  the ``POST`` and ``PUT`` ``/api/library/references`` routes. It validates
  ``reference_type`` first (Req 2.3), then delegates to
  ``governance.schemas.validate_guideline_payload`` for view-only fields
  (Req 5.5, 5.6, 5.7, 5.8, 5.10) and adds template-specific validation
  for ``template_subtype``, ``label``, ``is_default``, and
  ``placeholder_defaults`` when ``reference_type == 'template'`` (Req 4.4,
  4.12).
- ``validate_template_payload(data, partial=False)`` is used by template
  metadata edits that do not change the underlying file (Req 4.12).
"""

from __future__ import annotations

import json
from typing import Optional

from app.api.governance.schemas import validate_guideline_payload
from app.services import library_service, settings_service


# Maximum label length that ``settings_service._clean_template_label`` will
# preserve. Anything longer is silently truncated by the legacy service; we
# surface a validation error here so the caller is never surprised by a
# silent truncation.
TEMPLATE_LABEL_MAX_LENGTH = 120

# Strings that ``is_default`` may be sent as in addition to native bools.
# Settings service ultimately calls ``bool(value)`` which would accept any
# non-empty string as true; we want a stricter, explicit accept-list so a
# typo such as ``"flase"`` does not silently flip the default.
_TRUE_STRINGS = {'true', '1', 'yes', 'on'}
_FALSE_STRINGS = {'false', '0', 'no', 'off', ''}


def validate_reference_payload(
    data,
    partial: bool = False,
    role: Optional[str] = None,
) -> dict:
    """Validate a Library create/update payload.

    Args:
        data: The request payload.
        partial: ``True`` for ``PUT`` (update) calls so missing fields are
            tolerated; ``False`` for ``POST`` (create) calls so all
            required fields must be present.
        role: The acting user's role. Currently unused. The parameter is
            accepted so future role-scoped validation rules can be added
            without changing the route layer signature; the route handlers
            already pass it through.

    Returns:
        ``{}`` when the payload is valid, otherwise a
        ``{field_name: message}`` mapping shaped identically to the result
        of ``governance.schemas.validate_guideline_payload``.
    """
    # ``role`` is accepted but not consumed today; see the docstring above.
    del role

    if not isinstance(data, dict):
        data = dict(data or {})

    errors: dict = {}

    reference_type_present = 'reference_type' in data
    reference_type = data.get('reference_type') if reference_type_present else None

    if not partial or reference_type_present:
        if _is_blank(reference_type):
            errors['reference_type'] = 'Reference type is required.'
        elif reference_type not in library_service.VALID_REFERENCE_TYPES:
            errors['reference_type'] = 'Select a supported reference type.'

    # If reference_type itself is invalid we cannot dispatch to a per-type
    # validator; surface only the reference_type error in that case so the
    # caller fixes the root mistake first. This mirrors how
    # governance.schemas short-circuits an unknown ``guideline_type``.
    if 'reference_type' in errors:
        return errors

    if reference_type in library_service.VIEW_ONLY_REFERENCE_TYPES:
        errors.update(_validate_view_only_payload(data, partial=partial))
    elif reference_type == 'template':
        errors.update(_validate_template_fields(data, partial=partial, creating=True))
    elif partial and not reference_type_present:
        # Update (PUT) without a reference_type: we cannot know which
        # validator to apply. Validate any template-shaped fields if
        # present; otherwise validate guideline-shaped fields. Templates
        # and view-only references share no overlapping field names
        # outside of ``title`` (which validate_guideline_payload accepts
        # as optional under partial=True), so a dual pass is safe.
        errors.update(_validate_view_only_payload(data, partial=True))
        errors.update(_validate_template_fields(data, partial=True, creating=False))

    return errors


def validate_template_payload(data, partial: bool = False) -> dict:
    """Validate a template metadata edit payload.

    Used for ``update_reference`` calls that change only ``label``,
    ``is_default``, or ``placeholder_defaults`` without re-uploading the
    underlying DOCX (Req 4.12). Returns ``{}`` when valid, otherwise a
    ``{field_name: message}`` mapping.
    """
    if not isinstance(data, dict):
        data = dict(data or {})

    return _validate_template_fields(data, partial=partial, creating=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_view_only_payload(data, *, partial: bool) -> dict:
    """Validate the fields shared with ``ProgramGuideline`` create/update.

    Translates ``reference_type`` -> ``guideline_type`` so the existing
    ``validate_guideline_payload`` helper can be reused without changes,
    then translates any ``guideline_type`` errors it returns back to
    ``reference_type`` so the caller receives field names from the public
    Library payload, not the legacy governance payload.
    """
    translated = dict(data)
    if 'reference_type' in translated:
        translated['guideline_type'] = translated.pop('reference_type')

    raw = validate_guideline_payload(translated, partial=partial) or {}
    if not raw:
        return {}

    translated_errors = {}
    for field, message in raw.items():
        if field == 'guideline_type':
            translated_errors['reference_type'] = message
        else:
            translated_errors[field] = message
    return translated_errors


def _validate_template_fields(data, *, partial: bool, creating: bool) -> dict:
    """Validate template-specific fields.

    When ``creating`` is true, ``template_subtype`` is required unless
    ``partial`` is true (the latter is only used by ``PUT`` flows that do
    not touch the subtype). Other fields (``label``, ``is_default``,
    ``placeholder_defaults``) are always optional and only validated when
    present.
    """
    errors: dict = {}

    template_subtype_present = 'template_subtype' in data
    template_subtype = data.get('template_subtype') if template_subtype_present else None

    require_subtype = creating and not partial
    if require_subtype or template_subtype_present:
        if _is_blank(template_subtype):
            errors['template_subtype'] = 'Template subtype is required.'
        elif template_subtype not in settings_service.DOCUMENT_TEMPLATE_TYPES:
            errors['template_subtype'] = 'Select a supported template subtype.'

    if 'label' in data:
        label_error = _validate_label(data.get('label'))
        if label_error:
            errors['label'] = label_error

    if 'is_default' in data:
        is_default_error = _validate_is_default(data.get('is_default'))
        if is_default_error:
            errors['is_default'] = is_default_error

    if 'placeholder_defaults' in data:
        placeholder_error = _validate_placeholder_defaults(data.get('placeholder_defaults'))
        if placeholder_error:
            errors['placeholder_defaults'] = placeholder_error

    return errors


def _validate_label(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return 'Label must be text.'
    if len(value.strip()) > TEMPLATE_LABEL_MAX_LENGTH:
        return f'Label must be {TEMPLATE_LABEL_MAX_LENGTH} characters or less.'
    return None


def _validate_is_default(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return None if value in (0, 1) else 'Default flag must be true or false.'
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_STRINGS or normalized in _FALSE_STRINGS:
            return None
        return 'Default flag must be true or false.'
    return 'Default flag must be true or false.'


def _validate_placeholder_defaults(value):
    if value is None or value == '':
        return None
    if isinstance(value, dict):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return 'Placeholder defaults must be a valid JSON object.'
    else:
        return 'Placeholder defaults must be an object.'
    if not isinstance(parsed, dict):
        return 'Placeholder defaults must be an object.'
    return None


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())
