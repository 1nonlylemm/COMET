from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Program, ProgramCycle, ProgramPhase, Project, Requirement
from app.services import audit_service
from app.services.import_field_catalog import normalize_label
from app.services.requirement_matching_service import (
    EXACT_MATCH_THRESHOLD,
    find_requirement_candidates,
    standardize_annex_reference,
    standardize_requirement_name,
)


PROGRAM_IDENTITY_CONSTRAINTS = {
    'programs_code_key',
    'programs_name_key',
    'uq_program_cycle_year_code',
    'uq_program_phase_order',
}


def _is_program_identity_conflict(exc):
    orig = getattr(exc, 'orig', None)
    if orig is not None:
        diag = getattr(orig, 'diag', None)
        if diag is not None:
            constraint_name = getattr(diag, 'constraint_name', None)
            if constraint_name:
                return constraint_name if constraint_name in PROGRAM_IDENTITY_CONSTRAINTS else None

    # Fallback for SQLite / engines without psycopg2 diag
    msg = str(orig if orig is not None else exc).lower()
    if 'unique constraint failed:' in msg:
        if 'programs.code' in msg:
            return 'programs_code_key'
        if 'programs.name' in msg:
            return 'programs_name_key'
        if 'program_cycles.program_id, program_cycles.fiscal_year, program_cycles.cycle_code' in msg:
            return 'uq_program_cycle_year_code'
        if 'program_phases.program_id, program_phases.phase_order' in msg:
            return 'uq_program_phase_order'
    for c in PROGRAM_IDENTITY_CONSTRAINTS:
        if c in msg:
            return c
    return None


def _handle_program_integrity_error(exc, default_phase_order=None):
    db.session.rollback()
    conflict = _is_program_identity_conflict(exc)
    if conflict == 'programs_code_key':
        raise ProgramError('Program code already exists', 409) from exc
    if conflict == 'programs_name_key':
        raise ProgramError('Program name already exists', 409) from exc
    if conflict == 'uq_program_cycle_year_code':
        raise ProgramError('Program cycle already exists for this fiscal year and cycle code', 409) from exc
    if conflict == 'uq_program_phase_order':
        order_str = f' {default_phase_order}' if default_phase_order is not None else ''
        raise ProgramError(f'Phase order{order_str} already exists for this program', 409) from exc
    raise exc


class ProgramError(Exception):
    def __init__(self, message, status_code=400, errors=None):
        self.message = message
        self.status_code = status_code
        self.errors = errors


VALID_PROGRAM_TYPES = ('infrastructure', 'non_infrastructure', 'hybrid')
VALID_REQ_TYPES = ('document', 'certificate', 'resolution', 'financial', 'engineering', 'inspection', 'other')

# Shared workflow document categories reused across the Monitoring,
# Evidence Intake, and Completion modules. Every project requirement
# tagged with one of these categories drives the shared Draft -> Submitted
# -> Under Verification -> Staff Approved -> Pending Provincial Approval ->
# Approved workflow (with Returned for Revision -> Resubmitted).
VALID_DOCUMENT_CATEGORIES = (
    'monthly_progress_report',
    'form_3',
    'form_3_mov',
    'project_exception_report',
    'apm_template',
    'non_infra_monitoring_evidence',
    'signed_distribution_list',
    'acknowledgement_receipt',
    'beneficiary_tracking_record',
    'turnover_photos',
    'delivery_invoice',
    'final_swa',
    'final_inspection_report',
    'certificate_of_final_acceptance',
    'final_sord',
    'proof_of_return_of_funds',
)


def _clean_required_text(value, field_label, blank_message=None):
    text = str(value).strip() if value is not None else ''
    if not text:
        raise ProgramError(blank_message or f'{field_label} is required', 422)
    return text


def _clean_optional_text(value):
    if isinstance(value, str):
        return value.strip()
    return value


def _require_bool(value, field_name):
    if not isinstance(value, bool):
        raise ProgramError(f'{field_name} must be true or false', 422)
    return value


def _validate_positive_int(value, message):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ProgramError(message, 422)
    return value


def _normalized_text(value):
    return normalize_label(value)


def _find_program_by_normalized(field_name, value, exclude_id=None):
    normalized = _normalized_text(value)
    query = Program.query
    if exclude_id is not None:
        query = query.filter(Program.id != exclude_id)
    for program in query.all():
        if _normalized_text(getattr(program, field_name)) == normalized:
            return program
    return None


