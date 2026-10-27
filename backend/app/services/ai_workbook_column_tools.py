"""Scoped column inspection and confirmed, validated column configuration."""
from copy import deepcopy
from functools import partial
import hashlib
import json
import math
import re
from types import SimpleNamespace

from app.extensions import db
from app.models import Project, WorkbookCell, WorkbookColumn, WorkbookConflict, WorkbookRow, WorkbookSheet
from app.services import (access_service, ai_workbook_tools as workbook,
                          workbook_workspace_service as service)
from app.services.ai_program_schema_tools import _json_value


TOOL_NAMES = {'get_workbook_column', 'update_workbook_column'}
DISPLAY = ('display_label', 'display_format', 'number_format')
STRUCTURAL = ('data_type', 'binding_target', 'binding_config', 'validation_rules', 'validation_options', 'is_required', 'is_editable')
FIELDS = (*DISPLAY, *STRUCTURAL)


def _registry():
    from app.services import ai_tool_registry
    return ai_tool_registry


def _error(message, code=422):
    return _registry().AiToolError(message, code)


def _snapshot(record):
    return {column.name: getattr(record, column.name) for column in record.__table__.columns} if record else None


def _column(args, user):
    workspace = workbook._workspace(args, user)
    column = WorkbookColumn.query.join(WorkbookSheet).filter(
        WorkbookColumn.id == args['column_id'], WorkbookSheet.workspace_id == workspace.id).populate_existing().first()
    if not column or column.sheet_id not in {sheet.id for sheet in workbook._sheets(workspace, user)}:
        raise _error('Workbook column not found in your assigned scope.', 404)
    return workspace, column


def _proposed(column, args):
    before = service._serialize_column(column)
    result = deepcopy(before)
    result.update({key: args[key] for key in FIELDS if key in args})
    for key in ('is_editable', 'is_required'):
        if key in args and not isinstance(args[key], bool):
            raise _error(f'{key} must be true or false.')
    for key in ('binding_config', 'validation_rules'):
        if key in args and not isinstance(args[key], dict):
            raise _error(f'{key} must be an object; use {{}} to clear it.')
    if 'validation_options' in args and not isinstance(args['validation_options'], list):
        raise _error('validation_options must be a list.')
    _json_value({key: args[key] for key in FIELDS if key in args})
    for key in ('display_label', 'number_format'):
        if key in args and not (key == 'number_format' and args[key] is None):
            limit = 500 if key == 'display_label' else 120
            if not isinstance(args[key], str) or not args[key].strip() or len(args[key]) > limit:
                raise _error(f'{key} must be nonblank text, up to {limit} characters.')
            args[key] = args[key].strip()
            result[key] = args[key]
    if 'display_format' in args and (not isinstance(args['display_format'], str) or args['display_format'] not in service.DISPLAY_FORMATS):
        raise _error('display_format must be auto, money, year or number.')
    configured_format = (result['binding_config'] or {}).get('display_format', 'auto')
    if not isinstance(configured_format, str) or configured_format not in service.DISPLAY_FORMATS:
        raise _error('binding_config.display_format must be auto, money, year or number.')
    if 'display_format' in args:
        if args['display_format'] == 'auto':
            result['binding_config'].pop('display_format', None)
        else:
            result['binding_config']['display_format'] = args['display_format']
    result['display_format'] = result['binding_config'].get('display_format') or 'auto'
    if 'data_type' in args:
        if not isinstance(args['data_type'], str):
            raise _error('data_type must be text.')
        result['data_type'] = args['data_type'] = service._normalize_column_data_type(args['data_type'])
        if result['data_type'] == 'formula':
            raise _error('Formula configuration remains in the workbook interface.')
    target = result['binding_target']
    if 'binding_target' in args and (not isinstance(target, str) or not (
        target in service.EDITABLE_PROJECT_FIELDS or target == 'import_only' or
        re.fullmatch(r'project\.custom_fields\.[A-Za-z_][A-Za-z0-9_]{0,99}', target))):
        raise _error('Use an ordinary editable project/custom-field binding or import_only.')
    if any(key in args for key in STRUCTURAL):
        if result['data_type'] not in service.COLUMN_DATA_TYPES - {'formula'}:
            raise _error('Select a supported non-formula column type.')
        if column.is_formula or column.data_type == 'formula' or (
            column.binding_target in service.READ_ONLY_BINDINGS - {'import_only'}
        ) or (column.binding_target or '').startswith('project_requirement.') or not (
            column.binding_target in service.EDITABLE_PROJECT_FIELDS or column.binding_target == 'import_only' or
            re.fullmatch(r'project\.custom_fields\.[A-Za-z_][A-Za-z0-9_]{0,99}', column.binding_target or '')
        ):
            raise _error('Formula, source-controlled and documentary columns allow display settings only.')
        if target == 'import_only' and result['is_editable']:
            raise _error('An import_only column cannot be made editable. Select a permitted binding first.')
        if target in ('project.budget_amount', 'project.physical_completion_pct') and result['data_type'] not in ('number', 'currency', 'percent'):
            raise _error('Budget/progress bindings require a numeric column type.')
        if target in ('project.project_name', 'project.overall_status') and result['data_type'] not in ('text', 'status'):
            raise _error('Project name/status bindings require text or status columns.')
        rules = result['validation_rules'] or {}
        if set(rules) - {'min', 'max', 'min_length', 'max_length'}:
            raise _error('Unsupported validation rules; use min/max/min_length/max_length.')
        for key, value in rules.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
                raise _error('Validation bounds must be finite numbers.')
            if key.endswith('_length') and (type(value) is not int or value < 0):
                raise _error('Length bounds must be nonnegative integers.')
        for lower, upper in (('min', 'max'), ('min_length', 'max_length')):
            if lower in rules and upper in rules and rules[lower] > rules[upper]:
                raise _error(f'{lower} cannot exceed {upper}.')
    return before, result


