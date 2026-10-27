"""Role-scoped capability presentation derived from the live tool registry.

Presentation metadata is not authorization. Execution still validates the
registered tool, role, target, fields, workflow and confirmation state.
"""
import re

from app.services import settings_service


CATEGORY_ORDER = (
    'Search', 'Portfolio insights', 'Field work', 'Projects', 'LGUs and clusters',
    'Program setup', 'Requirements and evidence', 'Compliance', 'Compliance deadlines',
    'Regional handoff', 'Notices', 'Monitoring', 'Imports and workbooks',
    'Reference library', 'Completion', 'Reports and downloads', 'User accounts', 'Settings', 'Audit',
    'Technical administration', 'Other actions',
)
ROLE_LABELS = {'admin': 'Operational administrator', 'staff': 'Staff',
               'field_officer': 'Field Officer', 'system_admin': 'System administrator'}
INTERNAL_FIELDS = frozenset({
    'expected_revision', 'preview_token', 'preview_fingerprint', 'mapping_fingerprint',
    'template_fingerprint', 'file_hash', 'preview_expires_in_seconds', 'target_ids',
})
INPUT_LABELS = {
    'attachment_id': 'Uploaded attachment', 'attachment_stored_object_id': 'Uploaded attachment',
    'definition_id': 'Requirement definition ID', 'requirement_id': 'Project requirement ID',
    'reference_uri': 'Library reference', 'cell_ref': 'Cell reference',
    'confirmation_phrase': 'Required confirmation phrase',
}
ACTION_LABELS = {
    'query_projects': 'Find projects', 'query_requirements': 'Find project requirements',
    'query_audit_log': 'Search audit entries', 'upsert_subaybayan_verification': 'Save SubayBAYAN verification',
    'update_user_profile': 'Update account name and email',
    'bulk_update_project_metadata': 'Update project details in bulk',
    'bulk_update_project_schedule': 'Update project schedules in bulk',
    'bulk_update_project_status': 'Update project statuses in bulk',
}
CATEGORY_SUMMARIES = {
    'Search': 'Find records within the areas available to your account.',
    'Portfolio insights': 'Summarize accessible portfolios, risks, deficiencies and recent activity.',
    'Field work': 'View your assigned work, LGUs and action items.',
    'Projects': 'Use supported project details, budgets, assignments, schedules and status controls.',
    'LGUs and clusters': 'View or maintain the LGU and cluster details permitted for your role.',
    'Program setup': 'Work with programs, cycles, phases and requirement definitions.',
    'Requirements and evidence': 'Inspect project requirements, add comments or upload evidence.',
    'Compliance': 'Summarize compliance without replacing formal document review.',
    'Compliance deadlines': 'Inspect deadlines and use the permitted deadline actions.',
    'Regional handoff': 'Inspect or prepare the supported regional handoff actions.',
    'Notices': 'Prepare drafts or record permitted notice metadata and receipts.',
    'Monitoring': 'Work with supported monitoring records within your assigned projects.',
    'Imports and workbooks': 'Use supported import previews, mapping review and workbook actions.',
    'Reference library': 'Inspect references or maintain the metadata permitted for your role.',
    'Completion': 'Inspect completion documents or edit the permitted draft metadata.',
    'Reports and downloads': 'Inspect reports and request authenticated downloads.',
    'Settings': 'Check configuration readiness for your operational role.',
    'Audit': 'Inspect audit information permitted for your role.',
    'Technical administration': 'Check technical readiness and use the supported backup actions.',
    'User accounts': 'Maintain the operational account details permitted for your role.',
    'Other actions': 'Use this registered action subject to its execution checks.',
}
NOTES = {
    'preview_import': 'Preview may save upload and mapping staging data; it creates no operational projects or requirements.',
    'commit_import': 'Requires a current reviewed preview. Changed content requires another preview.',
    'create_requirement_definition': 'Creates baseline definitions. Manual cycle-specific creation remains in Program setup.',
    'update_requirement_definition': 'Edits the existing definition without moving it between cycles.',
    'create_notice_draft': 'Creates an Annex E draft. Release, signing and dispatch remain in Escalation.',
    'generate_notice_for_sla': 'Prepares the next eligible draft; it does not release, sign or dispatch it.',
    'update_notice_draft': 'Only unreleased drafts can be edited.',
    'record_notice_receipt': 'Requires a released notice and an explicit receipt timestamp.',
    'create_user': 'Creates one operational account at a time; system-administrator provisioning remains in user administration.',
    'update_user_profile': 'Only supported name and email details can be edited. Security controls remain in user administration.',
    'update_monitoring_inspection': 'Approved inspections cannot be edited through the assistant.',
    'update_completion_document_metadata': 'Field Officer: draft Proof of Return of Funds amount and receipt only. Submitted or approved documents are locked.',
    'create_management_action_draft': 'Creates a project-linked draft. Submit, acknowledge and close remain in Monitoring.',
    'update_management_action_draft': 'Only draft content is editable; project reassignment and stage changes are excluded.',
    'update_workbook_cell': 'Formula, source-controlled and documentary-status changes are excluded. The reviewed cell is checked again at confirmation.',
    'resolve_workbook_conflict': 'Uses the reviewed conflict and permitted cell binding; documentary decisions remain in review.',
    'create_library_reference': 'Creates guideline-backed references; new template files use the Library page.',
    'generate_qaar_outputs': 'Creates saved PDFs after confirmation. It does not approve evidence or release an official notice.',
    'download_project_revision_report': 'Generated when Download is selected; the existing service saves an audited report artifact.',
    'download_requirement_correction_report': 'Requires an active return or a valid historical report/return ID. It does not return evidence for revision.',
    'export_monitoring_report_pdf': 'Generated when Download is selected, using current authorized data and the requested filters.',
    'export_workbook_workspace': 'Generated when Download is selected; only currently accessible workbook rows are exported.',
}


