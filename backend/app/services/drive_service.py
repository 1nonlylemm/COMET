import json
import secrets
import base64
import contextlib
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
import requests

from app.extensions import db
from app.models import DocumentFile, Project, SystemConfig
from app.services import access_service, object_storage_service, settings_service


DRIVE_FOLDER_MIMETYPE = 'application/vnd.google-apps.folder'
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']
OAUTH_SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]
DRIVE_ITEM_FIELDS = (
    'id,name,mimeType,parents,webViewLink,webContentLink,size,modifiedTime,createdTime,iconLink,thumbnailLink'
)
OAUTH_TOKEN_CONFIG_KEY = 'google_drive_oauth_token'
OAUTH_STATE_CONFIG_KEY = 'google_drive_oauth_state'
DRIVE_ROOT_CONFIG_KEY = 'google_drive_root_folder_id'
ENCRYPTED_VALUE_PREFIX = 'fernet:v1:'
UNREADABLE_OAUTH_TOKEN_MESSAGE = (
    'Stored Google Drive account credentials cannot be decrypted; reconnect Google Drive from Settings.'
)


class DriveServiceError(Exception):
    def __init__(self, message, status_code=503):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def is_configured():
    return bool(current_app.config.get('GOOGLE_DRIVE_ENABLED'))


def get_connection_status():
    credential_error = None
    has_oauth_token = _has_config_value(OAUTH_TOKEN_CONFIG_KEY)
    try:
        token = _get_oauth_token()
    except DriveServiceError as exc:
        if not _is_decryption_error(exc):
            raise
        token = None
        credential_error = UNREADABLE_OAUTH_TOKEN_MESSAGE
    root_folder_id = _get_root_folder_id()
    service_account_configured = bool(
        current_app.config.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE')
        or current_app.config.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON')
    )
    oauth_configured = _oauth_client_configured()

    if token:
        auth_mode = 'oauth'
    elif credential_error:
        auth_mode = 'oauth_error'
    elif service_account_configured:
        auth_mode = 'service_account'
    else:
        auth_mode = 'unconfigured'

    return {
        'enabled': is_configured(),
        'auth_mode': auth_mode,
        'oauth_configured': oauth_configured,
        'oauth_connected': bool(token),
        'has_oauth_token': bool(token) or has_oauth_token,
        'credential_error': credential_error,
        'connected_email': token.get('account_email') if token else None,
        'root_folder_id': root_folder_id,
        'has_root_folder': bool(root_folder_id),
        'service_account_configured': service_account_configured,
        'shared_drive_id': _shared_drive_id(),
    }


def start_oauth_connection(user_id):
    client_id, client_secret = _require_oauth_client()
    state = secrets.token_urlsafe(32)
    _set_config(
        OAUTH_STATE_CONFIG_KEY,
        {
            'state': state,
            'user_id': int(user_id),
            'created_at': datetime.now(timezone.utc).isoformat(),
        },
        user_id=user_id,
        secret=True,
    )
    params = {
        'client_id': client_id,
        'redirect_uri': _oauth_redirect_uri(),
        'response_type': 'code',
        'scope': ' '.join(OAUTH_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': state,
    }
    return {
        'authorization_url': 'https://accounts.google.com/o/oauth2/v2/auth?' + requests.compat.urlencode(params),
        'redirect_uri': _oauth_redirect_uri(),
    }


def complete_oauth_connection(code, state):
    if not code or not state:
        raise DriveServiceError('Google Drive OAuth callback is missing code or state.', 400)
    state_payload = _get_config_json(OAUTH_STATE_CONFIG_KEY)
    if not state_payload or state_payload.get('state') != state:
        raise DriveServiceError('Google Drive connection state is invalid or expired.', 400)

    created_at = _parse_iso_datetime(state_payload.get('created_at'))
    if not created_at or datetime.now(timezone.utc) - created_at > timedelta(minutes=15):
        _delete_config(OAUTH_STATE_CONFIG_KEY)
        raise DriveServiceError('Google Drive connection state is expired. Start the connection again.', 400)

    client_id, client_secret = _require_oauth_client()
    try:
        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': _oauth_redirect_uri(),
                'grant_type': 'authorization_code',
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        raise DriveServiceError('Unable to connect to Google OAuth token endpoint.', 503) from exc
    if response.status_code >= 400:
        raise DriveServiceError(_google_oauth_error(response, 'Google rejected the Drive authorization code.'), 400)

    token_payload = response.json()
    try:
        existing_token = _get_oauth_token() or {}
    except DriveServiceError as exc:
        if not _is_decryption_error(exc):
            raise
        existing_token = {}
    if not token_payload.get('refresh_token') and existing_token.get('refresh_token'):
        token_payload['refresh_token'] = existing_token['refresh_token']
    if not token_payload.get('refresh_token'):
        raise DriveServiceError(
            f'Google did not return a refresh token. Revoke the {settings_service.get_app_name()} app from your Google account, then connect again.',
            400,
        )

    account_email = _fetch_google_account_email(token_payload.get('access_token'))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_payload.get('expires_in') or 3600))
    token_record = {
        'refresh_token': token_payload.get('refresh_token'),
        'token_uri': 'https://oauth2.googleapis.com/token',
        'scopes': OAUTH_SCOPES,
        'expiry': expires_at.isoformat(),
        'account_email': account_email,
    }
    user_id = state_payload.get('user_id')
    _set_config(OAUTH_TOKEN_CONFIG_KEY, token_record, user_id=user_id, secret=True)
    _delete_config(OAUTH_STATE_CONFIG_KEY)
    return get_connection_status()


