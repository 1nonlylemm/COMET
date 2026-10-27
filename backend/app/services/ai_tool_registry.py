from dataclasses import dataclass, field
from typing import Callable

from app.services import (
    access_service,
    audit_service,
    backup_service,
    escalation_service,
    ai_insight_service,
    global_search_service,
    governance_service,
    import_service,
    monitoring_service,
    project_service,
    settings_service,
    sla_service,
    submission_service,
    field_officer_service,
    non_infra_monitoring_service,
    beneficiary_evidence_service,
    requirement_workflow_service,
    operational_reporting_service,
    lgu_service,
    program_service,
    monthly_progress_service,
    form3_service,
    notice_service,
    batch_import_service,
)
from app.services.email_service import _format_requirement_status_label
from app.services.project_status import project_status_label


class AiToolError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


PROJECT_TRACKING_DATES = ('nadai_received_at', 'subaybayan_enrolled_at')
PROJECT_SCHEDULE_DATES = (
    'target_start_date', 'target_end_date', 'actual_start_date', 'actual_end_date',
    *PROJECT_TRACKING_DATES,
)


def _validate_project_tracking_dates(args):
    from app.api.projects.schemas import _coerce_iso_date
    errors = {}
    for field in PROJECT_TRACKING_DATES:
        if field in args:
            _coerce_iso_date(args, field, errors)
            if args[field] == '':
                args[field] = None
    if errors:
        raise AiToolError('; '.join(f'{key}: {value}' for key, value in errors.items()), 422)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    roles: tuple
    risk_level: str = 'low'
    requires_confirmation: bool = False
    required_args: tuple = field(default_factory=tuple)
    display_type: str = 'text'
    executor: Callable = None
    operation_type: str = 'read'
    scope_type: str = 'global'
    canonical_service: str = ''
    allowed_fields: tuple = field(default_factory=tuple)



USER_FACING_TOOL_LABELS = {
    'update_project_metadata': 'Edit general project details',
    'update_project_budget': "Change a project's budget",
    'update_project_lgu_assignment': "Change the project's assigned LGU",
    'update_project_cycle': "Change the project's program cycle",
    'update_project_status': "Update the project's operational status",
    'update_project_schedule': "Update the project's milestone schedule",
    'create_project': 'Create new project',
    'search_projects': 'Search projects',
    'query_projects': 'Query projects',
    'get_project_overview': 'View project overview',
    'bulk_update_project_metadata': 'Bulk edit project details',
    'bulk_update_project_schedule': 'Bulk update milestone schedules',
    'bulk_update_project_status': 'Bulk update operational statuses',
    'create_monthly_progress_report': 'Create monthly progress report',
    'create_form3_request': 'Create Form 3 inspection request',
    'create_non_infra_monitoring_record': 'Create non-infrastructure monitoring record',
    'create_monitoring_inspection': 'Record monitoring inspection',
    'create_beneficiary_evidence_record': 'Record beneficiary evidence',
    'list_beneficiary_evidence_records': 'List beneficiary evidence records',
    'list_non_infra_monitoring_records': 'List non-infrastructure monitoring records',
    'list_monitoring_inspections': 'List monitoring inspections',
    'monitoring_workbench': 'Open monitoring workbench',
    'query_requirements': 'Query documentary requirements',
    'get_requirement_detail': 'View requirement details',
    'create_requirement_comment': 'Post requirement comment',
    'push_requirement_handoff': 'Submit requirement for handoff',
    'upload_evidence_from_attachment': 'Upload documentary evidence',
    'list_guidelines': 'List documentary guidelines',
    'list_handoff_queue': 'View handoff review queue',
    'generate_compliance_summary': 'Generate compliance summary',
    'get_deficiency_pattern_summary': 'View deficiency pattern summary',
    'get_provincial_overview': 'View provincial operational overview',
    'compare_lgu_portfolios': 'Compare LGU portfolios',
    'get_portfolio_risk_ranking': 'View portfolio risk ranking',
    'get_recent_operational_activity': 'View recent operational activity',
    'get_field_summary': 'View field officer dashboard summary',
    'list_assigned_lgus': 'List assigned LGUs',
    'list_action_items': 'List field action items',
    'list_overdue_slas': 'List overdue compliance deadlines',
    'get_sla_summary': 'View SLA compliance summary',
    'get_sla_deadline_detail': 'View deadline details',
    'create_sla_deadline': 'Create compliance deadline',
    'resolve_sla_deadline': 'Resolve compliance deadline',
    'generate_notice_for_sla': 'Generate Notice of Deficiency for SLA',
    'create_notice_draft': 'Draft Notice of Deficiency',
    'list_notices': 'List escalation notices',
    'create_lgu': 'Create LGU profile',
    'update_lgu': 'Update LGU profile',
    'create_cluster': 'Create LGU cluster',
    'update_cluster': 'Update LGU cluster',
    'create_program': 'Create grant program',
    'update_program': 'Update grant program',
    'create_program_cycle': 'Create program cycle',
    'update_program_cycle': 'Update program cycle',
    'create_user': 'Create user account',
    'update_user_profile': 'Update user profile',
    'preview_import': 'Preview batch or workbook import',
    'commit_import': 'Commit batch or workbook import',
    'list_import_batches': 'List import batches',
    'query_audit_log': 'Query audit logs',
    'audit_summary': 'Summarize audit trail',
    'get_system_readiness': 'Check system readiness',
    'settings_readiness': 'Check system settings readiness',
    'trigger_database_backup': 'Trigger database backup',
    'restore_database_backup': 'Restore database backup',
    'list_database_backups': 'List database backups',
    'global_search': 'Search workspace',
}


def get_user_facing_tool_label(tool_name: str) -> str:
    """Return a concise, human-readable user-facing action description for a registered tool."""
    if not tool_name:
        return 'Assistant Action'
    return USER_FACING_TOOL_LABELS.get(tool_name, tool_name.replace('_', ' ').title())


def _get_app_name() -> str:
    try:
        from app.services import settings_service
        name = settings_service.get_app_name()
        if name and name.strip():
            return name.strip()
    except Exception:
        pass
    try:
        from flask import current_app
        if current_app and current_app.config.get('APP_NAME'):
            return str(current_app.config['APP_NAME']).strip()
    except Exception:
        pass
    import os
    env_name = os.environ.get('APP_NAME')
    if env_name and env_name.strip():
        return env_name.strip()
    return 'DILG Operations Workspace'


def get_capability_definition(tool_name):
    tool = get_tool(tool_name)
    app_name = _get_app_name()
    return {
        'name': tool.name,
        'description': settings_service.format_dynamic_branding(tool.description, app_name=app_name),
        'roles': list(tool.roles),
        'risk_level': tool.risk_level,
        'requires_confirmation': tool.requires_confirmation,
        'required_args': list(tool.required_args),
        'display_type': tool.display_type,
        'operation_type': tool.operation_type,
        'scope_type': tool.scope_type,
        'canonical_service': tool.canonical_service,
        'allowed_fields': list(tool.allowed_fields),
    }


def get_tool_catalog_for_prompt(user_role):
    app_name = _get_app_name()
    return [
        {
            'name': tool.name,
            'description': settings_service.format_dynamic_branding(tool.description, app_name=app_name),
            'risk_level': tool.risk_level,
            'requires_confirmation': tool.requires_confirmation,
            'required_args': list(tool.required_args),
            'allowed_fields': list(tool.allowed_fields) + (
                ['all_fiscal_years'] if tool.operation_type == 'read'
                and 'fiscal_year' in tool.allowed_fields
                and 'all_fiscal_years' not in tool.allowed_fields else []
            ),
            'display_type': tool.display_type,
        }
        for tool in TOOLS.values()
        if user_role in tool.roles
    ]


def get_tool(tool_name):
    tool = TOOLS.get(tool_name)
    if not tool:
        raise AiToolError(f'Unknown {settings_service.get_assistant_name()} action: {tool_name}', 422)
    return tool


def run_tool(tool_name, arguments, user):
    tool = get_tool(tool_name)
    args = validate_tool_request(tool, arguments, user)
    return tool.executor(args, user)


def validate_tool_request(tool, arguments, user):
    _ensure_role(tool, user)
    args = dict(arguments or {})
    _normalize_tool_arguments(tool, args)
    if tool.operation_type == 'read' and 'fiscal_year' in tool.allowed_fields:
        all_years = args.pop('all_fiscal_years', False)
        if not isinstance(all_years, bool):
            raise AiToolError('all_fiscal_years must be true or false.', 422)
        if all_years:
            args.pop('fiscal_year', None)
    _validate_required_args(tool, args)
    from app.services import ai_cru_tools, ai_import_tools, ai_workbook_tools, ai_metadata_tools, ai_report_tools, ai_program_setup_tools, ai_operational_read_tools, ai_workbook_column_tools
    if tool.name in ai_workbook_column_tools.TOOL_NAMES:
        ai_workbook_column_tools.prepare(tool, args, user)
    elif tool.name in ai_operational_read_tools.TOOL_NAMES:
        ai_operational_read_tools.prepare(tool, args, user)
    elif tool.name in ai_program_setup_tools.TOOL_NAMES:
        ai_program_setup_tools.prepare(tool, args, user)
    elif tool.name in ai_report_tools.TOOL_NAMES:
        ai_report_tools.prepare(tool, args, user)
    elif tool.name in ai_metadata_tools.TOOL_NAMES:
        ai_metadata_tools.prepare(tool, args, user)
    elif tool.name in ai_workbook_tools.TOOL_NAMES:
        ai_workbook_tools.prepare(tool, args, user)
    elif tool.name in ai_import_tools.TOOL_NAMES:
        ai_import_tools.prepare(tool, args, user)
    elif tool.name in ai_cru_tools.TOOL_NAMES:
        ai_cru_tools.prepare(tool, args, user)
    else:
        _validate_allowed_fields(tool, args)
    _validate_scoped_args(tool, args, user)
    from app.services import ai_program_schema_tools
    ai_program_schema_tools.prepare(tool, args, user)
    if tool.name in ('preview_import', 'commit_import'):
        ai_import_tools.prepare_import(tool, args, user)
    _prepare_confirmation_display(tool, args, user)
    return args


def _normalize_tool_arguments(tool, args):
    if tool.name == 'create_user':
        if 'cluster_id' in args:
            single_val = args.pop('cluster_id')
            if single_val is not None and str(single_val).strip() != '':
                plural_vals = args.get('cluster_ids')
                if plural_vals is not None:
                    if isinstance(plural_vals, (int, str)):
                        plural_list = [plural_vals]
                    elif isinstance(plural_vals, (list, tuple, set)):
                        plural_list = list(plural_vals)
                    else:
                        plural_list = []
                    try:
                        single_int = int(single_val)
                        plural_ints = [int(x) for x in plural_list]
                        if plural_ints and single_int not in plural_ints:
                            raise AiToolError('Conflicting cluster_id and cluster_ids provided.', 422)
                        args['cluster_ids'] = plural_ints or [single_int]
                    except (ValueError, TypeError):
                        if str(single_val) not in [str(x) for x in plural_list] and plural_list:
                            raise AiToolError('Conflicting cluster_id and cluster_ids provided.', 422)
                        args['cluster_ids'] = plural_list or [single_val]
                else:
                    args['cluster_ids'] = [single_val]

        if 'lgu_id' in args:
            single_val = args.pop('lgu_id')
            if single_val is not None and str(single_val).strip() != '':
                plural_vals = args.get('lgu_ids')
                if plural_vals is not None:
                    if isinstance(plural_vals, (int, str)):
                        plural_list = [plural_vals]
                    elif isinstance(plural_vals, (list, tuple, set)):
                        plural_list = list(plural_vals)
                    else:
                        plural_list = []
                    try:
                        single_int = int(single_val)
                        plural_ints = [int(x) for x in plural_list]
                        if plural_ints and single_int not in plural_ints:
                            raise AiToolError('Conflicting lgu_id and lgu_ids provided.', 422)
                        args['lgu_ids'] = plural_ints or [single_int]
                    except (ValueError, TypeError):
                        if str(single_val) not in [str(x) for x in plural_list] and plural_list:
                            raise AiToolError('Conflicting lgu_id and lgu_ids provided.', 422)
                        args['lgu_ids'] = plural_list or [single_val]
                else:
                    args['lgu_ids'] = [single_val]


def _validate_allowed_fields(tool, args):
    if not tool.allowed_fields and tool.operation_type != 'read':
        return

    # Check for explicitly forbidden fields on specific tools
    if tool.name == 'update_project_metadata':
        if 'budget_amount' in args:
            raise AiToolError('Budget updates must be performed using the update_project_budget action.', 422)
        if 'lgu_id' in args or 'program_id' in args:
            raise AiToolError('Project LGU and Program assignments cannot be modified via metadata update.', 422)
        if 'current_phase' in args:
            raise AiToolError('Project phase changes must follow the formal project lifecycle workflow.', 422)

    if tool.operation_type == 'bulk_update':
        from app.services import bulk_project_service
        updates_dict = args.get('updates') if isinstance(args.get('updates'), dict) else {}
        combined = {**args, **updates_dict}
        if tool.name == 'bulk_update_project_metadata':
            if 'budget_amount' in combined:
                raise AiToolError('Budget updates must be performed using the update_project_budget action.', 422)
            if 'current_phase' in combined:
                raise AiToolError('Project phase transitions must be processed through the formal project lifecycle workflow.', 422)
            if 'overall_status' in combined:
                raise AiToolError('Project status updates must be performed using the bulk_update_project_status action.', 422)
            if 'lgu_id' in updates_dict or 'program_id' in updates_dict or 'program_cycle_id' in updates_dict:
                raise AiToolError('Project LGU and Program assignments cannot be modified via metadata update.', 422)

        ignored_keys = set(tool.required_args) | {
            'confirmation_display', 'confirmation_phrase', 'reason',
            'selectors', 'updates', 'target_ids', 'preview_fingerprint', '_bulk_change_set'
        }
        disallowed = [k for k in args.keys() if k not in tool.allowed_fields and k not in ignored_keys]
        if disallowed:
            raise AiToolError(
                f"Field(s) {', '.join(sorted(disallowed))} cannot be modified with {tool.name}. Allowed fields: {', '.join(tool.allowed_fields)}.",
                422,
            )
        return

    # Check that any provided field outside required_args and metadata is in allowed_fields
    ignored_keys = set(tool.required_args) | {'confirmation_display', 'confirmation_phrase', 'reason'}
    if tool.operation_type == 'read' and 'fiscal_year' in tool.allowed_fields:
        ignored_keys.add('all_fiscal_years')
    if tool.name == 'create_notice_draft':
        ignored_keys |= {'status', 'notice_type'}
    disallowed = [k for k in args.keys() if k not in tool.allowed_fields and k not in ignored_keys]
    if disallowed:
        raise AiToolError(
            f"Field(s) {', '.join(sorted(disallowed))} cannot be modified with {tool.name}. Allowed fields: {', '.join(tool.allowed_fields)}.",
            422,
        )

    if tool.operation_type == 'read':
        return

    # Check that at least one allowed field is provided for the update
    provided_updates = [k for k in tool.allowed_fields if k in args and (
        args[k] is not None or (tool.name == 'update_project_schedule' and k in PROJECT_TRACKING_DATES)
    )]
    if not provided_updates:
        raise AiToolError(
            f"At least one field to update must be provided. Allowed fields: {', '.join(tool.allowed_fields)}.",
            422,
        )


def _ensure_role(tool, user):
    if user.role not in tool.roles:
        raise AiToolError(f'Your role cannot use the {tool.name} {settings_service.get_assistant_name()} action.', 403)


def _validate_required_args(tool, args):
    if tool.name == 'get_sla_deadline_detail':
        if args.get('deadline_id') in (None, '') and args.get('sla_id') not in (None, ''):
            args['deadline_id'] = args['sla_id']
    missing = [key for key in tool.required_args if args.get(key) in (None, '')]
    if missing:
        if tool.name == 'generate_notice_for_sla' and missing == ['sla_id']:
            raise AiToolError(
                'Prepare Notice for Deadline requires an SLA ID. List overdue deadlines first, then use the Deadline ID as the SLA ID.',
                422,
            )
        if tool.name == 'resolve_sla_deadline' and missing == ['sla_id']:
            raise AiToolError(
                'Resolve Compliance Deadline requires an SLA ID. List overdue deadlines first, then use the Deadline ID as the SLA ID.',
                422,
            )
        if tool.name == 'get_sla_deadline_detail' and missing == ['deadline_id']:
            raise AiToolError(
                'Inspect Deadline Detail requires a Deadline ID (e.g. deadline_id=10).',
                422,
            )
        raise AiToolError(f'{tool.name} requires: {", ".join(missing)}.', 422)


