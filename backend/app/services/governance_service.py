from datetime import date
from pathlib import Path, PureWindowsPath
import uuid

from sqlalchemy import false
from werkzeug.utils import secure_filename
from flask import current_app

from app.extensions import db
from app.models import (
    AuditLog,
    CommunicationLog,
    DocumentFile,
    EscalationNotice,
    GoogleDrivePush,
    LguProfile,
    Program,
    ProgramGuideline,
    Project,
    ProjectRequirement,
    Submission,
    SubmissionVersion,
    User,
)
from app.services import access_service, audit_service, object_storage_service
from app.services.upload_validation import resolve_upload_mime_type, validate_upload_filename
from app.utils.datetime import to_iso_utc


VALID_GUIDELINE_TYPES = (
    'memorandum',
    'circular',
    'annex',
    'local_budget_circular',
    'omnibus_guideline',
    'other',
)


class GovernanceError(Exception):
    def __init__(self, message, status_code=400, errors=None):
        self.message = message
        self.status_code = status_code
        self.errors = errors
        super().__init__(message)


def list_guidelines(search=None, program_id=None, guideline_type=None, is_current=None, page=1, per_page=20):
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
    if guideline_type:
        query = query.filter(ProgramGuideline.guideline_type == guideline_type)
    if is_current is not None:
        query = query.filter(ProgramGuideline.is_current == is_current)

    pagination = query.order_by(
        ProgramGuideline.is_current.desc(),
        ProgramGuideline.effective_date.desc().nullslast(),
        ProgramGuideline.created_at.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)
    return {
        'items': [_serialize_guideline(item) for item in pagination.items],
        'page': pagination.page,
        'per_page': pagination.per_page,
        'total': pagination.total,
        'pages': pagination.pages,
    }


def create_guideline(data, user_id, upload=None):
    program_id = _parse_int(data.get('program_id'), 'program_id')
    if not db.session.get(Program, program_id):
        raise GovernanceError('Program not found', 404, errors={'program_id': 'Program was not found.'})
    guideline_type = _clean_required_text(data.get('guideline_type'), 'guideline_type', 'Type')
    _validate_guideline_type(guideline_type)
    with object_storage_service.storage_transaction() as storage_tx:
        upload_metadata = _store_guideline_upload(upload, user_id=user_id, tracker=storage_tx) if upload else {}
        client_file_path = None if upload_metadata else _normalize_client_file_reference(data.get('file_path'))

        guideline = ProgramGuideline(
            program_id=program_id,
            uploaded_by=int(user_id),
            title=_clean_required_text(data.get('title'), 'title', 'Title'),
            guideline_type=guideline_type,
            reference_number=_clean_optional_text(data.get('reference_number')),
            issuing_body=_clean_optional_text(data.get('issuing_body')),
            effective_date=_parse_optional_date(data.get('effective_date')),
            is_current=_parse_bool(data.get('is_current', True)),
            file_path=upload_metadata.get('file_path', client_file_path),
            file_name=upload_metadata.get('file_name', _clean_optional_text(data.get('file_name'))),
            stored_object_id=upload_metadata.get('stored_object_id'),
            description=_clean_optional_text(data.get('description')),
        )
        db.session.add(guideline)
        db.session.commit()
        storage_tx.commit()

    audit_service.log_action(
        user_id=int(user_id),
        action='create',
        entity_type='program_guideline',
        entity_id=guideline.id,
        old_value=None,
        new_value=_serialize_guideline(guideline),
    )
    return guideline