def _registry():
    from app.services import ai_tool_registry
    return ai_tool_registry


def category_for(name):
    from app.services.ai_report_tools import TOOL_NAMES as report_names
    if name in ('list_staff_assignments', 'list_field_assignments'):
        return 'User accounts'
    if name == 'list_change_status_requests':
        return 'Projects'
    if name == 'global_search':
        return 'Search'
    if name in {'get_provincial_overview', 'compare_lgu_portfolios', 'get_portfolio_risk_ranking',
                'get_deficiency_pattern_summary', 'get_recent_operational_activity'}:
        return 'Portfolio insights'
    if name in {'get_field_summary', 'list_action_items', 'list_assigned_lgus'}:
        return 'Field work'
    if name in {'get_system_readiness', 'trigger_database_backup', 'list_database_backups', 'restore_database_backup'}:
        return 'Technical administration'
    if name in {'audit_summary', 'query_audit_log'}:
        return 'Audit'
    if name == 'settings_readiness':
        return 'Settings'
    if 'import' in name or 'workbook' in name:
        return 'Imports and workbooks'
    if name in report_names:
        return 'Reports and downloads'
    if 'guideline' in name or 'library_reference' in name:
        return 'Reference library'
    if 'completion_document' in name:
        return 'Completion'
    if 'handoff' in name:
        return 'Regional handoff'
    if 'notice' in name:
        return 'Notices'
    if 'program' in name or 'requirement_definition' in name:
        return 'Program setup'
    if any(term in name for term in ('_lgu', '_cluster')) and not name.startswith(('update_project_', 'create_project')):
        return 'LGUs and clusters'
    if any(term in name for term in ('user_profile', '_user')):
        return 'User accounts'
    if '_sla' in name:
        return 'Compliance deadlines'
    if name == 'generate_compliance_summary':
        return 'Compliance'
    if 'requirement' in name or name == 'upload_evidence_from_attachment':
        return 'Requirements and evidence'
    if 'project' in name and 'management_action' not in name:
        return 'Projects'
    if any(term in name for term in ('monitoring', 'monthly_progress', 'form3', 'exception_report',
                                    'beneficiary_evidence', 'subaybayan', 'management_action')):
        return 'Monitoring'
    return 'Other actions'


def humanize(value):
    words = str(value).replace('_', ' ').capitalize()
    for word in ('lgu', 'qaar', 'sla', 'pdf', 'docx', 'xlsx', 'id', 'mfa'):
        words = re.sub(rf'\b{word}s?\b', lambda m: word.upper() + ('s' if m[0].endswith('s') else ''), words, flags=re.I)
    words = re.sub(r'\bsubaybayan\b', 'SubayBAYAN', words, flags=re.I)
    words = re.sub(r'\bform3\b', 'Form 3', words, flags=re.I)
    return words


