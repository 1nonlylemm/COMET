"""Assistant coverage for master data and editable monitoring records.

All writes go through the same services as the API. Workflow decisions,
security administration and deletion are deliberately absent.
"""
import re
import json
from functools import partial

from app.extensions import db
from app.services import (
    access_service, auth_service, lgu_service, program_service,
    monthly_progress_service, form3_service, project_exception_service,
    non_infra_monitoring_service, beneficiary_evidence_service, monitoring_service,
)


OPERATIONAL = ('admin', 'staff', 'field_officer')
PAGE_FIELDS = ('page', 'per_page')
REQUIREMENT_FIELDS = (
    'name', 'description', 'requirement_type', 'document_category',
    'annex_reference', 'sort_order', 'is_mandatory', 'has_sla', 'sla_days',
    'custom_field_schema', 'checker_configuration', 'confirm_similar',
)
SAFE_USER_FIELDS = (
    'id', 'email', 'first_name', 'last_name', 'full_name', 'role', 'is_active',
    'assigned_clusters', 'assigned_lgus',
)

# service, get, list, update, serializer, editable fields, record ID name
RECORDS = {
    'monthly_progress_report': (
        monthly_progress_service, 'get_report', 'list_reports', 'update_report', '_serialize_report',
        ('assessment_date', 'self_reported_actual_pct', 'target_to_date_pct',
         'budget_utilization_pct', 'financial_progress_amount', 'qaar_inspection_id', 'evidence_submission_id'), 'report_id',
    ),
    'form3_request': (
        form3_service, 'get_request', 'list_requests', 'update_request', '_serialize_request',
        ('delay_reason_category', 'justification_text', 'requested_exemption_start',
         'requested_exemption_end', 'mov_submission_id'), 'request_id',
    ),
    'exception_report': (
        project_exception_service, 'get_report', 'list_reports', 'update_report', '_serialize_report',
        ('exception_category', 'description'), 'report_id',
    ),
    'non_infra_monitoring_record': (
        non_infra_monitoring_service, 'get_record', 'list_records', 'update_record', '_serialize_record',
        ('reporting_period', 'appendix_reference', 'items_verified_summary', 'specifications_met', 'remarks'), 'record_id',
    ),
    'beneficiary_evidence_record': (
        beneficiary_evidence_service, 'get_record', 'list_records', 'update_record', '_serialize_record',
        ('appendix_reference', 'beneficiary_count', 'distribution_date', 'reference_number', 'description'), 'record_id',
    ),
    'monitoring_inspection': (
        monitoring_service, 'get_inspection', None, 'update_inspection', '_serialize_inspection',
        ('inspection_date', 'physical_accomplishment_pct', 'observation_summary', 'findings',
         'recommendations', 'agreement_summary', 'issues_identified', 'is_site_visit',
         'aide_memoire_text', 'annex_d_reference'), 'inspection_id',
    ),
}

ERRORS = (
    access_service.AccessError, auth_service.AuthError, lgu_service.LguError,
    program_service.ProgramError, monthly_progress_service.MonthlyProgressError,
    form3_service.Form3Error, project_exception_service.ProjectExceptionError,
    non_infra_monitoring_service.NonInfraMonitoringError,
    beneficiary_evidence_service.BeneficiaryEvidenceError, monitoring_service.MonitoringError,
)


def _registry():
    from app.services import ai_tool_registry
    return ai_tool_registry


def _integer(value, label):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9]\d*', str(value)):
        raise _registry().AiToolError(f'{label} must be a positive integer.', 422)
    return int(value)


def _payload(tool, args):
    return {key: args[key] for key in tool.allowed_fields if key in args}


def _master_record_matches(entity, text):
    """Resolve human-readable LGU/program/cluster names to canonical records."""
    from app.models import LguCluster, LguProfile, Program

    model = {'lgu': LguProfile, 'program': Program, 'cluster': LguCluster}[entity]
    records = model.query.all()
    haystack = (text or '').casefold()
    matches = []
    for record in records:
        aliases = [record.name]
        if entity == 'lgu':
            aliases.append(record.municipality)
            aliases.append(re.sub(r'^(?:city|municipality)\s+of\s+|\s+city$', '', record.name or '', flags=re.I))
            aliases.append(re.sub(r'^(?:city|municipality)\s+of\s+|\s+city$', '', record.municipality or '', flags=re.I))
        elif entity == 'program':
            aliases.append(record.code)
            # Program acronyms are commonly spoken without the LGSF prefix.
            aliases.extend(re.split(r'[-_\s]+', record.code or ''))
        score = max((len(alias.strip()) for alias in aliases
                     if alias and len(alias.strip()) >= 3
                     and re.search(rf'(?<!\w){re.escape(alias.strip())}(?!\w)', haystack, re.I)), default=0)
        if score:
            matches.append((score, record))
    if not matches:
        return []
    longest = max(score for score, _ in matches)
    return [record for score, record in matches if score == longest]


