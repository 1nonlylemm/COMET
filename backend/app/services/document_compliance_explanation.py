"""COMET Document Compliance Explanation Service — Phase 3.2.

Provides an objective, evidence-grounded plain-language explanation and
reviewer guidance layer for automated document review findings.

ARCHITECTURAL INVARIANTS:
1. The LLM is an EXPLANATION LAYER ONLY, not a checker and not an evaluator.
2. Findings originate exclusively from deterministic / visual checker engines.
3. The explanation layer MUST NOT:
   - Invent findings or evidence.
   - Modify finding severity, category, confidence, page, bbox, or evidence_text.
   - Make automated compliance determinations (approved, rejected, waived,
     compliant, non-compliant, return for revision).
   - Assert legal validity or signature/stamp authenticity.
   - Introduce scores, score bands, grades, or readiness percentages.
4. Deterministic fallback is guaranteed whenever AI is unavailable, times out,
   or emits malformed/unsupported responses.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.services import ai_connection, ai_guardrails, document_compliance_rule_engine as rule_engine

logger = logging.getLogger(__name__)

# Canonical category display themes for reviewer orientation
THEME_MAPPINGS: dict[str, str] = {
    rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY: 'Document Quality & Readability',
    rule_engine.CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY: 'Layout & Structural Integrity',
    rule_engine.CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE: 'Required Information & Content',
    rule_engine.CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE: 'Signatory & Official-Mark Verification',
    rule_engine.CATEGORY_DATE_TEMPORAL_CONSISTENCY: 'Date & Temporal Alignment',
    rule_engine.CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY: 'Internal & Cross-Document Consistency',
    rule_engine.CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY: 'Calculation & Arithmetic Consistency',
}

# Forbidden verdict keywords that must never appear in automated explanations
FORBIDDEN_VERDICT_TERMS: tuple[str, ...] = (
    'ready_for_approval',
    'return_for_revision',
    'non_compliant',
    'is_compliant',
    'score_band',
    'overall_score',
    'legally valid',
    'legally invalid',
    'authentic signature',
    'inauthentic signature',
    'genuine signature',
    'valid signature',
    'invalid signature',
    'fraudulent document',
    'document approved',
    'document rejected',
)


def generate_document_explanation(
    findings: list[dict[str, Any]],
    *,
    document_context: dict[str, Any] | None = None,
    user_id: int | None = None,
    allow_ai: bool = True,
) -> dict[str, Any]:
    """Generates a structured, evidence-grounded explanation for checker findings.

    If findings is empty, returns an immediate neutral response without invoking AI.
    If AI is disabled or fails, falls back gracefully to deterministic guidance.

    Returns:
        Structured explanation dict satisfying the Phase 3.2 schema.
    """
    if not findings:
        return generate_deterministic_explanation(
            [],
            reason='no_findings',
        )

    context = document_context or {}
    valid_finding_ids = {
        f.get('finding_id') or f.get('id')
        for f in findings
        if (f.get('finding_id') or f.get('id'))
    }

    if not allow_ai:
        return generate_deterministic_explanation(
            findings,
            reason='ai_disabled',
        )

    # Check whether an active AI provider client is configured
    try:
        provider_clients = ai_connection._get_provider_clients()
    except Exception as exc:
        logger.warning('Failed to query AI provider clients: %s', exc)
        provider_clients = []

    if not provider_clients:
        return generate_deterministic_explanation(
            findings,
            reason='ai_not_configured',
        )

    # Construct bounded input messages
    messages = _build_explanation_prompt_messages(findings, context=context)

    def _validator(payload: Any) -> dict[str, Any]:
        return validate_explanation_payload(payload, valid_finding_ids=valid_finding_ids)

    try:
        gen_result = ai_connection.generate_json(
            messages,
            validator=_validator,
            purpose='document_review_explanation',
        )
        explanation = gen_result.payload
        explanation['provenance'] = {
            'source': 'llm_explanation',
            'provider': gen_result.provider,
            'model': gen_result.model,
            'source_finding_ids': sorted(list(valid_finding_ids)),
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        return explanation

    except Exception as exc:
        logger.warning('AI explanation generation failed (%s); falling back to deterministic explanation.', exc)
        return generate_deterministic_explanation(
            findings,
            reason=f'fallback_after_error_{type(exc).__name__}',
        )


def generate_deterministic_explanation(
    findings: list[dict[str, Any]],
    *,
    reason: str = 'deterministic_fallback',
) -> dict[str, Any]:
    """Produces an objective, deterministic explanation payload without external LLM calls.

    Strictly grounded in the supplied finding observations and reviewer actions.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    valid_finding_ids = [
        f.get('finding_id') or f.get('id')
        for f in findings
        if (f.get('finding_id') or f.get('id'))
    ]

    if not findings:
        return {
            'summary': 'No potential issues or discrepancies were flagged by the automated review.',
            'priority_findings': [],
            'grouped_themes': [],
            'review_checklist': [
                'Perform standard document intake inspection according to program requirements.',
            ],
            'provenance': {
                'source': 'deterministic_fallback',
                'reason': reason,
                'source_finding_ids': [],
                'generated_at': now_iso,
            },
        }

    # 1. Group findings by canonical category theme
    theme_groups: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        cat = f.get('category') or rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY
        theme_groups.setdefault(cat, []).append(f)

    grouped_themes = []
    for cat, cat_findings in theme_groups.items():
        theme_name = THEME_MAPPINGS.get(cat, cat.replace('_', ' ').title())
        f_ids = [f.get('finding_id') or f.get('id') for f in cat_findings if f.get('finding_id') or f.get('id')]
        count = len(cat_findings)
        grouped_themes.append({
            'theme_name': theme_name,
            'category': cat,
            'finding_ids': f_ids,
            'explanation': f'Automated inspection identified {count} item(s) relating to {theme_name.lower()}.',
        })

    # 2. Build priority finding explanations
    priority_findings = []
    # Order by severity priority: blocker > warning > needs_verification > info
    severity_order = {'blocker': 0, 'warning': 1, 'needs_verification': 2, 'info': 3}
    sorted_findings = sorted(
        findings,
        key=lambda x: severity_order.get(x.get('severity', 'info'), 4),
    )

    for f in sorted_findings:
        f_id = f.get('finding_id') or f.get('id')
        if not f_id:
            continue
        obs = f.get('observation') or f.get('message') or 'Automated finding detected.'
        action = f.get('reviewer_action') or f.get('corrective_instruction') or 'Review the document.'

        # Formulate reviewer-friendly plain-language explanation
        explanation_text = _format_plain_language_explanation(f, obs)
        priority_findings.append({
            'finding_id': f_id,
            'explanation': explanation_text,
            'review_instruction': action,
        })

    # 3. Assemble review checklist from unique actionable instructions
    seen_instructions = set()
    checklist = []
    for f in sorted_findings:
        action = f.get('reviewer_action') or f.get('corrective_instruction')
        if action and action not in seen_instructions:
            seen_instructions.add(action)
            checklist.append(action)

    if not checklist:
        checklist.append('Inspect the document to evaluate automated findings.')

    # 4. Summary
    cat_names = [THEME_MAPPINGS.get(c, c) for c in theme_groups.keys()]
    cats_str = ', '.join(cat_names[:3])
    if len(cat_names) > 3:
        cats_str += f', and {len(cat_names) - 3} other category(ies)'

    summary = (
        f'Automated review flagged {len(findings)} potential issue(s) across {cats_str}. '
        'Human reviewer inspection is required to adjudicate documentary intake.'
    )

    return {
        'summary': summary,
        'priority_findings': priority_findings,
        'grouped_themes': grouped_themes,
        'review_checklist': checklist,
        'provenance': {
            'source': 'deterministic_fallback',
            'reason': reason,
            'source_finding_ids': valid_finding_ids,
            'generated_at': now_iso,
        },
    }