def disconnect_oauth(user_id):
    _delete_config(OAUTH_TOKEN_CONFIG_KEY)
    _delete_config(OAUTH_STATE_CONFIG_KEY)
    return get_connection_status()


def update_drive_settings(root_folder_id=None, user_id=None):
    root_folder_id = _normalize_drive_id(root_folder_id)
    if root_folder_id:
        _set_config(DRIVE_ROOT_CONFIG_KEY, root_folder_id, user_id=user_id, secret=False)
    else:
        _delete_config(DRIVE_ROOT_CONFIG_KEY)
    return get_connection_status()


def get_workspace_root(user_id=None):
    root_folder_id = _require_root_folder_id()
    service, _ = _build_client()
    root = _get_file(service, root_folder_id)
    return {
        'root_id': root_folder_id,
        'root': _serialize_drive_item(root),
    }


def list_children(parent_id=None, user_id=None):
    root_folder_id = _require_root_folder_id()
    parent_id = _normalize_drive_id(parent_id) or root_folder_id

    service, _ = _build_client()
    parent_path = []
    if parent_id != root_folder_id:
        _assert_descendant_of_root(service, parent_id, root_folder_id)
        parent_path = _drive_path_from_root(service, parent_id, root_folder_id)
        _assert_drive_path_visible(parent_path, user_id)

    files = []
    page_token = None
    while True:
        result = _execute_drive_request(service.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            spaces='drive',
            fields=f'nextPageToken,files({DRIVE_ITEM_FIELDS})',
            orderBy='folder,name_natural',
            pageSize=200,
            pageToken=page_token,
            **_list_drive_kwargs(),
        ), 'list Google Drive folder contents')
        files.extend(result.get('files') or [])
        page_token = result.get('nextPageToken')
        if not page_token:
            break

    visible_files = _filter_drive_children_for_user(files, parent_path, user_id)
    return {
        'root_id': root_folder_id,
        'parent_id': parent_id,
        'items': [_serialize_drive_item(item) for item in visible_files],
    }


def create_folder(name, parent_id=None, user_id=None):
    root_folder_id = _require_root_folder_id()
    name = _folder_label(name)
    if not name:
        raise DriveServiceError('Folder name is required.', 422)

    parent_id = _normalize_drive_id(parent_id) or root_folder_id
    service, _ = _build_client()
    parent_path = []
    if parent_id != root_folder_id:
        _assert_descendant_of_root(service, parent_id, root_folder_id)
        parent_path = _drive_path_from_root(service, parent_id, root_folder_id)
    _assert_drive_mutation_parent_visible(parent_path, user_id)

    folder = _execute_drive_request(service.files().create(
        body={
            'name': name,
            'mimeType': DRIVE_FOLDER_MIMETYPE,
            'parents': [parent_id],
        },
        fields=DRIVE_ITEM_FIELDS,
        **_mutation_drive_kwargs(),
    ), 'create Google Drive folder')
    return _serialize_drive_item(folder)