def _extract_update_value(message, allowed_fields):
    """Read common `field to value` edits while preserving multiword values."""
    field_aliases = {
        'name': r'(?:name|nama)',
        'municipality': r'municipality',
        'province': r'province',
        'code': r'(?:program\s+)?code',
        'program_type': r'program[_ ]type|type',
        'description': r'description',
        'funding_agency': r'funding[_ ]agency',
        'is_active': r'(?:active|status)',
        'cluster_id': r'cluster(?:\s+id)?',
        'mayor_name': r'mayor(?:\s+name)?',
        'mayor_email': r'mayor[_ ]email',
        'contact_person': r'contact[_ ]person',
        'contact_email': r'contact[_ ]email',
        'contact_phone': r'contact[_ ]phone',
    }
    for field in allowed_fields:
        label = field_aliases.get(field, re.escape(field).replace('_', '[_ ]'))
        match = re.search(
            rf'\b(?:update|edit|change|set|rename)\b.*?\b{label}\b.*?\b(?:to|as)\s+["\']?(.+?)["\']?(?:[.!?]|$)',
            message,
            re.I,
        )
        if not match:
            match = re.search(rf'\b{label}\s*(?:=|:|\bto\b|\bas\b|\bis\b)\s*["\']?(.+?)["\']?(?:[.!?]|$)', message, re.I)
        if match:
            value = match.group(1).strip().strip(' "\'')
            if value:
                if field == 'is_active':
                    normalized = value.casefold()
                    if normalized in ('active', 'yes', 'true', 'enabled'):
                        value = True
                    elif normalized in ('inactive', 'no', 'false', 'disabled'):
                        value = False
                elif field in ('name', 'municipality', 'province', 'code', 'description', 'funding_agency', 'program_type'):
                    value = value[:200] if field != 'description' else value
                return field, value
    return None, None


def _extract_master_create_fields(entity, message, allowed_fields):
    """Extract straightforward named fields for LGU/program/cluster creation."""
    text = message or ''
    args = {}
    name_match = re.search(
        r'\b(?:name\s+it|named|called|name)\s*(?:is|as|:)?\s*["\']?(.+?)["\']?(?=\s+(?:in|under|with|province|municipality|code|type)\b|[,;.!?]|$)',
        text,
        re.I,
    )
    if name_match and 'name' in allowed_fields:
        args['name'] = name_match.group(1).strip().strip(' "\'')

    labels = {
        'municipality': r'municipality(?:\s+of)?',
        'province': r'province',
        'code': r'(?:program\s+)?code',
        'program_type': r'(?:program\s+)?type',
        'description': r'description',
        'funding_agency': r'funding[_ ]agency',
    }
    for field, label in labels.items():
        if field not in allowed_fields:
            continue
        found = re.search(rf'\b{label}\s*(?:=|:|\bis\b)?\s*["\']?(.+?)["\']?(?:[,;.!?]|$)', text, re.I)
        if found:
            args[field] = found.group(1).strip().strip(' "\'')

    if entity == 'lgu' and not args.get('municipality') and args.get('name'):
        inferred = re.match(r'^(?:municipality|city)\s+of\s+(.+)$', args['name'], re.I)
        if inferred:
            args['municipality'] = inferred.group(1).strip()
    if entity == 'program' and 'program_type' in allowed_fields and 'program_type' not in args:
        type_match = re.search(r'\b(hybrid|infrastructure|non[- ]infrastructure)\b', text, re.I)
        if type_match:
            args['program_type'] = type_match.group(1).lower().replace('-', '_').replace(' ', '_')
    return args


def _safe_user(data):
    return {key: data[key] for key in SAFE_USER_FIELDS if key in data}


