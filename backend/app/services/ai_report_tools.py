"""Scoped reports and authenticated, on-demand downloads for assistant results."""
import hashlib
import json
import re
from functools import partial
from io import BytesIO

from flask import send_file

from app.extensions import db
from app.models import (AiToolCall, GeneratedReport, Program, QaarGeneratedOutput, QaarInspection,
                        RequirementWorkflowTransition, StoredObject, User)
from app.services import (
    access_service, appendix_template_catalog as appendices, monitoring_service as monitoring,
    object_storage_service as storage, project_service, qaar_output_service,
    reporting_service, reporting_pdf_service, workbook_workspace_service as workbooks,
)
from app.utils.fiscal_year import FiscalYearError, validate_fiscal_year

OPERATIONAL = ('admin', 'staff', 'field_officer')
EDITORS = ('admin', 'staff')
FILTERS = ('fiscal_year', 'program_id', 'cluster_id', 'lgu_id', 'status')
PAGING = ('page', 'per_page')
TOOL_NAMES = set()
REPORT_READS = {'get_monitoring_updates_report', 'get_deep_dive_analytics'}
DOWNLOAD_TOOLS = {
    'export_monitoring_report_pdf', 'export_workbook_workspace', 'download_project_revision_report',
    'download_requirement_correction_report', 'get_saved_project_report', 'download_appendix_template',
    'get_qaar_output', 'generate_qaar_outputs', 'list_qaar_outputs', 'list_saved_project_reports',
}
ERRORS = (access_service.AccessError, monitoring.MonitoringError, project_service.ProjectError,
          storage.ObjectStorageError, workbooks.WorkbookWorkspaceError)


def _registry():
    from app.services import ai_tool_registry
    return ai_tool_registry


def _error(message, code=422):
    return _registry().AiToolError(message, code)


def _integer(value, field):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9]\d*', str(value)):
        raise _error(f'{field} must be a positive integer.')
    return int(value)


def _saved_report(report_id, user, requirement_id=None):
    report = db.session.get(GeneratedReport, report_id)
    parameters = report.parameters or {} if report else {}
    if not report or report.report_type != 'custom' or not parameters.get('project_id'):
        raise _error('Saved project report not found.', 404)
    access_service.ensure_project_access(parameters['project_id'], user.id)
    if requirement_id and parameters.get('project_requirement_id') != requirement_id:
        raise _error('Correction report does not belong to this requirement.', 404)
    stored = db.session.get(StoredObject, parameters.get('stored_object_id')) if parameters.get('stored_object_id') else None
    if not stored or stored.source_module not in ('revision_report', 'correction_report'):
        raise _error('Saved project report file not found.', 404)
    return report, stored


def _report_summary(report):
    return {'id': report.id, 'title': report.title, 'file_name': report.file_name,
            'file_format': report.file_format, 'project_id': (report.parameters or {}).get('project_id'),
            'project_requirement_id': (report.parameters or {}).get('project_requirement_id')}


def _correction_context(args, user):
    requirement = access_service.ensure_project_requirement_access(args['requirement_id'], user.id)
    if args.get('report_id'):
        _saved_report(args['report_id'], user, requirement.id)
    elif args.get('transition_id'):
        transition = db.session.get(RequirementWorkflowTransition, args['transition_id'])
        if not transition or transition.project_requirement_id != requirement.id or transition.action != 'return_for_revision':
            raise _error('Return-for-revision transition not found for this requirement.', 404)
    elif requirement.workflow_status != 'returned_for_revision':
        raise _error('No active return for revision. Specify a historical report_id or transition_id.', 404)
    return requirement


def _revision(inspection):
    snapshot = monitoring._serialize_inspection(inspection)
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


