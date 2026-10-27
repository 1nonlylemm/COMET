"""
COMET Bulk Project Service
Authoritative canonical service for controlled multi-record project CRU operations.

Enforces:
- Deterministic target selection and size limits (max 50)
- Scope authorization and partial-scope request rejection (no silent partial execution)
- Change set calculation and idempotency detection
- Deterministic preview fingerprinting (SHA-256)
- Row-level locking and revalidation before commit (staleness protection)
- Atomic all-or-nothing execution with rollback
- Traceable per-record and bulk audit logging
"""

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal

from app.extensions import db
from app.models import (
    LguCluster,
    LguProfile,
    Program,
    ProgramCycle,
    Project,
)
from app.services import (
    access_service,
    audit_service,
    project_service,
)
from app.services.project_status import CANONICAL_PROJECT_STATUSES, normalize_project_status

MAX_BULK_TARGET_COUNT = 50

# Allowlisted metadata fields for bulk update
ALLOWED_BULK_METADATA_FIELDS = (
    'notes',
    'subaybayan_project_code',
    'subaybayan_url',
    'subaybayan_enrollment_status',
    'qaar_category',
    'monitoring_applicability',
    'custom_fields',
)

# Blocked high-impact fields in bulk metadata
BLOCKED_BULK_METADATA_FIELDS = (
    'budget_amount',
    'lgu_id',
    'program_id',
    'program_cycle_id',
    'current_phase',
    'overall_status',
    'project_name',
    'project_kind',
)

# Allowlisted schedule fields for bulk update
ALLOWED_BULK_SCHEDULE_FIELDS = (
    'target_start_date',
    'target_end_date',
    'actual_start_date',
    'actual_end_date',
)

# SQL-like keywords blocked from selector and text arguments
SQL_INJECTION_PATTERN = re.compile(
    r'\b(SELECT|DROP|UNION|INSERT|DELETE|UPDATE|TRUNCATE|ALTER|EXEC|SHUTDOWN)\b',
    re.IGNORECASE,
)


