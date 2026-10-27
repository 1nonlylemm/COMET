"""HTTP routes for the unified Reference Library API.

The handlers in this module wire the public ``/api/library/*`` surface to
``library_service``. They mirror the existing governance routes
(``/api/governance/guidelines*``) for shape, decorator usage, payload
parsing, and error envelope, so that legacy frontend conventions continue to
work uniformly across the unified Library and the legacy endpoints.

Authorization is enforced at two layers:

- Route decorator: ``@admin_or_staff_or_field_required`` for read paths,
  ``@admin_or_staff_required`` for write paths and the template subtypes
  catalog, ``@admin_required`` for delete.
- ``library_service``: defensive role gates that reject ``field_officer``
  writes and ``staff`` template writes regardless of the route decorator.

Reference URIs are URL-decoded (``urllib.parse.unquote``) before being
passed to the service so callers can encode the ``:`` separator if they
prefer; the service's :func:`library_service.decode_reference_uri` raises
``LibraryError(422, errors={'reference_uri': ...})`` for any input that
does not match the documented grammar, which this module forwards as a
422 ``validation_error`` envelope.
"""

from urllib.parse import unquote

from flask import request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from app.api.library.schemas import validate_reference_payload
from app.services import document_compliance_service, library_service, object_storage_service, settings_service
from app.utils.auth import (
    admin_or_staff_or_field_required,
    admin_or_staff_required,
    admin_required,
)
from app.utils.response import error_response, success_response, validation_error

from . import library_bp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_user_role():
    """Return the role claim from the current JWT.

    The login flow embeds the role under the ``role`` additional claim
    (see ``auth_service.login_user``). Reading it from the token avoids
    a database round-trip on every Library request; the
    ``role_required`` decorator already verified the user is live and
    has an authorized role before we get here.
    """
    claims = get_jwt() or {}
    return claims.get('role')


def _decode_reference_uri_arg(reference_uri):
    """URL-decode the path segment carrying a Reference URI.

    Clients are free to encode the colon separator (``%3A``) or send the
    raw form (``guideline:42``); both must reach the service as
    ``guideline:42``. Empty input is normalized to an empty string so
    ``library_service.decode_reference_uri`` raises a uniform 422.
    """
    if reference_uri is None:
        return ''
    return unquote(reference_uri)


def _request_payload():
    """Read a create/update payload from JSON or form data.

    Mirrors the governance routes' pattern so multipart uploads (which
    cannot use JSON bodies) keep working. Returns an empty dict when the
    request body is missing.
    """
    if request.is_json:
        data = request.get_json(silent=True)
    else:
        data = request.form.to_dict()
    return data or {}


def _library_error_response(exc):
    """Convert a ``LibraryError`` into the right HTTP response envelope.

    422 errors with a non-empty ``errors`` map are surfaced through
    :func:`validation_error` so the response matches the field-scoped
    shape used by the legacy ``/api/governance/guidelines`` endpoint
    (Req 12.1). Every other status code falls through to
    :func:`error_response` with the original message, status code, and
    any ancillary error map preserved.
    """
    errors = exc.errors or None
    if exc.status_code == 422 and errors:
        return validation_error(errors)
    return error_response(exc.message, errors=errors, status_code=exc.status_code)


def _checker_error_response(exc):
    errors = exc.errors or None
    if exc.status_code == 422 and errors:
        return validation_error(errors)
    return error_response(exc.message, errors=errors, status_code=exc.status_code)


def _parse_optional_bool(value):
    """Parse a query-string boolean ('true'/'false') to bool|None.

    Returns ``None`` when the value is missing so the underlying service
    can distinguish "no filter" from "filter to False".
    """
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized == '':
        return None
    if normalized in {'true', '1', 'yes', 'on'}:
        return True
    if normalized in {'false', '0', 'no', 'off'}:
        return False
    raise ValueError('Current status filter must be true or false.')


# ---------------------------------------------------------------------------
# Reference listing and detail
# ---------------------------------------------------------------------------