def prepare(tool, args, user):
    extra = set(args) - set(tool.required_args) - set(tool.allowed_fields) - {'reason', 'confirmation_display'}
    if extra:
        raise _error('Unsupported fields: ' + ', '.join(sorted(extra)) + '.')
    for key in set(args) & (set(tool.required_args) | set(tool.allowed_fields)):
        if ((key.endswith('_id') and key != 'template_id') or key == 'appendix_number') and args[key] is not None:
            args[key] = _integer(args[key], key)
    if 'fiscal_year' in args and args['fiscal_year'] is not None:
        try:
            if isinstance(args['fiscal_year'], bool):
                raise _error('fiscal_year must be a year.')
            args['fiscal_year'] = validate_fiscal_year(args['fiscal_year'])
        except FiscalYearError as exc:
            raise _error(str(exc)) from exc
    for key in ('status', 'project_kind', 'template_id', 'risk_detail', 'orientation', 'search', 'scope'):
        if key in args and args[key] is not None and not isinstance(args[key], str):
            raise _error(f'{key} must be text.')
    if args.get('status') and args['status'] not in ('not_yet_started', 'ongoing', 'completed', 'cancelled'):
        raise _error('Unsupported project status.')
    if any(key in tool.allowed_fields for key in PAGING):
        args['page'] = _integer(args.get('page', 1), 'page')
        args['per_page'] = min(_integer(args.get('per_page', 10), 'per_page'), 20)
    if tool.name == 'export_monitoring_report_pdf':
        if args.get('search') is None:
            args.pop('search', None)
        args.setdefault('scope', 'filtered')
        if args['scope'] not in ('filtered', 'all'):
            raise _error('scope must be filtered or all.')
        if args['scope'] == 'all' and any(args.get(k) for k in ('program_id', 'cluster_id', 'lgu_id', 'status', 'search')):
            raise _error('All-visible export cannot be combined with project filters. Use filtered scope or remove those filters.')
        if 'tabs' in args and (not isinstance(args['tabs'], list) or not args['tabs'] or
                any(not isinstance(v, str) or v not in ('analytics', 'monitoring', 'documents', 'risk') for v in args['tabs'])):
            raise _error('tabs must be a nonempty list of analytics, monitoring, documents or risk.')
        for key, options, default in (('orientation', ('portrait', 'landscape'), 'landscape'),
                                      ('risk_detail', ('executive', 'comprehensive'), 'executive')):
            args.setdefault(key, default)
            if args[key] not in options:
                raise _error(f'Unsupported {key}.')
    if tool.name == 'generate_qaar_outputs':
        args.setdefault('output_types', ['full_package', 'aide_memoire', 'notice_of_defects'])
        values = args['output_types']
        if not isinstance(values, list) or not values or len(values) > 8 or any(
                not isinstance(v, str) or v not in qaar_output_service.VALID_OUTPUT_TYPES for v in values) or len(set(values)) != len(values):
            raise _error('output_types must be a nonempty list of unique supported QAAR output types.')
    try:
        if args.get('program_id') and not db.session.get(Program, args['program_id']):
            raise _error('Program not found.', 404)
        if args.get('cluster_id'):
            access_service.ensure_cluster_access(args['cluster_id'], user.id)
        if args.get('lgu_id'):
            access_service.ensure_lgu_access(args['lgu_id'], user.id)
        if args.get('project_id'):
            access_service.ensure_project_access(args['project_id'], user.id)
        if args.get('inspection_id'):
            inspection = monitoring.get_inspection(args['inspection_id'], user_id=user.id)
        if tool.name == 'generate_qaar_outputs':
            if inspection.monitoring_type != 'qaar':
                raise _error('Select a QAAR inspection to generate QAAR outputs.')
            revision = _revision(inspection)
            if args.get('expected_revision') and args['expected_revision'] != revision:
                raise _error('Inspection content changed after review. Prepare a fresh generation request.', 409)
            args['expected_revision'] = revision
            args['confirmation_display'] = {'action': 'Generate QAAR outputs',
                'target': {'inspection_id': inspection.id, 'project_id': inspection.project_id},
                'changes': {'output_types': {'from': None, 'to': args['output_types']}},
                'notice': 'Creates saved PDF outputs. It does not approve evidence or release, sign or dispatch notices.'}
        if tool.name == 'get_qaar_output':
            monitoring.get_generated_output_download(args['output_id'], user_id=user.id)
        if tool.name == 'get_saved_project_report':
            _saved_report(args['report_id'], user)
        if tool.name == 'download_requirement_correction_report':
            if args.get('report_id') and args.get('transition_id'):
                raise _error('Specify report_id or transition_id, not both.')
            _correction_context(args, user)
        if tool.name == 'export_workbook_workspace':
            # Reuse the workbook assistant's intersection of imported and current project scope.
            from app.services import ai_workbook_tools
            ai_workbook_tools._workspace(args, user)
        if tool.name == 'download_appendix_template':
            if not appendices.get_appendix_by_number(args['appendix_number']) or not appendices.get_appendix_file_path(args['appendix_number']):
                raise _error('Appendix template file not found.', 404)
    except ERRORS as exc:
        raise _error(exc.message, exc.status_code) from exc


