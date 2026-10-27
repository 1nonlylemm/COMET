"""Confirmed ordinary metadata operations; formal workflow transitions stay in UI."""
import hashlib
import json
import math
import re
from functools import partial

from app.extensions import db
from app.models import (CompletionDocumentRecord, ManagementActionReport, SubaybayanVerification, Program,
                        EscalationNotice, ProgramGuideline, Project, ProjectRequirement, SystemConfig)
from app.services import (
    access_service, completion_documents_service as completion, governance_service as governance,
    library_service as library, monitoring_service as monitoring, notice_service as notice,
    escalation_service as escalation,
)

OPERATIONAL = ('admin', 'staff', 'field_officer')
EDITORS = ('admin', 'staff')
GUIDELINE_FIELDS = ('program_id', 'title', 'guideline_type', 'reference_number', 'issuing_body',
                    'effective_date', 'is_current', 'description', 'file_path', 'file_name')
REFERENCE_FIELDS = tuple(f for f in GUIDELINE_FIELDS if f != 'guideline_type') + ('reference_type',)
TEMPLATE_FIELDS = ('label', 'is_default', 'placeholder_defaults')
SUBAY_FIELDS = ('lgu_encoded_status', 'lgu_encoded_at', 'cmlgoo_verified_at', 'po_validated_at',
                'ro_action_status', 'ro_action_at', 'discrepancy_notes', 'observations', 'evidence_links', 'status')
MAR_FIELDS = ('risk_level', 'trigger_source', 'trigger_summary', 'action_required',
              'responsible_office', 'due_date', 'inspection_id', 'verification_id')
TOOL_NAMES = set()
ERRORS = (access_service.AccessError, completion.CompletionDocumentError, governance.GovernanceError,
          library.LibraryError, monitoring.MonitoringError, notice.NoticeError, escalation.EscalationError)


def _registry():
    from app.services import ai_tool_registry
    return ai_tool_registry


def _error(message, code=422):
    return _registry().AiToolError(message, code)


def _data(tool, args):
    return {k: args[k] for k in set(tool.required_args) | set(tool.allowed_fields)
            if k in args and k != 'expected_revision'}


def _revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _project(project_id, user, write=False):
    project = access_service.ensure_project_access(project_id, user.id)
    if write:
        access_service.assert_project_movement_allowed(project)
    return project


def _before(name, args, user):
    if 'notice_id' in args:
        return notice._serialize_notice_snapshot(notice._get_notice_with_access(args['notice_id'], user_id=user.id))
    if 'guideline_id' in args:
        return governance._serialize_guideline(governance.get_guideline(args['guideline_id']))
    if 'reference_uri' in args:
        return library.get_reference(args['reference_uri'], user_id=user.id, user_role=user.role)
    if name == 'upsert_subaybayan_verification':
        item = SubaybayanVerification.query.filter_by(
            project_id=args['project_id'], cycle_month=args['cycle_month']).first()
        return monitoring._serialize_subaybayan_verification(item) if item else None
    if 'action_id' in args:
        item = db.session.get(ManagementActionReport, args['action_id'])
        if not item:
            raise _error('Management Action Report not found.', 404)
        if item.project_id:
            _project(item.project_id, user, True)
        elif user.role != 'admin':
            raise _error('Province-wide drafts require an administrator.', 403)
        return monitoring._serialize_management_action(item)
    if 'document_type' in args:
        return completion.get_completion_document(args['project_id'], args['document_type'], user_id=user.id, initialize=False)
    return None