def _table(title, rows, args, total=None):
    page, size = args.get('page', 1), args.get('per_page', 10)
    if total is None:
        total = len(rows)
        rows = rows[(page - 1) * size:page * size]
    columns = [{'key': key, 'label': key.replace('_', ' ').title()}
               for key in ('id', 'name', 'code', 'project_id', 'reporting_period', 'email', 'role')
               if any(key in row for row in rows)]
    summary = None
    if title == _registry().get_user_facing_tool_label('list_programs'):
        year = f" for FY {args['fiscal_year']}" if args.get('fiscal_year') else ''
        entries = [f"{row['name']} ({row['code']})" if row.get('code') and row['code'] not in row['name']
                   else row['name'] for row in rows]
        summary = (f"Found {total} program(s){year}. " + '; '.join(entries) + '.'
                   if entries else f"No programs found{year}.")
    return _registry()._table_result(title, rows, columns, summary=summary, meta={
        'page': page, 'per_page': size, 'total': total, 'pages': (total + size - 1) // size,
    })


def _get_record(entity, args, user):
    service, getter, _, _, _, _, id_key = RECORDS[entity]
    return getattr(service, getter)(args[id_key], user_id=user.id)


def prepare(tool, args, user):
    """Validate IDs, scope and preview before staging, and again on execution."""
    if tool.name not in TOOL_NAMES:
        return
    registry = _registry()
    permitted = set(tool.required_args) | set(tool.allowed_fields)
    if tool.name.startswith('list_'):
        permitted.update(PAGE_FIELDS)
    extra = set(args) - permitted - {'confirmation_display', 'reason'}
    if extra:
        raise registry.AiToolError(f'Unsupported fields: {", ".join(sorted(extra))}.', 422)
    for key in permitted:
        if key.endswith('_id') and key in args and args[key] is not None:
            args[key] = _integer(args[key], key)
    if tool.name.startswith('list_'):
        args['page'] = _integer(args.get('page', 1), 'page')
        args['per_page'] = min(_integer(args.get('per_page', 10), 'per_page'), 20)
    for key in ('is_active', 'is_mandatory', 'has_sla', 'confirm_similar', 'baseline_only', 'specifications_met', 'is_site_visit'):
        if key in args and args[key] is not None and not isinstance(args[key], bool):
            raise registry.AiToolError(f'{key} must be a boolean.', 422)
    if tool.operation_type == 'update' and not any(key in args for key in tool.allowed_fields):
        raise registry.AiToolError('Provide at least one field to update.', 422)
    from app.api.programs import schemas as program_schemas
    validators = {
        'create_program_phase': program_schemas.validate_phase_create,
        'update_program_phase': program_schemas.validate_phase_update,
        'create_requirement_definition': program_schemas.validate_requirement_create,
        'update_requirement_definition': program_schemas.validate_requirement_update,
    }
    if tool.name in validators:
        errors = validators[tool.name](_payload(tool, args))
        if errors:
            raise registry.AiToolError('; '.join(f'{key}: {value}' for key, value in errors.items()), 422)
    if tool.name == 'update_monitoring_inspection':
        from app.api.monitoring.schemas import validate_inspection_payload
        errors = validate_inspection_payload(_payload(tool, args), partial=True)
        if errors:
            raise registry.AiToolError(str(errors), 422)

    try:
        before = None
        entity = RECORD_TOOL_ENTITIES.get(tool.name)
        if entity:
            if tool.name.startswith(('get_', 'update_')):
                item = _get_record(entity, args, user)
                before = getattr(RECORDS[entity][0], RECORDS[entity][4])(item)
                if tool.name.startswith('update_'):
                    access_service.assert_project_movement_allowed(item.project_id)
                    requirement = getattr(item, 'project_requirement', None)
                    if requirement and requirement.workflow_status not in (None, 'draft', 'returned_for_revision'):
                        raise registry.AiToolError('Submitted records must be returned through the review workflow before editing.', 409)
                    if entity == 'monitoring_inspection' and item.status == 'approved':
                        raise registry.AiToolError('Approved inspections cannot be edited through the assistant.', 409)
            if args.get('project_id'):
                registry._ensure_project_arg(args, 'project_id', user, required=True,
                                             assert_movement=tool.operation_type == 'create')
        if tool.name in ('get_lgu', 'list_lgus'):
            if tool.name == 'get_lgu':
                lgu_service.get_lgu(args['lgu_id'], user_id=user.id)
            if args.get('cluster_id'):
                lgu_service.get_cluster(args['cluster_id'], user_id=user.id)
        if tool.name == 'get_cluster':
            lgu_service.get_cluster(args['cluster_id'], user_id=user.id)
        if tool.name == 'get_user':
            auth_service.get_user_for_admin(args['user_id'], actor_id=user.id)
        if 'program_id' in args:
            program_service.get_program(args['program_id'])
        if 'cycle_id' in args:
            program_service.get_program_cycle(args['cycle_id'])
        if 'phase_id' in args:
            from app.models import ProgramPhase
            phase = db.session.get(ProgramPhase, args['phase_id'])
            if not phase:
                raise registry.AiToolError('Program phase not found.', 404)
            before = program_service._serialize_phase(phase)
        if 'definition_id' in args:
            definition = program_service.get_requirement(args['definition_id'])
            before = program_service._serialize_requirement(definition)
        if tool.name in ('list_requirement_definitions', 'get_program_matrix'):
            # Let the canonical resolver reject cycles belonging to another program.
            program_service._resolve_program_cycle(args['program_id'], args.get('program_cycle_id'), args.get('fiscal_year'))
        if tool.requires_confirmation:
            # Never trust a model-provided confirmation preview.
            target = {key: args[key] for key in tool.required_args if key.endswith('_id')}
            target_label = ', '.join(f'{key.replace("_id", "").replace("_", " ")} #{value}'
                                     for key, value in target.items())
            args['confirmation_display'] = {
                'action': registry.get_user_facing_tool_label(tool.name),
                'before': before,
                'changes': {key: {'from': (before or {}).get(key), 'to': value}
                            for key, value in _payload(tool, args).items()},
                'target': target,
                'notice': f'Target: {target_label}. Formal workflow decisions remain in the review workspace.',
            }
    except ERRORS as exc:
        raise registry.AiToolError(exc.message, exc.status_code) from exc


