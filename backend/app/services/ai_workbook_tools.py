"""Scoped workbook reads and confirmed edits, without documentary decisions."""
import json
import math
import re
from datetime import date, datetime
from functools import partial

from app.extensions import db
from app.models import Project, WorkbookWorkspace, WorkbookSheet, WorkbookRow, WorkbookCell, WorkbookConflict
from app.services import access_service, project_service, workbook_workspace_service as service


TOOL_NAMES = {
    'list_workbook_workspaces', 'list_workbook_sheets', 'get_workbook_grid',
    'get_workbook_cell', 'list_workbook_cell_history', 'list_workbook_conflicts',
    'update_workbook_cell', 'resolve_workbook_conflict',
}
MUTATIONS = {'update_workbook_cell', 'resolve_workbook_conflict'}
ADDRESS_FIELDS = ('cell_id', 'sheet_id', 'cell_ref')
PAGE_FIELDS = ('page', 'per_page')
ERRORS = (service.WorkbookWorkspaceError, access_service.AccessError, project_service.ProjectError)


def _registry():
    from app.services import ai_tool_registry
    return ai_tool_registry


def _error(message, code=422):
    return _registry().AiToolError(message, code)


def _rows(user, workspace_id=None):
    query = WorkbookRow.query.join(WorkbookSheet).filter(WorkbookRow.row_state.in_(('active', 'conflict')))
    if workspace_id:
        query = query.filter(WorkbookSheet.workspace_id == workspace_id)
    if user.role != 'admin':
        query = query.join(Project, WorkbookRow.project_id == Project.id)
        query = access_service.restrict_project_query(query, user.id)
    return service._restrict_row_query(query, user.id)


def _conflicts(workspace_id, user, status='open'):
    query = WorkbookConflict.query.join(WorkbookCell).filter(
        WorkbookConflict.workspace_id == workspace_id,
        WorkbookCell.row_id.in_(_rows(user, workspace_id).with_entities(WorkbookRow.id)),
    )
    if status != 'all':
        query = query.filter(WorkbookConflict.status == status)
    return query


def _workspace(args, user):
    workspace = service._get_workspace(args['workspace_id'])
    if user.role != 'admin' and not _rows(user, workspace.id).first():
        raise _error('Workbook workspace not found in your assigned scope.', 404)
    return workspace


def _sheets(workspace, user):
    query = workspace.sheets
    if user.role != 'admin':
        query = query.filter(WorkbookSheet.id.in_(_rows(user, workspace.id).with_entities(WorkbookRow.sheet_id)))
    return query.order_by(WorkbookSheet.sheet_order, WorkbookSheet.id).all()


def _sheet_summary(sheet, user):
    result = service._serialize_sheet(sheet)
    result['row_count'] = _rows(user, sheet.workspace_id).filter(WorkbookRow.sheet_id == sheet.id).count()
    return result


def _workspace_summary(workspace, user):
    result = service._serialize_workspace(workspace)
    result['sheet_count'] = len(_sheets(workspace, user))
    result['conflict_count'] = _conflicts(workspace.id, user).count()
    return result


def _cell(args, user):
    workspace = _workspace(args, user)
    if not args.get('cell_id'):
        if not args.get('sheet_id') or not args.get('cell_ref'):
            raise _error('Provide a cell ID, or both a sheet ID and a cell reference such as F2.')
        cell = WorkbookCell.query.join(WorkbookRow).join(WorkbookSheet).filter(
            WorkbookSheet.workspace_id == workspace.id, WorkbookSheet.id == args['sheet_id'],
            WorkbookCell.cell_ref == args['cell_ref'],
        ).first()
        if not cell:
            raise _error('Workbook cell not found.', 404)
        args['cell_id'] = cell.id
    cell = service._get_workspace_cell(workspace.id, args['cell_id'])
    if args.get('sheet_id') and cell.row.sheet_id != args['sheet_id']:
        raise _error('Cell does not belong to the selected sheet.', 422)
    if args.get('cell_ref') and cell.cell_ref != args['cell_ref']:
        raise _error('The cell ID and reference do not match.', 422)
    if not _rows(user, workspace.id).filter(WorkbookRow.id == cell.row_id).first():
        raise _error('Workbook cell not found in your assigned scope.', 404)
    if cell.row.project_id:
        access_service.ensure_project_access(cell.row.project_id, user.id)
    return cell