def move_item(file_id, target_parent_id, user_id=None):
    root_folder_id = _require_root_folder_id()
    file_id = _require_drive_id(file_id, 'file_id')
    target_parent_id = _require_drive_id(target_parent_id, 'target_parent_id')

    service, _ = _build_client()
    _assert_descendant_of_root(service, file_id, root_folder_id)
    source_path = _drive_path_from_root(service, file_id, root_folder_id)
    _assert_drive_mutation_item_visible(source_path, user_id)
    target = _get_file(service, target_parent_id)
    if target.get('mimeType') != DRIVE_FOLDER_MIMETYPE:
        raise DriveServiceError('Target parent must be a Google Drive folder.', 422)
    target_path = []
    if target_parent_id != root_folder_id:
        _assert_descendant_of_root(service, target_parent_id, root_folder_id)
        target_path = _drive_path_from_root(service, target_parent_id, root_folder_id)
    _assert_drive_mutation_parent_visible(target_path, user_id)

    current = _get_file(service, file_id)
    previous_parents = ','.join(current.get('parents') or [])
    update_kwargs = {
        'fileId': file_id,
        'addParents': target_parent_id,
        'fields': DRIVE_ITEM_FIELDS,
        **_mutation_drive_kwargs(),
    }
    if previous_parents:
        update_kwargs['removeParents'] = previous_parents

    moved = _execute_drive_request(service.files().update(**update_kwargs), 'move Google Drive item')
    return _serialize_drive_item(moved)


def push_submission(project_requirement, submission):
    root_folder_id = _require_root_folder_id()

    service, media_upload_cls = _build_client()
    requirement_folder = _ensure_requirement_folder(service, project_requirement, root_folder_id)
    project = project_requirement.project
    lgu = project.lgu
    program = project.program

    uploaded_files = []
    total_size_bytes = 0
    for document_file in submission.document_files.order_by(DocumentFile.created_at.asc()).all():
        with _document_file_for_drive(document_file) as file_path:
            metadata = {
                'name': document_file.file_name,
                'parents': [requirement_folder['id']],
            }
            uploaded = _execute_drive_request(service.files().create(
                body=metadata,
                media_body=media_upload_cls(str(file_path), mimetype=document_file.mime_type, resumable=False),
                fields='id,name,webViewLink,webContentLink,size',
                **_mutation_drive_kwargs(),
            ), 'upload file to Google Drive')
        uploaded_files.append(uploaded)
        total_size_bytes += int(document_file.file_size_bytes or 0)

    return {
        'drive_folder_id': requirement_folder['id'],
        'drive_folder_url': requirement_folder['url'],
        'destination_path': _requirement_destination_path(project_requirement),
        'files_count': len(uploaded_files),
        'total_size_bytes': total_size_bytes,
        'api_response_metadata': {
            'uploaded_files': uploaded_files,
        },
    }


@contextlib.contextmanager
def _document_file_for_drive(document_file):
    if document_file.stored_object is not None:
        try:
            with object_storage_service.temporary_file(document_file.stored_object) as temp_path:
                yield temp_path
                return
        except object_storage_service.ObjectStorageError as exc:
            raise DriveServiceError(exc.message, exc.status_code) from exc

    from app.services import submission_service

    try:
        file_path = submission_service.resolve_document_file_path(document_file)
    except submission_service.SubmissionError as exc:
        raise DriveServiceError(exc.message, exc.status_code) from exc
    yield file_path


def ensure_requirement_folder(project_requirement):
    root_folder_id = _require_root_folder_id()
    service, _ = _build_client()
    folder = _ensure_requirement_folder(service, project_requirement, root_folder_id)
    return {
        'drive_folder_id': folder['id'],
        'drive_folder_url': folder['url'],
        'destination_path': _requirement_destination_path(project_requirement),
    }


def _ensure_requirement_folder(service, project_requirement, root_folder_id):
    project = project_requirement.project
    lgu = project.lgu
    program = project.program

    program_folder = _ensure_folder(service, _folder_label(program.code or program.name), root_folder_id)
    fiscal_year_folder = _ensure_folder(service, str(project.fiscal_year), program_folder['id'])
    project_folder = _ensure_folder(
        service,
        _folder_label(f'{lgu.name} - {project.project_name}'),
        fiscal_year_folder['id'],
    )
    requirement_folder = _ensure_folder(
        service,
        _folder_label(project_requirement.requirement_name),
        project_folder['id'],
    )
    return requirement_folder