def _validate_payload(name, data, args, user, before):
    from app.api.escalation.schemas import validate_notice_update, validate_notice_receipt
    from app.api.governance.schemas import validate_guideline_payload
    from app.api.library.schemas import validate_reference_payload, validate_template_payload
    errors = None
    if name == 'update_notice_draft':
        errors = validate_notice_update({k: v for k, v in data.items() if k != 'notice_id'})
        if before['status'] != 'draft' or before.get('sent_at'):
            raise _error('Only unreleased draft notices can be edited through the assistant.', 409)
    elif name == 'record_notice_receipt':
        errors = validate_notice_receipt(data)
        if not before.get('sent_at'):
            raise _error('Release the notice in the Escalation workspace before recording receipt.', 409)
        received = notice._parse_optional_datetime(data['acknowledged_at'])
        if received < notice._to_aware_datetime(notice._get_notice_with_access(args['notice_id'], user.id).sent_at):
            raise _error('Receipt timestamp cannot be earlier than the release timestamp.')
    elif name in ('create_guideline', 'update_guideline'):
        errors = validate_guideline_payload(data, partial=name.startswith('update_'))
    elif name in ('create_library_reference', 'update_library_reference'):
        if 'reference_uri' in args and library.decode_reference_uri(args['reference_uri'])['origin'] == 'template':
            if user.role != 'admin':
                raise _error('Only administrators can edit template metadata.', 403)
            extra = set(data) - set(TEMPLATE_FIELDS) - {'reference_uri'}
            if extra:
                raise _error('Template edits support only label, is_default and placeholder_defaults.')
            if data.get('is_default') is False and before.get('is_default'):
                from app.services import settings_service
                decoded = library.decode_reference_uri(args['reference_uri'])
                group = next(g for g in settings_service.list_document_templates()
                             if g['template_type'] == decoded['template_subtype'])
                if len(group['templates']) <= 1:
                    raise _error('Add another template before removing the sole template default in the Library workspace.')
            errors = validate_template_payload(data, partial=True)
        else:
            if data.get('reference_type') == 'template' or set(data) & set(TEMPLATE_FIELDS):
                raise _error('Template creation requires a file upload in the Library workspace.')
            errors = validate_reference_payload(data, partial=name.startswith('update_'))
    elif name == 'update_completion_document_metadata':
        if args['document_type'] != 'proof_of_return_of_funds':
            raise _error('Only Proof of Return of Funds has editable amount and receipt metadata.')
        if before.get('workflow_status') not in (None, 'draft', 'returned_for_revision'):
            raise _error('Submitted or approved documents must use the review workflow before editing.', 409)
        if 'returned_amount' in data and data['returned_amount'] is not None:
            value = data['returned_amount']
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise _error('returned_amount must be a finite, nonnegative number.')
            project = _project(args['project_id'], user, True)
            if project.budget_amount and value > float(project.budget_amount):
                raise _error('Returned amount cannot exceed the project budget.')
    elif name == 'upsert_subaybayan_verification':
        monitoring._validate_cycle_month(args['cycle_month'])
        # Validate against the service on a transient object, never on the stored record.
        monitoring._apply_subaybayan_verification_fields(SubaybayanVerification(), data, user.id)
        if 'evidence_links' in data and (not isinstance(data['evidence_links'], list) or
                not all(isinstance(link, str) for link in data['evidence_links'])):
            raise _error('evidence_links must be a list of strings.')
    elif name in ('create_management_action_draft', 'update_management_action_draft'):
        if before and before['status'] != 'draft':
            raise _error('Only draft management actions can be edited conversationally.', 409)
        target = args.get('project_id') or (before or {}).get('project_id')
        for field, model in (('inspection_id', monitoring.QaarInspection), ('verification_id', SubaybayanVerification)):
            if data.get(field):
                item = db.session.get(model, data[field])
                if not item or item.project_id != target:
                    raise _error(f'{field} must belong to the draft project.')
                _project(item.project_id, user)
        transient = ManagementActionReport(project_id=target)
        monitoring._apply_management_action_fields(transient, data, user.id)
    if errors:
        raise _error('; '.join(f'{k}: {v}' for k, v in errors.items()))


