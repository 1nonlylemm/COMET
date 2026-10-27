"""Reference Library service facade.

This module is a scaffold. The full facade (listing, get, create, update,
delete, apply-template, download) is implemented in later tasks. The Reference
URI codec (``encode_reference_uri`` / ``decode_reference_uri``) is implemented
here because every other operation in the facade is keyed off the URI.
"""

from __future__ import annotations

import re
from typing import Optional


class LibraryError(Exception):
    """Raised by ``library_service`` when a Library operation fails.

    Attributes:
        message: Human-readable error message.
        status_code: HTTP status code the API layer should surface
            (defaults to 400).
        errors: Optional field-level error map shaped like the existing
            ``validation_error`` response (``{field_name: message}``).
    """

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        errors: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.errors = errors or {}


# The seven valid Reference_Type values. The first six are View_Only_Reference
# types backed by the ``program_guidelines`` table; ``template`` is backed by
# the ``SystemConfig`` JSON catalog.
VALID_REFERENCE_TYPES = (
    'memorandum',
    'circular',
    'annex',
    'local_budget_circular',
    'omnibus_guideline',
    'other',
    'template',
)


# Reference_Types that cannot be applied to a Generation_Flow. This is every
# valid Reference_Type except ``template``.
VIEW_ONLY_REFERENCE_TYPES = VALID_REFERENCE_TYPES[:-1]


# ---------------------------------------------------------------------------
# Reference URI codec
# ---------------------------------------------------------------------------
#
# The Library exposes a single public identifier per Reference, the
# "Reference URI". It is the only id the API surface accepts and emits, so the
# frontend never has to know which backing store a Reference came from.
#
# Grammar (see design.md "Reference URI"):
#
#     guideline:<positive_integer>
#     template:<template_subtype>:<hex_template_id>
#
# - ``<positive_integer>`` is a base-10 integer >= 1 with no leading zeros and
#   no sign.
# - ``<template_subtype>`` is a key of
#   ``settings_service.DOCUMENT_TEMPLATE_TYPES`` (lowercase letters and
#   underscores, e.g. ``project_revision_report``).
# - ``<hex_template_id>`` is a non-empty hex string (the
#   ``uuid.uuid4().hex`` value persisted by ``settings_service``). Both upper
#   and lower case hex digits are accepted on decode; encoding emits the
#   string unchanged.

_GUIDELINE_URI_RE = re.compile(r'^guideline:([1-9]\d*)$')
_TEMPLATE_URI_RE = re.compile(r'^template:([a-z][a-z0-9_]*):([0-9a-fA-F]+)$')
_HEX_RE = re.compile(r'^[0-9a-fA-F]+$')


def _reference_uri_error(message: str) -> 'LibraryError':
    return LibraryError(
        message,
        status_code=422,
        errors={'reference_uri': message},
    )


def encode_reference_uri(
    origin: str,
    *,
    guideline_id: int | None = None,
    template_subtype: str | None = None,
    template_id: str | None = None,
) -> str:
    """Encode a Reference identifier into its public URI form.

    Raises ``ValueError`` for invalid arguments. Encoding is only ever called
    with values produced internally (DB rows, catalog entries), so a bad
    input here is a programmer error rather than a user-input validation
    failure; callers should not catch ``LibraryError`` from this function.
    """
    # Avoid importing ``settings_service`` at module load time; ``library_service``
    # is imported very early during app startup.
    from app.services import settings_service

    if origin == 'guideline':
        # ``bool`` is a subclass of ``int`` — exclude it explicitly so that
        # ``encode_reference_uri('guideline', guideline_id=True)`` doesn't
        # silently produce ``'guideline:1'``.
        if not isinstance(guideline_id, int) or isinstance(guideline_id, bool) or guideline_id <= 0:
            raise ValueError('guideline_id must be a positive integer')
        if template_subtype is not None or template_id is not None:
            raise ValueError("template_subtype and template_id must be None when origin='guideline'")
        return f'guideline:{guideline_id}'

    if origin == 'template':
        if template_subtype not in settings_service.DOCUMENT_TEMPLATE_TYPES:
            raise ValueError(
                'template_subtype must be a key of settings_service.DOCUMENT_TEMPLATE_TYPES'
            )
        if not isinstance(template_id, str) or not _HEX_RE.match(template_id):
            raise ValueError('template_id must be a non-empty hex string')
        if guideline_id is not None:
            raise ValueError("guideline_id must be None when origin='template'")
        return f'template:{template_subtype}:{template_id}'

    raise ValueError(f"Unknown reference URI origin: {origin!r}")


def decode_reference_uri(reference_uri: str) -> dict:
    """Decode a Reference URI into its component parts.

    Returns a dict with the keys ``origin``, ``guideline_id``,
    ``template_subtype``, and ``template_id``. Exactly one of ``guideline_id``
    or (``template_subtype``, ``template_id``) is populated; the other slot is
    ``None``.

    Raises ``LibraryError(422, errors={'reference_uri': ...})`` for any input
    that does not match the documented grammar, including ``None``,
    non-strings, the empty string, unknown origins, malformed integers, hex
    strings with non-hex characters, and template subtypes that are not
    registered in ``settings_service.DOCUMENT_TEMPLATE_TYPES``.
    """
    if not isinstance(reference_uri, str) or not reference_uri:
        raise _reference_uri_error('Reference URI must be a non-empty string.')

    guideline_match = _GUIDELINE_URI_RE.match(reference_uri)
    if guideline_match:
        return {
            'origin': 'guideline',
            'guideline_id': int(guideline_match.group(1)),
            'template_subtype': None,
            'template_id': None,
        }

    template_match = _TEMPLATE_URI_RE.match(reference_uri)
    if template_match:
        # Lazy import to avoid a circular import during app startup.
        from app.services import settings_service

        subtype = template_match.group(1)
        if subtype not in settings_service.DOCUMENT_TEMPLATE_TYPES:
            raise _reference_uri_error(
                f"Unknown template_subtype {subtype!r}; must be one of "
                f"{sorted(settings_service.DOCUMENT_TEMPLATE_TYPES)}."
            )
        return {
            'origin': 'template',
            'guideline_id': None,
            'template_subtype': subtype,
            'template_id': template_match.group(2),
        }

    raise _reference_uri_error(
        'Reference URI must be of the form "guideline:<positive_integer>" '
        'or "template:<template_subtype>:<hex_template_id>".'
    )


