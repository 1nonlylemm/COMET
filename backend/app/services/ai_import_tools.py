"""Reviewed import mapping and user-bound, expiring preview receipts."""
import hashlib
import json
import re
from functools import partial

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db
from app.models import ImportRow, StoredObject, AiToolCall
from app.services import import_service, batch_import_service
from app.services.import_field_catalog import CANONICAL_FIELDS


TOOL_NAMES = {
    'inspect_import_mapping', 'list_import_templates', 'select_import_template',
    'save_import_mapping_decisions', 'list_import_mapping_history', 'list_import_errors',
}
DECISION_FIELDS = {
    'source_sheet', 'source_column', 'classification', 'canonical_label',
    'target_field', 'suggested_role', 'binding_target', 'binding_config',
    'requirement_metadata', 'value_mapping_rules',
}


def _registry():
    from app.services import ai_tool_registry
    return ai_tool_registry


def _error(message, code=422):
    return _registry().AiToolError(message, code)


def _hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def _signer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='assistant-import-preview-v1')


def _target(args):
    raw = str(args.get('target') or '').strip().lower()
    if raw in ('users', 'user', 'accounts', 'internal users'):
        raise _error('User-account imports must be performed through the Admin Batch Import UI.')
    if args.get('batch_id') or raw in ('workbook', 'workbooks', 'project', 'projects', 'project_workbook'):
        return 'workbook'
    target = batch_import_service.TARGET_ALIASES.get(raw or 'lgus')
    if target not in ('clusters', 'lgus', 'programs'):
        raise _error('Supported import targets are clusters, LGUs, programs and workbooks.')
    return target


def _batch(batch_id, lock=False):
    try:
        return import_service._get_batch(batch_id, for_update=lock)
    except import_service.ImportError as exc:
        raise _error(exc.message, exc.status_code) from exc


def _attachment(attachment_id, user):
    stored = db.session.get(StoredObject, attachment_id)
    if not stored:
        raise _error('Import attachment not found.', 404)
    if stored.uploaded_by is not None and stored.uploaded_by != user.id:
        raise _error('Use an attachment you uploaded.', 403)
    return stored


def preview_snapshot(args, user):
    """No writes: hash the actual proposed content and its target context."""
    target = _target(args)
    if target == 'workbook':
        batch = _batch(args.get('batch_id'))
        if batch.status != 'previewed':
            raise _error('Generate and review a new workbook preview before committing.', 409)
        try:
            fingerprint = import_service.workbook_preview_fingerprint(batch)
        except import_service.ImportError as exc:
            raise _error(exc.message, exc.status_code) from exc
        return {'target': target, 'batch_id': batch.id, 'fingerprint': fingerprint}
    stored = _attachment(args.get('attachment_id'), user)
    if args.get('file_hash') and args['file_hash'] != stored.sha256_hash:
        raise _error('The uploaded file has changed since the preview was generated. Please run a new preview before committing.')
    upload = _registry()._get_upload_from_stored_object(stored)
    actual_hash = hashlib.sha256(upload.stream.read()).hexdigest()
    upload.stream.seek(0)
    if stored.sha256_hash != actual_hash:
        raise _error('The source file has changed since the preview. Upload and preview again.')
    try:
        result = batch_import_service.process_upload(target, upload, user.id, dry_run=True)
    except batch_import_service.BatchImportError as exc:
        raise _error(exc.message, exc.status_code) from exc
    return {'target': target, 'attachment_id': stored.id,
            'fingerprint': _hash({'source_hash': actual_hash, 'preview': result})}


def issue_receipt(args, user):
    snapshot = preview_snapshot(args, user)
    return {'preview_fingerprint': snapshot['fingerprint'],
            'preview_token': _signer().dumps({**snapshot, 'user_id': user.id}),
            'preview_expires_in_seconds': 3600}