def _value(cell, value):
    column = cell.column
    if value is None or value == '':
        if column.is_required:
            raise _error('This workbook column requires a value.')
        return None
    if column.data_type != 'json' and isinstance(value, (dict, list)):
        raise _error('This cell requires a single value.')
    if column.data_type in ('number', 'currency', 'percent') and isinstance(value, bool):
        raise _error('A numeric cell cannot contain a boolean.')
    if column.data_type in ('text', 'status', 'date', 'datetime') and not isinstance(value, str):
        raise _error('This workbook cell requires text.')
    if isinstance(value, str) and len(value) > 10000:
        raise _error('Cell text is limited to 10,000 characters.')
    coerced = service._coerce_cell_value(value, column.data_type)
    if isinstance(coerced, float) and not math.isfinite(coerced):
        raise _error('Numeric cell values must be finite.')
    if column.data_type in ('date', 'datetime'):
        try:
            (date.fromisoformat if column.data_type == 'date' else datetime.fromisoformat)(coerced)
        except (TypeError, ValueError) as exc:
            raise _error('Use an ISO date or date/time for this column.') from exc
    options = column.validation_options or []
    if options and coerced not in options:
        raise _error('Choose one of this column\'s allowed values.')
    rules = column.validation_rules or {}
    supported = {'min', 'max', 'min_length', 'max_length'}
    if set(rules) - supported:
        raise _error('This column has additional validation rules. Edit it in the workbook workspace.')
    for rule, bound in rules.items():
        measured = len(coerced) if rule.endswith('_length') and isinstance(coerced, str) else coerced
        try:
            invalid = measured < bound if rule.startswith('min') else measured > bound
        except TypeError as exc:
            raise _error('The column validation configuration is incompatible with this value.') from exc
        if invalid:
            raise _error(f'The value does not meet the column\'s {rule.replace("_", " ")} rule.')
    if cell.column.binding_target == 'project.budget_amount' and (coerced is None or coerced < 0):
        raise _error('Project budgets must be non-negative.')
    if cell.column.binding_target == 'project.physical_completion_pct' and not 0 <= coerced <= 100:
        raise _error('Physical completion must be between 0 and 100.')
    if cell.column.binding_target == 'project.overall_status' and coerced not in ('not_yet_started', 'ongoing', 'suspended', 'cancelled'):
        raise _error('Only operational status changes are allowed. Completion uses the closeout workflow.')
    return coerced


def _mutable(cell, user, keep=False):
    workspace = cell.row.sheet.workspace
    if workspace.status != 'active' or not workspace.program_cycle.is_active:
        raise _error('Only active workbook workspaces and cycles can be changed.', 409)
    if cell.row.project_id:
        access_service.assert_project_movement_allowed(cell.row.project_id)
    else:
        raise _error('Only rows linked to accessible projects can be changed through the assistant.')
    column = cell.column
    if (column.binding_target or '').startswith('project_requirement.'):
        raise _error('Documentary status decisions must use the Documentary Review interface.')
    if keep:
        return
    service._assert_cell_editable(cell)
    if cell.formula or column.is_formula or column.data_type == 'formula' or column.binding_target in service.READ_ONLY_BINDINGS:
        raise _error('Calculated and source-controlled cells are read-only through the assistant.')
    target = column.binding_target or ''
    if target not in service.EDITABLE_PROJECT_FIELDS and not target.startswith('project.custom_fields.'):
        raise _error('This cell binding is not supported for assistant edits.')


