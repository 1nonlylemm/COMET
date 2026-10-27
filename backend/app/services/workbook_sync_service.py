from datetime import date, datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models import (
    ProjectRequirement,
    Requirement,
    WorkbookCell,
    WorkbookCellChange,
    WorkbookColumn,
    WorkbookRow,
    WorkbookSheet,
    WorkbookWorkspace,
)
from app.services.import_field_catalog import normalize_label


class WorkbookSyncError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


PROJECT_FIELD_BINDINGS = {
    'project_name': 'project.project_name',
    'budget_amount': 'project.budget_amount',
    'overall_status': 'project.overall_status',
    'physical_completion_pct': 'project.physical_completion_pct',
    'source_project_code': 'project.source_project_code',
}


def assert_project_fields_unlocked(project_id, field_names):
    locked = locked_project_fields(project_id, field_names)
    if not locked:
        return
    summary = ', '.join(
        f'{field} ({", ".join(item["cell_ref"] for item in locks[:3])})'
        for field, locks in locked.items()
    )
    raise WorkbookSyncError(
        f'This project field is locked by the workbook workbench. Unlock the bound column first: {summary}.',
        409,
    )


def locked_project_fields(project_id, field_names):
    targets = {
        PROJECT_FIELD_BINDINGS[field]: field
        for field in field_names
        if field in PROJECT_FIELD_BINDINGS
    }
    if not targets:
        return {}

    locked = {}
    for cell, column, row, sheet, workspace in _project_cells_for_targets(
        project_id,
        targets.keys(),
        editable=False,
    ):
        field = targets.get(column.binding_target)
        locked.setdefault(field, []).append(_cell_lock_descriptor(cell, column, sheet, workspace))
    return locked


def project_field_lock_summary(project_id):
    return locked_project_fields(project_id, PROJECT_FIELD_BINDINGS.keys())


def sync_project_fields(project, field_names, user_id=None, commit=False):
    targets = {
        PROJECT_FIELD_BINDINGS[field]: field
        for field in field_names
        if field in PROJECT_FIELD_BINDINGS
    }
    if not targets:
        return 0

    changed_count = 0
    for cell, column, row, sheet, workspace in _project_cells_for_targets(
        project.id,
        targets.keys(),
        editable=True,
    ):
        field = targets.get(column.binding_target)
        value = _json_safe(getattr(project, field, None))
        if _sync_cell(
            cell,
            value,
            workspace_id=workspace.id,
            project_id=project.id,
            binding_target=column.binding_target,
            user_id=user_id,
            reason='Synced from project detail update.',
        ):
            changed_count += 1

    if changed_count and commit:
        db.session.commit()
    return changed_count


def assert_requirement_status_unlocked(requirement):
    locked = [
        _cell_lock_descriptor(cell, column, sheet, workspace)
        for cell, column, row, sheet, workspace in _requirement_status_cells(requirement, editable=False)
    ]
    if not locked:
        return
    summary = ', '.join(item['cell_ref'] for item in locked[:3])
    raise WorkbookSyncError(
        f'This requirement status is locked by the workbook workbench. Unlock the bound column first: {summary}.',
        409,
    )


def sync_requirement_status(requirement, user_id=None, commit=False):
    changed_count = 0
    for cell, column, row, sheet, workspace in _requirement_status_cells(requirement, editable=True):
        value = _json_safe(_status_value_for_column(requirement.status, column))
        if _sync_cell(
            cell,
            value,
            workspace_id=workspace.id,
            project_id=requirement.project_id,
            binding_target=column.binding_target,
            user_id=user_id,
            reason='Synced from project requirement update.',
        ):
            changed_count += 1

    if changed_count and commit:
        db.session.commit()
    return changed_count


def _project_cells_for_targets(project_id, binding_targets, editable=None):
    query = (
        db.session.query(WorkbookCell, WorkbookColumn, WorkbookRow, WorkbookSheet, WorkbookWorkspace)
        .join(WorkbookColumn, WorkbookCell.column_id == WorkbookColumn.id)
        .join(WorkbookRow, WorkbookCell.row_id == WorkbookRow.id)
        .join(WorkbookSheet, WorkbookRow.sheet_id == WorkbookSheet.id)
        .join(WorkbookWorkspace, WorkbookSheet.workspace_id == WorkbookWorkspace.id)
        .filter(
            WorkbookRow.project_id == project_id,
            WorkbookRow.row_state == 'active',
            WorkbookWorkspace.status == 'active',
            WorkbookColumn.binding_target.in_(list(binding_targets)),
        )
    )
    if editable is not None:
        query = query.filter(WorkbookColumn.is_editable.is_(bool(editable)))
    return query.all()