class BulkProjectError(Exception):
    def __init__(self, message, status_code=400, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _assert_no_sql_injection(value, field_name='selector'):
    if isinstance(value, str) and SQL_INJECTION_PATTERN.search(value):
        raise BulkProjectError(
            f"Invalid syntax in {field_name}: SQL expressions are prohibited.",
            422,
        )


def _parse_date(date_val):
    if not date_val:
        return None
    if isinstance(date_val, (date, datetime)):
        return date_val if isinstance(date_val, date) else date_val.date()
    try:
        return datetime.strptime(str(date_val).strip()[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise BulkProjectError(f"Invalid date format: {date_val}. Expected YYYY-MM-DD.", 422)


def _serialize_json_friendly(val):
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    return val


CORE_GOVERNANCE_FIELDS = (
    'lgu_id',
    'program_id',
    'program_cycle_id',
    'fiscal_year',
    'overall_status',
)


def _get_effective_cluster_id(project):
    """Resolves effective cluster ID directly or via associated LGU."""
    if getattr(project, 'cluster_id', None) is not None:
        return project.cluster_id
    lgu = getattr(project, 'lgu', None)
    if lgu and getattr(lgu, 'cluster_id', None) is not None:
        return lgu.cluster_id
    return None


def _is_project_movement_allowed(project):
    """Checks whether project movement gate is open (associated program active)."""
    program = getattr(project, 'program', None)
    if program and hasattr(program, 'is_active'):
        return bool(program.is_active)
    return True


def compute_bulk_preview_fingerprint(projects, updates):
    """
    Computes a deterministic SHA-256 hash representing the exact state of target records,
    governance/scope invariants, eligibility fields, and proposed updates at preview time.
    Excludes unrelated fields (e.g. project_name, descriptions, timestamps) to prevent false invalidations.
    """
    targets_state = []
    update_keys = sorted(updates.keys())
    has_schedule_updates = any(k in ALLOWED_BULK_SCHEDULE_FIELDS for k in update_keys)

    for p in sorted(projects, key=lambda x: x.id):
        state_fields = {}
        # 1. State for fields proposed to be updated
        for k in update_keys:
            cur = getattr(p, k, None)
            state_fields[k] = _serialize_json_friendly(cur)

        # 2. Scope, eligibility, and governance fields
        for gf in CORE_GOVERNANCE_FIELDS:
            state_fields[gf] = _serialize_json_friendly(getattr(p, gf, None))

        state_fields['effective_cluster_id'] = _get_effective_cluster_id(p)
        state_fields['movement_allowed'] = _is_project_movement_allowed(p)

        # 3. Schedule validation dependency fields (when updating schedule)
        if has_schedule_updates:
            for sf in ALLOWED_BULK_SCHEDULE_FIELDS:
                state_fields[sf] = _serialize_json_friendly(getattr(p, sf, None))

        targets_state.append({'id': p.id, 'fields': state_fields})

    fingerprint_payload = {
        'targets': targets_state,
        'updates': {k: _serialize_json_friendly(updates[k]) for k in update_keys},
    }
    encoded = json.dumps(fingerprint_payload, sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def resolve_bulk_project_targets(selectors, user_id=None):
    """
    Resolves a deterministic list of Project records matching given selectors.
    Enforces scope rules, detects partial-scope requests, and applies the size limit.
    """
    if not isinstance(selectors, dict) or not selectors:
        raise BulkProjectError(
            "Target selection is underspecified. Please specify an LGU, Cluster, Program, Fiscal Year, or explicit Project IDs.",
            422,
        )

    for k, v in selectors.items():
        _assert_no_sql_injection(v, field_name=k)

    project_ids = selectors.get('project_ids')
    lgu_id = selectors.get('lgu_id')
    cluster_id = selectors.get('cluster_id')
    program_id = selectors.get('program_id')
    program_cycle_id = selectors.get('program_cycle_id')
    fiscal_year = selectors.get('fiscal_year')
    status = selectors.get('project_status') or selectors.get('status') or selectors.get('overall_status')
    project_kind = selectors.get('project_kind')

    has_selector = any([
        project_ids,
        lgu_id,
        cluster_id,
        program_id,
        program_cycle_id,
        fiscal_year,
        status,
        project_kind,
    ])
    if not has_selector:
        raise BulkProjectError(
            "Target selection is underspecified. Please specify an LGU, Cluster, Program, Fiscal Year, or explicit Project IDs.",
            422,
        )

    # 1. Build Base Unrestricted Query
    base_query = Project.query

    if project_ids:
        if not isinstance(project_ids, (list, tuple)):
            raise BulkProjectError("project_ids must be a list of integers.", 422)
        try:
            p_ids = [int(x) for x in project_ids]
        except (ValueError, TypeError):
            raise BulkProjectError("project_ids must contain valid integers.", 422)
        if not p_ids:
            raise BulkProjectError("project_ids list cannot be empty.", 422)
        base_query = base_query.filter(Project.id.in_(p_ids))

    if lgu_id:
        try:
            lgu_id = int(lgu_id)
        except (ValueError, TypeError):
            raise BulkProjectError("lgu_id must be an integer.", 422)
        base_query = base_query.filter(Project.lgu_id == lgu_id)

    if cluster_id:
        try:
            cluster_id = int(cluster_id)
        except (ValueError, TypeError):
            raise BulkProjectError("cluster_id must be an integer.", 422)
        base_query = base_query.filter(Project.lgu.has(LguProfile.cluster_id == cluster_id))

    if program_id:
        try:
            program_id = int(program_id)
        except (ValueError, TypeError):
            raise BulkProjectError("program_id must be an integer.", 422)
        base_query = base_query.filter(Project.program_id == program_id)

    if program_cycle_id:
        try:
            program_cycle_id = int(program_cycle_id)
        except (ValueError, TypeError):
            raise BulkProjectError("program_cycle_id must be an integer.", 422)
        base_query = base_query.filter(Project.program_cycle_id == program_cycle_id)

    if fiscal_year:
        try:
            fiscal_year = int(fiscal_year)
        except (ValueError, TypeError):
            raise BulkProjectError("fiscal_year must be an integer.", 422)
        base_query = base_query.filter(Project.fiscal_year == fiscal_year)

    if status:
        norm_status = normalize_project_status(status, default=status)
        base_query = base_query.filter(Project.overall_status == norm_status)

    if project_kind:
        base_query = base_query.filter(Project.project_kind == str(project_kind).strip())

    unrestricted_projects = base_query.order_by(Project.id.asc()).all()
    unrestricted_count = len(unrestricted_projects)

    # 2. Scope Security & Partial Scope Detection
    if user_id is not None:
        user = access_service.get_user(user_id)
        if user.role not in ('admin', 'staff'):
            raise BulkProjectError(
                f"Your role ({user.role}) does not have permission to execute bulk project operations. Only Admins and Staff are authorized.",
                403,
            )

        scoped_query = access_service.restrict_project_query(base_query, user_id)
        scoped_projects = scoped_query.order_by(Project.id.asc()).all()
        scoped_count = len(scoped_projects)

        # Partial scope check: did the user request targets outside their scope?
        if user.role == 'staff' and unrestricted_count > scoped_count:
            raise BulkProjectError(
                "Your requested scope includes records outside your assigned clusters. Please narrow the selection.",
                403,
            )
        if user.role == 'field_officer' and unrestricted_count > scoped_count:
            raise BulkProjectError(
                "Your requested scope includes records outside your assigned LGUs. Please narrow the selection.",
                403,
            )
        if user.role == 'system_admin':
            raise BulkProjectError(
                "System Administrators do not have operational authority to mutate project records.",
                403,
            )

        matching_projects = scoped_projects
    else:
        matching_projects = unrestricted_projects

    target_count = len(matching_projects)

    # Size limit enforcement (Section 28)
    if target_count > MAX_BULK_TARGET_COUNT:
        raise BulkProjectError(
            f"This request affects {target_count} records, which exceeds the conversational bulk-action limit of {MAX_BULK_TARGET_COUNT}. Please narrow the selection.",
            422,
            details={'target_count': target_count, 'limit': MAX_BULK_TARGET_COUNT},
        )

    return matching_projects


def calculate_project_metadata_changes(projects, update_fields, user_id=None):
    """
    Validates metadata fields against the strict allowlist, checks movement pauses,
    and calculates changed vs unchanged records (idempotency).
    """
    if not isinstance(update_fields, dict) or not update_fields:
        raise BulkProjectError("No update fields provided for bulk metadata update.", 422)

    # Check for blocked high-impact fields
    for blocked_f in BLOCKED_BULK_METADATA_FIELDS:
        if blocked_f in update_fields:
            if blocked_f == 'budget_amount':
                msg = "Budget updates must be performed using the update_project_budget action."
            elif blocked_f == 'current_phase':
                msg = "Project phase transitions must be processed through the formal project lifecycle workflow."
            elif blocked_f == 'overall_status':
                msg = "Project status updates must be performed using the bulk_update_project_status action."
            else:
                msg = f"Field '{blocked_f}' cannot be modified in bulk metadata updates. Reassignment must be performed individually."
            raise BulkProjectError(msg, 422)

    # Allowlist check
    valid_updates = {}
    for k, v in update_fields.items():
        if k not in ALLOWED_BULK_METADATA_FIELDS:
            raise BulkProjectError(
                f"Field '{k}' cannot be modified with bulk_update_project_metadata. Allowed fields: {', '.join(ALLOWED_BULK_METADATA_FIELDS)}.",
                422,
            )
        _assert_no_sql_injection(v, field_name=k)
        valid_updates[k] = v

    changed_projects = []
    unchanged_projects = []

    for p in projects:
        # Check project movement
        try:
            access_service.assert_project_movement_allowed(p)
        except access_service.AccessError as exc:
            raise BulkProjectError(f"Project #{p.id} movement is paused: {exc.message}", 409)

        # Compare values
        diff = {}
        for k, new_val in valid_updates.items():
            cur_val = getattr(p, k, None)
            cur_norm = _clean_str(cur_val) if isinstance(cur_val, str) else cur_val
            new_norm = _clean_str(new_val) if isinstance(new_val, str) else new_val
            if cur_norm != new_norm:
                diff[k] = {'from': cur_val, 'to': new_val}

        if diff:
            changed_projects.append({'project': p, 'diff': diff})
        else:
            unchanged_projects.append({'project': p})

    fingerprint = compute_bulk_preview_fingerprint(projects, valid_updates)

    return {
        'operation': 'bulk_update_project_metadata',
        'target_count': len(projects),
        'target_ids': [p.id for p in projects],
        'changed_count': len(changed_projects),
        'unchanged_count': len(unchanged_projects),
        'blocked_count': 0,
        'updates': valid_updates,
        'preview_fingerprint': fingerprint,
        'changed_samples': [
            {'id': item['project'].id, 'name': item['project'].project_name, 'diff': item['diff']}
            for item in changed_projects[:5]
        ],
    }


def calculate_project_schedule_changes(projects, schedule_fields, user_id=None):
    """
    Validates schedule fields and date ordering, checks movement pauses,
    and calculates changed vs unchanged records (idempotency).
    """
    if not isinstance(schedule_fields, dict) or not schedule_fields:
        raise BulkProjectError("No schedule dates provided for bulk schedule update.", 422)

    valid_updates = {}
    for k, v in schedule_fields.items():
        if k not in ALLOWED_BULK_SCHEDULE_FIELDS:
            raise BulkProjectError(
                f"Field '{k}' cannot be modified with bulk_update_project_schedule. Allowed fields: {', '.join(ALLOWED_BULK_SCHEDULE_FIELDS)}.",
                422,
            )
        parsed = _parse_date(v)
        valid_updates[k] = parsed

    # Validate date ordering if both start and end dates provided
    t_start = valid_updates.get('target_start_date')
    t_end = valid_updates.get('target_end_date')
    if t_start and t_end and t_end < t_start:
        raise BulkProjectError("Target end date must be on or after target start date.", 422)

    a_start = valid_updates.get('actual_start_date')
    a_end = valid_updates.get('actual_end_date')
    if a_start and a_end and a_end < a_start:
        raise BulkProjectError("Actual end date must be on or after actual start date.", 422)

    changed_projects = []
    unchanged_projects = []

    for p in projects:
        try:
            access_service.assert_project_movement_allowed(p)
        except access_service.AccessError as exc:
            raise BulkProjectError(f"Project #{p.id} movement is paused: {exc.message}", 409)

        # Cross check per project against current start/end dates
        eff_t_start = t_start or p.target_start_date
        eff_t_end = t_end or p.target_end_date
        if eff_t_start and eff_t_end and eff_t_end < eff_t_start:
            raise BulkProjectError(
                f"Project #{p.id} target end date ({eff_t_end}) would precede target start date ({eff_t_start}).",
                422,
            )

        diff = {}
        for k, new_date in valid_updates.items():
            cur_date = getattr(p, k, None)
            if cur_date != new_date:
                diff[k] = {
                    'from': cur_date.isoformat() if cur_date else None,
                    'to': new_date.isoformat() if new_date else None,
                }

        if diff:
            changed_projects.append({'project': p, 'diff': diff})
        else:
            unchanged_projects.append({'project': p})

    # Prepare string serializable updates for fingerprint and display
    serializable_updates = {k: v.isoformat() if v else None for k, v in valid_updates.items()}
    fingerprint = compute_bulk_preview_fingerprint(projects, serializable_updates)

    return {
        'operation': 'bulk_update_project_schedule',
        'target_count': len(projects),
        'target_ids': [p.id for p in projects],
        'changed_count': len(changed_projects),
        'unchanged_count': len(unchanged_projects),
        'blocked_count': 0,
        'updates': serializable_updates,
        'preview_fingerprint': fingerprint,
        'changed_samples': [
            {'id': item['project'].id, 'name': item['project'].project_name, 'diff': item['diff']}
            for item in changed_projects[:5]
        ],
    }


def calculate_project_status_changes(projects, status_payload, user_id=None):
    """
    Validates operational status (not_yet_started, ongoing, suspended; rejects completed),
    checks movement pauses, and calculates changed vs unchanged records (idempotency).
    """
    if not isinstance(status_payload, dict):
        status_payload = {'overall_status': status_payload}

    raw_status = status_payload.get('overall_status') or status_payload.get('status')
    if not raw_status:
        raise BulkProjectError("overall_status is required for bulk status update.", 422)

    norm_status = normalize_project_status(raw_status, default=str(raw_status).strip().lower())
    if norm_status == 'completed':
        raise BulkProjectError("Project completion must be processed through the completion closeout service.", 422)
    if norm_status not in ('not_yet_started', 'ongoing', 'cancelled'):
        raise BulkProjectError(
            f"Invalid overall_status: '{raw_status}'. Allowed values for bulk update: not_yet_started, ongoing, suspended (cancelled).",
            422,
        )

    valid_updates = {'overall_status': norm_status}
    changed_projects = []
    unchanged_projects = []

    for p in projects:
        try:
            access_service.assert_project_movement_allowed(p)
        except access_service.AccessError as exc:
            raise BulkProjectError(f"Project #{p.id} movement is paused: {exc.message}", 409)

        diff = {}
        if p.overall_status != norm_status:
            diff['overall_status'] = {'from': p.overall_status, 'to': norm_status}

        if diff:
            changed_projects.append({'project': p, 'diff': diff})
        else:
            unchanged_projects.append({'project': p})

    fingerprint = compute_bulk_preview_fingerprint(projects, valid_updates)
    alias_note = None
    if str(raw_status).strip().lower() in ('suspended', 'suspend'):
        alias_note = "Status 'suspended' is an operational alias normalized to database-canonical status 'cancelled'."

    return {
        'operation': 'bulk_update_project_status',
        'target_count': len(projects),
        'target_ids': [p.id for p in projects],
        'changed_count': len(changed_projects),
        'unchanged_count': len(unchanged_projects),
        'blocked_count': 0,
        'updates': valid_updates,
        'alias_note': alias_note,
        'preview_fingerprint': fingerprint,
        'changed_samples': [
            {'id': item['project'].id, 'name': item['project'].project_name, 'diff': item['diff']}
            for item in changed_projects[:5]
        ],
    }


def execute_bulk_project_update(operation, target_ids, updates, preview_fingerprint, selection, user_id):
    """
    Executes atomic, transactional bulk update over target projects with row-level locks.
    Revalidates existence, scope, and fingerprint staleness.
    Rolls back entirely on any error.
    """
    if not target_ids:
        raise BulkProjectError("No target projects to update.", 422)

    user = access_service.get_user(user_id)
    if user.role not in ('admin', 'staff'):
        raise BulkProjectError("Only Administrators and Staff may execute bulk project updates.", 403)

    # 1. Acquire row-level locks on target projects
    locked_projects = (
        Project.query
        .filter(Project.id.in_(target_ids))
        .order_by(Project.id.asc())
        .with_for_update()
        .all()
    )

    # 2. Revalidate Target Count
    if len(locked_projects) != len(target_ids):
        found_ids = {p.id for p in locked_projects}
        missing_ids = set(target_ids) - found_ids
        raise BulkProjectError(
            f"The selected records changed after the preview: projects {sorted(missing_ids)} no longer exist. A new preview is required.",
            409,
        )

    # 3. Revalidate Scope & Movement
    for p in locked_projects:
        try:
            access_service.ensure_project_access(p, user.id)
            access_service.assert_project_movement_allowed(p)
        except access_service.AccessError as exc:
            raise BulkProjectError(
                f"The selected records changed after the preview: project #{p.id} is no longer accessible ({exc.message}). A new preview is required.",
                409,
            )

    # 4. Revalidate Fingerprint Staleness
    current_fingerprint = compute_bulk_preview_fingerprint(locked_projects, updates)
    if preview_fingerprint and current_fingerprint != preview_fingerprint:
        raise BulkProjectError(
            "The selected records changed after the preview. A new preview is required.",
            409,
        )

    # 4.5 Revalidate Schedule Chronological Invariants against live row state
    if any(f in updates for f in ALLOWED_BULK_SCHEDULE_FIELDS):
        for p in locked_projects:
            t_start = _parse_date(updates.get('target_start_date', p.target_start_date))
            t_end = _parse_date(updates.get('target_end_date', p.target_end_date))
            if t_start and t_end and t_end < t_start:
                raise BulkProjectError(
                    f"Project #{p.id} schedule invalidation: target_end_date ({t_end}) cannot be before target_start_date ({t_start}). A new preview is required.",
                    409,
                )
            a_start = _parse_date(updates.get('actual_start_date', p.actual_start_date))
            a_end = _parse_date(updates.get('actual_end_date', p.actual_end_date))
            if a_start and a_end and a_end < a_start:
                raise BulkProjectError(
                    f"Project #{p.id} schedule invalidation: actual_end_date ({a_end}) cannot be before actual_start_date ({a_start}). A new preview is required.",
                    409,
                )

    # 5. Apply Updates Atomically
    changed_count = 0
    unchanged_count = 0

    try:
        from app.services import workbook_sync_service

        for project in locked_projects:
            before_snapshot = project_service._serialize_project(project)
            has_changes = False

            for field_name, new_val in updates.items():
                cur_val = getattr(project, field_name, None)
                if field_name in ALLOWED_BULK_SCHEDULE_FIELDS:
                    parsed_date = _parse_date(new_val)
                    if cur_val != parsed_date:
                        setattr(project, field_name, parsed_date)
                        has_changes = True
                else:
                    if str(cur_val) != str(new_val):
                        setattr(project, field_name, new_val)
                        has_changes = True

            if has_changes:
                changed_count += 1
                # Sync workbook fields if applicable
                wb_fields = project_service._changed_workbook_project_fields(project, updates)
                if wb_fields:
                    try:
                        workbook_sync_service.assert_project_fields_unlocked(project.id, wb_fields)
                        workbook_sync_service.sync_project_fields(project, wb_fields, user_id=user.id, commit=False)
                    except workbook_sync_service.WorkbookSyncError as exc:
                        raise BulkProjectError(
                            f"Project #{project.id} workbook sync failed: {exc.message}",
                            exc.status_code,
                        )

                # Canonical per-record audit log
                audit_service.log_action(
                    user_id=user.id,
                    action='update',
                    entity_type='project',
                    entity_id=project.id,
                    old_value=before_snapshot,
                    new_value=project_service._serialize_project(project),
                    commit=False,
                )
            else:
                unchanged_count += 1

        # Canonical bulk parent audit log
        audit_service.log_action(
            user_id=user.id,
            action=operation,
            entity_type='bulk_project_operation',
            entity_id=0,
            old_value={
                'selection': selection,
                'target_count': len(target_ids),
                'target_ids': target_ids,
            },
            new_value={
                'updates': updates,
                'changed_count': changed_count,
                'unchanged_count': unchanged_count,
            },
            commit=False,
        )

        db.session.commit()

    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, BulkProjectError):
            raise exc
        raise BulkProjectError(f"Bulk update failed during transaction execution: {str(exc)}", 500) from exc

    return {
        'success': True,
        'operation': operation,
        'target_count': len(target_ids),
        'changed_count': changed_count,
        'unchanged_count': unchanged_count,
        'blocked_count': 0,
        'failed_count': 0,
        'audit_logged': True,
        'updates': updates,
    }


def _clean_str(val):
    return str(val).strip() if val is not None else ''