# ---------------------------------------------------------------------------
# Reference DTO builders
# ---------------------------------------------------------------------------
#
# Both helpers produce the unified "Reference" dict described in
# ``design.md`` ("Unified Reference DTO" section). The DTO is a strict
# superset of the underlying serializer outputs:
#
# - ``_reference_from_guideline`` uses ``governance_service._serialize_guideline``
#   as a base and adds the unified fields (``reference_uri``, ``reference_type``,
#   ``origin``, ``file_kind``, ``has_downloadable_file``) plus ``None``
#   placeholders for every template-only field.
# - ``_reference_from_template`` uses ``settings_service._serialize_document_template_entry``
#   output as a base (passed in as ``entry``) and adds the unified fields plus
#   ``None`` placeholders for every view-only field.
#
# All keys listed in the design DTO block are always present; fields that do
# not apply to a given origin are set to ``None``. This invariant lets
# downstream code (list_references, get_reference, the API layer) treat a
# Reference uniformly without origin-specific branches.


def _is_external_url(value):
    """Return True if ``value`` looks like an http(s) URL.

    Mirrors ``governance_service._is_external_url`` so that the Library uses
    the same definition of "external" as the legacy guideline endpoints
    (Req 6.4).
    """
    if not value or not isinstance(value, str):
        return False
    return value.startswith('http://') or value.startswith('https://')


def _classify_file(file_path):
    """Map a stored ``file_path`` value to ``(file_kind, has_downloadable_file)``.

    - ``None`` / empty -> ('none', False)
    - http(s) URL    -> ('external_url', False)  (Library cannot stream it,
                                                  the UI offers an "Open" link)
    - anything else  -> ('upload', True)         (local disk or stored_object)
    """
    if not file_path:
        return 'none', False
    if _is_external_url(file_path):
        return 'external_url', False
    return 'upload', True


def _checker_profile_summary(reference_uri):
    from app.services import document_compliance_service

    return document_compliance_service.checker_profile_summary(reference_uri)


def _reference_from_guideline(guideline):
    """Build a Reference DTO for a ``ProgramGuideline`` row.

    Accepts either:

    - a ``ProgramGuideline`` model instance (used by ``get_reference``), in
      which case it is serialized via
      ``governance_service._serialize_guideline``; or
    - the dict produced by ``governance_service._serialize_guideline``
      directly (used by ``list_references``, which pages through
      ``governance_service.list_guidelines`` and gets back serialized dicts).

    Returns a dict containing every key listed in the design's
    "Unified Reference DTO" block. Template-only fields are set to ``None``.
    The ``program_name`` field is taken from
    ``governance_service._serialize_guideline`` (which already pulls it from
    ``guideline.program.name`` defensively); for the model form we re-check
    ``guideline.program`` as a belt-and-braces fallback for objects whose
    program relationship was loaded after serialization.
    """
    if isinstance(guideline, dict):
        base = guideline
    else:
        # Lazy import to avoid a circular import during app startup.
        from app.services import governance_service

        base = governance_service._serialize_guideline(guideline)
        program_name = base.get('program_name')
        if program_name is None:
            program = getattr(guideline, 'program', None)
            if program is not None:
                program_name = getattr(program, 'name', None)
                if program_name is not None:
                    # Don't mutate the dict returned by _serialize_guideline
                    # in place — other call sites rely on its identity.
                    base = dict(base, program_name=program_name)

    file_kind, has_downloadable_file = _classify_file(base.get('file_path'))

    reference_uri = encode_reference_uri('guideline', guideline_id=base['id'])

    return {
        # Unified identifiers
        'reference_uri': reference_uri,
        'reference_type': base.get('guideline_type'),
        'origin': 'guideline',
        # Common fields (view-only)
        'title': base.get('title'),
        'reference_number': base.get('reference_number'),
        'issuing_body': base.get('issuing_body'),
        'effective_date': base.get('effective_date'),
        'description': base.get('description'),
        'program_id': base.get('program_id'),
        'program_name': base.get('program_name'),
        'is_current': base.get('is_current'),
        'file_name': base.get('file_name'),
        'file_path': base.get('file_path'),
        'file_kind': file_kind,
        'has_downloadable_file': has_downloadable_file,
        'created_at': base.get('created_at'),
        'updated_at': base.get('updated_at'),
        # Template-only fields are not applicable to a view-only Reference.
        'template_subtype': None,
        'template_subtype_label': None,
        'template_label': None,
        'is_default': None,
        'placeholder_fields': None,
        'placeholder_definitions': None,
        'placeholder_defaults': None,
        'placeholder_default_suggestions': None,
        'available': None,
        'mime_type': None,
        'checker_profile': _checker_profile_summary(reference_uri),
    }