def update_guideline(guideline_id, data, user_id, upload=None):
    guideline = db.session.get(ProgramGuideline, guideline_id)
    if not guideline:
        raise GovernanceError('Program guideline not found', 404)

    before = _serialize_guideline(guideline)
    with object_storage_service.storage_transaction() as storage_tx:
        upload_metadata = _store_guideline_upload(upload, user_id=user_id, tracker=storage_tx) if upload else {}

        if 'program_id' in data:
            program_id = _parse_int(data['program_id'], 'program_id')
            if not db.session.get(Program, program_id):
                raise GovernanceError('Program not found', 404, errors={'program_id': 'Program was not found.'})
            guideline.program_id = program_id
        if 'title' in data:
            guideline.title = _clean_required_text(data['title'], 'title', 'Title')
        if 'guideline_type' in data:
            guideline_type = _clean_required_text(data['guideline_type'], 'guideline_type', 'Type')
            _validate_guideline_type(guideline_type)
            guideline.guideline_type = guideline_type
        if 'reference_number' in data:
            guideline.reference_number = _clean_optional_text(data['reference_number'])
        if 'issuing_body' in data:
            guideline.issuing_body = _clean_optional_text(data['issuing_body'])
        if 'effective_date' in data:
            guideline.effective_date = _parse_optional_date(data['effective_date'])
        if 'is_current' in data:
            guideline.is_current = _parse_bool(data['is_current'])
        if 'file_path' in data and not upload_metadata:
            guideline.file_path = _normalize_client_file_reference(data['file_path'])
            guideline.stored_object_id = None
        if 'file_name' in data:
            guideline.file_name = _clean_optional_text(data['file_name'])
        if upload_metadata:
            guideline.file_path = upload_metadata['file_path']
            guideline.file_name = upload_metadata['file_name']
            guideline.stored_object_id = upload_metadata.get('stored_object_id')
        if 'description' in data:
            guideline.description = _clean_optional_text(data['description'])

        db.session.commit()
        storage_tx.commit()

    audit_service.log_action(
        user_id=int(user_id),
        action='update',
        entity_type='program_guideline',
        entity_id=guideline.id,
        old_value=before,
        new_value=_serialize_guideline(guideline),
    )
    return guideline


def get_guideline(guideline_id):
    guideline = db.session.get(ProgramGuideline, guideline_id)
    if not guideline:
        raise GovernanceError('Program guideline not found', 404)
    return guideline


def get_guideline_download(guideline_id):
    guideline = get_guideline(guideline_id)
    if guideline.stored_object is not None:
        return {
            'guideline': guideline,
            'stored_object': guideline.stored_object,
            'path': None,
        }
    if not guideline.file_path:
        raise GovernanceError('Guideline does not have a stored file.', 404)
    if _is_external_url(guideline.file_path):
        raise GovernanceError('Guideline points to an external reference URL.', 409)

    path = _resolve_guideline_upload_path(guideline.file_path)
    if not path:
        raise GovernanceError('Stored guideline file is not available on disk.', 404)
    if not path.exists() or not path.is_file():
        raise GovernanceError('Stored guideline file is not available on disk.', 404)
    return {
        'guideline': guideline,
        'stored_object': None,
        'path': path,
    }


def list_communications(
    search=None,
    lgu_id=None,
    project_id=None,
    communication_type=None,
    channel=None,
    fiscal_year=None,
    page=1,
    per_page=20,
    user_id=None,
):
    query = (
        CommunicationLog.query
        .join(LguProfile, CommunicationLog.lgu_id == LguProfile.id)
        .outerjoin(EscalationNotice, CommunicationLog.related_notice_id == EscalationNotice.id)
    )
    query = _apply_lgu_scope(query, user_id)

    if search:
        query = query.filter(
            db.or_(
                CommunicationLog.subject.ilike(f'%{search}%'),
                CommunicationLog.recipient_name.ilike(f'%{search}%'),
                LguProfile.name.ilike(f'%{search}%'),
            )
        )
    if lgu_id is not None:
        query = query.filter(CommunicationLog.lgu_id == lgu_id)
    if project_id is not None:
        query = query.filter(EscalationNotice.project_id == project_id)
    if communication_type:
        query = query.filter(CommunicationLog.communication_type == communication_type)
    if channel:
        query = query.filter(CommunicationLog.channel == channel)
    if fiscal_year is not None:
        query = query.filter(EscalationNotice.project.has(Project.fiscal_year == fiscal_year))

    pagination = query.order_by(
        CommunicationLog.sent_at.desc().nullslast(),
        CommunicationLog.created_at.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)
    return {
        'items': [_serialize_communication(item) for item in pagination.items],
        'page': pagination.page,
        'per_page': pagination.per_page,
        'total': pagination.total,
        'pages': pagination.pages,
    }