def _find_cycle_by_normalized_code(program_id, fiscal_year, cycle_code, exclude_id=None):
    normalized = _normalized_text(cycle_code)
    query = ProgramCycle.query.filter_by(program_id=program_id, fiscal_year=fiscal_year)
    if exclude_id is not None:
        query = query.filter(ProgramCycle.id != exclude_id)
    for cycle in query.all():
        if _normalized_text(cycle.cycle_code) == normalized:
            return cycle
    return None


def _clean_requirement_name(value, blank_message):
    _clean_required_text(value, 'Requirement name', blank_message)
    standardized_name = standardize_requirement_name(value)
    if not standardized_name:
        raise ProgramError(blank_message, 422)
    return standardized_name


# ── Program CRUD ──────────────────────────────────────────────────────────

def create_program(name, code, program_type, description=None, funding_agency=None,
                   project_custom_field_schema=None, user_id=None):
    name = _clean_required_text(name, 'Program name')
    code = _clean_required_text(code, 'Program code')
    if program_type not in VALID_PROGRAM_TYPES:
        raise ProgramError(f'Invalid program_type. Must be one of: {", ".join(VALID_PROGRAM_TYPES)}', 422)

    if _find_program_by_normalized('code', code):
        raise ProgramError('Program code already exists', 409)
    if _find_program_by_normalized('name', name):
        raise ProgramError('Program name already exists', 409)

    program = Program(
        name=name,
        code=code,
        program_type=program_type,
        description=_clean_optional_text(description),
        funding_agency=_clean_optional_text(funding_agency),
        project_custom_field_schema=project_custom_field_schema or {},
    )
    db.session.add(program)
    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='create',
                entity_type='program',
                entity_id=program.id,
                old_value=None,
                new_value=_serialize_program(program),
                commit=False,
            )
        db.session.commit()
    except IntegrityError as exc:
        _handle_program_integrity_error(exc)
    except Exception:
        db.session.rollback()
        raise

    return program


def get_program(program_id):
    program = db.session.get(Program, program_id)
    if not program:
        raise ProgramError('Program not found', 404)
    return program


def list_programs(search=None, program_type=None, is_active=None, fiscal_year=None, page=1, per_page=20):
    query = Program.query

    if search:
        query = query.filter(
            db.or_(
                Program.name.ilike(f'%{search}%'),
                Program.code.ilike(f'%{search}%'),
            )
        )
    if program_type:
        query = query.filter_by(program_type=program_type)
    if is_active is not None:
        query = query.filter_by(is_active=is_active)
    if fiscal_year is not None:
        query = query.filter(db.or_(
            Program.cycles.any(ProgramCycle.fiscal_year == fiscal_year),
            Program.projects.any(Project.fiscal_year == fiscal_year),
            db.and_(
                ~Program.cycles.any(),
                ~Program.projects.any(),
            ),
        ))

    pagination = query.order_by(Program.name).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        'programs': [_serialize_program(p, fiscal_year=fiscal_year) for p in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'per_page': pagination.per_page,
        'pages': pagination.pages,
    }


def update_program(program_id, data, user_id=None):
    program = db.session.get(Program, program_id)
    if not program:
        raise ProgramError('Program not found', 404)

    before = _serialize_program(program)

    if 'name' in data:
        name = _clean_required_text(data['name'], 'Program name', 'Program name cannot be blank')
        existing = _find_program_by_normalized('name', name, exclude_id=program_id)
        if existing:
            raise ProgramError('Program name already exists', 409)
        program.name = name
    if 'code' in data:
        code = _clean_required_text(data['code'], 'Program code', 'Program code cannot be blank')
        existing = _find_program_by_normalized('code', code, exclude_id=program_id)
        if existing:
            raise ProgramError('Program code already exists', 409)
        program.code = code
    if 'description' in data:
        program.description = _clean_optional_text(data['description'])
    if 'program_type' in data:
        new_type = data['program_type']
        if new_type not in VALID_PROGRAM_TYPES:
            raise ProgramError(f'Invalid program_type. Must be one of: {", ".join(VALID_PROGRAM_TYPES)}', 422)
        if new_type != program.program_type:
            from app.services.project_service import resolve_effective_project_kind, validate_project_kind_for_program_type, ProjectError
            child_projects = program.projects.all()
            for child in child_projects:
                child_kind = resolve_effective_project_kind(child)
                try:
                    validate_project_kind_for_program_type(new_type, child_kind)
                except ProjectError as exc:
                    raise ProgramError(
                        f"Cannot change program_type to '{new_type}'. Existing project '{child.project_name}' has incompatible kind '{child_kind}'.",
                        422,
                    ) from exc
        program.program_type = new_type
    if 'funding_agency' in data:
        program.funding_agency = _clean_optional_text(data['funding_agency'])
    if 'is_active' in data:
        program.is_active = _require_bool(data['is_active'], 'is_active')
    if 'project_custom_field_schema' in data:
        program.project_custom_field_schema = data['project_custom_field_schema']

    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='update',
                entity_type='program',
                entity_id=program.id,
                old_value=before,
                new_value=_serialize_program(program),
                commit=False,
            )
        db.session.commit()
    except IntegrityError as exc:
        _handle_program_integrity_error(exc)
    except Exception:
        db.session.rollback()
        raise

    return program