def _reference_from_template(template_subtype, entry, group):
    """Build a Reference DTO for a template catalog entry.

    Args:
        template_subtype: A key of ``settings_service.DOCUMENT_TEMPLATE_TYPES``
            (e.g. ``'project_revision_report'``).
        entry: A single serialized template entry dict, shaped like the output
            of ``settings_service._serialize_document_template_entry`` — i.e.
            one element of ``group['templates']`` from
            ``settings_service.list_document_templates()``.
        group: The per-subtype group dict from
            ``settings_service.list_document_templates()`` (contains
            ``template_type``, ``label``, ``templates``, etc.). May be ``None``;
            in that case the subtype label falls back to
            ``DOCUMENT_TEMPLATE_TYPES[template_subtype]['label']``.

    Returns a dict containing every key listed in the design's
    "Unified Reference DTO" block. View-only fields (``program_id``,
    ``program_name``, ``is_current``, ``reference_number``, ``issuing_body``,
    ``effective_date``, ``description``) are set to ``None``.

    Template files always live on local disk under ``REPORT_TEMPLATE_UPLOAD_DIR``
    (no external URLs, no object storage), so ``file_kind`` is either
    ``'upload'`` (when the underlying file is present on disk, i.e.
    ``entry['available']`` is true) or ``'none'`` (file missing).
    """
    if not isinstance(entry, dict):
        raise TypeError('entry must be a serialized template dict')

    # Lazy import to avoid a circular import during app startup.
    from app.services import settings_service

    # Prefer the label exposed on the group dict; fall back to the canonical
    # catalog entry if the caller did not pass one in.
    template_subtype_label = None
    if isinstance(group, dict):
        template_subtype_label = group.get('label')
    if not template_subtype_label:
        definition = settings_service.DOCUMENT_TEMPLATE_TYPES.get(template_subtype) or {}
        template_subtype_label = definition.get('label')

    available = bool(entry.get('available'))
    file_kind = 'upload' if available else 'none'
    has_downloadable_file = available

    template_label = entry.get('label')
    title = template_label or entry.get('file_name') or 'DOCX template'

    reference_uri = encode_reference_uri(
        'template',
        template_subtype=template_subtype,
        template_id=entry.get('id'),
    )

    return {
        # Unified identifiers
        'reference_uri': reference_uri,
        'reference_type': 'template',
        'origin': 'template',
        # Common fields
        'title': title,
        'reference_number': None,
        'issuing_body': None,
        'effective_date': None,
        'description': None,
        'program_id': None,
        'program_name': None,
        'is_current': None,
        'file_name': entry.get('file_name'),
        # The serialized template entry intentionally omits ``file_path`` to
        # keep the local disk path off the API surface; downloads are
        # resolved via ``settings_service.get_document_template`` instead.
        'file_path': None,
        'file_kind': file_kind,
        'has_downloadable_file': has_downloadable_file,
        # Templates only carry an ``uploaded_at`` timestamp; surface it as
        # both created_at and updated_at so the unified DTO has consistent
        # keys across origins.
        'created_at': entry.get('uploaded_at'),
        'updated_at': entry.get('uploaded_at'),
        # Template-specific fields
        'template_subtype': template_subtype,
        'template_subtype_label': template_subtype_label,
        'template_label': template_label,
        'is_default': bool(entry.get('is_default')),
        'placeholder_fields': entry.get('placeholder_fields') or [],
        'placeholder_definitions': entry.get('placeholder_definitions') or [],
        'placeholder_defaults': entry.get('placeholder_defaults') or {},
        'placeholder_default_suggestions': entry.get('placeholder_default_suggestions') or {},
        'available': available,
        'mime_type': entry.get('mime_type'),
        'checker_profile': _checker_profile_summary(reference_uri),
    }


# ---------------------------------------------------------------------------
# Public read API
# ---------------------------------------------------------------------------


def _normalize_search_value(value):
    """Strip and lowercase a search term; return None for empty input."""
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    return cleaned


def _template_matches_search(reference, search_lower):
    """Return True if a template Reference matches a case-insensitive search.

    Property 8 / Req 11.3: search is applied case-insensitively across
    ``title``, ``reference_number``, and ``issuing_body``. Templates only
    populate ``title`` (the template label or filename); the other two fields
    are always ``None`` for a template, which is treated as the empty string.
    """
    haystack = ' '.join(
        str(reference.get(field) or '')
        for field in ('title', 'reference_number', 'issuing_body')
    )
    return search_lower in haystack.lower()


def _sort_key(reference):
    """Composite sort key for the merged listing.

    Property 4 / Req 11.2: pagination over the merged result must never
    duplicate or drop a Reference, which means the order has to be a strict
    total order. The sort key is:

    1. ``updated_at`` (descending), falling back to ``created_at`` when
       ``updated_at`` is missing — both are ISO 8601 strings so lexicographic
       comparison matches chronological comparison.
    2. ``origin`` priority: ``guideline`` before ``template`` (Property 4
       requires a deterministic tie-breaker between origins).
    3. The native id of the underlying entity (integer for guidelines,
       hex string for templates) — guaranteed unique within an origin.
    """
    timestamp = reference.get('updated_at') or reference.get('created_at') or ''
    origin = reference.get('origin')
    origin_priority = 0 if origin == 'guideline' else 1
    if origin == 'guideline':
        # decode_reference_uri is overkill here; we control the URI shape.
        try:
            native_id = int(reference['reference_uri'].split(':', 1)[1])
        except (KeyError, ValueError, IndexError):
            native_id = 0
        native_key = (0, native_id, '')
    else:
        # template URIs are 'template:<subtype>:<id>'; sort by subtype then id
        # so the order is deterministic across runs even when timestamps tie.
        parts = (reference.get('reference_uri') or '').split(':', 2)
        subtype = parts[1] if len(parts) >= 2 else ''
        template_id = parts[2] if len(parts) >= 3 else ''
        native_key = (1, 0, f'{subtype}:{template_id}')
    # Negate the timestamp by sorting descending in the caller; here we just
    # return the raw key. The caller uses ``reverse=True`` for the timestamp
    # axis only via a wrapper.
    return (timestamp, origin_priority, native_key)


def _sort_references(references):
    """Sort references with timestamp descending, origin/id ascending.

    A simple ``sort(key=_sort_key, reverse=True)`` would reverse the
    origin/id tie-breaker too, which we don't want — guidelines must stay
    before templates and ids must stay ascending so concatenated pages remain
    a stable total order. Instead we sort twice: first by the deterministic
    ascending tail, then by timestamp descending. Python's sort is stable, so
    the ascending tail is preserved within each timestamp bucket.
    """
    references.sort(key=lambda ref: _sort_key(ref)[1:])
    references.sort(key=lambda ref: _sort_key(ref)[0], reverse=True)
    return references


def _filter_template_references(
    *,
    search,
    template_subtype,
):
    """Pull every template Reference from ``settings_service`` and apply
    the in-memory filters that templates support.

    Templates have no SQL backing for the listing; the ``settings_service``
    catalog is a JSON document fetched in one shot. Filtering is therefore
    cheap regardless of input size.

    Returns ``(references, total)`` where ``total`` is the count after
    filters but before pagination.
    """
    # Lazy import to avoid a circular import during app startup.
    from app.services import settings_service

    groups = settings_service.list_document_templates()
    references = []
    for group in groups:
        subtype = group.get('template_type')
        if template_subtype is not None and subtype != template_subtype:
            continue
        for entry in group.get('templates') or []:
            references.append(_reference_from_template(subtype, entry, group))

    if search:
        search_lower = search.lower()
        references = [
            ref for ref in references
            if _template_matches_search(ref, search_lower)
        ]

    return references, len(references)