def _execute(name, args, user):
    registry = _registry()
    tool = registry.get_tool(name)
    data = _payload(tool, args)
    title = registry.get_user_facing_tool_label(name)
    try:
        entity = RECORD_TOOL_ENTITIES.get(name)
        if entity:
            service, getter, lister, updater, serializer, _, id_key = RECORDS[entity]
            if name.startswith('list_'):
                filters = {key: value for key, value in data.items() if key not in PAGE_FIELDS}
                return _table(title, getattr(service, lister)(**filters, user_id=user.id), args)
            if name.startswith('get_'):
                item = getattr(service, getter)(args[id_key], user_id=user.id)
            elif name.startswith('update_'):
                item = getattr(service, updater)(args[id_key], data, user_id=user.id)
            else:
                item = service.create_report(data, user_id=user.id)
            return registry._detail_result(title, getattr(service, serializer)(item))
        if name == 'list_lgus':
            result = lgu_service.list_lgus(**data, page=args['page'], per_page=args['per_page'], user_id=user.id)
            return _table(title, result['lgus'], args, result['total'])
        if name == 'get_lgu':
            result = lgu_service._serialize_lgu(lgu_service.get_lgu(args['lgu_id'], user_id=user.id))
        elif name == 'list_clusters':
            return _table(title, lgu_service.list_clusters(search=args.get('search'), user_id=user.id), args)
        elif name == 'get_cluster':
            result = lgu_service._serialize_cluster(lgu_service.get_cluster(args['cluster_id'], user_id=user.id))
        elif name == 'list_programs':
            result = program_service.list_programs(**data, page=args['page'], per_page=args['per_page'])
            return _table(title, result['programs'], args, result['total'])
        elif name == 'get_program':
            result = program_service._serialize_program(program_service.get_program(args['program_id']))
        elif name == 'list_program_cycles':
            return _table(title, program_service.list_program_cycles(args['program_id'], **data), args)
        elif name == 'get_program_cycle':
            result = program_service._serialize_program_cycle(program_service.get_program_cycle(args['cycle_id']))
        elif name == 'list_users':
            result = auth_service.list_users(**data, page=args['page'], per_page=args['per_page'], actor_id=user.id)
            return _table(title, [_safe_user(row) for row in result['users']], args, result['total'])
        elif name == 'get_user':
            result = _safe_user(auth_service.get_user_for_admin(args['user_id'], actor_id=user.id))
        elif name == 'list_program_phases':
            return _table(title, program_service.list_phases(args['program_id']), args)
        elif name == 'get_program_matrix':
            result = program_service.get_program_matrix(args['program_id'], **data)
        elif name == 'create_program_phase':
            result = program_service._serialize_phase(program_service.create_phase(args['program_id'], **data, user_id=user.id))
        elif name == 'update_program_phase':
            result = program_service._serialize_phase(program_service.update_phase(args['phase_id'], data, user_id=user.id))
        elif name == 'list_requirement_definitions':
            return _table(title, program_service.list_requirements(program_id=args['program_id'], **data), args)
        elif name == 'get_requirement_definition':
            result = program_service._serialize_requirement(program_service.get_requirement(args['definition_id']))
        elif name == 'create_requirement_definition':
            result = program_service._serialize_requirement(program_service.create_requirement(args['phase_id'], **data, user_id=user.id))
        elif name == 'update_requirement_definition':
            result = program_service._serialize_requirement(program_service.update_requirement(args['definition_id'], data, user_id=user.id))
        else:
            raise registry.AiToolError('Unsupported assistant action.', 422)
        summary = None
        if name in ('get_lgu', 'get_program', 'get_cluster'):
            label = result.get('name') or title
            context = [str(result[key]) for key in ('code', 'municipality', 'province') if result.get(key)]
            summary = f"{label}" + (f" ({', '.join(context)})" if context else '') + '.'
        return registry._detail_result(title, result, summary=summary)
    except ERRORS as exc:
        db.session.rollback()
        raise registry.AiToolError(exc.message, exc.status_code) from exc


