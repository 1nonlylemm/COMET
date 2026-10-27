import json
from datetime import datetime, timezone

from app.services import (
    ai_connection,
    ai_guardrails,
    escalation_service,
    monitoring_service,
    project_service,
    settings_service,
    sla_service,
)


SUMMARY_FIELDS = (
    'executive_summary',
    'bottlenecks',
    'recommended_actions',
    'risk_flags',
)


def generate_compliance_summary(user_id, fiscal_year=None):
    context = build_compliance_summary_context(user_id, fiscal_year=fiscal_year)
    messages = build_compliance_summary_messages(context)

    try:
        generation = ai_connection.generate_json(
            messages=messages,
            validator=validate_compliance_summary_payload,
            purpose='workspace_compliance_summary',
        )
        summary = generation.payload
        provider = generation.provider
        model = f'{generation.provider}:{generation.model}'
        prompt_snapshot = ai_guardrails.build_prompt_snapshot(messages, generation.attempts)
    except ai_connection.AiConnectionError:
        summary = _fallback_compliance_summary(context)
        provider = 'local'
        model = 'local:structured-compliance-summary'
        prompt_snapshot = None

    summary['source_metrics'] = context['metrics']
    summary['generated_at'] = context['generated_at']
    summary['ai_provider_used'] = provider
    summary['ai_model_used'] = model
    summary['prompt_snapshot'] = prompt_snapshot
    return summary


def build_compliance_summary_context(user_id, fiscal_year=None):
    projects = _safe_service_call(
        'projects',
        lambda: project_service.list_projects(page=1, per_page=10, fiscal_year=fiscal_year, user_id=user_id),
        {'projects': [], 'total': 0},
    )
    sla_dashboard = _safe_service_call(
        'sla_dashboard',
        lambda: sla_service.get_sla_dashboard(user_id=user_id, fiscal_year=fiscal_year),
        {},
    )
    overdue_deadlines = _safe_service_call(
        'overdue_deadlines',
        lambda: sla_service.get_overdue_deadlines(user_id=user_id, fiscal_year=fiscal_year),
        [],
    )
    escalation_dashboard = _safe_service_call(
        'escalation_dashboard',
        lambda: escalation_service.get_escalation_dashboard(user_id=user_id, fiscal_year=fiscal_year),
        {},
    )
    monitoring_workbench = _safe_service_call(
        'monitoring_workbench',
        lambda: monitoring_service.get_monitoring_workbench(user_id=user_id, fiscal_year=fiscal_year),
        {'summary': {}, 'projects': []},
    )

    metrics = {
        'visible_projects': _int_value(projects.get('total')),
        'visible_project_sample_count': len(projects.get('projects') or []),
        'sla_total': _int_value(sla_dashboard.get('total')),
        'sla_active': _int_value(sla_dashboard.get('active')),
        'sla_overdue': _int_value(sla_dashboard.get('overdue')),
        'sla_upcoming': _int_value(sla_dashboard.get('upcoming')),
        'sla_escalated': _int_value(sla_dashboard.get('escalated')),
        'overdue_deadline_count': len(overdue_deadlines or []),
        'breached_deadlines': _int_value(escalation_dashboard.get('breached_deadlines')),
        'notices_ready_to_generate': _int_value(escalation_dashboard.get('ready_to_generate')),
        'blocked_escalations': _int_value(escalation_dashboard.get('blocked')),
        'monitorable_projects': _int_value((monitoring_workbench.get('summary') or {}).get('monitorable_projects')),
        'monitoring_flagged_findings': _int_value((monitoring_workbench.get('summary') or {}).get('flagged_findings')),
        'monitoring_pending_transmittal': _int_value((monitoring_workbench.get('summary') or {}).get('pending_transmittal')),
    }

    return {
        'app_name': _app_name(),
        'fiscal_year': fiscal_year,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'metrics': metrics,
        'project_samples': _project_samples(projects.get('projects') or []),
        'overdue_deadline_samples': _deadline_samples(overdue_deadlines or []),
        'sla_dashboard': sla_dashboard,
        'escalation_dashboard': escalation_dashboard,
        'monitoring_summary': monitoring_workbench.get('summary') or {},
        'monitoring_samples': _monitoring_samples(monitoring_workbench.get('projects') or []),
    }


def build_compliance_summary_messages(context):
    app_name = _app_name()
    system_prompt = (
        f'You are {_assistant_name()}, an internal DILG PDMU compliance summarization assistant. '
        f'Use only the structured {app_name} data supplied in the user message. Do not invent project facts, LGU facts, dates, '
        'amounts, legal conclusions, or compliance decisions. Do not include personally sensitive details. Produce a concise '
        'management-ready summary for internal staff review. Return only valid JSON.'
    )
    user_prompt = (
        f'Generate a source-backed {app_name} compliance summary from this role-scoped structured data.\n'
        'Return JSON with exactly these keys: executive_summary, bottlenecks, recommended_actions, risk_flags.\n'
        'Use short lists. Mention uncertainty when the data is limited. Do not recommend automatic approval, hidden status '
        'changes, or dispatch without human review.\n\n'
        f'{json.dumps(context, ensure_ascii=True, sort_keys=True)}'
    )
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]