def prepare(tool, args, user):
    permitted = set(tool.required_args) | set(tool.allowed_fields)
    if tool.name.startswith('list_'):
        permitted.update(('page', 'per_page'))
    extra = set(args) - permitted - {'confirmation_display', 'reason', 'expected_revision'}
    if extra:
        raise _error('Unsupported fields: ' + ', '.join(sorted(extra)) + '.')
    for key in permitted:
        if key.endswith('_id') and args.get(key) is not None:
            if isinstance(args[key], bool) or not re.fullmatch(r'[1-9]\d*', str(args[key])):
                raise _error(f'{key} must be a positive integer.')
            args[key] = int(args[key])
    for key in ('page', 'per_page') if tool.name.startswith('list_') else ():
        value = args.get(key, 1 if key == 'page' else 10)
        if isinstance(value, bool) or not re.fullmatch(r'[1-9]\d*', str(value)):
            raise _error(f'{key} must be a positive integer.')
        args[key] = min(int(value), 20) if key == 'per_page' else int(value)
    for key in ('is_current', 'is_default'):
        if key in args and not isinstance(args[key], bool):
            raise _error(f'{key} must be a boolean.')
    # Strings stay strings; canonical validators assume text for these metadata fields.
    non_text = {'project_id', 'program_id', 'guideline_id', 'notice_id', 'action_id', 'inspection_id',
                'verification_id', 'is_current', 'is_default', 'returned_amount', 'placeholder_defaults', 'evidence_links'}
    for key in set(args) & permitted - non_text - {'page', 'per_page'}:
        if args[key] is not None and not isinstance(args[key], str):
            raise _error(f'{key} must be text.')
    data = _data(tool, args)
    if tool.operation_type == 'update' and not any(k in args for k in tool.allowed_fields if k != 'expected_revision'):
        raise _error('Provide at least one field to update.')
    try:
        if args.get('program_id') and not db.session.get(Program, args['program_id']):
            raise _error('Program not found.', 404)
        if args.get('project_id'):
            _project(args['project_id'], user, tool.requires_confirmation)
        before = _before(tool.name, args, user)
        if before and before.get('project_id') and tool.requires_confirmation:
            _project(before['project_id'], user, True)
        if tool.requires_confirmation:
            _validate_payload(tool.name, data, args, user, before)
            revision = _revision(before)
            if args.get('expected_revision') and args['expected_revision'] != revision:
                raise _error('This record changed after review. Prepare a new action before confirming.', 409)
            args['expected_revision'] = revision
            changes = {k: {'from': (before or {}).get('template_label' if k == 'label' else k), 'to': args[k]}
                       for k in tool.allowed_fields if k in args and k != 'expected_revision'}
            args['confirmation_display'] = {
                'action': tool.name.replace('_', ' ').capitalize(), 'before': before, 'changes': changes,
                'target': {k: args[k] for k in tool.required_args},
                'notice': 'Confirm to save metadata. Formal review and release actions remain in their workspaces.',
            }
    except ERRORS as exc:
        raise _error(exc.message, exc.status_code) from exc


