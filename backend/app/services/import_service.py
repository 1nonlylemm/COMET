import hashlib
import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    ImportBatch,
    ImportMappingDecision,
    ImportRow,
    ImportTemplate,
    LguProfile,
    Program,
    ProgramCycle,
    ProgramPhase,
    Project,
    ProjectRequirement,
    Requirement,
)
from app.services import audit_service, object_storage_service, project_service
from app.services.import_field_catalog import normalize_label
from app.services.import_mapping_service import build_mapping, is_project_sheet, normalize_requirement_status
from app.services.project_status import normalize_project_status
from app.services.requirement_matching_service import (
    RequirementMatchContext,
    find_requirement_candidates,
    find_requirement_match,
    standardize_requirement_name,
)
from app.services.import_schema_diff_service import diff_profile_against_template
from app.services.workbook_profile_service import WorkbookProfileError, extract_rows, profile_workbook
from app.services.upload_validation import ArchiveSecurityError, validate_ooxml_container, validate_upload_filename


class ImportError(Exception):
    def __init__(self, message, status_code=400, errors=None):
        self.message = message
        self.status_code = status_code
        self.errors = errors


ALLOWED_FILE_TYPES = {'csv', 'xlsx'}
PROFILE_CACHE_VERSION = 2
SCHEMA_SIGNATURE_RE = re.compile(r'^[a-f0-9]{64}$')
PROJECT_FIELDS = {
    'project.source_project_code',
    'project.project_name',
    'project.budget_amount',
    'project.location',
    'project.target_beneficiaries',
    'project.mode_of_implementation',
    'project.implementation_period',
    'project.overall_status',
    'program_cycle.fiscal_year',
    'lgu.province',
    'lgu.name',
    'lgu.municipality',
    'lgu.level',
}
MAPPING_CLASSIFICATIONS = {'project_field', 'lgu_field', 'cycle_field', 'requirement', 'context', 'ignored', 'calculated'}
ROW_KEY_LIMIT = 255
SOURCE_PROJECT_CODE_LIMIT = 120
SOURCE_PROJECT_CODE_RE = re.compile(r'\b(?:FA|G3P|SAFPB|FALGU|LGSF)[A-Z0-9-]{4,}\b', re.IGNORECASE)
REQUIREMENT_RESOLUTION_FIELDS = (
    'resolution',
    'matched_requirement_id',
    'matched_requirement_name',
    'matched_phase_name',
    'canonical_name',
    'resolution_reason',
    'recommended_action',
    'similar_candidates',
)


class _ImportPreviewContext:
    def __init__(self, batch):
        self.batch = batch
        self.program_id = batch.program_id
        self.requirement_match_context = RequirementMatchContext(batch.program_id)
        self.requirement_resolution_cache = {}
        self.lgu_candidates = None
        self.lgu_match_cache = {}
        self.project_lookup_cache = {}


def upload_workbook(program_id, upload, program_cycle_id=None, import_template_id=None, user_id=None):
    if upload is None or not upload.filename:
        raise ImportError('Workbook file is required.', 422)

    program = db.session.get(Program, program_id)
    if not program:
        raise ImportError('Program not found.', 404)
    if not program.is_active:
        raise ImportError('Cannot upload workbook to an inactive program.', 422)

    cycle = _get_cycle(program_id, program_cycle_id)
    template = _get_template(program_id, import_template_id, program_cycle_id=program_cycle_id)
    file_type = _file_type(upload.filename)
    with object_storage_service.storage_transaction() as storage_tx:
        stored_path, file_hash, stored_object = _store_upload(upload, user_id=user_id, tracker=storage_tx)
        try:
            profile = _mark_profile_current(profile_workbook(stored_path, file_type=file_type), file_hash)
        except WorkbookProfileError as exc:
            raise ImportError(exc.message, exc.status_code) from exc

        batch = ImportBatch(
            program_id=program_id,
            program_cycle_id=cycle.id if cycle else None,
            import_template_id=template.id if template else None,
            uploaded_by=user_id,
            original_file_name=upload.filename,
            stored_file_path=str(stored_path),
            stored_object_id=stored_object.id if stored_object else None,
            file_hash=file_hash,
            file_type=file_type,
            status='profiled',
            workbook_profile=profile,
        )
        db.session.add(batch)
        db.session.commit()
        storage_tx.commit()

    _audit(user_id, 'upload', 'import_batch', batch.id, None, _serialize_batch(batch, include_profile=False))
    return _serialize_batch(batch)


def get_import_batch(batch_id):
    batch = db.session.get(ImportBatch, batch_id)
    if not batch:
        raise ImportError('Import batch not found.', 404)
    return _serialize_batch(batch)