def validate_receipt(args, user):
    # Evaluate the snapshot before the receipt so legacy invalid-target/file
    # errors remain specific. This operation never creates records.
    snapshot = preview_snapshot(args, user)
    token = args.get('preview_token')
    if not token:
        raise _error('Preview this import before committing. The reviewed preview receipt is required.')
    try:
        signed = _signer().loads(token, max_age=3600)
    except (BadSignature, SignatureExpired, TypeError) as exc:
        raise _error('The preview receipt is invalid or expired. Generate and review a new preview.', 409) from exc
    if signed.get('user_id') != user.id:
        raise _error('This import preview belongs to another user.', 403)
    if {key: signed.get(key) for key in snapshot} != snapshot:
        raise _error('The import changed after preview. Generate and review a new preview before committing.', 409)
    if args.get('preview_fingerprint') and args['preview_fingerprint'] != snapshot['fingerprint']:
        raise _error('The import preview fingerprint does not match. Preview again.', 409)
    args['preview_fingerprint'] = snapshot['fingerprint']
    args['target'] = snapshot['target']
    return snapshot


def prepare_import(tool, args, user):
    permitted = {'target', 'attachment_id', 'batch_id', 'file_hash', 'confirmation_display', 'reason'}
    if tool.name == 'preview_import':
        permitted.update(('program_id', 'program_cycle_id', 'import_template_id'))
    else:
        permitted.update(('preview_token', 'preview_fingerprint', 'confirm_similar_requirements'))
    if set(args) - permitted:
        raise _error('Unsupported import arguments.')
    for key in ('attachment_id', 'batch_id', 'program_id', 'program_cycle_id', 'import_template_id'):
        if args.get(key) is not None:
            if isinstance(args[key], bool) or not re.fullmatch(r'[1-9]\d*', str(args[key])):
                raise _error(f'{key} must be a positive integer.')
            args[key] = int(args[key])
    _target(args)
    if 'confirm_similar_requirements' in args and not isinstance(args['confirm_similar_requirements'], bool):
        raise _error('confirm_similar_requirements must be a boolean.')
    if args.get('attachment_id'):
        _attachment(args['attachment_id'], user)
    if tool.name == 'commit_import':
        validate_receipt(args, user)
        # Do not accept a model-supplied confirmation display.
        args.pop('confirmation_display', None)
    elif args.get('batch_id'):
        batch = _batch(args['batch_id'])
        if args.get('attachment_id') and args['attachment_id'] != batch.stored_object_id:
            raise _error('The attachment does not belong to this staged workbook.')
        if args.get('import_template_id') and args['import_template_id'] != batch.import_template_id:
            raise _error('Select and confirm the new template before previewing this staged batch.')


def hydrate_receipt(arguments, conversation_id):
    """Only reuse a completed preview from this conversation, never guess one."""
    args = dict(arguments)
    if args.get('preview_token'):
        return args
    calls = AiToolCall.query.filter_by(conversation_id=conversation_id, status='completed').filter(
        AiToolCall.tool_name.in_(('preview_import', 'select_import_template', 'save_import_mapping_decisions'))
    ).order_by(AiToolCall.id.desc()).limit(30).all()
    for call in calls:
        detail = (call.output_data or {}).get('detail') or {}
        if not detail.get('preview_token'):
            continue
        target = detail.get('target')
        if args.get('batch_id') and args['batch_id'] != detail.get('batch_id'):
            continue
        if args.get('attachment_id') and target != 'workbook' and args['attachment_id'] != detail.get('attachment_id'):
            continue
        if args.get('target') and not args.get('batch_id') and _target(args) != target:
            continue
        for key in ('target', 'batch_id', 'attachment_id', 'file_hash', 'preview_token', 'preview_fingerprint'):
            if detail.get(key) is not None:
                args[key] = detail[key]
        return args
    return args