def _requirement_status_cells(requirement, editable=None):
    labels = _requirement_labels(requirement)
    if not labels:
        return []

    query = (
        db.session.query(WorkbookCell, WorkbookColumn, WorkbookRow, WorkbookSheet, WorkbookWorkspace)
        .join(WorkbookColumn, WorkbookCell.column_id == WorkbookColumn.id)
        .join(WorkbookRow, WorkbookCell.row_id == WorkbookRow.id)
        .join(WorkbookSheet, WorkbookRow.sheet_id == WorkbookSheet.id)
        .join(WorkbookWorkspace, WorkbookSheet.workspace_id == WorkbookWorkspace.id)
        .filter(
            WorkbookRow.project_id == requirement.project_id,
            WorkbookRow.row_state == 'active',
            WorkbookWorkspace.status == 'active',
            WorkbookColumn.binding_target.like('project_requirement.status:%'),
        )
    )
    if editable is not None:
        query = query.filter(WorkbookColumn.is_editable.is_(bool(editable)))

    matched = []
    for cell, column, row, sheet, workspace in query.all():
        target_label = column.binding_target.split(':', 1)[1] if ':' in column.binding_target else ''
        if normalize_label(target_label) in labels:
            matched.append((cell, column, row, sheet, workspace))
    return matched


def _requirement_labels(requirement):
    labels = {
        requirement.requirement_name,
        requirement.annex_reference,
    }
    custom_fields = requirement.custom_fields or {}
    labels.update(
        custom_fields.get(key)
        for key in (
            'imported_requirement_name',
            'imported_canonical_label',
            'imported_source_header',
            'source_requirement_name',
        )
    )

    canonical = db.session.get(Requirement, requirement.requirement_id) if requirement.requirement_id else None
    if canonical:
        labels.update({canonical.name, canonical.annex_reference, canonical.source_label})
        import_mapping = ((canonical.custom_field_schema or {}).get('import_mapping') or {})
        labels.update({
            import_mapping.get('canonical_label'),
            import_mapping.get('source_header'),
        })

    return {normalize_label(value) for value in labels if normalize_label(value)}


def _status_value_for_column(status, column):
    if column.data_type == 'boolean':
        return status in {'under_review', 'compliant'}
    return status


def _sync_cell(cell, value, workspace_id, project_id, binding_target, user_id=None, reason=None):
    old_value = cell.current_value
    if _values_equal(old_value, value):
        return False

    cell.current_value = value
    cell.typed_value = value
    cell.display_value = _display_value(value)
    cell.value_type = cell.column.data_type
    cell.is_dirty = True
    cell.last_edited_by = user_id
    cell.last_edited_at = datetime.now(timezone.utc)
    db.session.add(WorkbookCellChange(
        cell_id=cell.id,
        workspace_id=workspace_id,
        project_id=project_id,
        binding_target=binding_target,
        old_value=old_value,
        new_value=value,
        change_source='system_sync',
        changed_by=user_id,
        reason=reason,
    ))
    return True


def _cell_lock_descriptor(cell, column, sheet, workspace):
    return {
        'workspace_id': workspace.id,
        'sheet_id': sheet.id,
        'column_id': column.id,
        'cell_id': cell.id,
        'cell_ref': cell.cell_ref,
        'source_column': column.source_column,
        'label': column.display_label or column.source_header or column.source_column,
    }


def _display_value(value):
    if value is None:
        return None
    return str(value)


def _values_equal(left, right):
    if left in (None, '') and right in (None, ''):
        return True
    try:
        if isinstance(left, (int, float, Decimal)) or isinstance(right, (int, float, Decimal)):
            return float(left or 0) == float(right or 0)
    except (TypeError, ValueError):
        pass
    return left == right


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