def list_import_batches(program_id=None, program_cycle_id=None, fiscal_year=None, status=None, page=1, per_page=20):
    query = ImportBatch.query
    if program_id is not None:
        query = query.filter_by(program_id=program_id)
    if program_cycle_id is not None:
        query = query.filter_by(program_cycle_id=program_cycle_id)
    if fiscal_year is not None:
        query = query.filter(ImportBatch.program_cycle.has(ProgramCycle.fiscal_year == fiscal_year))
    if status is not None:
        query = query.filter(ImportBatch.status == status)
    pagination = query.order_by(ImportBatch.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return {
        'items': [_serialize_batch(item, include_profile=False) for item in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def map_workbook(batch_id, overrides=None, user_id=None):
    batch = _get_batch(batch_id, for_update=True)
    _ensure_batch_not_committed(batch)
    _refresh_workbook_profile(batch)
    template = batch.import_template
    mapping = build_mapping(batch.workbook_profile or {}, template=template)
    if overrides:
        mapping = _apply_mapping_overrides(mapping, overrides)
    mapping = _prepare_mapping_decision_workshop(batch, mapping)
    batch.mapping_preview = mapping
    _invalidate_preview(batch)
    batch.status = 'mapped'
    db.session.commit()
    _audit(user_id, 'map', 'import_batch', batch.id, None, {'field_mappings': len(mapping.get('field_mappings', []))})
    return mapping


def _invalidate_preview(batch):
    batch.preview_summary = {}
    ImportRow.query.filter_by(import_batch_id=batch.id).delete()


def select_import_template(batch_id, template_id, user_id=None):
    """Apply an existing compatible template and require a fresh preview."""
    batch = _get_batch(batch_id, for_update=True)
    _ensure_batch_not_committed(batch)
    template = _get_template(batch.program_id, template_id, program_cycle_id=batch.program_cycle_id)
    if not template or not template.is_active or template.status not in ('draft', 'active'):
        raise ImportError('Choose an active or draft import template.', 422)
    if template.program_cycle_id not in (None, batch.program_cycle_id):
        raise ImportError('Import template belongs to a different program cycle.', 422)
    if template.file_type != batch.file_type:
        raise ImportError('Import template file type does not match this workbook.', 422)
    before = batch.import_template_id
    batch.import_template = template
    batch.import_template_id = template.id
    batch.mapping_preview = {}
    mapping = map_workbook(batch.id, user_id=user_id)
    _audit(user_id, 'select_import_template', 'import_batch', batch.id,
           {'import_template_id': before}, {'import_template_id': template.id})
    return {'batch_id': batch.id, 'import_template_id': template.id, 'mapping': mapping}


def workbook_preview_fingerprint(batch):
    """Hash the reviewed source, mapping, rows and affected record context.

    Recomputed under the batch lock at commit. No writes or preview regeneration
    take place here, so confirmation cannot silently approve different rows.
    """
    try:
        with open(batch.stored_file_path, 'rb') as source:
            source_hash = hashlib.file_digest(source, 'sha256').hexdigest()
    except OSError as exc:
        raise ImportError('Stored import file is no longer available. Upload and preview again.', 422) from exc
    if source_hash != batch.file_hash:
        raise ImportError('The source file has changed since the preview. Upload and preview again.', 422)
    rows = ImportRow.query.filter_by(import_batch_id=batch.id).order_by(ImportRow.sheet_name, ImportRow.row_number).all()
    context = _ImportPreviewContext(batch)
    targets = []
    for row in rows:
        mapped = row.mapped_data or {}
        project = _find_existing_project(batch, mapped, context=context)
        targets.append({
            'project': project_service._serialize_project(project) if project else None,
            'lgus': [(lgu.id, lgu.name, lgu.municipality, lgu.province, lgu.is_active)
                     for lgu in _match_lgus(mapped.get('lgu') or {}, context=context)],
        })
    requirements = Requirement.query.join(ProgramPhase).filter(ProgramPhase.program_id == batch.program_id).order_by(Requirement.id).all()
    payload = {
        'batch_id': batch.id, 'program_id': batch.program_id, 'cycle_id': batch.program_cycle_id,
        'template_id': batch.import_template_id, 'file_hash': source_hash, 'file_type': batch.file_type,
        'mapping': batch.mapping_preview, 'profile': batch.workbook_profile, 'summary': batch.preview_summary,
        'rows': [_serialize_import_row(row) for row in rows], 'targets': targets,
        'program_active': batch.program.is_active,
        'program_schema': batch.program.project_custom_field_schema,
        'cycle': {'id': batch.program_cycle_id, 'fiscal_year': batch.program_cycle.fiscal_year,
                  'active': batch.program_cycle.is_active, 'import_profile': batch.program_cycle.import_profile,
                  'field_schema': batch.program_cycle.field_schema} if batch.program_cycle_id else None,
        'template': _serialize_template(batch.import_template) if batch.import_template else None,
        'requirements': [{column.name: getattr(req, column.name) for column in Requirement.__table__.columns} for req in requirements],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def schema_diff(batch_id, template_id):
    batch = _get_batch(batch_id)
    template = db.session.get(ImportTemplate, template_id)
    if not template:
        raise ImportError('Import template not found.', 404)
    if template.program_id != batch.program_id:
        raise ImportError('Import template does not belong to this program.', 422)
    return diff_profile_against_template(batch.workbook_profile or {}, template)


def get_mapping_workshop(batch_id):
    batch = _get_batch(batch_id, for_update=True)
    _refresh_workbook_profile(batch)
    mapping = _mapping_for_current_profile(batch, batch.mapping_preview)
    mapping = _prepare_mapping_decision_workshop(batch, mapping)
    batch.mapping_preview = mapping
    db.session.commit()
    return {
        'batch_id': batch.id,
        'schema_signature': mapping.get('schema_signature'),
        'field_mappings': mapping.get('field_mappings') or [],
        'decisions': mapping.get('mapping_decisions') or [],
    }


def save_mapping_decisions(batch_id, decisions, user_id=None):
    batch = _get_batch(batch_id, for_update=True)
    _ensure_batch_not_committed(batch)
    _refresh_workbook_profile(batch)
    if not isinstance(decisions, list):
        raise ImportError('Mapping decisions must be a list.', 422)

    mapping = _mapping_for_current_profile(batch, batch.mapping_preview)
    mapping = _prepare_mapping_decision_workshop(batch, mapping)
    by_key = {
        _mapping_source_key(item): item
        for item in mapping.get('field_mappings', [])
        if _mapping_source_key(item)
    }
    # Validate the whole request before persisting any decisions.
    prepared = []
    seen = set()
    for payload in decisions:
        if not isinstance(payload, dict):
            raise ImportError('Each mapping decision must be an object.', 422)
        key = _mapping_source_key(payload)
        item = by_key.get(key)
        if not item:
            raise ImportError('Mapping decision must reference an existing source sheet and column.', 422)
        if key in seen:
            raise ImportError('A source column cannot have multiple decisions in one request.', 422)
        seen.add(key)
        merged = _merge_admin_decision(item, payload)
        prepared.append((key, merged))
    saved = []
    for key, merged in prepared:
        decision = _persist_mapping_decision(batch, merged, user_id=user_id)
        merged['mapping_decision_id'] = decision.id
        merged['decision_source'] = 'confirmed'
        merged['requires_confirmation'] = False
        by_key[key] = merged
        saved.append(_serialize_mapping_decision(decision))

    mapping['field_mappings'] = list(by_key.values())
    mapping['mapping_decisions'] = [_mapping_item_to_decision(item) for item in mapping['field_mappings']]
    batch.mapping_preview = mapping
    _invalidate_preview(batch)
    batch.status = 'mapped'
    db.session.commit()
    _audit(user_id, 'confirm_mapping_decisions', 'import_batch', batch.id, None, {'decisions': len(saved)})
    return {
        'batch_id': batch.id,
        'mapping': mapping,
        'decisions': saved,
    }


def list_mapping_history(program_id=None, program_cycle_id=None, source_header=None, limit=100):
    query = ImportMappingDecision.query.filter_by(status='active')
    if program_id is not None:
        query = query.filter_by(program_id=program_id)
    if program_cycle_id is not None:
        query = query.filter_by(program_cycle_id=program_cycle_id)
    if source_header:
        query = query.filter(ImportMappingDecision.normalized_source_header == normalize_label(source_header))
    return [
        _serialize_mapping_decision(item)
        for item in query.order_by(ImportMappingDecision.updated_at.desc(), ImportMappingDecision.id.desc()).limit(min(limit or 100, 500)).all()
    ]


def preview_workbook(batch_id, mapping_payload=None, user_id=None):
    batch = _get_batch(batch_id, for_update=True)
    _ensure_batch_not_committed(batch)
    _refresh_workbook_profile(batch)
    mapping = _mapping_for_current_profile(batch, mapping_payload)
    context = _ImportPreviewContext(batch)

    profile = batch.workbook_profile or {}
    preview_profile = {
        **profile,
        'sheets': [sheet for sheet in profile.get('sheets', []) if is_project_sheet(sheet)],
    }
    if not preview_profile['sheets']:
        raise ImportError('No project sheets were recognized. Review the project-name, LGU and allocation headers before importing.', 422)
    try:
        rows = extract_rows(batch.stored_file_path, preview_profile)
    except WorkbookProfileError as exc:
        raise ImportError(exc.message, exc.status_code) from exc
    if not rows:
        raise ImportError('No project data rows were found. Add project rows before previewing this workbook.', 422)
    ImportRow.query.filter_by(import_batch_id=batch.id).delete()
    mapped_rows = []
    summary = {
        'projects': {'new': 0, 'updates': 0, 'skipped': 0, 'invalid': 0},
        'lgus': {'matched': 0, 'new': 0, 'ambiguous': 0},
        'requirements': {
            'detected': 0,
            'matched_existing': 0,
            'matched_imported': 0,
            'new_imported': 0,
            'similar_warnings': 0,
            'review_items': [],
        },
        'rows': [],
    }

    for row in rows:
        sheet = _profile_sheet(profile, row['sheet_name'])
        if sheet and not is_project_sheet(sheet):
            continue
        mapped = _map_row(row, mapping)
        _annotate_requirement_resolutions(batch.program_id, mapped, context=context)
        if not _has_project_signal(mapped):
            continue
        action, errors, lgu_resolution = _classify_row(batch, mapped, context=context)
        summary['projects'][_summary_key(action)] += 1
        if lgu_resolution:
            summary['lgus'][lgu_resolution] += 1
        _summarize_requirement_resolutions(summary['requirements'], mapped.get('requirements') or [])

        import_row = ImportRow(
            import_batch_id=batch.id,
            sheet_name=row['sheet_name'],
            row_number=row['row_number'],
            row_key=mapped.get('row_key'),
            raw_data=row['values'],
            mapped_data=mapped,
            validation_errors=errors,
            action=action,
        )
        db.session.add(import_row)
        mapped_rows.append(import_row)
        summary['rows'].append({
            'sheet': row['sheet_name'],
            'row_number': row['row_number'],
            'action': action,
            'errors': errors,
            'project_name': mapped.get('project', {}).get('project_name'),
            'source_project_code': mapped.get('project', {}).get('source_project_code'),
            'lgu_name': mapped.get('lgu', {}).get('name') or mapped.get('lgu', {}).get('municipality'),
        })

    review_items = _similar_requirement_warnings_for_rows(batch.program_id, mapped_rows, context=context)
    summary['requirements']['review_items'] = review_items
    summary['requirements']['similar_warnings'] = len(review_items)
    batch.mapping_preview = mapping
    batch.preview_summary = summary
    batch.status = 'previewed'
    db.session.commit()
    _audit(user_id, 'preview', 'import_batch', batch.id, None, summary)
    return {
        'summary': summary,
        'rows': [_serialize_import_row(row) for row in mapped_rows[:200]],
    }


def commit_workbook(batch_id, user_id=None, confirm_similar_requirements=False, expected_preview_fingerprint=None):
    # Lock the import batch to serialize concurrent commits on the same batch
    batch = ImportBatch.query.filter_by(id=batch_id).with_for_update().first()
    if not batch:
        raise ImportError('Import batch not found.', 404)
    if batch.status == 'committed':
        raise ImportError('This import batch has already been committed.', 409)
    if batch.status != 'previewed':
        raise ImportError('Preview the workbook before committing it.', 422)
    if expected_preview_fingerprint is not None and workbook_preview_fingerprint(batch) != expected_preview_fingerprint:
        raise ImportError('The import changed after preview. Generate and review a new preview before committing.', 409)
    if not batch.program.is_active:
        raise ImportError('Cannot commit workbook for an inactive program.', 422)

    rows = ImportRow.query.filter_by(import_batch_id=batch.id).order_by(ImportRow.row_number).all()
    blocking = [row for row in rows if row.action == 'error']
    if blocking:
        raise ImportError('Fix invalid import rows before committing.', 422)
    similar_warnings = _similar_requirement_warnings_for_rows(batch.program_id, rows)
    if similar_warnings and not confirm_similar_requirements:
        raise ImportError(
            'Some imported requirement columns look similar to existing requirements. Review and confirm before creating new imported requirements.',
            409,
            errors={'requirement_warnings': similar_warnings},
        )
    _validate_imported_non_compliant_statuses(batch, rows)

    try:
        committed = {'created_projects': 0, 'updated_projects': 0, 'requirements': 0, 'skipped': 0}
        for row in rows:
            if row.action == 'skip':
                committed['skipped'] += 1
                continue
            project = _commit_project_row(batch, row, user_id=user_id)
            if row.action == 'create_project':
                committed['created_projects'] += 1
            elif row.action == 'update_project':
                committed['updated_projects'] += 1
            _annotate_requirement_resolutions(batch.program_id, row.mapped_data)
            committed['requirements'] += _commit_requirements(batch, project, row.mapped_data.get('requirements') or [])
            row.committed_entity_type = 'project'
            row.committed_entity_id = project.id

        template = _ensure_template_from_batch(batch, user_id=user_id)
        committed['import_template_id'] = template.id if template else batch.import_template_id

        from app.services import workbook_workspace_service
        workspace = workbook_workspace_service.create_or_update_workspace_from_batch(batch.id, user_id=user_id, commit=False)
        if workspace:
            committed['workbook_workspace_id'] = workspace.id

        batch.status = 'committed'
        batch.committed_at = datetime.now(timezone.utc)
        db.session.flush()

        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='commit',
                entity_type='import_batch',
                entity_id=batch.id,
                old_value=None,
                new_value=committed,
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        'batch': _serialize_batch(batch, include_profile=False),
        'committed': committed,
    }


def list_import_templates(program_id=None, program_cycle_id=None, fiscal_year=None):
    query = ImportTemplate.query
    if program_id is not None:
        query = query.filter_by(program_id=program_id)
    if program_cycle_id is not None:
        query = query.filter_by(program_cycle_id=program_cycle_id)
    if fiscal_year is not None:
        query = query.filter(ImportTemplate.program_cycle.has(ProgramCycle.fiscal_year == fiscal_year))
    return [_serialize_template(item) for item in query.order_by(ImportTemplate.created_at.desc()).all()]


def create_import_template(data, user_id=None):
    program = db.session.get(Program, data.get('program_id'))
    if not program:
        raise ImportError('Program not found.', 404)
    if data.get('program_cycle_id'):
        _get_cycle(program.id, data.get('program_cycle_id'))
    file_type = data.get('file_type', 'xlsx')
    if file_type not in ALLOWED_FILE_TYPES:
        raise ImportError('Unsupported template file type.', 422)
    template = ImportTemplate(
        program_id=program.id,
        program_cycle_id=data.get('program_cycle_id'),
        name=data.get('name') or 'Workbook Import Template',
        file_type=file_type,
        status=data.get('status', 'draft'),
        schema_signature=data.get('schema_signature'),
        sheet_mappings=data.get('sheet_mappings') or {},
        column_mappings=data.get('column_mappings') or {},
        transform_rules=data.get('transform_rules') or {},
        created_by=user_id,
    )
    db.session.add(template)
    return _save_template_with_audit(template, user_id, 'create', None)


def update_import_template(template_id, data, user_id=None):
    template = db.session.get(ImportTemplate, template_id)
    if not template:
        raise ImportError('Import template not found.', 404)
    if template.locked_at and any(key in data for key in ['sheet_mappings', 'column_mappings', 'transform_rules']):
        raise ImportError('Locked templates cannot be edited in place. Clone the template first.', 409)
    before = _serialize_template(template)
    for field in ['name', 'status', 'schema_signature']:
        if field in data:
            setattr(template, field, data[field])
    for field in ['sheet_mappings', 'column_mappings', 'transform_rules']:
        if field in data:
            setattr(template, field, data[field] or {})
    if 'is_active' in data:
        template.is_active = bool(data['is_active'])
    if data.get('lock'):
        template.locked_at = datetime.now(timezone.utc)
        template.status = 'active'
    return _save_template_with_audit(template, user_id, 'update', before)


def clone_import_template(template_id, data=None, user_id=None):
    data = data or {}
    source = db.session.get(ImportTemplate, template_id)
    if not source:
        raise ImportError('Import template not found.', 404)
    target_cycle_id = data.get('program_cycle_id', source.program_cycle_id)
    if target_cycle_id:
        _get_cycle(source.program_id, target_cycle_id)
    clone = ImportTemplate(
        program_id=source.program_id,
        program_cycle_id=target_cycle_id,
        cloned_from_template_id=source.id,
        name=data.get('name') or f'{source.name} Copy',
        file_type=source.file_type,
        version_number=1,
        status='draft',
        schema_signature=source.schema_signature,
        sheet_mappings=source.sheet_mappings or {},
        column_mappings=source.column_mappings or {},
        transform_rules=source.transform_rules or {},
        created_by=user_id,
    )
    db.session.add(clone)
    return _save_template_with_audit(clone, user_id, 'clone', {'source_template_id': source.id})


def _save_template_with_audit(template, user_id, action, before):
    try:
        db.session.flush()
        result = _serialize_template(template)
        _audit(user_id, action, 'import_template', template.id, before, result, commit=False)
        db.session.commit()
        return result
    except Exception:
        db.session.rollback()
        raise


def _commit_project_row(batch, row, user_id=None):
    mapped = row.mapped_data or {}
    project_data = mapped.get('project') or {}
    lgu_data = mapped.get('lgu') or {}
    lgu = _get_or_create_lgu(lgu_data)
    custom_fields = {
        key: value for key, value in project_data.items()
        if key in {'location', 'target_beneficiaries', 'mode_of_implementation', 'implementation_period'}
        and value not in (None, '')
    }
    custom_fields.update(mapped.get('custom_fields') or {})
    existing = _find_existing_project(batch, mapped)
    if existing:
        payload = {
            'lgu_id': lgu.id,
            'project_name': project_data.get('project_name') or existing.project_name,
            'budget_amount': project_data.get('budget_amount'),
            'overall_status': project_data.get('overall_status') or existing.overall_status,
            'custom_fields': {**(existing.custom_fields or {}), **custom_fields},
            'source_project_code': project_data.get('source_project_code') or existing.source_project_code,
            'source_row_key': mapped.get('row_key') or existing.source_row_key,
            'source_sheet_name': row.sheet_name,
        }
        return project_service.update_project(
            existing.id,
            payload,
            user_id=user_id,
            enforce_workbook_locks=False,
            sync_workbook=False,
        )

    try:
        return project_service.create_project(
            lgu_id=lgu.id,
            program_id=batch.program_id,
            program_cycle_id=batch.program_cycle_id,
            project_name=project_data.get('project_name'),
            fiscal_year=_project_fiscal_year(batch, mapped),
            source_project_code=project_data.get('source_project_code'),
            source_row_key=mapped.get('row_key'),
            source_sheet_name=row.sheet_name,
            budget_amount=project_data.get('budget_amount'),
            overall_status=project_data.get('overall_status') or 'not_yet_started',
            custom_fields=custom_fields,
            user_id=user_id,
        )
    except project_service.ProjectError as exc:
        raise ImportError(exc.message, exc.status_code) from exc


def _commit_requirements(batch, project, requirements):
    if not requirements:
        return 0
    imported_phase = None
    committed = 0
    for item in requirements:
        name = item.get('name')
        if not name:
            continue
        requirement = find_requirement_match(batch.program_id, name)
        if requirement:
            project_requirement = _find_project_requirement_for_requirement(project.id, requirement)
            if not project_requirement:
                project_requirement = _create_project_requirement_from_requirement(project, requirement, item)
                db.session.add(project_requirement)
        else:
            project_requirement = _find_project_requirement_by_name(project.id, name)
            if project_requirement:
                requirement = project_requirement.requirement
            else:
                standardized_name = standardize_requirement_name(name)
                if imported_phase is None:
                    imported_phase = _get_or_create_imported_phase(batch.program_id)
                requirement = _get_or_create_imported_requirement(imported_phase, standardized_name, batch=batch, item=item)
                project_requirement = ProjectRequirement.query.filter_by(
                    project_id=project.id,
                    requirement_id=requirement.id,
                ).first()
            if not project_requirement:
                project_requirement = ProjectRequirement(
                    project_id=project.id,
                    requirement_id=requirement.id,
                    requirement_name=requirement.name,
                    requirement_type=requirement.requirement_type,
                    annex_reference=requirement.annex_reference,
                    is_mandatory=bool(item.get('is_mandatory')),
                    phase_name=imported_phase.name if imported_phase else (requirement.phase.name if requirement.phase else None),
                    status='pending',
                    sort_order=project.project_requirements.count() + 1,
                    custom_fields={},
                )
                db.session.add(project_requirement)

        _apply_imported_requirement_status(project_requirement, item)
        project_requirement.custom_fields = _merge_imported_requirement_fields(
            project_requirement,
            imported_name=name,
            source_column=item.get('source_column'),
            source_header=item.get('source_header'),
            source_sheet=item.get('source_sheet'),
            canonical_label=item.get('canonical_label'),
            raw_value=item.get('raw_value'),
            mapping_decision_id=item.get('mapping_decision_id'),
            value_mapping_mode=item.get('value_mapping_mode'),
        )
        committed += 1
    return committed


def _get_or_create_imported_requirement(phase, name, batch=None, item=None):
    standardized_name = standardize_requirement_name(name)
    query = Requirement.query.filter_by(phase_id=phase.id)
    if batch and batch.program_cycle_id:
        query = query.filter(db.or_(Requirement.program_cycle_id == batch.program_cycle_id, Requirement.program_cycle_id.is_(None)))
    for requirement in query.all():
        if normalize_label(requirement.name) == normalize_label(standardized_name):
            return requirement
    requirement = None
    if not requirement:
        item = item or {}
        requirement = Requirement(
            phase_id=phase.id,
            program_cycle_id=batch.program_cycle_id if batch else None,
            created_from_mapping_decision_id=item.get('mapping_decision_id'),
            name=standardized_name,
            requirement_type=item.get('requirement_type') or 'document',
            sort_order=phase.requirements.count() + 1,
            is_mandatory=bool(item.get('is_mandatory')),
            source_label=item.get('source_header'),
            source_sheet_name=item.get('source_sheet'),
            source_column=item.get('source_column'),
            custom_field_schema={
                'import_mapping': {
                    'canonical_label': item.get('canonical_label') or standardized_name,
                    'source_header': item.get('source_header'),
                    'source_sheet': item.get('source_sheet'),
                    'source_column': item.get('source_column'),
                    'mapping_decision_id': item.get('mapping_decision_id'),
                },
            },
        )
        db.session.add(requirement)
        db.session.flush()
    return requirement


def _find_project_requirement_for_requirement(project_id, requirement):
    project_requirement = ProjectRequirement.query.filter_by(
        project_id=project_id,
        requirement_id=requirement.id,
    ).first()
    if project_requirement:
        return project_requirement

    normalized_name = normalize_label(requirement.name)
    candidates = ProjectRequirement.query.filter_by(project_id=project_id).all()
    for candidate in candidates:
        if normalize_label(candidate.requirement_name) == normalized_name:
            return candidate
    return None


def _find_project_requirement_by_name(project_id, name):
    normalized_names = {normalize_label(name), normalize_label(standardize_requirement_name(name))}
    candidates = ProjectRequirement.query.filter_by(project_id=project_id).all()
    for candidate in candidates:
        if normalize_label(candidate.requirement_name) in normalized_names:
            return candidate
        custom_fields = candidate.custom_fields or {}
        if normalize_label(custom_fields.get('imported_requirement_name')) in normalized_names:
            return candidate
    return None


def _create_project_requirement_from_requirement(project, requirement, item):
    return ProjectRequirement(
        project_id=project.id,
        requirement_id=requirement.id,
        requirement_name=requirement.name,
        requirement_type=requirement.requirement_type,
        annex_reference=requirement.annex_reference,
        is_mandatory=requirement.is_mandatory,
        has_sla=requirement.has_sla,
        sla_days=requirement.sla_days,
        phase_name=requirement.phase.name if requirement.phase else None,
        status='pending',
        sort_order=project.project_requirements.count() + 1,
        custom_fields={},
    )


def _apply_imported_requirement_status(project_requirement, item):
    target_status = item.get('status')
    if not target_status:
        return
    if project_requirement.id is None:
        db.session.flush()
    if target_status == 'non_compliant':
        try:
            project_service.assert_requirement_can_be_non_compliant(project_requirement.id, status_code=422)
        except project_service.ProjectError as exc:
            raise ImportError(exc.message, exc.status_code) from exc
    project_requirement.status = target_status


def _validate_imported_non_compliant_statuses(batch, rows):
    errors = []
    for row in rows:
        if row.action == 'skip':
            continue
        mapped = row.mapped_data or {}
        non_compliant_requirements = [
            item for item in (mapped.get('requirements') or [])
            if item.get('status') == 'non_compliant'
        ]
        if not non_compliant_requirements:
            continue

        _annotate_requirement_resolutions(batch.program_id, mapped)
        project = _find_existing_project(batch, mapped)
        for item in non_compliant_requirements:
            project_requirement = _find_existing_import_project_requirement(batch, project, item) if project else None
            if not project_requirement or not project_service.requirement_has_overdue_deadline(project_requirement.id):
                errors.append({
                    'row_number': row.row_number,
                    'requirement_name': item.get('canonical_name') or item.get('name'),
                    'project_name': (mapped.get('project') or {}).get('project_name'),
                    'reason': project_service.NON_COMPLIANT_REQUIRES_OVERDUE_DEADLINE_MESSAGE,
                })
    if errors:
        raise ImportError(
            'Imported non-compliant requirement statuses require an unresolved overdue working-day deadline.',
            422,
            errors={'non_compliant_requirements': errors},
        )


def _find_existing_import_project_requirement(batch, project, item):
    if not project:
        return None
    matched_requirement_id = item.get('matched_requirement_id')
    if matched_requirement_id:
        existing = ProjectRequirement.query.filter_by(
            project_id=project.id,
            requirement_id=matched_requirement_id,
        ).first()
        if existing:
            return existing
        requirement = db.session.get(Requirement, matched_requirement_id)
        if requirement:
            existing = _find_project_requirement_for_requirement(project.id, requirement)
            if existing:
                return existing

    name = item.get('name')
    if name:
        requirement = find_requirement_match(batch.program_id, name)
        if requirement:
            existing = _find_project_requirement_for_requirement(project.id, requirement)
            if existing:
                return existing
        return _find_project_requirement_by_name(project.id, name)
    return None


def _merge_imported_requirement_fields(project_requirement, imported_name, source_column,
                                       source_header=None, source_sheet=None, canonical_label=None,
                                       raw_value=None, mapping_decision_id=None, value_mapping_mode=None):
    fields = dict(project_requirement.custom_fields or {})
    if source_column:
        fields['imported_source_column'] = source_column
    if source_header:
        fields['imported_source_header'] = source_header
    if source_sheet:
        fields['imported_source_sheet'] = source_sheet
    if canonical_label:
        fields['imported_canonical_label'] = canonical_label
    if raw_value not in (None, ''):
        fields['imported_raw_value'] = raw_value
    if mapping_decision_id:
        fields['import_mapping_decision_id'] = mapping_decision_id
    if value_mapping_mode:
        fields['imported_value_mapping_mode'] = value_mapping_mode
    if imported_name and normalize_label(imported_name) != normalize_label(project_requirement.requirement_name):
        fields['imported_requirement_name'] = imported_name
    return fields


def _ensure_template_from_batch(batch, user_id=None):
    if batch.import_template_id:
        return batch.import_template
    mapping = batch.mapping_preview or {}
    if not mapping.get('field_mappings'):
        return None
    column_mappings = {}
    for item in mapping.get('field_mappings', []):
        source_sheet = item.get('source_sheet')
        source_column = item.get('source_column')
        if not source_sheet or not source_column:
            continue
        column_mappings[f'{source_sheet}::{source_column}'] = {
            'source_sheet': source_sheet,
            'source_column': source_column,
            'source_header': item.get('source_header'),
            'canonical_label': item.get('canonical_label'),
            'classification': item.get('classification'),
            'target_field': item.get('target_field'),
            'suggested_role': item.get('suggested_role'),
            'binding_target': item.get('binding_target'),
            'binding_config': item.get('binding_config') or {},
            'requirement_metadata': item.get('requirement_metadata') or {},
            'value_mapping_rules': item.get('value_mapping_rules') or {},
            'mapping_decision_id': item.get('mapping_decision_id'),
            'column_fingerprint': item.get('column_fingerprint'),
            'confidence': item.get('confidence'),
        }
    template = ImportTemplate(
        program_id=batch.program_id,
        program_cycle_id=batch.program_cycle_id,
        name=f'{Path(batch.original_file_name).stem} Import Template',
        file_type=batch.file_type,
        status='active',
        schema_signature=(batch.workbook_profile or {}).get('schema_signature'),
        sheet_mappings=mapping.get('sheet_mappings') or {},
        column_mappings=column_mappings,
        transform_rules={},
        created_by=user_id,
        locked_at=datetime.now(timezone.utc),
    )
    db.session.add(template)
    db.session.flush()
    batch.import_template_id = template.id
    return template


def _map_row(row, mapping):
    field_by_col = {
        item.get('source_column'): item
        for item in mapping.get('field_mappings', [])
        if item.get('source_sheet') == row['sheet_name']
    }
    project = {}
    project_confidence = {}
    lgu = {}
    custom_fields = {}
    requirements = []
    for column, value in row['values'].items():
        if value in (None, ''):
            continue
        item = field_by_col.get(column)
        if not item:
            continue
        classification = item.get('classification') or _classification_for_mapping(item)
        if classification == 'ignored':
            continue
        target = item.get('target_field')
        if classification == 'requirement':
            requirements.append(_requirement_item_from_mapping(item, column, value))
        elif target == 'program_cycle.fiscal_year':
            project['fiscal_year'] = _as_int(value)
        elif target and target.startswith('project.'):
            field = target.split('.', 1)[1]
            _set_project_field(project, project_confidence, field, _coerce_project_value(target, value), item)
        elif target and target.startswith('lgu.'):
            lgu[target.split('.', 1)[1]] = str(value).strip()
        elif classification == 'context' or item.get('suggested_role'):
            _set_context_field(custom_fields, item, value, row['sheet_name'], column)
    source_code = project.get('source_project_code')
    project_name = project.get('project_name')
    row_key = _safe_row_key(source_code or f"{normalize_label(lgu.get('name') or lgu.get('municipality'))}:{normalize_label(project_name)}")
    return {
        'project': project,
        'lgu': lgu,
        'requirements': requirements,
        'custom_fields': custom_fields,
        'row_key': row_key,
    }


def _requirement_item_from_mapping(item, column, value):
    metadata = item.get('requirement_metadata') or {}
    name = metadata.get('name') or item.get('canonical_label') or _requirement_name(item)
    rules = item.get('value_mapping_rules') or {}
    status = _status_from_value_rules(value, rules)
    return {
        'name': name,
        'status': status,
        'source_column': column,
        'source_header': item.get('source_header'),
        'source_sheet': item.get('source_sheet'),
        'canonical_label': item.get('canonical_label') or name,
        'raw_value': value,
        'mapping_decision_id': item.get('mapping_decision_id'),
        'requirement_type': metadata.get('requirement_type') or 'document',
        'is_mandatory': bool(metadata.get('is_mandatory')),
        'value_mapping_mode': rules.get('mode') or 'source_reported_under_review',
    }


def _status_from_value_rules(value, rules):
    mode = (rules or {}).get('mode')
    if mode == 'legacy_status':
        return normalize_requirement_status(value)
    if value in (None, ''):
        return 'pending'
    normalized = normalize_label(value)
    if normalized in {'false', 'no', '0', 'not submitted', 'pending', 'none'}:
        return 'pending'
    return 'under_review'


def _set_context_field(custom_fields, item, value, source_sheet, source_column):
    key = item.get('context_key') or _custom_key(item)
    custom_fields[key] = value
    imported_context = dict(custom_fields.get('imported_context') or {})
    imported_context[key] = {
        'label': item.get('canonical_label') or item.get('source_header') or source_column,
        'source_header': item.get('source_header') or source_column,
        'source_column': source_column,
        'source_sheet': source_sheet,
        'value': value,
        'mapping_decision_id': item.get('mapping_decision_id'),
    }
    custom_fields['imported_context'] = imported_context


def _annotate_requirement_resolutions(program_id, mapped, context=None):
    for requirement in mapped.get('requirements') or []:
        name = requirement.get('name')
        if not name:
            continue
        for field in REQUIREMENT_RESOLUTION_FIELDS:
            requirement.pop(field, None)
        requirement.update(deepcopy(_resolve_requirement(program_id, name, context=context)))


def _resolve_requirement(program_id, name, context=None):
    cache_key = normalize_label(name)
    if context is not None and cache_key in context.requirement_resolution_cache:
        return context.requirement_resolution_cache[cache_key]

    match_context = context.requirement_match_context if context is not None else None
    match = find_requirement_match(program_id, name, match_context=match_context)
    if match:
        resolution = {
            'resolution': 'matched_existing',
            'matched_requirement_id': match.id,
            'matched_requirement_name': match.name,
            'matched_phase_name': match.phase.name if match.phase else None,
            'canonical_name': match.name,
        }
    else:
        program_cycle_id = context.batch.program_cycle_id if context is not None else None
        imported_match = _find_existing_imported_requirement(program_id, name, program_cycle_id=program_cycle_id)
        if imported_match:
            resolution = {
                'resolution': 'matched_imported',
                'matched_requirement_id': imported_match.id,
                'matched_requirement_name': imported_match.name,
                'matched_phase_name': imported_match.phase.name if imported_match.phase else 'Imported Requirements',
                'canonical_name': imported_match.name,
                'resolution_reason': 'This imported column already exists under Imported Requirements for this program.',
                'recommended_action': 'Import the cell values into the existing imported requirement; no duplicate requirement will be created.',
            }
        else:
            resolution = {
                'resolution': 'new_imported',
                'canonical_name': standardize_requirement_name(name),
            }
            candidates = _dedupe_requirement_candidates([
                _serialize_requirement_candidate(candidate)
                for candidate in find_requirement_candidates(
                    program_id,
                    name,
                    include_project_snapshots=True,
                    match_context=match_context,
                )
            ])[:5]
            if candidates:
                resolution['similar_candidates'] = candidates

    if context is not None:
        context.requirement_resolution_cache[cache_key] = resolution
    return resolution


def _requirements_need_resolution(mapped):
    return any(
        requirement.get('name') and not requirement.get('resolution')
        for requirement in mapped.get('requirements') or []
    )


def _summarize_requirement_resolutions(summary, requirements):
    for requirement in requirements:
        summary['detected'] += 1
        if requirement.get('resolution') == 'matched_existing':
            summary['matched_existing'] += 1
        elif requirement.get('resolution') == 'matched_imported':
            summary['matched_imported'] += 1
        else:
            summary['new_imported'] += 1
            if requirement.get('similar_candidates'):
                summary['similar_warnings'] += 1


def _similar_requirement_warnings_for_rows(program_id, rows, context=None):
    warnings_by_name = {}
    for row in rows:
        if row.action == 'skip':
            continue
        mapped = row.mapped_data or {}
        if context is None or _requirements_need_resolution(mapped):
            _annotate_requirement_resolutions(program_id, mapped, context=context)
        for requirement in mapped.get('requirements') or []:
            if requirement.get('resolution') in {'matched_existing', 'matched_imported'}:
                continue
            candidates = requirement.get('similar_candidates') or []
            if not candidates:
                continue
            name = requirement.get('name')
            key = normalize_label(name)
            existing = warnings_by_name.setdefault(key, {
                'warning_key': key,
                'imported_name': name,
                'standardized_name': requirement.get('canonical_name') or standardize_requirement_name(name),
                'source_columns': set(),
                'reason': _warning_reason(requirement, candidates),
                'recommended_action': _warning_recommended_action(requirement),
                'apply_anyway_effect': _warning_apply_anyway_effect(requirement),
                'candidates': [],
            })
            if not existing['candidates']:
                existing['candidates'] = candidates[:5]
            if requirement.get('source_column'):
                existing['source_columns'].add(requirement.get('source_column'))
    warnings = []
    for item in warnings_by_name.values():
        warnings.append({
            **item,
            'source_columns': sorted(item['source_columns']),
        })
    return warnings


def _find_existing_imported_requirement(program_id, name, program_cycle_id=None):
    normalized_names = {normalize_label(name), normalize_label(standardize_requirement_name(name))}
    phases = ProgramPhase.query.filter_by(program_id=program_id).all()
    imported_phase = next(
        (phase for phase in phases if normalize_label(phase.name) == 'imported requirements'),
        None,
    )
    if not imported_phase:
        return None

    query = Requirement.query.filter_by(phase_id=imported_phase.id)
    if program_cycle_id is not None:
        query = query.filter(db.or_(Requirement.program_cycle_id == program_cycle_id, Requirement.program_cycle_id.is_(None)))
    for requirement in query.all():
        if normalize_label(requirement.name) in normalized_names:
            return requirement
    return None


def _dedupe_requirement_candidates(candidates):
    grouped = {}
    for candidate in candidates:
        key = (
            normalize_label(candidate.get('name')),
            normalize_label(candidate.get('phase_name')),
            normalize_label(candidate.get('annex_reference')),
        )
        existing = grouped.get(key)
        if not existing:
            item = {
                **candidate,
                'occurrence_count': candidate.get('occurrence_count') or 1,
                'matched_sources': sorted({candidate.get('matched_on')} if candidate.get('matched_on') else set()),
            }
            item['reason'] = item.get('reason') or _candidate_reason(item)
            item['recommended_action'] = item.get('recommended_action') or _candidate_recommended_action(item)
            grouped[key] = item
            continue

        existing['occurrence_count'] = (existing.get('occurrence_count') or 1) + (candidate.get('occurrence_count') or 1)
        existing['score'] = max(existing.get('score') or 0, candidate.get('score') or 0)
        if candidate.get('match_type') == 'exact':
            existing['match_type'] = 'exact'
        matched_sources = set(existing.get('matched_sources') or [])
        if candidate.get('matched_on'):
            matched_sources.add(candidate.get('matched_on'))
        existing['matched_sources'] = sorted(matched_sources)

    return sorted(
        grouped.values(),
        key=lambda item: (item.get('score') or 0, -(item.get('occurrence_count') or 1), item.get('name') or ''),
        reverse=True,
    )


def _serialize_requirement_candidate(candidate):
    item = {
        'id': candidate.get('id'),
        'name': candidate.get('name'),
        'phase_name': candidate.get('phase_name'),
        'annex_reference': candidate.get('annex_reference'),
        'score': round(candidate.get('score') or 0, 3),
        'match_type': candidate.get('match_type'),
        'matched_on': candidate.get('matched_on'),
    }
    item['reason'] = _candidate_reason(item)
    item['recommended_action'] = _candidate_recommended_action(item)
    return item


def _candidate_reason(candidate):
    match_type = candidate.get('match_type')
    matched_on = candidate.get('matched_on')
    if match_type == 'exact':
        return 'Strong match by normalized name, acronym, or annex reference.'
    if matched_on == 'project_requirement':
        return 'Similar wording was found in existing project requirement snapshots.'
    return 'Similar wording, acronym, or annex reference was found in the program requirement matrix.'


def _candidate_recommended_action(candidate):
    phase_name = candidate.get('phase_name') or 'Unassigned phase'
    if normalize_label(phase_name) == 'imported requirements':
        return 'Reuse or keep this imported requirement if it represents the same workbook column.'
    return f'Use the existing requirement in {phase_name} if this imported column is the same documentary requirement.'


def _warning_reason(requirement, candidates):
    if any((candidate.get('score') or 0) >= 0.95 for candidate in candidates):
        return 'At least one existing requirement has a strong normalized-name, acronym, or annex-reference match.'
    return 'This imported column does not exactly match a known requirement, but it is close to existing requirement wording.'


def _warning_recommended_action(requirement):
    canonical_name = requirement.get('canonical_name') or standardize_requirement_name(requirement.get('name'))
    return (
        'Review the existing candidates below. If one is the same requirement, cancel the import and update the program matrix '
        f'or source header to use "{canonical_name}". If it is genuinely separate, confirm and apply anyway.'
    )


def _warning_apply_anyway_effect(requirement):
    canonical_name = requirement.get('canonical_name') or standardize_requirement_name(requirement.get('name'))
    return f'Applying anyway will keep "{canonical_name}" as its own imported requirement and import the workbook values into it.'


def _classify_row(batch, mapped, context=None):
    errors = []
    project = mapped.get('project') or {}
    lgu = mapped.get('lgu') or {}
    if not project.get('project_name'):
        errors.append('Project title is required.')
    if not (lgu.get('name') or lgu.get('municipality')):
        errors.append('LGU name or municipality is required.')

    program = batch.program or db.session.get(Program, batch.program_id)
    program_type = program.program_type if program else None
    project_kind = project.get('project_kind')
    if program_type in ('hybrid', 'non_infrastructure') and not project_kind:
        label = 'non-infrastructure' if program_type == 'non_infrastructure' else 'hybrid'
        errors.append(f'Project classification (project_kind) is required for {label} programs — not supported by this import format yet.')


    lgu_resolution = None
    if not errors:
        lgu_matches = _match_lgus(lgu, context=context)
        if len(lgu_matches) > 1:
            errors.append('LGU name is ambiguous.')
            lgu_resolution = 'ambiguous'
        elif len(lgu_matches) == 1:
            lgu_resolution = 'matched'
        else:
            lgu_resolution = 'new'

    if errors:
        return 'error', errors, lgu_resolution
    existing = _find_existing_project(batch, mapped, context=context)
    return ('update_project' if existing else 'create_project'), [], lgu_resolution


def _find_existing_project(batch, mapped, context=None):
    project = mapped.get('project') or {}
    source_code = project.get('source_project_code')
    if batch.program_cycle_id and source_code:
        lookup_key = ('cycle_source', batch.program_cycle_id, source_code)
        if context is not None and lookup_key in context.project_lookup_cache:
            return context.project_lookup_cache[lookup_key]
        existing = Project.query.filter_by(
            program_cycle_id=batch.program_cycle_id,
            source_project_code=source_code,
        ).first()
        if context is not None:
            context.project_lookup_cache[lookup_key] = existing
        return existing
    if source_code:
        fiscal_year = _project_fiscal_year(batch, mapped)
        lookup_key = ('program_year_source', batch.program_id, fiscal_year, source_code)
        if context is not None and lookup_key in context.project_lookup_cache:
            return context.project_lookup_cache[lookup_key]
        existing = Project.query.filter_by(
            program_id=batch.program_id,
            fiscal_year=fiscal_year,
            source_project_code=source_code,
        ).first()
        if context is not None:
            context.project_lookup_cache[lookup_key] = existing
        return existing
    row_key = mapped.get('row_key')
    if row_key:
        fiscal_year = _project_fiscal_year(batch, mapped)
        lookup_key = ('program_year_row_key', batch.program_id, fiscal_year, row_key)
        if context is not None and lookup_key in context.project_lookup_cache:
            return context.project_lookup_cache[lookup_key]
        existing = Project.query.filter_by(
            program_id=batch.program_id,
            fiscal_year=fiscal_year,
            source_row_key=row_key,
        ).first()
        if context is not None:
            context.project_lookup_cache[lookup_key] = existing
        return existing
    return None


def _get_or_create_lgu(lgu_data):
    matches = _match_lgus(lgu_data)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ImportError('LGU name is ambiguous.', 422)
    name = lgu_data.get('name') or lgu_data.get('municipality')
    municipality = lgu_data.get('municipality') or name
    lgu = LguProfile(
        name=name,
        municipality=municipality,
        province=lgu_data.get('province') or 'Laguna',
        is_active=True,
    )
    db.session.add(lgu)
    db.session.flush()
    return lgu


def _match_lgus(lgu_data, context=None):
    name = normalize_label(lgu_data.get('name') or lgu_data.get('municipality'))
    province = normalize_label(lgu_data.get('province'))
    if not name:
        return []
    cache_key = (name, province)
    if context is not None and cache_key in context.lgu_match_cache:
        return context.lgu_match_cache[cache_key]
    if context is not None:
        if context.lgu_candidates is None:
            context.lgu_candidates = LguProfile.query.all()
        candidates = context.lgu_candidates
    else:
        candidates = LguProfile.query.all()
    matches = []
    for lgu in candidates:
        labels = {normalize_label(lgu.name), normalize_label(lgu.municipality)}
        if name in labels or any(name in label or label in name for label in labels if label):
            if not province or normalize_label(lgu.province) == province:
                matches.append(lgu)
    if context is not None:
        context.lgu_match_cache[cache_key] = matches
    return matches


def _get_or_create_imported_phase(program_id):
    phase = ProgramPhase.query.filter_by(program_id=program_id, name='Imported Requirements').first()
    if phase:
        return phase
    last = ProgramPhase.query.filter_by(program_id=program_id).order_by(ProgramPhase.phase_order.desc()).first()
    phase = ProgramPhase(
        program_id=program_id,
        name='Imported Requirements',
        phase_order=(last.phase_order + 1) if last else 1,
        description='Requirements detected from workbook import templates.',
    )
    db.session.add(phase)
    db.session.flush()
    return phase


def _profile_sheet(profile, sheet_name):
    for sheet in profile.get('sheets', []):
        if sheet.get('name') == sheet_name:
            return sheet
    return None


def _has_project_signal(mapped):
    project = mapped.get('project') or {}
    lgu = mapped.get('lgu') or {}
    return bool(project.get('project_name') or project.get('source_project_code') or lgu.get('name') or lgu.get('municipality'))


def _summary_key(action):
    return {
        'create_project': 'new',
        'update_project': 'updates',
        'skip': 'skipped',
        'error': 'invalid',
    }[action]


def _apply_mapping_overrides(mapping, overrides):
    if overrides.get('field_mappings'):
        mapping['field_mappings'] = overrides['field_mappings']
    if overrides.get('sheet_mappings'):
        mapping['sheet_mappings'] = overrides['sheet_mappings']
    return mapping


def _prepare_mapping_decision_workshop(batch, mapping):
    mapping = deepcopy(mapping or {})
    profile = batch.workbook_profile or {}
    history_by_fingerprint, history_by_header = _mapping_history_for_batch(batch)
    prepared = []
    for item in mapping.get('field_mappings') or []:
        enriched = _normalize_mapping_item(item)
        fingerprint = _column_fingerprint(enriched)
        suggestion = history_by_fingerprint.get(fingerprint) or history_by_header.get(normalize_label(enriched.get('source_header')))
        if suggestion and not enriched.get('mapping_decision_id'):
            enriched['history_suggestion'] = _serialize_mapping_decision(suggestion)
            enriched['requires_confirmation'] = True
            enriched['decision_source'] = 'history_suggestion'
        enriched.setdefault('column_fingerprint', fingerprint)
        prepared.append(enriched)

    existing_keys = {_mapping_source_key(item) for item in prepared}
    for sheet in profile.get('sheets') or []:
        for column in sheet.get('columns') or []:
            item = _mapping_item_from_profile_column(sheet, column)
            key = _mapping_source_key(item)
            if key in existing_keys:
                continue
            suggestion = history_by_fingerprint.get(item['column_fingerprint']) or history_by_header.get(normalize_label(item.get('source_header')))
            if suggestion:
                item['history_suggestion'] = _serialize_mapping_decision(suggestion)
                item['requires_confirmation'] = True
                item['decision_source'] = 'history_suggestion'
            prepared.append(item)

    mapping['field_mappings'] = prepared
    mapping['mapping_decisions'] = [_mapping_item_to_decision(item) for item in prepared]
    return mapping


def _mapping_history_for_batch(batch):
    query = ImportMappingDecision.query.filter_by(program_id=batch.program_id, status='active', trust_level='confirmed')
    decisions = query.order_by(ImportMappingDecision.updated_at.desc(), ImportMappingDecision.id.desc()).all()
    decisions.sort(key=lambda decision: _mapping_history_priority(decision, batch), reverse=True)
    by_fingerprint = {}
    by_header = {}
    for decision in decisions:
        fingerprint = decision.column_fingerprint
        header = decision.normalized_source_header
        if fingerprint and fingerprint not in by_fingerprint:
            by_fingerprint[fingerprint] = decision
        if header and header not in by_header:
            by_header[header] = decision
    return by_fingerprint, by_header


def _mapping_history_priority(decision, batch):
    if decision.program_cycle_id == batch.program_cycle_id:
        scope_priority = 2
    elif decision.program_cycle_id is None:
        scope_priority = 1
    else:
        scope_priority = 0
    updated_at = decision.updated_at.isoformat() if decision.updated_at else ''
    return (scope_priority, updated_at, decision.id or 0)


def _mapping_item_from_profile_column(sheet, column):
    header = column.get('header') or column.get('source_header') or column.get('column')
    item = {
        'source_sheet': sheet.get('name'),
        'source_column': column.get('column'),
        'source_header': header,
        'header_path': column.get('header_path') or [],
        'target_field': None,
        'suggested_role': None,
        'confidence': 0,
    }
    return _normalize_mapping_item(item)


def _normalize_mapping_item(item):
    item = dict(item or {})
    item.setdefault('source_header', item.get('header') or item.get('source_column'))
    item.setdefault('classification', _classification_for_mapping(item))
    item.setdefault('canonical_label', _canonical_label_for_mapping(item))
    item.setdefault('column_fingerprint', _column_fingerprint(item))
    item.setdefault('binding_target', _binding_target_for_mapping(item))
    if item.get('classification') == 'requirement':
        metadata = dict(item.get('requirement_metadata') or {})
        metadata.setdefault('name', item.get('canonical_label') or _requirement_name(item))
        metadata.setdefault('is_mandatory', False)
        metadata.setdefault('requirement_type', 'document')
        item['requirement_metadata'] = metadata
        rules = dict(item.get('value_mapping_rules') or {})
        rules.setdefault('mode', 'legacy_status')
        item['value_mapping_rules'] = rules
    elif item.get('classification') == 'context':
        item.setdefault('context_key', _custom_key(item))
    return item


def _classification_for_mapping(item):
    target = item.get('target_field')
    if target == 'program_cycle.fiscal_year':
        return 'cycle_field'
    if target and target.startswith('project.'):
        return 'project_field'
    if target and target.startswith('lgu.'):
        return 'lgu_field'
    if item.get('suggested_role') == 'requirement':
        return 'requirement'
    if item.get('suggested_role') in {'calculated_only'}:
        return 'calculated'
    if item.get('suggested_role'):
        return 'context'
    return 'ignored'


def _canonical_label_for_mapping(item):
    if item.get('canonical_label'):
        return str(item.get('canonical_label')).strip()
    if item.get('target_field') in PROJECT_FIELDS:
        return item.get('source_header') or item.get('target_field')
    if item.get('suggested_role') == 'requirement':
        return _requirement_name(item)
    return item.get('source_header') or item.get('source_column')


def _binding_target_for_mapping(item):
    classification = item.get('classification') or _classification_for_mapping(item)
    target = item.get('target_field')
    if classification in {'project_field', 'lgu_field', 'cycle_field'} and target:
        return target
    if classification == 'requirement':
        return f"project_requirement.status:{item.get('canonical_label') or _requirement_name(item)}"
    if classification == 'context':
        return f"project.custom_fields.{_custom_key(item)}"
    if classification == 'calculated':
        return 'calculated_only'
    return 'import_only'


def _column_fingerprint(item):
    source_sheet = normalize_label(item.get('source_sheet'))
    source_header = normalize_label(item.get('source_header') or item.get('header'))
    header_path = '>'.join(normalize_label(part) for part in (item.get('header_path') or []) if part)
    return hashlib.sha256(f'{source_sheet}|{source_header}|{header_path}'.encode('utf-8')).hexdigest()[:40]


def _mapping_item_to_decision(item):
    return {
        'source_sheet': item.get('source_sheet'),
        'source_column': item.get('source_column'),
        'source_header': item.get('source_header'),
        'header_path': item.get('header_path') or [],
        'column_fingerprint': item.get('column_fingerprint') or _column_fingerprint(item),
        'classification': item.get('classification') or _classification_for_mapping(item),
        'canonical_label': item.get('canonical_label') or _canonical_label_for_mapping(item),
        'target_field': item.get('target_field'),
        'suggested_role': item.get('suggested_role'),
        'binding_target': item.get('binding_target') or _binding_target_for_mapping(item),
        'binding_config': item.get('binding_config') or {},
        'requirement_metadata': item.get('requirement_metadata') or {},
        'value_mapping_rules': item.get('value_mapping_rules') or {},
        'mapping_decision_id': item.get('mapping_decision_id'),
        'decision_source': item.get('decision_source') or 'auto',
        'requires_confirmation': bool(item.get('requires_confirmation')),
        'history_suggestion': item.get('history_suggestion'),
    }


def _mapping_source_key(item):
    source_sheet = item.get('source_sheet')
    source_column = item.get('source_column')
    if not source_sheet or not source_column:
        return None
    return f'{source_sheet}::{source_column}'


def _merge_admin_decision(item, payload):
    merged = dict(item or {})
    classification = payload.get('classification') or merged.get('classification') or 'context'
    if classification not in MAPPING_CLASSIFICATIONS:
        raise ImportError(f'Invalid column classification: {classification}', 422)
    merged['classification'] = classification
    merged['canonical_label'] = str(payload.get('canonical_label') or merged.get('canonical_label') or merged.get('source_header') or '').strip()
    merged['target_field'] = payload.get('target_field') if 'target_field' in payload else merged.get('target_field')
    merged['suggested_role'] = payload.get('suggested_role') if 'suggested_role' in payload else merged.get('suggested_role')
    merged['binding_config'] = payload.get('binding_config') or merged.get('binding_config') or {}
    merged['requirement_metadata'] = payload.get('requirement_metadata') or merged.get('requirement_metadata') or {}
    if 'value_mapping_rules' in payload:
        merged['value_mapping_rules'] = payload.get('value_mapping_rules') or {}
    else:
        merged['value_mapping_rules'] = merged.get('value_mapping_rules') or {}
    merged['binding_target'] = payload.get('binding_target') or _binding_target_for_mapping(merged)
    if classification == 'requirement':
        merged['suggested_role'] = 'requirement'
        metadata = dict(merged.get('requirement_metadata') or {})
        metadata['name'] = merged.get('canonical_label') or metadata.get('name') or _requirement_name(merged)
        metadata.setdefault('is_mandatory', False)
        metadata.setdefault('requirement_type', 'document')
        merged['requirement_metadata'] = metadata
        rules = dict(merged.get('value_mapping_rules') or {})
        if not rules or rules.get('mode') == 'legacy_status':
            rules['mode'] = 'source_reported_under_review'
        merged['value_mapping_rules'] = rules
    elif classification == 'context':
        if not merged.get('suggested_role'):
            merged['suggested_role'] = 'context'
        merged['target_field'] = None
    elif classification == 'ignored':
        merged['target_field'] = None
        merged['suggested_role'] = None
        merged['binding_target'] = 'import_only'
    return _normalize_mapping_item(merged)


def _persist_mapping_decision(batch, item, user_id=None):
    fingerprint = item.get('column_fingerprint') or _column_fingerprint(item)
    source_header = item.get('source_header') or item.get('source_column')
    active_query = ImportMappingDecision.query.filter_by(
        program_id=batch.program_id,
        program_cycle_id=batch.program_cycle_id,
        column_fingerprint=fingerprint,
        status='active',
    )
    for existing in active_query.all():
        existing.status = 'superseded'
    prior = (
        ImportMappingDecision.query
        .filter_by(program_id=batch.program_id, program_cycle_id=batch.program_cycle_id, column_fingerprint=fingerprint)
        .order_by(ImportMappingDecision.version_number.desc(), ImportMappingDecision.id.desc())
        .first()
    )
    decision = ImportMappingDecision(
        program_id=batch.program_id,
        program_cycle_id=batch.program_cycle_id,
        import_template_id=batch.import_template_id,
        created_from_batch_id=batch.id,
        source_sheet_name=item.get('source_sheet'),
        source_column=item.get('source_column'),
        source_header=source_header,
        normalized_source_header=normalize_label(source_header),
        column_fingerprint=fingerprint,
        classification=item.get('classification') or 'context',
        canonical_label=item.get('canonical_label') or source_header,
        target_field=item.get('target_field'),
        suggested_role=item.get('suggested_role'),
        binding_target=item.get('binding_target') or _binding_target_for_mapping(item),
        binding_config=item.get('binding_config') or {},
        requirement_metadata=item.get('requirement_metadata') or {},
        value_mapping_rules=item.get('value_mapping_rules') or {},
        trust_level='confirmed',
        status='active',
        version_number=(prior.version_number + 1) if prior else 1,
        confirmed_by=user_id,
    )
    db.session.add(decision)
    db.session.flush()
    return decision


def _serialize_mapping_decision(decision):
    return {
        'id': decision.id,
        'program_id': decision.program_id,
        'program_cycle_id': decision.program_cycle_id,
        'import_template_id': decision.import_template_id,
        'created_from_batch_id': decision.created_from_batch_id,
        'source_sheet': decision.source_sheet_name,
        'source_column': decision.source_column,
        'source_header': decision.source_header,
        'column_fingerprint': decision.column_fingerprint,
        'classification': decision.classification,
        'canonical_label': decision.canonical_label,
        'target_field': decision.target_field,
        'suggested_role': decision.suggested_role,
        'binding_target': decision.binding_target,
        'binding_config': decision.binding_config or {},
        'requirement_metadata': decision.requirement_metadata or {},
        'value_mapping_rules': decision.value_mapping_rules or {},
        'trust_level': decision.trust_level,
        'status': decision.status,
        'version_number': decision.version_number,
        'confirmed_by': decision.confirmed_by,
        'created_at': decision.created_at.isoformat() if decision.created_at else None,
        'updated_at': decision.updated_at.isoformat() if decision.updated_at else None,
    }


def _mapping_for_current_profile(batch, mapping_payload=None):
    profile_signature = (batch.workbook_profile or {}).get('schema_signature')
    for candidate in (mapping_payload, batch.mapping_preview):
        if not candidate or not candidate.get('field_mappings'):
            continue
        candidate_signature = candidate.get('schema_signature')
        if not candidate_signature or candidate_signature == profile_signature:
            return _prepare_mapping_decision_workshop(batch, candidate)
    return _prepare_mapping_decision_workshop(batch, build_mapping(batch.workbook_profile or {}, template=batch.import_template))


def _refresh_workbook_profile(batch, force=False):
    if not force and _workbook_profile_is_current(batch):
        return batch.workbook_profile
    if not force and _legacy_workbook_profile_can_be_adopted(batch):
        batch.workbook_profile = _mark_profile_current(batch.workbook_profile, batch.file_hash)
        return batch.workbook_profile

    try:
        profile = _mark_profile_current(
            profile_workbook(batch.stored_file_path, file_type=batch.file_type),
            batch.file_hash,
        )
    except WorkbookProfileError as exc:
        raise ImportError(exc.message, exc.status_code) from exc
    except OSError as exc:
        raise ImportError('Stored import file is no longer available.', 500) from exc

    current_signature = (batch.workbook_profile or {}).get('schema_signature')
    if profile.get('schema_signature') != current_signature:
        batch.mapping_preview = None
        batch.preview_summary = None
        if batch.status in {'mapped', 'previewed'}:
            batch.status = 'profiled'
    batch.workbook_profile = profile
    return profile


def _mark_profile_current(profile, file_hash):
    profile = dict(profile or {})
    profile['file_hash'] = file_hash
    profile['profile_cache_version'] = PROFILE_CACHE_VERSION
    return profile


def _workbook_profile_is_current(batch):
    profile = batch.workbook_profile or {}
    schema_signature = profile.get('schema_signature')
    return bool(
        profile.get('sheets')
        and profile.get('file_hash') == batch.file_hash
        and profile.get('profile_cache_version') == PROFILE_CACHE_VERSION
        and isinstance(schema_signature, str)
        and SCHEMA_SIGNATURE_RE.fullmatch(schema_signature)
    )


def _legacy_workbook_profile_can_be_adopted(batch):
    profile = batch.workbook_profile or {}
    schema_signature = profile.get('schema_signature')
    return bool(
        profile.get('sheets')
        and batch.file_hash
        and not profile.get('file_hash')
        and not profile.get('profile_cache_version')
        and isinstance(schema_signature, str)
        and SCHEMA_SIGNATURE_RE.fullmatch(schema_signature)
    )


def _get_batch(batch_id, for_update=False):
    batch = (ImportBatch.query.filter_by(id=batch_id).with_for_update().populate_existing().first()
             if for_update else db.session.get(ImportBatch, batch_id))
    if not batch:
        raise ImportError('Import batch not found.', 404)
    return batch


def _ensure_batch_not_committed(batch):
    if batch.status == 'committed' or batch.committed_at:
        raise ImportError(
            'Committed workbook imports are final. Upload a new workbook to re-import this cycle.',
            409,
        )


def _get_cycle(program_id, program_cycle_id):
    if program_cycle_id is None:
        return None
    cycle = db.session.get(ProgramCycle, program_cycle_id)
    if not cycle:
        raise ImportError('Program cycle not found.', 404)
    if cycle.program_id != program_id:
        raise ImportError('Program cycle does not belong to this program.', 422)
    return cycle


def _get_template(program_id, import_template_id, program_cycle_id=None):
    if import_template_id is None:
        return None
    template = db.session.get(ImportTemplate, import_template_id)
    if not template:
        raise ImportError('Import template not found.', 404)
    if template.program_id != program_id:
        raise ImportError('Import template does not belong to this program.', 422)
    if program_cycle_id and template.program_cycle_id not in (None, program_cycle_id):
        raise ImportError('Import template belongs to a different program cycle.', 422)
    return template


def _file_type(filename):
    suffix = Path(filename).suffix.lower().lstrip('.')
    if suffix not in ALLOWED_FILE_TYPES:
        raise ImportError('Only CSV and XLSX workbook imports are supported.', 422)
    return suffix


def _store_upload(upload, user_id=None, tracker=None):
    size_bytes = _measure_upload_size(upload)
    if size_bytes == 0:
        raise ImportError('The uploaded workbook file is empty (0 bytes).', 422)
    max_size_bytes = int(current_app.config.get('MAX_IMPORT_FILE_BYTES') or 0)
    if max_size_bytes and size_bytes > max_size_bytes:
        raise ImportError(
            f'Workbook imports must be {max_size_bytes // (1024 * 1024)} MB or smaller.',
            422,
        )

    file_type = _file_type(upload.filename)
    if file_type == 'xlsx':
        try:
            validate_ooxml_container(upload, expected_kind='xlsx')
        except ArchiveSecurityError as exc:
            raise ImportError(f'Invalid or corrupt Excel workbook: {exc}', 422) from exc

    upload_dir = current_app.config.get('IMPORT_UPLOAD_DIR')
    if upload_dir:
        upload_dir = Path(upload_dir)
    else:
        upload_dir = Path(current_app.instance_path) / 'uploads' / 'imports'
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = validate_upload_filename(
        upload.filename,
        error_factory=lambda msg: ImportError(msg, 422),
        label='Workbook import file',
    )
    stored_name = f'{uuid.uuid4().hex}_{filename}'
    path = upload_dir / stored_name
    upload.seek(0)
    payload = upload.read()
    if file_type == 'csv' and b'\x00' in payload[:4096]:
        raise ImportError('CSV file contains invalid binary content.', 422)
    path.write_bytes(payload)
    if tracker is not None:
        tracker.track_local_path(path)
    file_hash = hashlib.sha256(payload).hexdigest()
    stored_object = object_storage_service.store_file(
        path,
        source_module='imports',
        original_filename=filename,
        content_type='text/csv' if file_type == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        uploaded_by=user_id,
        metadata={'file_type': file_type},
        tracker=tracker,
    )
    return path, file_hash, stored_object


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


def _project_fiscal_year(batch, mapped):
    if batch.program_cycle:
        return batch.program_cycle.fiscal_year
    value = (mapped.get('project') or {}).get('fiscal_year')
    return _as_int(value) or datetime.now(timezone.utc).year


def _as_int(value):
    if value in (None, ''):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value):
    if value in (None, ''):
        return None
    try:
        return float(str(value).replace(',', ''))
    except (TypeError, ValueError):
        return None


def _coerce_project_value(target, value):
    if target == 'project.source_project_code':
        return _coerce_source_project_code(value)
    if target == 'project.budget_amount':
        return _as_float(value)
    if target == 'project.overall_status':
        return normalize_project_status(value, default='ongoing')
    return str(value).strip() if value is not None else None


def _set_project_field(project, confidence_by_field, field, value, mapping_item):
    if value in (None, ''):
        return
    confidence = float(mapping_item.get('confidence') or 0)
    current = project.get(field)
    current_confidence = confidence_by_field.get(field, -1)
    if current not in (None, '') and confidence <= current_confidence:
        return
    project[field] = value
    confidence_by_field[field] = confidence


def _coerce_source_project_code(value):
    if value in (None, ''):
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if len(cleaned) <= SOURCE_PROJECT_CODE_LIMIT:
        return cleaned
    match = SOURCE_PROJECT_CODE_RE.search(cleaned)
    if match:
        return match.group(0)[:SOURCE_PROJECT_CODE_LIMIT]
    return None


def _safe_row_key(value):
    if value in (None, ''):
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if len(cleaned) <= ROW_KEY_LIMIT:
        return cleaned
    digest = hashlib.sha256(cleaned.encode('utf-8')).hexdigest()[:16]
    prefix_length = ROW_KEY_LIMIT - len(digest) - 4
    return f'{cleaned[:prefix_length].rstrip()}...#{digest}'


def _requirement_name(mapping_item):
    header = mapping_item.get('source_header') or mapping_item.get('header') or mapping_item.get('source_column')
    if header:
        parts = [part.strip() for part in str(header).split('/') if part.strip()]
        return parts[-1] if parts else str(header).strip()
    return 'Imported Requirement'


def _custom_key(mapping_item):
    return normalize_label(mapping_item.get('source_header') or mapping_item.get('source_column')).replace(' ', '_')


def _serialize_batch(batch, include_profile=True):
    data = {
        'id': batch.id,
        'program_id': batch.program_id,
        'program_cycle_id': batch.program_cycle_id,
        'import_template_id': batch.import_template_id,
        'uploaded_by': batch.uploaded_by,
        'original_file_name': batch.original_file_name,
        'file_hash': batch.file_hash,
        'file_type': batch.file_type,
        'status': batch.status,
        'mapping_preview': batch.mapping_preview or {},
        'preview_summary': batch.preview_summary or {},
        'committed_at': batch.committed_at.isoformat() if batch.committed_at else None,
        'created_at': batch.created_at.isoformat() if batch.created_at else None,
        'updated_at': batch.updated_at.isoformat() if batch.updated_at else None,
    }
    if include_profile:
        data['workbook_profile'] = batch.workbook_profile or {}
    return data


def _serialize_template(template):
    return {
        'id': template.id,
        'program_id': template.program_id,
        'program_cycle_id': template.program_cycle_id,
        'cloned_from_template_id': template.cloned_from_template_id,
        'name': template.name,
        'file_type': template.file_type,
        'version_number': template.version_number,
        'status': template.status,
        'schema_signature': template.schema_signature,
        'sheet_mappings': template.sheet_mappings or {},
        'column_mappings': template.column_mappings or {},
        'transform_rules': template.transform_rules or {},
        'is_active': template.is_active,
        'locked_at': template.locked_at.isoformat() if template.locked_at else None,
        'created_at': template.created_at.isoformat() if template.created_at else None,
        'updated_at': template.updated_at.isoformat() if template.updated_at else None,
    }


def _serialize_import_row(row):
    return {
        'id': row.id,
        'import_batch_id': row.import_batch_id,
        'sheet_name': row.sheet_name,
        'row_number': row.row_number,
        'row_key': row.row_key,
        'mapped_data': row.mapped_data or {},
        'validation_errors': row.validation_errors or [],
        'action': row.action,
        'committed_entity_type': row.committed_entity_type,
        'committed_entity_id': row.committed_entity_id,
    }


def _audit(user_id, action, entity_type, entity_id, old_value, new_value, commit=True):
    if user_id is None:
        return
    audit_service.log_action(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        commit=commit,
    )