def toggle_program_active(program_id, user_id=None):
    program = db.session.get(Program, program_id)
    if not program:
        raise ProgramError('Program not found', 404)

    before = _serialize_program(program)
    program.is_active = not program.is_active
    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='toggle_active',
                entity_type='program',
                entity_id=program.id,
                old_value=before,
                new_value=_serialize_program(program),
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return program


# ── Program Cycle CRUD ────────────────────────────────────────────────────

def create_program_cycle(program_id, name, fiscal_year, cycle_code,
                         source_template_name=None, import_profile=None,
                         field_schema=None, cloned_from_cycle_id=None,
                         user_id=None):
    program = db.session.get(Program, program_id)
    if not program:
        raise ProgramError('Program not found', 404)
    if not program.is_active:
        raise ProgramError('Cannot create program cycle under an inactive program', 422)
    name = _clean_required_text(name, 'Cycle name')
    cycle_code = _clean_required_text(cycle_code, 'Cycle code')
    _validate_cycle_fields(fiscal_year, cycle_code)

    if cloned_from_cycle_id is not None:
        source_cycle = db.session.get(ProgramCycle, cloned_from_cycle_id)
        if not source_cycle:
            raise ProgramError('Source program cycle not found', 404)
        if source_cycle.program_id != program_id:
            raise ProgramError('Source cycle must belong to the same program', 422)

    existing = _find_cycle_by_normalized_code(program_id, fiscal_year, cycle_code)
    if existing:
        raise ProgramError('Program cycle already exists for this fiscal year and cycle code', 409)

    cycle = ProgramCycle(
        program_id=program_id,
        cloned_from_cycle_id=cloned_from_cycle_id,
        name=name,
        fiscal_year=fiscal_year,
        cycle_code=cycle_code,
        source_template_name=source_template_name,
        import_profile=import_profile or {},
        field_schema=field_schema or {},
    )
    db.session.add(cycle)
    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='create',
                entity_type='program_cycle',
                entity_id=cycle.id,
                old_value=None,
                new_value=_serialize_program_cycle(cycle),
                commit=False,
            )
        db.session.commit()
    except IntegrityError as exc:
        _handle_program_integrity_error(exc)
    except Exception:
        db.session.rollback()
        raise

    return cycle


def list_program_cycles(program_id, is_active=None, fiscal_year=None):
    program = db.session.get(Program, program_id)
    if not program:
        raise ProgramError('Program not found', 404)

    query = ProgramCycle.query.filter_by(program_id=program_id)
    if is_active is not None:
        query = query.filter_by(is_active=is_active)
    if fiscal_year is not None:
        query = query.filter_by(fiscal_year=fiscal_year)
    return [
        _serialize_program_cycle(cycle)
        for cycle in query.order_by(ProgramCycle.fiscal_year.desc(), ProgramCycle.name.asc()).all()
    ]


def get_program_cycle(cycle_id):
    cycle = db.session.get(ProgramCycle, cycle_id)
    if not cycle:
        raise ProgramError('Program cycle not found', 404)
    return cycle


