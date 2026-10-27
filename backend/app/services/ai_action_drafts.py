"""Resume explicit record edits without depending on a provider remembering a form.

Drafts contain user supplied values only. Execution, scope validation and confirmation
remain in the tool registry and the assistant's normal tool-call lifecycle.
"""
import json
import re

from app.services import ai_tool_registry as registry


SUBJECTS = (
    (r'monthly\s+progress\s+report', 'monthly_progress_report'),
    (r'form\s*3\s+request', 'form3_request'),
    (r'exception\s+report', 'exception_report'),
    (r'non[- ]infra(?:structure)?\s+monitoring\s+record', 'non_infra_monitoring_record'),
    (r'beneficiary\s+evidence\s+record', 'beneficiary_evidence_record'),
    (r'(?:monitoring|qaar)\s+inspection', 'monitoring_inspection'),
    (r'program\s+phase', 'program_phase'),
    (r'program\s+cycle', 'program_cycle'),
    (r'requirement\s+definition', 'requirement_definition'),
    (r'LGU', 'lgu'), (r'cluster', 'cluster'), (r'program', 'program'),
    (r'project', 'project'),
)
ALIASES = {
    'name': ('official name', 'name'),
    'project_name': ('project name', 'name'),
    'fiscal_year': ('fiscal year', 'year'),
    'mayor_name': ("mayor's name", "mayor's office", 'mayor name', 'mayor'),
    'contact_phone': ('contact phone', 'phone'),
    'contact_email': ('contact email', 'email'),
    'cluster_id': ('cluster id', 'cluster assignment', 'cluster'),
    'lgu_id': ('lgu id', 'lgu'),
    'program_id': ('program id', 'program'),
    'program_type': ('program type', 'type'),
    'project_kind': ('project kind', 'project type', 'classification'),
}


def _fields(message, tool):
    permitted = set(tool.required_args) | set(tool.allowed_fields)
    values = {}
    if '{' in message:
        try:
            payload = json.loads(message[message.index('{'):])
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        # Keep unsupported JSON fields so registry validation cannot silently drop them.
        values.update(payload)
        message = message[:message.index('{')]
    labels = {}
    for key in permitted:
        for alias in ALIASES.get(key, (key.replace('_', ' '),)):
            labels[alias] = key
        labels[key] = key
    pattern = '|'.join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
    labeled = list(re.finditer(rf'\b({pattern})\s*(?::|=|\bto\b|\bis\b)\s*', message, re.I))
    for index, match in enumerate(labeled):
        end = labeled[index + 1].start() if index + 1 < len(labeled) else len(message)
        raw = message[match.end():end]
        # Unsupported form labels (e.g. LGU Type) must not become part of the
        # preceding name or phone number.
        raw = re.split(r'\r?\n\s*[^:\r\n]{1,80}:', raw, maxsplit=1)[0]
        raw = re.sub(r'\s+and\s*$', '', raw).strip(' \t\r\n,;.').strip('"\'')
        key = labels[match.group(1).lower()]
        if key not in values and raw:
            values[key] = raw
    for key in permitted:
        label = r'(?:description|describing)' if key == 'description' else re.escape(key).replace('_', '[_ ]')
        quoted = re.search(rf'\b{label}\s*(?::|=|\bto\b|\bis\b)?\s*["\']([^"\']+)["\']', message, re.I)
        if quoted and key not in values:
            values[key] = quoted.group(1)
    for key in permitted:
        if key.endswith('_id') or key == 'fiscal_year':
            label = key[:-3] if key.endswith('_id') else r'(?:fiscal\s+year|FY)'
            found = re.search(rf'\b{label}\s*(?:id\s*|#\s*|:\s*|=\s*)?([1-9]\d*)\b', message, re.I)
            if found and key not in values:
                values[key] = int(found.group(1))
        if key in values and isinstance(values[key], str):
            raw = values[key]
            if (key.endswith('_id') or key in ('fiscal_year', 'phase_order')) and re.fullmatch(r'#?\d+', raw):
                values[key] = int(raw.lstrip('#'))
            elif key in ('is_active', 'is_mandatory', 'has_sla', 'confirm_similar', 'specifications_met', 'is_site_visit') and raw.lower() in ('true', 'false'):
                values[key] = raw.lower() == 'true'
    if tool.operation_type == 'create':
        name_key = 'project_name' if tool.name == 'create_project' else 'name'
        named = re.search(r'\b(?:named|called|titled|name\s+it\s+as|name\s+it)\s+(.+?)(?=\s+(?:for|under|in|with)\b|[,;\n]|$)', message, re.I)
        if named and name_key in permitted and name_key not in values:
            values[name_key] = named.group(1).strip(' "\'.')
    if tool.name in ('create_lgu', 'update_lgu'):
        channel = re.search(r'^\s*(?:official website\s*/\s*)?contact channel\s*:\s*(.+)$', message, re.I | re.M)
        if channel:
            email = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', channel.group(1))
            if email:
                values.setdefault('contact_email', email.group())
            phone = re.search(r'/\s*([+\d(][\d() +.-]+)\s*$', channel.group(1))
            if phone:
                values.setdefault('contact_phone', phone.group(1).strip())
    return values