def prepare(tool, args, user):
    permitted = set(tool.required_args) | set(tool.allowed_fields) | {'confirmation_display'}
    if set(args) - permitted:
        raise _error('Unsupported workbook arguments.')
    for key in permitted:
        if (key.endswith('_id') or key in PAGE_FIELDS or key == 'fiscal_year') and args.get(key) is not None:
            if isinstance(args[key], bool) or not re.fullmatch(r'[1-9]\d*', str(args[key])):
                raise _error(f'{key} must be a positive integer.')
            args[key] = int(args[key])
    if args.get('per_page', 20) > 50:
        raise _error('Use at most 50 rows per page.')
    if args.get('cell_ref'):
        if not isinstance(args['cell_ref'], str) or not re.fullmatch(r'[A-Za-z]{1,3}[1-9]\d{0,6}', args['cell_ref']):
            raise _error('Use a cell reference such as F2.')
        args['cell_ref'] = args['cell_ref'].upper()
    if 'reason' in args and (not isinstance(args['reason'], str) or len(args['reason']) > 2000):
        raise _error('Use a short text reason for the workbook change.')
    try:
        if tool.name == 'list_workbook_workspaces':
            return
        workspace = _workspace(args, user)
        if tool.name in ('list_workbook_sheets', 'list_workbook_conflicts'):
            if tool.name == 'list_workbook_conflicts' and args.get('status', 'open') not in ('open', 'all', 'keep_comet', 'accept_import'):
                raise _error('Choose open, all, keep_comet or accept_import conflicts.')
            return
        if tool.name == 'get_workbook_grid':
            if args['sheet_id'] not in {sheet.id for sheet in _sheets(workspace, user)}:
                raise _error('Workbook sheet not found in your assigned scope.', 404)
            return
        conflict = None
        if tool.name == 'resolve_workbook_conflict':
            conflict = WorkbookConflict.query.filter_by(id=args['conflict_id'], workspace_id=workspace.id).first()
            if not conflict:
                raise _error('Workbook conflict not found.', 404)
            if args.get('cell_id') and args['cell_id'] != conflict.cell_id:
                raise _error('The cell does not belong to this conflict.')
            args['cell_id'] = conflict.cell_id
        cell = _cell(args, user)
        if tool.name not in MUTATIONS:
            return
        if conflict:
            if conflict.status != 'open':
                raise _error('This workbook conflict is already resolved.', 409)
            if args['decision'] not in ('keep_comet', 'accept_import'):
                raise _error('Choose keep_comet or accept_import.')
            _mutable(cell, user, keep=args['decision'] == 'keep_comet')
            proposed = cell.current_value if args['decision'] == 'keep_comet' else _value(cell, service._incoming_conflict_value(conflict, strict=True))
        else:
            if 'value' not in args:
                raise _error('Provide the proposed cell value, including null to clear an optional cell.')
            _mutable(cell, user)
            if WorkbookConflict.query.filter_by(cell_id=cell.id, status='open').first():
                raise _error('Resolve the open import conflict before editing this cell.', 409)
            proposed = _value(cell, args['value'])
        revision = service.cell_revision(cell, conflict)
        if args.get('expected_revision') and args['expected_revision'] != revision:
            raise _error('The workbook changed after review. Inspect it and prepare a new confirmation.', 409)
        args['expected_revision'] = revision
        changes = {'value': {'from': cell.current_value, 'to': proposed}}
        target = cell.column.binding_target or ''
        if target in service.EDITABLE_PROJECT_FIELDS:
            bound = getattr(cell.row.project, target.split('.', 1)[1])
            changes['linked_project_value'] = {'from': service._json_safe(bound), 'to': proposed}
        elif target.startswith('project.custom_fields.'):
            key = target.split('project.custom_fields.', 1)[1]
            changes['linked_project_value'] = {'from': (cell.row.project.custom_fields or {}).get(key), 'to': proposed}
        args['confirmation_display'] = {
            'workspace': workspace.name, 'sheet': cell.row.sheet.display_name,
            'cell': cell.cell_ref, 'project': cell.row.project.project_name,
            'decision': args.get('decision'),
            'changes': changes,
            'notice': 'Confirm this workbook change and its linked project update. Changes after review require a new confirmation.',
        }
    except ERRORS as exc:
        raise _error(exc.message, exc.status_code) from exc