def update_program_cycle(cycle_id, data, user_id=None):
    cycle = get_program_cycle(cycle_id)
    before = _serialize_program_cycle(cycle)

    if 'name' in data:
        cycle.name = _clean_required_text(data['name'], 'Cycle name', 'Cycle name cannot be blank')
    if 'fiscal_year' in data:
        _validate_fiscal_year(data['fiscal_year'])
        new_fy = data['fiscal_year']
        if new_fy != cycle.fiscal_year:
            attached_projects_count = cycle.projects.count()
            if attached_projects_count > 0:
                raise ProgramError(
                    f'Cannot change fiscal year of a program cycle with {attached_projects_count} attached project(s)',
                    409,
                )
            cycle.fiscal_year = new_fy
    if 'cycle_code' in data:
        cycle.cycle_code = _clean_required_text(data['cycle_code'], 'Cycle code', 'Cycle code cannot be blank')
    if 'source_template_name' in data:
        cycle.source_template_name = data['source_template_name']
    if 'import_profile' in data:
        cycle.import_profile = data['import_profile'] or {}
    if 'field_schema' in data:
        cycle.field_schema = data['field_schema'] or {}
    if 'is_active' in data:
        cycle.is_active = _require_bool(data['is_active'], 'is_active')

    duplicate = _find_cycle_by_normalized_code(
        cycle.program_id,
        cycle.fiscal_year,
        cycle.cycle_code,
        exclude_id=cycle.id,
    )
    if duplicate:
        raise ProgramError('Program cycle already exists for this fiscal year and cycle code', 409)

    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='update',
                entity_type='program_cycle',
                entity_id=cycle.id,
                old_value=before,
                new_value=_serialize_program_cycle(cycle),
                commit=False,
            )
        db.session.commit()
    except IntegrityError as exc:
        _handle_program_integrity_error(exc)
    except Exception:
        db.session.rollback()
        raise

    return cycle


def clone_program_cycle(source_cycle_id, fiscal_year, cycle_code=None, name=None, user_id=None):
    source = get_program_cycle(source_cycle_id)
    if not source.program.is_active:
        raise ProgramError('Cannot clone program cycle under an inactive program', 422)
    _validate_fiscal_year(fiscal_year)
    target_code = (
        _clean_required_text(cycle_code, 'Cycle code', 'Cycle code cannot be blank')
        if cycle_code is not None
        else source.cycle_code
    )
    target_name = (
        _clean_required_text(name, 'Cycle name', 'Cycle name cannot be blank')
        if name is not None
        else f'{source.program.name} FY {fiscal_year}'
    )

    existing = _find_cycle_by_normalized_code(source.program_id, fiscal_year, target_code)
    if existing:
        raise ProgramError('Program cycle already exists for this fiscal year and cycle code', 409)

    cycle = ProgramCycle(
        program_id=source.program_id,
        cloned_from_cycle_id=source.id,
        name=target_name,
        fiscal_year=fiscal_year,
        cycle_code=target_code,
        source_template_name=source.source_template_name,
        import_profile=source.import_profile or {},
        field_schema=source.field_schema or {},
    )
    db.session.add(cycle)
    try:
        db.session.flush()
        cloned_templates = _clone_cycle_import_templates(source, cycle, user_id=user_id)
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='clone',
                entity_type='program_cycle',
                entity_id=cycle.id,
                old_value={'source_cycle_id': source.id},
                new_value={
                    **_serialize_program_cycle(cycle),
                    'cloned_import_templates': cloned_templates,
                },
                commit=False,
            )
        db.session.commit()
    except IntegrityError as exc:
        _handle_program_integrity_error(exc)
    except Exception:
        db.session.rollback()
        raise

    return cycle


def _clone_cycle_import_templates(source_cycle, target_cycle, user_id=None):
    from app.models import ImportTemplate

    cloned_count = 0
    templates = ImportTemplate.query.filter_by(program_cycle_id=source_cycle.id, is_active=True).all()
    for template in templates:
        db.session.add(ImportTemplate(
            program_id=target_cycle.program_id,
            program_cycle_id=target_cycle.id,
            cloned_from_template_id=template.id,
            name=f'{template.name} FY {target_cycle.fiscal_year}',
            file_type=template.file_type,
            version_number=1,
            status='draft',
            schema_signature=template.schema_signature,
            sheet_mappings=template.sheet_mappings or {},
            column_mappings=template.column_mappings or {},
            transform_rules=template.transform_rules or {},
            is_active=True,
            created_by=user_id,
        ))
        cloned_count += 1
    return cloned_count


def _validate_cycle_fields(fiscal_year, cycle_code):
    _validate_fiscal_year(fiscal_year)
    if not str(cycle_code or '').strip():
        raise ProgramError('Cycle code is required', 422)


def _validate_fiscal_year(fiscal_year):
    if not isinstance(fiscal_year, int) or isinstance(fiscal_year, bool) or fiscal_year < 2000 or fiscal_year > 2100:
        raise ProgramError('Fiscal year must be between 2000 and 2100', 422)


# ── Program Phase CRUD ─────────────────────────────────────────────────────