def _decisions(batch, decisions):
    if not isinstance(decisions, list) or not decisions or len(decisions) > 200:
        raise _error('Provide between 1 and 200 column decisions.')
    sources = {(item.get('source_sheet'), item.get('source_column'))
               for item in (batch.mapping_preview or {}).get('field_mappings') or []}
    seen = set()
    for decision in decisions:
        if not isinstance(decision, dict) or set(decision) - DECISION_FIELDS:
            raise _error('Each column decision must contain only supported mapping fields.')
        if not all(isinstance(decision.get(field), str) for field in ('source_sheet', 'source_column', 'classification')):
            raise _error('Source sheet, column and classification must be text.')
        key = (decision.get('source_sheet'), decision.get('source_column'))
        if key not in sources or key in seen:
            raise _error('Use an existing source sheet/column exactly once per decision request.')
        seen.add(key)
        if decision.get('classification') not in import_service.MAPPING_CLASSIFICATIONS:
            raise _error('Choose a supported column classification.')
        if decision.get('target_field') is not None and (not isinstance(decision['target_field'], str) or decision['target_field'] not in CANONICAL_FIELDS):
            raise _error('Choose a supported canonical target field.')
        if 'canonical_label' in decision and not isinstance(decision['canonical_label'], str):
            raise _error('The column label must be text.')
        for field in ('binding_config', 'requirement_metadata', 'value_mapping_rules'):
            if field in decision and not isinstance(decision[field], dict):
                raise _error(f'{field} must be an object.')
        # Evidence approval is never a side effect of conversational mapping.
        rules = decision.get('value_mapping_rules') or {}
        if rules and rules.get('mode') not in (None, 'source_reported_under_review'):
            raise _error('Requirement values may be imported for review, not automatically approved.')


def prepare(tool, args, user):
    if user.role != 'admin':
        raise _error('Only administrators can manage imports.', 403)
    permitted = set(tool.required_args) | set(tool.allowed_fields) | {'confirmation_display', 'reason'}
    if set(args) - permitted:
        raise _error('Unsupported import mapping arguments.')
    for key in ('batch_id', 'template_id', 'program_id', 'program_cycle_id', 'page', 'per_page', 'limit', 'fiscal_year'):
        if args.get(key) is not None:
            if isinstance(args[key], bool) or not re.fullmatch(r'[1-9]\d*', str(args[key])):
                raise _error(f'{key} must be a positive integer.')
            args[key] = int(args[key])
    if args.get('per_page', 10) > 50 or args.get('limit', 100) > 100:
        raise _error('Use at most 50 results per page or 100 history entries.')
    if not args.get('batch_id'):
        return
    batch = _batch(args['batch_id'])
    if tool.name in ('select_import_template', 'save_import_mapping_decisions'):
        try:
            import_service._ensure_batch_not_committed(batch)
        except import_service.ImportError as exc:
            raise _error(exc.message, exc.status_code) from exc
        fingerprint = _hash({'mapping': batch.mapping_preview, 'template_id': batch.import_template_id,
                             'file_hash': batch.file_hash, 'profile': batch.workbook_profile})
        if args.get('mapping_fingerprint') and args['mapping_fingerprint'] != fingerprint:
            raise _error('The mapping changed while awaiting confirmation. Review the mapping and try again.', 409)
        args['mapping_fingerprint'] = fingerprint
        if tool.name == 'save_import_mapping_decisions':
            _decisions(batch, args['decisions'])
        else:
            try:
                template = import_service._get_template(batch.program_id, args['template_id'], batch.program_cycle_id)
            except import_service.ImportError as exc:
                raise _error(exc.message, exc.status_code) from exc
            if not template.is_active or template.status not in ('draft', 'active') or template.file_type != batch.file_type or template.program_cycle_id not in (None, batch.program_cycle_id):
                raise _error('Choose a compatible active or draft template for this program and cycle.')
            template_fp = _hash(import_service._serialize_template(template))
            if args.get('template_fingerprint') and args['template_fingerprint'] != template_fp:
                raise _error('The selected template changed. Review it and try again.', 409)
            args['template_fingerprint'] = template_fp
        args['confirmation_display'] = {
            'batch_id': batch.id, 'source_file': batch.original_file_name,
            'template_id': args.get('template_id'), 'decisions': args.get('decisions'),
            'notice': 'Confirm the mapping change. A fresh import preview will be generated; operational records are saved only after a separate import confirmation.',
        }