def _execute(name, args, user):
    registry = _registry()
    page, size = args.get('page', 1), args.get('per_page', 20)
    try:
        if name == 'list_workbook_workspaces':
            items = service.list_workspaces(**{key: args[key] for key in ('program_id', 'program_cycle_id', 'fiscal_year') if key in args}, user_id=user.id)
            ids = {row.sheet.workspace_id for row in _rows(user).all()} if user.role != 'admin' else None
            items = [_workspace_summary(db.session.get(WorkbookWorkspace, item['id']), user)
                     for item in items if ids is None or item['id'] in ids]
            result = {'workspaces': items[(page-1)*size:page*size], 'total': len(items), 'page': page}
        elif name == 'list_workbook_sheets':
            items = _sheets(_workspace(args, user), user)
            result = {'workspace_id': args['workspace_id'], 'sheets': [_sheet_summary(sheet, user) for sheet in items[(page-1)*size:page*size]], 'total': len(items), 'page': page}
        elif name == 'get_workbook_grid':
            sheet = db.session.get(WorkbookSheet, args['sheet_id'])
            rows = _rows(user, args['workspace_id']).filter(WorkbookRow.sheet_id == sheet.id).order_by(WorkbookRow.source_row_number).paginate(page=page, per_page=size, error_out=False)
            columns = sheet.columns.order_by(service.WorkbookColumn.column_index).all()
            service._ensure_editable_cells(rows.items, columns)
            result = {'workspace': _workspace_summary(_workspace(args, user), user), 'sheet': _sheet_summary(sheet, user),
                      'columns': [service._serialize_column(column) for column in columns],
                      'rows': [service._serialize_row(row, columns) for row in rows.items],
                      'page': rows.page, 'per_page': rows.per_page, 'total': rows.total, 'pages': rows.pages}
        elif name == 'list_workbook_conflicts':
            conflicts = _conflicts(args['workspace_id'], user, args.get('status', 'open')).order_by(WorkbookConflict.id.desc()).paginate(page=page, per_page=size, error_out=False)
            result = {'items': [service._serialize_conflict(item) for item in conflicts.items],
                      'page': conflicts.page, 'per_page': conflicts.per_page, 'total': conflicts.total, 'pages': conflicts.pages}
        elif name == 'list_workbook_cell_history':
            result = service.list_cell_history(args['workspace_id'], args['cell_id'], user_id=user.id, page=page, per_page=size)
        elif name == 'get_workbook_cell':
            cell = _cell(args, user)
            result = {'workspace_id': args['workspace_id'], 'sheet_id': cell.row.sheet_id,
                      'column': service._serialize_column(cell.column), 'cell': service._serialize_cell(cell)}
        else:
            # Lock the same records used by ordinary workbook writes and
            # recheck policy/scope immediately before the canonical mutation.
            service._get_workspace_cell(args['workspace_id'], args['cell_id'], for_update=True)
            prepare(registry.get_tool(name), args, user)
            if name == 'update_workbook_cell':
                result = service.update_cell(args['workspace_id'], args['cell_id'], args['value'], user_id=user.id,
                                             reason=args.get('reason'), expected_revision=args['expected_revision'])
            else:
                result = service.resolve_conflict(args['workspace_id'], args['conflict_id'], args['decision'],
                                                 user_id=user.id, expected_revision=args['expected_revision'])
        return registry._detail_result(registry.get_user_facing_tool_label(name), result)
    except ERRORS as exc:
        db.session.rollback()
        raise _error(exc.message, exc.status_code) from exc
    except Exception:
        db.session.rollback()
        raise


def build_tools(definition):
    operational = ('admin', 'staff', 'field_officer')
    specs = {
        'list_workbook_workspaces': ((), ('program_id', 'program_cycle_id', 'fiscal_year') + PAGE_FIELDS, operational, 'list_workspaces', 'List workbook workspaces visible in your assigned scope.'),
        'list_workbook_sheets': (('workspace_id',), PAGE_FIELDS, operational, 'list_sheets', 'List visible sheets and scoped row counts.'),
        'get_workbook_grid': (('workspace_id', 'sheet_id'), PAGE_FIELDS, operational, 'get_sheet_grid', 'Read a scoped workbook grid, including exact cell IDs and references.'),
        'get_workbook_cell': (('workspace_id',), ADDRESS_FIELDS, operational, '_get_workspace_cell', 'Inspect a cell using cell_id or sheet_id plus cell_ref.'),
        'list_workbook_cell_history': (('workspace_id',), ADDRESS_FIELDS + PAGE_FIELDS, operational, 'list_cell_history', 'Inspect scoped cell history using cell_id or sheet_id plus cell_ref.'),
        'list_workbook_conflicts': (('workspace_id',), ('status',) + PAGE_FIELDS, ('admin', 'staff'), 'list_conflicts', 'List scoped re-import conflicts and incoming/current values.'),
        'update_workbook_cell': (('workspace_id',), ADDRESS_FIELDS + ('value', 'reason', 'expected_revision'), ('admin', 'staff'), 'update_cell', 'Edit an editable cell after confirmation. value is required and may be null. Documentary status and calculated/source-controlled cells remain UI-only.'),
        'resolve_workbook_conflict': (('workspace_id', 'conflict_id', 'decision'), ('cell_id', 'expected_revision'), ('admin', 'staff'), 'resolve_conflict', 'Confirm keep_comet or accept_import for one conflict. Accepting import must satisfy cell validation and excludes documentary status decisions.'),
    }
    return {name: definition(name=name, description=description, roles=roles, required_args=required,
                            allowed_fields=fields, operation_type='update' if name in MUTATIONS else 'read',
                            requires_confirmation=name in MUTATIONS, risk_level='high' if name in MUTATIONS else 'low',
                            scope_type='lgu', canonical_service=f'workbook_workspace_service.{method}',
                            display_type='detail', executor=partial(_execute, name))
            for name, (required, fields, roles, method, description) in specs.items()}