def create_phase(program_id, name, phase_order, description=None, user_id=None):
    program = db.session.get(Program, program_id)
    if not program:
        raise ProgramError('Program not found', 404)

    name = _clean_required_text(name, 'Phase name')
    phase_order = _validate_positive_int(phase_order, 'Phase order must be a positive integer')

    # Check for duplicate order within the same program
    existing = ProgramPhase.query.filter_by(program_id=program_id, phase_order=phase_order).first()
    if existing:
        raise ProgramError(f'Phase order {phase_order} already exists for this program', 409)

    phase = ProgramPhase(
        program_id=program_id,
        name=name,
        phase_order=phase_order,
        description=_clean_optional_text(description),
    )
    db.session.add(phase)
    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='create',
                entity_type='program_phase',
                entity_id=phase.id,
                old_value=None,
                new_value=_serialize_phase(phase),
                commit=False,
            )
        db.session.commit()
    except IntegrityError as exc:
        _handle_program_integrity_error(exc, default_phase_order=phase_order)
    except Exception:
        db.session.rollback()
        raise

    return phase


def list_phases(program_id):
    program = db.session.get(Program, program_id)
    if not program:
        raise ProgramError('Program not found', 404)

    phases = ProgramPhase.query.filter_by(program_id=program_id).order_by(ProgramPhase.phase_order).all()
    return [_serialize_phase(ph) for ph in phases]


def update_phase(phase_id, data, user_id=None):
    phase = db.session.get(ProgramPhase, phase_id)
    if not phase:
        raise ProgramError('Phase not found', 404)

    before = _serialize_phase(phase)
    target_order = None

    if 'name' in data:
        phase.name = _clean_required_text(data['name'], 'Phase name', 'Phase name cannot be blank')
    if 'phase_order' in data:
        target_order = _validate_positive_int(data['phase_order'], 'Phase order must be a positive integer')
        # Check for duplicate order within the same program
        existing = ProgramPhase.query.filter(
            ProgramPhase.program_id == phase.program_id,
            ProgramPhase.phase_order == target_order,
            ProgramPhase.id != phase_id,
        ).first()
        if existing:
            raise ProgramError(f'Phase order {target_order} already exists for this program', 409)
        phase.phase_order = target_order
    if 'description' in data:
        phase.description = _clean_optional_text(data['description'])

    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='update',
                entity_type='program_phase',
                entity_id=phase.id,
                old_value=before,
                new_value=_serialize_phase(phase),
                commit=False,
            )
        db.session.commit()
    except IntegrityError as exc:
        _handle_program_integrity_error(exc, default_phase_order=target_order)
    except Exception:
        db.session.rollback()
        raise

    return phase


def delete_phase(phase_id, user_id=None):
    phase = db.session.get(ProgramPhase, phase_id)
    if not phase:
        raise ProgramError('Phase not found', 404)

    req_count = Requirement.query.filter_by(phase_id=phase_id).count()
    if req_count > 0:
        raise ProgramError(f'Cannot delete phase with {req_count} requirement(s). Remove requirements first.', 409)

    before = _serialize_phase(phase)
    db.session.delete(phase)
    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='delete',
                entity_type='program_phase',
                entity_id=phase_id,
                old_value=before,
                new_value=None,
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {'message': 'Phase deleted successfully'}


# ── Requirement CRUD ───────────────────────────────────────────────────────

def create_requirement(phase_id, name, requirement_type='document', description=None,
                       annex_reference=None, sort_order=0, is_mandatory=True,
                       has_sla=False, sla_days=None, custom_field_schema=None,
                       checker_configuration=None,
                       document_category=None,
                       user_id=None, confirm_similar=False):
    phase = db.session.get(ProgramPhase, phase_id)
    if not phase:
        raise ProgramError('Phase not found', 404)

    if requirement_type not in VALID_REQ_TYPES:
        raise ProgramError(f'Invalid requirement_type. Must be one of: {", ".join(VALID_REQ_TYPES)}', 422)
    if document_category is not None and document_category not in VALID_DOCUMENT_CATEGORIES:
        raise ProgramError(
            f'Invalid document_category. Must be one of: {", ".join(VALID_DOCUMENT_CATEGORIES)}', 422,
        )

    standardized_name = _clean_requirement_name(name, 'Requirement name is required')
    standardized_annex = standardize_annex_reference(annex_reference)
    is_mandatory = _require_bool(is_mandatory, 'is_mandatory')
    has_sla = _require_bool(has_sla, 'has_sla')
    if has_sla and sla_days is None:
        raise ProgramError('SLA days is required when has_sla is true', 422)
    if sla_days is not None:
        sla_days = _validate_positive_int(sla_days, 'SLA days must be a positive integer')
    _assert_requirement_unique_or_confirmed(
        phase.program_id,
        standardized_name,
        annex_reference=standardized_annex,
        confirm_similar=confirm_similar,
    )

    schema = dict(custom_field_schema or {})
    if checker_configuration is not None:
        schema['checker_configuration'] = checker_configuration

    req = Requirement(
        phase_id=phase_id,
        name=standardized_name,
        requirement_type=requirement_type,
        document_category=document_category,
        description=_clean_optional_text(description),
        annex_reference=standardized_annex,
        sort_order=sort_order,
        is_mandatory=is_mandatory,
        has_sla=has_sla,
        sla_days=sla_days,
        custom_field_schema=schema,
    )
    db.session.add(req)
    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='create',
                entity_type='requirement',
                entity_id=req.id,
                old_value=None,
                new_value=_serialize_requirement(req),
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return req