def prepare(tool, args, user, lock=False):
    extra = set(args) - set(tool.required_args) - set(tool.allowed_fields) - {'reason', 'confirmation_display'}
    if extra:
        raise _error('Unsupported fields: ' + ', '.join(sorted(extra)))
    for key in ('workspace_id', 'column_id'):
        if isinstance(args[key], bool) or not re.fullmatch(r'[1-9]\d*', str(args[key])):
            raise _error(f'{key} must be a positive integer.')
        args[key] = int(args[key])
    try:
        workspace, column = _column(args, user)
        if tool.name == 'get_workbook_column':
            return
        if not any(key in args for key in FIELDS):
            raise _error('Provide at least one column setting.')
        if lock:
            # Configuration services acquire program/cycle before child records.
            db.session.refresh(workspace.program, with_for_update=True)
            db.session.refresh(workspace.program_cycle, with_for_update=True)
            db.session.refresh(workspace, with_for_update=True)
        # Match ordinary cell writes: cells first, then column, rows, projects.
        cells_query = WorkbookCell.query.filter_by(column_id=column.id).order_by(WorkbookCell.id).populate_existing()
        cells = (cells_query.with_for_update() if lock else cells_query).all()
        if lock:
            WorkbookColumn.query.filter_by(id=column.id).populate_existing().with_for_update().one()
        rows_query = WorkbookRow.query.filter_by(sheet_id=column.sheet_id).order_by(WorkbookRow.id).populate_existing()
        rows = (rows_query.with_for_update() if lock else rows_query).all()
        projects = []
        for project_id in sorted({row.project_id for row in rows if row.project_id}):
            query = Project.query.filter_by(id=project_id).populate_existing()
            projects.append((query.with_for_update() if lock else query).one())
        # Refresh lifecycle flags at confirmation too.
        db.session.refresh(workspace)
        db.session.refresh(workspace.program_cycle)
        db.session.refresh(workspace.program)
        db.session.refresh(column.sheet)
        if workspace.status != 'active' or not workspace.program_cycle.is_active or not workspace.program.is_active:
            raise _error('Only active workspaces, cycles and programs can be configured.', 409)
        before, proposed = _proposed(column, args)
        structural = any(key in args for key in STRUCTURAL)
        conflicts = WorkbookConflict.query.filter(WorkbookConflict.cell_id.in_([cell.id for cell in cells]),
                                                  WorkbookConflict.status == 'open').all()
        if structural:
            if conflicts or any(cell.formula for cell in cells):
                raise _error('Resolve column conflicts first; formula cells keep structural configuration in the workbook UI.', 409)
            for row in rows:
                if not row.project_id or row.row_state != 'active':
                    raise _error('Structural configuration requires active rows linked to projects.', 409)
                access_service.ensure_project_access(row.project_id, user.id)
                access_service.assert_project_movement_allowed(row.project_id)
                if row.project.program_id != workspace.program_id or row.project.program_cycle_id != workspace.program_cycle_id:
                    raise _error('A linked project moved outside this workbook cycle. Use the workbook UI.', 409)
            test_cell = SimpleNamespace(column=SimpleNamespace(**proposed))
            for option in proposed.get('validation_options') or []:
                workbook._value(test_cell, option)
            by_row = {cell.row_id: cell for cell in cells}
            for row in rows:
                value = by_row[row.id].current_value if row.id in by_row else None
                try:
                    workbook._value(test_cell, value)
                except _registry().AiToolError as exc:
                    raise _error(f'Existing row {row.source_row_number} fails the proposed settings: {exc.message}') from exc
        payload = {key: args[key] for key in FIELDS if key in args}
        state = dict(column=_snapshot(column), workspace=service._serialize_workspace(workspace),
                     sheet=_snapshot(column.sheet), cycle_updated=str(workspace.program_cycle.updated_at),
                     program_updated=str(workspace.program.updated_at), rows=[_snapshot(row) for row in rows],
                     cells=[_snapshot(cell) for cell in cells], projects=[_snapshot(project) for project in projects],
                     conflicts=[_snapshot(conflict) for conflict in conflicts], payload=payload, user_id=user.id)
        revision = hashlib.sha256(json.dumps(state, default=str, sort_keys=True, allow_nan=False).encode()).hexdigest()
        if args.get('expected_revision') is not None and args['expected_revision'] != revision:
            raise _error('Workbook settings or linked records changed after review. Prepare a new action.', 409)
        args['expected_revision'] = revision
        created = sum(row.id not in {cell.row_id for cell in cells} for row in rows) if args.get('is_editable') is True else 0
        args['confirmation_display'] = {
            'changes': {key: {'from': before.get(key), 'to': proposed.get(key)} for key in payload},
            'affected_rows': len(rows), 'existing_cells': len(cells), 'blank_cells_to_create': created,
            'notice': f'Workspace {workspace.name} (#{workspace.id}), sheet {column.sheet.display_name}, column {column.source_column} (#{column.id}). '
                      f'Affects {len(rows)} rows and {len(cells)} existing cells; creates {created} blank cells. '
                      'Binding changes affect future edits. Existing cell/project values are not rewritten; changing data type relabels existing cell types.',
        }
    except (service.WorkbookWorkspaceError, access_service.AccessError) as exc:
        raise _error(exc.message, exc.status_code) from exc