def _execute(name, args, user):
    registry = _registry()
    try:
        page, size = args.get('page', 1), args.get('per_page', 10)
        if name == 'inspect_import_mapping':
            result = import_service.get_mapping_workshop(args['batch_id'])
            fields = result.pop('field_mappings')
            decisions = result.pop('decisions')
            result.update(field_mappings=fields[(page-1)*size:page*size],
                          decisions=decisions[(page-1)*size:page*size], total_columns=len(fields), page=page, per_page=size)
        elif name == 'list_import_templates':
            items = import_service.list_import_templates(**{key: args[key] for key in ('program_id', 'program_cycle_id', 'fiscal_year') if key in args})
            if args.get('batch_id'):
                batch = _batch(args['batch_id'])
                items = [item for item in items if item['program_id'] == batch.program_id and item['program_cycle_id'] in (None, batch.program_cycle_id) and item['file_type'] == batch.file_type]
            result = {'templates': items[(page-1)*size:page*size], 'total': len(items), 'page': page}
        elif name == 'list_import_mapping_history':
            result = {'decisions': import_service.list_mapping_history(**{key: args[key] for key in ('program_id', 'program_cycle_id', 'source_header', 'limit') if key in args})}
        elif name == 'list_import_errors':
            batch = _batch(args['batch_id'])
            if batch.status != 'previewed':
                raise _error('Generate a fresh preview to inspect current validation errors.', 409)
            rows = ImportRow.query.filter_by(import_batch_id=batch.id, action='error').order_by(ImportRow.sheet_name, ImportRow.row_number).paginate(page=page, per_page=size, error_out=False)
            result = {'batch_id': batch.id, 'rows': [import_service._serialize_import_row(row) for row in rows.items],
                      'total_errors': rows.total, 'page': page, 'requirement_warnings': (batch.preview_summary or {}).get('requirements', {}).get('review_items') or []}
        else:
            # Lock and recheck again before any mapping write.
            _batch(args['batch_id'], lock=True)
            prepare(registry.get_tool(name), args, user)
            if name == 'select_import_template':
                import_service.select_import_template(args['batch_id'], args['template_id'], user_id=user.id)
            else:
                import_service.save_mapping_decisions(args['batch_id'], args['decisions'], user_id=user.id)
            # Return the same receipt-bearing format as normal preview_import,
            # so a subsequent commit always refers to the newly reviewed rows.
            try:
                return registry._tool_preview_import({'batch_id': args['batch_id'], 'target': 'workbook'}, user)
            except registry.AiToolError as exc:
                return registry._detail_result('Mapping saved; preview needs attention', {
                    'batch_id': args['batch_id'], 'mapping_saved': True, 'preview_required': True,
                    'preview_error': exc.message,
                }, summary='The mapping was saved, but preview failed. Review the error and preview again before committing.')
        return registry._detail_result(registry.get_user_facing_tool_label(name), result)
    except import_service.ImportError as exc:
        db.session.rollback()
        raise _error(exc.message, exc.status_code) from exc


def build_tools(definition):
    specs = {
        'inspect_import_mapping': (('batch_id',), ('page', 'per_page'), 'read', 'Inspect workbook columns, classifications, targets and mapping suggestions.'),
        'list_import_templates': ((), ('program_id', 'program_cycle_id', 'fiscal_year', 'batch_id', 'page', 'per_page'), 'read', 'List reusable import templates, optionally compatible with a staged batch.'),
        'list_import_mapping_history': (('program_id',), ('program_cycle_id', 'source_header', 'limit'), 'read', 'Find previously reviewed column mappings for reuse.'),
        'list_import_errors': (('batch_id',), ('page', 'per_page'), 'read', 'Inspect current invalid workbook rows and similar-requirement warnings.'),
        'select_import_template': (('batch_id', 'template_id'), ('mapping_fingerprint', 'template_fingerprint'), 'update', 'Apply an existing compatible template after confirmation, then generate a fresh preview.'),
        'save_import_mapping_decisions': (('batch_id', 'decisions'), ('mapping_fingerprint',), 'update', 'Confirm column decisions: source_sheet, source_column, classification, canonical_label, target_field, optional requirement_metadata. Then regenerate preview. Values remain subject to documentary review.'),
    }
    return {name: definition(name=name, description=description, roles=('admin',), required_args=required,
                            allowed_fields=fields, risk_level='medium' if operation == 'update' else 'low',
                            requires_confirmation=operation == 'update', operation_type=operation,
                            canonical_service='import_service', scope_type='province', display_type='detail',
                            executor=partial(_execute, name))
            for name, (required, fields, operation, description) in specs.items()}