def _assert_requirement_unique_or_confirmed(program_id, name, annex_reference=None,
                                            exclude_requirement_id=None, confirm_similar=False):
    candidates = find_requirement_candidates(
        program_id,
        name,
        annex_reference=annex_reference,
        include_project_snapshots=True,
        exclude_requirement_id=exclude_requirement_id,
    )
    exact = [
        candidate for candidate in candidates
        if candidate['score'] >= EXACT_MATCH_THRESHOLD
        or normalize_label(candidate.get('name')) == normalize_label(name)
    ]
    if exact:
        raise ProgramError(
            'A matching requirement already exists in this program.',
            409,
            errors={'requirement_similarity': {
                'type': 'exact',
                'submitted_name': name,
                'candidates': [_serialize_requirement_candidate(candidate) for candidate in exact[:5]],
            }},
        )
    if candidates and not confirm_similar:
        raise ProgramError(
            'This requirement looks similar to existing requirements in this program.',
            409,
            errors={'requirement_similarity': {
                'type': 'similar',
                'submitted_name': name,
                'requires_confirmation': True,
                'candidates': [_serialize_requirement_candidate(candidate) for candidate in candidates[:5]],
            }},
        )


def _serialize_requirement_candidate(candidate):
    return {
        'id': candidate.get('id'),
        'name': candidate.get('name'),
        'phase_name': candidate.get('phase_name'),
        'annex_reference': candidate.get('annex_reference'),
        'score': round(candidate.get('score') or 0, 3),
        'match_type': candidate.get('match_type'),
        'matched_on': candidate.get('matched_on'),
    }


def _resolve_program_cycle(program_id, program_cycle_id=None, fiscal_year=None):
    if program_cycle_id is not None:
        cycle = db.session.get(ProgramCycle, program_cycle_id)
        if not cycle or cycle.program_id != program_id:
            raise ProgramError('Program cycle not found for this program', 404)
        return cycle
    if fiscal_year is not None:
        return (
            ProgramCycle.query
            .filter_by(program_id=program_id, fiscal_year=fiscal_year, is_active=True)
            .order_by(ProgramCycle.name.asc(), ProgramCycle.id.asc())
            .first()
        )
    return None


def list_requirements(phase_id=None, program_id=None, requirement_type=None, is_mandatory=None,
                      program_cycle_id=None, fiscal_year=None):
    query = Requirement.query

    if phase_id:
        query = query.filter_by(phase_id=phase_id)
    if program_id:
        query = query.join(ProgramPhase).filter(ProgramPhase.program_id == program_id)
        cycle = _resolve_program_cycle(program_id, program_cycle_id=program_cycle_id, fiscal_year=fiscal_year)
        if cycle is not None:
            query = query.filter(db.or_(
                Requirement.program_cycle_id == cycle.id,
                Requirement.program_cycle_id.is_(None),
            ))
        else:
            query = query.filter(Requirement.program_cycle_id.is_(None))
    elif program_cycle_id is not None:
        cycle = get_program_cycle(program_cycle_id)
        query = query.filter(db.or_(
            Requirement.program_cycle_id == cycle.id,
            Requirement.program_cycle_id.is_(None),
        ))
    if requirement_type:
        query = query.filter_by(requirement_type=requirement_type)
    if is_mandatory is not None:
        query = query.filter_by(is_mandatory=is_mandatory)

    requirements = query.order_by(Requirement.sort_order).all()
    return [_serialize_requirement(r) for r in requirements]


def get_requirement(requirement_id):
    req = db.session.get(Requirement, requirement_id)
    if not req:
        raise ProgramError('Requirement not found', 404)
    return req