def list_archive_records(search=None, lgu_id=None, program_id=None, fiscal_year=None, page=1, per_page=20, user_id=None):
    query = (
        ProjectRequirement.query
        .join(Project, ProjectRequirement.project_id == Project.id)
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .join(Program, Project.program_id == Program.id)
        .filter(
            db.or_(
                ProjectRequirement.reviewed_at.isnot(None),
                ProjectRequirement.submissions.any(),
                ProjectRequirement.google_drive_pushes.any(),
            )
        )
    )
    query = _apply_requirement_scope(query, user_id)

    if search:
        query = query.filter(
            db.or_(
                Project.project_name.ilike(f'%{search}%'),
                ProjectRequirement.requirement_name.ilike(f'%{search}%'),
                LguProfile.name.ilike(f'%{search}%'),
                Program.name.ilike(f'%{search}%'),
            )
        )
    if lgu_id is not None:
        query = query.filter(Project.lgu_id == lgu_id)
    if program_id is not None:
        query = query.filter(Project.program_id == program_id)
    if fiscal_year is not None:
        query = query.filter(Project.fiscal_year == fiscal_year)

    pagination = query.order_by(
        ProjectRequirement.reviewed_at.desc().nullslast(),
        ProjectRequirement.updated_at.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)
    return {
        'items': [_serialize_archive_record(item) for item in pagination.items],
        'page': pagination.page,
        'per_page': pagination.per_page,
        'total': pagination.total,
        'pages': pagination.pages,
    }


def get_archive_record_detail(project_requirement_id, user_id=None):
    query = (
        ProjectRequirement.query
        .join(Project, ProjectRequirement.project_id == Project.id)
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .filter(ProjectRequirement.id == project_requirement_id)
    )
    query = _apply_requirement_scope(query, user_id)
    requirement = query.first()
    if not requirement:
        raise GovernanceError('Archive record not found', 404)

    project = requirement.project
    submissions = requirement.submissions.order_by(Submission.created_at.desc(), Submission.id.desc()).all()
    handoffs = requirement.google_drive_pushes.order_by(GoogleDrivePush.pushed_at.desc(), GoogleDrivePush.id.desc()).all()
    communications = _project_communications(project).all() if project else []
    audit_events = _archive_audit_events(requirement, submissions, handoffs, communications)

    return {
        **_serialize_archive_record(requirement),
        'submissions': [_serialize_submission_history(item) for item in submissions],
        'handoffs': [_serialize_handoff(item) for item in handoffs],
        'communications': [_serialize_communication(item) for item in communications],
        'audit_events': [_serialize_audit_event(item) for item in audit_events],
    }


def _apply_lgu_scope(query, user_id):
    if user_id is None:
        return query

    scope = access_service.get_access_scope(user_id)
    if scope['unrestricted']:
        return query
    lgu_ids = scope['lgu_ids']
    if lgu_ids:
        return query.filter(LguProfile.id.in_(lgu_ids))
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return query.filter(false())
    return query.filter(LguProfile.cluster_id.in_(cluster_ids))


def _apply_requirement_scope(query, user_id):
    if user_id is None:
        return query

    scope = access_service.get_access_scope(user_id)
    if scope['unrestricted']:
        return query
    lgu_ids = scope['lgu_ids']
    if lgu_ids:
        return query.filter(LguProfile.id.in_(lgu_ids))
    cluster_ids = scope['cluster_ids']
    if not cluster_ids:
        return query.filter(false())
    return query.filter(LguProfile.cluster_id.in_(cluster_ids))


def _validate_guideline_type(value):
    if value not in VALID_GUIDELINE_TYPES:
        raise GovernanceError(
            'Select a supported reference type',
            422,
            errors={'guideline_type': 'Select a supported reference type'},
        )