def _execute(name, args, user):
    registry = _registry()
    tool = registry.get_tool(name)
    try:
        if tool.requires_confirmation:
            _lock_target(args)
        # Revalidate pending state and scope immediately before service execution.
        prepare(tool, args, user)
        data = _data(tool, args)
        title = name.replace('_', ' ').capitalize()
        rows = None
        total = None
        if name == 'get_notice':
            result = _before(name, args, user)
        elif name in ('update_notice_draft', 'record_notice_receipt'):
            method = notice.update_notice if name == 'update_notice_draft' else notice.record_notice_receipt
            method(args['notice_id'], data, user_id=user.id)
            result = _before(name, args, user)
        elif name in ('get_guideline', 'create_guideline', 'update_guideline'):
            item = (governance.get_guideline(args['guideline_id']) if name == 'get_guideline' else
                    governance.create_guideline(data, user.id) if name == 'create_guideline' else
                    governance.update_guideline(args['guideline_id'], data, user.id))
            result = governance._serialize_guideline(item)
        elif name == 'list_library_references':
            result = library.list_references(**data, user_id=user.id, user_role=user.role,
                                             page=args['page'], per_page=args['per_page'])
            rows, total = result['items'], result['total']
        elif name == 'get_library_reference':
            result = library.get_reference(args['reference_uri'], user_id=user.id, user_role=user.role)
        elif name == 'create_library_reference':
            result = library.create_reference(data, user_id=user.id, user_role=user.role)
        elif name == 'update_library_reference':
            data.pop('reference_uri')
            result = library.update_reference(args['reference_uri'], data, user_id=user.id, user_role=user.role)
        elif name == 'list_completion_documents':
            rows = completion.list_completion_documents(args['project_id'], user_id=user.id, initialize=False)
        elif name == 'get_completion_document':
            result = completion.get_completion_document(args['project_id'], args['document_type'], user_id=user.id, initialize=False)
        elif name == 'update_completion_document_metadata':
            result = completion.update_document_metadata(args['project_id'], args['document_type'], data, user.id)
        elif name in ('list_subaybayan_verifications', 'list_management_actions'):
            method = monitoring.list_subaybayan_verifications if name.startswith('list_subay') else monitoring.list_management_actions
            rows = method(**data, user_id=user.id)
        elif name == 'upsert_subaybayan_verification':
            item = monitoring.upsert_subaybayan_verification(data, user_id=user.id)
            result = monitoring._serialize_subaybayan_verification(item)
        else:
            if name == 'update_management_action_draft':
                data['id'] = data.pop('action_id')
            else:
                data['status'] = 'draft'
            item = monitoring.upsert_management_action(data, user_id=user.id)
            result = monitoring._serialize_management_action(item)
        if rows is not None:
            result = _table(title, rows, args, total)
            if name == 'list_completion_documents' and not rows:
                result['summary'] = 'No initialized completion documents. Open the Completion workspace to initialize the matrix.'
            return result
        return registry._detail_result(title, result)
    except _registry().AiToolError:
        db.session.rollback()
        raise
    except ERRORS as exc:
        db.session.rollback()
        raise _error(exc.message, exc.status_code) from exc
    except Exception:
        db.session.rollback()
        raise


def _lock_target(args):
    """Serialize assistant writes, and refresh state before comparing the reviewed revision."""
    project_id = args.get('project_id')
    for key, model in (('notice_id', EscalationNotice), ('guideline_id', ProgramGuideline),
                       ('action_id', ManagementActionReport)):
        if args.get(key):
            item = model.query.filter_by(id=args[key]).populate_existing().with_for_update().first()
            project_id = getattr(item, 'project_id', None) or project_id
    if args.get('reference_uri'):
        decoded = library.decode_reference_uri(args['reference_uri'])
        if decoded['origin'] == 'guideline':
            ProgramGuideline.query.filter_by(id=decoded['guideline_id']).populate_existing().with_for_update().first()
        else:
            # Templates share a JSON catalog. Lock configuration before reading it.
            from app.services import settings_service
            prefix = settings_service.DOCUMENT_TEMPLATE_TYPES[decoded['template_subtype']]['config_prefix']
            SystemConfig.query.filter(SystemConfig.key.startswith(prefix + '_')).populate_existing().with_for_update().all()
    if project_id:
        Project.query.filter_by(id=project_id).populate_existing().with_for_update().first()
        if args.get('cycle_month'):
            SubaybayanVerification.query.filter_by(project_id=project_id, cycle_month=args['cycle_month']).populate_existing().with_for_update().all()
        if args.get('document_type'):
            record = CompletionDocumentRecord.query.filter_by(project_id=project_id, document_type=args['document_type']).populate_existing().with_for_update().first()
            if record:
                ProjectRequirement.query.filter_by(id=record.project_requirement_id).populate_existing().with_for_update().first()