def _filter_guideline_references(
    *,
    search,
    program_id,
    is_current,
    reference_type,
    page=1,
    per_page=None,
    limit=None,
):
    """Page through ``governance_service.list_guidelines`` and convert each
    serialized row into a Reference DTO.

    When ``per_page`` is ``None`` we fetch every matching row (used by the
    merged path so that pagination can be applied after merging). Otherwise
    the underlying SQL pagination is honored as-is and the returned ``total``
    is the full unpaginated count from ``governance_service``.

    The ``reference_type`` argument is passed through as ``guideline_type``
    so that the SQL filter is applied at the database level.
    """
    # Lazy import to avoid a circular import during app startup.
    from app.services import governance_service

    if per_page is None:
        # Merged Library pagination only needs the first N guideline rows
        # from the guideline branch, where N is the end offset of the merged
        # page. Fetching every matching guideline would violate the server-side
        # pagination contract as the library grows.
        query = _guideline_listing_query(
            search=search,
            program_id=program_id,
            is_current=is_current,
            reference_type=reference_type,
        )
        total = query.count()
        from app.models import ProgramGuideline

        rows = query.order_by(
            ProgramGuideline.updated_at.desc().nullslast(),
            ProgramGuideline.id.asc(),
        )
        if limit is not None:
            rows = rows.limit(limit)
        return [_reference_from_guideline(item) for item in rows.all()], total

    chunk = governance_service.list_guidelines(
        search=search,
        program_id=program_id,
        guideline_type=reference_type,
        is_current=is_current,
        page=page,
        per_page=per_page,
    )
    return (
        [_reference_from_guideline(item) for item in chunk['items']],
        chunk['total'],
    )


def _guideline_listing_query(*, search, program_id, is_current, reference_type):
    """Return the guideline query used by the unified Library listing."""
    from app.extensions import db
    from app.models import Program, ProgramGuideline

    query = ProgramGuideline.query.join(Program, ProgramGuideline.program_id == Program.id)

    if search:
        query = query.filter(
            db.or_(
                ProgramGuideline.title.ilike(f'%{search}%'),
                ProgramGuideline.reference_number.ilike(f'%{search}%'),
                ProgramGuideline.issuing_body.ilike(f'%{search}%'),
                Program.name.ilike(f'%{search}%'),
            )
        )
    if program_id is not None:
        query = query.filter(ProgramGuideline.program_id == program_id)
    if reference_type:
        query = query.filter(ProgramGuideline.guideline_type == reference_type)
    if is_current is not None:
        query = query.filter(ProgramGuideline.is_current == is_current)

    return query


def list_references(
    *,
    user_id,
    user_role,
    search=None,
    reference_type=None,
    program_id=None,
    is_current=None,
    template_subtype=None,
    origin=None,
    page=1,
    per_page=20,
):
    """List Library References across both backing stores.

    Returns a dict with the keys ``items``, ``page``, ``per_page``, ``total``,
    and ``pages`` — shaped identically to ``governance_service.list_guidelines``
    so the API layer can pass it straight through ``success_response``.

    Branching (see ``design.md``: "Read path"):

    - If ``reference_type == 'template'`` and the caller is *not* a field
      officer, only the templates branch runs.
    - Else if ``reference_type`` is one of ``VIEW_ONLY_REFERENCE_TYPES``, only
      the guidelines branch runs (a view-only ``reference_type`` is a hard
      signal that templates are excluded).
    - Else if ``user_role == 'field_officer'``, only the guidelines branch
      runs (field officers never see templates — Property 9 / Req 10.4).
    - Else if ``program_id`` or ``is_current`` is set (both apply only to
      guidelines), only the guidelines branch runs.
    - Else if ``template_subtype`` is set, only the templates branch runs.
    - Otherwise both branches run and the results are merged with stable
      composite ordering before pagination is applied.

    Filters:

    - ``reference_type``: applied to whichever branch runs. Validated only
      to the extent that it must be in ``VALID_REFERENCE_TYPES`` for the
      branching to make sense; values outside that set are still accepted
      here so the route layer can rely on field-level validation in
      ``schemas.validate_reference_payload`` to surface a 422 error.
    - ``program_id``: guidelines branch only. Templates have no program
      association, so when ``program_id`` is set the templates branch is
      skipped and the templates total is 0.
    - ``is_current``: guidelines branch only. Templates have no
      historical/current distinction.
    - ``template_subtype``: templates branch only. When set, the guidelines
      branch is skipped and the guidelines total is 0.
    - ``search``: applied case-insensitively to both branches over
      ``title``, ``reference_number``, and ``issuing_body``. The guidelines
      branch reuses ``governance_service.list_guidelines``'s built-in
      search (which is already case-insensitive ``ILIKE``); the templates
      branch filters in memory.

    Pagination is server-side. ``per_page`` defaults to 20 and is clamped to
    a sensible range. ``total`` is always
    ``guideline_total + template_total`` even when one branch is skipped
    (the skipped branch contributes 0).
    """
    # ``user_id`` is intentionally accepted but unused at this layer; the
    # underlying services do not currently scope reads by user.
    del user_id

    page = max(int(page or 1), 1)
    per_page = max(int(per_page or 20), 1)
    # Cap per_page defensively to avoid a runaway query if a caller passes a
    # huge value. 200 matches the guidelines fetch chunk size used internally.
    per_page = min(per_page, 200)
    search_term = _normalize_search_value(search)

    # Decide which branches to run.
    is_field_officer = (user_role == 'field_officer')
    skip_templates_for_role = is_field_officer
    skip_templates_for_filters = (
        program_id is not None
        or is_current is not None
        or reference_type in VIEW_ONLY_REFERENCE_TYPES
        or origin == 'guideline'
    )
    skip_guidelines_for_filters = (
        reference_type == 'template'
        or template_subtype is not None
        or origin == 'template'
    )

    run_templates = not (skip_templates_for_role or skip_templates_for_filters)
    run_guidelines = not skip_guidelines_for_filters

    # Single-branch fast paths: delegate pagination to the source where
    # possible. The guidelines fast path uses SQL pagination; the templates
    # fast path slices the in-memory list.
    if run_guidelines and not run_templates:
        # Pass ``reference_type`` to the SQL filter only when it is a
        # view-only type; ``None`` means "any view-only type".
        guideline_type_filter = (
            reference_type if reference_type in VIEW_ONLY_REFERENCE_TYPES else None
        )
        items, total = _filter_guideline_references(
            search=search_term,
            program_id=program_id,
            is_current=is_current,
            reference_type=guideline_type_filter,
            page=page,
            per_page=per_page,
        )
        pages = (total + per_page - 1) // per_page if total else 0
        return {
            'items': items,
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': pages,
        }

    if run_templates and not run_guidelines:
        all_templates, template_total = _filter_template_references(
            search=search_term,
            template_subtype=template_subtype,
        )
        _sort_references(all_templates)
        start = (page - 1) * per_page
        end = start + per_page
        items = all_templates[start:end]
        pages = (template_total + per_page - 1) // per_page if template_total else 0
        return {
            'items': items,
            'page': page,
            'per_page': per_page,
            'total': template_total,
            'pages': pages,
        }

    if not run_guidelines and not run_templates:
        # Defensive: all branches were skipped (e.g. caller passed a
        # nonsensical combination such as program_id + reference_type=template).
        # Return an empty page rather than raising — the route layer is
        # responsible for surfacing client-friendly validation errors before
        # we get here.
        return {
            'items': [],
            'page': page,
            'per_page': per_page,
            'total': 0,
            'pages': 0,
        }

    # Merged path: run both branches, fetch every matching row, merge under
    # the composite sort key, then slice. Property 4 demands a stable total
    # order so pagination over the merged result never duplicates or drops a
    # Reference.
    guideline_type_filter = (
        reference_type if reference_type in VIEW_ONLY_REFERENCE_TYPES else None
    )
    guideline_items, guideline_total = _filter_guideline_references(
        search=search_term,
        program_id=program_id,
        is_current=is_current,
        reference_type=guideline_type_filter,
        page=1,
        per_page=None,
        limit=page * per_page,
    )
    template_items, template_total = _filter_template_references(
        search=search_term,
        template_subtype=template_subtype,
    )

    merged = guideline_items + template_items
    _sort_references(merged)

    total = guideline_total + template_total
    start = (page - 1) * per_page
    end = start + per_page
    items = merged[start:end]
    pages = (total + per_page - 1) // per_page if total else 0
    return {
        'items': items,
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': pages,
    }