def _requirement_destination_path(project_requirement):
    project = project_requirement.project
    lgu = project.lgu
    program = project.program
    return '/'.join([
        _folder_label(program.code or program.name),
        str(project.fiscal_year),
        _folder_label(f'{lgu.name} - {project.project_name}'),
        _folder_label(project_requirement.requirement_name),
    ])


def _require_root_folder_id():
    if not is_configured():
        raise DriveServiceError(
            f'Google Drive handoff is not enabled in the current {settings_service.get_app_name()} configuration.',
            503,
        )

    root_folder_id = _get_root_folder_id()
    if not root_folder_id:
        raise DriveServiceError('GOOGLE_DRIVE_ROOT_FOLDER_ID is not configured.', 503)
    return _require_drive_id(root_folder_id, 'GOOGLE_DRIVE_ROOT_FOLDER_ID')


def _build_client():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise DriveServiceError(
            'Google Drive integration dependencies are missing. Install google-api-python-client and google-auth.',
            503,
        ) from exc

    credentials = _load_oauth_credentials() or _load_credentials(service_account)
    return build('drive', 'v3', credentials=credentials, cache_discovery=False), MediaFileUpload


def _load_oauth_credentials():
    token = _get_oauth_token()
    if not token:
        return None
    credentials = Credentials(
        token=token.get('access_token'),
        refresh_token=token.get('refresh_token'),
        token_uri=token.get('token_uri') or 'https://oauth2.googleapis.com/token',
        client_id=current_app.config.get('GOOGLE_OAUTH_CLIENT_ID'),
        client_secret=current_app.config.get('GOOGLE_OAUTH_CLIENT_SECRET'),
        scopes=token.get('scopes') or OAUTH_SCOPES,
    )
    expiry = _parse_iso_datetime(token.get('expiry'))
    if expiry:
        credentials.expiry = expiry.replace(tzinfo=None)
    if not credentials.valid and credentials.refresh_token:
        try:
            credentials.refresh(GoogleAuthRequest())
        except Exception as exc:
            raise DriveServiceError('Google Drive OAuth token has expired and could not be refreshed. Reconnect Drive in Settings.', 401) from exc
        refreshed = {
            **token,
            'expiry': credentials.expiry.replace(tzinfo=timezone.utc).isoformat() if credentials.expiry else None,
        }
        for transient_key in ('access_token', 'client_id', 'client_secret'):
            refreshed.pop(transient_key, None)
        _set_config(OAUTH_TOKEN_CONFIG_KEY, refreshed, user_id=None, secret=True)
    return credentials


def _load_credentials(service_account_module):
    raw_info = current_app.config.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON')
    file_path = current_app.config.get('GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE')

    if raw_info:
        try:
            info = json.loads(raw_info)
        except json.JSONDecodeError as exc:
            raise DriveServiceError('GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON is not valid JSON.', 503) from exc
        try:
            return service_account_module.Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
        except Exception as exc:
            raise DriveServiceError(
                'Google Drive service account credentials are malformed or incomplete. Check GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON.',
                503,
            ) from exc

    if file_path:
        credential_path = Path(file_path)
        if not credential_path.exists():
            raise DriveServiceError('GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE does not exist.', 503)
        try:
            return service_account_module.Credentials.from_service_account_file(str(credential_path), scopes=DRIVE_SCOPES)
        except Exception as exc:
            raise DriveServiceError(
                'Google Drive service account credentials are malformed or incomplete. Check GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE.',
                503,
            ) from exc

    raise DriveServiceError(
        'Google Drive service account credentials are not configured. Set GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE or GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON.',
        503,
    )


def _ensure_folder(service, name, parent_id):
    escaped_name = name.replace("'", "\\'")
    query = (
        f"mimeType = '{DRIVE_FOLDER_MIMETYPE}' and trashed = false "
        f"and name = '{escaped_name}' and '{parent_id}' in parents"
    )
    result = _execute_drive_request(service.files().list(
        q=query,
        spaces='drive',
        fields='files(id,name,webViewLink)',
        **_list_drive_kwargs(),
    ), 'find Google Drive folder')
    existing = (result.get('files') or [])
    if existing:
        folder = existing[0]
        return {
            'id': folder['id'],
            'url': folder.get('webViewLink') or f"https://drive.google.com/drive/folders/{folder['id']}",
        }

    folder = _execute_drive_request(service.files().create(
        body={
            'name': name,
            'mimeType': DRIVE_FOLDER_MIMETYPE,
            'parents': [parent_id],
        },
        fields='id,webViewLink',
        **_mutation_drive_kwargs(),
    ), 'create Google Drive folder')
    return {
        'id': folder['id'],
        'url': folder.get('webViewLink') or f"https://drive.google.com/drive/folders/{folder['id']}",
    }


