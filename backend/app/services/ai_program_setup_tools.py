"""Confirmed cycle/template operations; no archive/delete or account controls."""
from functools import partial
import hashlib
import json
import re

from app.extensions import db
from app.models import ImportTemplate, Program, ProgramCycle
from app.services import import_service, program_service
from app.services.ai_program_schema_tools import _json_value


TOOL_NAMES = {'clone_program_cycle', 'create_import_template', 'update_import_template', 'clone_import_template'}
MAPPINGS = ('sheet_mappings', 'column_mappings', 'transform_rules')


def _registry():
    from app.services import ai_tool_registry
    return ai_tool_registry


def _error(message, code=422):
    return _registry().AiToolError(message, code)


def _snapshot(model):
    if model is None:
        return None
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}


def _record(model, key, lock):
    query = model.query.filter_by(id=key).populate_existing()
    result = (query.with_for_update() if lock else query).first()
    if not result:
        raise _error(f'{model.__name__} not found.', 404)
    return result


def _data(tool, args):
    return {key: args[key] for key in (*tool.required_args, *tool.allowed_fields)
            if key in args and key not in ('expected_revision', 'template_id', 'source_cycle_id')}


def prepare(tool, args, user, lock=False):
    permitted = set(tool.required_args) | set(tool.allowed_fields)
    extra = set(args) - permitted - {'confirmation_display', 'reason'}
    if extra:
        raise _error('Unsupported fields: ' + ', '.join(sorted(extra)))
    for key in permitted:
        if key.endswith('_id') and key in args and args[key] is not None:
            if isinstance(args[key], bool) or not re.fullmatch(r'[1-9]\d*', str(args[key])):
                raise _error(f'{key} must be a positive integer.')
            args[key] = int(args[key])
    for key in ('name', 'cycle_code', 'schema_signature'):
        if key in args:
            limit = {'name': 200, 'cycle_code': 80, 'schema_signature': 128}[key]
            if not isinstance(args[key], str) or not args[key].strip() or len(args[key]) > limit:
                raise _error(f'{key} must be nonblank text of at most {limit} characters.')
    for key in MAPPINGS:
        if key in args:
            if not isinstance(args[key], dict):
                raise _error(f'{key} must be a JSON object; use {{}} to clear it.')
            _json_value(args[key])
    if tool.name == 'create_import_template' and args.get('file_type', 'xlsx') not in ('csv', 'xlsx'):
        raise _error('New assistant import templates support csv or xlsx.')
    if tool.name == 'update_import_template' and not any(key in args for key in ('name', 'schema_signature', *MAPPINGS)):
        raise _error('Provide at least one template field to update.')

    source_cycle = source_template = target_cycle = None
    if tool.name == 'clone_program_cycle':
        source_cycle = _record(ProgramCycle, args['source_cycle_id'], False)
        program_id = source_cycle.program_id
    elif tool.name in ('update_import_template', 'clone_import_template'):
        source_template = _record(ImportTemplate, args['template_id'], False)
        program_id = source_template.program_id
    else:
        program_id = args['program_id']
    # Consistent lock order: program, cycle, template. The program service owns
    # the final clone transaction and the import service owns template/audit writes.
    program = _record(Program, program_id, lock)
    if source_cycle:
        source_cycle = _record(ProgramCycle, source_cycle.id, lock)
        if source_cycle.program_id != program.id:
            raise _error('Source cycle changed program. Prepare a new review.', 409)
    if source_template:
        source_template = _record(ImportTemplate, source_template.id, lock)
        if source_template.program_id != program.id:
            raise _error('Source template changed program. Prepare a new review.', 409)
    if tool.name in ('create_import_template', 'clone_import_template'):
        cycle_id = args.get('program_cycle_id', source_template.program_cycle_id if source_template else None)
        if cycle_id is not None:
            target_cycle = _record(ProgramCycle, cycle_id, lock)
            if target_cycle.program_id != program.id:
                raise _error('Target cycle must belong to the same program.')

    copied_templates = []
    if source_cycle:
        year = args['fiscal_year']
        try:
            program_service._validate_fiscal_year(year)
        except program_service.ProgramError as exc:
            raise _error(exc.message, exc.status_code) from exc
        if not program.is_active:
            raise _error('Cannot clone a cycle under an inactive program.')
        code = args.get('cycle_code', source_cycle.cycle_code)
        if program_service._find_cycle_by_normalized_code(program.id, year, code):
            raise _error('Program cycle already exists for this fiscal year and cycle code.', 409)
        templates = ImportTemplate.query.filter_by(program_cycle_id=source_cycle.id, is_active=True).order_by(ImportTemplate.id)
        copied_templates = [_snapshot(row) for row in (templates.with_for_update() if lock else templates).all()]
        effect = {'new_cycle_name': args.get('name', f'{program.name} FY {year}'),
                  'fiscal_year': year, 'cycle_code': code, 'copied_active_templates': len(copied_templates)}
        notice = (f'Source cycle: {source_cycle.name} (#{source_cycle.id}), program {program.name} (#{program.id}). '
                  f'New cycle: {effect["new_cycle_name"]}, FY {year}, code {code}. '
                  'Creates a new cycle and draft copies of its active import templates. Projects and requirement definitions are not cloned.')
    else:
        if tool.name == 'update_import_template' and source_template.locked_at and any(key in args for key in MAPPINGS):
            raise _error('Locked template mappings cannot be edited in place. Clone the template first.', 409)
        effect = {'program_id': program.id, 'program_cycle_id': args.get('program_cycle_id', source_template.program_cycle_id if source_template else None),
                  'fields': _data(tool, args)}
        destination = f'cycle #{effect["program_cycle_id"]}' if effect['program_cycle_id'] is not None else 'program-level configuration'
        label = args.get('name') or (f'{source_template.name} Copy' if tool.name == 'clone_import_template' else source_template.name if source_template else 'Workbook Import Template')
        effect.update(name=label, file_type=args.get('file_type', source_template.file_type if source_template else 'xlsx'))
        notice = f'Template: {label}; program {program.name} (#{program.id}), {destination}. '
        if source_template:
            notice += f'Source template: {source_template.name} (#{source_template.id}). '
        notice += 'Saves template configuration. New and cloned templates are drafts. Existing batches and workbook bindings are not rewritten. '
        if tool.name == 'update_import_template':
            notice += 'Existing import previews must be regenerated after a template change.'
        else:
            notice += 'Select the new template separately and review the import before committing.'
    state = dict(program=_snapshot(program), source_cycle=_snapshot(source_cycle),
                 source_template=_snapshot(source_template), target_cycle=_snapshot(target_cycle),
                 copied_templates=copied_templates, data=_data(tool, args), tool=tool.name, user=user.id)
    revision = hashlib.sha256(json.dumps(state, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()
    if args.get('expected_revision') is not None and args['expected_revision'] != revision:
        raise _error('The reviewed program, cycle or template changed. Prepare a new review.', 409)
    args['expected_revision'] = revision
    args['confirmation_display'] = {
        'target': {'program_id': program.id, 'program_name': program.name},
        'changes': {key: {'from': getattr(source_template, key, None) if tool.name == 'update_import_template' else None,
                          'to': value} for key, value in _data(tool, args).items()},
        'effect': effect, 'notice': notice + (' Active templates copied: ' + str(len(copied_templates)) + '.' if source_cycle else ''),
    }


def _execute(name, args, user):
    tool = _registry().get_tool(name)
    try:
        prepare(tool, args, user, lock=True)
        data = _data(tool, args)
        if name == 'clone_program_cycle':
            cycle = program_service.clone_program_cycle(args['source_cycle_id'], user_id=user.id, **data)
            detail = program_service._serialize_program_cycle(cycle)
        elif name == 'create_import_template':
            detail = import_service.create_import_template({**data, 'status': 'draft'}, user_id=user.id)
        elif name == 'update_import_template':
            detail = import_service.update_import_template(args['template_id'], data, user_id=user.id)
        else:
            detail = import_service.clone_import_template(args['template_id'], data, user_id=user.id)
        return {'display_type': 'detail', 'title': name.replace('_', ' ').capitalize(), 'detail': detail,
                'summary': f'Saved {detail["name"]} (#{detail["id"]}).'}
    except (program_service.ProgramError, import_service.ImportError) as exc:
        db.session.rollback()
        raise _error(exc.message, exc.status_code) from exc
    except Exception:
        db.session.rollback()
        raise


def build_tools(definition):
    specs = {
        'clone_program_cycle': (('source_cycle_id', 'fiscal_year'), ('name', 'cycle_code'),
                               'Clone a program cycle and active templates into a new year/code; projects and requirements are not copied.',
                               'program_service.clone_program_cycle'),
        'create_import_template': (('program_id', 'name'), ('program_cycle_id', 'file_type', 'schema_signature', *MAPPINGS),
                                   'Create a draft CSV/XLSX import template with explicit mapping JSON objects.', 'import_service.create_import_template'),
        'update_import_template': (('template_id',), ('name', 'schema_signature', *MAPPINGS),
                                   'Update template metadata/mapping JSON objects; {} clears an object. Locked mappings require cloning.', 'import_service.update_import_template'),
        'clone_import_template': (('template_id',), ('name', 'program_cycle_id'),
                                  'Clone an import template as a new unlocked draft in the same program, optionally into another cycle.', 'import_service.clone_import_template'),
    }
    return {name: definition(name=name, description=description, roles=('admin',), required_args=required,
                            allowed_fields=(*fields, 'expected_revision'), requires_confirmation=True, risk_level='high',
                            operation_type='update' if name == 'update_import_template' else 'create', scope_type='province',
                            canonical_service=service, display_type='detail', executor=partial(_execute, name))
            for name, (required, fields, description, service) in specs.items()}


def heuristic_plan(message, user):
    text = message.split('{', 1)[0].lower()
    if re.search(r'\b(delete|archive|approve|dispatch|explain|steps)\b|\bhow\s+(?:do|does|can|to)\b', text):
        return None
    name = None
    for verb, action in (('clone', 'clone'), ('create|add', 'create'), ('update|edit|rename', 'update')):
        if re.search(rf'\b(?:{verb})\s+(?:(?:an?|the)\s+)?(?:import|workbook)\s+template\b', text):
            name = action + '_import_template'
            break
    if name is None and re.search(r'\bclone\s+(?:the\s+)?(?:program\s+)?cycle\b', text):
        name = 'clone_program_cycle'
    if not name:
        return None
    plan = dict(assistant_reply='I will prepare the setup change for confirmation.', tool_calls=[],
                ai_provider_used='local', ai_model_used='local:program-setup', heuristic_rule_hit='program_setup')
    if not user or user.role != 'admin':
        plan['assistant_reply'] = 'Only administrators can clone cycles or manage import templates.'
        return plan
    args = {}
    for label, key in (('cycle', 'source_cycle_id' if name == 'clone_program_cycle' else 'program_cycle_id'),
                       ('template', 'template_id'), ('program', 'program_id')):
        match = re.search(rf'\b{label}\s*(?:#|id\s*)\s*([1-9]\d*)\b', text)
        if match:
            args[key] = int(match.group(1))
    if name == 'clone_program_cycle':
        year = re.search(r'\b(?:fy\s*|fiscal year\s*|into\s+|to\s+)(20\d\d|2100)\b', text)
        if year:
            args['fiscal_year'] = int(year.group(1))
        args.pop('program_id', None)
    if name == 'create_import_template':
        args.pop('template_id', None)
    if '{' in message:
        try:
            payload = json.loads(message[message.index('{'):])
            if not isinstance(payload, dict):
                raise ValueError()
            args.update(payload)
        except ValueError:
            plan['assistant_reply'] = 'Please supply a valid JSON object for the setup fields.'
            return plan
    tool = _registry().get_tool(name)
    missing = [key.replace('_', ' ') for key in tool.required_args if key not in args]
    if missing:
        plan['assistant_reply'] = 'Please provide ' + ', '.join(missing) + ' for this setup action.'
        return plan
    plan['tool_calls'] = [dict(tool_name=name, arguments=args, reason='Explicit cycle/template setup request.')]
    return plan