def _table(title, rows, args, total=None):
    page, size = args['page'], args['per_page']
    if total is None:
        total = len(rows)
        rows = rows[(page - 1) * size:page * size]
    keys = ('id', 'reference_uri', 'title', 'project_id', 'document_label', 'cycle_month', 'status')
    columns = [{'key': k, 'label': k.replace('_', ' ').title()} for k in keys if any(k in row for row in rows)]
    return _registry()._table_result(title, rows, columns,
        meta={'page': page, 'per_page': size, 'total': total, 'pages': (total + size - 1) // size})


def build_tools(definition):
    tools = {}

    def add(name, service, required=(), fields=(), roles=OPERATIONAL, operation='read', description=None):
        mutation = operation != 'read'
        tools[name] = definition(
            name=name, description=description or name.replace('_', ' ').capitalize(), roles=roles,
            required_args=required, allowed_fields=fields + (('expected_revision',) if mutation else ()),
            requires_confirmation=mutation, risk_level='medium' if mutation else 'low',
            operation_type=operation, scope_type='province', canonical_service=service,
            display_type='table' if name.startswith('list_') else 'detail', executor=partial(_execute, name))

    add('get_notice', 'escalation_service.get_escalation_notice_detail', ('notice_id',), roles=EDITORS)
    add('update_notice_draft', 'notice_service.update_notice', ('notice_id',),
        ('title', 'body_text', 'final_text'), EDITORS, 'update', 'Edit unreleased draft notice text only; cannot review, release, sign or dispatch.')
    add('record_notice_receipt', 'notice_service.record_notice_receipt', ('notice_id', 'acknowledged_at'),
        ('acknowledged_at',), EDITORS, 'update', 'Record receipt of an already released notice using an explicit ISO timestamp; cannot release notices.')
    add('get_guideline', 'governance_service.get_guideline', ('guideline_id',))
    add('create_guideline', 'governance_service.create_guideline', ('program_id', 'title', 'guideline_type'),
        GUIDELINE_FIELDS, EDITORS, 'create', 'Create guideline metadata with an optional public HTTP(S) reference URL. File uploads use Library UI.')
    add('update_guideline', 'governance_service.update_guideline', ('guideline_id',), GUIDELINE_FIELDS, EDITORS, 'update')
    add('list_library_references', 'library_service.list_references', fields=(
        'search', 'reference_type', 'program_id', 'is_current', 'template_subtype', 'origin'))
    add('get_library_reference', 'library_service.get_reference', ('reference_uri',))
    add('create_library_reference', 'library_service.create_reference', ('program_id', 'title', 'reference_type'),
        REFERENCE_FIELDS, EDITORS, 'create', 'Create a guideline-backed Library reference. Template file creation uses Library UI.')
    add('update_library_reference', 'library_service.update_reference', ('reference_uri',),
        REFERENCE_FIELDS + TEMPLATE_FIELDS, EDITORS, 'update',
        'Edit guideline reference metadata. Only Admin may edit existing template label/default/placeholders; no file replacement.')
    add('list_completion_documents', 'completion_documents_service.list_completion_documents', ('project_id',))
    add('get_completion_document', 'completion_documents_service.get_completion_document', ('project_id', 'document_type'))
    add('update_completion_document_metadata', 'completion_documents_service.update_document_metadata',
        ('project_id', 'document_type'), ('returned_amount', 'receipt_number'), ('field_officer',), 'update',
        'Field Officer: edit draft Proof of Return of Funds amount/receipt only. Applicability and approvals use review UI.')
    add('list_subaybayan_verifications', 'monitoring_service.list_subaybayan_verifications', fields=('project_id', 'cycle_month'))
    add('upsert_subaybayan_verification', 'monitoring_service.upsert_subaybayan_verification',
        ('project_id', 'cycle_month'), SUBAY_FIELDS, EDITORS, 'update', 'Save SubayBAYAN verification metadata for an explicit project and cycle month.')
    add('list_management_actions', 'monitoring_service.list_management_actions', fields=('project_id', 'cycle_month'))
    add('create_management_action_draft', 'monitoring_service.upsert_management_action', ('project_id', 'cycle_month'),
        MAR_FIELDS, EDITORS, 'create', 'Create a project-linked management action draft. Submit/acknowledge/close use Monitoring UI.')
    add('update_management_action_draft', 'monitoring_service.upsert_management_action', ('action_id',),
        MAR_FIELDS, EDITORS, 'update', 'Edit a management action still in draft. Cannot reassign project, change status or close.')
    TOOL_NAMES.update(tools)
    return tools


def heuristic_plan(message, user):
    """Explicit tool-shaped commands with JSON values; never guess write arguments."""
    if user is None:
        return None
    # Full tool names are also useful when diagnosing a failed remote planner.
    match = re.match(r'^\s*([a-z_]+)\s*(\{.*\})?\s*$', message, re.S)
    if match and match[1] in TOOL_NAMES:
        name, raw = match[1], match[2]
        inferred = {}
    else:
        command, _, payload = message.partition('{')
        raw = '{' + payload if payload else None
        patterns = (
            (r'(?:get|show|view) notice\s*#?(\d+)', 'get_notice', 'notice_id'),
            (r'(?:update|edit) notice draft\s*#?(\d+)', 'update_notice_draft', 'notice_id'),
            (r'(?:record|log) notice receipt\s*#?(\d+)', 'record_notice_receipt', 'notice_id'),
            (r'(?:get|show|view) guideline\s*#?(\d+)', 'get_guideline', 'guideline_id'),
            (r'(?:update|edit) guideline\s*#?(\d+)', 'update_guideline', 'guideline_id'),
            (r'(?:create|add) guideline', 'create_guideline', None),
            (r'(?:list|show) library references', 'list_library_references', None),
            (r'(?:get|show|view) library reference\s+(\S+)', 'get_library_reference', 'reference_uri'),
            (r'(?:update|edit) library reference\s+(\S+)', 'update_library_reference', 'reference_uri'),
            (r'(?:create|add) library reference', 'create_library_reference', None),
            (r'(?:list|show) completion documents for project\s*#?(\d+)', 'list_completion_documents', 'project_id'),
            (r'(?:update|edit) completion document metadata for project\s*#?(\d+)', 'update_completion_document_metadata', 'project_id'),
            (r'(?:list|show) subaybayan verifications(?: for project\s*#?(\d+))?', 'list_subaybayan_verifications', 'project_id'),
            (r'(?:save|update|edit) subaybayan verification for project\s*#?(\d+)', 'upsert_subaybayan_verification', 'project_id'),
            (r'(?:list|show) management actions(?: for project\s*#?(\d+))?', 'list_management_actions', 'project_id'),
            (r'(?:create|add) management action draft for project\s*#?(\d+)', 'create_management_action_draft', 'project_id'),
            (r'(?:update|edit) management action draft\s*#?(\d+)', 'update_management_action_draft', 'action_id'),
        )
        selected = next(((found, name, key) for pattern, name, key in patterns
                         if (found := re.fullmatch(pattern, command.strip().rstrip('.?'), re.I))), None)
        if not selected:
            return None
        found, name, key = selected
        inferred = {key: found[1]} if key and found[1] else {}
    tool = _registry().get_tool(name)
    if user.role not in tool.roles:
        return {'assistant_reply': 'Your role cannot perform that action.', 'tool_calls': [],
                'ai_provider_used': 'local', 'heuristic_rule_hit': 'metadata_role_refusal'}
    try:
        args = json.loads(raw) if raw else {}
    except ValueError:
        return None
    if not isinstance(args, dict):
        return None
    # Explicit target and JSON must agree; retain conflicting fields for validation.
    for key, value in inferred.items():
        if key in args and str(args[key]) != str(value):
            return {'assistant_reply': 'The record IDs conflict. Please provide one target.', 'tool_calls': [],
                    'ai_provider_used': 'local', 'heuristic_rule_hit': 'metadata_clarification'}
        args[key] = value
    missing = [key for key in tool.required_args if key not in args]
    if missing:
        return {'assistant_reply': 'Please provide ' + ', '.join(missing) + '.', 'tool_calls': [],
                'ai_provider_used': 'local', 'heuristic_rule_hit': 'metadata_clarification'}
    return {'assistant_reply': 'I will prepare that change for confirmation.' if tool.requires_confirmation else 'I will retrieve those records.',
            'tool_calls': [{'tool_name': name, 'arguments': args, 'reason': 'Explicit metadata request.'}],
            'ai_provider_used': 'local', 'heuristic_rule_hit': 'metadata'}