def get_reference(reference_uri: str, *, user_id: int, user_role: str) -> dict:
    """Resolve a Reference URI to its unified Reference DTO.

    The URI is decoded via :func:`decode_reference_uri` (which already raises
    ``LibraryError(422)`` for malformed input) and then dispatched to the
    matching backing store:

    - ``guideline:<id>`` -> :func:`governance_service.get_guideline`
    - ``template:<subtype>:<id>`` -> the
      :func:`settings_service.list_document_templates` catalog filtered by
      subtype and id.

    Any "not found" response from the underlying service is normalized into
    ``LibraryError('Reference not found.', status_code=404)`` so the API layer
    surfaces a single consistent shape regardless of origin.

    Field-officer callers cannot see Templates at all (Property 9 / Req 10.4):
    every template URI raises ``LibraryError(404)`` for that role, including
    URIs that would otherwise resolve to a real template entry. The 404 is
    deliberate — a 403 would leak the existence of templates to a role that
    is supposed to be unaware of them.

    Args:
        reference_uri: The public Reference URI.
        user_id: The acting user's id (currently unused; reserved for future
            row-level filtering parity with ``list_references``).
        user_role: The acting user's role. Only ``'field_officer'`` triggers
            origin-specific filtering at this layer; other roles defer to the
            underlying service for authorization.

    Returns:
        A unified Reference DTO (see ``design.md``: "Unified Reference DTO").

    Raises:
        LibraryError: 404 when the URI is well-formed but the underlying
            entity cannot be found (or, for ``field_officer``, when origin is
            ``template``). 422 propagated from
            :func:`decode_reference_uri` for malformed URIs.
    """
    # ``user_id`` is intentionally accepted but unused at this layer; the
    # underlying services do not currently scope reads by user.
    del user_id

    decoded = decode_reference_uri(reference_uri)

    if decoded['origin'] == 'guideline':
        # Lazy import to avoid a circular import during app startup.
        from app.services import governance_service

        try:
            guideline = governance_service.get_guideline(decoded['guideline_id'])
        except governance_service.GovernanceError as exc:
            if getattr(exc, 'status_code', None) == 404:
                raise LibraryError('Reference not found.', status_code=404) from exc
            raise
        return _reference_from_guideline(guideline)

    # origin == 'template' (decode_reference_uri only returns these two values)
    if user_role == 'field_officer':
        # Hide Templates from field officers entirely (Req 10.4 design flag).
        raise LibraryError('Reference not found.', status_code=404)

    from app.services import settings_service

    template_subtype = decoded['template_subtype']
    template_id = decoded['template_id']

    groups = settings_service.list_document_templates()
    group = next(
        (g for g in groups if g.get('template_type') == template_subtype),
        None,
    )
    if group is None:
        # Should not happen: decode_reference_uri already validated the
        # subtype is a key of DOCUMENT_TEMPLATE_TYPES, and
        # list_document_templates returns one group per registered subtype.
        # Treat as not-found defensively rather than letting an AttributeError
        # bubble up.
        raise LibraryError('Reference not found.', status_code=404)

    entry = next(
        (t for t in (group.get('templates') or []) if t.get('id') == template_id),
        None,
    )
    if entry is None:
        raise LibraryError('Reference not found.', status_code=404)

    return _reference_from_template(template_subtype, entry, group)


# ---------------------------------------------------------------------------
# Write API: create / update / delete / apply / download
# ---------------------------------------------------------------------------


def _governance_error_to_library_error(exc):
    """Wrap a ``governance_service.GovernanceError`` as a ``LibraryError``.

    Status code, message, and the ``errors`` field map (used by
    ``validation_error()`` to surface field-scoped errors per Req 12.1) are
    preserved verbatim so the API layer can return the same shape regardless
    of which underlying service raised.
    """
    return LibraryError(
        exc.message,
        status_code=getattr(exc, 'status_code', 400) or 400,
        errors=getattr(exc, 'errors', None) or {},
    )