def _validate_scoped_args(tool, args, user):
    """Re-check object IDs before AI tools run or enter pending confirmation."""
    if tool.name in {'list_overdue_slas', 'list_notices', 'query_projects', 'query_requirements'}:
        _resolve_lgu_filter(args, user, empty_if_missing=tool.name in {'query_projects', 'query_requirements'})
    if tool.name == 'query_projects':
        _resolve_program_filter(args)
        if 'project_ids' in args:
            ids = args['project_ids']
            if not isinstance(ids, list) or len(ids) > 100 or any(
                    not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in ids):
                raise AiToolError('project_ids must be a list of up to 100 positive integers.', 422)
    if tool.name == 'get_project_overview':
        _ensure_project_arg(args, 'project_id', user, required=True)
    elif tool.name in {'list_overdue_slas', 'list_notices', 'list_monitoring_inspections', 'list_non_infra_monitoring_records', 'list_beneficiary_evidence_records'}:
        _ensure_project_arg(args, 'project_id', user)

    if tool.name in {'resolve_sla_deadline', 'generate_notice_for_sla'}:
        _ensure_sla_arg(args, 'sla_id', user, required=True, assert_movement=True)
    elif tool.name == 'get_sla_deadline_detail':
        sla_key = 'deadline_id' if args.get('deadline_id') not in (None, '') else 'sla_id'
        _ensure_sla_arg(args, sla_key, user, required=True)
    elif tool.name == 'list_notices':
        _ensure_sla_arg(args, 'trigger_sla_id', user)

    if tool.name in {'push_requirement_handoff', 'create_requirement_comment', 'upload_evidence_from_attachment'}:
        _ensure_requirement_arg(args, 'requirement_id', user, required=True, assert_movement=True)
    elif tool.name == 'get_requirement_detail':
        _ensure_requirement_arg(args, 'requirement_id', user, required=True)
    elif tool.name == 'query_requirements':
        _ensure_requirement_arg(args, 'requirement_id', user, required=False)

    if tool.name == 'restore_database_backup':
        from app.services.backup_service import REQUIRED_RESTORE_CONFIRMATION_PHRASE
        phrase = str(args.get('confirmation_phrase') or '').strip()
        if phrase != REQUIRED_RESTORE_CONFIRMATION_PHRASE:
            raise AiToolError(
                f"Invalid confirmation phrase. You must provide '{REQUIRED_RESTORE_CONFIRMATION_PHRASE}'.",
                422,
            )
        args['confirmation_display'] = {
            'backup_id': args.get('backup_id'),
            'target_db': args.get('target_db') or 'Production Primary',
            'notice': 'CRITICAL: This will overwrite the database with data from the specified backup snapshot.',
        }

    if tool.name == 'upload_evidence_from_attachment':
        from app.models import ProjectRequirement, Project, StoredObject, Submission
        from app.extensions import db
        requirement_id = int(args['requirement_id'])
        req = db.session.get(ProjectRequirement, requirement_id)
        if not req or not req.is_active:
            raise AiToolError(f'Requirement #{requirement_id} not found or inactive.', 404)
        if req.status == 'compliant' or req.workflow_status in ('approved', 'staff_approved'):
            raise AiToolError(f'Requirement #{requirement_id} is already compliant and approved. Movement or new evidence upload is not allowed.', 409)
        proj = db.session.get(Project, req.project_id) if req else None
        lgu_name = proj.lgu.name if proj and proj.lgu else ''
        attachment_id = int(args['attachment_id'])
        stored = db.session.get(StoredObject, attachment_id)
        if not stored:
            raise AiToolError('Attachment not found.', 404)
        if stored.uploaded_by is not None and stored.uploaded_by != user.id:
            raise AiToolError('You can only attach files that you uploaded.', 403)
        
        prior_count = Submission.query.filter_by(project_requirement_id=req.id).count()
        new_version_number = prior_count + 1
        
        workflow_impact = "Document intake into official review workflow."
        if req.workflow_status == 'returned_for_revision':
            from_wf = _format_requirement_status_label('returned_for_revision')
            to_wf = _format_requirement_status_label('resubmitted')
            workflow_impact = f"Resubmits requirement (transitions from {from_wf} to {to_wf} as Version {new_version_number})."
        elif req.status == 'pending':
            to_wf = _format_requirement_status_label('under_review')
            workflow_impact = f"Submits initial evidence (moves requirement to {to_wf} as Version {new_version_number})."
        else:
            status_label = _format_requirement_status_label(req.status) or (req.status or 'N/A')
            workflow_impact = f"Submits new documentary evidence as Version {new_version_number} (status remains {status_label})."

        args['confirmation_display'] = {
            'file_name': stored.original_filename,
            'file_type': stored.content_type,
            'file_size_bytes': stored.size_bytes,
            'project_id': proj.id if proj else None,
            'project_name': proj.project_name if proj else None,
            'lgu_name': lgu_name,
            'requirement_id': req.id,
            'requirement_name': req.requirement_name,
            'annex_reference': req.annex_reference,
            'phase_name': req.phase_name or (proj.current_phase if proj else None) or 'N/A',
            'submission_version': f"Version {new_version_number}",
            'action_impact': workflow_impact,
            'document_structure': args.get('document_structure'),
            'readability': args.get('readability'),
            'advisory_observations': args.get('advisory_observations'),
            'notice': f'This creates a NEW submission for the requirement in {_get_app_name()}. It does NOT automatically approve or mark the requirement compliant.',
        }

    if tool.name == 'push_requirement_handoff':
        from app.models import ProjectRequirement, Project
        from app.extensions import db
        req = db.session.get(ProjectRequirement, int(args['requirement_id']))
        proj = db.session.get(Project, req.project_id) if req else None
        args['confirmation_display'] = {
            'requirement_name': req.requirement_name if req else None,
            'project_name': proj.project_name if proj else None,
            'notice': 'This uploads the approved requirement evidence to the regional handoff repository.',
        }

    if tool.name == 'generate_notice_for_sla':
        from app.models import SlaDeadline, ProjectRequirement, Project
        from app.extensions import db
        sla = db.session.get(SlaDeadline, int(args['sla_id']))
        req = db.session.get(ProjectRequirement, sla.project_requirement_id) if sla and sla.project_requirement_id else None
        proj = db.session.get(Project, req.project_id) if req else (db.session.get(Project, sla.project_id) if sla and sla.project_id else None)
        args['confirmation_display'] = {
            'stage': sla.deadline_type if sla else None,
            'deadline_date': sla.deadline_date.isoformat() if sla and sla.deadline_date else None,
            'requirement_name': req.requirement_name if req else None,
            'project_name': proj.project_name if proj else None,
            'notice': 'This generates the next escalation or reminder notice for this overdue compliance deadline.',
        }

    if tool.name == 'resolve_sla_deadline':
        from app.models import SlaDeadline, ProjectRequirement, Project
        from app.extensions import db
        sla = db.session.get(SlaDeadline, int(args['sla_id']))
        req = db.session.get(ProjectRequirement, sla.project_requirement_id) if sla and sla.project_requirement_id else None
        proj = db.session.get(Project, req.project_id) if req else (db.session.get(Project, sla.project_id) if sla and sla.project_id else None)
        args['confirmation_display'] = {
            'stage': sla.deadline_type if sla else None,
            'deadline_date': sla.deadline_date.isoformat() if sla and sla.deadline_date else None,
            'requirement_name': req.requirement_name if req else None,
            'project_name': proj.project_name if proj else None,
            'notice': 'This marks the working-day deadline as resolved in the system.',
        }

    if tool.name == 'create_requirement_comment':
        from app.models import ProjectRequirement, Project
        from app.extensions import db
        req = db.session.get(ProjectRequirement, int(args['requirement_id']))
        proj = db.session.get(Project, req.project_id) if req else None
        args['confirmation_display'] = {
            'requirement_name': req.requirement_name if req else None,
            'project_name': proj.project_name if proj else None,
            'comment_type': args.get('comment_type'),
            'visibility': args.get('visibility'),
            'comment': args.get('body'),
            'notice': 'This posts a permanent comment/update on the project requirement.',
        }

    # Wave A Scoped Arguments
    if tool.name == 'update_lgu':
        lgu_id = _int_arg(args, 'lgu_id')
        if lgu_id is None:
            raise AiToolError('lgu_id is required.', 422)
        try:
            lgu_service.get_lgu(lgu_id, user_id=user.id)
        except lgu_service.LguError as exc:
            _raise_scoped_tool_error(exc)

    elif tool.name == 'update_cluster':
        cluster_id = _int_arg(args, 'cluster_id')
        if cluster_id is None:
            raise AiToolError('cluster_id is required.', 422)
        try:
            lgu_service.get_cluster(cluster_id, user_id=user.id)
        except lgu_service.LguError as exc:
            _raise_scoped_tool_error(exc)

    elif tool.name in ('update_program', 'create_program_cycle'):
        program_id = _int_arg(args, 'program_id')
        if program_id is None:
            raise AiToolError('program_id is required.', 422)
        try:
            program_service.get_program(program_id)
        except program_service.ProgramError as exc:
            _raise_scoped_tool_error(exc)

    elif tool.name == 'update_program_cycle':
        cycle_id = _int_arg(args, 'cycle_id')
        if cycle_id is None:
            raise AiToolError('cycle_id is required.', 422)
        try:
            program_service.get_program_cycle(cycle_id)
        except program_service.ProgramError as exc:
            _raise_scoped_tool_error(exc)

    elif tool.name == 'create_project':
        _ensure_lgu_arg(args, 'lgu_id', user, required=True)
        _validate_project_tracking_dates(args)
        from app.api.projects.schemas import VALID_SUBAYBAYAN_ENROLLMENT_STATUSES
        status = args.get('subaybayan_enrollment_status')
        if status not in (None, '') and status not in VALID_SUBAYBAYAN_ENROLLMENT_STATUSES:
            raise AiToolError('Invalid subaybayan_enrollment_status. Must be one of: '
                              + ', '.join(VALID_SUBAYBAYAN_ENROLLMENT_STATUSES), 422)
        program_id = _int_arg(args, 'program_id')
        if program_id is None:
            raise AiToolError('program_id is required.', 422)
        try:
            program = program_service.get_program(program_id)
            args['project_kind'] = project_service.validate_project_kind_for_program_type(
                program.program_type, args.get('project_kind'))
        except program_service.ProgramError as exc:
            _raise_scoped_tool_error(exc)
        except project_service.ProjectError as exc:
            _raise_scoped_tool_error(exc)

        fiscal_year = _int_arg(args, 'fiscal_year')
        cycle_id = _int_arg(args, 'program_cycle_id')
        from app.extensions import db
        from app.models import ProgramCycle
        if cycle_id is not None:
            cycle = db.session.get(ProgramCycle, cycle_id)
            if not cycle:
                raise AiToolError('Program cycle not found.', 404)
            if cycle.program_id != program_id:
                raise AiToolError('Program cycle does not belong to the selected program.', 422)
            if fiscal_year and cycle.fiscal_year != fiscal_year:
                raise AiToolError('Fiscal year must match the selected program cycle.', 422)
            if not cycle.is_active:
                raise AiToolError(f'The program cycle for FY {cycle.fiscal_year} is inactive.', 422)
        elif fiscal_year is not None:
            cycles_for_year = (
                ProgramCycle.query
                .filter_by(program_id=program_id, fiscal_year=fiscal_year)
                .order_by(ProgramCycle.name.asc(), ProgramCycle.id.asc())
                .all()
            )
            if cycles_for_year:
                active_cycles = [c for c in cycles_for_year if c.is_active]
                if len(active_cycles) == 1:
                    args['program_cycle_id'] = active_cycles[0].id
                elif len(active_cycles) > 1:
                    raise AiToolError(
                        f'Multiple active program cycles exist for FY {fiscal_year}. Please specify a program cycle.',
                        422,
                    )
                else:
                    raise AiToolError(
                        f'The program cycle for FY {fiscal_year} is inactive.',
                        422,
                    )
            else:
                raise AiToolError(
                    f'No program cycle found for Program #{program_id} in FY {fiscal_year}. Projects require an active program cycle.',
                    422,
                )

    elif tool.name in ('update_project_metadata', 'update_project_budget'):
        _ensure_project_arg(args, 'project_id', user, required=True, assert_movement=True)

    elif tool.name in (
        'create_monthly_progress_report',
        'create_form3_request',
        'create_non_infra_monitoring_record',
        'create_beneficiary_evidence_record',
        'create_monitoring_inspection',
    ):
        _ensure_project_arg(args, 'project_id', user, required=True, assert_movement=True)

    # Wave B Scoped Arguments
    elif tool.name == 'update_project_lgu_assignment':
        _ensure_project_arg(args, 'project_id', user, required=True, assert_movement=True)
        new_lgu_id = _int_arg(args, 'lgu_id')
        if new_lgu_id is None:
            raise AiToolError('lgu_id is required.', 422)
        from app.extensions import db
        from app.models import LguProfile
        target_lgu = db.session.get(LguProfile, new_lgu_id)
        if not target_lgu:
            raise AiToolError('Target LGU not found.', 404)
        if not target_lgu.is_active:
            raise AiToolError(f"Target LGU '{target_lgu.name}' is inactive.", 422)
        try:
            access_service.ensure_lgu_access(target_lgu, user.id)
        except access_service.AccessError as exc:
            _raise_scoped_tool_error(exc)
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        if project.lgu_id == target_lgu.id:
            raise AiToolError(f"Project #{project.id} is already assigned to {target_lgu.name}.", 422)
        try:
            project_service._assert_project_identity_available(
                lgu_id=target_lgu.id,
                program_id=project.program_id,
                fiscal_year=project.fiscal_year,
                project_name=project.project_name,
                program_cycle_id=project.program_cycle_id,
                source_project_code=project.source_project_code,
                exclude_project_id=project.id,
            )
        except project_service.ProjectError as exc:
            _raise_scoped_tool_error(exc)

    elif tool.name == 'update_project_cycle':
        _ensure_project_arg(args, 'project_id', user, required=True, assert_movement=True)
        new_cycle_id = _int_arg(args, 'program_cycle_id')
        if new_cycle_id is None:
            raise AiToolError('program_cycle_id is required.', 422)
        from app.extensions import db
        from app.models import ProgramCycle
        target_cycle = db.session.get(ProgramCycle, new_cycle_id)
        if not target_cycle:
            raise AiToolError('Program cycle not found.', 404)
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        if target_cycle.program_id != project.program_id:
            raise AiToolError(
                f"Program cycle #{target_cycle.id} belongs to Program #{target_cycle.program_id}, but project belongs to Program #{project.program_id}. Programs cannot be changed after project creation.",
                422,
            )
        if not target_cycle.is_active:
            raise AiToolError(f"Cannot reassign project to inactive program cycle #{target_cycle.id} ('{target_cycle.name}').", 422)
        if project.program_cycle_id == target_cycle.id:
            raise AiToolError(f"Project #{project.id} is already assigned to program cycle #{target_cycle.id} ('{target_cycle.name}').", 422)
        try:
            project_service._assert_project_identity_available(
                lgu_id=project.lgu_id,
                program_id=project.program_id,
                fiscal_year=target_cycle.fiscal_year,
                project_name=project.project_name,
                program_cycle_id=target_cycle.id,
                source_project_code=project.source_project_code,
                exclude_project_id=project.id,
            )
        except project_service.ProjectError as exc:
            _raise_scoped_tool_error(exc)

    elif tool.name == 'update_project_status':
        _ensure_project_arg(args, 'project_id', user, required=True, assert_movement=True)
        raw_status = args.get('overall_status')
        if not raw_status:
            raise AiToolError('overall_status is required.', 422)
        from app.services.project_status import normalize_project_status
        norm_status = normalize_project_status(raw_status, default=raw_status)
        if str(norm_status).strip().lower() == 'completed':
            raise AiToolError('Project completion must be processed through the completion closeout service.', 422)
        valid_operational_statuses = ('not_yet_started', 'ongoing', 'suspended')
        if norm_status not in valid_operational_statuses:
            raise AiToolError(f"Invalid overall_status. Must be one of: {', '.join(valid_operational_statuses)}.", 422)
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        if project.overall_status == norm_status:
            raise AiToolError(f"Project #{project.id} is already in '{norm_status}' status.", 409)
        args['overall_status'] = norm_status

    elif tool.name == 'update_project_schedule':
        _ensure_project_arg(args, 'project_id', user, required=True, assert_movement=True)
        _validate_project_tracking_dates(args)
        schedule_fields = PROJECT_SCHEDULE_DATES
        provided = [f for f in schedule_fields if f in args and (args[f] is not None or f in PROJECT_TRACKING_DATES)]
        if not provided:
            raise AiToolError(f"At least one schedule date must be provided: {', '.join(schedule_fields)}.", 422)
        for f in provided:
            val = args[f]
            try:
                project_service._parse_date(val)
            except Exception as exc:
                raise AiToolError(f"Invalid date format for '{f}': {val}. Expected YYYY-MM-DD.", 422) from exc
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        reviewed_changes = (args.get('confirmation_display') or {}).get('changes', {})
        if any(field in reviewed_changes for field in PROJECT_TRACKING_DATES):
            # Hold the reviewed record through the canonical update/commit and
            # refresh values cached when the request first checked its scope.
            from app.extensions import db
            from app.models import Project
            db.session.query(Project).filter_by(id=project.id).populate_existing().with_for_update().one()
            _ensure_project_arg(args, 'project_id', user, required=True, assert_movement=True)
        for field in PROJECT_TRACKING_DATES:
            if field in reviewed_changes:
                current = getattr(project, field)
                current = current.isoformat() if current else None
                if current != reviewed_changes[field]['from']:
                    raise AiToolError('Project tracking dates changed after review. Please prepare a new review.', 409)
        t_start = project_service._parse_date(args.get('target_start_date')) if args.get('target_start_date') else project.target_start_date
        t_end = project_service._parse_date(args.get('target_end_date')) if args.get('target_end_date') else project.target_end_date
        if t_start and t_end and t_end < t_start:
            raise AiToolError('target_end_date cannot be earlier than target_start_date.', 422)
        a_start = project_service._parse_date(args.get('actual_start_date')) if args.get('actual_start_date') else project.actual_start_date
        a_end = project_service._parse_date(args.get('actual_end_date')) if args.get('actual_end_date') else project.actual_end_date
        if a_start and a_end and a_end < a_start:
            raise AiToolError('actual_end_date cannot be earlier than actual_start_date.', 422)

    elif tool.name == 'create_sla_deadline':
        _ensure_project_arg(args, 'project_id', user, required=True, assert_movement=True)
        deadline_type = _text_arg(args, 'deadline_type')
        if not deadline_type or deadline_type not in sla_service.VALID_DEADLINE_TYPES:
            raise AiToolError(f"Invalid deadline_type. Must be one of: {', '.join(sla_service.VALID_DEADLINE_TYPES)}.", 422)
        trigger_date = args.get('trigger_date')
        deadline_date = args.get('deadline_date')
        if not trigger_date or not deadline_date:
            raise AiToolError('trigger_date and deadline_date are required.', 422)
        try:
            trig_dt = sla_service._parse_datetime(trigger_date)
            dl_dt = sla_service._parse_datetime(deadline_date)
        except Exception as exc:
            raise AiToolError(f"Invalid date format for trigger_date or deadline_date: {exc}.", 422) from exc
        if sla_service._to_aware_datetime(dl_dt) <= sla_service._to_aware_datetime(trig_dt):
            raise AiToolError('deadline_date must be after trigger_date.', 422)
        req_id = _int_arg(args, 'project_requirement_id')
        if req_id:
            _ensure_requirement_arg(args, 'project_requirement_id', user, required=True, assert_movement=True)
            from app.extensions import db
            from app.models import ProjectRequirement, SlaDeadline
            req = db.session.get(ProjectRequirement, req_id)
            if req.project_id != int(args['project_id']):
                raise AiToolError('Project requirement does not belong to this project.', 422)
            if req.status == 'compliant':
                raise AiToolError('Cannot create SLA deadline for a compliant requirement.', 422)
            if project_service.is_valid_waived_requirement(req):
                raise AiToolError('Cannot create SLA deadline for a waived requirement.', 422)
            existing = SlaDeadline.query.filter(
                SlaDeadline.project_requirement_id == req_id,
                SlaDeadline.is_resolved == False,
            ).first()
            if existing:
                raise AiToolError('An unresolved working-day deadline already exists for this requirement.', 409)

    elif tool.name == 'create_notice_draft':
        _ensure_project_arg(args, 'project_id', user, required=True, assert_movement=True)
        if args.get('status') in ('sent', 'released'):
            raise AiToolError(f'Notices cannot be created in sent or released status. Official release and dispatch are governance actions restricted to the {_get_app_name()} web interface.', 422)
        args['status'] = 'draft'
        args['notice_type'] = 'annex_e'
        if args.get('trigger_sla_id'):
            _ensure_sla_arg(args, 'trigger_sla_id', user, required=False, assert_movement=True)
        if args.get('trigger_project_requirement_id'):
            _ensure_requirement_arg(args, 'trigger_project_requirement_id', user, required=False, assert_movement=True)

    elif tool.name == 'preview_import':
        if not user or user.role != 'admin':
            raise AiToolError('Administrative permissions required. Only administrators can preview or perform imports.', 403)
        raw_target = str(args.get('target') or '').strip().lower()
        if raw_target in ('users', 'user', 'accounts', 'internal users'):
            raise AiToolError(
                'Batch import of user accounts involves sensitive authorization controls and must be performed directly through the Admin Batch Import UI.',
                422,
            )

    elif tool.name == 'commit_import':
        if not user or user.role != 'admin':
            raise AiToolError('Administrative permissions required. Only administrators can preview or perform imports.', 403)
        raw_target = str(args.get('target') or '').strip().lower()
        if raw_target in ('users', 'user', 'accounts', 'internal users'):
            raise AiToolError(
                'Batch import of user accounts involves sensitive authorization controls and must be performed directly through the Admin Batch Import UI.',
                422,
            )
        batch_id = _int_arg(args, 'batch_id')
        attachment_id = _int_arg(args, 'attachment_id')
        if not batch_id and not attachment_id:
            raise AiToolError('attachment_id or batch_id is required to commit an import.', 422)

    elif tool.name == 'create_user':
        if not user or user.role != 'admin':
            raise AiToolError('Administrative permissions required. Only administrators can create user accounts.', 403)
        target_role = str(args.get('role') or '').strip().lower()
        if target_role in ('system_admin', 'system administrator', 'sysadmin'):
            raise AiToolError('Operational Admins cannot manage System Administrator (System Admin) accounts.', 403)
        if target_role not in ('admin', 'staff', 'field_officer'):
            raise AiToolError(f"Invalid role '{target_role}'. Allowed roles: admin, staff, field_officer.", 422)
        args['role'] = target_role

        disallowed = {'password', 'plaintext_password', 'is_active', 'must_change_password',
                      'token_version', 'mfa_enabled', 'mfa_secret', 'mfa_type',
                      'can_approve_technical_documents', 'can_close_management_actions'}
        for f in disallowed:
            if f in args and args[f] is not None:
                raise AiToolError(f"Field '{f}' cannot be set through the Smart Assistant. Security and role controls must be managed through the {_get_app_name()} Admin interface.", 422)

        email = str(args.get('email') or '').strip().lower()
        if not email or '@' not in email:
            raise AiToolError('A valid email address is required.', 422)
        args['email'] = email

        from app.models import User, LguCluster, LguProfile
        from app.extensions import db
        from sqlalchemy import func
        existing = User.query.filter(func.lower(func.trim(User.email)) == email).first()
        if existing:
            raise AiToolError('Email already registered.', 409)

        cluster_ids = args.get('cluster_ids') or []
        lgu_ids = args.get('lgu_ids') or []
        if isinstance(cluster_ids, (int, str)):
            cluster_ids = [cluster_ids]
        if isinstance(lgu_ids, (int, str)):
            lgu_ids = [lgu_ids]

        try:
            cluster_ids = [int(c) for c in cluster_ids]
        except (ValueError, TypeError):
            raise AiToolError('cluster_ids must be an array of integers.', 422)
        try:
            lgu_ids = [int(l) for l in lgu_ids]
        except (ValueError, TypeError):
            raise AiToolError('lgu_ids must be an array of integers.', 422)

        if target_role == 'staff':
            if not cluster_ids:
                raise AiToolError('Staff accounts must be assigned to at least one LGU cluster.', 422)
            if lgu_ids:
                raise AiToolError('Staff accounts must be scoped by cluster, not by specific LGUs.', 422)
            for cid in cluster_ids:
                if not db.session.get(LguCluster, cid):
                    raise AiToolError(f'Cluster {cid} not found.', 404)
        elif target_role == 'field_officer':
            if not lgu_ids:
                raise AiToolError('Field officer accounts must be assigned to at least one LGU.', 422)
            if cluster_ids:
                raise AiToolError('Field officer accounts must be assigned to specific LGUs, not clusters.', 422)
            for lid in lgu_ids:
                if not db.session.get(LguProfile, lid):
                    raise AiToolError(f'LGU {lid} not found.', 404)
        elif target_role == 'admin':
            if lgu_ids:
                raise AiToolError('Admins can be province-wide or cluster-scoped, but not LGU-scoped.', 422)
            for cid in cluster_ids:
                if not db.session.get(LguCluster, cid):
                    raise AiToolError(f'Cluster {cid} not found.', 404)

        args['cluster_ids'] = cluster_ids
        args['lgu_ids'] = lgu_ids

    elif tool.name == 'update_user_profile':
        if not user or user.role != 'admin':
            raise AiToolError('Administrative permissions required. Only administrators can update user profiles.', 403)
        user_id = _int_arg(args, 'user_id')
        if not user_id:
            raise AiToolError('user_id is required.', 422)

        from app.models import User
        from app.extensions import db
        from sqlalchemy import func
        target = db.session.get(User, user_id)
        if not target:
            raise AiToolError(f'User #{user_id} not found.', 404)
        if target.role == 'system_admin':
            raise AiToolError('Operational Admins cannot manage System Administrator (System Admin) accounts.', 403)

        disallowed = {'password', 'role', 'is_active', 'must_change_password',
                      'token_version', 'mfa_enabled', 'mfa_secret', 'mfa_type',
                      'cluster_ids', 'lgu_ids', 'can_approve_technical_documents',
                      'can_close_management_actions'}
        for f in disallowed:
            if f in args and args[f] is not None:
                raise AiToolError(f"Field '{f}' cannot be updated through the Smart Assistant. Security and role controls must be managed through the {_get_app_name()} Admin interface.", 422)

        safe_fields = {'first_name', 'last_name', 'email'}
        provided_safe = {f: args[f] for f in safe_fields if f in args and args[f] is not None and str(args[f]).strip()}
        if not provided_safe:
            raise AiToolError('At least one profile field (first_name, last_name, email) must be provided for update.', 422)

        if 'email' in provided_safe:
            new_email = str(provided_safe['email']).strip().lower()
            if '@' not in new_email:
                raise AiToolError('Invalid email format.', 422)
            existing = User.query.filter(
                func.lower(func.trim(User.email)) == new_email,
                User.id != target.id,
            ).first()
            if existing:
                raise AiToolError('Email already in use.', 409)
            args['email'] = new_email

    # Phase 9E: Scoped arguments for bulk project operations
    if tool.operation_type == 'bulk_update':
        from app.services import bulk_project_service
        selectors, updates = _extract_bulk_tool_inputs(tool.name, args)

        if 'target_ids' in args and args['target_ids']:
            selectors['project_ids'] = args['target_ids']

        try:
            targets = bulk_project_service.resolve_bulk_project_targets(selectors, user_id=user.id)
            if not targets:
                raise AiToolError("No matching projects found for the specified selectors.", 404)

            if tool.name == 'bulk_update_project_metadata':
                change_set = bulk_project_service.calculate_project_metadata_changes(targets, updates, user_id=user.id)
            elif tool.name == 'bulk_update_project_schedule':
                change_set = bulk_project_service.calculate_project_schedule_changes(targets, updates, user_id=user.id)
            elif tool.name == 'bulk_update_project_status':
                change_set = bulk_project_service.calculate_project_status_changes(targets, updates, user_id=user.id)
            else:
                raise AiToolError(f"Unsupported bulk operation: {tool.name}", 422)

            args['selectors'] = selectors
            args['updates'] = change_set['updates']
            args['target_ids'] = change_set['target_ids']
            if not args.get('preview_fingerprint'):
                args['preview_fingerprint'] = change_set['preview_fingerprint']
            args['_bulk_change_set'] = change_set

        except bulk_project_service.BulkProjectError as exc:
            raise AiToolError(exc.message, exc.status_code)


def _extract_bulk_tool_inputs(tool_name, args):
    from app.services import bulk_project_service
    selectors = {}
    if isinstance(args.get('selectors'), dict):
        selectors.update(args['selectors'])
    for k in ('project_ids', 'lgu_id', 'cluster_id', 'program_id', 'program_cycle_id', 'fiscal_year', 'project_status', 'project_kind'):
        if k in args and args[k] is not None and k not in selectors:
            selectors[k] = args[k]

    updates = {}
    if isinstance(args.get('updates'), dict):
        updates.update(args['updates'])

    if tool_name == 'bulk_update_project_metadata':
        for k in bulk_project_service.ALLOWED_BULK_METADATA_FIELDS:
            if k in args and args[k] is not None and k not in updates:
                updates[k] = args[k]
    elif tool_name == 'bulk_update_project_schedule':
        for k in bulk_project_service.ALLOWED_BULK_SCHEDULE_FIELDS:
            if k in args and args[k] is not None and k not in updates:
                updates[k] = args[k]
    elif tool_name == 'bulk_update_project_status':
        for k in ('overall_status', 'status'):
            if k in args and args[k] is not None and 'overall_status' not in updates:
                updates['overall_status'] = args[k]

    return selectors, updates