def _execute(name, args, user):
    tool = _registry().get_tool(name)
    if name == 'get_workbook_column':
        workspace, column = _column(args, user)
        return _registry()._detail_result('Workbook column', {'workspace_id': workspace.id, 'sheet_id': column.sheet_id,
            'column': service._serialize_column(column),
            'visible_rows': workbook._rows(user, workspace.id).filter(WorkbookRow.sheet_id == column.sheet_id).count()})
    try:
        prepare(tool, args, user, lock=True)
        result = service.update_column_settings(args['workspace_id'], args['column_id'],
                                                {key: args[key] for key in FIELDS if key in args}, user_id=user.id)
        return _registry()._detail_result('Workbook column updated', result)
    except Exception:
        db.session.rollback()
        raise


def build_tools(definition):
    return {name: definition(name=name, description=description, roles=roles,
            required_args=('workspace_id', 'column_id'), allowed_fields=fields,
            operation_type='update' if name == 'update_workbook_column' else 'read',
            requires_confirmation=name == 'update_workbook_column', risk_level='high' if name == 'update_workbook_column' else 'low',
            scope_type='lgu', canonical_service='workbook_workspace_service.' + method,
            display_type='detail', executor=partial(_execute, name))
        for name, roles, fields, method, description in (
            ('get_workbook_column', ('admin', 'staff', 'field_officer'), (), '_serialize_column',
             'Inspect column settings for a sheet visible in your current scope, without creating cells.'),
            ('update_workbook_column', ('admin',), (*FIELDS, 'expected_revision'), 'update_column_settings',
             'Configure column labels/formats and ordinary type/binding/validation/editability settings after confirmation. Existing values must satisfy proposed settings. Formula/source/documentary structural controls remain UI-only.'))}


def heuristic_plan(message, user):
    text = message.split('{', 1)[0].lower()
    match = re.search(r'\b(show|inspect|get|view|update|configure|edit|change)\s+(?:the\s+)?(?:workbook\s+)?column\b', text)
    if not match or not re.search(r'\b(workbook|workspace)\b', text) or re.search(r'\b(delete|archive|approve|waive|explain)\b|\bhow\s+(?:do|can|to)\b', text):
        return None
    name = 'get_workbook_column' if match.group(1) in ('show', 'inspect', 'get', 'view') else 'update_workbook_column'
    plan = dict(assistant_reply='I will inspect the column settings.', tool_calls=[], ai_provider_used='local',
                ai_model_used='local:workbook-columns', heuristic_rule_hit='workbook_column')
    if not user or user.role not in _registry().get_tool(name).roles:
        plan['assistant_reply'] = 'Your role cannot perform that column action.'
        return plan
    args = {}
    for label, key in (('(?:workspace|workbook)', 'workspace_id'), ('column', 'column_id')):
        found = re.search(rf'\b{label}\s*(?:#|id\s*)\s*([1-9]\d*)\b', text)
        if found:
            args[key] = int(found.group(1))
    if '{' in message:
        try:
            payload = json.loads(message[message.index('{'):])
            if not isinstance(payload, dict):
                raise ValueError()
            args.update(payload)
        except ValueError:
            plan['assistant_reply'] = 'Please provide a valid JSON settings object.'
            return plan
    missing = [key.replace('_', ' ') for key in ('workspace_id', 'column_id') if key not in args]
    if name == 'update_workbook_column' and not any(key in args for key in FIELDS):
        missing.append('proposed settings as JSON')
    if missing:
        plan['assistant_reply'] = 'Please provide ' + ', '.join(missing) + '.'
        return plan
    plan['tool_calls'] = [dict(tool_name=name, arguments=args, reason='Explicit workbook column request.')]
    return plan