def update_requirement(requirement_id, data, user_id=None):
    req = db.session.get(Requirement, requirement_id)
    if not req:
        raise ProgramError('Requirement not found', 404)

    before = _serialize_requirement(req)

    if 'name' in data:
        standardized_name = _clean_requirement_name(data['name'], 'Requirement name cannot be blank')
        _assert_requirement_unique_or_confirmed(
            req.phase.program_id,
            standardized_name,
            annex_reference=data.get('annex_reference', req.annex_reference),
            exclude_requirement_id=req.id,
            confirm_similar=data.get('confirm_similar', False),
        )
        req.name = standardized_name
    if 'description' in data:
        req.description = _clean_optional_text(data['description'])
    if 'requirement_type' in data:
        if data['requirement_type'] not in VALID_REQ_TYPES:
            raise ProgramError(f'Invalid requirement_type. Must be one of: {", ".join(VALID_REQ_TYPES)}', 422)
        req.requirement_type = data['requirement_type']
    if 'document_category' in data:
        category = data['document_category']
        if category is not None and category not in VALID_DOCUMENT_CATEGORIES:
            raise ProgramError(
                f'Invalid document_category. Must be one of: {", ".join(VALID_DOCUMENT_CATEGORIES)}', 422,
            )
        req.document_category = category
    if 'annex_reference' in data:
        req.annex_reference = standardize_annex_reference(data['annex_reference'])
    if 'sort_order' in data:
        req.sort_order = data['sort_order']
    if 'is_mandatory' in data:
        req.is_mandatory = _require_bool(data['is_mandatory'], 'is_mandatory')
    if 'has_sla' in data:
        req.has_sla = _require_bool(data['has_sla'], 'has_sla')
    if 'sla_days' in data:
        req.sla_days = (
            _validate_positive_int(data['sla_days'], 'SLA days must be a positive integer')
            if data['sla_days'] is not None
            else None
        )
    if req.has_sla and not req.sla_days:
        raise ProgramError('SLA days is required when has_sla is true', 422)
    if 'custom_field_schema' in data:
        req.custom_field_schema = data['custom_field_schema']
    if 'checker_configuration' in data:
        schema = dict(req.custom_field_schema or {})
        schema['checker_configuration'] = data['checker_configuration']
        req.custom_field_schema = schema

    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='update',
                entity_type='requirement',
                entity_id=req.id,
                old_value=before,
                new_value=_serialize_requirement(req),
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return req