def plan(conversation, message, user):
    """Handle direct record requests and labeled replies; leave other topics alone."""
    text = (message or '').strip()
    if re.match(r"^(?:please\s+)?(?:do\s+not|don't|don’t|never)\s+(?:create|add|register|update|edit|rename|modify)\b", text, re.I):
        return {'assistant_reply': 'No action was prepared.', 'tool_calls': [],
                'ai_provider_used': 'local', 'provider_called': False,
                'heuristic_rule_hit': 'action_not_requested'}
    ctx = getattr(conversation, 'context', None) or {}
    pending = ctx.get('pending_action_draft') or {}
    if pending and text.lower().rstrip('.!') in ('cancel', 'never mind', 'nevermind', 'stop', 'forget it'):
        return _response('Cancelled the record change.', None, {}, clear=True)
    # Guidance, imports, bulk actions and governance workflows have their own routers.
    if re.search(r'\b(?:import|bulk|delete|archive|approve|waive|dispatch|release)\b', text, re.I):
        return None
    command = None
    assignment = re.match(r'^(?:please\s+)?(?:assign|move|place|put|make)\s+(.+?)\s+(?:under|to|in)\s+(cluster\s+.+?)[.!]?$', text, re.I)
    if assignment:
        from app.services.ai_cru_tools import _master_record_matches
        target = re.sub(r'^(?:the\s+)?(?:lgu\s+)?', '', assignment.group(1), flags=re.I).strip()
        lgus = [lgu for lgu in _master_record_matches('lgu', target)
                if target.casefold() in (lgu.name.casefold(), (lgu.municipality or '').casefold())]
        clusters = _master_record_matches('cluster', assignment.group(2))
        if lgus:
            if len(lgus) != 1 or len(clusters) != 1:
                return _response('Which LGU and cluster do you mean? Please give their full names.', None, {})
            tool = registry.get_tool('update_lgu')
            if user is None or user.role not in tool.roles:
                return _response('Your role cannot perform that action.', None, {}, clear=True)
            return _response('I will prepare that change for confirmation.', tool,
                             {'lgu_id': lgus[0].id, 'cluster_id': clusters[0].id}, clear=True, ready=True)
    for subject, entity in SUBJECTS:
        command = re.search(rf'\b(create|add|register|update|edit|rename|modify)\s+(?:(?:a|an|the|new)\s+)*{subject}\b', text, re.I)
        if command:
            operation = 'create' if command.group(1).lower() in ('create', 'add', 'register') else 'update'
            name = f'{operation}_{entity}'
            # Project updates use several dedicated actions; keep that existing router.
            if name == 'update_project':
                return None
            break
    if command and re.search(r'\b(?:how|where|what|steps|instructions|(?:can|could)\s+(?:i|we)|is\s+it\s+possible)\b', text[:command.start()], re.I):
        return None
    # A rename may identify the record by its existing official name alone.
    rename = re.match(r'^(?:please\s+)?(?:rename\s+|(?:edit|change|update)\s+(?:the\s+)?name\s+)(.+?)\s+to\s+(.+?)[.!]?$', text, re.I)
    if not command and rename:
        from app.services.ai_cru_tools import _master_record_matches
        matches = [(entity, record) for entity in ('lgu', 'program', 'cluster')
                   for record in _master_record_matches(entity, rename.group(1))]
        if len(matches) == 1:
            entity, record = matches[0]
            tool = registry.get_tool(f'update_{entity}')
            if user is None or user.role not in tool.roles:
                return _response('Your role cannot perform that action.', None, {}, clear=True)
            return _response('I will prepare that change for confirmation.', tool,
                             {f'{entity}_id': record.id, 'name': rename.group(2).strip(' "\'')}, clear=True, ready=True)
        if matches:
            return _response('I found multiple matching records. Which full record name do you mean?', None, {})
    if command:
        try:
            tool = registry.get_tool(name)
        except registry.AiToolError:
            return None
        args = {}
    elif pending:
        tool = registry.get_tool(pending['tool_name'])
        args = dict(pending.get('arguments') or {})
    else:
        return None
    if not command and re.match(r'^(?:please\s+)?(?:show|list|find|get|tell|give|what|which|how|where|can|could|why|is|are)\b', text, re.I):
        return None
    extracted = _fields(text, tool)
    if extracted is None:
        return None  # Complex free-form/invalid JSON remains with the provider.
    if not command and not extracted:
        from app.services.ai_cru_tools import _master_record_matches
        if tool.name == 'create_project':
            from app.models import ProgramCycle
            cycles = ProgramCycle.query.filter_by(program_id=args.get('program_id'), fiscal_year=args.get('fiscal_year'), is_active=True).all()
            cycle_reply = any(value and re.search(rf'(?<!\w){re.escape(value)}(?!\w)', text, re.I)
                              for cycle in cycles for value in (cycle.name, cycle.cycle_code))
            project_reply = (re.fullmatch(r'(?:make it\s+|use\s+)?20\d{2}[.!]?', text, re.I)
                             or re.search(r'\b(?:infrastructure|goods|vehicles?|financial assistance|civil works)\b', text, re.I)
                             or any(_master_record_matches(entity, text) for entity in ('lgu', 'program')) or cycle_reply)
            if not project_reply:
                return None
        elif tool.name in ('create_lgu', 'update_lgu', 'create_program', 'update_program', 'create_cluster', 'update_cluster'):
            missing = [key for key in tool.required_args if args.get(key) in (None, '')]
            official_lgu = re.fullmatch(r'(?:Municipality|City)\s+of\s+(.+)', text, re.I)
            if tool.name == 'create_lgu' and official_lgu and not args.get('name'):
                extracted = {'name': text, 'municipality': official_lgu.group(1)}
            elif len(missing) == 1 and missing[0].endswith('_id'):
                matches = _master_record_matches(missing[0][:-3], text)
                if len(matches) == 1:
                    extracted[missing[0]] = matches[0].id
            elif len(missing) == 1 and missing[0] in ('name', 'province', 'code', 'program_type') and re.fullmatch(r'[\w -]{2,100}', text) and not re.search(r'\b(?:hi|hello|thanks|list|show|what|how|tell|give|help)\b', text, re.I):
                extracted[missing[0]] = text
            if not extracted:
                return None
        else:
            return None
    if user is None or user.role not in tool.roles:
        return _response('Your role cannot perform that action.', None, {}, clear=True)
    args.update(extracted)
    if tool.name == 'create_project':
        from app.services.ai_assistant_service import _plan_create_project
        result = _plan_create_project(text, user, draft=args)
        updates = result.setdefault('context_updates', {})
        clarification = updates.pop('pending_clarification', None)
        updates['pending_action_draft'] = (
            {'tool_name': tool.name, 'arguments': clarification['draft']}
            if clarification else None
        )
        updates['pending_clarification'] = None
        result['heuristic_rule_hit'] = 'action_draft'
        return result
    if tool.name in ('create_lgu', 'update_lgu', 'create_program', 'update_program', 'create_cluster', 'update_cluster'):
        from app.services.ai_cru_tools import _master_record_matches, _extract_master_create_fields, _extract_update_value
        entity = tool.name.split('_', 1)[1]
        id_key = f'{entity}_id'
        if tool.operation_type == 'create':
            for key, value in _extract_master_create_fields(entity, text, tool.allowed_fields).items():
                args.setdefault(key, value)
        else:
            identity = re.split(r'\bto\b', text, maxsplit=1, flags=re.I)[0]
            if not isinstance(args.get(id_key), int):
                matches = _master_record_matches(entity, str(args.get(id_key) or identity))
                if len(matches) == 1:
                    args[id_key] = matches[0].id
                elif len(matches) > 1:
                    choices = ', '.join(record.name for record in matches)
                    return _response(f'I found multiple matching records: {choices}. Which one do you mean?', tool, args)
            field, value = _extract_update_value(text, tool.allowed_fields)
            if field:
                args[field] = value
        if isinstance(args.get('program_type'), str):
            args['program_type'] = args['program_type'].casefold().replace('-', '_').replace(' ', '_')
        for key, target in (('cluster_id', 'cluster'), ('program_id', 'program'), ('lgu_id', 'lgu')):
            if key not in tool.allowed_fields:
                continue
            value = args.get(key)
            if value is None and key == 'cluster_id' and re.search(r'\bcluster\b', text, re.I):
                value = text
            if isinstance(value, str):
                matches = _master_record_matches(target, value)
                if len(matches) == 1:
                    args[key] = matches[0].id
    if tool.name == 'create_lgu' and not args.get('municipality'):
        # A municipality explicitly named in the official name is sufficient.
        municipality = re.fullmatch(r'(?:Municipality|City)\s+of\s+(.+)', str(args.get('name', '')), re.I)
        if municipality:
            args['municipality'] = municipality.group(1)
    missing = [key for key in tool.required_args if args.get(key) in (None, '')]
    unresolved = [key for key, value in args.items() if key.endswith('_id') and isinstance(value, str)]
    missing.extend(key for key in unresolved if key not in missing)
    if tool.operation_type == 'update' and not any(key in args for key in tool.allowed_fields):
        missing.append('fields and values to change')
    if missing:
        friendly = {'lgu_id': 'LGU name', 'program_id': 'program name or code', 'cluster_id': 'cluster name'}
        labels = ', '.join(friendly.get(key, key.replace('_', ' ')) for key in missing)
        return _response(f'Please provide {labels}. I have kept the details already supplied.', tool, args)
    reply = 'I will prepare that change for confirmation.' if tool.requires_confirmation else 'I will create the requested draft record.'
    return _response(reply, tool, args, clear=True, ready=True)