def _settings_error_to_library_error(exc):
    """Wrap a ``settings_service.SettingsError`` as a ``LibraryError``.

    ``SettingsError`` does not carry an ``errors`` field map; status code and
    message are forwarded as-is. The route layer can still surface a generic
    422/404/409 response with the original message text.
    """
    return LibraryError(
        exc.message,
        status_code=getattr(exc, 'status_code', 400) or 400,
    )


def _admin_only(user_role, message):
    if user_role != 'admin':
        raise LibraryError(message, status_code=403)


def _reject_field_officer_write(user_role):
    if user_role == 'field_officer':
        raise LibraryError(
            'Field officers cannot create Library entries.',
            status_code=403,
        )


def _validate_reference_type(value):
    if value not in VALID_REFERENCE_TYPES:
        raise LibraryError(
            'Select a supported reference type.',
            status_code=422,
            errors={'reference_type': 'Select a supported reference type.'},
        )


def _split_template_payload(data):
    """Pull the four template-specific fields out of a Library payload.

    Returns a tuple ``(template_subtype, label, is_default, placeholder_defaults)``.
    Each value is either the supplied value or ``None`` / sentinel if absent.
    The ``is_default`` slot is a tri-state: ``True``, ``False``, or ``None``
    (meaning "the caller did not specify; defer to ``settings_service``").
    """
    template_subtype = data.get('template_subtype')
    label = data.get('label')
    placeholder_defaults = data.get('placeholder_defaults')
    if 'is_default' in data:
        is_default = _coerce_template_default_flag(data.get('is_default'))
    else:
        is_default = None
    return template_subtype, label, is_default, placeholder_defaults