def _clean_optional_text(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _clean_required_text(value, field_name, label):
    cleaned = _clean_optional_text(value)
    if cleaned is None:
        message = f'{label} is required'
        raise GovernanceError(message, 422, errors={field_name: message})
    return cleaned


def _parse_optional_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            message = 'Effective date must use YYYY-MM-DD'
            raise GovernanceError(message, 422, errors={'effective_date': message}) from exc
    message = 'Effective date must use YYYY-MM-DD'
    raise GovernanceError(message, 422, errors={'effective_date': message})


def _parse_int(value, field_name):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        message = 'Select a valid program' if field_name == 'program_id' else f'{field_name} must be an integer'
        raise GovernanceError(message, 422, errors={field_name: message}) from exc
    if field_name == 'program_id' and parsed <= 0:
        message = 'Select a valid program'
        raise GovernanceError(message, 422, errors={field_name: message})
    return parsed


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {'true', '1', 'yes', 'on'}
    return bool(value)


def _is_external_url(value):
    if not value:
        return False
    return value.startswith('http://') or value.startswith('https://')


def _store_guideline_upload(upload, user_id=None, tracker=None):
    if upload is None or not upload.filename:
        return {}

    filename = validate_upload_filename(
        upload.filename,
        error_factory=lambda message: GovernanceError(message, 422, errors={'file': message}),
        label='Guideline file',
    )

    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    allowed_extensions = current_app.config.get('SUBMISSION_ALLOWED_EXTENSIONS') or ()
    if allowed_extensions and extension not in allowed_extensions:
        message = 'Guideline file type is not allowed.'
        raise GovernanceError(message, 422, errors={'file': message})

    mime_type = resolve_upload_mime_type(
        filename,
        upload,
        current_app.config.get('SUBMISSION_ALLOWED_MIME_TYPES') or (),
        lambda message: GovernanceError(message, 422, errors={'file': message}),
        label='Guideline file',
    )

    size_bytes = _measure_upload_size(upload)
    max_size_bytes = int(current_app.config.get('MAX_GUIDELINE_FILE_BYTES') or current_app.config.get('MAX_SUBMISSION_FILE_BYTES') or 0)
    if max_size_bytes and size_bytes > max_size_bytes:
        message = f'Guideline files must be {max_size_bytes // (1024 * 1024)} MB or smaller.'
        raise GovernanceError(message, 422, errors={'file': message})

    upload_dir = _guideline_upload_root()
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f'{uuid.uuid4().hex}_{filename}'
    file_path = upload_dir / stored_name
    upload.save(file_path)
    if tracker is not None:
        tracker.track_local_path(file_path)
    stored_object = object_storage_service.store_file(
        file_path,
        source_module='guidelines',
        original_filename=filename,
        content_type=mime_type,
        uploaded_by=user_id,
        metadata={'reference_filename': filename},
        tracker=tracker,
    )
    return {
        'file_name': filename,
        'file_path': str(file_path),
        'stored_object_id': stored_object.id,
    }


def _measure_upload_size(upload):
    content_length = getattr(upload, 'content_length', None)
    if content_length is not None and int(content_length) > 0:
        return int(content_length)

    stream = getattr(upload, 'stream', None)
    if stream is None:
        return 0

    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return size


def _normalize_client_file_reference(value):
    if value in (None, ''):
        return None
    reference = str(value).strip()
    if not reference:
        return None
    if _is_external_url(reference):
        return reference
    message = 'Use an http:// or https:// URL, or upload the file instead'
    raise GovernanceError(message, 422, errors={'file_path': message})


def _guideline_upload_root():
    upload_dir = current_app.config.get('GUIDELINE_UPLOAD_DIR')
    if upload_dir:
        return Path(upload_dir)
    base_upload_dir = current_app.config.get('SUBMISSION_UPLOAD_DIR')
    if base_upload_dir:
        return Path(base_upload_dir) / 'guidelines'
    return Path(current_app.instance_path) / 'uploads' / 'guidelines'


def _resolve_guideline_upload_path(path_value):
    if not path_value:
        return None
    for candidate in _guideline_upload_path_candidates(path_value):
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if _path_is_allowed_guideline_file(resolved) and resolved.exists() and resolved.is_file():
            return resolved
    return None


def _guideline_upload_path_candidates(path_value):
    names = []
    for name in (Path(path_value).name, PureWindowsPath(path_value).name):
        if name and name not in names:
            names.append(name)

    candidates = [Path(path_value)]
    for name in names:
        for root in _guideline_file_allowed_roots():
            candidates.append(root / name)

    parts = _portable_path_parts(path_value)
    if 'uploads' in parts:
        upload_index = parts.index('uploads')
        suffix = parts[upload_index:]
        if len(suffix) >= 2 and suffix[1] == 'guidelines':
            candidates.extend([
                Path(current_app.root_path).parent.joinpath(*suffix),
                Path(current_app.instance_path).joinpath(*suffix),
            ])

    return _unique_paths(candidates)


def _path_is_allowed_guideline_file(path):
    for root in _guideline_file_allowed_roots():
        try:
            path.relative_to(root.resolve(strict=False))
            return True
        except (OSError, RuntimeError, ValueError):
            continue
    return False


def _guideline_file_allowed_roots():
    roots = [
        _guideline_upload_root(),
        Path(current_app.instance_path) / 'uploads' / 'guidelines',
        Path(current_app.root_path).parent / 'instance' / 'uploads' / 'guidelines',
        Path(current_app.root_path).parent / 'uploads' / 'guidelines',
    ]
    base_upload_dir = current_app.config.get('SUBMISSION_UPLOAD_DIR')
    if base_upload_dir:
        roots.append(Path(base_upload_dir) / 'guidelines')
    return _unique_paths(roots)


def _portable_path_parts(path_value):
    normalized = str(path_value or '').replace('\\', '/')
    return [part for part in normalized.split('/') if part and part not in ('.', '..')]


def _unique_paths(paths):
    unique = []
    seen = set()
    for path in paths:
        key = str(Path(path))
        if key not in seen:
            seen.add(key)
            unique.append(Path(path))
    return unique


def _project_communications(project):
    return (
        CommunicationLog.query
        .outerjoin(EscalationNotice, CommunicationLog.related_notice_id == EscalationNotice.id)
        .filter(CommunicationLog.lgu_id == project.lgu_id)
        .filter(
            db.or_(
                EscalationNotice.project_id == project.id,
                CommunicationLog.related_notice_id.is_(None),
            )
        )
        .order_by(CommunicationLog.sent_at.desc().nullslast(), CommunicationLog.created_at.desc())
    )


def _archive_audit_events(requirement, submissions, handoffs, communications):
    entity_pairs = [('project_requirement', requirement.id)]
    entity_pairs.extend(('submission', item.id) for item in submissions)
    entity_pairs.extend(('google_drive_push', item.id) for item in handoffs)
    entity_pairs.extend(('communication_log', item.id) for item in communications)

    filters = [
        db.and_(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        for entity_type, entity_id in entity_pairs
    ]
    if not filters:
        return []
    return (
        AuditLog.query
        .filter(db.or_(*filters))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(50)
        .all()
    )


def _serialize_guideline(guideline):
    program = guideline.program
    uploader = db.session.get(User, guideline.uploaded_by) if guideline.uploaded_by else None
    return {
        'id': guideline.id,
        'program_id': guideline.program_id,
        'program_name': program.name if program else None,
        'uploaded_by': guideline.uploaded_by,
        'uploaded_by_name': uploader.full_name if uploader else None,
        'title': guideline.title,
        'guideline_type': guideline.guideline_type,
        'reference_number': guideline.reference_number,
        'issuing_body': guideline.issuing_body,
        'effective_date': guideline.effective_date.isoformat() if guideline.effective_date else None,
        'is_current': bool(guideline.is_current),
        'file_path': guideline.file_path,
        'file_name': guideline.file_name,
        'description': guideline.description,
        'created_at': to_iso_utc(guideline.created_at),
        'updated_at': to_iso_utc(guideline.updated_at),
    }


def _serialize_communication(communication):
    sender = db.session.get(User, communication.sent_by) if communication.sent_by else None
    lgu = communication.lgu
    notice = communication.related_notice
    project = notice.project if notice else None
    return {
        'id': communication.id,
        'lgu_id': communication.lgu_id,
        'lgu_name': lgu.name if lgu else None,
        'project_id': project.id if project else None,
        'project_name': project.project_name if project else None,
        'sent_by': communication.sent_by,
        'sent_by_name': sender.full_name if sender else None,
        'communication_type': communication.communication_type,
        'channel': communication.channel,
        'subject': communication.subject,
        'body': communication.body,
        'recipient_email': communication.recipient_email,
        'recipient_name': communication.recipient_name,
        'recipient_destination': communication.recipient_destination,
        'recipient_office': communication.recipient_office,
        'reference_no': communication.reference_no,
        'related_notice_id': communication.related_notice_id,
        'delivery_status': communication.delivery_status,
        'sent_at': to_iso_utc(communication.sent_at),
        'posted_at': to_iso_utc(communication.posted_at),
        'remarks': communication.remarks,
        'created_at': to_iso_utc(communication.created_at),
    }


def _serialize_submission_history(submission):
    uploader = db.session.get(User, submission.uploaded_by) if submission.uploaded_by else None
    versions = submission.versions.order_by(None).order_by(SubmissionVersion.version_number.desc()).all()
    files = submission.document_files.order_by(DocumentFile.is_primary.desc(), DocumentFile.created_at.desc()).all()
    return {
        'id': submission.id,
        'uploaded_by': submission.uploaded_by,
        'uploaded_by_name': uploader.full_name if uploader else None,
        'description': submission.description,
        'source': submission.source,
        'current_version': submission.current_version,
        'created_at': to_iso_utc(submission.created_at),
        'updated_at': to_iso_utc(submission.updated_at),
        'versions': [_serialize_submission_version(item) for item in versions],
        'document_files': [_serialize_document_file(item) for item in files],
    }


def _serialize_submission_version(version):
    return {
        'id': version.id,
        'submission_id': version.submission_id,
        'version_number': version.version_number,
        'original_filename': version.original_filename,
        'stored_filename': version.stored_filename,
        'file_size_bytes': version.file_size_bytes,
        'mime_type': version.mime_type,
        'uploaded_at': to_iso_utc(version.uploaded_at),
    }


def _serialize_document_file(document_file):
    return {
        'id': document_file.id,
        'file_name': document_file.file_name,
        'file_size_bytes': document_file.file_size_bytes,
        'mime_type': document_file.mime_type,
        'file_hash_sha256': document_file.file_hash_sha256,
        'is_primary': bool(document_file.is_primary),
        'created_at': to_iso_utc(document_file.created_at),
    }


def _serialize_handoff(push):
    pusher = db.session.get(User, push.pushed_by) if push.pushed_by else None
    return {
        'id': push.id,
        'project_id': push.project_id,
        'project_requirement_id': push.project_requirement_id,
        'submission_id': push.submission_id,
        'pushed_by': push.pushed_by,
        'pushed_by_name': pusher.full_name if pusher else None,
        'drive_folder_id': push.drive_folder_id,
        'drive_folder_url': push.drive_folder_url,
        'destination_path': push.destination_path,
        'files_count': push.files_count,
        'total_size_bytes': push.total_size_bytes,
        'push_status': push.push_status,
        'error_message': push.error_message,
        'pushed_at': to_iso_utc(push.pushed_at),
        'created_at': to_iso_utc(push.created_at),
    }


def _serialize_audit_event(event):
    actor = db.session.get(User, event.user_id) if event.user_id else None
    return {
        'id': event.id,
        'user_id': event.user_id,
        'user_name': actor.full_name if actor else None,
        'action': event.action,
        'entity_type': event.entity_type,
        'entity_id': event.entity_id,
        'record_hash': event.record_hash,
        'previous_hash': event.previous_hash,
        'created_at': to_iso_utc(event.created_at),
    }


def _serialize_archive_record(requirement):
    project = requirement.project
    lgu = project.lgu if project else None
    program = project.program if project else None
    latest_submission = requirement.submissions.order_by(Submission.created_at.desc(), Submission.id.desc()).first()
    latest_push = requirement.google_drive_pushes.order_by(GoogleDrivePush.pushed_at.desc(), GoogleDrivePush.id.desc()).first()
    latest_file = None
    if latest_submission is not None:
        latest_file = latest_submission.document_files.order_by(
            DocumentFile.is_primary.desc(),
            DocumentFile.created_at.desc(),
        ).first()

    return {
        'project_requirement_id': requirement.id,
        'project_id': requirement.project_id,
        'project_name': project.project_name if project else None,
        'program_id': project.program_id if project else None,
        'program_name': program.name if program else None,
        'lgu_id': project.lgu_id if project else None,
        'lgu_name': lgu.name if lgu else None,
        'fiscal_year': project.fiscal_year if project else None,
        'requirement_name': requirement.requirement_name,
        'phase_name': requirement.phase_name,
        'status': requirement.status,
        'submission_count': requirement.submissions.count(),
        'latest_submission_at': to_iso_utc(latest_submission.created_at) if latest_submission and latest_submission.created_at else None,
        'latest_submission_source': latest_submission.source if latest_submission else None,
        'latest_submission_file_name': latest_file.file_name if latest_file else None,
        'reviewed_at': to_iso_utc(requirement.reviewed_at) if requirement.reviewed_at else None,
        'latest_push_status': latest_push.push_status if latest_push else None,
        'latest_push_at': to_iso_utc(latest_push.pushed_at) if latest_push and latest_push.pushed_at else None,
        'latest_push_destination': latest_push.destination_path if latest_push else None,
        'latest_push_url': latest_push.drive_folder_url if latest_push else None,
        'handoff_count': requirement.google_drive_pushes.count(),
    }