def _response(reply, tool, args, clear=False, ready=False):
    return {
        'assistant_reply': reply,
        'tool_calls': ([{'tool_name': tool.name, 'arguments': args,
                         'reason': 'Explicit record change with supplied details.'}] if ready else []),
        'context_updates': {'pending_action_draft': None if clear or tool is None else {'tool_name': tool.name, 'arguments': args}},
        'ai_provider_used': 'local', 'ai_model_used': 'local:action-draft',
        'provider_called': False, 'heuristic_rule_hit': 'action_draft',
    }


def revise_pending(call, message, user):
    """Labeled corrections replace a review card; they never confirm a write."""
    if not call or not re.match(r'^[\w /\'_-]+\s*[:=]', message.strip()):
        return None
    tool = registry.get_tool(call.tool_name)
    record_names = {f'{op}_{entity}' for _, entity in SUBJECTS for op in ('create', 'update')}
    if tool.name not in record_names or user.role not in tool.roles:
        return None
    first_label = re.split(r'[:=]', message.strip(), maxsplit=1)[0].strip().lower()
    labels = {label for key in set(tool.required_args) | set(tool.allowed_fields)
              for label in (*ALIASES.get(key, (key.replace('_', ' '),)), key)}
    if first_label not in labels:
        return None
    changes = _fields(message, tool)
    if not changes:
        return None
    args = {key: value for key, value in call.input_data.items() if key != 'confirmation_display'}
    args.update(changes)
    result = _response('I will prepare the revised details for confirmation.', tool, args, clear=True, ready=True)
    result['replaces_tool_call_id'] = call.id
    return result