def _get_file(service, file_id):
    return _execute_drive_request(service.files().get(
        fileId=file_id,
        fields=DRIVE_ITEM_FIELDS,
        **_mutation_drive_kwargs(),
    ), 'get Google Drive item')


def _execute_drive_request(request, action):
    try:
        return request.execute()
    except Exception as exc:
        if exc.__class__.__name__ != 'HttpError':
            raise
        raise _drive_service_error_from_http_error(exc, action) from exc


def _drive_service_error_from_http_error(exc, action):
    status_code = getattr(getattr(exc, 'resp', None), 'status', None) or 503
    reason = ''
    message = str(exc)
    content = getattr(exc, 'content', None)

    if isinstance(content, bytes):
        content = content.decode('utf-8', errors='replace')
    if content:
        try:
            payload = json.loads(content)
            error = payload.get('error') or {}
            details = error.get('errors') or []
            if details:
                reason = details[0].get('reason') or ''
                message = details[0].get('message') or message
            else:
                message = error.get('message') or message
        except (TypeError, ValueError):
            message = str(content)

    if reason == 'storageQuotaExceeded' or 'do not have storage quota' in message:
        app_name = settings_service.get_app_name()
        return DriveServiceError(
            'Google Drive upload failed because the configured root appears to be in a normal My Drive folder. '
            f'Service accounts do not have personal Drive storage quota. Move the {app_name} handoff root to a Google Shared Drive '
            'and set GOOGLE_DRIVE_ROOT_FOLDER_ID to a folder inside that Shared Drive, or switch the integration to OAuth/domain delegation.',
            403,
        )

    return DriveServiceError(f'Unable to {action}: {message}', status_code)


def _assert_descendant_of_root(service, file_id, root_folder_id):
    current_id = _require_drive_id(file_id, 'file_id')
    visited = set()

    for _ in range(50):
        if current_id == root_folder_id:
            return True
        if current_id in visited:
            break
        visited.add(current_id)

        item = _get_file(service, current_id)
        parents = item.get('parents') or []
        if root_folder_id in parents:
            return True
        if not parents:
            break
        current_id = parents[0]

    raise DriveServiceError('The requested Google Drive item is outside the configured regional handoff root.', 403)


def _drive_path_from_root(service, file_id, root_folder_id):
    current_id = _require_drive_id(file_id, 'file_id')
    chain = []
    visited = set()

    for _ in range(50):
        if current_id == root_folder_id:
            return [item.get('name') for item in reversed(chain)]
        if current_id in visited:
            break
        visited.add(current_id)

        item = _get_file(service, current_id)
        chain.append(item)
        parents = item.get('parents') or []
        if root_folder_id in parents:
            return [item.get('name') for item in reversed(chain)]
        if not parents:
            break
        current_id = parents[0]

    raise DriveServiceError('The requested Google Drive item is outside the configured regional handoff root.', 403)


def _filter_drive_children_for_user(items, parent_path, user_id):
    scope = _drive_scope_for_user(user_id)
    if scope is None:
        return items
    return [
        item for item in items
        if _drive_path_visible([*parent_path, item.get('name')], scope)
    ]


def _assert_drive_path_visible(path, user_id):
    scope = _drive_scope_for_user(user_id)
    if scope is None:
        return
    if not _drive_path_visible(path, scope):
        raise DriveServiceError('You do not have permission to access this Google Drive folder.', 403)


def _assert_drive_mutation_parent_visible(parent_path, user_id):
    scope = _drive_scope_for_user(user_id)
    if scope is None:
        return
    if not _drive_project_path_visible(parent_path, scope):
        raise DriveServiceError(
            f'Drive changes are limited to project folders within your assigned {settings_service.get_app_name()} scope.',
            403,
        )