def heuristic_plan(conversation, message, user):
    """Route explicit import review commands, preserving ordinary entity CRU."""
    context = getattr(conversation, 'context', None) or {}
    pending = context.get('pending_import_draft') or {}
    if pending and message.strip().lower().rstrip('.!') in ('cancel', 'never mind', 'stop'):
        return {'assistant_reply': 'Cancelled the import draft.', 'tool_calls': [],
                'context_updates': {'pending_import_draft': None},
                'ai_provider_used': 'local', 'heuristic_rule_hit': 'import_command'}
    # Resume a requested program selection or attachment without losing the target.
    answering = pending and (
        re.fullmatch(r'\s*program\s*(?:id\s*|#|:)?\s*[1-9]\d*\s*[.!]?\s*', message, re.I)
        or re.fullmatch(r'\s*(?:here(?:\s+it\s+is)?|attached|use\s+this\s+file)\s*[.!]?\s*', message, re.I)
    )
    if answering:
        message = f"Preview {pending['target']} import " + message
    from app.services import ai_program_setup_tools
    setup_plan = ai_program_setup_tools.heuristic_plan(message, user)
    if setup_plan:
        return setup_plan
    text = message.lower()
    if re.search(r'\b(delete|remove|purge|drop|truncate|archive|approve|waive|dispatch)\b', text):
        return None
    # Resolve explicit import commands before project context can turn them into
    # an overview of a previously mentioned project.
    if ((re.search(r'\b(?:preview|inspect|review|validate|commit|finalize|save)\b', text)
         or re.match(r'^(?:please\s+|i\s+(?:want|need)\s+to\s+)?import\b', text))
            and re.search(r'\b(?:import|workbooks?|batch)\b', text)
            and not re.search(r'\b(?:mapping|mappings|columns?|errors?|history|templates?)\b', text)):
        plan = {'assistant_reply': 'I will prepare the import.', 'tool_calls': [],
                'ai_provider_used': 'local', 'ai_model_used': 'local:import-review',
                'heuristic_rule_hit': 'import_command'}
        if not user or user.role != 'admin':
            plan['assistant_reply'] = 'Only administrators can preview and commit imports.'
            return plan
        if re.search(r'\b(?:users?|accounts?)\b', text):
            plan['assistant_reply'] = 'Batch import of user accounts involves sensitive authorization controls and must be performed directly through the Admin Batch Import UI.'
            return plan
        committing = bool(re.search(r'\b(?:commit|finalize|save)\b', text))
        target = next((value for pattern, value in (
            (r'\b(?:workbooks?|projects?)\b', 'workbook'),
            (r'\bclusters?\b', 'clusters'), (r'\blgus?\b', 'lgus'),
            (r'\bprograms?\b(?!\s*(?:#|id)\s*\d)', 'programs'))
            if re.search(pattern, text)), None)
        args = {'target': target if committing else target or 'lgus'}
        if answering:
            args.update(pending)
        batch = re.search(r'\bbatch\s*(?:#|id\s*)?\s*([1-9]\d*)\b', text)
        if batch:
            args['batch_id'] = int(batch.group(1))
        if conversation:
            from app.models import AiMessage
            attachment = AiMessage.query.filter_by(conversation_id=conversation.id).filter(
                AiMessage.attachment_stored_object_id.isnot(None)).order_by(AiMessage.id.desc()).first()
            if attachment:
                args['attachment_id'] = attachment.attachment_stored_object_id
        if not committing and args['target'] == 'workbook' and not batch:
            program = re.search(r'\bprogram\s*(?:#|id\s*)?\s*([1-9]\d*)\b', text)
            if program:
                args['program_id'] = int(program.group(1))
            if not args.get('program_id'):
                plan['assistant_reply'] = 'Which program should this workbook be imported into? Please provide the program ID.'
                plan['context_updates'] = {'pending_import_draft': args}
                return plan
        if not committing and not args.get('batch_id') and not args.get('attachment_id'):
            plan['assistant_reply'] = 'Please attach a CSV or XLSX file to preview the import.'
            plan['context_updates'] = {'pending_import_draft': args}
            return plan
        plan['tool_calls'] = [{'tool_name': 'commit_import' if committing else 'preview_import',
                               'arguments': args, 'reason': 'Explicit import command.'}]
        plan['context_updates'] = {'pending_import_draft': None}
        return plan
    name = None
    if re.search(r'\b(?:mapping|column)\s+history\b', text):
        name = 'list_import_mapping_history'
    elif re.search(r'\b(?:list|show|find|available)\b.*\b(?:import|workbook) templates?\b', text):
        name = 'list_import_templates'
    elif re.search(r'\b(?:select|use|apply)\b.*\btemplate\b', text) and re.search(r'\b(?:import|workbook|batch)\b', text):
        name = 'select_import_template'
    elif re.search(r'\b(?:save|change|update|correct|map|ignore|rename)\b', text) and re.search(r'\b(?:mapping|column|columns)\b', text):
        name = 'save_import_mapping_decisions'
    elif re.search(r'\b(?:show|inspect|review|list)\b.*\b(?:mapping|mappings|columns)\b', text) and re.search(r'\b(?:import|workbook|batch)\b', text):
        name = 'inspect_import_mapping'
    elif re.search(r'\b(?:show|inspect|list|review)\b.*\b(?:errors|invalid rows|validation errors)\b', text) and re.search(r'\b(?:import|workbook|batch)\b', text):
        name = 'list_import_errors'
    if not name:
        return None
    plan = {'assistant_reply': 'I will inspect the import review details.', 'tool_calls': [],
            'ai_provider_used': 'local', 'ai_model_used': 'local:import-review',
            'heuristic_rule_hit': 'import_review'}
    if not user or user.role != 'admin':
        plan['assistant_reply'] = 'Only administrators can review and manage imports.'
        return plan
    args = {}
    for key, label in (('batch_id', 'batch'), ('template_id', 'template'), ('program_id', 'program'), ('program_cycle_id', 'cycle')):
        found = re.search(rf'\b{label}\s*(?:#|id\s*|:\s*)?\s*([1-9]\d*)\b', text)
        if found:
            args[key] = int(found.group(1))
    if conversation and 'batch_id' not in args and name != 'list_import_mapping_history':
        recent = AiToolCall.query.filter_by(conversation_id=conversation.id, status='completed').order_by(AiToolCall.id.desc()).limit(20).all()
        for call in recent:
            if call.tool_name not in TOOL_NAMES | {'preview_import'}:
                continue
            batch_id = ((call.output_data or {}).get('detail') or {}).get('batch_id')
            if batch_id:
                args['batch_id'] = batch_id
                break
    if '{' in message:
        try:
            payload = json.loads(message[message.index('{'):])
            if not isinstance(payload, dict):
                return None
            args.update(payload)
        except ValueError:
            return None
    if name == 'save_import_mapping_decisions' and 'decisions' not in args:
        column = re.search(r'\bcolumn\s+["\']?([A-Z]{1,3})["\']?\b', message, re.I)
        sheet = re.search(r'\bsheet\s+["\']([^"\']+)["\']', message, re.I)
        target = re.search(r'\bto\s+["\']?((?:project|lgu|program_cycle)\.[a-z_]+)', text)
        if column and sheet and (target or re.search(r'\bignore\b', text)):
            decision = {'source_sheet': sheet.group(1), 'source_column': column.group(1).upper()}
            if target:
                field = target.group(1)
                decision.update(target_field=field, classification={'project': 'project_field', 'lgu': 'lgu_field', 'program_cycle': 'cycle_field'}[field.split('.')[0]])
            else:
                decision['classification'] = 'ignored'
            args['decisions'] = [decision]
    tool = _registry().get_tool(name)
    allowed = set(tool.required_args) | set(tool.allowed_fields)
    # Drop inferred program context when a batch action does not accept it.
    args = {key: value for key, value in args.items() if key in allowed or ('payload' in locals() and key in payload)}
    missing = [key.replace('_', ' ') for key in tool.required_args if key not in args]
    if missing:
        plan['assistant_reply'] = 'Please provide ' + ', '.join(missing) + ' for the import review.'
        return plan
    plan['assistant_reply'] = 'I will prepare the mapping change for confirmation.' if tool.requires_confirmation else 'I will inspect the import review details.'
    plan['tool_calls'] = [{'tool_name': name, 'arguments': args, 'reason': 'Explicit import review request.'}]
    return plan
