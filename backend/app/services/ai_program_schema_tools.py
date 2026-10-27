"""Review JSON configuration replacements on existing program/cycle tools.

These are stored configuration objects, not a schema migration or an instruction
to rewrite existing project values, import templates or workbook bindings.
"""
import hashlib
import json
import math

from app.extensions import db
from app.models import ImportBatch, ImportTemplate, Program, ProgramCycle, WorkbookWorkspace, WorkbookColumn, WorkbookSheet
from app.services import program_service


FIELDS = {
    'update_program': ('project_custom_field_schema',),
    'update_program_cycle': ('import_profile', 'field_schema'),
}


def _error(message, status=422):
    from app.services.ai_tool_registry import AiToolError
    return AiToolError(message, status)


def _json_value(value, depth=0):
    if depth > 20:
        raise _error('Configuration nesting cannot exceed 20 levels.')
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise _error('Configuration object keys must be strings.')
        for child in value.values():
            _json_value(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _json_value(child, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise _error('Configuration numbers must be finite.')
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        raise _error('Configuration must contain JSON values only.')


def applies(tool, args):
    return tool.name in FIELDS and any(field in args for field in (*FIELDS[tool.name], 'expected_revision'))


def _related(model, filters):
    # Timestamp and status changes invalidate a reviewed dependency set. Include
    # IDs too so replacing a row with another does not preserve the review.
    return [dict(id=row.id, updated_at=row.updated_at.isoformat() if row.updated_at else None,
                 status=row.status) for row in model.query.filter_by(**filters).order_by(model.id).all()]


def prepare(tool, args, user, lock=False):
    if not applies(tool, args):
        return
    fields = [field for field in FIELDS[tool.name] if field in args]
    if not fields:
        raise _error('Provide a schema or import-profile object to review.')
    for field in fields:
        if not isinstance(args[field], dict):
            raise _error(f'{field} must be a JSON object. Use {{}} to clear it; null is not accepted.')
        _json_value(args[field])

    if tool.name == 'update_program':
        program_id = int(args['program_id'])
    else:
        cycle = program_service.get_program_cycle(int(args['cycle_id']))
        program_id = cycle.program_id
    query = Program.query.filter_by(id=program_id).populate_existing()
    program = (query.with_for_update() if lock else query).first()
    if not program:
        raise _error('Program not found.', 404)
    filters = dict(program_id=program.id)
    if tool.name == 'update_program_cycle':
        query = ProgramCycle.query.filter_by(id=int(args['cycle_id'])).populate_existing()
        target = (query.with_for_update() if lock else query).first()
        if not target or target.program_id != program.id:
            raise _error('Program cycle changed or is unavailable. Prepare a new review.', 409)
        before = program_service._serialize_program_cycle(target)
        filters['program_cycle_id'] = target.id
    else:
        target = program
        before = program_service._serialize_program(program)
    related = {label: _related(model, filters) for label, model in (
        ('import_templates', ImportTemplate), ('import_batches', ImportBatch), ('workbook_workspaces', WorkbookWorkspace))}
    columns = WorkbookColumn.query.join(WorkbookSheet).join(WorkbookWorkspace).filter(
        WorkbookWorkspace.program_id == program.id)
    if tool.name == 'update_program_cycle':
        columns = columns.filter(WorkbookWorkspace.program_cycle_id == target.id)
    related['workbook_columns'] = [dict(id=column.id, updated_at=column.updated_at.isoformat(),
                                      binding_target=column.binding_target, binding_config=column.binding_config,
                                      validation_rules=column.validation_rules, is_editable=column.is_editable)
                                   for column in columns.order_by(WorkbookColumn.id).all()]
    impact = dict(projects=target.projects.count(), **{key: len(rows) for key, rows in related.items()})
    payload = {key: args[key] for key in tool.allowed_fields if key in args and key != 'expected_revision'}
    _json_value(payload)
    state = dict(before=before, parent=program_service._serialize_program(program),
                 related=related, payload=payload, user_id=user.id)
    revision = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if args.get('expected_revision') is not None and args['expected_revision'] != revision:
        raise _error('Program configuration or related import state changed after review. Prepare a new action.', 409)
    args['expected_revision'] = revision
    args['confirmation_display'] = {
        'target': dict(id=target.id, name=target.name, program_id=program.id),
        'changes': {key: {'from': before.get(key), 'to': value} for key, value in payload.items()},
        'related_record_counts': impact,
        'notice': 'Confirm to replace the supplied configuration objects in full. Use {} to clear an object. '
                  'Existing project values, templates and workbook bindings are not rewritten; imports are not reprocessed. '
                  'Omitted configuration objects stay unchanged. Related records: '
                  + ', '.join(f'{key.replace("_", " ")}: {count}' for key, count in impact.items()) + '.',
    }