def _assert_drive_mutation_item_visible(item_path, user_id):
    scope = _drive_scope_for_user(user_id)
    if scope is None:
        return
    if not _drive_project_path_visible(item_path, scope):
        raise DriveServiceError(
            'Staff Drive changes are limited to project folders within their assigned LGU cluster.',
            403,
        )


def _drive_scope_for_user(user_id):
    if user_id is None:
        return None
    try:
        scope = access_service.get_access_scope(user_id)
    except access_service.AccessError as exc:
        raise DriveServiceError(exc.message, exc.status_code) from exc
    if scope['unrestricted']:
        return None

    query = access_service.restrict_project_query(Project.query, user_id)
    projects = query.all()
    scope = {
        'programs': set(),
        'fiscal_years': set(),
        'projects': set(),
    }
    for project in projects:
        program_label = _folder_label(project.program.code or project.program.name)
        fiscal_year_label = str(project.fiscal_year)
        project_label = _folder_label(f'{project.lgu.name} - {project.project_name}')
        scope['programs'].add(program_label)
        scope['fiscal_years'].add((program_label, fiscal_year_label))
        scope['projects'].add((program_label, fiscal_year_label, project_label))
    return scope


def _drive_path_visible(path, scope):
    normalized = [_folder_label(item) for item in path if item not in (None, '')]
    if not normalized:
        return True
    if len(normalized) == 1:
        return normalized[0] in scope['programs']
    if len(normalized) == 2:
        return tuple(normalized[:2]) in scope['fiscal_years']
    return tuple(normalized[:3]) in scope['projects']


def _drive_project_path_visible(path, scope):
    normalized = [_folder_label(item) for item in path if item not in (None, '')]
    return len(normalized) >= 3 and tuple(normalized[:3]) in scope['projects']


def _serialize_drive_item(item):
    mime_type = item.get('mimeType')
    is_folder = mime_type == DRIVE_FOLDER_MIMETYPE
    return {
        'id': item.get('id'),
        'name': item.get('name'),
        'mime_type': mime_type,
        'is_folder': is_folder,
        'parents': item.get('parents') or [],
        'web_view_link': item.get('webViewLink') or (
            f"https://drive.google.com/drive/folders/{item.get('id')}" if is_folder and item.get('id') else None
        ),
        'web_content_link': item.get('webContentLink'),
        'size': int(item.get('size') or 0),
        'modified_time': item.get('modifiedTime'),
        'created_time': item.get('createdTime'),
        'icon_link': item.get('iconLink'),
        'thumbnail_link': item.get('thumbnailLink'),
    }


def _normalize_drive_id(value):
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if "'" in normalized or '"' in normalized:
        raise DriveServiceError('Invalid Google Drive id.', 422)
    return normalized


def _require_drive_id(value, field_name):
    normalized = _normalize_drive_id(value)
    if not normalized:
        raise DriveServiceError(f'{field_name} is required.', 422)
    return normalized


def _shared_drive_id():
    from app.services.integration_config_service import resolve_drive_runtime_value
    return resolve_drive_runtime_value('GOOGLE_DRIVE_SHARED_DRIVE_ID')


def _get_root_folder_id():
    from app.services.integration_config_service import resolve_drive_runtime_value
    return resolve_drive_runtime_value(DRIVE_ROOT_CONFIG_KEY)


def _oauth_client_configured():
    return bool(current_app.config.get('GOOGLE_OAUTH_CLIENT_ID') and current_app.config.get('GOOGLE_OAUTH_CLIENT_SECRET'))


