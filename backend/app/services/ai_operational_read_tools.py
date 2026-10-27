"""Read-only assignment and operational lists through canonical services."""
from functools import partial
import json
import re

from app.extensions import db
from app.models import User
from app.services import (access_service, lgu_service, project_service, requirement_workflow_service,
                          sla_service, submission_service)


TOOL_NAMES = {'list_staff_assignments', 'list_field_assignments', 'list_change_status_requests',
              'list_requirement_deficiencies', 'list_requirement_submissions', 'list_sla_deadlines'}
OPERATIONAL = ('admin', 'staff', 'field_officer')
BOOL_FIELDS = ('is_active', 'is_resolved', 'has_requirement', 'overdue_only')


def _registry():
    from app.services import ai_tool_registry
    return ai_tool_registry


def _error(message, status=422):
    return _registry().AiToolError(message, status)


def prepare(tool, args, user):
    extra = set(args) - set(tool.required_args) - set(tool.allowed_fields) - {'reason'}
    if extra:
        raise _error('Unsupported fields: ' + ', '.join(sorted(extra)))
    for key in set(args) & (set(tool.required_args) | set(tool.allowed_fields)):
        if key.endswith('_id') or key in ('page', 'per_page', 'fiscal_year'):
            if isinstance(args[key], bool) or not re.fullmatch(r'[1-9]\d*', str(args[key])):
                raise _error(f'{key} must be a positive integer.')
            args[key] = int(args[key])
        elif key in BOOL_FIELDS:
            if not isinstance(args[key], bool):
                raise _error(f'{key} must be true or false.')
        elif not isinstance(args[key], str):
            raise _error(f'{key} must be text.')
    if 'fiscal_year' in args and not 2000 <= args['fiscal_year'] <= 2100:
        raise _error('fiscal_year must be between 2000 and 2100.')
    args.setdefault('page', 1)
    args['per_page'] = min(args.get('per_page', 10), 20)
    choices = {'state': ('open', 'resolved', 'waived', 'all'), 'status': ('pending', 'approved', 'rejected'),
               'deadline_type': sla_service.VALID_DEADLINE_TYPES,
               'requirement_status': ('pending', 'under_review', 'compliant', 'non_compliant', 'waived'),
               'due_bucket': ('overdue', 'due_today', 'due_3', 'due_in_3', 'due_7', 'due_in_7', 'upcoming', 'future', 'resolved')}
    for key, allowed in choices.items():
        if key in args and args[key] not in allowed:
            raise _error(f'{key} must be one of: ' + ', '.join(allowed))
    try:
        if args.get('project_id'):
            access_service.ensure_project_access(args['project_id'], user.id)
        for key in ('requirement_id', 'project_requirement_id'):
            if args.get(key):
                requirement = access_service.ensure_project_requirement_access(args[key], user.id)
                if args.get('project_id') and requirement.project_id != args['project_id']:
                    raise _error('The requirement must belong to the selected project.')
        if args.get('lgu_id'):
            access_service.ensure_lgu_access(args['lgu_id'], user.id)
        if args.get('cluster_id'):
            access_service.ensure_cluster_access(args['cluster_id'], user.id)
        if tool.name in ('list_staff_assignments', 'list_field_assignments') and args.get('user_id'):
            target = db.session.get(User, args['user_id'])
            if not target or target.role not in OPERATIONAL:
                raise _error('Operational user not found.', 404)
    except access_service.AccessError as exc:
        raise _error(exc.message, exc.status_code) from exc