TOOL_NAMES = set()
RECORD_TOOL_ENTITIES = {}
MASTER_WRITE_TOOL_NAMES = {
    'create_lgu', 'update_lgu',
    'create_cluster', 'update_cluster',
    'create_program', 'update_program',
}


def build_tools(definition):
    tools = {}

    def add(name, required=(), fields=(), roles=OPERATIONAL, operation='read', description=None):
        label = name.replace('_', ' ').capitalize()
        service_methods = {
            'list_lgus': 'lgu_service.list_lgus', 'get_lgu': 'lgu_service.get_lgu',
            'list_clusters': 'lgu_service.list_clusters', 'get_cluster': 'lgu_service.get_cluster',
            'list_programs': 'program_service.list_programs', 'get_program': 'program_service.get_program',
            'list_program_cycles': 'program_service.list_program_cycles', 'get_program_cycle': 'program_service.get_program_cycle',
            'list_users': 'auth_service.list_users', 'get_user': 'auth_service.get_user_for_admin',
            'list_program_phases': 'program_service.list_phases', 'get_program_matrix': 'program_service.get_program_matrix',
            'create_program_phase': 'program_service.create_phase', 'update_program_phase': 'program_service.update_phase',
            'list_requirement_definitions': 'program_service.list_requirements',
            'get_requirement_definition': 'program_service.get_requirement',
            'create_requirement_definition': 'program_service.create_requirement',
            'update_requirement_definition': 'program_service.update_requirement',
        }
        if name in RECORD_TOOL_ENTITIES:
            service, getter, lister, updater, _, _, _ = RECORDS[RECORD_TOOL_ENTITIES[name]]
            method = lister if name.startswith('list_') else getter if operation == 'read' else updater if operation == 'update' else 'create_report'
            service_methods[name] = f'{service.__name__.rsplit(".", 1)[-1]}.{method}'
        description = description or label
        if name.startswith('list_'):
            description += '. Supports page and per_page (maximum 20).'
        tools[name] = definition(
            name=name, description=description, roles=roles,
            required_args=required, allowed_fields=fields,
            requires_confirmation=operation != 'read',
            risk_level='medium' if operation != 'read' else 'low',
            operation_type=operation, scope_type='lgu' if name in RECORD_TOOL_ENTITIES else 'province',
            canonical_service=service_methods[name],
            display_type='table' if name.startswith('list_') else 'detail',
            executor=partial(_execute, name),
        )

    add('list_lgus', fields=('search', 'cluster_id', 'is_active'))
    add('get_lgu', ('lgu_id',))
    add('list_clusters', fields=('search',))
    add('get_cluster', ('cluster_id',))
    add('list_programs', fields=('search', 'program_type', 'is_active', 'fiscal_year'))
    add('get_program', ('program_id',))
    add('list_program_cycles', ('program_id',), ('is_active', 'fiscal_year'))
    add('get_program_cycle', ('cycle_id',))
    add('list_users', fields=('search', 'role', 'is_active'), roles=('admin',))
    add('get_user', ('user_id',), roles=('admin',))
    add('list_program_phases', ('program_id',))
    add('get_program_matrix', ('program_id',), ('program_cycle_id', 'fiscal_year', 'baseline_only'))
    add('create_program_phase', ('program_id', 'name', 'phase_order'), ('name', 'phase_order', 'description'), ('admin',), 'create')
    add('update_program_phase', ('phase_id',), ('name', 'phase_order', 'description'), ('admin',), 'update')
    add('list_requirement_definitions', ('program_id',), ('program_cycle_id', 'fiscal_year', 'requirement_type', 'is_mandatory'))
    add('get_requirement_definition', ('definition_id',))
    add('create_requirement_definition', ('phase_id', 'name'), REQUIREMENT_FIELDS, ('admin',), 'create',
        'Create a baseline program requirement definition. Does not approve project evidence or create a cycle-specific variant.')
    add('update_requirement_definition', ('definition_id',), REQUIREMENT_FIELDS, ('admin',), 'update',
        'Edit a requirement definition in its existing baseline or cycle. Cannot move it between cycles or approve evidence.')
    for entity, spec in RECORDS.items():
        _, _, _, _, _, fields, id_key = spec
        names = [('get_' + entity, (id_key,), (), 'read'),
                 ('update_' + entity, (id_key,), fields, 'update')]
        if entity in ('monthly_progress_report', 'form3_request', 'exception_report'):
            names.append(('list_' + entity + 's', (), ('project_id', 'reporting_period', 'workflow_status'), 'read'))
        if entity == 'exception_report':
            names.append(('create_exception_report', ('project_id', 'reporting_period'),
                          ('project_id', 'reporting_period', 'exception_category', 'description'), 'create'))
        for name, required, allowed, operation in names:
            RECORD_TOOL_ENTITIES[name] = entity
            roles = ('admin', 'staff') if entity == 'monitoring_inspection' and operation == 'update' else OPERATIONAL
            add(name, required, allowed, roles, operation)
    TOOL_NAMES.update(tools)
    return tools