def delete_requirement(requirement_id, user_id=None):
    req = db.session.get(Requirement, requirement_id)
    if not req:
        raise ProgramError('Requirement not found', 404)

    # Check if referenced by project requirements
    from app.models import ProjectRequirement
    ref_count = ProjectRequirement.query.filter_by(requirement_id=requirement_id).count()
    if ref_count > 0:
        raise ProgramError(f'Cannot delete requirement referenced by {ref_count} project requirement(s)', 409)

    before = _serialize_requirement(req)
    db.session.delete(req)
    try:
        db.session.flush()
        if user_id is not None:
            audit_service.log_action(
                user_id=user_id,
                action='delete',
                entity_type='requirement',
                entity_id=requirement_id,
                old_value=before,
                new_value=None,
                commit=False,
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {'message': 'Requirement deleted successfully'}


# ── Requirement Matrix (full program with phases & requirements) ──────────

def get_available_fiscal_years(include_current=True):
    from datetime import datetime

    years = {
        year for (year,) in db.session.query(Project.fiscal_year).filter(Project.fiscal_year.isnot(None)).distinct().all()
    }
    years.update(
        year for (year,) in db.session.query(ProgramCycle.fiscal_year).filter(ProgramCycle.fiscal_year.isnot(None)).distinct().all()
    )
    if include_current:
        years.add(datetime.now().year)

    ordered = sorted(years, reverse=True)
    return {
        'years': ordered,
        'default_fiscal_year': ordered[0] if ordered else datetime.now().year,
    }


def get_program_matrix(program_id, program_cycle_id=None, fiscal_year=None, baseline_only=False):
    program = db.session.get(Program, program_id)
    if not program:
        raise ProgramError('Program not found', 404)
    if baseline_only and program_cycle_id is not None:
        raise ProgramError('baseline_only cannot be combined with program_cycle_id', 422)
    cycle = (
        None
        if baseline_only
        else _resolve_program_cycle(program_id, program_cycle_id=program_cycle_id, fiscal_year=fiscal_year)
    )
    selected_cycle_id = cycle.id if cycle else None

    phases = ProgramPhase.query.filter_by(program_id=program_id).order_by(ProgramPhase.phase_order).all()
    phases_data = []
    for ph in phases:
        req_query = Requirement.query.filter_by(phase_id=ph.id)
        if cycle is not None:
            req_query = req_query.filter(db.or_(
                Requirement.program_cycle_id == cycle.id,
                Requirement.program_cycle_id.is_(None),
            ))
        else:
            req_query = req_query.filter(Requirement.program_cycle_id.is_(None))
        reqs = req_query.order_by(Requirement.sort_order).all()
        phases_data.append({
            **_serialize_phase(ph),
            'requirements_count': len(reqs),
            'requirements': [_serialize_requirement(r) for r in reqs],
        })

    return {
        **_serialize_program(program, fiscal_year=fiscal_year),
        'selected_fiscal_year': fiscal_year or (cycle.fiscal_year if cycle else None),
        'selected_program_cycle_id': selected_cycle_id,
        'selected_program_cycle': _serialize_program_cycle(cycle) if cycle else None,
        'phases': phases_data,
    }


# ── Serializers ────────────────────────────────────────────────────────────

def _serialize_program(program, fiscal_year=None):
    cycles_query = program.cycles
    projects_query = program.projects
    if fiscal_year is not None:
        cycles_query = cycles_query.filter(ProgramCycle.fiscal_year == fiscal_year)
        projects_query = projects_query.filter(Project.fiscal_year == fiscal_year)
    return {
        'id': program.id,
        'name': program.name,
        'code': program.code,
        'description': program.description,
        'program_type': program.program_type,
        'funding_agency': program.funding_agency,
        'is_active': program.is_active,
        'project_custom_field_schema': program.project_custom_field_schema,
        'phases_count': program.phases.count(),
        'cycles_count': cycles_query.count(),
        'projects_count': projects_query.count(),
        'selected_fiscal_year': fiscal_year,
        'created_at': program.created_at.isoformat() if program.created_at else None,
        'updated_at': program.updated_at.isoformat() if program.updated_at else None,
    }


def _serialize_program_cycle(cycle):
    source = db.session.get(ProgramCycle, cycle.cloned_from_cycle_id) if cycle.cloned_from_cycle_id else None
    return {
        'id': cycle.id,
        'program_id': cycle.program_id,
        'program_name': cycle.program.name if cycle.program else None,
        'cloned_from_cycle_id': cycle.cloned_from_cycle_id,
        'cloned_from_cycle_name': source.name if source else None,
        'name': cycle.name,
        'fiscal_year': cycle.fiscal_year,
        'cycle_code': cycle.cycle_code,
        'source_template_name': cycle.source_template_name,
        'import_profile': cycle.import_profile or {},
        'field_schema': cycle.field_schema or {},
        'is_active': cycle.is_active,
        'projects_count': cycle.projects.count(),
        'import_templates_count': cycle.import_templates.count(),
        'created_at': cycle.created_at.isoformat() if cycle.created_at else None,
        'updated_at': cycle.updated_at.isoformat() if cycle.updated_at else None,
    }


def _serialize_phase(phase):
    return {
        'id': phase.id,
        'program_id': phase.program_id,
        'name': phase.name,
        'phase_order': phase.phase_order,
        'description': phase.description,
        'requirements_count': phase.requirements.count(),
        'created_at': phase.created_at.isoformat() if phase.created_at else None,
    }


def _serialize_requirement(req):
    return {
        'id': req.id,
        'phase_id': req.phase_id,
        'program_cycle_id': req.program_cycle_id,
        'created_from_mapping_decision_id': req.created_from_mapping_decision_id,
        'name': req.name,
        'description': req.description,
        'requirement_type': req.requirement_type,
        'document_category': req.document_category,
        'annex_reference': req.annex_reference,
        'sort_order': req.sort_order,
        'is_mandatory': req.is_mandatory,
        'has_sla': req.has_sla,
        'sla_days': req.sla_days,
        'custom_field_schema': req.custom_field_schema,
        'checker_configuration': (req.custom_field_schema or {}).get('checker_configuration') if isinstance(req.custom_field_schema, dict) else {},
        'source_label': req.source_label,
        'source_sheet_name': req.source_sheet_name,
        'source_column': req.source_column,
        'created_at': req.created_at.isoformat() if req.created_at else None,
        'updated_at': req.updated_at.isoformat() if req.updated_at else None,
    }
