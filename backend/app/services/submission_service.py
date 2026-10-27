from datetime import datetime, timezone
import hashlib
import os
import uuid
from pathlib import Path, PureWindowsPath

from flask import current_app
import sqlalchemy as sa
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    DocumentFile,
    DocumentComplianceResult,
    GoogleDrivePush,
    LguProfile,
    NlpScanResult,
    Program,
    Project,
    ProjectRequirement,
    Submission,
    SubmissionVersion,
)
from app.services import access_service, audit_service, document_compliance_service, document_intelligence_service, drive_service, object_storage_service, search_service
from app.services.fiscal_year_scope import apply_requirement_project_fiscal_year
from app.services.upload_validation import resolve_upload_mime_type, validate_upload_filename


VALID_SUBMISSION_SOURCES = ('dms_ingestion', 'direct_upload', 'field_upload', 'api_push')
EVIDENCE_REQUIRED_STATUSES = {'under_review', 'compliant'}


class SubmissionError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def get_intake_queue_summary(
    *,
    fiscal_year=None,
    user_id=None,
    lgu_id=None,
    project_id=None,
):
    query = (
        ProjectRequirement.query
        .join(Project, ProjectRequirement.project_id == Project.id)
        .filter(ProjectRequirement.is_active == True)
    )
    if user_id is not None:
        query = access_service.restrict_project_requirement_query(query, user_id)
    query = apply_requirement_project_fiscal_year(query, fiscal_year)
    if project_id is not None:
        query = query.filter(Project.id == project_id)
    if lgu_id is not None:
        query = query.filter(Project.lgu_id == lgu_id)

    has_evidence_sub = (
        db.session.query(DocumentFile.id)
        .join(Submission, DocumentFile.submission_id == Submission.id)
        .filter(Submission.project_requirement_id == ProjectRequirement.id)
        .correlate(ProjectRequirement)
        .exists()
    )
    res = query.with_entities(
        sa.func.count(ProjectRequirement.id).label('total'),
        sa.func.count(ProjectRequirement.id).filter(has_evidence_sub).label('with_evidence'),
        sa.func.count(ProjectRequirement.id).filter(
            sa.and_(
                ProjectRequirement.status == 'pending',
                ProjectRequirement.applicability == 'applicable',
            )
        ).label('pending'),
        sa.func.count(ProjectRequirement.id).filter(
            sa.and_(
                ProjectRequirement.status == 'under_review',
                ProjectRequirement.applicability == 'applicable',
            )
        ).label('under_review'),
        sa.func.count(ProjectRequirement.id).filter(
            ProjectRequirement.applicability == 'not_applicable'
        ).label('not_applicable'),
    ).first()
    return {
        'total': int(res[0]) if res and res[0] is not None else 0,
        'with_evidence': int(res[1]) if res and res[1] is not None else 0,
        'pending': int(res[2]) if res and res[2] is not None else 0,
        'under_review': int(res[3]) if res and res[3] is not None else 0,
        'not_applicable': int(res[4]) if res and res[4] is not None else 0,
    }


