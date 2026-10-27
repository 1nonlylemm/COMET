from app.extensions import db
from app.models import EscalationNotice, LegalFinding, LguProfile, Project, ProjectRequirement
from app.services import access_service, ai_connection, ai_guardrails


class AiServiceError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def draft_annex_e_finding(notice_id, informal_notes, finding_id=None, user_id=None):
    notice = _get_notice_with_access(notice_id, user_id=user_id)
    if notice.notice_type != 'annex_e':
        raise AiServiceError('AI drafting is only available for Annex E notices.', 422)

    normalized_notes = (informal_notes or '').strip()
    if not normalized_notes:
        raise AiServiceError('informal_notes is required for AI drafting.', 422)

    project = db.session.get(Project, notice.project_id)
    lgu = db.session.get(LguProfile, project.lgu_id) if project else None
    requirement = (
        db.session.get(ProjectRequirement, notice.trigger_project_requirement_id)
        if notice.trigger_project_requirement_id else None
    )
    finding = _get_finding_for_notice(notice, finding_id)

    messages = ai_guardrails.build_annex_e_messages(
        notice=notice,
        project=project,
        lgu=lgu,
        requirement=requirement,
        informal_notes=normalized_notes,
        finding=finding,
    )

    try:
        generation = ai_connection.generate_json(
            messages=messages,
            validator=ai_guardrails.validate_annex_e_draft_payload,
            purpose='annex_e_notice_draft',
        )
    except ai_connection.AiConnectionError as exc:
        raise AiServiceError(exc.message, exc.status_code) from exc

    payload = generation.payload

    return {
        'formal_findings': payload['formal_findings'],
        'recommendations': payload['recommendations'],
        'agreements_timelines': payload['agreements_timelines'],
        'informal_notes': normalized_notes,
        'ai_provider_used': generation.provider,
        'ai_model_used': f'{generation.provider}:{generation.model}',
        'ai_prompt_used': ai_guardrails.build_prompt_snapshot(messages, generation.attempts),
    }


def _get_notice_with_access(notice_id, user_id=None):
    notice = db.session.get(EscalationNotice, notice_id)
    if not notice:
        raise AiServiceError('Escalation notice not found', 404)

    try:
        if user_id is not None:
            access_service.ensure_project_access(notice.project_id, user_id)
    except access_service.AccessError as exc:
        raise AiServiceError(exc.message, exc.status_code)

    return notice


def _get_finding_for_notice(notice, finding_id):
    if finding_id in (None, ''):
        return None

    try:
        finding_id = int(finding_id)
    except (TypeError, ValueError):
        raise AiServiceError('finding_id must be a positive integer.', 422)

    finding = db.session.get(LegalFinding, finding_id)
    if not finding or finding.notice_id != notice.id:
        raise AiServiceError('Legal finding not found for this notice.', 404)
    return finding