def _table(tool, args, rows, total=None):
    if total is None:
        total = len(rows)
        rows = rows[(args['page'] - 1) * args['per_page']:args['page'] * args['per_page']]
    keys = ('id', 'user_name', 'cluster_name', 'lgu_name', 'is_active', 'project_id',
            'project_requirement_id', 'description', 'finding_observation', 'resolution_state',
            'status', 'requested_status', 'deadline_type_label', 'deadline_date', 'is_resolved', 'current_version')
    columns = [{'key': key, 'label': key.replace('_', ' ').title()} for key in keys if any(key in row for row in rows)]
    return _registry()._table_result(tool.name.replace('_', ' ').capitalize(), rows, columns, meta={
        'page': args['page'], 'per_page': args['per_page'], 'total': total,
        'pages': (total + args['per_page'] - 1) // args['per_page']})


def _execute(name, args, user):
    tool = _registry().get_tool(name)
    data = {key: args[key] for key in tool.allowed_fields if key in args and key not in ('page', 'per_page')}
    try:
        if name in ('list_staff_assignments', 'list_field_assignments'):
            rows = lgu_service.list_assignments(scope_type='cluster' if name == 'list_staff_assignments' else 'lgu', **data)
            safe = []
            for row in rows:
                target = db.session.get(User, row['user_id'])
                roles = ('admin', 'staff') if name == 'list_staff_assignments' else ('field_officer',)
                if not target or target.role not in roles:
                    continue
                safe.append({**row, 'user_name': row.get('user', {}).get('full_name'),
                             'cluster_name': row.get('cluster', {}).get('name'), 'lgu_name': row.get('lgu', {}).get('name')})
            rows = sorted(safe, key=lambda row: (row.get('assigned_at') or '', row['id']), reverse=True)
        elif name == 'list_change_status_requests':
            rows = project_service.list_change_status_requests(user_id=user.id, **data)
            rows = sorted(rows, key=lambda row: (row.get('created_at') or '', row['id']), reverse=True)
        elif name == 'list_requirement_deficiencies':
            rows = requirement_workflow_service.list_deficiencies(args['requirement_id'], user_id=user.id, **data)
        elif name == 'list_requirement_submissions':
            records = submission_service.list_requirement_submissions(args['requirement_id'], user_id=user.id)
            # List metadata and authenticated file links; detailed checker outputs
            # remain in their existing result/review workflows.
            fields = ('id', 'project_id', 'project_requirement_id', 'uploaded_by', 'description', 'source',
                      'current_version', 'created_at', 'updated_at', 'document_files')
            rows = [{key: row[key] for key in fields if key in row} for row in records]
        else:
            result = sla_service.list_sla_deadlines(user_id=user.id, page=args['page'], per_page=args['per_page'], **data)
            for row in result['deadlines']:
                row['deadline_type_label'] = sla_service.format_deadline_type(row['deadline_type'])
            return _table(tool, args, result['deadlines'], result['total'])
        return _table(tool, args, rows)
    except (access_service.AccessError, lgu_service.LguError, project_service.ProjectError,
            requirement_workflow_service.WorkflowError, submission_service.SubmissionError, sla_service.SlaError) as exc:
        raise _error(exc.message, exc.status_code) from exc


def build_tools(definition):
    page = ('page', 'per_page')
    specs = {
        'list_staff_assignments': (('admin',), (), ('cluster_id', 'user_id', 'is_active', *page),
                                   'List explicit staff/admin cluster scope assignments; filter active/inactive rows explicitly. Operational users only.', 'lgu_service.list_assignments'),
        'list_field_assignments': (('admin',), (), ('lgu_id', 'user_id', 'is_active', *page),
                                   'List operational field-officer LGU scope assignments; filter user, LGU and active state.', 'lgu_service.list_assignments'),
        'list_change_status_requests': (('admin', 'staff'), (), ('project_id', 'status', 'fiscal_year', *page),
                                        'List requirement status-change requests. Staff see only their own in-scope requests. Does not review requests.', 'project_service.list_change_status_requests'),
        'list_requirement_deficiencies': (OPERATIONAL, ('requirement_id',), ('state', *page),
                                           'List documented deficiencies for an accessible requirement in the shared document workflow; state open/resolved/waived/all. Does not resolve or waive.', 'requirement_workflow_service.list_deficiencies'),
        'list_requirement_submissions': (OPERATIONAL, ('requirement_id',), page,
                                         'List submission metadata/current version numbers and authenticated file links for an accessible requirement. No scans or approvals.', 'submission_service.list_requirement_submissions'),
        'list_sla_deadlines': (OPERATIONAL, (), ('project_id', 'project_requirement_id', 'program_id', 'lgu_id', 'deadline_type',
                              'phase_name', 'requirement_status', 'has_requirement', 'due_bucket', 'is_resolved', 'overdue_only',
                              'fiscal_year', 'search', *page),
                               'List accessible SLA deadlines, including resolved and upcoming timers using explicit filters; paginated. Does not update or resolve timers.', 'sla_service.list_sla_deadlines'),
    }
    return {name: definition(name=name, description=description, roles=roles, required_args=required,
                            allowed_fields=fields, operation_type='read', scope_type='province' if roles == ('admin',) else 'project',
                            canonical_service=service, display_type='table', executor=partial(_execute, name))
            for name, (roles, required, fields, description, service) in specs.items()}


def heuristic_plan(message, user):
    text = message.split('{', 1)[0].lower()
    if not re.search(r'\b(list|show|view|get|find)\b', text) or re.search(r'\b(create|update|edit|delete|archive|resolve|approve|waive|explain|steps)\b|\bhow\s+(?:do|does|can|to)\b', text):
        return None
    name = next((name for pattern, name in (
        (r'\bstaff[- ](?:cluster[- ])?assignments?\b', 'list_staff_assignments'),
        (r'\bfield(?:[- ]officer)?[- ](?:lgu[- ])?assignments?\b', 'list_field_assignments'),
        (r'\b(?:status[- ]change|change[- ]status|change) requests?\b', 'list_change_status_requests'),
        (r'\bdeficiencies\b', 'list_requirement_deficiencies'),
        (r'\bsubmissions\b', 'list_requirement_submissions'),
        (r'\bsla deadlines?\b', 'list_sla_deadlines')) if re.search(pattern, text)), None)
    if not name:
        return None
    plan = dict(assistant_reply='I will list the accessible records.', tool_calls=[], ai_provider_used='local',
                ai_model_used='local:operational-reads', heuristic_rule_hit='operational_read')
    tool = _registry().get_tool(name)
    if not user or user.role not in tool.roles:
        plan['assistant_reply'] = 'Your role cannot access this record list.'
        return plan
    args = {}
    for label, key in (('project', 'project_id'), ('requirement', 'project_requirement_id' if name == 'list_sla_deadlines' else 'requirement_id'),
                       ('cluster', 'cluster_id'), ('lgu', 'lgu_id'), ('user', 'user_id'), ('program', 'program_id')):
        found = re.search(rf'\b{label}\s*(?:#|id\s*)\s*([1-9]\d*)\b', text)
        if found:
            args[key] = int(found.group(1))
    if name in ('list_staff_assignments', 'list_field_assignments'):
        if re.search(r'\binactive\b', text):
            args['is_active'] = False
        elif re.search(r'\bactive\b', text):
            args['is_active'] = True
    elif name == 'list_requirement_deficiencies':
        state = re.search(r'\b(open|resolved|waived)\b', text)
        if state:
            args['state'] = state.group(1)
    elif name == 'list_change_status_requests':
        status = re.search(r'\b(pending|approved|rejected)\b', text)
        if status:
            args['status'] = status.group(1)
    elif name == 'list_sla_deadlines':
        if re.search(r'\boverdue\b', text):
            args['overdue_only'] = True
        if re.search(r'\bunresolved\b', text):
            args['is_resolved'] = False
        elif re.search(r'\bresolved\b', text):
            args['is_resolved'] = True
        for phrase, value in ((r'due today', 'due_today'), (r'upcoming', 'upcoming'), (r'future', 'future')):
            if re.search(rf'\b{phrase}\b', text):
                args['due_bucket'] = value
    if 'fiscal_year' in tool.allowed_fields:
        year = re.search(r'\b(?:fy\s*|fiscal year\s*)(20\d\d|2100)\b', text)
        if year:
            args['fiscal_year'] = int(year.group(1))
    if '{' in message:
        try:
            payload = json.loads(message[message.index('{'):])
            if not isinstance(payload, dict):
                raise ValueError()
            args.update(payload)
        except ValueError:
            plan['assistant_reply'] = 'Please provide a valid JSON filter object.'
            return plan
    # Named filters require the planner's entity resolution rather than silently
    # turning an unknown person/location into an unfiltered list.
    for label, key in (('project', 'project_id'), ('requirement', 'project_requirement_id' if name == 'list_sla_deadlines' else 'requirement_id'),
                       ('cluster', 'cluster_id'), ('lgu', 'lgu_id'), ('user', 'user_id'), ('program', 'program_id')):
        if re.search(rf'\b(?:for|in)\s+{label}\b', text) and key not in args:
            return None
    missing = [key.replace('_', ' ') for key in tool.required_args if key not in args]
    if missing:
        plan['assistant_reply'] = 'Please provide ' + ', '.join(missing) + ' for this record list.'
        return plan
    plan['tool_calls'] = [dict(tool_name=name, arguments=args, reason='Explicit operational list request.')]
    return plan