def catalog_for_role(role):
    registry = _registry()
    catalog = []
    for item in registry.get_tool_catalog_for_prompt(role):
        name = item['name']
        category = category_for(name)
        label = ACTION_LABELS.get(name, humanize(registry.get_user_facing_tool_label(name)))
        label = re.sub(r'^Get\b', 'View', label)
        # Labels and input labels are presentation only; retain the existing API schema.
        required = [{'key': k, 'label': INPUT_LABELS.get(k, humanize(k))}
                    for k in item['required_args'] if k not in INTERNAL_FIELDS]
        supported = [{'key': k, 'label': INPUT_LABELS.get(k, humanize(k))}
                     for k in item['allowed_fields'] if k not in INTERNAL_FIELDS and k not in item['required_args']]
        note = NOTES.get(name)
        if name == 'update_library_reference':
            note = ('Guideline metadata only; template metadata requires an operational administrator.' if role == 'staff'
                    else 'Existing template metadata only; template uploads and file replacement use the Library page.')
        catalog.append({**item, 'label': label, 'category': category,
            'summary': CATEGORY_SUMMARIES.get(category, 'Maintain permitted operational account details.'),
            'required_inputs': required, 'supported_inputs': supported, 'notes': [note] if note else []})
    order = {label: index for index, label in enumerate(CATEGORY_ORDER)}
    return sorted(catalog, key=lambda item: (order.get(item['category'], len(order)), item['label']))


def summary_for_role(role, catalog=None):
    catalog = catalog if catalog is not None else catalog_for_role(role)
    groups = {}
    for item in catalog:
        group = groups.setdefault(item['category'], {'label': item['category'], 'count': 0, 'confirmation_count': 0})
        group['count'] += 1
        group['confirmation_count'] += int(item['requires_confirmation'])
    limits = [
        'Operational-record deletion and archive are unavailable in chat.',
        'Document approvals, returns for revision, waivers and project phase transitions use their review or lifecycle pages.',
        'Official notice release, signing and dispatch use Escalation.',
        'Role, permission, password, MFA and session changes use account administration.',
    ]
    if role == 'system_admin':
        limits.append('Technical-administrator access does not grant operational record actions.')
    else:
        if any(item['name'] == 'preview_import' for item in catalog):
            limits.append('Import support covers clusters, LGUs, programs and program workbooks. User-account imports use the administration page; other entity imports and universal update-by-import are not supported.')
        else:
            limits.append('Your role cannot preview or commit batch or workbook imports. Those import actions require an operational administrator.')
        limits.append('The assistant does not expose every application field or workflow. Individual actions may have additional record and stage restrictions.')
    return {'role': role, 'role_label': ROLE_LABELS.get(role, humanize(role)),
        'total': len(catalog), 'confirmation_count': sum(int(t['requires_confirmation']) for t in catalog),
        'categories': list(groups.values()), 'limits': limits,
        'scope_note': 'Availability follows your role. Access to individual records is checked when an action runs.',
        'confirmation_note': 'Actions marked Confirmation required wait for your approval. Other actions run when requested; previews and downloads may save staging data or report files.'}


def capability_plan(message, user):
    if user is None:
        return None
    text = (message or '').strip().rstrip('.?!').lower()
    text = re.sub(r'^please\s+', '', text)
    if not text.startswith(('what ', 'show ', 'list ', 'does ')) or len(text) > 300:
        return None
    assistant = re.escape(settings_service.get_assistant_name().lower())
    actor = rf'(?:you|i|the (?:smart )?assistant|{assistant})'
    patterns = (
        rf'what (?:can {actor} do|are your capabilities)',
        rf'(?:show|list) (?:me )?(?:your capabilities|(?:the )?(?:available|supported) (?:assistant )?actions(?: for my role)?)',
        rf'what (?:actions|operations) (?:can {actor} (?:do|perform)|are available (?:to me|for my role))',
        rf'does (?:the (?:smart )?assistant|{assistant}) support everything(?: in (?:the )?system)?',
    )
    if not any(re.fullmatch(pattern, text) for pattern in patterns):
        return None
    return answer_for_user(user)


def answer_for_user(user):
    """Render the current role catalog after intent has been established."""
    summary = summary_for_role(user.role)
    reply = [f'For your **{summary["role_label"]}** account, {summary["total"]} assistant actions are registered.',
             '', '| Area | Available actions | Confirmation required |', '| --- | ---: | ---: |']
    reply.extend(f'| {group["label"]} | {group["count"]} | {group["confirmation_count"]} |'
                 for group in summary['categories'])
    reply.extend(['', summary['scope_note'], summary['confirmation_note'], '', 'Current limits:'])
    reply.extend('- ' + limit for limit in summary['limits'])
    reply.extend(['', 'Open Available Actions in the expanded assistant to inspect individual actions and supported details.'])
    return {'assistant_reply': '\n'.join(reply), 'tool_calls': [], 'is_capability_answer': True,
        'ai_provider_used': 'local', 'ai_model_used': 'local:capability-registry',
        'provider_called': False, 'prompt_snapshot': None, 'heuristic_rule_hit': 'capability_registry',
        'routing_diagnostics': {'planner_source': 'capability_registry', 'validation_passed': True}}