def _download(label, **identifiers):
    # These server-owned descriptors are resolved by an authenticated tool-call endpoint.
    return {'label': label, **identifiers}


def _output_summary(output):
    return {key: output.get(key) for key in ('id', 'inspection_id', 'output_type', 'title', 'status', 'generated_at')}


def _table(title, rows, args):
    total, size, page = len(rows), args['per_page'], args['page']
    rows = rows[(page - 1) * size:page * size]
    columns = [{'key': key, 'label': key.replace('_', ' ').title()} for key in
               ('id', 'title', 'appendix_reference', 'project_id', 'file_name', 'output_type') if any(key in row for row in rows)]
    return _registry()._table_result(title, rows, columns, meta={
        'page': page, 'per_page': size, 'total': total, 'pages': (total + size - 1) // size})


def _execute(name, args, user):
    try:
        tool = _registry().get_tool(name)
        if name == 'generate_qaar_outputs':
            QaarInspection.query.filter_by(id=args['inspection_id']).populate_existing().with_for_update().first()
        prepare(tool, args, user)
        title = name.replace('_', ' ').capitalize()
        downloads = []
        if name in REPORT_READS:
            method = reporting_service.get_monitoring_updates_report if name == 'get_monitoring_updates_report' else reporting_service.get_deep_dive_analytics
            data = method(user_id=user.id, **{k: args[k] for k in FILTERS if k in args})
            totals = {k: len(v) for k, v in data.items() if isinstance(v, list)}
            start = (args['page'] - 1) * args['per_page']
            data = {k: v[start:start + args['per_page']] if isinstance(v, list) else v for k, v in data.items()}
            data['pagination'] = {'page': args['page'], 'per_page': args['per_page'], 'totals': totals}
            result = _registry()._detail_result(title, data)
        elif name == 'list_appendix_templates':
            project_kind = args.get('project_kind')
            if args.get('project_id'):
                project = access_service.ensure_project_access(args['project_id'], user.id)
                project_kind = project_kind or project_service.resolve_effective_project_kind(project)
            result = _table(title, appendices.list_appendix_templates(project_kind=project_kind), args)
        elif name in ('list_qaar_outputs', 'generate_qaar_outputs'):
            if name == 'generate_qaar_outputs':
                outputs = monitoring.generate_qaar_outputs(args['inspection_id'], output_types=args['output_types'], user_id=user.id)
                result = _registry()._detail_result(title, {'outputs': [_output_summary(o) for o in outputs]})
            else:
                items = QaarGeneratedOutput.query.filter_by(inspection_id=args['inspection_id']).order_by(QaarGeneratedOutput.id.desc()).all()
                outputs = [monitoring._serialize_generated_output(o) for o in items]
                result = _table(title, [_output_summary(o) for o in outputs], args)
                outputs = outputs[(args['page'] - 1) * args['per_page']:args['page'] * args['per_page']]
            downloads = [_download(o['title'], output_id=o['id']) for o in outputs if o.get('file')]
        elif name == 'get_qaar_output':
            output = monitoring.get_generated_output(args['output_id'], user_id=user.id)
            result = _registry()._detail_result(title, _output_summary(monitoring._serialize_generated_output(output)))
            downloads = [_download('Download QAAR PDF', output_id=output.id)]
        elif name == 'list_saved_project_reports':
            items = GeneratedReport.query.filter(GeneratedReport.report_type == 'custom',
                GeneratedReport.parameters['project_id'].as_integer() == args['project_id']).order_by(GeneratedReport.id.desc()).all()
            summaries = []
            for item in items:
                try:
                    _saved_report(item.id, user)
                    summaries.append(_report_summary(item))
                except _registry().AiToolError as exc:
                    if exc.status_code != 404:
                        raise
            result = _table(title, summaries, args)
            downloads = [_download(row['file_name'] or row['title'], report_id=row['id']) for row in result['rows']]
        elif name == 'get_saved_project_report':
            report, _ = _saved_report(args['report_id'], user)
            result = _registry()._detail_result(title, _report_summary(report))
            downloads = [_download('Download saved report', report_id=report.id)]
        else:
            result = _registry()._detail_result(title, {k: v for k, v in args.items()
                if k not in ('confirmation_display', 'reason', 'expected_revision')})
            downloads = [_download({'export_monitoring_report_pdf': 'Download monitoring report PDF',
                'export_workbook_workspace': 'Download workbook XLSX',
                'download_project_revision_report': 'Download project revision report DOCX',
                'download_requirement_correction_report': 'Download requirement correction report DOCX',
                'download_appendix_template': 'Download appendix template XLSX'}[name])]
            result['summary'] = 'Download is available. The file is generated or retrieved when selected, using your current access.'
        if downloads:
            result['downloads'] = downloads
        return result
    except ERRORS as exc:
        db.session.rollback()
        raise _error(exc.message, exc.status_code) from exc
    except Exception:
        db.session.rollback()
        raise


def _correction_download(args, user):
    requirement = _correction_context(args, user)
    if args.get('report_id'):
        return _stored_response(*_saved_report(args['report_id'], user, requirement.id))
    transition_id = args.get('transition_id')
    if not transition_id:
        transition = RequirementWorkflowTransition.query.filter_by(
            project_requirement_id=requirement.id, action='return_for_revision').order_by(
                RequirementWorkflowTransition.created_at.desc(), RequirementWorkflowTransition.id.desc()).first()
        transition_id = transition.id if transition else None
    if transition_id:
        saved = GeneratedReport.query.filter(GeneratedReport.report_type == 'custom',
            GeneratedReport.parameters['project_requirement_id'].as_integer() == requirement.id,
            GeneratedReport.parameters['workflow_transition_id'].as_integer() == transition_id).order_by(GeneratedReport.id.desc()).first()
        if saved:
            return _stored_response(*_saved_report(saved.id, user, requirement.id))
    generated = project_service.generate_requirement_correction_report(requirement.id, user_id=user.id, transition_id=transition_id)
    return _bytes_response(generated)


def _stored_response(report, stored):
    return storage.download_response(stored, download_name=report.file_name, content_type=stored.content_type)


def _bytes_response(file):
    return send_file(BytesIO(file['content']), as_attachment=True,
                     download_name=file['file_name'], mimetype=file['mimetype'])


def download_tool_file(call_id, index, user_id):
    """Never accept a client path, URL, object ID, or generation payload at download time."""
    call = db.session.get(AiToolCall, call_id)
    if not call or call.conversation.user_id != int(user_id) or call.requested_by != int(user_id):
        raise _error('Assistant download not found.', 404)
    if call.status != 'completed' or call.tool_name not in DOWNLOAD_TOOLS:
        raise _error('This action has no completed download.', 409)
    descriptors = (call.output_data or {}).get('downloads') or []
    if index < 0 or index >= len(descriptors):
        raise _error('Assistant file not found.', 404)
    user = db.session.get(User, int(user_id))
    try:
        download_args = dict(call.input_data or {})
        if call.tool_name == 'generate_qaar_outputs':
            # A saved PDF remains a valid historical artifact after an inspection edit.
            download_args.pop('expected_revision', None)
        args = _registry().validate_tool_request(_registry().get_tool(call.tool_name), download_args, user)
        descriptor = descriptors[index]
        name = call.tool_name
        if name == 'export_monitoring_report_pdf':
            filters = {k: args[k] for k in FILTERS + ('search',) if k in args}
            content, filename = reporting_pdf_service.generate_reports_analytics_pdf(user_id=user.id,
                tabs=args.get('tabs'), scope=args['scope'], orientation=args['orientation'], risk_detail=args['risk_detail'], filters=filters)
            response = _bytes_response({'content': content, 'file_name': filename, 'mimetype': 'application/pdf'})
        elif name == 'export_workbook_workspace':
            response = _bytes_response(workbooks.export_workspace(args['workspace_id'], user_id=user.id))
        elif name == 'download_project_revision_report':
            response = _bytes_response(project_service.generate_revision_report(args['project_id'], user_id=user.id, template_id=args.get('template_id')))
        elif name == 'download_requirement_correction_report':
            response = _correction_download(args, user)
        elif name in ('get_saved_project_report', 'list_saved_project_reports'):
            report, stored = _saved_report(descriptor['report_id'], user)
            if args.get('project_id') and (report.parameters or {}).get('project_id') != args['project_id']:
                raise _error('Report does not belong to this project.', 404)
            response = _stored_response(report, stored)
        elif name == 'download_appendix_template':
            item = appendices.get_appendix_by_number(args['appendix_number'])
            response = send_file(appendices.get_appendix_file_path(args['appendix_number']), as_attachment=True,
                download_name=item['filename'], mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else:
            output, stored = monitoring.get_generated_output_download(descriptor['output_id'], user_id=user.id)
            if args.get('inspection_id') and output.inspection_id != args['inspection_id']:
                raise _error('Output does not belong to this inspection.', 404)
            response = storage.download_response(stored, download_name=stored.original_filename, content_type=stored.content_type)
        response.headers['Cache-Control'] = 'private, no-store'
        return response
    except ERRORS as exc:
        db.session.rollback()
        raise _error(exc.message, exc.status_code) from exc


def build_tools(definition):
    tools = {}

    def add(name, service, required=(), fields=(), roles=OPERATIONAL, confirmation=False, description=None):
        tools[name] = definition(name=name, description=description or name.replace('_', ' ').capitalize(),
            roles=roles, required_args=required, allowed_fields=fields,
            requires_confirmation=confirmation, risk_level='medium' if confirmation else 'low',
            operation_type='create' if confirmation else 'read', scope_type='province', canonical_service=service,
            display_type='table' if name.startswith('list_') else 'detail', executor=partial(_execute, name))

    add('get_monitoring_updates_report', 'reporting_service.get_monitoring_updates_report', fields=FILTERS + PAGING, roles=EDITORS)
    add('get_deep_dive_analytics', 'reporting_service.get_deep_dive_analytics', fields=FILTERS + PAGING, roles=EDITORS)
    add('export_monitoring_report_pdf', 'reporting_pdf_service.generate_reports_analytics_pdf',
        fields=FILTERS + ('tabs', 'orientation', 'risk_detail', 'search', 'scope'), roles=EDITORS,
        description='Offer authenticated PDF export of current visible report data, with explicit filters; generation occurs on download.')
    add('export_workbook_workspace', 'workbook_workspace_service.export_workspace', ('workspace_id',),
        description='Offer an XLSX workbook export of currently accessible rows; generation occurs on download.')
    add('download_project_revision_report', 'project_service.generate_revision_report', ('project_id',), ('template_id',),
        description='Offer DOCX project revision report generation on download. Saves an audited report artifact; no review or return action.')
    add('download_requirement_correction_report', 'project_service.generate_requirement_correction_report', ('requirement_id',), ('report_id', 'transition_id'),
        description='Download current or explicitly historical correction report DOCX. Requires an active return or a valid historical report/return ID; never returns evidence for revision.')
    add('list_saved_project_reports', 'GeneratedReport/project access', ('project_id',), PAGING)
    add('get_saved_project_report', 'GeneratedReport/project access', ('report_id',))
    add('list_appendix_templates', 'appendix_template_catalog.list_appendix_templates', fields=('project_id', 'project_kind') + PAGING)
    add('download_appendix_template', 'appendix_template_catalog.get_appendix_file_path', ('appendix_number',))
    add('list_qaar_outputs', 'monitoring_service.get_inspection', ('inspection_id',), PAGING)
    add('get_qaar_output', 'monitoring_service.get_generated_output_download', ('output_id',))
    add('generate_qaar_outputs', 'monitoring_service.generate_qaar_outputs', ('inspection_id',),
        ('output_types', 'expected_revision'), EDITORS, True,
        'Generate saved QAAR PDF outputs after confirmation. No evidence approval, official release, signature or dispatch.')
    TOOL_NAMES.update(tools)
    return tools


def heuristic_plan(message, user):
    if user is None:
        return None
    text, _, payload = message.partition('{')
    patterns = (
        (r'(?:show|get) monitoring updates report', 'get_monitoring_updates_report', None),
        (r'(?:show|get) deep[- ]dive analytics', 'get_deep_dive_analytics', None),
        (r'(?:export|download) monitoring report pdf', 'export_monitoring_report_pdf', None),
        (r'(?:export|download) workbook(?: workspace)?\s*#?(\d+)', 'export_workbook_workspace', 'workspace_id'),
        (r'(?:download|generate) project revision report for project\s*#?(\d+)', 'download_project_revision_report', 'project_id'),
        (r'(?:download|get) requirement correction report for requirement\s*#?(\d+)', 'download_requirement_correction_report', 'requirement_id'),
        (r'(?:list|show) saved reports for project\s*#?(\d+)', 'list_saved_project_reports', 'project_id'),
        (r'(?:get|download) saved report\s*#?(\d+)', 'get_saved_project_report', 'report_id'),
        (r'(?:list|show) appendix templates', 'list_appendix_templates', None),
        (r'download appendix(?: template)?\s*#?(\d+)', 'download_appendix_template', 'appendix_number'),
        (r'(?:list|show) qaar outputs for inspection\s*#?(\d+)', 'list_qaar_outputs', 'inspection_id'),
        (r'(?:get|download) qaar output\s*#?(\d+)', 'get_qaar_output', 'output_id'),
        (r'generate qaar outputs for inspection\s*#?(\d+)', 'generate_qaar_outputs', 'inspection_id'),
    )
    selected = next(((m, name, key) for pattern, name, key in patterns
                     if (m := re.fullmatch(pattern, text.strip().rstrip('.?'), re.I))), None)
    if not selected:
        return None
    match, name, key = selected
    tool = _registry().get_tool(name)
    if user.role not in tool.roles:
        return {'assistant_reply': 'Your role cannot perform that action.', 'tool_calls': [],
                'ai_provider_used': 'local', 'heuristic_rule_hit': 'report_role_refusal'}
    try:
        args = json.loads('{' + payload) if payload else {}
    except ValueError:
        return None
    if not isinstance(args, dict):
        return None
    if key:
        if key in args and str(args[key]) != match[1]:
            return {'assistant_reply': 'The record IDs conflict. Please provide one target.', 'tool_calls': [],
                    'ai_provider_used': 'local', 'heuristic_rule_hit': 'report_clarification'}
        args[key] = int(match[1])
    return {'assistant_reply': 'I will prepare those outputs for confirmation.' if tool.requires_confirmation else 'I will retrieve that report or download option.',
            'tool_calls': [{'tool_name': name, 'arguments': args, 'reason': 'Explicit report request.'}],
            'ai_provider_used': 'local', 'heuristic_rule_hit': 'report_access'}