def _require_oauth_client():
    client_id = current_app.config.get('GOOGLE_OAUTH_CLIENT_ID')
    client_secret = current_app.config.get('GOOGLE_OAUTH_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise DriveServiceError('Google OAuth client id and secret are not configured.', 503)
    return client_id, client_secret


def _oauth_redirect_uri():
    return current_app.config.get('GOOGLE_DRIVE_OAUTH_REDIRECT_URI')


def _get_oauth_token():
    token = _get_config_json(OAUTH_TOKEN_CONFIG_KEY)
    if token:
        removed_transient = False
        for transient_key in ('access_token', 'client_id', 'client_secret'):
            if transient_key in token:
                removed_transient = True
                token.pop(transient_key, None)
        if removed_transient:
            _set_config(OAUTH_TOKEN_CONFIG_KEY, token, user_id=None, secret=True)
    return token


def _config_by_key(key):
    config = SystemConfig.query.filter_by(key=key).first()
    if not config or config.value in (None, ''):
        return None
    if config.is_encrypted:
        return _decrypt_secret_value(config.value)
    return config.value


def _get_config_json(key):
    config = SystemConfig.query.filter_by(key=key).first()
    if not config or config.value in (None, ''):
        return None
    value = _decrypt_secret_value(config.value) if config.is_encrypted else config.value
    if not value:
        return None
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return None
    if config.value_type == 'secret' and not _is_encrypted_value(config.value):
        _set_config(key, payload, user_id=config.updated_by, secret=True)
    return payload


def _set_config(key, value, user_id=None, secret=False):
    config = SystemConfig.query.filter_by(key=key).first()
    if not config:
        config = SystemConfig(key=key)
        db.session.add(config)
    serialized = json.dumps(value) if isinstance(value, (dict, list)) else value
    config.value = _encrypt_secret_value(serialized) if secret and serialized not in (None, '') else serialized
    config.value_type = 'secret' if secret else 'string'
    config.is_encrypted = bool(secret)
    config.description = _drive_config_description(key)
    config.updated_by = int(user_id) if user_id else None
    db.session.commit()
    return config


def _delete_config(key):
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        db.session.delete(config)
        db.session.commit()


def _has_config_value(key):
    config = SystemConfig.query.filter_by(key=key).first()
    return bool(config and config.value not in (None, ''))


def _is_decryption_error(exc):
    return (
        isinstance(exc, DriveServiceError)
        and exc.status_code == 503
        and 'could not be decrypted' in str(exc.message)
    )


def _is_encrypted_value(value):
    return isinstance(value, str) and value.startswith(ENCRYPTED_VALUE_PREFIX)


def _encrypt_secret_value(value):
    if value in (None, ''):
        return value
    if _is_encrypted_value(value):
        return value
    token = _secret_cipher().encrypt(str(value).encode('utf-8')).decode('utf-8')
    return f'{ENCRYPTED_VALUE_PREFIX}{token}'


def _decrypt_secret_value(value):
    if value in (None, '') or not _is_encrypted_value(value):
        return value
    token = value[len(ENCRYPTED_VALUE_PREFIX):]
    try:
        return _secret_cipher().decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken as exc:
        raise DriveServiceError(
            'Encrypted Google Drive configuration could not be decrypted. Check SYSTEM_CONFIG_SECRET_KEY.',
            503,
        ) from exc


def _secret_cipher():
    secret = current_app.config.get('SYSTEM_CONFIG_SECRET_KEY')
    if not secret:
        raise DriveServiceError('SYSTEM_CONFIG_SECRET_KEY is required for encrypted Drive settings.', 503)
    key = base64.urlsafe_b64encode(hashlib.sha256(str(secret).encode('utf-8')).digest())
    return Fernet(key)


def _drive_config_description(key):
    descriptions = {
        OAUTH_TOKEN_CONFIG_KEY: 'Google Drive OAuth token for the connected COMET handoff account.',
        OAUTH_STATE_CONFIG_KEY: 'Temporary Google Drive OAuth connection state.',
        DRIVE_ROOT_CONFIG_KEY: 'Google Drive root folder id used by regional handoff.',
    }
    return descriptions.get(key, 'Google Drive integration setting.')


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _fetch_google_account_email(access_token):
    if not access_token:
        return None
    try:
        response = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=20,
        )
    except requests.RequestException:
        return None
    if response.status_code >= 400:
        return None
    return response.json().get('email')


def _google_oauth_error(response, fallback):
    try:
        payload = response.json()
    except ValueError:
        return fallback
    error = payload.get('error_description') or payload.get('error')
    return error or fallback


def _list_drive_kwargs():
    shared_drive_id = _shared_drive_id()
    kwargs = {
        'supportsAllDrives': True,
        'includeItemsFromAllDrives': True,
    }
    if shared_drive_id:
        kwargs['corpora'] = 'drive'
        kwargs['driveId'] = shared_drive_id
    return kwargs


def _mutation_drive_kwargs():
    return {
        'supportsAllDrives': True,
    }


def _folder_label(value):
    return str(value or 'Uncategorized').replace('/', '-').strip()