def heuristic_plan(message, user):
    """Conservative fallback for explicit entity reads and structured edits.

    Free-form argument extraction remains with the LLM. Missing identifiers
    are requested rather than inferred from unrelated project/requirement IDs.
    """
    if user is None:
        return None
    text = message.lower()
    if not re.search(r'\b(list|show|view|get|find|create|add|update|edit|rename|change|set|give|tell|provide|what|ihatag|ibigay|bigay)\b', text):
        return None
    patterns = (
        (r'\brequirement definitions?\b', 'requirement_definition', 'definition_id'),
        (r'\bprogram (?:phases?|stages?)\b', 'program_phase', 'phase_id'),
        (r'\bprogram (?:cycles?)\b', 'program_cycle', 'cycle_id'),
        (r'\bmonthly progress reports?\b', 'monthly_progress_report', 'report_id'),
        (r'\bform\s*3 requests?\b', 'form3_request', 'request_id'),
        (r'\bexception reports?\b', 'exception_report', 'report_id'),
        (r'\bnon[- ]infra(?:structure)? monitoring records?\b', 'non_infra_monitoring_record', 'record_id'),
        (r'\bbeneficiary evidence records?\b', 'beneficiary_evidence_record', 'record_id'),
        (r'\b(?:monitoring|qaar) inspections?\b', 'monitoring_inspection', 'inspection_id'),
        (r'\bclusters?\b', 'cluster', 'cluster_id'),
        (r'\blgus?\b', 'lgu', 'lgu_id'),
        (r'\bprograms?\b', 'program', 'program_id'),
        (r'\busers?\b', 'user', 'user_id'),
    )
    if re.search(r'\b(import|delete|archive|approve|return|waive|release|dispatch|transition|bulk)\b', text):
        return None
    selected = next(((match, entity, key) for pattern, entity, key in patterns
                     if (match := re.search(pattern, text))), None)
    verb_match = re.search(r'\b(list|show|view|get|find|create|add|update|edit|rename|change|set|give|tell|provide|what|ihatag|ibigay|bigay)\b', text)
    if not selected and verb_match and verb_match.group(1) in ('update', 'edit', 'rename', 'change', 'set') and re.search(r'\bname\b', text):
        identity_text = re.split(r'\bto\b', message, maxsplit=1, flags=re.I)[0]
        inferred = []
        for entity, key in (('lgu', 'lgu_id'), ('program', 'program_id'), ('cluster', 'cluster_id')):
            inferred.extend((entity, key, record) for record in _master_record_matches(entity, identity_text))
        if len(inferred) == 1:
            entity, key, _record = inferred[0]
            selected = (re.search(r'\bname\b', text), entity, key)
        elif inferred:
            kinds = ', '.join(sorted({entity.upper() for entity, _, _ in inferred}))
            return {'assistant_reply': f"I found matching records in {kinds}. Which type of record do you want to rename?",
                    'tool_calls': [], 'ai_provider_used': 'local', 'heuristic_rule_hit': 'cru_ambiguous_entity'}
    if not selected:
        return None
    match, entity, id_key = selected
    if not verb_match:
        return None
    # The subject must directly follow the action. Do not steal requests such
    # as "show projects for LGU 7" or "update project 3 in program 2".
    between = text[verb_match.end():match.start()].strip()
    verb = verb_match.group(1)
    conversational_read = (
        verb in ('give', 'tell', 'provide', 'what', 'ihatag', 'ibigay', 'bigay')
        and bool(re.search(r'\b(details?|information|record|profile|detalye|impormasyon|data)\b', text))
    ) or (
        verb in ('what', 'tell')
        and entity in ('lgu', 'program', 'cluster')
        and bool(re.search(r'\b(?:about|is|are|name|code|type)\b', between))
        and not re.search(r'\bprojects?\b', text)
    )
    if not conversational_read and not re.fullmatch(r'(?:(?:all|the|a|an|new|me|our|operational|available|active)\s*)*', between):
        return None
    args = {}
    # IDs are only read from explicit ID fields or labels; no bare-number guesses.
    for key, label in ((id_key, re.escape(match.group())), ('program_id', 'program'),
                       ('project_id', 'project'), ('phase_id', 'phase'), ('program_cycle_id', 'cycle')):
        found = re.search(rf'\b(?:{key}\s*[=:]\s*|{label}\s*(?:id\s*|#)?\s*)([1-9]\d*)\b', text)
        if found:
            args[key] = int(found.group(1))

    if entity in ('lgu', 'program', 'cluster') and id_key not in args and verb in ('get', 'view', 'show', 'find', 'give', 'tell', 'provide', 'what', 'ihatag', 'ibigay', 'bigay', 'update', 'edit', 'rename', 'change', 'set'):
        # For edits, resolve the existing record from the target portion only;
        # the value after "to" may itself be another valid LGU/program name.
        identity_text = message
        if verb in ('update', 'edit', 'rename', 'change', 'set'):
            identity_text = re.split(r'\bto\b', message, maxsplit=1, flags=re.I)[0]
        matches = _master_record_matches(entity, identity_text)
        if len(matches) == 1:
            args[id_key] = matches[0].id
        elif len(matches) > 1:
            choices = ', '.join(getattr(record, 'name', f'{entity} #{record.id}') for record in matches[:5])
            return {
                'assistant_reply': f"I found multiple matching {entity.upper()} records: {choices}. Which one do you mean?",
                'tool_calls': [], 'ai_provider_used': 'local', 'heuristic_rule_hit': 'cru_ambiguous_entity',
            }
    operation = 'create' if verb in ('create', 'add') else 'update' if verb in ('update', 'edit', 'rename', 'change', 'set') else 'get' if id_key in args else 'list'
    if verb in ('give', 'tell', 'provide', 'what', 'ihatag', 'ibigay', 'bigay'):
        operation = 'get' if id_key in args else 'list'
    name = f'{operation}_{entity}' + ('s' if operation == 'list' else '')
    if entity == 'program_phase' and operation == 'list':
        name = 'list_program_phases'
    if name not in TOOL_NAMES and name not in MASTER_WRITE_TOOL_NAMES:
        return None
    tool = _registry().get_tool(name)
    if user.role not in tool.roles:
        return {'assistant_reply': 'Your role cannot perform that action.', 'tool_calls': [],
                'ai_provider_used': 'local', 'heuristic_rule_hit': 'cru_role_refusal'}
    permitted = set(tool.required_args) | set(tool.allowed_fields) | set(PAGE_FIELDS)
    args = {key: value for key, value in args.items() if key in permitted}
    if operation == 'create' and entity in ('lgu', 'program', 'cluster'):
        args.update(_extract_master_create_fields(entity, message, tool.allowed_fields))
        if entity == 'lgu' and 'cluster_id' in tool.allowed_fields:
            clusters = _master_record_matches('cluster', message)
            if len(clusters) == 1:
                args['cluster_id'] = clusters[0].id
    if operation == 'list' and 'search' in tool.allowed_fields:
        tail = message[match.end():].strip().rstrip('.?')
        if tail and '{' not in tail:
            # Do not turn a named lookup into an unfiltered list when the
            # remote planner is unavailable. Unsupported compound filters
            # stay with the main planner rather than being silently ignored.
            named = re.match(r'^(?:named|matching|containing|called)\s+(.+)$', tail, re.I)
            inventory_context = (
                entity in ('program', 'lgu', 'cluster')
                and re.fullmatch(r'(?:(?:are|available|here|in|for|during|this|the|current|currently|now|fiscal|year|fy|active)\s*|(?:19|20)\d{2}\s*)+', tail, re.I)
                and re.search(r'\b(?:here|available|current|currently|now|year|fy|active|(?:19|20)\d{2})\b', tail, re.I)
            )
            if named:
                args['search'] = named.group(1).strip('"\' ')
            elif inventory_context:
                year = re.search(r'\b((?:19|20)\d{2})\b', tail)
                if year and 'fiscal_year' in tool.allowed_fields:
                    args['fiscal_year'] = int(year.group(1))
            elif verb in ('find', 'get', 'view') and not re.search(r'\b(for|in|with|where|by)\b', tail, re.I):
                args['search'] = tail.strip('"\' ')
            else:
                return None
    if operation == 'list' and 'is_active' in tool.allowed_fields and re.search(r'\b(?:available|active)\b', between + ' ' + message[match.end():], re.I):
        args['is_active'] = True
    if '{' in message:
        try:
            payload = json.loads(message[message.index('{'):])
            if not isinstance(payload, dict):
                return None
            args.update(payload)
        except (ValueError, TypeError):
            return None
    # Natural fallback for common name/description edits and reporting-period filters.
    for key in ('name', 'description', 'remarks', 'justification_text', 'observation_summary'):
        if key in args:
            continue  # Explicit JSON values take precedence over natural text.
        label = r'(?:description|describing)' if key == 'description' else key.replace('_', '[_ ]')
        value = re.search(rf'\b{label}\s*(?:=|:|\bto\b|\bis\b)?\s*["\']([^"\']+)["\']', message, re.I)
        if value and key in tool.allowed_fields:
            args[key] = value.group(1)
    period = re.search(r'\b(20\d\d-(?:0[1-9]|1[0-2]))\b', text)
    if period and 'reporting_period' in tool.allowed_fields:
        args['reporting_period'] = period.group(1)
    if operation == 'update' and entity in ('lgu', 'program', 'cluster'):
        field, value = _extract_update_value(message, tool.allowed_fields)
        if field and field not in args:
            if field == 'cluster_id' and isinstance(value, str) and not value.isdigit():
                clusters = _master_record_matches('cluster', value)
                if len(clusters) == 1:
                    value = clusters[0].id
                elif len(clusters) > 1:
                    choices = ', '.join(cluster.name for cluster in clusters[:5])
                    return {'assistant_reply': f"I found multiple clusters matching that name: {choices}. Which cluster should I use?",
                            'tool_calls': [], 'ai_provider_used': 'local', 'heuristic_rule_hit': 'cru_ambiguous_entity'}
                else:
                    return {'assistant_reply': f"I couldn't find a cluster named '{value}'. Which existing cluster should I assign?",
                            'tool_calls': [], 'ai_provider_used': 'local', 'heuristic_rule_hit': 'cru_missing_cluster'}
            if field == 'program_type':
                value = str(value).lower().replace('-', '_').replace(' ', '_')
            args[field] = value
    missing = [key for key in tool.required_args if key not in args]
    if operation == 'update' and not any(key in args for key in tool.allowed_fields):
        missing.append('the fields and values to change')
    if missing:
        missing_labels = {
            'lgu_id': 'the LGU name or ID',
            'program_id': 'the program name, code, or ID',
            'cluster_id': 'the cluster name or ID',
        }
        return {'assistant_reply': 'Please provide ' + ', '.join(missing_labels.get(key, key.replace('_', ' ')) for key in missing) + '.',
                'tool_calls': [], 'ai_provider_used': 'local', 'heuristic_rule_hit': 'cru_clarification'}
    return {'assistant_reply': 'I will prepare that change for confirmation.' if tool.requires_confirmation else 'I will retrieve those records.',
            'tool_calls': [{'tool_name': name, 'arguments': args, 'reason': 'Explicit entity request.'}],
            'ai_provider_used': 'local', 'heuristic_rule_hit': 'cru_coverage'}