def validate_compliance_summary_payload(payload):
    if not isinstance(payload, dict):
        raise ai_guardrails.AiGuardrailError('Assistant returned an invalid compliance summary format.')

    executive_summary = _required_text(payload.get('executive_summary'), 'executive_summary', max_length=1200)
    return {
        'executive_summary': executive_summary,
        'bottlenecks': _text_list(payload.get('bottlenecks'), 'bottlenecks', max_items=6, max_length=220),
        'recommended_actions': _text_list(payload.get('recommended_actions'), 'recommended_actions', max_items=6, max_length=220),
        'risk_flags': _text_list(payload.get('risk_flags'), 'risk_flags', max_items=6, max_length=220),
    }


def _fallback_compliance_summary(context):
    metrics = context.get('metrics') or {}
    app_name = context.get('app_name') or _app_name()
    visible_projects = _int_value(metrics.get('visible_projects'))
    overdue = _int_value(metrics.get('sla_overdue') or metrics.get('overdue_deadline_count'))
    upcoming = _int_value(metrics.get('sla_upcoming'))
    ready_notices = _int_value(metrics.get('notices_ready_to_generate'))
    flagged_findings = _int_value(metrics.get('monitoring_flagged_findings'))
    pending_transmittal = _int_value(metrics.get('monitoring_pending_transmittal'))

    executive_summary = (
        f'{app_name} is tracking {visible_projects} visible project record(s), with {overdue} overdue working-day '
        f'deadline(s), {upcoming} upcoming deadline(s), and {ready_notices} escalation item(s) ready for staff review.'
    )
    bottlenecks = []
    if overdue:
        bottlenecks.append(f'{overdue} unresolved working-day deadline(s) are overdue.')
    if ready_notices:
        bottlenecks.append(f'{ready_notices} breached item(s) are ready for notice generation review.')
    if flagged_findings:
        bottlenecks.append(f'{flagged_findings} implementation monitoring finding(s) are flagged.')
    if pending_transmittal:
        bottlenecks.append(f'{pending_transmittal} monitoring item(s) are pending transmittal.')
    if not bottlenecks:
        bottlenecks.append('No major compliance bottleneck is visible in the current role-scoped metrics.')

    recommended_actions = [
        'Review overdue working-day deadlines and confirm whether reminder or notice action is required.',
        'Check source project and requirement records before issuing any official communication.',
        'Use the audit trail and handoff queue to verify that completed actions remain traceable.',
    ]
    risk_flags = []
    if overdue:
        risk_flags.append('Overdue deadlines may require receipt-aware escalation review.')
    if flagged_findings:
        risk_flags.append('Flagged monitoring findings should be reviewed before reporting project progress.')
    if not risk_flags:
        risk_flags.append('No elevated risk flag is visible from the summarized metrics.')

    return {
        'executive_summary': executive_summary,
        'bottlenecks': bottlenecks[:6],
        'recommended_actions': recommended_actions,
        'risk_flags': risk_flags[:6],
    }


def _safe_service_call(label, callback, fallback):
    try:
        return callback()
    except Exception as exc:
        return {
            **fallback,
            'service_unavailable': label,
            'error': str(exc)[:300],
        } if isinstance(fallback, dict) else fallback


def _project_samples(projects):
    return [
        {
            'id': item.get('id'),
            'project_name': item.get('project_name'),
            'fiscal_year': item.get('fiscal_year'),
            'current_phase': item.get('current_phase'),
            'overall_status': item.get('overall_status'),
            'source_project_code': item.get('source_project_code'),
        }
        for item in projects[:10]
    ]


def _deadline_samples(deadlines):
    return [
        {
            'id': item.get('id'),
            'project_name': item.get('project_name'),
            'requirement_name': item.get('requirement_name'),
            'deadline_date': item.get('deadline_date'),
            'days_remaining': item.get('days_remaining'),
            'deadline_type': item.get('deadline_type'),
        }
        for item in deadlines[:10]
    ]


def _monitoring_samples(projects):
    return [
        {
            'project_id': item.get('project_id'),
            'project_name': item.get('project_name'),
            'lgu_name': item.get('lgu_name'),
            'monitoring_state': item.get('monitoring_state'),
            'latest_status': item.get('latest_status'),
            'flagged_count': item.get('flagged_count'),
            'pending_transmittal_count': item.get('pending_transmittal_count'),
        }
        for item in projects[:10]
    ]


def _text_list(value, field_name, max_items=6, max_length=220):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ai_guardrails.AiGuardrailError(f'Assistant response "{field_name}" must be a list.')
    result = []
    for item in value[:max_items]:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            result.append(text[:max_length])
    return result


def _required_text(value, field_name, max_length=1200):
    if not isinstance(value, str) or not value.strip():
        raise ai_guardrails.AiGuardrailError(f'Assistant response is missing "{field_name}".')
    return value.strip()[:max_length]


def _int_value(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _app_name():
    try:
        return settings_service.get_app_name()
    except Exception:
        return 'DILG Operations Workspace'


def _assistant_name():
    try:
        return settings_service.get_assistant_name()
    except Exception:
        return 'DILG Operations Workspace Assistant'