@library_bp.route('/references', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_references():
    reference_type = request.args.get('reference_type')
    if reference_type and reference_type not in library_service.VALID_REFERENCE_TYPES:
        return validation_error({'reference_type': 'Select a supported reference type.'})

    origin = request.args.get('origin')
    if origin and origin not in ('guideline', 'template'):
        return validation_error({'origin': 'Select a supported origin (guideline or template).'})

    try:
        is_current = _parse_optional_bool(request.args.get('is_current'))
        result = library_service.list_references(
            user_id=get_jwt_identity(),
            user_role=_current_user_role(),
            search=request.args.get('search'),
            reference_type=reference_type,
            program_id=request.args.get('program_id', type=int),
            is_current=is_current,
            template_subtype=request.args.get('template_subtype'),
            origin=origin,
            page=request.args.get('page', 1, type=int),
            per_page=request.args.get('per_page', 20, type=int),
        )
        return success_response(data=result['items'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except ValueError as exc:
        return validation_error({'is_current': str(exc)})
    except library_service.LibraryError as exc:
        return _library_error_response(exc)


@library_bp.route('/references/<string:reference_uri>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_reference(reference_uri):
    try:
        reference = library_service.get_reference(
            _decode_reference_uri_arg(reference_uri),
            user_id=get_jwt_identity(),
            user_role=_current_user_role(),
        )
        return success_response(data=reference)
    except library_service.LibraryError as exc:
        return _library_error_response(exc)


# ---------------------------------------------------------------------------
# Reference create / update / delete
# ---------------------------------------------------------------------------


@library_bp.route('/references', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def create_reference():
    data = _request_payload()
    role = _current_user_role()
    errors = validate_reference_payload(data, partial=False, role=role)
    if errors:
        return validation_error(errors)

    try:
        reference = library_service.create_reference(
            data,
            user_id=get_jwt_identity(),
            user_role=role,
            upload=request.files.get('file'),
        )
        return success_response(
            data=reference,
            message='Reference saved successfully',
            status_code=201,
        )
    except library_service.LibraryError as exc:
        return _library_error_response(exc)


@library_bp.route('/references/<string:reference_uri>', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_reference(reference_uri):
    data = _request_payload()
    role = _current_user_role()
    errors = validate_reference_payload(data, partial=True, role=role)
    if errors:
        return validation_error(errors)

    try:
        reference = library_service.update_reference(
            _decode_reference_uri_arg(reference_uri),
            data,
            user_id=get_jwt_identity(),
            user_role=role,
            upload=request.files.get('file'),
        )
        return success_response(
            data=reference,
            message='Reference updated successfully',
        )
    except library_service.LibraryError as exc:
        return _library_error_response(exc)


@library_bp.route('/references/<string:reference_uri>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_reference(reference_uri):
    try:
        library_service.delete_reference(
            _decode_reference_uri_arg(reference_uri),
            user_id=get_jwt_identity(),
            user_role=_current_user_role(),
        )
        return success_response(message='Reference deleted successfully')
    except library_service.LibraryError as exc:
        return _library_error_response(exc)


# ---------------------------------------------------------------------------
# Reference download
# ---------------------------------------------------------------------------


@library_bp.route('/references/<string:reference_uri>/download', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def download_reference(reference_uri):
    try:
        download = library_service.get_reference_download(
            _decode_reference_uri_arg(reference_uri),
            user_id=get_jwt_identity(),
            user_role=_current_user_role(),
        )
    except library_service.LibraryError as exc:
        return _library_error_response(exc)

    stored_object = download.get('stored_object')
    download_name = download.get('download_name') or 'reference'
    mime_type = download.get('mime_type') or 'application/octet-stream'

    if stored_object is not None:
        try:
            return object_storage_service.download_response(
                stored_object,
                download_name=download_name,
                content_type=mime_type,
            )
        except object_storage_service.ObjectStorageError as exc:
            return error_response(exc.message, status_code=exc.status_code)

    path = download.get('path')
    if path is None:
        # Defensive: ``library_service`` raises before reaching this branch
        # for every well-defined missing-file scenario, but handle the
        # edge anyway so the route never returns an empty 200.
        return error_response('Stored reference file is not available.', status_code=404)

    return send_file(
        path,
        as_attachment=True,
        download_name=download_name,
        mimetype=mime_type,
    )


# ---------------------------------------------------------------------------
# Checker reference applicability
# ---------------------------------------------------------------------------


@library_bp.route('/references/<string:reference_uri>/checker-profile', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_checker_profile(reference_uri):
    try:
        profile = document_compliance_service.get_reference_profile(
            _decode_reference_uri_arg(reference_uri),
            user_id=get_jwt_identity(),
            user_role=_current_user_role(),
        )
        return success_response(data=profile)
    except document_compliance_service.DocumentComplianceError as exc:
        return _checker_error_response(exc)


@library_bp.route('/references/<string:reference_uri>/checker-profile', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_checker_profile(reference_uri):
    try:
        profile = document_compliance_service.upsert_reference_profile(
            _decode_reference_uri_arg(reference_uri),
            _request_payload(),
            user_id=get_jwt_identity(),
            user_role=_current_user_role(),
        )
        return success_response(data=profile, message='Checker reference profile saved.')
    except document_compliance_service.DocumentComplianceError as exc:
        return _checker_error_response(exc)


# ---------------------------------------------------------------------------
# Template subtype catalog
# ---------------------------------------------------------------------------


@library_bp.route('/template-subtypes', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def list_template_subtypes():
    """Return the registered template subtype catalog with default ids.

    The catalog is sourced from
    ``settings_service.DOCUMENT_TEMPLATE_TYPES`` (the registered subtypes
    and their human-readable metadata) and merged with the per-subtype
    default template id from ``settings_service.list_document_templates``
    so a UI can drive a "select template" dropdown without two round
    trips.
    """
    try:
        groups = settings_service.list_document_templates()
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)

    defaults_by_subtype = {
        group.get('template_type'): group.get('default_template_id')
        for group in groups
    }

    catalog = []
    for subtype, definition in settings_service.DOCUMENT_TEMPLATE_TYPES.items():
        catalog.append({
            'template_subtype': subtype,
            'label': definition.get('label'),
            'description': definition.get('description'),
            'category': definition.get('category'),
            'allowed_extension': definition.get('allowed_extension'),
            'mime_type': definition.get('mime_type'),
            'default_template_id': defaults_by_subtype.get(subtype),
        })
    return success_response(data=catalog)


@library_bp.route('/template-placeholders/preview', methods=['POST'])
@jwt_required()
@admin_required
def preview_template_placeholders():
    """Scan a DOCX template upload for placeholders before persistence."""
    data = _request_payload()
    template_subtype = data.get('template_subtype')
    errors = {}
    if not template_subtype:
        errors['template_subtype'] = 'Template subtype is required.'
    elif template_subtype not in settings_service.DOCUMENT_TEMPLATE_TYPES:
        errors['template_subtype'] = 'Select a supported template subtype.'
    if not request.files.get('file'):
        errors['file'] = 'Choose a DOCX template file before scanning.'
    if errors:
        return validation_error(errors)

    try:
        result = settings_service.preview_document_template_placeholders(
            template_subtype,
            request.files.get('file'),
        )
        return success_response(data=result)
    except settings_service.SettingsError as exc:
        if exc.status_code == 422:
            return validation_error({'file': exc.message})
        return error_response(exc.message, status_code=exc.status_code)