def _sanitize_speculative_clauses(text: str) -> str:
    if not text:
        return text
    # Strip unsupported speculative cause clauses that convert observations into speculation
    cleaned = re.sub(
        r',?\s*(?:suggesting|likely due to|likely because)\s+[^,.]*',
        '',
        text,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned


def validate_explanation_payload(
    payload: Any,
    *,
    valid_finding_ids: set[str],
) -> dict[str, Any]:
    """Validates and sanitizes the structured output returned by an LLM.

    Raises:
        AiGuardrailError if the payload is malformed or violates semantic safety invariants.
    """
    if not isinstance(payload, dict):
        raise ai_guardrails.AiGuardrailError('Explanation response must be a JSON object.')

    # Summary validation
    summary = payload.get('summary')
    if not isinstance(summary, str) or not summary.strip():
        raise ai_guardrails.AiGuardrailError('Explanation payload is missing a valid "summary".')
    clean_summary = _sanitize_speculative_clauses(summary.strip())

    # Priority findings validation
    raw_priority = payload.get('priority_findings')
    if not isinstance(raw_priority, list):
        raise ai_guardrails.AiGuardrailError('Explanation payload is missing "priority_findings" list.')

    validated_priority = []
    for item in raw_priority:
        if not isinstance(item, dict):
            continue
        f_id = item.get('finding_id')
        if not f_id or f_id not in valid_finding_ids:
            # Model hallucinated a finding_id not present in deterministic findings
            logger.warning('Dropping unrecognized finding_id "%s" from LLM explanation.', f_id)
            continue

        exp = item.get('explanation')
        ins = item.get('review_instruction')
        if not isinstance(exp, str) or not exp.strip():
            continue
        if not isinstance(ins, str):
            ins = ''

        validated_priority.append({
            'finding_id': f_id,
            'explanation': _sanitize_speculative_clauses(exp.strip()),
            'review_instruction': ins.strip(),
        })

    # Grouped themes validation
    raw_themes = payload.get('grouped_themes')
    validated_themes = []
    if isinstance(raw_themes, list):
        for t in raw_themes:
            if not isinstance(t, dict):
                continue
            name = str(t.get('theme_name') or '').strip()
            raw_ids = t.get('finding_ids') or []
            safe_ids = [fid for fid in raw_ids if fid in valid_finding_ids]
            theme_exp = _sanitize_speculative_clauses(str(t.get('explanation') or '').strip())
            if name and safe_ids:
                validated_themes.append({
                    'theme_name': name,
                    'finding_ids': safe_ids,
                    'explanation': theme_exp,
                })

    # Review checklist validation
    raw_checklist = payload.get('review_checklist')
    validated_checklist = []
    if isinstance(raw_checklist, list):
        for step in raw_checklist:
            if isinstance(step, str) and step.strip():
                validated_checklist.append(step.strip())

    if not validated_checklist:
        validated_checklist = ['Review document to verify all flagged findings.']

    result = {
        'summary': clean_summary,
        'priority_findings': validated_priority,
        'grouped_themes': validated_themes,
        'review_checklist': validated_checklist,
    }

    # Semantic Safety Scan: reject if the model introduced prohibited verdict terms
    _assert_no_forbidden_verdicts(result)

    return result


def enrich_findings_with_explanation(
    findings: list[dict[str, Any]],
    explanation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Enriches findings with plain-language explanations without mutating deterministic invariants.

    Preserves finding_id, severity, category, rule, observation, page, bbox,
    evidence_text, confidence, automation_level, reviewer_action, and provenance.
    """
    if not explanation or not isinstance(explanation, dict):
        return findings

    priority_map = {
        item['finding_id']: item
        for item in (explanation.get('priority_findings') or [])
        if isinstance(item, dict) and item.get('finding_id')
    }

    enriched = []
    for f in findings:
        f_copy = dict(f)
        f_id = f_copy.get('finding_id') or f_copy.get('id')
        if f_id and f_id in priority_map:
            match = priority_map[f_id]
            f_copy['ai_explanation'] = match.get('explanation')
            if match.get('review_instruction'):
                f_copy['review_instruction'] = match.get('review_instruction')
        enriched.append(f_copy)

    return enriched


def _build_explanation_prompt_messages(
    findings: list[dict[str, Any]],
    *,
    context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Builds tightly scoped developer and user prompt messages."""
    if context is None:
        context = {}
    system_prompt = (
        'You are an automated document-review explanation assistant for human reviewers in the COMET system. '
        'You are an explanation layer, NOT a compliance evaluator and NOT an approval engine.\n\n'
        'Your task is to translate deterministic checker findings and machine evidence into clear, objective, '
        'plain-language explanations and a practical inspection checklist for human evaluators.\n\n'
        'STRICT RULES:\n'
        '1. Grounding: Rely strictly and solely on the supplied findings and evidence. Do not invent facts, page numbers, '
        'signatures, or calculations.\n'
        '2. Reviewer Guidance vs Facts: You may suggest what the reviewer should inspect, but do not state speculative causes as facts. '
        'State ONLY observable facts directly given in the finding observation. NEVER assert unproven root causes (e.g. do NOT say "likely due to low resolution", "scanning defect", "assembly defect", "image flattening", or "content was omitted"). Possible causes must be phrased ONLY as reviewer checks/questions in the review_checklist (e.g. "Reviewer should check whether...").\n'
        '3. Arithmetic Honesty: You may explain the supplied arithmetic, but do not invent additional amounts or unlisted line items.\n'
        '4. Signatory Boundaries: You may describe an observed visual mark, but NEVER call it an authentic "signature", "official mark", "official seal", or "stamp". Never evaluate authenticity. Direct the reviewer to inspect physical marks.\n'
        '5. Preserve Uncertainty & Structural Bounds: If OCR was poor or text was not found, explain that text was not detected in machine extraction; do NOT claim a signature or document element is definitively absent in reality, and do NOT claim content was omitted or that a document is defective. State only the physical observation.\n'
        '6. Finding IDs: Every item in "priority_findings" must explicitly cite a valid "finding_id" from the input.\n'
        '7. No Verdicts: Never state that a document is compliant, non-compliant, approved, rejected, valid, invalid, or fraudulent.\n'
        '8. No Scores or Readiness: Never produce scores, readiness grades, or percentage ratings.\n'
        '9. Output format: Return only a valid JSON object matching the requested schema:\n'
        '{\n'
        '  "summary": "plain-language summary of findings",\n'
        '  "priority_findings": [\n'
        '    {"finding_id": "...", "explanation": "plain-language translation", "review_instruction": "action"}\n'
        '  ],\n'
        '  "grouped_themes": [\n'
        '    {"theme_name": "...", "finding_ids": ["..."], "explanation": "..."}\n'
        '  ],\n'
        '  "review_checklist": ["..."]\n'
        '}'
    )

    # Format findings into a clean, bounded JSON representation
    bounded_findings = []
    for f in findings:
        f_id = f.get('finding_id') or f.get('id')
        if not f_id:
            continue
        bounded_findings.append({
            'finding_id': f_id,
            'category': f.get('category'),
            'rule': f.get('rule'),
            'severity': f.get('severity'),
            'observation': f.get('observation') or f.get('message'),
            'page': f.get('page'),
            'evidence_text': f.get('evidence_text'),
            'confidence': f.get('confidence'),
            'automation_level': f.get('automation_level'),
            'reviewer_action': f.get('reviewer_action') or f.get('corrective_instruction'),
        })

    user_payload: dict[str, Any] = {
        'context': {
            'file_name': context.get('file_name'),
            'requirement_name': context.get('requirement_name'),
            'project_kind': context.get('project_kind'),
        },
        'findings': bounded_findings,
    }

    import json
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': json.dumps(user_payload, indent=2, ensure_ascii=False)},
    ]


def _format_plain_language_explanation(finding: dict[str, Any], observation: str) -> str:
    """Translates technical observations into reviewer-friendly language for deterministic fallback."""
    rule = finding.get('rule') or ''
    page = finding.get('page')
    page_prefix = f'On page {page}, ' if page else ''

    if rule == 'blank_page_interruption':
        clause = 'an intermediate blank sheet was detected between populated pages. Inspect to ensure no pages were skipped during scanning.'
    elif rule == 'mixed_page_orientation':
        clause = 'mixed portrait and landscape page orientations were detected. Inspect to ensure pages are oriented legibly.'
    elif rule == 'inconsistent_page_dimensions':
        clause = 'page dimensions vary significantly across sheets. Verify that no document content was clipped.'
    elif rule == 'empty_structural_section':
        clause = 'a required section header was found without accompanying body content. Inspect to confirm that narrative or attachments are complete.'
    elif rule == 'quantity_unit_cost_mismatch':
        clause = 'the quantity multiplied by the unit cost does not match the stated total. Verify line-item arithmetic.'
    elif rule in ('financial_reconciliation_mismatch', 'subtotal_arithmetic_mismatch'):
        clause = 'the sum of line items does not equal the stated total. Inspect calculations and check for unlisted charges or deductions.'
    elif rule in ('missing_signatory', 'missing_evidence_signatory'):
        clause = 'no printed signatory label or role was detected in the readable text. This does not confirm a signature is absent; inspect the physical signature block.'
    elif rule == 'signatory_visual_mark_present':
        clause = 'a printed signatory label was detected alongside visual marks in the signing area. Human reviewer must verify signature authenticity and authority.'
    elif rule in ('technical_blank_document', 'technical_low_text'):
        clause = 'automated text extraction found very little or no readable text. Inspect the scan directly because OCR may have failed on low-contrast imagery.'
    else:
        return f'{page_prefix}{observation}'

    if page_prefix:
        return f'{page_prefix}{clause}'
    return clause[:1].upper() + clause[1:]


def _assert_no_forbidden_verdicts(result: dict[str, Any]) -> None:
    """Recursively checks text in the explanation payload against forbidden verdict terms."""
    texts_to_check = [result.get('summary', '')]
    for pf in result.get('priority_findings', []):
        texts_to_check.append(pf.get('explanation', ''))
        texts_to_check.append(pf.get('review_instruction', ''))
    for t in result.get('grouped_themes', []):
        texts_to_check.append(t.get('explanation', ''))
    for step in result.get('review_checklist', []):
        texts_to_check.append(step)

    blob = ' '.join(texts_to_check).lower()
    for forbidden in FORBIDDEN_VERDICT_TERMS:
        if forbidden in blob:
            raise ai_guardrails.AiGuardrailError(
                f'Explanation payload contained prohibited verdict keyword: "{forbidden}".'
            )