def heuristic_plan(message, user):
    text = message.lower()
    if 'workbook' not in text and 'workspace' not in text:
        return None
    if re.search(r'\b(delete|archive|approve|waive|dispatch|import template|mapping)\b', text):
        return None
    if re.search(r'\b(resolve|keep|accept)\b.*\bconflict\b', text):
        name = 'resolve_workbook_conflict'
    elif re.search(r'\b(?:edit|update|set|change|clear)\b.*\bcell\b', text):
        name = 'update_workbook_cell'
    elif 'history' in text and 'cell' in text:
        name = 'list_workbook_cell_history'
    elif re.search(r'\b(list|show|inspect|view|get)\b', text):
        name = ('list_workbook_conflicts' if 'conflict' in text else 'get_workbook_cell' if 'cell' in text
                else 'get_workbook_grid' if 'grid' in text or 'rows' in text else 'list_workbook_sheets' if 'sheet' in text
                else 'list_workbook_workspaces' if 'workspace' in text else None)
    else:
        return None
    if not name:
        return None
    plan = {'assistant_reply': 'I will inspect the workbook.', 'tool_calls': [], 'ai_provider_used': 'local',
            'heuristic_rule_hit': 'workbook_review', 'ai_model_used': 'local:workbook-review'}
    tool = _registry().get_tool(name)
    if not user or user.role not in tool.roles:
        plan['assistant_reply'] = 'Your role cannot perform that workbook action.'
        return plan
    args = {}
    for key, label in (('workspace_id', '(?:workspace|workbook)'), ('sheet_id', 'sheet'), ('cell_id', 'cell'),
                       ('conflict_id', 'conflict'), ('program_id', 'program'), ('program_cycle_id', 'cycle')):
        found = re.search(rf'\b{label}\s*(?:#|id\s*|:\s*)?\s*([1-9]\d*)\b', text)
        if found:
            args[key] = int(found.group(1))
    ref = re.search(r'\bcell\s+([A-Za-z]{1,3}[1-9]\d*)\b', message, re.I)
    if ref:
        args['cell_ref'] = ref.group(1).upper()
    if name == 'resolve_workbook_conflict':
        if re.search(r'\bkeep(?:_comet| comet| current| the current)\b', text):
            args['decision'] = 'keep_comet'
        elif re.search(r'\baccept(?:_import| import| the import| incoming| the incoming)\b', text):
            args['decision'] = 'accept_import'
    if name == 'update_workbook_cell':
        value = re.search(r'\bto\s+(.+?)(?=\s+(?:in|for)\s+(?:workbook|workspace|sheet)\b|$)', message, re.I)
        if 'clear' in text:
            args['value'] = None
        elif value:
            raw = value.group(1).strip()
            try:
                args['value'] = json.loads(raw)
            except ValueError:
                args['value'] = raw.strip('"\'')
    missing = [key.replace('_', ' ') for key in tool.required_args if key not in args]
    if name in ('get_workbook_cell', 'list_workbook_cell_history', 'update_workbook_cell') and not args.get('cell_id') and not (args.get('cell_ref') and args.get('sheet_id')):
        missing.append('cell ID or sheet ID and cell reference')
    if name == 'update_workbook_cell' and 'value' not in args:
        missing.append('the proposed value')
    if missing:
        plan['assistant_reply'] = 'Please provide ' + ', '.join(missing) + '.'
        return plan
    allowed = set(tool.required_args) | set(tool.allowed_fields)
    args = {key: value for key, value in args.items() if key in allowed}
    plan['assistant_reply'] = 'I will prepare the workbook change for confirmation.' if name in MUTATIONS else 'I will inspect the workbook.'
    plan['tool_calls'] = [{'tool_name': name, 'arguments': args, 'reason': 'Explicit workbook request.'}]
    return plan