def list_intake_queue(
    *,
    search=None,
    status=None,
    phase_name=None,
    project_id=None,
    lgu_id=None,
    page=1,
    per_page=20,
    fiscal_year=None,
    user_id=None,
    applicability=None,
):
    summary = get_intake_queue_summary(
        fiscal_year=fiscal_year,
        user_id=user_id,
        lgu_id=lgu_id,
        project_id=project_id,
    )
    query = (
        ProjectRequirement.query
        .join(Project, ProjectRequirement.project_id == Project.id)
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .join(Program, Project.program_id == Program.id)
        .filter(ProjectRequirement.is_active == True)
    )
    if user_id is not None:
        query = access_service.restrict_project_requirement_query(query, user_id)
    query = apply_requirement_project_fiscal_year(query, fiscal_year)

    if applicability == 'all':
        pass
    elif applicability:
        query = query.filter(ProjectRequirement.applicability == applicability)
    else:
        query = query.filter(ProjectRequirement.applicability == 'applicable')

    if status:
        query = query.filter(ProjectRequirement.status == status)
    if phase_name:
        query = query.filter(ProjectRequirement.phase_name == phase_name)
    if project_id is not None:
        query = query.filter(Project.id == project_id)
    if lgu_id is not None:
        query = query.filter(Project.lgu_id == lgu_id)

    order_by = (Project.updated_at.desc(), ProjectRequirement.sort_order.asc())
    user_role = access_service.get_user_role(user_id) if user_id else None
    if search:
        search_result = search_service.search_requirements(
            query,
            search,
            page=page,
            per_page=per_page,
            serialize=lambda req: _serialize_intake_requirement(req, user_role=user_role),
            order_by=order_by,
        )
        search_result['summary'] = summary
        return search_result

    pagination = query.order_by(*order_by).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return {
        'items': [_serialize_intake_requirement(requirement, user_role=user_role) for requirement in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
        'summary': summary,
    }


def create_submission(
    *,
    requirement_id,
    source,
    description,
    upload,
    user_id,
):
    _require_role(user_id, 'admin', 'staff', 'field_officer')
    role = access_service.get_user_role(user_id)
    requirement = _get_requirement_with_access(requirement_id, user_id=user_id)
    # Serialize intake against applicability decisions before checking the state.
    requirement = ProjectRequirement.query.filter_by(id=requirement.id).with_for_update().populate_existing().one()
    try:
        access_service.assert_project_requirement_movement_allowed(requirement, require_applicable=True)
    except access_service.AccessError as exc:
        raise SubmissionError(exc.message, exc.status_code) from exc
    source = str(source or '').strip()
    if role == 'field_officer':
        source = 'field_upload'
    if source not in VALID_SUBMISSION_SOURCES:
        raise SubmissionError(f'Source must be one of: {", ".join(VALID_SUBMISSION_SOURCES)}', 422)
    if upload is None or not getattr(upload, 'filename', '').strip():
        raise SubmissionError('A documentary file is required for intake.', 422)

    original_filename = validate_upload_filename(
        upload.filename,
        error_factory=lambda msg: SubmissionError(msg, 422),
        label='Documentary intake file',
    )
    mime_type = _validate_upload_constraints(original_filename, upload)
    extension = Path(original_filename).suffix
    stored_filename = f'{uuid.uuid4().hex}{extension}'

    # Dynamic version calculation based on prior submissions for this requirement.
    # The parent row lock acquired above also serializes version allocation
    # across concurrent submissions and prevents duplicate version numbers.
    prior_count = Submission.query.filter_by(project_requirement_id=requirement.id).count()
    version_number = prior_count + 1

    with object_storage_service.storage_transaction() as storage_tx:
        submission = Submission(
            project_requirement_id=requirement.id,
            uploaded_by=user_id,
            description=description,
            source=source,
            current_version=version_number,
        )
        db.session.add(submission)
        db.session.flush()

        destination_dir = _submission_root() / str(submission.id)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / stored_filename
        upload.save(destination_path)
        storage_tx.track_local_path(destination_path)

        file_hash = _sha256(destination_path)
        file_size = destination_path.stat().st_size
        stored_object = object_storage_service.store_file(
            destination_path,
            source_module='submissions',
            original_filename=original_filename,
            content_type=mime_type,
            uploaded_by=user_id,
            metadata={
                'submission_id': submission.id,
                'project_requirement_id': requirement.id,
                'source': source,
            },
            tracker=storage_tx,
        )

        version = SubmissionVersion(
            submission_id=submission.id,
            version_number=version_number,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=str(destination_path),
            stored_object_id=stored_object.id,
            file_size_bytes=file_size,
            mime_type=mime_type,
        )
        document_file = DocumentFile(
            submission_id=submission.id,
            file_name=original_filename,
            file_path=str(destination_path),
            stored_object_id=stored_object.id,
            file_size_bytes=file_size,
            mime_type=mime_type,
            file_hash_sha256=file_hash,
            is_primary=True,
        )
        db.session.add(version)
        db.session.add(document_file)

        requirement_status_before = _requirement_status_audit_payload(requirement)
        moved_to_review = False
        is_resubmission = requirement.workflow_status == 'returned_for_revision'

        if is_resubmission and requirement.document_category:
            from app.models.workflow import RequirementWorkflowTransition
            requirement.workflow_status = 'resubmitted'
            requirement.workflow_return_reason = None
            requirement.workflow_returned_at = None
            requirement.workflow_returned_by = None
            requirement.workflow_submitted_by = user_id
            requirement.workflow_submitted_at = datetime.now(timezone.utc)
            if requirement.status != 'under_review':
                requirement.status = 'under_review'
                requirement.reviewed_at = None
                requirement.last_action_by = user_id
                moved_to_review = True

            transition = RequirementWorkflowTransition(
                project_requirement_id=requirement.id,
                from_status='returned_for_revision',
                to_status='resubmitted',
                action='resubmit',
                actor_id=user_id,
                reason=description or 'Resubmitted revised documentary files.',
            )
            db.session.add(transition)
        elif is_resubmission:
            # Unmanaged requirement: resubmission clears returned state back to standard under_review
            requirement.workflow_status = None
            requirement.workflow_return_reason = None
            requirement.workflow_returned_at = None
            requirement.workflow_returned_by = None
            if requirement.status != 'under_review':
                requirement.status = 'under_review'
                requirement.reviewed_at = None
                requirement.last_action_by = user_id
                moved_to_review = True
        elif requirement.status == 'pending':
            requirement.status = 'under_review'
            requirement.reviewed_at = None
            requirement.last_action_by = user_id
            moved_to_review = True

        # Atomically stage centralized audit log for submission creation
        audit_service.log_action(
            user_id=user_id,
            action='create',
            entity_type='submission',
            entity_id=submission.id,
            old_value=None,
            new_value=_serialize_submission(submission),
            commit=False,
        )
        if is_resubmission and requirement.document_category:
            audit_service.log_action(
                user_id=user_id,
                action='workflow_resubmit',
                entity_type='project_requirement',
                entity_id=requirement.id,
                old_value=requirement_status_before,
                new_value=_requirement_status_audit_payload(requirement),
                commit=False,
            )
        elif moved_to_review or is_resubmission:
            audit_service.log_action(
                user_id=user_id,
                action='status_change',
                entity_type='project_requirement',
                entity_id=requirement.id,
                old_value=requirement_status_before,
                new_value=_requirement_status_audit_payload(requirement),
                commit=False,
            )

        if moved_to_review or is_resubmission:
            from app.services import workbook_sync_service
            workbook_sync_service.sync_requirement_status(requirement, user_id=user_id, commit=False)
        db.session.commit()
        storage_tx.commit()

    if is_resubmission and requirement.document_category:
        from app.services import requirement_workflow_service
        requirement_workflow_service._notify_best_effort(
            requirement_workflow_service._notify_workflow_event,
            requirement=requirement,
            event='resubmitted',
            actor_id=user_id,
        )

    evidence = None
    try:
        evidence = document_intelligence_service.build_document_evidence(
            destination_path,
            mime_type=mime_type,
            file_name=original_filename,
            document_file=document_file,
        )
    except Exception as exc:
        current_app.logger.warning(
            'DocumentEvidence extraction skipped for submission %s: %s',
            submission.id,
            exc,
        )

    try:
        document_intelligence_service.scan_submission(submission.id, user_id, evidence=evidence)
    except document_intelligence_service.DocumentIntelligenceError as exc:
        current_app.logger.warning(
            'Document intelligence scan skipped for submission %s: %s',
            submission.id,
            exc.message,
        )
    except Exception as exc:  # pragma: no cover - defensive, intake should survive OCR failures.
        current_app.logger.exception(
            'Document intelligence scan failed for submission %s: %s',
            submission.id,
            exc,
        )

    try:
        document_compliance_service.run_submission_check(submission.id, user_id=user_id, evidence=evidence)
    except document_compliance_service.DocumentComplianceError as exc:
        current_app.logger.warning(
            'Document compliance check skipped for submission %s: %s',
            submission.id,
            exc.message,
        )
    except Exception as exc:  # pragma: no cover - defensive, intake should survive compliance failures.
        current_app.logger.exception(
            'Document compliance check failed for submission %s: %s',
            submission.id,
            exc,
        )

    # Trigger notification for initial field officer uploads for non-workflow requirements
    # (workflow-managed requirements notify on explicit workflow submit; resubmissions notify via workflow event)
    if source == 'field_upload' and not is_resubmission and not requirement.document_category:
        try:
            from app.services import notification_service
            notification_service.notify_staff_on_field_upload(
                submission_id=submission.id,
                project_requirement_id=requirement.id,
                uploaded_by_user_id=user_id,
            )
        except Exception as exc:  # pragma: no cover - defensive, intake should survive notification failures.
            current_app.logger.exception(
                'Notification creation failed for submission %s: %s',
                submission.id,
                exc,
            )

    user_role = access_service.get_user_role(user_id) if user_id else None
    return _serialize_submission(submission, user_role=user_role)


def list_requirement_submissions(requirement_id, user_id=None):
    requirement = _get_requirement_with_access(requirement_id, user_id=user_id)
    user_role = access_service.get_user_role(user_id) if user_id else None
    submissions = (
        Submission.query
        .filter_by(project_requirement_id=requirement.id)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
        .all()
    )
    return [_serialize_submission(item, user_role=user_role) for item in submissions]


def get_document_file(file_id, user_id=None):
    document_file = db.session.get(DocumentFile, file_id)
    if not document_file:
        raise SubmissionError('Document file not found.', 404)

    submission = db.session.get(Submission, document_file.submission_id)
    if not submission:
        raise SubmissionError('Submission not found for this file.', 404)

    _get_requirement_with_access(submission.project_requirement_id, user_id=user_id)
    return document_file


def resolve_document_file_path(document_file):
    for candidate in _document_file_path_candidates(document_file):
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if _path_is_allowed_document_file(resolved) and resolved.exists() and resolved.is_file():
            return resolved
    raise SubmissionError('Stored documentary file is not available on disk.', 404)


def assert_documentary_evidence(requirement_id, target_status):
    if target_status not in EVIDENCE_REQUIRED_STATUSES:
        return
    if has_documentary_evidence(requirement_id):
        return
    raise SubmissionError(
        'A documentary intake record with an uploaded file is required before this requirement can move into review or compliance.',
        409,
    )


def has_documentary_evidence(requirement_id):
    return (
        db.session.query(DocumentFile.id)
        .join(Submission, DocumentFile.submission_id == Submission.id)
        .filter(Submission.project_requirement_id == requirement_id)
        .first()
        is not None
    )


def list_handoff_queue(*, search=None, page=1, per_page=20, fiscal_year=None, user_id=None):
    query = (
        ProjectRequirement.query
        .join(Project, ProjectRequirement.project_id == Project.id)
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .join(Program, Project.program_id == Program.id)
        .filter(
            ProjectRequirement.is_active == True,
            ProjectRequirement.status == 'compliant',
            _documentary_evidence_exists_clause(),
        )
    )
    if user_id is not None:
        query = access_service.restrict_project_requirement_query(query, user_id)
    query = apply_requirement_project_fiscal_year(query, fiscal_year)

    order_by = (ProjectRequirement.reviewed_at.desc(), ProjectRequirement.updated_at.desc())
    if search:
        return search_service.search_requirements(
            query,
            search,
            page=page,
            per_page=per_page,
            serialize=_serialize_handoff_item,
            order_by=order_by,
        )

    pagination = query.order_by(*order_by).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return {
        'items': [_serialize_handoff_item(item) for item in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def push_requirement_to_drive(requirement_id, user_id):
    _require_role(user_id, 'admin', 'staff')
    requirement = _get_requirement_with_access(requirement_id, user_id=user_id)
    try:
        access_service.assert_project_requirement_movement_allowed(requirement)
    except access_service.AccessError as exc:
        raise SubmissionError(exc.message, exc.status_code) from exc
    if requirement.status != 'compliant':
        raise SubmissionError('Only compliant requirements can be handed off to Google Drive.', 409)

    submission = _latest_submission(requirement.id)
    if submission is None:
        raise SubmissionError('No documentary evidence is available for this requirement.', 409)

    existing_push = (
        GoogleDrivePush.query
        .filter_by(
            project_requirement_id=requirement.id,
            submission_id=submission.id,
            push_status='completed',
        )
        .order_by(GoogleDrivePush.created_at.desc(), GoogleDrivePush.id.desc())
        .first()
    )
    if existing_push:
        payload = _serialize_drive_push(existing_push)
        payload['already_handed_off'] = True
        return payload

    push_record = GoogleDrivePush(
        project_id=requirement.project_id,
        project_requirement_id=requirement.id,
        submission_id=submission.id,
        pushed_by=user_id,
        push_status='in_progress',
    )
    db.session.add(push_record)
    db.session.flush()

    try:
        payload = drive_service.push_submission(requirement, submission)
        push_record.drive_folder_id = payload['drive_folder_id']
        push_record.drive_folder_url = payload['drive_folder_url']
        push_record.destination_path = payload['destination_path']
        push_record.files_count = payload['files_count']
        push_record.total_size_bytes = payload['total_size_bytes']
        push_record.api_response_metadata = payload['api_response_metadata']
        push_record.push_status = 'completed'
        push_record.error_message = None
    except drive_service.DriveServiceError as exc:
        push_record.push_status = 'failed'
        push_record.error_message = exc.message
        db.session.commit()
        raise SubmissionError(exc.message, exc.status_code) from exc

    db.session.commit()
    audit_service.log_action(
        user_id=user_id,
        action='create',
        entity_type='google_drive_push',
        entity_id=push_record.id,
        old_value=None,
        new_value=_serialize_drive_push(push_record),
    )
    return _serialize_drive_push(push_record)


def _latest_submission(requirement_id):
    return (
        Submission.query
        .filter_by(project_requirement_id=requirement_id)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
        .first()
    )


def _get_requirement_with_access(requirement_id, user_id=None):
    try:
        if user_id is not None:
            return access_service.ensure_project_requirement_access(requirement_id, user_id)
    except access_service.AccessError as exc:
        raise SubmissionError(exc.message, exc.status_code) from exc

    requirement = db.session.get(ProjectRequirement, requirement_id)
    if not requirement:
        raise SubmissionError('Project requirement not found.', 404)
    return requirement


def _require_role(user_id, *roles):
    role = access_service.get_user_role(user_id)
    if role not in roles:
        raise SubmissionError(
            f"Role '{role}' is not authorized for this action. Requires one of: {', '.join(roles)}",
            403,
        )


def _serialize_intake_requirement(requirement, user_role=None):
    project = requirement.project
    lgu = project.lgu if project else None
    program = project.program if project else None
    latest_submission = _latest_submission(requirement.id)
    latest_revision = (requirement.custom_fields or {}).get('latest_revision')
    if user_role == 'field_officer' and isinstance(latest_revision, dict):
        latest_revision = dict(latest_revision)
        latest_revision.pop('stored_object_id', None)
    is_returned = requirement.workflow_status == 'returned_for_revision'
    current_return = None
    if is_returned:
        current_return = {
            'notes': requirement.workflow_return_reason or (latest_revision.get('notes') if latest_revision else ''),
            'returned_at': requirement.workflow_returned_at.isoformat() if requirement.workflow_returned_at else (latest_revision.get('returned_at') if latest_revision else None),
            'returned_by': requirement.workflow_returned_by or (latest_revision.get('returned_by') if latest_revision else None),
            'report_id': latest_revision.get('report_id') if latest_revision else None,
            'report_file_name': latest_revision.get('report_file_name') if latest_revision else None,
            'has_report': bool(latest_revision and (latest_revision.get('report_id') or latest_revision.get('stored_object_id'))),
        }
    return {
        'id': requirement.id,
        'project_id': project.id if project else None,
        'project_name': project.project_name if project else None,
        'source_project_code': project.source_project_code if project else None,
        'fiscal_year': project.fiscal_year if project else None,
        'lgu_id': lgu.id if lgu else None,
        'lgu_name': lgu.name if lgu else None,
        'program_id': program.id if program else None,
        'program_name': program.name if program else None,
        'program_is_active': bool(program.is_active) if program else True,
        'phase_name': requirement.phase_name,
        'requirement_name': requirement.requirement_name,
        'annex_reference': requirement.annex_reference,
        'status': requirement.status,
        'workflow_status': requirement.workflow_status,
        'workflow_return_reason': requirement.workflow_return_reason,
        'workflow_returned_at': requirement.workflow_returned_at.isoformat() if requirement.workflow_returned_at else None,
        'is_returned': is_returned,
        'current_return': current_return,
        'submission_count': requirement.submissions.count(),
        'has_documentary_evidence': has_documentary_evidence(requirement.id),
        'latest_submission': _serialize_submission_summary(latest_submission, user_role=user_role),
        'latest_revision': latest_revision,
        'applicability': getattr(requirement, 'applicability', 'applicable'),
        'applicability_reason': getattr(requirement, 'applicability_reason', None),
    }


def _serialize_handoff_item(requirement):
    project = requirement.project
    lgu = project.lgu if project else None
    program = project.program if project else None
    latest_submission = _latest_submission(requirement.id)
    latest_push = (
        requirement.google_drive_pushes
        .order_by(GoogleDrivePush.created_at.desc(), GoogleDrivePush.id.desc())
        .first()
    )
    return {
        'id': requirement.id,
        'project_id': project.id if project else None,
        'project_name': project.project_name if project else None,
        'lgu_name': lgu.name if lgu else None,
        'program_name': program.name if program else None,
        'requirement_name': requirement.requirement_name,
        'annex_reference': requirement.annex_reference,
        'reviewed_at': requirement.reviewed_at.isoformat() if requirement.reviewed_at else None,
        'latest_submission': _serialize_submission_summary(latest_submission),
        'latest_push': _serialize_drive_push(latest_push) if latest_push else None,
    }


def _serialize_submission_summary(submission, user_role=None):
    if submission is None:
        return None
    primary_file = submission.document_files.order_by(DocumentFile.created_at.desc()).first()
    return {
        'id': submission.id,
        'source': submission.source,
        'description': submission.description,
        'created_at': submission.created_at.isoformat() if submission.created_at else None,
        'document_count': submission.document_files.count(),
        'primary_file_id': primary_file.id if primary_file else None,
        'primary_file_name': primary_file.file_name if primary_file else None,
        'primary_file_mime_type': primary_file.mime_type if primary_file else None,
        'primary_file_size_bytes': primary_file.file_size_bytes if primary_file else None,
        'latest_nlp_scan': None if user_role == 'field_officer' else document_intelligence_service.latest_scan_summary(submission),
        'latest_compliance_result': None if user_role == 'field_officer' else document_compliance_service.latest_result_summary(submission),
    }


def _serialize_submission(submission, user_role=None):
    files = submission.document_files.order_by(DocumentFile.created_at.asc()).all()
    if user_role == 'field_officer':
        scans = []
        compliance_results = []
    else:
        scans = (
            submission.nlp_results
            .order_by(NlpScanResult.scanned_at.desc(), NlpScanResult.id.desc())
            .all()
        )
        compliance_results = (
            submission.compliance_results
            .order_by(DocumentComplianceResult.created_at.desc(), DocumentComplianceResult.id.desc())
            .all()
        )
    return {
        'id': submission.id,
        'project_id': submission.project_requirement.project_id if getattr(submission, 'project_requirement', None) else None,
        'project_requirement_id': submission.project_requirement_id,
        'uploaded_by': submission.uploaded_by,
        'description': submission.description,
        'source': submission.source,
        'current_version': submission.current_version,
        'version_number': submission.current_version,
        'created_at': submission.created_at.isoformat() if submission.created_at else None,
        'updated_at': submission.updated_at.isoformat() if submission.updated_at else None,
        'document_files': [
            {
                'id': document_file.id,
                'file_name': document_file.file_name,
                'file_size_bytes': document_file.file_size_bytes,
                'mime_type': document_file.mime_type,
                'download_url': f'/api/projects/files/{document_file.id}/download',
                'created_at': document_file.created_at.isoformat() if document_file.created_at else None,
            }
            for document_file in files
        ],
        'nlp_scan_results': (
            [] if user_role == 'field_officer'
            else [document_intelligence_service.serialize_scan_result(scan) for scan in scans]
        ),
        'compliance_results': (
            [] if user_role == 'field_officer'
            else [document_compliance_service.serialize_compliance_result(result) for result in compliance_results]
        ),
        'latest_compliance_result': (
            None if user_role == 'field_officer'
            else (document_compliance_service.serialize_compliance_result(compliance_results[0]) if compliance_results else None)
        ),
    }


def _requirement_status_audit_payload(requirement):
    return {
        'id': requirement.id,
        'project_id': requirement.project_id,
        'requirement_name': requirement.requirement_name,
        'status': requirement.status,
        'reviewed_at': requirement.reviewed_at.isoformat() if requirement.reviewed_at else None,
        'last_action_by': requirement.last_action_by,
        'updated_at': requirement.updated_at.isoformat() if requirement.updated_at else None,
    }


def _serialize_drive_push(push_record):
    if push_record is None:
        return None
    return {
        'id': push_record.id,
        'project_id': push_record.project_id,
        'project_requirement_id': push_record.project_requirement_id,
        'submission_id': push_record.submission_id,
        'drive_folder_id': push_record.drive_folder_id,
        'drive_folder_url': push_record.drive_folder_url,
        'destination_path': push_record.destination_path,
        'files_count': push_record.files_count,
        'total_size_bytes': push_record.total_size_bytes,
        'push_status': push_record.push_status,
        'error_message': push_record.error_message,
        'created_at': push_record.created_at.isoformat() if push_record.created_at else None,
        'pushed_at': push_record.pushed_at.isoformat() if push_record.pushed_at else None,
    }


def _submission_root():
    configured = current_app.config.get('SUBMISSION_UPLOAD_DIR')
    if configured:
        root = Path(configured)
    else:
        root = Path(current_app.root_path).parent / 'uploads' / 'submissions'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _document_file_path_candidates(document_file):
    path_value = str(document_file.file_path or '').strip()
    if not path_value:
        return []

    names = []
    for name in (Path(path_value).name, PureWindowsPath(path_value).name):
        if name and name not in names:
            names.append(name)

    candidates = [Path(path_value)]
    for name in names:
        for root in _document_file_allowed_roots():
            candidates.append(root / str(document_file.submission_id) / name)

    parts = _portable_path_parts(path_value)
    for marker in ('demo_submissions', 'uploads'):
        if marker not in parts:
            continue
        marker_index = parts.index(marker)
        suffix = parts[marker_index:]
        if marker == 'demo_submissions':
            candidates.extend([
                Path(current_app.instance_path).joinpath(*suffix),
                Path(current_app.root_path).parent.joinpath('instance', *suffix),
            ])
        elif len(suffix) >= 2 and suffix[1] == 'submissions':
            candidates.extend([
                Path(current_app.root_path).parent.joinpath(*suffix),
                Path(current_app.instance_path).joinpath(*suffix),
            ])

    unique = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _portable_path_parts(path_value):
    normalized = str(path_value or '').replace('\\', '/')
    return [part for part in normalized.split('/') if part and part not in ('.', '..')]


def _path_is_allowed_document_file(path):
    for root in _document_file_allowed_roots():
        try:
            path.relative_to(root.resolve(strict=False))
            return True
        except (OSError, RuntimeError, ValueError):
            continue
    return False


def _document_file_allowed_roots():
    return _unique_paths([
        _submission_root(),
        Path(current_app.instance_path) / 'demo_submissions',
        Path(current_app.instance_path) / 'uploads' / 'submissions',
        Path(current_app.root_path).parent / 'instance' / 'demo_submissions',
        Path(current_app.root_path).parent / 'instance' / 'uploads' / 'submissions',
        Path(current_app.root_path).parent / 'uploads' / 'submissions',
    ])


def _unique_paths(paths):
    unique = []
    seen = set()
    for path in paths:
        key = str(Path(path))
        if key not in seen:
            seen.add(key)
            unique.append(Path(path))
    return unique


def _documentary_evidence_exists_clause():
    return (
        db.session.query(DocumentFile.id)
        .join(Submission, DocumentFile.submission_id == Submission.id)
        .filter(Submission.project_requirement_id == ProjectRequirement.id)
        .exists()
    )


def _validate_upload_constraints(filename, upload):
    extension = Path(filename).suffix.lower().lstrip('.')
    allowed_extensions = set(current_app.config.get('SUBMISSION_ALLOWED_EXTENSIONS') or ())
    if not extension or extension not in allowed_extensions:
        allowed = ', '.join(sorted(allowed_extensions))
        raise SubmissionError(f'Unsupported file type for documentary intake. Allowed extensions: {allowed}.', 422)

    mime_type = resolve_upload_mime_type(
        filename,
        upload,
        current_app.config.get('SUBMISSION_ALLOWED_MIME_TYPES') or (),
        lambda message: SubmissionError(message, 422),
        label='Documentary intake file',
    )

    size_bytes = _measure_upload_size(upload)
    max_size_bytes = int(current_app.config.get('MAX_SUBMISSION_FILE_BYTES') or 0)
    if max_size_bytes and size_bytes > max_size_bytes:
        raise SubmissionError(
            f'Documentary intake files must be {max_size_bytes // (1024 * 1024)} MB or smaller.',
            422,
        )

    return mime_type


def _measure_upload_size(upload):
    content_length = getattr(upload, 'content_length', None)
    if content_length is not None and int(content_length) > 0:
        return int(content_length)

    stream = getattr(upload, 'stream', None)
    if stream is None:
        return 0

    position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size_bytes = stream.tell()
    stream.seek(position)
    return int(size_bytes)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