def _coerce_template_default_flag(value):
    """Parse form/JSON truthy-falsy values before calling settings_service.

    ``settings_service.update_document_template`` expects a native bool.
    Passing raw multipart strings such as ``"false"`` would evaluate truthy
    under ``bool("false")`` and accidentally mark a template default.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if value in (0, 1):
            return value != 0
        raise LibraryError(
            'Default flag must be true or false.',
            status_code=422,
            errors={'is_default': 'Default flag must be true or false.'},
        )
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes', 'on'}:
            return True
        if normalized in {'false', '0', 'no', 'off', ''}:
            return False
    raise LibraryError(
        'Default flag must be true or false.',
        status_code=422,
        errors={'is_default': 'Default flag must be true or false.'},
    )


def _find_template_reference(template_subtype, template_id):
    """Look up a freshly stored or updated template entry and build its DTO.

    Re-reads the catalog via ``list_document_templates`` so the returned
    Reference reflects every post-write transformation
    ``settings_service`` performs (default-flag normalization, placeholder
    suggestion merging, ``available`` flag based on disk state).

    Raises ``LibraryError(404)`` if the entry has disappeared between the
    write and this lookup (should not happen in normal flows).
    """
    from app.services import settings_service

    groups = settings_service.list_document_templates()
    group = next(
        (g for g in groups if g.get('template_type') == template_subtype),
        None,
    )
    if group is None:
        raise LibraryError('Reference not found.', status_code=404)
    entry = next(
        (t for t in (group.get('templates') or []) if t.get('id') == template_id),
        None,
    )
    if entry is None:
        raise LibraryError('Reference not found.', status_code=404)
    return _reference_from_template(template_subtype, entry, group)


def _existing_template_ids(template_subtype):
    """Return the set of template ``id`` values currently registered for a subtype.

    Used to pinpoint the newly stored entry after a successful
    ``store_document_template`` call (the underlying service does not return
    the new id directly).
    """
    from app.services import settings_service

    groups = settings_service.list_document_templates()
    group = next(
        (g for g in groups if g.get('template_type') == template_subtype),
        None,
    )
    if group is None:
        return set()
    return {t.get('id') for t in (group.get('templates') or []) if t.get('id')}


def create_reference(data, *, user_id, user_role, upload=None):
    """Create a new Library Reference and return its unified DTO.

    Routes the request to the correct underlying service based on
    ``data['reference_type']``:

    - View-only types (``VIEW_ONLY_REFERENCE_TYPES``) -> ``governance_service.create_guideline``
    - ``template`` -> ``settings_service.store_document_template``

    Validates ``reference_type`` first (422 on bad value), then enforces
    role gates defensively (the route layer already gates these). Errors
    raised by the underlying services are wrapped as ``LibraryError`` with
    their original status code and field map preserved (Req 12.1, 12.2).

    Args:
        data: The request payload. Must include ``reference_type``. For
            view-only types, the remaining keys mirror the legacy
            ``/api/governance/guidelines`` POST body. For ``template``,
            recognized keys are ``template_subtype``, ``label``,
            ``is_default``, and ``placeholder_defaults``.
        user_id: The acting user's id.
        user_role: The acting user's role.
        upload: Optional ``werkzeug.FileStorage`` for file uploads.

    Returns:
        The unified Reference DTO for the newly created entity.

    Raises:
        LibraryError: 403 for unauthorized roles, 422 for validation
            failures (including unknown ``reference_type`` and unsupported
            ``template_subtype``), 404 / 409 / etc. propagated from the
            underlying service.
    """
    if not isinstance(data, dict):
        data = dict(data or {})

    _reject_field_officer_write(user_role)

    reference_type = data.get('reference_type')
    _validate_reference_type(reference_type)

    if reference_type in VIEW_ONLY_REFERENCE_TYPES:
        # Lazy import to avoid a circular import during app startup.
        from app.services import governance_service

        # Translate reference_type -> guideline_type for the legacy service,
        # while preserving any caller-supplied guideline_type (callers should
        # supply only one of the two).
        forwarded = dict(data)
        forwarded.pop('reference_type', None)
        forwarded.setdefault('guideline_type', reference_type)

        try:
            guideline = governance_service.create_guideline(
                forwarded,
                user_id=user_id,
                upload=upload,
            )
        except governance_service.GovernanceError as exc:
            raise _governance_error_to_library_error(exc) from exc
        return _reference_from_guideline(guideline)

    # reference_type == 'template' (validated above to be in VALID_REFERENCE_TYPES)
    _admin_only(user_role, 'Staff cannot create Templates.')

    from app.services import settings_service

    template_subtype, label, is_default, placeholder_defaults = _split_template_payload(data)
    if template_subtype not in settings_service.DOCUMENT_TEMPLATE_TYPES:
        message = 'Select a supported template subtype.'
        raise LibraryError(
            message,
            status_code=422,
            errors={'template_subtype': message},
        )

    before_ids = _existing_template_ids(template_subtype)

    store_kwargs = {'label': label, 'placeholder_defaults': placeholder_defaults}
    if is_default is not None:
        store_kwargs['is_default'] = is_default

    try:
        settings_service.store_document_template(
            template_subtype,
            upload,
            user_id,
            **store_kwargs,
        )
    except settings_service.SettingsError as exc:
        raise _settings_error_to_library_error(exc) from exc

    after_ids = _existing_template_ids(template_subtype)
    new_ids = after_ids - before_ids
    if not new_ids:
        # The store call succeeded but no new id appeared. Should not happen
        # in normal flows; treat as a 500-equivalent so the API surface is
        # honest about the unexpected state.
        raise LibraryError(
            'Template was stored but could not be located in the catalog.',
            status_code=500,
        )
    # If multiple ids appeared simultaneously (e.g. concurrent uploads) we
    # fall back to whichever the catalog reports last, mirroring the
    # append order used by ``store_document_template``.
    new_id = next(iter(new_ids)) if len(new_ids) == 1 else _last_template_id_in_set(template_subtype, new_ids)
    return _find_template_reference(template_subtype, new_id)


def _last_template_id_in_set(template_subtype, candidate_ids):
    """Return the id from ``candidate_ids`` that appears last in the catalog.

    ``settings_service.store_document_template`` appends new entries to the
    catalog list, so when multiple ids are unaccounted for the most recent
    one is the last entry whose id is in the candidate set.
    """
    from app.services import settings_service

    groups = settings_service.list_document_templates()
    group = next(
        (g for g in groups if g.get('template_type') == template_subtype),
        None,
    )
    if group is None:
        return next(iter(candidate_ids))
    for entry in reversed(group.get('templates') or []):
        if entry.get('id') in candidate_ids:
            return entry.get('id')
    return next(iter(candidate_ids))


def update_reference(reference_uri, data, *, user_id, user_role, upload=None):
    """Update an existing Library Reference and return its updated DTO.

    Decodes the URI, applies defensive role gates, then dispatches to the
    correct underlying service:

    - guideline origin -> ``governance_service.update_guideline`` (with
      ``reference_type`` translated to ``guideline_type``).
    - template origin  -> ``settings_service.update_document_template``
      forwarding only the fields the legacy service understands
      (``label``, ``is_default``, ``placeholder_defaults``) — Req 4.12
      explicitly allows these edits without re-uploading the file.

    Underlying errors are wrapped as ``LibraryError`` with the same
    status_code and field map.
    """
    if not isinstance(data, dict):
        data = dict(data or {})

    _reject_field_officer_write(user_role)

    decoded = decode_reference_uri(reference_uri)
    origin = decoded['origin']

    if origin == 'guideline':
        from app.services import governance_service

        forwarded = dict(data)
        if 'reference_type' in forwarded:
            forwarded['guideline_type'] = forwarded.pop('reference_type')

        try:
            guideline = governance_service.update_guideline(
                decoded['guideline_id'],
                forwarded,
                user_id=user_id,
                upload=upload,
            )
        except governance_service.GovernanceError as exc:
            raise _governance_error_to_library_error(exc) from exc
        return _reference_from_guideline(guideline)

    # origin == 'template'
    _admin_only(user_role, 'Staff cannot update Templates.')

    from app.services import settings_service

    template_subtype = decoded['template_subtype']
    template_id = decoded['template_id']

    # Forward only the keys ``settings_service.update_document_template``
    # recognizes (Req 4.12: label, is_default, placeholder_defaults). Any
    # other key the caller supplies is silently ignored at this layer; the
    # schema validator (task 6.1) is responsible for surfacing unsupported
    # fields as a 422.
    template_data = {}
    if 'label' in data:
        template_data['label'] = data.get('label')
    if 'is_default' in data:
        template_data['is_default'] = _coerce_template_default_flag(data.get('is_default'))
    if 'placeholder_defaults' in data:
        template_data['placeholder_defaults'] = data.get('placeholder_defaults')

    try:
        settings_service.update_document_template(
            template_subtype,
            template_id,
            data=template_data,
            user_id=user_id,
        )
    except settings_service.SettingsError as exc:
        raise _settings_error_to_library_error(exc) from exc

    return _find_template_reference(template_subtype, template_id)


def delete_reference(reference_uri, *, user_id, user_role):
    """Delete an existing Library Reference.

    Admin-only at this layer (the route layer already enforces this; the
    in-service check is defensive — Req 5.11). For guideline origin the
    ``ProgramGuideline`` row is removed and a ``delete`` audit entry is
    written through ``audit_service.log_action`` (Req 9.3); the underlying
    ``stored_objects`` row, if any, is left in place so existing object
    storage references remain intact (matching the behavior of every other
    deletion path in this codebase).

    For template origin, delegates to
    ``settings_service.delete_document_template`` which removes orphan files
    from disk, promotes a remaining template to default if the deleted
    entry was the default, and writes its own audit entry (Req 4.13, 9.4).

    Returns ``None`` on success.
    """
    _admin_only(user_role, 'Only administrators can delete Library entries.')

    decoded = decode_reference_uri(reference_uri)
    origin = decoded['origin']

    if origin == 'guideline':
        # No ``governance_service.delete_guideline`` exists today, so the
        # delete is implemented inline using the same audit pattern the
        # other governance writes use (see ``governance_service.create_guideline``).
        # This is a deliberate exception to the "delegate to governance_service"
        # guidance in the spec; introducing the function in
        # ``governance_service`` would violate the "do not touch
        # governance_service.py" constraint for this task.
        from app.extensions import db
        from app.services import audit_service, governance_service

        try:
            guideline = governance_service.get_guideline(decoded['guideline_id'])
        except governance_service.GovernanceError as exc:
            if getattr(exc, 'status_code', None) == 404:
                raise LibraryError('Reference not found.', status_code=404) from exc
            raise _governance_error_to_library_error(exc) from exc

        before = governance_service._serialize_guideline(guideline)
        guideline_id = guideline.id
        from app.services import document_compliance_service

        document_compliance_service.delete_reference_profile(reference_uri, commit=False)
        db.session.delete(guideline)

        audit_service.log_action(
            user_id=int(user_id),
            action='delete',
            entity_type='program_guideline',
            entity_id=guideline_id,
            old_value=before,
            new_value=None,
            commit=False,
        )
        db.session.commit()
        return None

    # origin == 'template'
    from app.services import settings_service

    from app.services import document_compliance_service

    try:
        settings_service.delete_document_template(
            decoded['template_subtype'],
            decoded['template_id'],
            user_id=user_id,
        )
    except settings_service.SettingsError as exc:
        raise _settings_error_to_library_error(exc) from exc
    document_compliance_service.delete_reference_profile(reference_uri, commit=True)
    return None


def apply_template(reference_uri, *, user_id, user_role):
    """Resolve a Reference URI to the dict ``notice_service`` and
    ``project_service`` expect when applying a template to a generation flow.

    Property 6 / Req 3.4 - 3.6: only template References can be applied. For
    a guideline URI this function raises ``LibraryError(422)`` and **does
    not** call ``settings_service.get_document_template``,
    ``settings_service.get_report_template``, ``notice_service``, or
    ``project_service`` — guarded by an early return that bypasses every
    downstream lookup.

    Field-officer callers cannot see Templates at all (Req 10.4), so a
    template URI raises ``LibraryError(404)`` for that role — the same
    behavior as ``get_reference``.

    Args:
        reference_uri: A Library Reference URI.
        user_id: The acting user's id (currently unused; reserved).
        user_role: The acting user's role.

    Returns:
        The dict produced by ``settings_service.get_document_template``
        (keys: ``id``, ``label``, ``file_name``, ``path``, ``mime_type``,
        ``placeholder_defaults``, ``placeholder_definitions``,
        ``placeholder_fields``).
    """
    del user_id

    decoded = decode_reference_uri(reference_uri)

    if decoded['origin'] == 'guideline':
        # Property 6: return WITHOUT touching any consumer service.
        message = 'Only templates can be applied to generation flows.'
        raise LibraryError(
            message,
            status_code=422,
            errors={'reference_type': message},
        )

    # origin == 'template'
    if user_role == 'field_officer':
        raise LibraryError('Reference not found.', status_code=404)

    from app.services import settings_service

    try:
        result = settings_service.get_document_template(
            decoded['template_subtype'],
            template_id=decoded['template_id'],
        )
    except settings_service.SettingsError as exc:
        if getattr(exc, 'status_code', None) == 404:
            raise LibraryError('Template not found.', status_code=404) from exc
        raise _settings_error_to_library_error(exc) from exc

    if result is None:
        # ``get_document_template`` returns None when no template is configured
        # for the subtype and no specific template_id was supplied. Since we
        # always pass a template_id here, this branch is defensive.
        raise LibraryError('Template not found.', status_code=404)
    return result


def get_reference_download(reference_uri, *, user_id, user_role):
    """Resolve a Reference URI to the metadata required to stream a file.

    Returns a dict with the keys ``reference``, ``stored_object``, ``path``,
    ``download_name``, and ``mime_type``. The shape is identical for both
    origins so the route layer can stream the file without origin-specific
    branches:

    - ``reference``: the unified Reference DTO.
    - ``stored_object``: a ``StoredObject`` row when the file lives in
      object storage (guideline origin only); ``None`` otherwise.
    - ``path``: a ``pathlib.Path`` to the on-disk file when streaming from
      disk; ``None`` when streaming from object storage.
    - ``download_name``: the suggested filename for the
      ``Content-Disposition`` header.
    - ``mime_type``: the content type the route should use.

    Authorization rules (Req 6, 10.2):
    - Field officers can download any view-only Reference.
    - Field officers cannot see Templates at all; a template URI raises
      ``LibraryError(404)`` for that role (templates hidden — Req 10.4).
    - 404 propagates from the underlying service when the file is missing
      on disk; 409 propagates when the guideline points to an external URL.
    """
    del user_id

    decoded = decode_reference_uri(reference_uri)
    origin = decoded['origin']

    if origin == 'guideline':
        from app.services import governance_service

        try:
            download = governance_service.get_guideline_download(
                decoded['guideline_id'],
            )
        except governance_service.GovernanceError as exc:
            raise _governance_error_to_library_error(exc) from exc

        guideline = download['guideline']
        stored_object = download.get('stored_object')
        path = download.get('path')
        reference = _reference_from_guideline(guideline)
        download_name = guideline.file_name or (path.name if path else None) or 'reference'
        if stored_object is not None:
            mime_type = stored_object.content_type or 'application/octet-stream'
        else:
            mime_type = 'application/octet-stream'
        return {
            'reference': reference,
            'stored_object': stored_object,
            'path': path,
            'download_name': download_name,
            'mime_type': mime_type,
        }

    # origin == 'template'
    if user_role == 'field_officer':
        raise LibraryError('Reference not found.', status_code=404)

    from app.services import settings_service

    template_subtype = decoded['template_subtype']
    template_id = decoded['template_id']

    try:
        result = settings_service.get_document_template(
            template_subtype,
            template_id=template_id,
        )
    except settings_service.SettingsError as exc:
        if getattr(exc, 'status_code', None) == 404:
            raise LibraryError('Reference not found.', status_code=404) from exc
        raise _settings_error_to_library_error(exc) from exc

    if result is None:
        raise LibraryError('Reference not found.', status_code=404)

    path = result.get('path')
    if path is None:
        # ``get_document_template`` validates the file exists before
        # returning, so this is a defensive branch.
        raise LibraryError(
            'Stored template file is not available on disk.',
            status_code=404,
        )

    reference = _find_template_reference(template_subtype, template_id)
    return {
        'reference': reference,
        'stored_object': None,
        'path': path,
        'download_name': result.get('file_name') or path.name,
        'mime_type': result.get('mime_type') or 'application/octet-stream',
    }


__all__ = [
    'LibraryError',
    'VALID_REFERENCE_TYPES',
    'VIEW_ONLY_REFERENCE_TYPES',
    'encode_reference_uri',
    'decode_reference_uri',
    'list_references',
    'get_reference',
    'create_reference',
    'update_reference',
    'delete_reference',
    'apply_template',
    'get_reference_download',
]