def _prepare_confirmation_display(tool, args, user):
    if not tool.requires_confirmation:
        return
    if 'confirmation_display' in args and args['confirmation_display']:
        return

    from app.extensions import db
    from app.models import LguProfile, LguCluster, Program, ProgramCycle, Project

    if tool.name == 'create_lgu':
        args['confirmation_display'] = {
            'name': args.get('name'),
            'municipality': args.get('municipality'),
            'province': args.get('province') or 'Laguna',
            'cluster_id': args.get('cluster_id'),
            'mayor_name': args.get('mayor_name'),
            'contact_person': args.get('contact_person'),
            'notice': f'This registers a new municipal Local Government Unit (LGU) in {_get_app_name()}.',
        }

    elif tool.name == 'update_lgu':
        lgu = lgu_service.get_lgu(int(args['lgu_id']), user_id=user.id)
        diff = {}
        for f in tool.allowed_fields:
            if f in args and args[f] is not None:
                cur_val = getattr(lgu, f, None)
                if str(cur_val) != str(args[f]):
                    diff[f] = {'from': cur_val, 'to': args[f]}
        args['confirmation_display'] = {
            'lgu_id': lgu.id,
            'lgu_name': lgu.name,
            'changes': diff,
            'notice': f'This will update {len(diff)} field(s) on LGU {lgu.name}.',
        }

    elif tool.name == 'create_cluster':
        args['confirmation_display'] = {
            'name': args.get('name'),
            'description': args.get('description'),
            'notice': f'This creates a new LGU cluster in {_get_app_name()}.',
        }

    elif tool.name == 'update_cluster':
        cluster = lgu_service.get_cluster(int(args['cluster_id']), user_id=user.id)
        diff = {}
        for f in tool.allowed_fields:
            if f in args and args[f] is not None:
                cur_val = getattr(cluster, f, None)
                if str(cur_val) != str(args[f]):
                    diff[f] = {'from': cur_val, 'to': args[f]}
        args['confirmation_display'] = {
            'cluster_id': cluster.id,
            'cluster_name': cluster.name,
            'changes': diff,
            'notice': f'This will update cluster {cluster.name}.',
        }

    elif tool.name == 'create_program':
        args['confirmation_display'] = {
            'name': args.get('name'),
            'code': args.get('code'),
            'program_type': args.get('program_type'),
            'funding_agency': args.get('funding_agency'),
            'notice': f'This registers a new funding program in {_get_app_name()}.',
        }

    elif tool.name == 'update_program':
        program = program_service.get_program(int(args['program_id']))
        diff = {}
        for f in tool.allowed_fields:
            if f in args and args[f] is not None:
                cur_val = getattr(program, f, None)
                if str(cur_val) != str(args[f]):
                    diff[f] = {'from': cur_val, 'to': args[f]}
        args['confirmation_display'] = {
            'program_id': program.id,
            'program_name': program.name,
            'changes': diff,
            'notice': f'This will update funding program {program.name}.',
        }

    elif tool.name == 'create_program_cycle':
        program = program_service.get_program(int(args['program_id']))
        args['confirmation_display'] = {
            'program_id': program.id,
            'program_name': program.name,
            'name': args.get('name'),
            'fiscal_year': args.get('fiscal_year'),
            'cycle_code': args.get('cycle_code'),
            'notice': f'This creates a new program cycle ({args.get("name")}) for {program.name}.',
        }

    elif tool.name == 'update_program_cycle':
        cycle = program_service.get_program_cycle(int(args['cycle_id']))
        diff = {}
        for f in tool.allowed_fields:
            if f in args and args[f] is not None:
                cur_val = getattr(cycle, f, None)
                if str(cur_val) != str(args[f]):
                    diff[f] = {'from': cur_val, 'to': args[f]}
        args['confirmation_display'] = {
            'cycle_id': cycle.id,
            'cycle_name': cycle.name,
            'changes': diff,
            'notice': f'This will update program cycle {cycle.name}.',
        }

    elif tool.name == 'create_project':
        lgu = db.session.get(LguProfile, int(args['lgu_id']))
        prog = db.session.get(Program, int(args['program_id']))
        cycle = db.session.get(ProgramCycle, int(args['program_cycle_id'])) if args.get('program_cycle_id') else None
        budget = args.get('budget_amount')
        budget_str = f"₱{float(budget):,.2f}" if budget is not None else "Not specified"
        args['confirmation_display'] = {
            'project_name': args.get('project_name'),
            'lgu_id': args.get('lgu_id'),
            'lgu_name': lgu.name if lgu else None,
            'program_id': args.get('program_id'),
            'program_name': prog.name if prog else None,
            'program_cycle_id': cycle.id if cycle else None,
            'program_cycle_name': cycle.name if cycle else None,
            'cycle_code': cycle.cycle_code if cycle else None,
            'fiscal_year': args.get('fiscal_year'),
            'budget_amount': budget_str,
            **{field: args[field] for field in (*PROJECT_TRACKING_DATES, 'subaybayan_enrollment_status') if field in args},
            'notice': f'This creates a new project in {_get_app_name()} under the specified LGU and Program.',
        }

    elif tool.name == 'update_project_metadata':
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        diff = {}
        for f in tool.allowed_fields:
            if f in args and args[f] is not None:
                cur_val = getattr(project, f, None)
                if str(cur_val) != str(args[f]):
                    diff[f] = {'from': cur_val, 'to': args[f]}
        args['confirmation_display'] = {
            'project_id': project.id,
            'project_name': project.project_name,
            'changes': diff,
            'notice': f'This will update details on Project #{project.id} ({project.project_name}).',
        }

    elif tool.name == 'update_project_budget':
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        old_b = float(project.budget_amount or 0)
        new_b = float(args.get('budget_amount') or 0)
        delta = new_b - old_b
        args['confirmation_display'] = {
            'project_id': project.id,
            'project_name': project.project_name,
            'old_budget': f"₱{old_b:,.2f}",
            'new_budget': f"₱{new_b:,.2f}",
            'budget_delta': f"{'+' if delta >= 0 else ''}₱{delta:,.2f}",
            'notes': args.get('notes'),
            'notice': f'CRITICAL: This updates the official project budget allocation in {_get_app_name()}.',
        }

    elif tool.name == 'update_project_lgu_assignment':
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        cur_lgu = db.session.get(LguProfile, project.lgu_id)
        cur_cluster = db.session.get(LguCluster, cur_lgu.cluster_id) if cur_lgu and cur_lgu.cluster_id else None
        target_lgu = db.session.get(LguProfile, int(args['lgu_id']))
        target_cluster = db.session.get(LguCluster, target_lgu.cluster_id) if target_lgu and target_lgu.cluster_id else None
        args['confirmation_display'] = {
            'project_id': project.id,
            'project_name': project.project_name,
            'current_lgu_id': cur_lgu.id if cur_lgu else None,
            'current_lgu_name': cur_lgu.name if cur_lgu else None,
            'current_cluster_id': cur_cluster.id if cur_cluster else None,
            'current_cluster_name': cur_cluster.name if cur_cluster else None,
            'new_lgu_id': target_lgu.id if target_lgu else None,
            'new_lgu_name': target_lgu.name if target_lgu else None,
            'new_cluster_id': target_cluster.id if target_cluster else None,
            'new_cluster_name': target_cluster.name if target_cluster else None,
            'notes': args.get('notes'),
            'notice': "This will change the project's operational LGU scope.",
        }

    elif tool.name == 'update_project_cycle':
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        prog = db.session.get(Program, project.program_id) if project.program_id else None
        cur_cycle = db.session.get(ProgramCycle, project.program_cycle_id) if project.program_cycle_id else None
        target_cycle = db.session.get(ProgramCycle, int(args['program_cycle_id']))
        args['confirmation_display'] = {
            'project_id': project.id,
            'project_name': project.project_name,
            'program_id': project.program_id,
            'program_name': prog.name if prog else None,
            'current_cycle_id': cur_cycle.id if cur_cycle else None,
            'current_cycle_name': cur_cycle.name if cur_cycle else None,
            'current_fiscal_year': project.fiscal_year,
            'new_cycle_id': target_cycle.id if target_cycle else None,
            'new_cycle_name': target_cycle.name if target_cycle else None,
            'new_fiscal_year': target_cycle.fiscal_year if target_cycle else None,
            'notes': args.get('notes'),
            'notice': f"This will reassign Project #{project.id} to program cycle '{target_cycle.name}' (FY {target_cycle.fiscal_year}).",
        }

    elif tool.name == 'update_project_status':
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        current_status_label = project_status_label(project.overall_status)
        new_status_label = project_status_label(args.get('overall_status'))
        args['confirmation_display'] = {
            'project_id': project.id,
            'project_name': project.project_name,
            'current_status': project.overall_status,
            'new_status': args.get('overall_status'),
            'notes': args.get('notes'),
            'notice': f"This will change the overall operational status of Project #{project.id} from '{current_status_label}' to '{new_status_label}'.",
        }

    elif tool.name == 'update_project_schedule':
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        diff = {}
        for f in PROJECT_SCHEDULE_DATES:
            if f in args and (args[f] is not None or f in PROJECT_TRACKING_DATES):
                cur_val = getattr(project, f, None)
                cur_str = cur_val.isoformat() if cur_val else None
                new_str = str(args[f]) if args[f] is not None else None
                if cur_str != new_str or f in PROJECT_TRACKING_DATES:
                    diff[f] = {'from': cur_str, 'to': new_str}
        args['confirmation_display'] = {
            'project_id': project.id,
            'project_name': project.project_name,
            'changes': diff,
            'notes': args.get('notes'),
            'notice': f"This will update milestone schedule dates on Project #{project.id} ({project.project_name}).",
        }

    elif tool.name == 'create_sla_deadline':
        from app.models import ProjectRequirement
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        req = db.session.get(ProjectRequirement, int(args['project_requirement_id'])) if args.get('project_requirement_id') else None
        args['confirmation_display'] = {
            'project_id': project.id,
            'project_name': project.project_name,
            'project_requirement_id': req.id if req else None,
            'requirement_name': req.requirement_name if req else None,
            'deadline_type': args.get('deadline_type'),
            'trigger_date': str(args.get('trigger_date')),
            'deadline_date': str(args.get('deadline_date')),
            'sla_working_days': args.get('sla_working_days'),
            'notes': args.get('notes'),
            'notice': f"This creates a {sla_service.format_deadline_type(args.get('deadline_type'))} compliance deadline for Project #{project.id}.",
        }

    elif tool.name == 'create_notice_draft':
        project = project_service.get_project(int(args['project_id']), user_id=user.id)
        lgu = db.session.get(LguProfile, project.lgu_id) if project.lgu_id else None
        args['confirmation_display'] = {
            'project_id': project.id,
            'project_name': project.project_name,
            'lgu_name': lgu.name if lgu else None,
            'notice_type': "Annex E - Notice of Deficiency",
            'status': "Draft (Not Released)",
            'trigger_sla_id': args.get('trigger_sla_id'),
            'trigger_project_requirement_id': args.get('trigger_project_requirement_id'),
            'title': args.get('title') or "Annex E - Notice of Deficiency",
            'notice': "This generates an official draft Notice of Deficiency (Annex E). No notice will be released, signed, or dispatched.",
        }

    elif tool.name == 'commit_import':
        from app.models import StoredObject, ImportBatch
        target = args.get('target') or 'data'
        batch_id = args.get('batch_id')
        attachment_id = args.get('attachment_id')
        batch = db.session.get(ImportBatch, int(batch_id)) if batch_id else None
        filename = args.get('filename')
        if not filename and attachment_id:
            stored = db.session.get(StoredObject, int(attachment_id))
            if stored:
                filename = stored.original_filename
        if not filename and batch_id:
            if batch:
                filename = batch.original_file_name
        is_wb = target in ('workbook', 'workbooks', 'project', 'projects', 'project_workbook') or bool(batch_id)
        args['confirmation_display'] = {
            'action_label': 'Confirm Import',
            'target': str(target).title(),
            'source_file': filename or 'Attached file',
            'batch_id': batch_id,
            'attachment_id': attachment_id,
            'preview_summary': batch.preview_summary if batch_id and batch else None,
            'confirm_similar_requirements': args.get('confirm_similar_requirements', False),
            'transaction_semantics': 'Whole-batch atomic commit' if is_wb else 'Row-level processing (valid rows committed individually)',
            'notice': (
                f"Confirming will commit the staged {target} import into {_get_app_name()}. "
                "No operational records have been saved. If the source, mapping or preview changes, a fresh review is required."
            ),
        }

    elif tool.name == 'create_user':
        from app.models import LguCluster, LguProfile
        from app.extensions import db
        from app.services import auth_service
        role_val = args.get('role', 'staff')
        role_label = auth_service.format_role(role_val)
        scope_desc = 'Province-wide operational authority'
        if args.get('cluster_ids'):
            cluster_names = [c.name for cid in args['cluster_ids'] if (c := db.session.get(LguCluster, cid))]
            scope_desc = f"Cluster Scope: {', '.join(cluster_names) if cluster_names else args['cluster_ids']}"
        elif args.get('lgu_ids'):
            lgu_names = [l.name for lid in args['lgu_ids'] if (l := db.session.get(LguProfile, lid))]
            scope_desc = f"LGU Scope: {', '.join(lgu_names) if lgu_names else args['lgu_ids']}"

        args['confirmation_display'] = {
            'action_label': 'Confirm User Creation',
            'full_name': f"{args.get('first_name', '')} {args.get('last_name', '')}".strip(),
            'email': args.get('email'),
            'role': role_label,
            'scope': scope_desc,
            'cluster_ids': args.get('cluster_ids') or [],
            'lgu_ids': args.get('lgu_ids') or [],
            'notice': 'No account has been created yet. Confirm to create this user.',
        }

    elif tool.name == 'update_user_profile':
        from app.models import User
        from app.extensions import db
        from app.services import auth_service
        target = db.session.get(User, int(args['user_id']))
        changes = {}
        for f in ('first_name', 'last_name', 'email'):
            if f in args and args[f] is not None:
                old_val = getattr(target, f, None) if target else None
                new_val = str(args[f]).strip()
                if old_val != new_val:
                    changes[f] = {'from': old_val, 'to': new_val}

        diff_lines = [f"{k}: {v['from']} → {v['to']}" for k, v in changes.items()]
        diff_summary = "\n".join(diff_lines) if diff_lines else "No field changes detected."

        args['confirmation_display'] = {
            'action_label': 'Confirm Profile Update',
            'user_id': target.id if target else int(args['user_id']),
            'user_name': target.full_name if target else None,
            'role': auth_service.format_role(target.role) if target else None,
            'changes': changes,
            'diff_summary': diff_summary,
            'notice': 'No changes have been made yet. Confirm to apply.',
        }

    elif tool.operation_type == 'bulk_update':
        change_set = args.get('_bulk_change_set') or {}
        target_count = change_set.get('target_count', len(args.get('target_ids') or []))
        changed_count = change_set.get('changed_count', 0)
        unchanged_count = change_set.get('unchanged_count', 0)
        updates = args.get('updates') or {}
        preview_fp = args.get('preview_fingerprint') or ''

        # Build formatted sample rows
        sample_rows = []
        for sample in change_set.get('changed_samples', []):
            diff_parts = []
            for field, d in sample.get('diff', {}).items():
                old_v = d.get('from') or '(empty)'
                new_v = d.get('to') or '(empty)'
                diff_parts.append(f"{field}: `{old_v}` → `{new_v}`")
            sample_rows.append(f"| #{sample['id']} | {sample.get('name', 'N/A')} | {'; '.join(diff_parts)} |")

        preview_lines = [
            "> [!IMPORTANT]",
            f"> Confirming will apply this update atomically to **{target_count}** selected project(s).",
            f"> - **Total Targets:** {target_count}",
            f"> - **Records Changing:** {changed_count}",
            f"> - **Already Up-to-Date (Idempotent):** {unchanged_count}",
        ]
        if preview_fp:
            preview_lines.append(f"> - **Preview Fingerprint:** `{preview_fp[:16]}...`")
        if change_set.get('alias_note'):
            preview_lines.append(f"> - **Note:** {change_set['alias_note']}")
        preview_lines.extend([
            "",
            "**Proposed Updates:**",
        ])
        for k, v in updates.items():
            preview_lines.append(f"- **{k}**: `{v}`")

        if sample_rows:
            preview_lines.extend([
                "",
                "**Sample Affected Projects (First 5):**",
                "| ID | Project Name | Changes |",
                "|---|---|---|",
            ] + sample_rows)

        preview_markdown = "\n".join(preview_lines)

        args['confirmation_display'] = {
            'action_label': f"Confirm Update for {target_count} Projects",
            'operation': tool.name,
            'target_count': target_count,
            'changed_count': changed_count,
            'unchanged_count': unchanged_count,
            'blocked_count': 0,
            'target_ids': args.get('target_ids') or [],
            'updates': updates,
            'preview_fingerprint': preview_fp,
            'preview_markdown': preview_markdown,
            'notice': f"Confirming will apply this update atomically to {target_count} selected project(s) with row-level locks and full audit logging. No changes have been saved yet.",
        }


def _ensure_project_arg(args, key, user, required=False, assert_movement=False):
    project_id = _int_arg(args, key)
    if project_id is None:
        if required:
            raise AiToolError(f'{key} is required.', 422)
        return None
    try:
        project = project_service.get_project(project_id, user_id=user.id)
        if assert_movement and project:
            access_service.assert_project_movement_allowed(project)
        return project
    except (project_service.ProjectError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _ensure_lgu_arg(args, key, user, required=False):
    lgu_id = _int_arg(args, key)
    if lgu_id is None:
        if required:
            raise AiToolError(f'{key} is required.', 422)
        return None
    try:
        return access_service.ensure_lgu_access(lgu_id, user.id)
    except access_service.AccessError as exc:
        _raise_scoped_tool_error(exc)


def _ensure_cluster_arg(args, key, user, required=False):
    cluster_id = _int_arg(args, key)
    if cluster_id is None:
        if required:
            raise AiToolError(f'{key} is required.', 422)
        return None
    try:
        return access_service.ensure_cluster_access(cluster_id, user.id)
    except access_service.AccessError as exc:
        _raise_scoped_tool_error(exc)


def _ensure_sla_arg(args, key, user, required=False, assert_movement=False):
    sla_id = _int_arg(args, key)
    if sla_id is None:
        if required:
            raise AiToolError(f'{key} is required.', 422)
        return
    try:
        deadline = sla_service.get_sla_deadline(sla_id, user_id=user.id)
        if assert_movement and deadline:
            access_service.assert_project_movement_allowed(deadline.project_id)
    except (sla_service.SlaError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _ensure_requirement_arg(args, key, user, required=False, assert_movement=False):
    requirement_id = _int_arg(args, key)
    if requirement_id is None:
        if required:
            raise AiToolError(f'{key} is required.', 422)
        return
    try:
        req = access_service.ensure_project_requirement_access(requirement_id, user.id)
        if assert_movement and req:
            access_service.assert_project_requirement_movement_allowed(req)
    except access_service.AccessError as exc:
        _raise_scoped_tool_error(exc)


def _raise_scoped_tool_error(exc):
    raise AiToolError(
        getattr(exc, 'message', 'You do not have permission to access this resource.'),
        getattr(exc, 'status_code', 403),
    ) from exc


def _int_arg(args, key, default=None):
    value = args.get(key, default)
    if value in (None, ''):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AiToolError(f'{key} must be an integer.', 422) from exc


def _bool_arg(args, key, default=None):
    value = args.get(key, default)
    if value in (None, ''):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {'true', '1', 'yes', 'on'}:
        return True
    if text in {'false', '0', 'no', 'off'}:
        return False
    raise AiToolError(f'{key} must be boolean-like.', 422)


def _text_arg(args, key, default=None):
    value = args.get(key, default)
    if value is None:
        return default
    return str(value).strip() or default


def _page_args(args, default_per_page=10, max_per_page=20):
    return {
        'page': max(_int_arg(args, 'page', 1) or 1, 1),
        'per_page': min(max(_int_arg(args, 'per_page', default_per_page) or default_per_page, 1), max_per_page),
    }


def _table_result(title, rows, columns, summary=None, meta=None):
    return {
        'display_type': 'table',
        'title': title,
        'summary': summary or '',
        'columns': columns,
        'rows': rows,
        'meta': meta or {},
        'detail': meta or {},
    }


def _metric_result(title, metrics, summary=None, detail=None):
    return {
        'display_type': 'metrics',
        'title': title,
        'summary': summary or '',
        'metrics': metrics,
        'detail': detail or {},
    }


def _detail_result(title, detail, summary=None):
    return {
        'display_type': 'detail',
        'title': title,
        'summary': summary or '',
        'detail': detail,
    }


def _tool_search_projects(args, user):
    paging = _page_args(args)
    result = project_service.list_projects(
        search=_text_arg(args, 'search'),
        lgu_id=_int_arg(args, 'lgu_id'),
        program_id=_int_arg(args, 'program_id'),
        fiscal_year=_int_arg(args, 'fiscal_year'),
        program_cycle_id=_int_arg(args, 'program_cycle_id'),
        current_phase=_text_arg(args, 'current_phase'),
        overall_status=_text_arg(args, 'overall_status'),
        page=paging['page'],
        per_page=paging['per_page'],
        user_id=user.id,
    )
    rows = result['projects']
    return _table_result(
        'Projects',
        rows,
        [
            {'key': 'id', 'label': 'ID'},
            {'key': 'project_name', 'label': 'Project'},
            {'key': 'fiscal_year', 'label': 'FY'},
            {'key': 'current_phase', 'label': 'Phase'},
            {'key': 'overall_status', 'label': 'Status'},
            {'key': 'source_project_code', 'label': 'Source Code'},
        ],
        summary=f'Found {result["total"]} project record(s).',
        meta={'total': result['total'], 'page': result['page'], 'pages': result['pages']},
    )


def _tool_global_search(args, user):
    per_type = min(max(_int_arg(args, 'per_type', 5) or 5, 1), 10)
    result = global_search_service.global_search(
        _text_arg(args, 'search') or _text_arg(args, 'q'),
        types=_text_arg(args, 'types'),
        per_type=per_type,
        fiscal_year=_int_arg(args, 'fiscal_year'),
        user_id=user.id,
    )
    rows = []
    for group in result['groups']:
        for item in group['items']:
            rows.append({
                'surface': group['label'],
                'type': item['type'],
                'id': item['id'],
                'title': item['title'],
                'subtitle': item['subtitle'],
                'url': item['url'],
                'search_score': item.get('search_score'),
            })
    return _table_result(
        'Global Search',
        rows,
        [
            {'key': 'surface', 'label': 'Surface'},
            {'key': 'title', 'label': 'Result'},
            {'key': 'subtitle', 'label': 'Context'},
            {'key': 'url', 'label': 'Open'},
        ],
        summary=f'Found {result["total"]} role-scoped result(s) across {len(result["groups"])} surface(s).',
        meta={'query': result['query'], 'groups': result['groups'], 'total': result['total']},
    )


def _tool_get_project_overview(args, user):
    detail = project_service.get_project_detail(_int_arg(args, 'project_id'), user_id=user.id)
    phase_label = project_service.PHASE_NAME_BY_KEY.get(
        detail['current_phase'],
        (detail['current_phase'] or '').replace('_', ' ').title(),
    )
    status_label = (detail['overall_status'] or '').replace('_', ' ').title()
    summary_parts = [part for part in (
        f'{phase_label} phase' if phase_label else None,
        f'{status_label} status' if status_label else None,
    ) if part]
    return _detail_result(
        f'Project #{detail["id"]}: {detail["project_name"]}',
        detail,
        summary=' · '.join(summary_parts) if summary_parts else 'Project overview',
    )


def _tool_get_sla_summary(args, user):
    dashboard = sla_service.get_sla_dashboard(user_id=user.id, fiscal_year=_int_arg(args, 'fiscal_year'))
    metrics = [{'label': key.replace('_', ' ').title(), 'value': value} for key, value in dashboard.items()]
    return _metric_result('Compliance Deadline Summary', metrics, detail=dashboard)


def _tool_generate_compliance_summary(args, user):
    summary = ai_insight_service.generate_compliance_summary(user.id, fiscal_year=_int_arg(args, 'fiscal_year'))
    detail = {
        'executive_summary': summary.get('executive_summary'),
        'bottlenecks': summary.get('bottlenecks', []),
        'recommended_actions': summary.get('recommended_actions', []),
        'risk_flags': summary.get('risk_flags', []),
        'source_metrics': summary.get('source_metrics', {}),
        'generated_at': summary.get('generated_at'),
        'ai_provider_used': summary.get('ai_provider_used'),
        'ai_model_used': summary.get('ai_model_used'),
    }
    return _detail_result(
        'Compliance Summary',
        detail,
        summary=summary.get('executive_summary') or 'Generated a role-scoped compliance summary.',
    )


def _resolve_program_filter(args):
    program_id = _int_arg(args, 'program_id')
    name = _text_arg(args, 'program_name')
    if program_id is not None or not name:
        return program_id
    result = program_service.list_programs(search=name, per_page=100)
    rows = result.get('programs', [])
    exact = [row for row in rows if name.casefold().strip() in (
        str(row.get('name') or '').casefold().strip(),
        str(row.get('code') or '').casefold().strip())]
    if len(exact) == 1:
        return exact[0]['id']
    if result.get('total') == 1:
        return rows[0]['id']
    if not rows:
        raise AiToolError('No program matches that name or code. Please specify the program.', 422)
    raise AiToolError('Multiple programs match that name. Please specify the full name or program code.', 422)


def _resolve_lgu_filter(args, user, empty_if_missing=False):
    lgu_id = _int_arg(args, 'lgu_id')
    name = _text_arg(args, 'lgu_name')
    if lgu_id is not None:
        # Canonical read services intersect this filter with the user's scope.
        # An inaccessible ID returns no rows rather than revealing its existence.
        return lgu_id
    if not name:
        return None
    result = lgu_service.list_lgus(search=name, per_page=100, user_id=user.id)
    rows = result.get('lgus', [])
    exact = [row for row in rows if name.casefold().strip() in (
        str(row.get('name') or '').casefold().strip(),
        str(row.get('municipality') or '').casefold().strip())]
    if len(exact) == 1:
        return exact[0]['id']
    if result.get('total') == 1:
        return rows[0]['id']
    if not rows:
        if empty_if_missing:
            return -1
        raise AiToolError('No accessible LGU matches that name. Please specify the LGU name or location.', 422)
    raise AiToolError('Multiple accessible LGUs match that name. Please specify the full name or province.', 422)


def _tool_list_overdue_slas(args, user):
    lgu_id = _resolve_lgu_filter(args, user)
    rows = sla_service.get_overdue_deadlines(
        project_id=_int_arg(args, 'project_id'),
        fiscal_year=_int_arg(args, 'fiscal_year'),
        user_id=user.id,
        lgu_id=lgu_id,
    )
    return _table_result(
        'Overdue Compliance Deadlines',
        rows,
        [
            {'key': 'id', 'label': 'Deadline ID'},
            {'key': 'project_name', 'label': 'Project'},
            {'key': 'requirement_name', 'label': 'Requirement'},
            {'key': 'deadline_date', 'label': 'Deadline'},
            {'key': 'days_remaining', 'label': 'Working Days'},
        ],
        summary=f'Found {len(rows)} overdue working-day deadline(s). Use the Deadline ID as the SLA ID for notice preparation.',
    )


def _tool_get_sla_deadline_detail(args, user):
    deadline_id = _int_arg(args, 'deadline_id') or _int_arg(args, 'sla_id')
    if not deadline_id:
        raise AiToolError('deadline_id is required.', 422)
    try:
        data = sla_service.get_sla_deadline_detail(deadline_id, user_id=user.id)
    except (sla_service.SlaError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)

    stage = data.get('stage_label') or sla_service.format_deadline_type(data.get('deadline_type'))
    proj_name = data.get('project_name') or 'Project'
    status = (data.get('status') or 'unknown').title()
    summary = f'Deadline #{data.get("id")}: {stage} for {proj_name} · Status: {status}'
    if data.get('is_overdue'):
        summary += ' (Overdue)'

    return _detail_result(
        f'Deadline #{data.get("id")}: {proj_name}',
        data,
        summary=summary,
    )


def _tool_list_handoff_queue(args, user):
    paging = _page_args(args)
    result = submission_service.list_handoff_queue(
        search=_text_arg(args, 'search'),
        page=paging['page'],
        per_page=paging['per_page'],
        fiscal_year=_int_arg(args, 'fiscal_year'),
        user_id=user.id,
    )
    return _table_result(
        'Regional Handoff Queue',
        result['items'],
        [
            {'key': 'requirement_id', 'label': 'Requirement ID'},
            {'key': 'project_name', 'label': 'Project'},
            {'key': 'requirement_name', 'label': 'Requirement'},
            {'key': 'lgu_name', 'label': 'LGU'},
            {'key': 'latest_submission_at', 'label': 'Latest Submission'},
        ],
        summary=f'Found {result["total"]} approved item(s) awaiting handoff.',
        meta={'total': result['total'], 'page': result['page'], 'pages': result['pages']},
    )


def _tool_list_notices(args, user):
    lgu_id = _resolve_lgu_filter(args, user)
    paging = _page_args(args)
    result = escalation_service.list_escalation_notices(
        page=paging['page'],
        per_page=paging['per_page'],
        user_id=user.id,
        project_id=_int_arg(args, 'project_id'),
        lgu_id=lgu_id,
        trigger_sla_id=_int_arg(args, 'trigger_sla_id'),
        notice_type=_text_arg(args, 'notice_type'),
        status=_text_arg(args, 'status'),
        fiscal_year=_int_arg(args, 'fiscal_year'),
    )
    return _table_result(
        'Notices and Follow-Up',
        result['notices'],
        [
            {'key': 'id', 'label': 'Notice ID'},
            {'key': 'title', 'label': 'Title'},
            {'key': 'notice_type', 'label': 'Type'},
            {'key': 'status', 'label': 'Status'},
            {'key': 'project_name', 'label': 'Project'},
        ],
        summary=f'Found {result["total"]} notice record(s).',
        meta={'total': result['total'], 'page': result['page'], 'pages': result['pages']},
    )


def _tool_monitoring_workbench(args, user):
    data = monitoring_service.get_monitoring_workbench(user_id=user.id, fiscal_year=_int_arg(args, 'fiscal_year'))
    return _table_result(
        'QAAR Implementation Monitoring Workbench',
        data.get('projects', []),
        [
            {'key': 'project_id', 'label': 'Project ID'},
            {'key': 'project_name', 'label': 'Project'},
            {'key': 'lgu_name', 'label': 'LGU'},
            {'key': 'monitoring_state', 'label': 'State'},
            {'key': 'latest_status', 'label': 'Latest Status'},
        ],
        summary=f'{len(data.get("projects", []))} QAAR implementation project(s) are visible to you.',
        meta={'summary': data.get('summary', {})},
    )


def _tool_list_monitoring_inspections(args, user):
    paging = _page_args(args)
    result = monitoring_service.list_inspections(
        project_id=_int_arg(args, 'project_id'),
        status=_text_arg(args, 'status'),
        monitoring_type=_text_arg(args, 'monitoring_type'),
        transmittal_status=_text_arg(args, 'transmittal_status'),
        monthly_cycle_tag=_text_arg(args, 'monthly_cycle_tag'),
        search=_text_arg(args, 'search'),
        page=paging['page'],
        per_page=paging['per_page'],
        fiscal_year=_int_arg(args, 'fiscal_year'),
        user_id=user.id,
    )
    return _table_result(
        'QAAR Monitoring Records',
        result['items'],
        [
            {'key': 'id', 'label': 'Inspection ID'},
            {'key': 'project_name', 'label': 'Project'},
            {'key': 'monitoring_type', 'label': 'Type'},
            {'key': 'inspection_date', 'label': 'Date'},
            {'key': 'status', 'label': 'Status'},
        ],
        summary=f'Found {result["total"]} QAAR monitoring record(s).',
        meta={'total': result['total'], 'page': result['page'], 'pages': result['pages']},
    )


def _tool_list_non_infra_monitoring_records(args, user):
    records = non_infra_monitoring_service.list_records(
        project_id=_int_arg(args, 'project_id'),
        template_type=_text_arg(args, 'template_type'),
        reporting_period=_text_arg(args, 'reporting_period'),
        workflow_status=_text_arg(args, 'workflow_status'),
        user_id=user.id,
    )
    return _table_result(
        'Non-Infrastructure Monitoring Records',
        records,
        [
            {'key': 'id', 'label': 'Record ID'},
            {'key': 'project_id', 'label': 'Project ID'},
            {'key': 'template_type', 'label': 'Template Type'},
            {'key': 'appendix_reference', 'label': 'Appendix'},
            {'key': 'reporting_period', 'label': 'Period'},
            {'key': 'items_verified_summary', 'label': 'Items Verified'},
            {'key': 'specifications_met', 'label': 'Specs Met'},
            {'key': 'workflow_status', 'label': 'Workflow Status'},
            {'key': 'remarks', 'label': 'Remarks'},
        ],
        summary=f'Found {len(records)} non-infrastructure monitoring record(s).',
        meta={'total': len(records)},
    )


def _tool_list_beneficiary_evidence_records(args, user):
    records = beneficiary_evidence_service.list_records(
        project_id=_int_arg(args, 'project_id'),
        evidence_type=_text_arg(args, 'evidence_type'),
        workflow_status=_text_arg(args, 'workflow_status'),
        user_id=user.id,
    )
    total_beneficiaries = sum(int(r.get('beneficiary_count') or 0) for r in records)
    return _table_result(
        'Beneficiary Evidence Records',
        records,
        [
            {'key': 'id', 'label': 'Record ID'},
            {'key': 'evidence_type', 'label': 'Evidence Type'},
            {'key': 'beneficiary_count', 'label': 'Beneficiary Count'},
            {'key': 'distribution_date', 'label': 'Distribution Date'},
            {'key': 'reference_number', 'label': 'Reference No.'},
            {'key': 'description', 'label': 'Description'},
            {'key': 'appendix_reference', 'label': 'Appendix'},
            {'key': 'workflow_status', 'label': 'Workflow Status'},
        ],
        summary=f'Found {len(records)} beneficiary evidence record(s) totaling {total_beneficiaries} beneficiary(ies).',
        meta={'total': len(records), 'total_beneficiaries': total_beneficiaries},
    )


def _tool_settings_readiness(args, user):
    data = settings_service.get_readiness_snapshot()
    return _detail_result(f'{settings_service.get_app_name()} System Checks', data, summary=data.get('summary', {}).get('overall', 'System checks completed.'))


def _tool_audit_summary(args, user):
    stats = audit_service.get_audit_stats()
    chain = audit_service.verify_audit_chain()
    metrics = [
        {'label': 'Audit Entries', 'value': stats.get('total', 0)},
        {'label': 'Last 24 Hours', 'value': stats.get('recent_count_24h', 0)},
        {'label': 'Unique Actors', 'value': stats.get('unique_users', 0)},
        {'label': 'Hash Chain Valid', 'value': 'Yes' if chain.get('is_valid') else 'No'},
    ]
    return _metric_result('Audit Summary', metrics, detail={'stats': stats, 'chain': chain})


def _tool_list_import_batches(args, user):
    paging = _page_args(args)
    result = import_service.list_import_batches(
        program_id=_int_arg(args, 'program_id'),
        program_cycle_id=_int_arg(args, 'program_cycle_id'),
        fiscal_year=_int_arg(args, 'fiscal_year'),
        status=_text_arg(args, 'status'),
        page=paging['page'],
        per_page=paging['per_page'],
    )
    return _table_result(
        'Workbook Import Batches',
        result['items'],
        [
            {'key': 'id', 'label': 'Batch ID'},
            {'key': 'original_file_name', 'label': 'File'},
            {'key': 'status', 'label': 'Status'},
            {'key': 'detected_sheets_count', 'label': 'Sheets'},
            {'key': 'created_at', 'label': 'Uploaded'},
        ],
        summary=f'Found {result["total"]} import batch record(s).',
        meta={'total': result['total'], 'page': result['page'], 'pages': result['pages']},
    )


def _tool_list_guidelines(args, user):
    paging = _page_args(args)
    is_current = _bool_arg(args, 'is_current')
    result = governance_service.list_guidelines(
        search=_text_arg(args, 'search'),
        program_id=_int_arg(args, 'program_id'),
        guideline_type=_text_arg(args, 'guideline_type'),
        is_current=is_current,
        page=paging['page'],
        per_page=paging['per_page'],
    )
    return _table_result(
        'Guidelines and Annexes',
        result['items'],
        [
            {'key': 'id', 'label': 'Guideline ID'},
            {'key': 'title', 'label': 'Title'},
            {'key': 'guideline_type', 'label': 'Type'},
            {'key': 'reference_number', 'label': 'Reference'},
            {'key': 'is_current', 'label': 'Current'},
        ],
        summary=f'Found {result["total"]} guideline record(s).',
        meta={'total': result['total'], 'page': result['page'], 'pages': result['pages']},
    )


def _tool_resolve_sla_deadline(args, user):
    deadline = sla_service.resolve_sla_deadline(
        _int_arg(args, 'sla_id'),
        notes=_text_arg(args, 'notes', f'Resolved through a confirmed {settings_service.get_assistant_name()} action.'),
        user_id=user.id,
    )
    return _detail_result(
        f'Deadline #{deadline.id} Resolved',
        sla_service._serialize_sla_deadline(deadline),
        summary='The working-day deadline was marked resolved after user confirmation.',
    )


def _tool_push_requirement_handoff(args, user):
    result = submission_service.push_requirement_to_drive(
        requirement_id=_int_arg(args, 'requirement_id'),
        user_id=user.id,
    )
    return _detail_result(
        'Regional Handoff',
        result,
        summary='The approved requirement handoff was processed after user confirmation.',
    )


def _tool_generate_notice_for_sla(args, user):
    notice = escalation_service.generate_next_notice_for_sla(
        sla_id=_int_arg(args, 'sla_id'),
        user_id=user.id,
    )
    detail = escalation_service.get_escalation_notice_detail(notice.id, user_id=user.id)
    return _detail_result(
        f'Notice #{notice.id} Prepared',
        detail,
        summary='The next notice was prepared after user confirmation.',
    )


def _tool_get_field_summary(args, user):
    summary = field_officer_service.get_field_summary(user_id=user.id, fiscal_year=_int_arg(args, 'fiscal_year'))
    return _detail_result(
        'Field Officer Dashboard Summary',
        summary,
        summary='Dashboard summary for assigned LGUs.'
    )


def _tool_list_assigned_lgus(args, user):
    lgus = field_officer_service.list_assigned_lgus(user_id=user.id, fiscal_year=_int_arg(args, 'fiscal_year'))
    return _table_result(
        'Assigned LGUs',
        lgus,
        [
            {'key': 'id', 'label': 'LGU ID'},
            {'key': 'name', 'label': 'LGU Name'},
            {'key': 'municipality', 'label': 'Municipality'},
            {'key': 'project_count', 'label': 'Projects'},
            {'key': 'open_requirement_count', 'label': 'Open Requirements'},
            {'key': 'overdue_deadline_count', 'label': 'Overdue Deadlines'},
        ],
        summary=f'Found {len(lgus)} assigned LGU(s).'
    )


def _tool_list_action_items(args, user):
    limit = min(max(_int_arg(args, 'limit', 50) or 50, 1), 100)
    items = field_officer_service.list_action_items(user_id=user.id, fiscal_year=_int_arg(args, 'fiscal_year'), limit=limit)
    return _table_result(
        'Action Item Workbench',
        items,
        [
            {'key': 'priority', 'label': 'Priority'},
            {'key': 'title', 'label': 'Title'},
            {'key': 'type', 'label': 'Type'},
            {'key': 'description', 'label': 'Description'},
        ],
        summary=f'Found {len(items)} action item(s).'
    )


def _tool_create_requirement_comment(args, user):
    requirement_id = _int_arg(args, 'requirement_id')
    data = {
        'body': _text_arg(args, 'body'),
        'comment_type': _text_arg(args, 'comment_type'),
        'visibility': _text_arg(args, 'visibility'),
    }
    result = field_officer_service.create_requirement_comment(requirement_id, data, user.id)
    return _detail_result(
        f'Requirement Comment Created',
        result,
        summary='The comment was successfully posted.'
    )



def _tool_query_projects(args, user):
    lgu_id = _resolve_lgu_filter(args, user, empty_if_missing=True)
    program_id = _resolve_program_filter(args)

    paging = _page_args(args)
    limit = min(max(_int_arg(args, 'limit', paging['per_page']) or 20, 1), 100)

    result = project_service.list_projects(
        project_ids=args.get('project_ids'),
        search=_text_arg(args, 'search'),
        lgu_id=lgu_id,
        program_id=program_id,
        fiscal_year=_int_arg(args, 'fiscal_year'),
        program_cycle_id=_int_arg(args, 'program_cycle_id'),
        current_phase=_text_arg(args, 'current_phase'),
        overall_status=_text_arg(args, 'overall_status'),
        has_non_compliant_requirements=_bool_arg(args, 'has_non_compliant_requirements'),
        page=paging['page'],
        per_page=limit,
        user_id=user.id,
    )
    rows = result['projects']
    total = result['total']

    return _table_result(
        'Project Query Results',
        rows,
        [
            {'key': 'id', 'label': 'ID'},
            {'key': 'project_name', 'label': 'Project'},
            {'key': 'fiscal_year', 'label': 'FY'},
            {'key': 'current_phase', 'label': 'Phase'},
            {'key': 'overall_status', 'label': 'Status'},
        ],
        summary=f'Showing {len(rows)} of {total} project record(s).',
        meta={'total': total, 'page': result['page'], 'pages': result['pages'], 'per_page': limit}
    )

def _tool_query_requirements(args, user):
    from app.models import ProjectRequirement, Project, SlaDeadline, User, LguProfile
    from app.services import access_service, project_service, lgu_service
    from sqlalchemy import false, or_
    from datetime import datetime, timezone
    from app.extensions import db

    query = ProjectRequirement.query.join(Project).filter(ProjectRequirement.is_active.is_(True))
    
    # 1. Enforce Role Scoping
    query = access_service.restrict_project_query(query, user.id)

    # 2. Apply Filters
    from app.models import Submission, DocumentFile, RequirementDeficiency, SubmissionVersion
    req_id = _int_arg(args, 'requirement_id')
    if req_id:
        query = query.filter(ProjectRequirement.id == req_id)

    project_id = _int_arg(args, 'project_id')
    if project_id:
        query = query.filter(ProjectRequirement.project_id == project_id)

    lgu_id = _resolve_lgu_filter(args, user, empty_if_missing=True)
    if lgu_id is not None:
        query = query.filter(Project.lgu_id == lgu_id)
        
    fiscal_year = _int_arg(args, 'fiscal_year')
    if fiscal_year:
        query = query.filter(Project.fiscal_year == fiscal_year)

    requirement_type = _text_arg(args, 'requirement_type')
    if requirement_type:
        req_type_norm = requirement_type.lower().strip()
        if req_type_norm in ('pow', 'program_of_works', 'program of works'):
            query = query.filter(
                or_(
                    ProjectRequirement.requirement_type == requirement_type,
                    ProjectRequirement.requirement_name.ilike('%Program of Works%'),
                    ProjectRequirement.requirement_name.ilike('%Program of Work%'),
                    ProjectRequirement.annex_reference.ilike('%POW%')
                )
            )
        elif req_type_norm in ('ded', 'detailed_engineering_design', 'detailed engineering design'):
            query = query.filter(
                or_(
                    ProjectRequirement.requirement_type == requirement_type,
                    ProjectRequirement.requirement_name.ilike('%Detailed Engineering Design%'),
                    ProjectRequirement.annex_reference.ilike('%DED%')
                )
            )
        elif req_type_norm in ('ntp', 'notice_to_proceed', 'notice to proceed'):
            query = query.filter(
                or_(
                    ProjectRequirement.requirement_type == requirement_type,
                    ProjectRequirement.requirement_name.ilike('%Notice to Proceed%'),
                    ProjectRequirement.annex_reference.ilike('%NTP%')
                )
            )
        elif req_type_norm in ('noa', 'notice_of_award', 'notice of award'):
            query = query.filter(
                or_(
                    ProjectRequirement.requirement_type == requirement_type,
                    ProjectRequirement.requirement_name.ilike('%Notice of Award%'),
                    ProjectRequirement.annex_reference.ilike('%NOA%')
                )
            )
        else:
            query = query.filter(ProjectRequirement.requirement_type == requirement_type)

    document_category = _text_arg(args, 'document_category')
    if document_category:
        query = query.filter(ProjectRequirement.document_category == document_category.lower().replace('-', '_').strip())

    annex_reference = _text_arg(args, 'annex_reference')
    if annex_reference:
        query = query.filter(ProjectRequirement.annex_reference.ilike(f"%{annex_reference.strip()}%"))

    phase = _text_arg(args, 'phase') or _text_arg(args, 'phase_name')
    if phase:
        query = query.filter(ProjectRequirement.phase_name.ilike(f"%{phase.strip()}%"))

    is_mandatory = _bool_arg(args, 'is_mandatory')
    if is_mandatory is None:
        is_mandatory = _bool_arg(args, 'mandatory')
    if is_mandatory is not None:
        query = query.filter(ProjectRequirement.is_mandatory == is_mandatory)

    has_sla = _bool_arg(args, 'has_sla')
    if has_sla is not None:
        query = query.filter(ProjectRequirement.has_sla == has_sla)

    applicability = _text_arg(args, 'applicability')
    if applicability:
        applicability = applicability.lower().strip()
        if applicability in ('not_applicable', 'na', 'n/a'):
            query = query.filter(ProjectRequirement.applicability == 'not_applicable')
        elif applicability in ('applicable', 'app'):
            query = query.filter(ProjectRequirement.applicability == 'applicable')

    has_sub = _bool_arg(args, 'has_submission')
    if has_sub is None:
        has_sub = _bool_arg(args, 'has_evidence')
    if has_sub is not None:
        sub_exists = Submission.query.filter(
            Submission.project_requirement_id == ProjectRequirement.id
        ).exists()
        if has_sub:
            query = query.filter(sub_exists)
        else:
            query = query.filter(~sub_exists)
            if not applicability and not _text_arg(args, 'compliance_status'):
                query = query.filter(ProjectRequirement.applicability == 'applicable')

    has_def = _bool_arg(args, 'has_open_deficiencies')
    if has_def is None:
        has_def = _bool_arg(args, 'has_deficiencies')
    if has_def is not None:
        def_exists = RequirementDeficiency.query.filter(
            RequirementDeficiency.project_requirement_id == ProjectRequirement.id,
            RequirementDeficiency.resolution_state == 'open'
        ).exists()
        if has_def:
            query = query.filter(def_exists)
        else:
            query = query.filter(~def_exists)

    search_term = _text_arg(args, 'search') or _text_arg(args, 'q')
    if search_term:
        query = query.filter(
            or_(
                ProjectRequirement.requirement_name.ilike(f"%{search_term}%"),
                ProjectRequirement.annex_reference.ilike(f"%{search_term}%")
            )
        )

    workflow_status = _text_arg(args, 'workflow_status')
    if workflow_status:
        workflow_status = workflow_status.lower().replace('-', '_').strip()
        query = query.filter(ProjectRequirement.workflow_status == workflow_status)

    compliance_status = _text_arg(args, 'compliance_status')
    if compliance_status:
        compliance_status = compliance_status.lower().replace('-', '_').strip()
        if compliance_status in ('returned_for_revision', 'returned'):
            query = query.filter(ProjectRequirement.workflow_status == 'returned_for_revision')
        elif compliance_status == 'resubmitted':
            query = query.filter(ProjectRequirement.workflow_status == 'resubmitted')
        elif compliance_status in ('not_applicable', 'na', 'n/a'):
            query = query.filter(ProjectRequirement.applicability == 'not_applicable')
        elif compliance_status == 'missing':
            # Natural-language "missing": requirements where no documentary submission is currently recorded
            sub_exists = Submission.query.filter(
                Submission.project_requirement_id == ProjectRequirement.id
            ).exists()
            query = query.filter(~sub_exists)
            if not applicability:
                query = query.filter(ProjectRequirement.applicability == 'applicable')
        elif compliance_status == 'incomplete':
            # Natural-language "incomplete": outstanding requirements not yet compliant/approved
            query = query.filter(
                ProjectRequirement.status.in_(['pending', 'under_review', 'non_compliant']),
                or_(
                    ProjectRequirement.workflow_status.is_(None),
                    ProjectRequirement.workflow_status.notin_(['approved', 'staff_approved'])
                )
            )
            if not applicability:
                query = query.filter(ProjectRequirement.applicability == 'applicable')
        else:
            query = query.filter(ProjectRequirement.status == compliance_status)
            if compliance_status in ('pending', 'under_review', 'non_compliant') and not applicability:
                query = query.filter(ProjectRequirement.applicability == 'applicable')
        
    overdue = _bool_arg(args, 'overdue')
    if overdue is not None:
        has_overdue = SlaDeadline.query.filter(
            SlaDeadline.project_requirement_id == ProjectRequirement.id,
            SlaDeadline.is_resolved == False,
            SlaDeadline.deadline_date < datetime.now(timezone.utc)
        ).exists()
        if overdue:
            query = query.filter(has_overdue)
        else:
            query = query.filter(~has_overdue)

    field_officer_name = _text_arg(args, 'assigned_field_officer')
    if field_officer_name:
        fo = User.query.filter_by(role='field_officer').filter(
            or_(User.first_name.ilike(f'%{field_officer_name}%'),
                User.last_name.ilike(f'%{field_officer_name}%'),
                User.email.ilike(f'%{field_officer_name}%'))
        ).first()
        if fo:
            query = access_service.restrict_project_query(query, fo.id)
        else:
            query = query.filter(false())
            
    date_start = _text_arg(args, 'date_start')
    if date_start:
        query = query.filter(ProjectRequirement.updated_at >= date_start)
    date_end = _text_arg(args, 'date_end')
    if date_end:
        query = query.filter(ProjectRequirement.updated_at <= date_end)

    default_limit = 100 if project_id else 20
    limit = min(max(_int_arg(args, 'limit') or default_limit, 1), 100)
    page = max(_int_arg(args, 'page', 1) or 1, 1)
    
    pagination = query.order_by(ProjectRequirement.created_at.desc()).paginate(
        page=page, per_page=limit, error_out=False
    )
    rows = []
    for req in pagination.items:
        data = project_service._serialize_project_requirement(req)
        proj = db.session.get(Project, req.project_id)
        data['project_name'] = proj.project_name if proj else None
        data['fiscal_year'] = proj.fiscal_year if proj else None
        
        latest_sub = Submission.query.filter_by(project_requirement_id=req.id).order_by(Submission.id.desc()).first()
        data['has_submission'] = bool(latest_sub)
        data['current_version_number'] = latest_sub.current_version if latest_sub else None
        data['latest_submission_at'] = latest_sub.created_at.isoformat() if (latest_sub and latest_sub.created_at) else None
        data['workflow_return_reason'] = req.workflow_return_reason
        data['open_deficiencies_count'] = RequirementDeficiency.query.filter_by(
            project_requirement_id=req.id, resolution_state='open'
        ).count()
        rows.append(data)
    total = pagination.total
    
    status_descriptor = ''
    if workflow_status:
        wf_display = _format_requirement_status_label(workflow_status) or workflow_status.replace('_', ' ').title()
        status_descriptor = f" with workflow status '{wf_display}'"
    elif compliance_status:
        comp_display = _format_requirement_status_label(compliance_status) or compliance_status.replace('_', ' ').title()
        status_descriptor = f" with status '{comp_display}'"

    summary_text = f'Showing {len(rows)} of {total} requirement record(s){status_descriptor}'
    if fiscal_year:
        summary_text += f' for FY {fiscal_year}'
    summary_text += '.'
    if field_officer_name and fo:
        summary_text = f"Showing {len(rows)} of {total} requirement record(s) in {fo.first_name} {fo.last_name}'s assigned LGU(s)."
    
    return _table_result(
        'Requirement Query Results',
        rows,
        [
            {'key': 'id', 'label': 'ID'},
            {'key': 'requirement_name', 'label': 'Requirement'},
            {'key': 'project_name', 'label': 'Project'},
            {'key': 'annex_reference', 'label': 'Annex'},
            {'key': 'applicability', 'label': 'Applicability'},
            {'key': 'status', 'label': 'Compliance'},
            {'key': 'workflow_status', 'label': 'Workflow'},
            {'key': 'current_version_number', 'label': 'Version'},
            {'key': 'open_deficiencies_count', 'label': 'Open Deficiencies'},
        ],
        summary=summary_text,
        meta={'total': total, 'page': pagination.page, 'pages': pagination.pages, 'per_page': limit}
    )


def _tool_get_requirement_detail(args, user):
    from app.models import ProjectRequirement, Project, SlaDeadline, User, Submission, SubmissionVersion, DocumentFile, RequirementDeficiency, RequirementWorkflowTransition
    from app.services import project_service, submission_service, requirement_workflow_service
    from app.extensions import db

    req_id = _int_arg(args, 'requirement_id')
    req = db.session.get(ProjectRequirement, req_id)
    if not req or not req.is_active:
        raise AiToolError(f'Requirement #{req_id} not found or inactive.', 404)

    project = db.session.get(Project, req.project_id)
    project_name = project.project_name if project else None

    req_data = project_service._serialize_project_requirement(req, user_role=user.role)
    submissions_data = submission_service.list_requirement_submissions(req.id, user_id=user.id)
    
    # Resolve uploader names
    for sub in submissions_data:
        sub_uploader = db.session.get(User, sub['uploaded_by']) if sub.get('uploaded_by') else None
        sub['uploaded_by_name'] = sub_uploader.full_name if sub_uploader else None

    all_versions = []
    current_ver_obj = None
    historical_ver_objs = []
    
    # Collect all versions chronologically
    for sub in submissions_data:
        sub_id = sub['id']
        versions = SubmissionVersion.query.filter_by(submission_id=sub_id).order_by(SubmissionVersion.version_number.asc()).all()
        for v in versions:
            is_curr = (sub_id == (submissions_data[0]['id'] if submissions_data else None)) and (v.version_number == sub.get('current_version'))
            v_info = {
                'submission_id': sub_id,
                'version_id': v.id,
                'version_number': v.version_number,
                'original_filename': v.original_filename,
                'mime_type': v.mime_type,
                'file_size_bytes': v.file_size_bytes,
                'uploaded_at': v.uploaded_at.isoformat() if v.uploaded_at else None,
                'uploader_id': sub.get('uploaded_by'),
                'uploader_name': sub.get('uploaded_by_name'),
                'source': sub.get('source'),
                'is_current': is_curr,
            }
            all_versions.append(v_info)
            if is_curr:
                current_ver_obj = v_info
            else:
                historical_ver_objs.append(v_info)

    # Sort all_versions by version_number ascending
    all_versions.sort(key=lambda x: x.get('version_number') or 0)

    # Deficiencies
    try:
        deficiencies_data = requirement_workflow_service.list_deficiencies(req.id, user_id=user.id)
    except Exception:
        # Fallback to direct query if requirement has no document_category or outside workflow service
        defs = RequirementDeficiency.query.filter_by(project_requirement_id=req.id).all()
        deficiencies_data = [{
            'id': d.id,
            'category': d.category,
            'finding_observation': d.finding_observation,
            'corrective_instruction': d.corrective_instruction,
            'resolution_state': d.resolution_state,
        } for d in defs]
    open_deficiencies = [d for d in deficiencies_data if d.get('resolution_state') == 'open']
    resolved_deficiencies = [d for d in deficiencies_data if d.get('resolution_state') == 'resolved']
    waived_deficiencies = [d for d in deficiencies_data if d.get('resolution_state') == 'waived']

    # Version comparison (what changed between latest and previous submission)
    version_comparison = None
    if len(all_versions) >= 2:
        prev_v = all_versions[-2]
        curr_v = all_versions[-1]
        resolved_since_prev = [
            d for d in resolved_deficiencies
            if d.get('resolved_submission_version_id') == curr_v.get('version_id')
        ]
        version_comparison = {
            'previous_version_number': prev_v.get('version_number'),
            'previous_filename': prev_v.get('original_filename'),
            'previous_uploaded_at': prev_v.get('uploaded_at'),
            'previous_file_size_bytes': prev_v.get('file_size_bytes'),
            'current_version_number': curr_v.get('version_number'),
            'current_filename': curr_v.get('original_filename'),
            'current_uploaded_at': curr_v.get('uploaded_at'),
            'current_file_size_bytes': curr_v.get('file_size_bytes'),
            'filename_changed': prev_v.get('original_filename') != curr_v.get('original_filename'),
            'file_size_delta_bytes': (curr_v.get('file_size_bytes') or 0) - (prev_v.get('file_size_bytes') or 0),
            'resolved_deficiencies_count': len(resolved_since_prev),
            'resolved_deficiencies': resolved_since_prev,
        }

    # Workflow lifecycle transitions
    try:
        workflow_info = requirement_workflow_service.get_requirement_workflow(req.id, user_id=user.id)
        transitions_data = workflow_info.get('transitions', [])
    except Exception:
        transitions_data = []

    # Format human-readable lifecycle history summary
    if transitions_data:
        history_steps = []
        for t in transitions_data:
            from_raw = t.get('from_status') or 'draft'
            from_st = _format_requirement_status_label(from_raw) or str(from_raw).replace('_', ' ').title()
            to_raw = t.get('to_status', '')
            to_st = _format_requirement_status_label(to_raw) or (str(to_raw).replace('_', ' ').title() if to_raw else '')
            actor = f" by {t['actor_name']}" if t.get('actor_name') else ""
            date_str = f" on {t['created_at'][:10]}" if t.get('created_at') else ""
            reason_str = f" (reason: '{t['reason']}')" if t.get('reason') else ""
            history_steps.append(f"{from_st} -> {to_st}{actor}{date_str}{reason_str}")
        workflow_history_summary = "; ".join(history_steps)
    else:
        workflow_history_summary = "Initial draft (no workflow transitions recorded yet)."

    # Advisory checker result
    checker_result = submissions_data[0].get('latest_compliance_result') if submissions_data else None
    if checker_result:
        checker_result['is_advisory'] = True
        checker_result['advisory_note'] = 'Document checker findings are advisory and do not constitute administrative approval.'

    detail = {
        'id': req.id,
        'requirement_name': req.requirement_name,
        'project_id': req.project_id,
        'project_name': project_name,
        'document_category': req.document_category,
        'annex_reference': req.annex_reference,
        'phase_name': req.phase_name,
        'is_mandatory': req.is_mandatory,
        'has_sla': req.has_sla,
        'sla_days': req.sla_days,
        'active_deadline': req_data.get('active_deadline'),
        'compliance_status': req.status,
        'workflow_status': req.workflow_status,
        'is_returned': req.workflow_status == 'returned_for_revision',
        'workflow_return_reason': req.workflow_return_reason,
        'workflow_returned_at': req.workflow_returned_at.isoformat() if req.workflow_returned_at else None,
        'submission_count': len(submissions_data),
        'has_documentary_evidence': req_data.get('has_documentary_evidence', False),
        'latest_submission': submissions_data[0] if submissions_data else None,
        'current_version': current_ver_obj,
        'historical_versions': historical_ver_objs,
        'all_versions': all_versions,
        'version_comparison': version_comparison,
        'submissions': submissions_data,
        'deficiencies': deficiencies_data,
        'open_deficiencies': open_deficiencies,
        'resolved_deficiencies': resolved_deficiencies,
        'waived_deficiencies': waived_deficiencies,
        'open_deficiencies_count': len(open_deficiencies),
        'resolved_deficiencies_count': len(resolved_deficiencies),
        'transitions': transitions_data,
        'workflow_history_summary': workflow_history_summary,
        'latest_compliance_result': checker_result,
    }

    comp_label = _format_requirement_status_label(req.status) or (req.status or 'N/A')
    wf_label = _format_requirement_status_label(req.workflow_status) if req.workflow_status else 'N/A'
    summary_parts = [
        f"Requirement #{req.id} '{req.requirement_name}' (Project #{req.project_id})",
        f"Compliance: {comp_label}",
        f"Workflow: {wf_label}"
    ]
    if req.annex_reference:
        summary_parts.append(f"Annex: {req.annex_reference}")
    if current_ver_obj:
        summary_parts.append(f"Current Version: v{current_ver_obj['version_number']} ({current_ver_obj['original_filename']})")
    elif not submissions_data:
        summary_parts.append("No submission is currently recorded.")
    if req.workflow_status == 'returned_for_revision':
        summary_parts.append(f"Return Reason: {req.workflow_return_reason or 'None'}")
        summary_parts.append(f"Open Deficiencies: {len(open_deficiencies)}")

    return _detail_result(
        f"Requirement #{req.id}: {req.requirement_name}",
        detail,
        summary=" · ".join(summary_parts)
    )


def _tool_upload_evidence_from_attachment(args, user):
    from app.services import submission_service, object_storage_service
    from app.models import StoredObject
    from app.extensions import db
    from werkzeug.datastructures import FileStorage
    
    requirement_id = _int_arg(args, 'requirement_id')
    attachment_id = _int_arg(args, 'attachment_id')
    
    stored = db.session.get(StoredObject, attachment_id)
    if not stored:
        raise AiToolError('Attachment not found.', 404)
        
    with object_storage_service.temporary_file(stored) as local_path:
        with open(local_path, 'rb') as f:
            # Wrap it so create_submission can use it like a Flask request.files upload
            file_wrapper = FileStorage(
                stream=f,
                filename=stored.original_filename,
                content_type=stored.content_type,
                name='file'
            )
            
            try:
                result = submission_service.create_submission(
                    requirement_id=requirement_id,
                    source='dms_ingestion' if user.role != 'field_officer' else 'field_upload',
                    description='Uploaded via AI Assistant',
                    upload=file_wrapper,
                    user_id=user.id,
                )
            except submission_service.SubmissionError as e:
                raise AiToolError(e.message, e.status_code)
            
    return _detail_result(
        f'Evidence Uploaded Successfully',
        result,
        summary='A new submission was created with the attached file.'
    )


def _tool_get_system_readiness(args, user):
    data = settings_service.get_readiness_snapshot()
    summary_data = data.get('summary') or {}
    total = summary_data.get('total', 0)
    ready = summary_data.get('ready', 0)
    warning = summary_data.get('warning', 0)
    disabled = summary_data.get('disabled', 0)
    summary_msg = f'{ready} of {total} system checks ready ({warning} warning, {disabled} disabled).'
    return _detail_result(
        f'{settings_service.get_app_name()} Technical System Readiness',
        data,
        summary=summary_msg,
    )


def _tool_query_audit_log(args, user):
    limit = min(max(_int_arg(args, 'limit') or 20, 1), 100)
    page = max(_int_arg(args, 'page', 1) or 1, 1)
    result = audit_service.list_audit_logs(
        entity_type=_text_arg(args, 'entity_type'),
        entity_id=_int_arg(args, 'entity_id'),
        user_id=_int_arg(args, 'user_id'),
        action=_text_arg(args, 'action'),
        start_date=_text_arg(args, 'start_date'),
        end_date=_text_arg(args, 'end_date'),
        search=_text_arg(args, 'search'),
        page=page,
        per_page=limit,
    )
    rows = [audit_service._serialize_audit_log(log) for log in result['logs']]
    total = result['total']
    return _table_result(
        'Audit Log Query Results',
        rows,
        [
            {'key': 'id', 'label': 'ID'},
            {'key': 'created_at', 'label': 'Timestamp'},
            {'key': 'user_name', 'label': 'Actor'},
            {'key': 'action', 'label': 'Action'},
            {'key': 'entity_type', 'label': 'Entity'},
            {'key': 'entity_id', 'label': 'Entity ID'},
        ],
        summary=f'Showing {len(rows)} of {total} audit log record(s).',
        meta={'total': total, 'page': result['page'], 'pages': result['pages']},
    )


def _tool_trigger_database_backup(args, user):
    try:
        data = backup_service.create_backup(user_id=getattr(user, 'id', None), trigger_type='manual')
    except backup_service.BackupError as exc:
        raise AiToolError(exc.message, exc.status_code) from exc
    return _detail_result(
        'Database Backup Created',
        data,
        summary=f"Snapshot archive {data.get('filename')} ({round(data.get('byte_size', 0)/1024, 1)} KB) saved to {data.get('storage_provider')}.",
    )


def _tool_list_database_backups(args, user):
    page = _int_arg(args, 'page') or 1
    limit = min(max(_int_arg(args, 'limit') or 20, 1), 100)
    data = backup_service.list_backups(page=page, per_page=limit)
    rows = data.get('backups') or []
    summary = data.get('summary') or {}
    return _table_result(
        'Database Backup Archives',
        rows,
        [
            {'key': 'id', 'label': 'ID'},
            {'key': 'filename', 'label': 'Filename'},
            {'key': 'status', 'label': 'Status'},
            {'key': 'byte_size', 'label': 'Size (bytes)'},
            {'key': 'trigger_type', 'label': 'Type'},
            {'key': 'storage_provider', 'label': 'Storage'},
            {'key': 'created_at', 'label': 'Created At'},
        ],
        summary=f"{summary.get('completed_count', 0)} completed backup(s), total storage: {round(summary.get('total_bytes', 0)/(1024*1024), 2)} MB on {summary.get('storage_provider')}.",
        meta=data.get('meta', {}),
    )


def _tool_restore_database_backup(args, user):
    backup_id = _int_arg(args, 'backup_id')
    confirmation_phrase = _text_arg(args, 'confirmation_phrase')
    target_db_url = _text_arg(args, 'target_db_url')

    try:
        data = backup_service.restore_backup(
            backup_id=backup_id,
            confirmation_phrase=confirmation_phrase,
            target_db_url=target_db_url,
            user_id=getattr(user, 'id', None),
        )
    except backup_service.BackupError as exc:
        raise AiToolError(exc.message, exc.status_code) from exc

    return _detail_result(
        'Database Restore Completed',
        data,
        summary=f"Database restored from archive #{data.get('backup_id')} ({data.get('filename')}). Pre-restore safety snapshot #{data.get('pre_restore_snapshot_id')} created.",
    )


def _tool_get_provincial_overview(args, user):
    fiscal_year = _int_arg(args, 'fiscal_year')
    try:
        data = operational_reporting_service.get_provincial_overview_data(user.id, fiscal_year=fiscal_year)
    except operational_reporting_service.OperationalReportingError as exc:
        raise AiToolError(exc.message, exc.status_code) from exc

    fy_label = f"FY {data.get('applicable_fiscal_year')}" if data.get('applicable_fiscal_year') else "All Projects"
    summary = (
        f"Provincial Overview ({fy_label}): {data.get('total_projects', 0)} project(s), "
        f"{data.get('documentary_compliance', {}).get('compliance_rate', 0.0)}% compliance, "
        f"{data.get('documentary_compliance', {}).get('open_documents', 0)} open document(s), "
        f"{data.get('deadlines', {}).get('overdue', 0)} overdue deadline(s)."
    )
    return _detail_result('Provincial Overview', data, summary=summary)


def _tool_compare_lgu_portfolios(args, user):
    lgu_names = args.get('lgu_names')
    if isinstance(lgu_names, str):
        lgu_names = [n.strip() for n in lgu_names.split(',') if n.strip()]
    lgu_ids = args.get('lgu_ids')
    if isinstance(lgu_ids, (int, str)) and not isinstance(lgu_ids, list):
        try:
            lgu_ids = [int(lgu_ids)]
        except ValueError:
            lgu_ids = None
    rank_by = _text_arg(args, 'rank_by')
    limit = _int_arg(args, 'limit', 10)
    fiscal_year = _int_arg(args, 'fiscal_year')

    try:
        data = operational_reporting_service.get_lgu_portfolio_comparison(
            user_id=user.id,
            lgu_names=lgu_names,
            lgu_ids=lgu_ids,
            rank_by=rank_by,
            limit=limit,
            fiscal_year=fiscal_year,
        )
    except operational_reporting_service.OperationalReportingError as exc:
        raise AiToolError(exc.message, exc.status_code) from exc

    columns = [
        {'key': 'rank', 'label': 'Rank'},
        {'key': 'lgu_name', 'label': 'LGU'},
        {'key': 'project_count', 'label': 'Projects'},
        {'key': 'open_document_count', 'label': 'Open Docs'},
        {'key': 'document_compliance_rate', 'label': 'Compliance %'},
        {'key': 'health_score', 'label': 'Health'},
        {'key': 'risk_project_count', 'label': 'Risk Projects'},
    ]
    summary = f"Compared {data['total_lgus_compared']} LGU(s) ranked by {data['metric_label']}."
    return _table_result('LGU Portfolio Analytics', data['lgus'], columns, summary=summary, meta=data)


def _tool_get_portfolio_risk_ranking(args, user):
    fiscal_year = _int_arg(args, 'fiscal_year')
    tier = _text_arg(args, 'tier')
    limit = _int_arg(args, 'limit', 10)

    try:
        data = operational_reporting_service.get_portfolio_risk_ranking_data(
            user_id=user.id,
            fiscal_year=fiscal_year,
            tier=tier,
            limit=limit,
        )
    except operational_reporting_service.OperationalReportingError as exc:
        raise AiToolError(exc.message, exc.status_code) from exc

    columns = [
        {'key': 'project_name', 'label': 'Project'},
        {'key': 'lgu_name', 'label': 'LGU'},
        {'key': 'health_score', 'label': 'Health Score'},
        {'key': 'health_label', 'label': 'Health Tier'},
        {'key': 'document_open_count', 'label': 'Open Docs'},
        {'key': 'physical_completion_pct', 'label': 'Progress %'},
        {'key': 'risk_reason_labels', 'label': 'Contributing Factors'},
    ]
    summary = f"{_get_app_name()} operational risk model: {data['returned_count']} project(s) prioritized for review."
    return _table_result('Portfolio Risk Ranking', data['projects'], columns, summary=summary, meta=data)


def _tool_get_deficiency_pattern_summary(args, user):
    fiscal_year = _int_arg(args, 'fiscal_year')
    lgu_id = _int_arg(args, 'lgu_id')
    project_id = _int_arg(args, 'project_id')
    resolution_state = _text_arg(args, 'resolution_state')

    try:
        data = operational_reporting_service.get_deficiency_pattern_data(
            user_id=user.id,
            fiscal_year=fiscal_year,
            lgu_id=lgu_id,
            project_id=project_id,
            resolution_state=resolution_state,
        )
    except operational_reporting_service.OperationalReportingError as exc:
        raise AiToolError(exc.message, exc.status_code) from exc

    columns = [
        {'key': 'category_label', 'label': 'Deficiency Category'},
        {'key': 'total_count', 'label': 'Occurrences'},
        {'key': 'open_count', 'label': 'Open'},
        {'key': 'resolved_count', 'label': 'Resolved'},
        {'key': 'waived_count', 'label': 'Waived'},
    ]
    summary = (
        f"Found {data['total_deficiencies']} deficiency record(s) across "
        f"{data['affected_project_count']} project(s) and {data['affected_requirement_count']} requirement(s)."
    )
    return _table_result('Deficiency Pattern Summary', data['top_categories'], columns, summary=summary, meta=data)


def _tool_get_recent_operational_activity(args, user):
    days = _int_arg(args, 'days', 30)
    fiscal_year = _int_arg(args, 'fiscal_year')
    lgu_id = _int_arg(args, 'lgu_id')
    project_id = _int_arg(args, 'project_id')

    try:
        data = operational_reporting_service.get_recent_operational_activity_data(
            user_id=user.id,
            days=days,
            fiscal_year=fiscal_year,
            lgu_id=lgu_id,
            project_id=project_id,
        )
    except operational_reporting_service.OperationalReportingError as exc:
        raise AiToolError(exc.message, exc.status_code) from exc

    columns = [
        {'key': 'timestamp', 'label': 'Timestamp'},
        {'key': 'project_name', 'label': 'Project'},
        {'key': 'requirement_name', 'label': 'Requirement'},
        {'key': 'action_label', 'label': 'Action'},
        {'key': 'to_status', 'label': 'Resulting Status'},
    ]
    summary = (
        f"Recorded {data['total_transitions']} workflow transition(s), {data['submissions_count']} submission(s), "
        f"and {data['monthly_reports_count']} monthly report(s) in the last {data['period_days']} day(s)."
    )
    return _table_result('Recent Operational Activity', data['activities'], columns, summary=summary, meta=data)


# -------------------------------------------------------------------------
# Phase 9B Wave A: Standard / Scoped CRU Tool Executors
# -------------------------------------------------------------------------

def _tool_create_lgu(args, user):
    try:
        lgu = lgu_service.create_lgu(
            name=_text_arg(args, 'name'),
            municipality=_text_arg(args, 'municipality'),
            province=_text_arg(args, 'province', 'Laguna') or 'Laguna',
            cluster_id=_int_arg(args, 'cluster_id'),
            mayor_name=_text_arg(args, 'mayor_name'),
            mayor_email=_text_arg(args, 'mayor_email'),
            contact_person=_text_arg(args, 'contact_person'),
            contact_email=_text_arg(args, 'contact_email'),
            contact_phone=_text_arg(args, 'contact_phone'),
            user_id=user.id,
        )
        return _detail_result(
            f'LGU {lgu.name} Registered',
            lgu_service._serialize_lgu(lgu),
            summary=f'Successfully registered LGU {lgu.name} ({lgu.municipality}, {lgu.province}).',
        )
    except lgu_service.LguError as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_lgu(args, user):
    lgu_id = _int_arg(args, 'lgu_id')
    tool = TOOLS['update_lgu']
    update_data = {k: args[k] for k in tool.allowed_fields if k in args and args[k] is not None}
    try:
        lgu = lgu_service.update_lgu(lgu_id, update_data, user_id=user.id)
        return _detail_result(
            f'LGU {lgu.name} Updated',
            lgu_service._serialize_lgu(lgu),
            summary=f'Successfully updated LGU {lgu.name}.',
        )
    except lgu_service.LguError as exc:
        _raise_scoped_tool_error(exc)


def _tool_create_cluster(args, user):
    try:
        cluster = lgu_service.create_cluster(
            name=_text_arg(args, 'name'),
            description=_text_arg(args, 'description'),
            user_id=user.id,
        )
        return _detail_result(
            f'Cluster {cluster.name} Created',
            lgu_service._serialize_cluster(cluster),
            summary=f'Successfully created LGU cluster {cluster.name}.',
        )
    except lgu_service.LguError as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_cluster(args, user):
    cluster_id = _int_arg(args, 'cluster_id')
    tool = TOOLS['update_cluster']
    update_data = {k: args[k] for k in tool.allowed_fields if k in args and args[k] is not None}
    try:
        cluster = lgu_service.update_cluster(cluster_id, update_data, user_id=user.id)
        return _detail_result(
            f'Cluster {cluster.name} Updated',
            lgu_service._serialize_cluster(cluster),
            summary=f'Successfully updated cluster {cluster.name}.',
        )
    except lgu_service.LguError as exc:
        _raise_scoped_tool_error(exc)


def _tool_create_program(args, user):
    try:
        program = program_service.create_program(
            name=_text_arg(args, 'name'),
            code=_text_arg(args, 'code'),
            program_type=_text_arg(args, 'program_type'),
            description=_text_arg(args, 'description'),
            funding_agency=_text_arg(args, 'funding_agency'),
            project_custom_field_schema=args.get('project_custom_field_schema'),
            user_id=user.id,
        )
        return _detail_result(
            f'Program {program.name} Created',
            program_service._serialize_program(program),
            summary=f'Successfully registered program {program.name} ({program.code}).',
        )
    except program_service.ProgramError as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_program(args, user):
    program_id = _int_arg(args, 'program_id')
    tool = TOOLS['update_program']
    from app.services import ai_program_schema_tools
    ai_program_schema_tools.prepare(tool, args, user, lock=True)
    update_data = {k: args[k] for k in tool.allowed_fields if k in args and args[k] is not None and k != 'expected_revision'}
    try:
        program = program_service.update_program(program_id, update_data, user_id=user.id)
        return _detail_result(
            f'Program {program.name} Updated',
            program_service._serialize_program(program),
            summary=f'Successfully updated program {program.name}.',
        )
    except program_service.ProgramError as exc:
        if ai_program_schema_tools.applies(tool, args):
            from app.extensions import db
            db.session.rollback()
        _raise_scoped_tool_error(exc)


def _tool_create_program_cycle(args, user):
    try:
        cycle = program_service.create_program_cycle(
            program_id=_int_arg(args, 'program_id'),
            name=_text_arg(args, 'name'),
            fiscal_year=_int_arg(args, 'fiscal_year'),
            cycle_code=_text_arg(args, 'cycle_code'),
            source_template_name=_text_arg(args, 'source_template_name'),
            import_profile=args.get('import_profile'),
            field_schema=args.get('field_schema'),
            user_id=user.id,
        )
        return _detail_result(
            f'Program Cycle {cycle.name} Created',
            program_service._serialize_program_cycle(cycle),
            summary=f'Successfully created program cycle {cycle.name} ({cycle.cycle_code}, FY {cycle.fiscal_year}).',
        )
    except program_service.ProgramError as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_program_cycle(args, user):
    cycle_id = _int_arg(args, 'cycle_id')
    tool = TOOLS['update_program_cycle']
    from app.services import ai_program_schema_tools
    ai_program_schema_tools.prepare(tool, args, user, lock=True)
    update_data = {k: args[k] for k in tool.allowed_fields if k in args and args[k] is not None and k != 'expected_revision'}
    try:
        cycle = program_service.update_program_cycle(cycle_id, update_data, user_id=user.id)
        return _detail_result(
            f'Program Cycle {cycle.name} Updated',
            program_service._serialize_program_cycle(cycle),
            summary=f'Successfully updated program cycle {cycle.name}.',
        )
    except program_service.ProgramError as exc:
        if ai_program_schema_tools.applies(tool, args):
            from app.extensions import db
            db.session.rollback()
        _raise_scoped_tool_error(exc)


def _tool_create_project(args, user):
    try:
        project = project_service.create_project(
            lgu_id=_int_arg(args, 'lgu_id'),
            program_id=_int_arg(args, 'program_id'),
            project_name=_text_arg(args, 'project_name'),
            fiscal_year=_int_arg(args, 'fiscal_year'),
            program_cycle_id=_int_arg(args, 'program_cycle_id'),
            source_project_code=_text_arg(args, 'source_project_code'),
            source_row_key=_text_arg(args, 'source_row_key'),
            source_sheet_name=_text_arg(args, 'source_sheet_name'),
            current_phase=_text_arg(args, 'current_phase', 'pre_implementation') or 'pre_implementation',
            overall_status=_text_arg(args, 'overall_status', 'not_yet_started') or 'not_yet_started',
            budget_amount=args.get('budget_amount'),
            target_start_date=args.get('target_start_date'),
            target_end_date=args.get('target_end_date'),
            project_kind=args.get('project_kind'),
            monitoring_applicability=args.get('monitoring_applicability'),
            qaar_category=args.get('qaar_category'),
            subaybayan_project_code=args.get('subaybayan_project_code'),
            subaybayan_url=args.get('subaybayan_url'),
            nadai_received_at=args.get('nadai_received_at'),
            subaybayan_enrolled_at=args.get('subaybayan_enrolled_at'),
            subaybayan_enrollment_status=args.get('subaybayan_enrollment_status'),
            notes=args.get('notes'),
            custom_fields=args.get('custom_fields'),
            user_id=user.id,
        )
        return _detail_result(
            f'Project Created: {project.project_name}',
            project_service._serialize_project(project),
            summary=f'Successfully created Project #{project.id} ({project.project_name}) in {project.lgu.name if project.lgu else "LGU"}.',
        )
    except (project_service.ProjectError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_project_metadata(args, user):
    project_id = _int_arg(args, 'project_id')
    tool = TOOLS['update_project_metadata']
    update_data = {k: args[k] for k in tool.allowed_fields if k in args and args[k] is not None}
    try:
        project = project_service.update_project(project_id, update_data, user_id=user.id)
        return _detail_result(
            f'Project #{project.id} Metadata Updated',
            project_service._serialize_project(project),
            summary=f'Successfully updated metadata for Project #{project.id} ({project.project_name}).',
        )
    except (project_service.ProjectError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_project_budget(args, user):
    project_id = _int_arg(args, 'project_id')
    update_data = {
        'budget_amount': args.get('budget_amount'),
    }
    if args.get('notes'):
        update_data['notes'] = args.get('notes')
    try:
        project = project_service.update_project(project_id, update_data, user_id=user.id)
        budget_str = f"₱{float(project.budget_amount):,.2f}" if project.budget_amount else "₱0.00"
        return _detail_result(
            f'Project #{project.id} Budget Updated',
            project_service._serialize_project(project),
            summary=f'Successfully updated budget for Project #{project.id} ({project.project_name}) to {budget_str}.',
        )
    except (project_service.ProjectError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_create_monthly_progress_report(args, user):
    data = {
        'project_id': _int_arg(args, 'project_id'),
        'reporting_period': _text_arg(args, 'reporting_period'),
        'assessment_date': args.get('assessment_date'),
        'self_reported_actual_pct': args.get('self_reported_actual_pct'),
        'target_to_date_pct': args.get('target_to_date_pct'),
        'budget_utilization_pct': args.get('budget_utilization_pct'),
        'financial_progress_amount': args.get('financial_progress_amount'),
        'qaar_inspection_id': args.get('qaar_inspection_id'),
        'evidence_submission_id': args.get('evidence_submission_id'),
    }
    try:
        report = monthly_progress_service.create_report(data, user_id=user.id)
        return _detail_result(
            f'Monthly Progress Report Created ({report.reporting_period})',
            monthly_progress_service._serialize_report(report),
            summary=f'Successfully created Monthly Progress Report for Project #{report.project_id} ({report.reporting_period}).',
        )
    except (monthly_progress_service.MonthlyProgressError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_create_form3_request(args, user):
    data = {
        'project_id': _int_arg(args, 'project_id'),
        'reporting_period': _text_arg(args, 'reporting_period'),
        'delay_reason_category': args.get('delay_reason_category'),
        'justification_text': args.get('justification_text'),
        'requested_exemption_start': args.get('requested_exemption_start'),
        'requested_exemption_end': args.get('requested_exemption_end'),
        'mov_submission_id': args.get('mov_submission_id'),
    }
    try:
        request = form3_service.create_request(data, user_id=user.id)
        return _detail_result(
            f'Form 3 Request Created ({request.reporting_period})',
            form3_service._serialize_request(request),
            summary=f'Successfully created Form 3 request for Project #{request.project_id} ({request.reporting_period}).',
        )
    except (form3_service.Form3Error, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_create_non_infra_monitoring_record(args, user):
    data = {
        'project_id': _int_arg(args, 'project_id'),
        'template_type': _text_arg(args, 'template_type'),
        'appendix_reference': args.get('appendix_reference'),
        'reporting_period': args.get('reporting_period'),
        'items_verified_summary': args.get('items_verified_summary'),
        'specifications_met': args.get('specifications_met'),
        'remarks': args.get('remarks'),
    }
    try:
        record = non_infra_monitoring_service.create_record(data, user_id=user.id)
        template_label = non_infra_monitoring_service.format_template_type(record.template_type)
        return _detail_result(
            f'Non-Infra Monitoring Record Created',
            non_infra_monitoring_service._serialize_record(record),
            summary=f'Successfully created {template_label} monitoring record for Project #{record.project_id}.',
        )
    except (non_infra_monitoring_service.NonInfraMonitoringError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_create_beneficiary_evidence_record(args, user):
    data = {
        'project_id': _int_arg(args, 'project_id'),
        'evidence_type': _text_arg(args, 'evidence_type'),
        'appendix_reference': args.get('appendix_reference'),
        'beneficiary_count': args.get('beneficiary_count'),
        'distribution_date': args.get('distribution_date'),
        'reference_number': args.get('reference_number'),
        'description': args.get('description'),
    }
    try:
        record = beneficiary_evidence_service.create_record(data, user_id=user.id)
        return _detail_result(
            f'Beneficiary Evidence Record Created',
            beneficiary_evidence_service._serialize_record(record),
            summary=f'Successfully created beneficiary evidence record for Project #{record.project_id}.',
        )
    except (beneficiary_evidence_service.BeneficiaryEvidenceError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_create_monitoring_inspection(args, user):
    data = {
        'project_id': _int_arg(args, 'project_id'),
        'inspection_date': _text_arg(args, 'inspection_date'),
        'monitoring_type': args.get('monitoring_type', 'qaar'),
        'physical_accomplishment_pct': args.get('physical_accomplishment_pct'),
        'observation_summary': args.get('observation_summary'),
        'findings': args.get('findings'),
        'recommendations': args.get('recommendations'),
        'agreement_summary': args.get('agreement_summary'),
        'issues_identified': args.get('issues_identified'),
        'is_site_visit': args.get('is_site_visit', True),
        'status': args.get('status', 'draft'),
    }
    try:
        inspection = monitoring_service.create_inspection(data, user_id=user.id)
        return _detail_result(
            f'Monitoring Inspection Created',
            monitoring_service._serialize_inspection(inspection),
            summary=f'Successfully recorded monitoring inspection for Project #{inspection.project_id}.',
        )
    except (monitoring_service.MonitoringError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_project_lgu_assignment(args, user):
    project_id = _int_arg(args, 'project_id')
    new_lgu_id = _int_arg(args, 'lgu_id')
    notes = _text_arg(args, 'notes')
    payload = {'lgu_id': new_lgu_id}
    if notes:
        payload['notes'] = notes
    try:
        project = project_service.update_project(project_id, payload, user_id=user.id)
        return _detail_result(
            f'Project #{project.id} Reassigned',
            project_service._serialize_project(project),
            summary=f"Project #{project.id} ({project.project_name}) territorial assignment successfully updated to LGU #{new_lgu_id} ({project.lgu.name if project.lgu else ''}).",
        )
    except (project_service.ProjectError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_project_cycle(args, user):
    project_id = _int_arg(args, 'project_id')
    cycle_id = _int_arg(args, 'program_cycle_id')
    notes = _text_arg(args, 'notes')
    try:
        cycle = program_service.get_program_cycle(cycle_id)
        payload = {
            'program_cycle_id': cycle.id,
            'fiscal_year': cycle.fiscal_year,
        }
        if notes:
            payload['notes'] = notes
        project = project_service.update_project(project_id, payload, user_id=user.id)
        return _detail_result(
            f'Project #{project.id} Cycle Reassigned',
            project_service._serialize_project(project),
            summary=f"Project #{project.id} ({project.project_name}) successfully reassigned to program cycle '{cycle.name}' (FY {cycle.fiscal_year}).",
        )
    except (program_service.ProgramError, project_service.ProjectError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_project_status(args, user):
    project_id = _int_arg(args, 'project_id')
    overall_status = _text_arg(args, 'overall_status')
    notes = _text_arg(args, 'notes')
    payload = {'overall_status': overall_status}
    if notes:
        payload['notes'] = notes
    try:
        project = project_service.update_project(project_id, payload, user_id=user.id)
        status_label = project_status_label(project.overall_status)
        return _detail_result(
            f'Project #{project.id} Status Updated',
            project_service._serialize_project(project),
            summary=f"Project #{project.id} ({project.project_name}) status successfully changed to '{status_label}'.",
        )
    except (project_service.ProjectError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_project_schedule(args, user):
    project_id = _int_arg(args, 'project_id')
    payload = {}
    for f in (*PROJECT_SCHEDULE_DATES, 'notes'):
        if f in args and (args[f] is not None or f in PROJECT_TRACKING_DATES):
            payload[f] = args[f]
    try:
        project = project_service.update_project(project_id, payload, user_id=user.id)
        return _detail_result(
            f'Project #{project.id} Schedule Updated',
            project_service._serialize_project(project),
            summary=f"Project #{project.id} ({project.project_name}) milestone schedule successfully updated.",
        )
    except (project_service.ProjectError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_create_sla_deadline(args, user):
    project_id = _int_arg(args, 'project_id')
    deadline_type = _text_arg(args, 'deadline_type')
    trigger_date = args.get('trigger_date')
    deadline_date = args.get('deadline_date')
    sla_working_days = _int_arg(args, 'sla_working_days')
    project_requirement_id = _int_arg(args, 'project_requirement_id')
    notes = _text_arg(args, 'notes')
    try:
        deadline = sla_service.create_sla_deadline(
            project_id=project_id,
            deadline_type=deadline_type,
            trigger_date=trigger_date,
            deadline_date=deadline_date,
            sla_working_days=sla_working_days,
            project_requirement_id=project_requirement_id,
            notes=notes,
            user_id=user.id,
        )
        return _detail_result(
            f'Compliance Deadline #{deadline.id} Created',
            sla_service._serialize_sla_deadline(deadline),
            summary=f"Created {sla_service.format_deadline_type(deadline_type)} deadline for Project #{project_id} due on {deadline.deadline_date.strftime('%Y-%m-%d') if deadline.deadline_date else 'N/A'}.",
        )
    except (sla_service.SlaError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


def _tool_create_notice_draft(args, user):
    project_id = _int_arg(args, 'project_id')
    trigger_sla_id = _int_arg(args, 'trigger_sla_id')
    trigger_project_requirement_id = _int_arg(args, 'trigger_project_requirement_id')
    title = _text_arg(args, 'title')
    final_text = _text_arg(args, 'final_text')
    try:
        notice = notice_service.create_notice(
            project_id=project_id,
            notice_type='annex_e',
            generated_by=user.id,
            trigger_sla_id=trigger_sla_id,
            trigger_project_requirement_id=trigger_project_requirement_id,
            title=title,
            final_text=final_text,
            status='draft',
            user_id=user.id,
        )
        return _detail_result(
            f'Notice Draft #{notice.id} Created',
            escalation_service._serialize_notice(notice, include_detail=True),
            summary=f"Official draft Notice of Deficiency (Annex E) #{notice.id} created for Project #{project_id}. Status: Draft (Not Released).",
        )
    except (notice_service.NoticeError, access_service.AccessError) as exc:
        _raise_scoped_tool_error(exc)


# -------------------------------------------------------------------------
# Phase 9C: Controlled Import Capabilities
# -------------------------------------------------------------------------

def _get_upload_from_stored_object(stored_obj):
    import io
    from pathlib import Path
    from flask import current_app
    from werkzeug.datastructures import FileStorage
    from app.services import object_storage_service
    if not stored_obj:
        raise AiToolError('Attachment not found.', 404)
    filename = stored_obj.original_filename or 'import_file.bin'
    suffix = Path(filename).suffix.lower().lstrip('.')
    if suffix == 'xls':
        raise AiToolError('Legacy .xls files are not supported. Save the workbook as .xlsx or CSV before importing.', 422)
    if suffix not in ('csv', 'xlsx'):
        raise AiToolError(f"Unsupported file type ('.{suffix}'). Only CSV and XLSX files can be imported.", 422)
    try:
        payload = object_storage_service.read_bytes(stored_obj)
    except Exception as exc:
        raise AiToolError(f'Failed to read attachment from storage: {exc}', 404) from exc
    if not payload:
        raise AiToolError('The uploaded file is empty (0 bytes).', 422)
    max_size = int(current_app.config.get('MAX_IMPORT_FILE_BYTES') or (25 * 1024 * 1024))
    if len(payload) > max_size:
        raise AiToolError(f'Import file exceeds maximum allowed size ({max_size // (1024 * 1024)} MB).', 422)
    return FileStorage(
        stream=io.BytesIO(payload),
        filename=filename,
        content_type=stored_obj.content_type or ('text/csv' if suffix == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        name='file',
    )


def _tool_preview_import(args, user):
    if not user or user.role != 'admin':
        raise AiToolError('Administrative permissions required. Only administrators can preview or perform imports.', 403)

    from app.extensions import db
    from app.models import StoredObject, ImportBatch, Program
    from app.services import batch_import_service, import_service

    raw_target = str(args.get('target') or '').strip().lower()
    if raw_target in ('users', 'user', 'accounts', 'internal users'):
        raise AiToolError(
            'Batch import of user accounts involves sensitive authorization controls and must be performed directly through the Admin Batch Import UI.',
            422,
        )

    attachment_id = _int_arg(args, 'attachment_id')
    batch_id = _int_arg(args, 'batch_id')

    if not attachment_id and not batch_id:
        raise AiToolError('An uploaded attachment (attachment_id) or staged import batch (batch_id) is required to preview.', 422)

    stored = None
    if attachment_id:
        stored = db.session.get(StoredObject, attachment_id)
        if not stored:
            raise AiToolError(f'Attachment #{attachment_id} not found.', 404)

    is_workbook = raw_target in ('workbook', 'workbooks', 'project', 'projects', 'project_workbook') or bool(batch_id)

    if is_workbook:
        if batch_id:
            batch = db.session.get(ImportBatch, batch_id)
            if not batch:
                raise AiToolError(f'Import batch #{batch_id} not found.', 404)
            b_id = batch.id
            if batch.stored_object_id:
                stored = db.session.get(StoredObject, batch.stored_object_id)
        else:
            program_id = _int_arg(args, 'program_id')
            if not program_id:
                raise AiToolError('program_id is required to preview a program workbook import.', 422)
            program = db.session.get(Program, program_id)
            if not program:
                raise AiToolError(f'Program #{program_id} not found.', 404)
            upload = _get_upload_from_stored_object(stored)
            cycle_id = _int_arg(args, 'program_cycle_id')
            template_id = _int_arg(args, 'import_template_id')
            try:
                batch_data = import_service.upload_workbook(
                    program_id=program.id,
                    upload=upload,
                    program_cycle_id=cycle_id,
                    import_template_id=template_id,
                    user_id=user.id,
                )
                b_id = batch_data['id']
                import_service.map_workbook(b_id, user_id=user.id)
            except import_service.ImportError as exc:
                raise AiToolError(exc.message, exc.status_code) from exc

        try:
            preview_res = import_service.preview_workbook(b_id, user_id=user.id)
        except import_service.ImportError as exc:
            raise AiToolError(exc.message, exc.status_code) from exc

        summary = preview_res.get('summary') or {}
        p_summary = summary.get('projects') or {}
        r_summary = summary.get('requirements') or {}
        l_summary = summary.get('lgus') or {}

        sample_rows = []
        for r in (summary.get('rows') or [])[:10]:
            sample_rows.append({
                'sheet': r.get('sheet'),
                'row': r.get('row_number'),
                'action': r.get('action'),
                'project_name': r.get('project_name'),
                'lgu': r.get('lgu_name'),
                'errors': r.get('errors') or [],
            })

        error_rows = [r for r in (summary.get('rows') or []) if r.get('action') == 'error'][:10]

        data = {
            'target': 'workbook',
            'import_family': 'workbook',
            'batch_id': b_id,
            'dry_run': True,
            'source_file': stored.original_filename if stored else 'staged_workbook.xlsx',
            'file_hash': stored.sha256_hash if stored else None,
            'attachment_id': stored.id if stored else None,
            'summary': {
                'total_rows': len(summary.get('rows') or []),
                'new_projects': p_summary.get('new', 0),
                'updated_projects': p_summary.get('updates', 0),
                'skipped_projects': p_summary.get('skipped', 0),
                'invalid_projects': p_summary.get('invalid', 0),
                'matched_lgus': l_summary.get('matched', 0),
                'detected_requirements': r_summary.get('detected', 0),
                'similar_warnings': r_summary.get('similar_warnings', 0),
            },
            'sample_rows': sample_rows,
            'errors': error_rows,
            'transaction_semantics': 'Whole-batch atomic commit (all valid projects and requirements are committed together; invalid rows block commit).',
            'notice': 'Preview completed. Zero operational projects or requirements were created. Confirm to commit.',
        }
        from app.services.ai_import_tools import issue_receipt
        data.update(issue_receipt({'target': 'workbook', 'batch_id': b_id}, user))
        return _detail_result(
            f'Workbook Import Preview (Batch #{b_id})',
            data,
            summary=(
                f"Workbook preview completed for Batch #{b_id}: {p_summary.get('new', 0)} new project(s), "
                f"{p_summary.get('updates', 0)} update(s), {p_summary.get('invalid', 0)} error(s). "
                "No operational database changes have been made."
            ),
        )
    else:
        norm_target = raw_target or 'lgus'
        if norm_target in batch_import_service.TARGET_ALIASES:
            norm_target = batch_import_service.TARGET_ALIASES[norm_target]
        if norm_target not in ('clusters', 'lgus', 'programs'):
            raise AiToolError(f"Unsupported batch import target '{raw_target}'. Supported targets: clusters, lgus, programs, workbook.", 422)

        upload = _get_upload_from_stored_object(stored)
        try:
            res = batch_import_service.process_upload(norm_target, upload, user.id, dry_run=True)
        except batch_import_service.BatchImportError as exc:
            raise AiToolError(exc.message, exc.status_code) from exc

        summary = res.get('summary') or {}
        sample_rows = res.get('rows', [])[:10]
        error_rows = [r for r in res.get('rows', []) if r.get('status') == 'failed'][:10]

        data = {
            'target': norm_target,
            'target_label': res.get('target_label'),
            'import_family': 'batch_import',
            'dry_run': True,
            'source_file': stored.original_filename,
            'file_hash': stored.sha256_hash,
            'attachment_id': stored.id,
            'summary': {
                'total_rows': res['file']['row_count'],
                'ready': summary.get('ready', 0),
                'skipped': summary.get('skipped', 0),
                'failed': summary.get('failed', 0),
                'valid_for_commit': summary.get('valid_for_commit', 0),
            },
            'sample_rows': sample_rows,
            'errors': error_rows,
            'transaction_semantics': 'Row-level processing (valid rows are committed individually; invalid rows fail without rolling back valid rows).',
            'notice': 'Preview completed. No operational records were created or updated. Confirm to commit.',
        }
        from app.services.ai_import_tools import issue_receipt
        data.update(issue_receipt({'target': norm_target, 'attachment_id': stored.id}, user))
        return _detail_result(
            f'Batch Import Preview: {res.get("target_label")}',
            data,
            summary=(
                f"Import preview for {res.get('target_label')}: {summary.get('ready', 0)} ready, "
                f"{summary.get('skipped', 0)} skipped, {summary.get('failed', 0)} invalid. "
                "No operational records have been changed. Preview and conversation data may be saved."
            ),
        )


def _tool_commit_import(args, user):
    if not user or user.role != 'admin':
        raise AiToolError('Administrative permissions required. Only administrators can perform imports.', 403)

    from app.extensions import db
    from app.models import StoredObject, ImportBatch, ImportRow
    from app.services import batch_import_service, import_service, audit_service

    raw_target = str(args.get('target') or '').strip().lower()
    if raw_target in ('users', 'user', 'accounts', 'internal users'):
        raise AiToolError(
            'Batch import of user accounts involves sensitive authorization controls and must be performed directly through the Admin Batch Import UI.',
            422,
        )

    attachment_id = _int_arg(args, 'attachment_id')
    batch_id = _int_arg(args, 'batch_id')
    file_hash = args.get('file_hash')
    confirm_similar = bool(args.get('confirm_similar_requirements', False))

    is_workbook = raw_target in ('workbook', 'workbooks', 'project', 'projects', 'project_workbook') or bool(batch_id)

    if is_workbook:
        if not batch_id:
            raise AiToolError('batch_id is required to commit a program workbook import.', 422)
        batch = db.session.get(ImportBatch, batch_id)
        if not batch:
            raise AiToolError(f'Import batch #{batch_id} not found.', 404)
        if batch.status == 'committed':
            raise AiToolError('This import batch has already been committed.', 409)
        if batch.status != 'previewed':
            raise AiToolError(f'Import batch #{batch_id} must be in previewed state (currently: {batch.status}). Please preview before committing.', 422)

        if batch.stored_object_id:
            stored = db.session.get(StoredObject, batch.stored_object_id)
            if not stored:
                raise AiToolError('Source attachment for this workbook was deleted. Please re-upload and preview.', 404)
            if file_hash and stored.sha256_hash != file_hash:
                raise AiToolError('The workbook file has changed since preview. Please generate a new preview before committing.', 422)

        blocking = ImportRow.query.filter_by(import_batch_id=batch.id, action='error').count()
        if blocking > 0:
            raise AiToolError(f'Cannot commit workbook: {blocking} invalid row(s) found. All rows must be valid before whole-batch commit.', 422)

        try:
            commit_res = import_service.commit_workbook(batch.id, user_id=user.id, confirm_similar_requirements=confirm_similar,
                expected_preview_fingerprint=args['preview_fingerprint'])
        except import_service.ImportError as exc:
            raise AiToolError(exc.message, exc.status_code) from exc

        committed = commit_res.get('committed') or {}
        data = {
            'success': True,
            'operation': 'import_commit',
            'import_family': 'workbook',
            'target': 'workbook',
            'import_batch_id': batch.id,
            'source_file': batch.original_file_name,
            'created_projects': committed.get('created_projects', 0),
            'updated_projects': committed.get('updated_projects', 0),
            'requirements': committed.get('requirements', 0),
            'skipped': committed.get('skipped', 0),
            'workbook_workspace_id': committed.get('workbook_workspace_id'),
            'transaction_semantics': 'Whole-batch atomic commit (all projects and requirements committed together).',
        }
        return _detail_result(
            f'Workbook Import #{batch.id} Committed',
            data,
            summary=(
                f"Workbook import committed atomically: {committed.get('created_projects', 0)} project(s) created, "
                f"{committed.get('updated_projects', 0)} updated, {committed.get('requirements', 0)} requirement(s) staged."
            ),
        )
    else:
        if not attachment_id:
            raise AiToolError('attachment_id is required to commit an administrative batch import.', 422)
        stored = db.session.get(StoredObject, attachment_id)
        if not stored:
            raise AiToolError(f'Attachment #{attachment_id} not found.', 404)
        if file_hash and stored.sha256_hash != file_hash:
            raise AiToolError('The uploaded file has changed since the preview was generated. Please run a new preview before committing.', 422)

        norm_target = raw_target or 'lgus'
        if norm_target in batch_import_service.TARGET_ALIASES:
            norm_target = batch_import_service.TARGET_ALIASES[norm_target]
        if norm_target not in ('clusters', 'lgus', 'programs'):
            raise AiToolError(f"Unsupported batch import target '{raw_target}'. Supported targets: clusters, lgus, programs, workbook.", 422)

        upload = _get_upload_from_stored_object(stored)
        try:
            res = batch_import_service.process_upload(norm_target, upload, user.id, dry_run=False)
        except batch_import_service.BatchImportError as exc:
            raise AiToolError(exc.message, exc.status_code) from exc

        summary = res.get('summary') or {}
        audit_service.log_action(
            user_id=user.id,
            action='commit_batch_import',
            entity_type='batch_import',
            entity_id=stored.id,
            old_value=None,
            new_value={
                'target': norm_target,
                'attachment_id': stored.id,
                'filename': stored.original_filename,
                'sha256_hash': stored.sha256_hash,
                'row_count': res['file']['row_count'],
                'created': summary.get('created', 0),
                'skipped': summary.get('skipped', 0),
                'failed': summary.get('failed', 0),
            },
        )
        db.session.commit()

        data = {
            'success': summary.get('failed', 0) == 0,
            'operation': 'import_commit',
            'import_family': 'batch_import',
            'target': norm_target,
            'source_file': stored.original_filename,
            'total_rows': res['file']['row_count'],
            'created': summary.get('created', 0),
            'skipped': summary.get('skipped', 0),
            'rejected': summary.get('failed', 0),
            'transaction_semantics': 'Row-level processing (valid rows were committed individually; rejected rows remained unapplied).',
            'rows': res.get('rows', [])[:20],
        }
        return _detail_result(
            f'Batch Import: {res.get("target_label")}',
            data,
            summary=(
                f"Batch import completed: {summary.get('created', 0)} created, "
                f"{summary.get('skipped', 0)} skipped, {summary.get('failed', 0)} rejected. "
                "Row-level transaction: valid rows were committed."
            ),
        )


def _serialize_safe_user(user):
    """Serialize user for Smart Assistant display, strictly omitting security/auth secrets."""
    if not user:
        return {}
    assigned_clusters = [
        {
            'cluster_id': a.cluster_id,
            'cluster_name': a.cluster.name if a.cluster else None,
            'is_active': a.is_active,
        }
        for a in getattr(user, 'lgu_assignments', [])
        if a.is_active and a.scope_type == 'cluster'
    ]
    assigned_lgus = [
        {
            'lgu_id': a.lgu_id,
            'lgu_name': a.lgu.name if a.lgu else None,
            'is_active': a.is_active,
        }
        for a in getattr(user, 'lgu_assignments', [])
        if a.is_active and a.scope_type == 'lgu'
    ]
    return {
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.full_name,
        'role': user.role,
        'is_active': user.is_active,
        'assigned_clusters': assigned_clusters,
        'assigned_lgus': assigned_lgus,
        'created_at': user.created_at.isoformat() if getattr(user, 'created_at', None) else None,
    }


def _tool_create_user(args, user):
    if not user or user.role != 'admin':
        raise AiToolError('Administrative permissions required. Only administrators can create user accounts.', 403)
    target_role = str(args.get('role') or '').strip().lower()
    if target_role in ('system_admin', 'system administrator', 'sysadmin'):
        raise AiToolError('Operational Admins cannot manage System Administrator (System Admin) accounts.', 403)
    if target_role not in ('admin', 'staff', 'field_officer'):
        raise AiToolError(f"Invalid role '{target_role}'. Allowed roles: admin, staff, field_officer.", 422)

    try:
        from app.services import auth_service
        res = auth_service.create_user_account(
            admin_id=user.id,
            email=args['email'],
            first_name=args['first_name'],
            last_name=args['last_name'],
            role=target_role,
            cluster_ids=args.get('cluster_ids'),
            lgu_ids=args.get('lgu_ids'),
        )
        created_dict = res.get('user') or {}
        from app.models import User
        from app.extensions import db
        u_model = db.session.get(User, created_dict.get('id'))
        safe_user = _serialize_safe_user(u_model) if u_model else created_dict

        delivery = res.get('delivery') or {}
        sanitized_delivery = {
            'status': delivery.get('status', 'sent'),
            'message': 'Account provisioned successfully. Temporary credentials have been securely generated and dispatched via email.',
        }

        role_label = auth_service.format_role(safe_user.get('role'))

        return _detail_result(
            f"User Created: {safe_user.get('full_name')}",
            {
                'user': safe_user,
                'delivery': sanitized_delivery,
            },
            summary=(
                f"Successfully created user account #{safe_user.get('id')} "
                f"({safe_user.get('full_name')} <{safe_user.get('email')}>, Role: {role_label}). "
                "Temporary credentials have been dispatched via email. No credentials are shown conversationally."
            ),
        )
    except auth_service.AuthError as exc:
        _raise_scoped_tool_error(exc)


def _tool_update_user_profile(args, user):
    if not user or user.role != 'admin':
        raise AiToolError('Administrative permissions required. Only administrators can update user profiles.', 403)
    user_id = _int_arg(args, 'user_id')
    if not user_id:
        raise AiToolError('user_id is required.', 422)

    from app.models import User
    from app.extensions import db
    from app.services import audit_service
    from sqlalchemy import func

    target = db.session.get(User, user_id)
    if not target:
        raise AiToolError(f'User #{user_id} not found.', 404)
    if target.role == 'system_admin':
        raise AiToolError('Operational Admins cannot manage System Administrator (System Admin) accounts.', 403)

    before_safe = _serialize_safe_user(target)
    changes_made = {}

    if 'first_name' in args and args['first_name'] is not None:
        val = str(args['first_name']).strip()
        if val and val != target.first_name:
            changes_made['first_name'] = {'old': target.first_name, 'new': val}
            target.first_name = val

    if 'last_name' in args and args['last_name'] is not None:
        val = str(args['last_name']).strip()
        if val and val != target.last_name:
            changes_made['last_name'] = {'old': target.last_name, 'new': val}
            target.last_name = val

    if 'email' in args and args['email'] is not None:
        new_email = str(args['email']).strip().lower()
        if '@' not in new_email:
            raise AiToolError('Invalid email format.', 422)
        existing = User.query.filter(
            func.lower(func.trim(User.email)) == new_email,
            User.id != target.id,
        ).first()
        if existing:
            raise AiToolError('Email already in use.', 409)
        if new_email != target.email:
            changes_made['email'] = {'old': target.email, 'new': new_email}
            target.email = new_email

    if not changes_made:
        raise AiToolError('No field changes detected for user profile update.', 422)

    db.session.commit()
    after_safe = _serialize_safe_user(target)

    audit_service.log_action(
        user_id=user.id,
        action='update',
        entity_type='user',
        entity_id=target.id,
        old_value=before_safe,
        new_value=after_safe,
    )

    diff_lines = [f"{k}: {v['old']} → {v['new']}" for k, v in changes_made.items()]
    diff_text = ", ".join(diff_lines)

    return _detail_result(
        f"User Profile Updated: {after_safe['full_name']}",
        after_safe,
        summary=f"Successfully updated profile for user #{target.id} ({after_safe['full_name']}): {diff_text}.",
    )


def _tool_bulk_update_project_metadata(args, user):
    from app.services import bulk_project_service
    try:
        res = bulk_project_service.execute_bulk_project_update(
            operation='bulk_update_project_metadata',
            target_ids=args.get('target_ids') or [],
            updates=args.get('updates') or {},
            preview_fingerprint=args.get('preview_fingerprint'),
            selection=args.get('selectors') or {},
            user_id=user.id,
        )
        return _detail_result(
            f"Bulk Metadata Update: {res['changed_count']} Projects Updated",
            res,
            summary=f"Successfully updated metadata across {res['changed_count']} projects ({res['unchanged_count']} already up to date). Changes committed atomically with full audit history.",
        )
    except bulk_project_service.BulkProjectError as exc:
        raise AiToolError(exc.message, exc.status_code)


def _tool_bulk_update_project_schedule(args, user):
    from app.services import bulk_project_service
    try:
        res = bulk_project_service.execute_bulk_project_update(
            operation='bulk_update_project_schedule',
            target_ids=args.get('target_ids') or [],
            updates=args.get('updates') or {},
            preview_fingerprint=args.get('preview_fingerprint'),
            selection=args.get('selectors') or {},
            user_id=user.id,
        )
        return _detail_result(
            f"Bulk Schedule Update: {res['changed_count']} Projects Updated",
            res,
            summary=f"Successfully updated schedule dates across {res['changed_count']} projects ({res['unchanged_count']} already up to date). Changes committed atomically with full audit history.",
        )
    except bulk_project_service.BulkProjectError as exc:
        raise AiToolError(exc.message, exc.status_code)


def _tool_bulk_update_project_status(args, user):
    from app.services import bulk_project_service
    try:
        res = bulk_project_service.execute_bulk_project_update(
            operation='bulk_update_project_status',
            target_ids=args.get('target_ids') or [],
            updates=args.get('updates') or {},
            preview_fingerprint=args.get('preview_fingerprint'),
            selection=args.get('selectors') or {},
            user_id=user.id,
        )
        target_status = res.get('updates', {}).get('overall_status', '')
        status_label = project_status_label(target_status)
        summary = (
            f"Successfully updated operational status to canonical '{status_label}' across {res['changed_count']} "
            f"project(s) ({res['unchanged_count']} already up to date). Changes committed atomically with full audit history."
        )
        return _detail_result(
            f"Bulk Status Update: {res['changed_count']} Projects Updated",
            res,
            summary=summary,
        )
    except bulk_project_service.BulkProjectError as exc:
        raise AiToolError(exc.message, exc.status_code)


TOOLS = {
    'create_lgu': ToolDefinition(
        name='create_lgu',
        description='Register a new municipal Local Government Unit (LGU) in {app_name}. Requires confirmation and admin role.',
        roles=('admin',),
        risk_level='high',
        requires_confirmation=True,
        required_args=('name', 'municipality'),
        allowed_fields=('name', 'municipality', 'province', 'cluster_id', 'mayor_name', 'mayor_email',
                        'contact_person', 'contact_email', 'contact_phone'),
        display_type='detail',
        executor=_tool_create_lgu,
        operation_type='create',
        scope_type='province',
        canonical_service='lgu_service.create_lgu',
    ),
    'update_lgu': ToolDefinition(
        name='update_lgu',
        description='Update an existing Local Government Unit (LGU) profile. Requires confirmation and admin role.',
        roles=('admin',),
        risk_level='medium',
        requires_confirmation=True,
        required_args=('lgu_id',),
        display_type='detail',
        executor=_tool_update_lgu,
        operation_type='update',
        scope_type='province',
        canonical_service='lgu_service.update_lgu',
        allowed_fields=('name', 'municipality', 'province', 'cluster_id', 'mayor_name', 'mayor_email', 'contact_person', 'contact_email', 'contact_phone', 'is_active'),
    ),
    'create_cluster': ToolDefinition(
        name='create_cluster',
        description='Create a new LGU cluster. Requires confirmation and admin role.',
        roles=('admin',),
        risk_level='high',
        requires_confirmation=True,
        required_args=('name',),
        allowed_fields=('name', 'description'),
        display_type='detail',
        executor=_tool_create_cluster,
        operation_type='create',
        scope_type='province',
        canonical_service='lgu_service.create_cluster',
    ),
    'update_cluster': ToolDefinition(
        name='update_cluster',
        description='Update an existing LGU cluster name or description. Requires confirmation and admin role.',
        roles=('admin',),
        risk_level='medium',
        requires_confirmation=True,
        required_args=('cluster_id',),
        display_type='detail',
        executor=_tool_update_cluster,
        operation_type='update',
        scope_type='province',
        canonical_service='lgu_service.update_cluster',
        allowed_fields=('name', 'description'),
    ),
    'create_program': ToolDefinition(
        name='create_program',
        description='Register a new funding program in {app_name}. Requires confirmation and admin role.',
        roles=('admin',),
        risk_level='high',
        requires_confirmation=True,
        required_args=('name', 'code', 'program_type'),
        allowed_fields=('name', 'code', 'program_type', 'description', 'funding_agency', 'project_custom_field_schema'),
        display_type='detail',
        executor=_tool_create_program,
        operation_type='create',
        scope_type='province',
        canonical_service='program_service.create_program',
    ),
    'update_program': ToolDefinition(
        name='update_program',
        description='Update a funding program profile or replace project_custom_field_schema with a complete JSON object ({} clears it). Does not migrate existing project values. Requires confirmation and admin role.',
        roles=('admin',),
        risk_level='high',
        requires_confirmation=True,
        required_args=('program_id',),
        display_type='detail',
        executor=_tool_update_program,
        operation_type='update',
        scope_type='province',
        canonical_service='program_service.update_program',
        allowed_fields=('name', 'code', 'program_type', 'description', 'funding_agency', 'is_active', 'project_custom_field_schema', 'expected_revision'),
    ),
    'create_program_cycle': ToolDefinition(
        name='create_program_cycle',
        description='Create a new operational program cycle for a funding program. Requires confirmation and admin role.',
        roles=('admin',),
        risk_level='high',
        requires_confirmation=True,
        required_args=('program_id', 'name', 'fiscal_year', 'cycle_code'),
        allowed_fields=('program_id', 'name', 'fiscal_year', 'cycle_code', 'source_template_name', 'import_profile', 'field_schema'),
        display_type='detail',
        executor=_tool_create_program_cycle,
        operation_type='create',
        scope_type='province',
        canonical_service='program_service.create_program_cycle',
    ),
    'update_program_cycle': ToolDefinition(
        name='update_program_cycle',
        description='Update a program cycle or replace import_profile/field_schema with complete JSON objects ({} clears an object). Does not reprocess imports or rewrite bindings. Requires confirmation and admin role.',
        roles=('admin',),
        risk_level='medium',
        requires_confirmation=True,
        required_args=('cycle_id',),
        display_type='detail',
        executor=_tool_update_program_cycle,
        operation_type='update',
        scope_type='province',
        canonical_service='program_service.update_program_cycle',
        allowed_fields=('name', 'fiscal_year', 'cycle_code', 'source_template_name', 'is_active', 'import_profile', 'field_schema', 'expected_revision'),
    ),
    'create_project': ToolDefinition(
        name='create_project',
        description='Create a new project under an authorized LGU and Program. Requires confirmation. Staff restricted to assigned cluster.',
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('lgu_id', 'program_id', 'project_name', 'fiscal_year'),
        allowed_fields=('lgu_id', 'program_id', 'project_name', 'fiscal_year', 'program_cycle_id',
                        'source_project_code', 'source_row_key', 'source_sheet_name', 'current_phase', 'overall_status',
                        'budget_amount', 'target_start_date', 'target_end_date', 'project_kind', 'monitoring_applicability',
                        'qaar_category', 'subaybayan_project_code', 'subaybayan_url', 'notes', 'custom_fields',
                        'nadai_received_at', 'subaybayan_enrolled_at', 'subaybayan_enrollment_status'),
        display_type='detail',
        executor=_tool_create_project,
        operation_type='create',
        scope_type='cluster',
        canonical_service='project_service.create_project',
    ),
    'update_project_metadata': ToolDefinition(
        name='update_project_metadata',
        description='Update general project details such as name, target dates, codes, notes, and custom fields. Dedicated actions exist for budget, assigned LGU, program cycle, and lifecycle phase. Requires confirmation.',
        roles=('admin', 'staff'),
        risk_level='medium',
        requires_confirmation=True,
        required_args=('project_id',),
        display_type='detail',
        executor=_tool_update_project_metadata,
        operation_type='update',
        scope_type='cluster',
        canonical_service='project_service.update_project',
        allowed_fields=('project_name', 'target_start_date', 'target_end_date', 'notes', 'custom_fields', 'subaybayan_project_code', 'subaybayan_url', 'project_kind', 'qaar_category'),
    ),
    'update_project_budget': ToolDefinition(
        name='update_project_budget',
        description='Update the official budget allocation for a project. Requires confirmation and high-risk approval. Generates budget delta preview.',
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('project_id', 'budget_amount'),
        display_type='detail',
        executor=_tool_update_project_budget,
        operation_type='update',
        scope_type='cluster',
        canonical_service='project_service.update_project',
        allowed_fields=('budget_amount', 'notes'),
    ),
    'create_monthly_progress_report': ToolDefinition(
        name='create_monthly_progress_report',
        description='Create a monthly progress report for a project in a specific period (YYYY-MM). Allowed for admin, staff, and assigned field officers.',
        roles=('admin', 'staff', 'field_officer'),
        risk_level='medium',
        requires_confirmation=False,
        required_args=('project_id', 'reporting_period'),
        display_type='detail',
        executor=_tool_create_monthly_progress_report,
        operation_type='create',
        scope_type='lgu',
        canonical_service='monthly_progress_service.create_report',
    ),
    'create_form3_request': ToolDefinition(
        name='create_form3_request',
        description='Create a Form 3 timeline adjustment/exemption request for a project. Allowed for admin, staff, and assigned field officers.',
        roles=('admin', 'staff', 'field_officer'),
        risk_level='medium',
        requires_confirmation=False,
        required_args=('project_id', 'reporting_period'),
        display_type='detail',
        executor=_tool_create_form3_request,
        operation_type='create',
        scope_type='lgu',
        canonical_service='form3_service.create_request',
    ),
    'create_non_infra_monitoring_record': ToolDefinition(
        name='create_non_infra_monitoring_record',
        description='Create a non-infrastructure monitoring record (goods, vehicle, apm_template) for non-infrastructure projects.',
        roles=('admin', 'staff', 'field_officer'),
        risk_level='medium',
        requires_confirmation=False,
        required_args=('project_id', 'template_type'),
        display_type='detail',
        executor=_tool_create_non_infra_monitoring_record,
        operation_type='create',
        scope_type='lgu',
        canonical_service='non_infra_monitoring_service.create_record',
    ),
    'create_beneficiary_evidence_record': ToolDefinition(
        name='create_beneficiary_evidence_record',
        description='Create a beneficiary evidence record for financial assistance projects.',
        roles=('admin', 'staff', 'field_officer'),
        risk_level='medium',
        requires_confirmation=False,
        required_args=('project_id', 'evidence_type'),
        display_type='detail',
        executor=_tool_create_beneficiary_evidence_record,
        operation_type='create',
        scope_type='lgu',
        canonical_service='beneficiary_evidence_service.create_record',
    ),
    'create_monitoring_inspection': ToolDefinition(
        name='create_monitoring_inspection',
        description='Create a QAAR or monitoring inspection for a project. Allowed for admin and staff within their assigned cluster.',
        roles=('admin', 'staff'),
        risk_level='medium',
        requires_confirmation=False,
        required_args=('project_id', 'inspection_date'),
        display_type='detail',
        executor=_tool_create_monitoring_inspection,
        operation_type='create',
        scope_type='cluster',
        canonical_service='monitoring_service.create_inspection',
    ),
    'update_project_lgu_assignment': ToolDefinition(
        name='update_project_lgu_assignment',
        description="Reassign an existing project's territorial LGU assignment. Requires confirmation and admin/staff role.",
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('project_id', 'lgu_id'),
        display_type='detail',
        executor=_tool_update_project_lgu_assignment,
        operation_type='update',
        scope_type='cluster',
        canonical_service='project_service.update_project',
        allowed_fields=('lgu_id', 'notes'),
    ),
    'update_project_cycle': ToolDefinition(
        name='update_project_cycle',
        description="Reassign an existing project to another active cycle of the same program. Requires confirmation and admin/staff role.",
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('project_id', 'program_cycle_id'),
        display_type='detail',
        executor=_tool_update_project_cycle,
        operation_type='update',
        scope_type='cluster',
        canonical_service='project_service.update_project',
        allowed_fields=('program_cycle_id', 'notes'),
    ),
    'update_project_status': ToolDefinition(
        name='update_project_status',
        description="Update a project's operational status (not_yet_started, ongoing, suspended). Requires confirmation and admin/staff role.",
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('project_id', 'overall_status'),
        display_type='detail',
        executor=_tool_update_project_status,
        operation_type='update',
        scope_type='cluster',
        canonical_service='project_service.update_project',
        allowed_fields=('overall_status', 'notes'),
    ),
    'update_project_schedule': ToolDefinition(
        name='update_project_schedule',
        description="Update a project's target/actual milestone dates, NADAI receipt date or SubayBAYAN enrollment date (YYYY-MM-DD). Null clears a tracking date. Requires confirmation and admin/staff role.",
        roles=('admin', 'staff'),
        risk_level='medium',
        requires_confirmation=True,
        required_args=('project_id',),
        display_type='detail',
        executor=_tool_update_project_schedule,
        operation_type='update',
        scope_type='cluster',
        canonical_service='project_service.update_project',
        allowed_fields=(*PROJECT_SCHEDULE_DATES, 'notes'),
    ),
    'create_sla_deadline': ToolDefinition(
        name='create_sla_deadline',
        description="Create a formal or custom working-day compliance deadline for a project. Requires confirmation and admin/staff role.",
        roles=('admin', 'staff'),
        risk_level='medium',
        requires_confirmation=True,
        required_args=('project_id', 'deadline_type', 'trigger_date', 'deadline_date'),
        display_type='detail',
        executor=_tool_create_sla_deadline,
        operation_type='create',
        scope_type='cluster',
        canonical_service='sla_service.create_sla_deadline',
        allowed_fields=('deadline_type', 'trigger_date', 'deadline_date', 'sla_working_days', 'project_requirement_id', 'notes'),
    ),
    'create_notice_draft': ToolDefinition(
        name='create_notice_draft',
        description="Create an official draft of an Annex E Notice of Deficiency. Requires confirmation and admin/staff role. Does not release or dispatch.",
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('project_id',),
        display_type='detail',
        executor=_tool_create_notice_draft,
        operation_type='create',
        scope_type='cluster',
        canonical_service='notice_service.create_notice',
        allowed_fields=('trigger_sla_id', 'trigger_project_requirement_id', 'title', 'final_text'),
    ),

    
    'query_projects': ToolDefinition(
        name='query_projects',
        description='Flexible query tool for projects with combined filters: search, lgu_id/lgu_name, program_id/program_name, fiscal_year, program_cycle_id, current_phase (pre_implementation/implementation/completion), overall_status (not_yet_started/ongoing/completed/cancelled), has_non_compliant_requirements (true/false).',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_query_projects,
        allowed_fields=('search', 'lgu_id', 'lgu_name', 'program_id', 'program_name', 'fiscal_year',
                        'program_cycle_id', 'current_phase', 'overall_status', 'has_non_compliant_requirements',
                        'project_ids', 'page', 'per_page', 'limit', 'all_fiscal_years'),
    ),
    'query_requirements': ToolDefinition(
        name='query_requirements',
        description='Flexible query tool for requirements with combined filters: project_id, lgu_id/lgu_name, requirement_type (document/certificate/resolution/financial/engineering/inspection/other), compliance_status (pending/under_review/compliant/non_compliant/waived/incomplete/missing/not_applicable), applicability (applicable/not_applicable), workflow_status (draft/submitted/under_verification/staff_approved/pending_provincial_approval/approved/returned_for_revision/resubmitted), overdue (true/false), date_start, date_end, assigned_field_officer (note: this filters for requirements in LGUs territorially assigned to the officer, not individual assignment).',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_query_requirements,
        allowed_fields=('requirement_id', 'project_id', 'lgu_id', 'lgu_name', 'fiscal_year',
                        'requirement_type', 'document_category', 'annex_reference', 'phase', 'phase_name',
                        'is_mandatory', 'mandatory', 'has_sla', 'applicability', 'has_submission', 'has_evidence',
                        'has_open_deficiencies', 'has_deficiencies', 'search', 'q', 'workflow_status',
                        'compliance_status', 'overdue', 'assigned_field_officer', 'date_start', 'date_end',
                        'limit', 'page', 'all_fiscal_years'),
    ),
    'get_requirement_detail': ToolDefinition(
        name='get_requirement_detail',
        description='Get full requirement context, compliance status, workflow transitions, return reason, submission history, document versions (current vs historical), and open/resolved deficiencies for a project requirement.',
        roles=('admin', 'staff', 'field_officer'),
        required_args=('requirement_id',),
        display_type='detail',
        executor=_tool_get_requirement_detail,
        allowed_fields=('requirement_id',),
    ),
    'search_projects': ToolDefinition(
        name='search_projects',
        description='Search visible projects by text, LGU, program, fiscal year, phase, or status.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_search_projects,
        allowed_fields=('search', 'lgu_id', 'program_id', 'fiscal_year', 'program_cycle_id',
                        'current_phase', 'overall_status', 'page', 'per_page', 'all_fiscal_years'),
    ),
    'global_search': ToolDefinition(
        name='global_search',
        description='Search role-scoped projects, requirements, intake, handoff, LGUs, programs, monitoring, guidelines, archive, and completion results.',
        roles=('admin', 'staff', 'field_officer'),
        required_args=('search',),
        display_type='table',
        executor=_tool_global_search,
        allowed_fields=('fiscal_year', 'per_type', 'q', 'search', 'types'),
    ),
    'get_project_overview': ToolDefinition(
        name='get_project_overview',
        description='Get full project context, requirements, phase logs, and source provenance for a visible project.',
        roles=('admin', 'staff', 'field_officer'),
        required_args=('project_id',),
        display_type='detail',
        executor=_tool_get_project_overview,
        allowed_fields=('project_id',),
    ),
    'get_sla_summary': ToolDefinition(
        name='get_sla_summary',
        description='Show working-day deadline metrics for the current user scope.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='metrics',
        executor=_tool_get_sla_summary,
        allowed_fields=('fiscal_year',),
    ),
    'generate_compliance_summary': ToolDefinition(
        name='generate_compliance_summary',
        description='Generate an AI-assisted executive compliance summary from role-scoped projects, working-day deadlines, escalations, and monitoring records.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='detail',
        executor=_tool_generate_compliance_summary,
        allowed_fields=('fiscal_year',),
    ),
    'list_overdue_slas': ToolDefinition(
        name='list_overdue_slas',
        description='List overdue unresolved working-day deadlines in the current user scope. Supports optional project_id and fiscal_year filters.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_list_overdue_slas,
        allowed_fields=('fiscal_year', 'lgu_id', 'lgu_name', 'project_id'),
    ),
    'get_sla_deadline_detail': ToolDefinition(
        name='get_sla_deadline_detail',
        description='Get full detail and status for a specific compliance working-day deadline by Deadline ID (deadline_id or sla_id).',
        roles=('admin', 'staff', 'field_officer'),
        risk_level='low',
        requires_confirmation=False,
        required_args=('deadline_id',),
        display_type='detail',
        executor=_tool_get_sla_deadline_detail,
        allowed_fields=('deadline_id', 'sla_id'),
    ),
    'list_handoff_queue': ToolDefinition(
        name='list_handoff_queue',
        description='List approved documentary requirements awaiting regional Google Drive handoff.',
        roles=('admin', 'staff'),
        display_type='table',
        executor=_tool_list_handoff_queue,
        allowed_fields=('fiscal_year', 'page', 'per_page', 'search'),
    ),
    'list_notices': ToolDefinition(
        name='list_notices',
        description='List notices, reminders, and follow-up records with filters: project_id, lgu_id/lgu_name, notice_type (annex_e/annex_m/annex_n/annex_o/annex_l/reminder_letter), status (draft/reviewed/sent/acknowledged/expired).',
        roles=('admin', 'staff'),
        display_type='table',
        executor=_tool_list_notices,
        allowed_fields=('fiscal_year', 'lgu_id', 'lgu_name', 'notice_type', 'page', 'per_page', 'project_id', 'status', 'trigger_sla_id'),
    ),
    'monitoring_workbench': ToolDefinition(
        name='monitoring_workbench',
        description='Show the QAAR implementation monitoring workbench and current QAAR monitoring state.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_monitoring_workbench,
        allowed_fields=('fiscal_year',),
    ),
    'list_monitoring_inspections': ToolDefinition(
        name='list_monitoring_inspections',
        description='List role-scoped QAAR monitoring records; Aide Memoire and Notice outputs are generated from saved QAAR records.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_list_monitoring_inspections,
        allowed_fields=('fiscal_year', 'monitoring_type', 'monthly_cycle_tag', 'page', 'per_page', 'project_id', 'search', 'status', 'transmittal_status'),
    ),
    'list_non_infra_monitoring_records': ToolDefinition(
        name='list_non_infra_monitoring_records',
        description='List role-scoped non-infrastructure monitoring records (delivery, inspection, specification verification, APM templates) for Goods and Vehicle projects.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_list_non_infra_monitoring_records,
        allowed_fields=('project_id', 'reporting_period', 'template_type', 'workflow_status'),
    ),
    'list_beneficiary_evidence_records': ToolDefinition(
        name='list_beneficiary_evidence_records',
        description='List role-scoped beneficiary evidence records (signed distribution lists, receipts, beneficiary counts, distribution dates) for Financial Assistance projects.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_list_beneficiary_evidence_records,
        allowed_fields=('evidence_type', 'project_id', 'workflow_status'),
    ),
    'settings_readiness': ToolDefinition(
        name='settings_readiness',
        description='Check system setup for database, JWT, SMTP, assistant providers, Google Drive, uploads, and scheduled jobs.',
        roles=('admin', 'staff'),
        display_type='detail',
        executor=_tool_settings_readiness,
        allowed_fields=(),
    ),
    'audit_summary': ToolDefinition(
        name='audit_summary',
        description='Show audit statistics and hash-chain integrity status.',
        roles=('admin',),
        display_type='metrics',
        executor=_tool_audit_summary,
        allowed_fields=(),
    ),
    'list_import_batches': ToolDefinition(
        name='list_import_batches',
        description='List workbook import batches with optional filter by status (uploaded/profiled/mapped/previewed/committed/failed/cancelled).',
        roles=('admin',),
        display_type='table',
        executor=_tool_list_import_batches,
        allowed_fields=('fiscal_year', 'page', 'per_page', 'program_cycle_id', 'program_id', 'status'),
    ),
    'list_guidelines': ToolDefinition(
        name='list_guidelines',
        description='Search guidelines, annexes, circulars, memoranda, and program reference documents.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_list_guidelines,
        allowed_fields=('guideline_type', 'is_current', 'page', 'per_page', 'program_id', 'search'),
    ),
    'resolve_sla_deadline': ToolDefinition(
        name='resolve_sla_deadline',
        description='Mark a working-day deadline as resolved. Requires confirmation.',
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('sla_id',),
        display_type='detail',
        executor=_tool_resolve_sla_deadline,
        operation_type='update',
    ),
    'push_requirement_handoff': ToolDefinition(
        name='push_requirement_handoff',
        description='Upload an approved requirement to the regional handoff destination. Requires confirmation.',
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('requirement_id',),
        display_type='detail',
        executor=_tool_push_requirement_handoff,
        operation_type='update',
    ),
    'generate_notice_for_sla': ToolDefinition(
        name='generate_notice_for_sla',
        description='Prepare the next notice for an overdue working-day deadline. Requires confirmation.',
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('sla_id',),
        display_type='detail',
        executor=_tool_generate_notice_for_sla,
        operation_type='create',
    ),
    'get_field_summary': ToolDefinition(
        name='get_field_summary',
        description='Get the dashboard summary (LGU count, project counts, requirement statuses, SLA summary) for the field officer.',
        roles=('field_officer',),
        display_type='detail',
        executor=_tool_get_field_summary,
        allowed_fields=('fiscal_year',),
    ),
    'list_assigned_lgus': ToolDefinition(
        name='list_assigned_lgus',
        description='List assigned LGUs and their aggregated statistics for the field officer.',
        roles=('field_officer',),
        display_type='table',
        executor=_tool_list_assigned_lgus,
        allowed_fields=('fiscal_year',),
    ),
    'list_action_items': ToolDefinition(
        name='list_action_items',
        description='List priority-sorted action items (returned requirements, pending evidence, overdue SLAs, monitoring findings) for the field officer.',
        roles=('field_officer',),
        display_type='table',
        executor=_tool_list_action_items,
        allowed_fields=('fiscal_year', 'limit'),
    ),
    'create_requirement_comment': ToolDefinition(
        name='create_requirement_comment',
        description='Create a comment on a requirement. Requires confirmation and type/visibility arguments: requirement_id, body, comment_type (comment/field_follow_up/submission_update/clarification/acknowledgement), visibility (internal/field_visible).',
        roles=('field_officer',),
        risk_level='high',
        requires_confirmation=True,
        required_args=('requirement_id', 'body', 'comment_type', 'visibility'),
        display_type='detail',
        executor=_tool_create_requirement_comment,
        operation_type='create',
    ),
    'upload_evidence_from_attachment': ToolDefinition(
        name='upload_evidence_from_attachment',
        description='Upload evidence to a requirement from a previously uploaded chat attachment.',
        roles=('admin', 'staff', 'field_officer'),
        risk_level='high',
        requires_confirmation=True,
        required_args=('requirement_id', 'attachment_id'),
        display_type='detail',
        executor=_tool_upload_evidence_from_attachment,
        operation_type='create',
    ),
    'get_system_readiness': ToolDefinition(
        name='get_system_readiness',
        description='Check technical platform readiness and subsystem health status (database, JWT, SMTP, AI providers, document intelligence, Google Drive, object storage, uploads, and background tasks).',
        roles=('system_admin',),
        risk_level='low',
        requires_confirmation=False,
        display_type='detail',
        executor=_tool_get_system_readiness,
        allowed_fields=(),
    ),
    'query_audit_log': ToolDefinition(
        name='query_audit_log',
        description='Query system audit logs with optional filters: action, entity_type, entity_id, user_id, search, start_date, end_date, limit.',
        roles=('system_admin',),
        risk_level='low',
        requires_confirmation=False,
        display_type='table',
        executor=_tool_query_audit_log,
        allowed_fields=('action', 'end_date', 'entity_id', 'entity_type', 'limit', 'page', 'search', 'start_date', 'user_id'),
    ),
    'trigger_database_backup': ToolDefinition(
        name='trigger_database_backup',
        description='Trigger an immediate snapshot backup of the {app_name} database to object storage (Cloudflare R2 or local durable fallback).',
        roles=('system_admin',),
        risk_level='low',
        requires_confirmation=False,
        display_type='detail',
        executor=_tool_trigger_database_backup,
        operation_type='create',
    ),
    'list_database_backups': ToolDefinition(
        name='list_database_backups',
        description='List database backup archives, including status, file sizes, storage providers, checksums, and timestamps.',
        roles=('system_admin',),
        risk_level='low',
        requires_confirmation=False,
        display_type='table',
        executor=_tool_list_database_backups,
        allowed_fields=('limit', 'page'),
    ),
    'restore_database_backup': ToolDefinition(
        name='restore_database_backup',
        description='Restore the database from an existing backup archive. Requires exact confirmation phrase CONFIRM-RESTORE-OVERWRITE. Target database can be explicitly specified for sandbox/testing.',
        roles=('system_admin',),
        risk_level='critical',
        requires_confirmation=True,
        required_args=('backup_id', 'confirmation_phrase'),
        display_type='detail',
        executor=_tool_restore_database_backup,
        operation_type='update',
    ),
    'get_provincial_overview': ToolDefinition(
        name='get_provincial_overview',
        description='Retrieve authoritative province-wide operational overview (project counts, canonical status mix, documentary compliance distribution, overdue SLAs, progress bands, and risk counts).',
        roles=('admin', 'staff'),
        display_type='detail',
        executor=_tool_get_provincial_overview,
        allowed_fields=('fiscal_year',),
    ),
    'compare_lgu_portfolios': ToolDefinition(
        name='compare_lgu_portfolios',
        description='Compare specific LGUs or rank LGUs across visible scope by outstanding requirements, compliance rate, health score, or risk projects.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_compare_lgu_portfolios,
        allowed_fields=('fiscal_year', 'lgu_ids', 'lgu_names', 'limit', 'rank_by'),
    ),
    'get_portfolio_risk_ranking': ToolDefinition(
        name='get_portfolio_risk_ranking',
        description='Retrieve {app_name} operational risk model ranking of projects needing attention, with health scores, contributing factors, and overdue deadlines.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_get_portfolio_risk_ranking,
        allowed_fields=('fiscal_year', 'limit', 'tier'),
    ),
    'get_deficiency_pattern_summary': ToolDefinition(
        name='get_deficiency_pattern_summary',
        description='Aggregate canonical document deficiency categories across authorized projects, showing occurrence frequency and open/resolved/waived breakdown.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_get_deficiency_pattern_summary,
        allowed_fields=('fiscal_year', 'lgu_id', 'project_id', 'resolution_state'),
    ),
    'get_recent_operational_activity': ToolDefinition(
        name='get_recent_operational_activity',
        description='Aggregate recent operational activity (workflow transitions, submissions, monthly progress updates) within a specified day window.',
        roles=('admin', 'staff', 'field_officer'),
        display_type='table',
        executor=_tool_get_recent_operational_activity,
        allowed_fields=('days', 'fiscal_year', 'lgu_id', 'project_id'),
    ),
    'preview_import': ToolDefinition(
        name='preview_import',
        description='Preview clusters, LGUs, programs or a program workbook. Workbook staging/mapping rows may be saved; no operational records are created. Returns an expiring receipt required for commit.',
        roles=('admin',),
        allowed_fields=('target', 'attachment_id', 'batch_id', 'program_id', 'program_cycle_id', 'import_template_id', 'file_hash'),
        risk_level='medium',
        requires_confirmation=False,
        display_type='detail',
        executor=_tool_preview_import,
        operation_type='import_preview',
        canonical_service='batch_import_service / import_service',
    ),
    'commit_import': ToolDefinition(
        name='commit_import',
        description='Commit the exact reviewed import using preview_token (automatically reused from this conversation). Changes after preview require a new preview. Requires explicit confirmation.',
        roles=('admin',),
        allowed_fields=('target', 'attachment_id', 'batch_id', 'file_hash', 'preview_token', 'preview_fingerprint', 'confirm_similar_requirements'),
        risk_level='high',
        requires_confirmation=True,
        display_type='detail',
        executor=_tool_commit_import,
        operation_type='import_commit',
        canonical_service='batch_import_service / import_service',
    ),
    'create_user': ToolDefinition(
        name='create_user',
        description='Create a new operational user account (Admin, Staff, Field Officer) with temporary credentials and role-specific scope assignments. Requires confirmation. Admin-only.',
        roles=('admin',),
        risk_level='high',
        requires_confirmation=True,
        required_args=('email', 'first_name', 'last_name', 'role'),
        display_type='detail',
        executor=_tool_create_user,
        operation_type='user_create',
        scope_type='global',
        canonical_service='auth_service.create_user_account',
        allowed_fields=('email', 'first_name', 'last_name', 'role', 'cluster_ids', 'lgu_ids'),
    ),
    'update_user_profile': ToolDefinition(
        name='update_user_profile',
        description='Update safe profile fields (first_name, last_name, email) for an operational user account. Rejects role, password, and security modifications. Requires confirmation. Admin-only.',
        roles=('admin',),
        risk_level='medium',
        requires_confirmation=True,
        required_args=('user_id',),
        display_type='detail',
        executor=_tool_update_user_profile,
        operation_type='user_update',
        scope_type='global',
        canonical_service='auth_service.update_user_profile',
        allowed_fields=('user_id', 'first_name', 'last_name', 'email'),
    ),
    'bulk_update_project_metadata': ToolDefinition(
        name='bulk_update_project_metadata',
        description='Bulk update metadata fields (notes, subaybayan codes, applicability) across multiple projects selected by LGU, Cluster, Program, or IDs. Admin and Staff only. Requires confirmation.',
        roles=('admin', 'staff'),
        risk_level='medium',
        requires_confirmation=True,
        display_type='detail',
        executor=_tool_bulk_update_project_metadata,
        operation_type='bulk_update',
        scope_type='cluster',
        canonical_service='bulk_project_service.calculate_project_metadata_changes / execute_bulk_project_update',
        allowed_fields=('selectors', 'updates', 'target_ids', 'preview_fingerprint', 'project_ids', 'lgu_id', 'cluster_id', 'program_id', 'program_cycle_id', 'fiscal_year', 'project_status', 'project_kind', 'notes', 'subaybayan_project_code', 'subaybayan_url', 'subaybayan_enrollment_status', 'qaar_category', 'monitoring_applicability', 'custom_fields'),
    ),
    'bulk_update_project_schedule': ToolDefinition(
        name='bulk_update_project_schedule',
        description='Bulk update milestone schedule dates (target/actual start and end dates) across multiple projects. Admin and Staff only. Requires confirmation.',
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        display_type='detail',
        executor=_tool_bulk_update_project_schedule,
        operation_type='bulk_update',
        scope_type='cluster',
        canonical_service='bulk_project_service.calculate_project_schedule_changes / execute_bulk_project_update',
        allowed_fields=('selectors', 'updates', 'target_ids', 'preview_fingerprint', 'project_ids', 'lgu_id', 'cluster_id', 'program_id', 'program_cycle_id', 'fiscal_year', 'project_status', 'project_kind', 'target_start_date', 'target_end_date', 'actual_start_date', 'actual_end_date'),
    ),
    'bulk_update_project_status': ToolDefinition(
        name='bulk_update_project_status',
        description='Bulk update overall operational status (not_yet_started, ongoing, suspended) across multiple projects. Completion transitions are prohibited. Admin and Staff only. Requires confirmation.',
        roles=('admin', 'staff'),
        risk_level='high',
        requires_confirmation=True,
        display_type='detail',
        executor=_tool_bulk_update_project_status,
        operation_type='bulk_update',
        scope_type='cluster',
        canonical_service='bulk_project_service.calculate_project_status_changes / execute_bulk_project_update',
        allowed_fields=('selectors', 'updates', 'target_ids', 'preview_fingerprint', 'project_ids', 'lgu_id', 'cluster_id', 'program_id', 'program_cycle_id', 'fiscal_year', 'project_status', 'project_kind', 'overall_status', 'status', 'notes'),
    ),
}

# Keep the added entity coverage separate from the legacy tool executors.
from app.services.ai_cru_tools import build_tools as _build_cru_tools
TOOLS.update(_build_cru_tools(ToolDefinition))
from app.services.ai_import_tools import build_tools as _build_import_tools
TOOLS.update(_build_import_tools(ToolDefinition))
from app.services.ai_workbook_tools import build_tools as _build_workbook_tools
TOOLS.update(_build_workbook_tools(ToolDefinition))
from app.services.ai_metadata_tools import build_tools as _build_metadata_tools
TOOLS.update(_build_metadata_tools(ToolDefinition))
from app.services.ai_report_tools import build_tools as _build_report_tools
TOOLS.update(_build_report_tools(ToolDefinition))
from app.services.ai_program_setup_tools import build_tools as _build_program_setup_tools
TOOLS.update(_build_program_setup_tools(ToolDefinition))
from app.services.ai_operational_read_tools import build_tools as _build_operational_read_tools
TOOLS.update(_build_operational_read_tools(ToolDefinition))
from app.services.ai_workbook_column_tools import build_tools as _build_workbook_column_tools
TOOLS.update(_build_workbook_column_tools(ToolDefinition))



