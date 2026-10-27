"""Requirement-Driven Documentary Evidence Checker for COMET.

Evaluates uploaded documentary evidence against concrete, requirement-specified
expectations (signatories, certifications, notarizations, dates, required phrases).
Does NOT generate artificial overall scores, percentage metrics, or quality bands.
Reports strictly whether expected documentary evidence was detected.
"""

from __future__ import annotations

from pathlib import Path
from datetime import date
import re
import unicodedata
from typing import Any

from app.services import document_compliance_rule_engine as rule_engine
from app.services.document_compliance_arithmetic import _find_text_location_for_snippet


# Standard Signatory Role Dictionary
STANDARD_SIGNATORY_ROLES = {
    'prepared_by': {
        'role_key': 'prepared_by',
        'label': 'Prepared by',
        'aliases': [
            'prepared by',
            'prepared by:',
            'prepared:',
            'prep by',
            'prep. by',
            'inihanda ni',
            'inihanda ni:',
        ],
    },
    'reviewed_by': {
        'role_key': 'reviewed_by',
        'label': 'Reviewed by',
        'aliases': [
            'reviewed by',
            'reviewed by:',
            'reviewed:',
            'checked by',
            'checked by:',
            'verified by',
            'verified by:',
            'sinuri ni',
            'sinuri ni:',
        ],
    },
    'approved_by': {
        'role_key': 'approved_by',
        'label': 'Approved by',
        'aliases': [
            'approved by',
            'approved by:',
            'approved:',
            'pinagtibay ni',
            'pinagtibay ni:',
            'inaprubahan ni',
            'inaprubahan ni:',
        ],
    },
    'certified_by': {
        'role_key': 'certified_by',
        'label': 'Certified by',
        'aliases': [
            'certified by',
            'certified by:',
            'certified correct by',
            'certified correct by:',
            'certified true and correct by',
            'certified true and correct by:',
            'pinatunayan ni',
        ],
    },
    'noted_by': {
        'role_key': 'noted_by',
        'label': 'Noted by',
        'aliases': [
            'noted by',
            'noted by:',
            'noted:',
            'pinansin ni',
        ],
    },
    'attested_by': {
        'role_key': 'attested_by',
        'label': 'Attested by',
        'aliases': [
            'attested by',
            'attested by:',
            'attested:',
            'pinatotohanan ni',
        ],
    },
}

STANDARD_CERTIFICATION_PHRASES = [
    'certified true copy',
    'certified true and correct',
    'certified correct',
    'certified copy',
    'certified true photocopy',
    'certified as true copy',
    'certified to be a true copy',
    'pinatutunayan na',
    'pinatutunayan nito',
    'this is to certify that',
    'certify that',
    'this document is hereby certified',
    'certifies that',
    'hereby certified',
]

STANDARD_NOTARIZATION_PHRASES = [
    'notary public',
    'subscribed and sworn',
    'subscribed & sworn',
    'acknowledgement',
    'acknowledgment',
    'jurat',
    'notarial seal',
    'doc no',
    'doc. no',
    'doc. no.',
    'page no',
    'page. no',
    'page. no.',
    'book no',
    'book. no',
    'book. no.',
]

# Regex for detecting standard date formats (ISO, written month-day-year, Day-Month-Year, slash/dash)
DATE_PATTERNS = [
    # Month Day, Year (e.g. October 14, 2025 or Oct. 14, 2025)
    re.compile(
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
        r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'\.?\s+(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?,?\s+[1-9]\d{3}\b',
        re.IGNORECASE,
    ),
    # Day Month Year (e.g. 15 August 2026 or 14th of October, 2025 or 10th day of August 2026)
    re.compile(
        r'\b(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+(?:day\s+of\s+|of\s+)?'
        r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
        r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'\.?,?\s+[1-9]\d{3}\b',
        re.IGNORECASE,
    ),
    # Month Year (e.g. October 2025)
    re.compile(
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
        r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'\.?\s+[1-9]\d{3}\b',
        re.IGNORECASE,
    ),
    # Bounded numerical date (MM/DD/YYYY or DD/MM/YYYY)
    re.compile(
        r'\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-][1-9]\d{3}\b'
    ),
    re.compile(
        r'\b(?:0?[1-9]|[12]\d|3[01])[/-](?:0?[1-9]|1[0-2])[/-][1-9]\d{3}\b'
    ),
    # ISO date (YYYY-MM-DD)
    re.compile(
        r'\b[1-9]\d{3}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b'
    ),
]


def normalize_text(text: str) -> str:
    """Normalizes text for robust token and phrase matching."""
    if not text:
        return ''
    # Normalize unicode characters
    normalized = unicodedata.normalize('NFKD', str(text))
    # Repair lightweight OCR noise for role prepositions
    normalized = re.sub(r'\bb\s+y\b', 'by', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\b8y\b', 'by', normalized, flags=re.IGNORECASE)
    # Replace newlines, tabs, and multiple spaces with a single space
    normalized = re.sub(r'[\r\n\t]+', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip().lower()


def normalize_phrase_for_comparison(text: str) -> str:
    """Normalizes phrase by stripping abbreviation periods and dashes for robust comparison."""
    if not text:
        return ''
    norm = normalize_text(text)
    # Strip abbreviation dots (e.g. d.i.l.g. -> dilg, p.o. -> po, r.a. -> ra)
    norm = re.sub(r'(?<=[a-z])\.', '', norm)
    # Normalize dashes and hyphens to spaces
    norm = re.sub(r'[-–—−]', ' ', norm)
    norm = re.sub(r'\s+', ' ', norm)
    return norm.strip()


def _extract_line_snippet(raw_text: str, match_start: int, match_end: int, padding: int = 40) -> str:
    """Extracts a readable snippet around a text match."""
    start = max(0, match_start - padding)
    end = min(len(raw_text), match_end + padding)
    snippet = raw_text[start:end].replace('\r', ' ').replace('\n', ' ')
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    if start > 0:
        snippet = '...' + snippet
    if end < len(raw_text):
        snippet = snippet + '...'
    return snippet


def _document_phrase_matches(raw_text: str, phrase: str):
    """Match whole phrases while retaining offsets into the actual document text."""
    def fold(value):
        chars, offsets = [], []
        for index, char in enumerate(value):
            for letter in unicodedata.normalize('NFKD', char).lower():
                if unicodedata.combining(letter):
                    continue
                if letter == '.' and chars and chars[-1].isalpha():
                    continue
                if letter in '-–—−':
                    letter = ' '
                if letter.isspace():
                    letter = ' '
                    if chars and chars[-1] == ' ':
                        continue
                chars.append(letter)
                offsets.append(index)
        return ''.join(chars), offsets

    corpus, offsets = fold(raw_text)
    expected, _ = fold(phrase)
    expected = expected.strip()
    if not expected:
        return None
    for match in re.finditer(r'(?<!\w)' + re.escape(expected) + r'(?!\w)', corpus):
        yield offsets[match.start()], offsets[match.end() - 1] + 1


def _match_document_phrase(raw_text: str, phrase: str):
    return next(_document_phrase_matches(raw_text, phrase), None)


def _negated_evidence(raw_text, start, end):
    before = re.split(r'[.;\n]', raw_text[max(0, start - 100):start])[-1]
    after = raw_text[end:end + 70]
    return bool(
        re.search(r'\b(?:no|not|without|missing|absent|lacks?)\b[^.;\n]{0,70}$', before, re.I)
        or re.match(r'\s+(?:(?:is|was|has\s+been)\s+)?(?:missing|absent|not\s+(?:attached|provided|present|included))\b', after, re.I)
    )


def resolve_requirement_checker_configuration(project_requirement: Any) -> dict[str, Any]:
    """Resolves effective checker configuration from template and project requirement.

    Precedence:
    1. ProjectRequirement.custom_fields['checker_configuration'] (project-specific override)
    2. Requirement.custom_field_schema['checker_configuration'] (program requirement template)
    3. Empty default dict {} (strict 'unchecked = not required'; unconfigured = no false warnings)
    """
    if not project_requirement:
        return {}

    config: dict[str, Any] = {}

    if isinstance(project_requirement, dict):
        base_cfg = {}
        schema = project_requirement.get('custom_field_schema')
        if isinstance(schema, dict):
            b_cfg = schema.get('checker_configuration') or schema.get('checker_config')
            if isinstance(b_cfg, dict):
                base_cfg = b_cfg

        override_cfg = {}
        for k in ('checker_configuration', 'checker_config'):
            if k in project_requirement and isinstance(project_requirement[k], dict):
                override_cfg = project_requirement[k]
                break
        if not override_cfg:
            cfields = project_requirement.get('custom_fields')
            if isinstance(cfields, dict):
                for k in ('checker_configuration', 'checker_config'):
                    if k in cfields and isinstance(cfields[k], dict):
                        override_cfg = cfields[k]
                        break
        config = {**base_cfg, **override_cfg}
    else:
        # 1. Base template configuration from Requirement model
        req_model = getattr(project_requirement, 'requirement', None)
        if not req_model and hasattr(project_requirement, 'custom_field_schema'):
            req_model = project_requirement
        elif not req_model and getattr(project_requirement, 'requirement_id', None):
            try:
                from app.models import Requirement
                from app.extensions import db
                req_model = db.session.get(Requirement, project_requirement.requirement_id)
            except Exception:
                req_model = None

        if req_model:
            template_schema = getattr(req_model, 'custom_field_schema', None)
            if isinstance(template_schema, dict):
                t_cfg = template_schema.get('checker_configuration') or template_schema.get('checker_config')
                if isinstance(t_cfg, dict):
                    config.update(t_cfg)
            t_direct = getattr(req_model, 'checker_configuration', None) or getattr(req_model, 'checker_config', None)
            if isinstance(t_direct, dict):
                config.update(t_direct)

        # 2. Layer project-specific requirement overrides
        custom_fields = getattr(project_requirement, 'custom_fields', None)
        if isinstance(custom_fields, dict):
            o_cfg = custom_fields.get('checker_configuration') or custom_fields.get('checker_config')
            if isinstance(o_cfg, dict):
                config.update(o_cfg)
        direct_cfg = getattr(project_requirement, 'checker_configuration', None) or getattr(project_requirement, 'checker_config', None)
        if isinstance(direct_cfg, dict):
            config.update(direct_cfg)

    if not config:
        return {}

    # Normalize configuration keys for consistent downstream access
    if 'required_context_fields' not in config:
        config['required_context_fields'] = list(config.get('expected_context_fields') or config.get('expected_fields') or [])
    if 'required_sections' not in config:
        config['required_sections'] = list(config.get('sections') or [])
    if 'required_phrases' not in config:
        config['required_phrases'] = list(config.get('phrases') or [])

    return config




def _configured_signatory_roles(config: dict[str, Any]) -> list:
    roles = config.get('signatory_roles')
    return list(['prepared_by', 'approved_by'] if roles is None else roles)


def requirement_checks_configured(config: dict[str, Any] | None) -> bool:
    """Whether effective configuration enables actual requirement criteria."""
    config = config or {}
    roles = _configured_signatory_roles(config)
    signatories = config.get('requires_signatories') and bool(roles or config.get('custom_signatory_roles'))
    context_fields = (config.get('expected_context_fields') or config.get('expected_fields')
                      or config.get('required_context_fields') or [])
    context_aliases = {'lgu', 'lgu_name', 'municipality', 'project', 'project_title',
                       'project_name', 'year', 'fiscal_year', 'fy', 'requirement',
                       'requirement_name', 'requirement_label'}
    context_enabled = (isinstance(context_fields, (list, tuple, set))
                       and bool(context_aliases.intersection(context_fields)))
    return bool(signatories or any(config.get(key) for key in (
        'requires_certification', 'requires_notarization', 'requires_date',
        'required_phrases', 'required_sections',
        'requires_lgu', 'check_lgu', 'requires_project_title', 'check_project_title',
        'requires_fiscal_year', 'check_fiscal_year',
        'requires_lgu_name', 'check_lgu_name', 'requires_project', 'check_project',
        'requires_year', 'check_year', 'requires_requirement', 'check_requirement',
        'requires_requirement_label', 'check_requirement_label',
    )) or context_enabled)


def _default_configuration_for_requirement(project_requirement: Any) -> dict[str, Any]:
    """Deprecated: Retained for backward compatibility in helper contexts."""
    return {}


def evaluate_document_evidence(
    extracted_text: str,
    checker_config: dict[str, Any] | None = None,
    *,
    file_name: str | None = None,
    extraction: dict[str, Any] | None = None,
    file_path: Path | str | Any = None,
    analysis_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluates extracted document text against the requirement's evidence configuration.

    Returns:
        dict containing:
            - 'evidence_checks': list of check results (key, label, check_type, state, snippet, explanation)
            - 'evidence_summary': total_required, detected_count, not_detected_count, all_required_detected
            - 'findings': list of actionable findings for not_detected required items
    """
    raw_text = str(extracted_text or '')
    # Metadata can identify an upload; it cannot prove its contents.
    normalized_corpus = normalize_text(raw_text)
    config = checker_config or {}

    requires_signatories = bool(config.get('requires_signatories', False))
    requires_certification = bool(config.get('requires_certification', False))
    requires_notarization = bool(config.get('requires_notarization', False))
    requires_date = bool(config.get('requires_date', False))
    required_phrases = list(dict.fromkeys(config.get('required_phrases') or []))
    required_sections = list(dict.fromkeys(config.get('required_sections') or []))

    # If no evidence checks are configured or enabled, return clean unconfigured state
    if not any([requires_signatories, requires_certification, requires_notarization, requires_date, bool(required_phrases), bool(required_sections)]):
        return {
            'evidence_checks': [],
            'evidence_summary': {
                'total_required': 0,
                'required_count': 0,
                'detected_count': 0,
                'not_detected_count': 0,
                'missing_count': 0,
                'all_required_detected': False,
                'manual_verification_count': 0,
                'status_message': 'No requirement-specific evidence checks configured',
            },
            'findings': [],
        }

    checks: list[dict[str, Any]] = []

    # 1. Signatory Checks
    if requires_signatories:
        configured_roles = _configured_signatory_roles(config)
        custom_roles = config.get('custom_signatory_roles') or []
        all_roles = configured_roles + [r for r in custom_roles if r and r not in configured_roles]
        for role_item in all_roles:
            check_result = _check_signatory_role(
                raw_text,
                normalized_corpus,
                role_item,
                extraction=extraction,
                file_path=file_path,
            )
            checks.append(check_result)

    # 2. Certification Check
    if requires_certification:
        custom_cert_phrases = config.get('certification_phrases') or []
        check_result = _check_certification(
            raw_text,
            normalized_corpus,
            custom_phrases=custom_cert_phrases,
            extraction=extraction,
        )
        checks.append(check_result)

    # 3. Notarization Check
    if requires_notarization:
        custom_notary_phrases = config.get('notarization_phrases') or []
        check_result = _check_notarization(
            raw_text,
            normalized_corpus,
            custom_phrases=custom_notary_phrases,
            extraction=extraction,
        )
        checks.append(check_result)

    # 4. Date Check
    if requires_date:
        date_result = _check_date(raw_text, extraction=extraction)
        checks.append(date_result)

    # 5. Required Phrases Check
    for idx, phrase in enumerate(required_phrases, 1):
        phrase_str = str(phrase).strip()
        if not phrase_str:
            continue
        phrase_result = _check_phrase_group(
            raw_text,
            normalized_corpus,
            phrases=[phrase_str],
            key=f'required_phrase_{idx}',
            label=f'Phrase: "{phrase_str}"',
            check_type='required_phrase',
            deficiency_category='other_documented_defect',
            missing_msg=f'Required phrase "{phrase_str}" was not detected in the document text.',
            missing_instruction=f'Verify that the document contains the required text: "{phrase_str}".',
        )
        checks.append(phrase_result)

    for idx, section in enumerate(required_sections, 1):
        section = str(section).strip()
        if section:
            checks.append(_check_phrase_group(
                raw_text, normalized_corpus, phrases=[section], key=f'required_section_{idx}',
                label=f'Section: "{section}"', check_type='required_section',
                deficiency_category='other_documented_defect',
                missing_msg=f'Required section "{section}" was not detected in the readable document text.',
                missing_instruction=f'Inspect the document for the "{section}" section; include it if it is missing.',
            ))

    metadata = (extraction or {}).get('metadata') or {}
    incomplete = bool((analysis_coverage or {}).get('is_partial') or metadata.get('extraction_incomplete')
                      or metadata.get('coverage_unknown') or metadata.get('unreadable_pages'))
    if incomplete:
        for check in checks:
            if check.get('state') != 'not_detected' or check.get('invalid_values'):
                continue
            check['state'] = 'needs_review'
            check['human_verification_required'] = True
            check['explanation'] = f'{check["label"]} could not be verified because some pages were unreadable or not analyzed.'
            check['finding_observation'] = check['explanation']
            check['corrective_instruction'] = 'Inspect the unreadable or unexamined pages in the original document before deciding whether evidence is missing.'

    return summarize_evidence_checks(checks)


def summarize_evidence_checks(checks):
    """Build consistent counts and findings after primary/supporting evidence checks."""
    # Calculate summary counts
    required_checks = [c for c in checks if c.get('state') != 'not_required']
    detected_count = sum(1 for c in required_checks if c.get('state') == 'detected')
    not_detected_count = sum(1 for c in required_checks if c.get('state') == 'not_detected')

    summary = {
        'total_required': len(required_checks),
        'required_count': len(required_checks),
        'detected_count': detected_count,
        'not_detected_count': not_detected_count,
        'missing_count': not_detected_count,
        'needs_review_count': sum(c.get('state') == 'needs_review' for c in required_checks),
        'all_required_detected': bool(required_checks) and detected_count == len(required_checks),
        'manual_verification_count': sum(bool(c.get('human_verification_required')) for c in required_checks),
    }

    # Generate actionable findings for any not_detected items
    findings = []
    for c in checks:
        for index, invalid_date in enumerate(c.get('invalid_values') or []):
            findings.append(rule_engine.finding(
                f'invalid_document_date_{index + 1}', 'warning',
                rule_engine.CATEGORY_DATE_TEMPORAL_CONSISTENCY,
                f'Date "{invalid_date}" is not a valid calendar date.',
                'Compare the extracted date with the source document. Correct it if the source also contains the invalid date.',
                rule='invalid_calendar_date', evidence_text=invalid_date,
            ))
        if c.get('state') == 'detected' and c.get('visual_evidence', {}).get('mark_detected') is False:
            findings.append(rule_engine.finding(
                f'signature_mark_unverified_{c["key"]}', 'needs_verification',
                rule_engine.CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE,
                f'Inspect the "{c["label"]}" signing area: no visual mark was detected.',
                'The printed signatory name was detected. Inspect the original signing area; '
                'request a signed copy only if you confirm the required signature is absent.',
                automation_level='human_verification', confidence='medium',
                deficiency_category='missing_signature_notarization',
                rule='signature_mark_unverified', page=c.get('page'), bbox=c.get('bbox'),
                evidence_text=c.get('snippet'),
            ))
        if c.get('state') in ('not_detected', 'needs_review'):
            if c.get('invalid_values'):
                continue  # The invalid-date finding already explains this failure.
            check_type = c.get('check_type')
            if check_type in ('signatory', 'certification', 'notarization'):
                cat = rule_engine.CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE
            elif check_type == 'date':
                cat = rule_engine.CATEGORY_DATE_TEMPORAL_CONSISTENCY
            elif check_type in ('required_phrase', 'phrase'):
                cat = rule_engine.CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE
            elif check_type == 'required_section':
                cat = rule_engine.CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY
            else:
                cat = rule_engine.CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE

            fid = f'missing_evidence_{c["key"]}'
            msg = c.get('explanation') or f'{c["label"]} not detected.'
            detail = c.get('corrective_instruction') or c.get('missing_instruction')
            obs = c.get('finding_observation') or c.get('explanation')
            inst = c.get('corrective_instruction') or c.get('missing_instruction')
            def_cat = c.get('deficiency_category') or 'other_documented_defect'
            auto_lvl = 'human_verification' if check_type in ('signatory', 'notarization') else 'automated_with_review'
            conf = 'medium' if check_type in ('signatory', 'notarization') else 'high'
            if c.get('state') == 'needs_review':
                auto_lvl, conf = 'human_verification', 'low'
            provenance = {'source': 'document_compliance_evidence_checker', 'check_key': c.get('key')}

            item = rule_engine.finding(
                fid,
                'needs_verification' if c.get('state') == 'needs_review' else 'warning',
                cat,
                msg,
                detail,
                rule=f'missing_{check_type}',
                deficiency_category=def_cat,
                finding_observation=obs,
                corrective_instruction=inst,
                automation_level=auto_lvl,
                confidence=conf,
                provenance=provenance,
                evidence_text=c.get('snippet'),
                page=None,
            )
            item['requirement_basis'] = {'source': 'requirement_configuration', 'check_key': c.get('key'), 'expected': c.get('label')}
            if c.get('supporting_evidence'):
                item['supporting_evidence'] = c['supporting_evidence']
            findings.append(item)


    return {
        'evidence_checks': checks,
        'evidence_summary': summary,
        'findings': findings,
    }


def _inspect_signature_area(
    file_path: Path | str | Any = None,
    *,
    page: int = 1,
    bbox: list[float] | dict[str, float] | None = None,
) -> dict[str, Any]:
    """Inspects expected signature area on an image for non-background pixel content.

    Strictly factual:
    - Never declares signature valid, genuine, or authentic.
    - Observes pixel contrast and stroke presence in the region above the printed name.
    - If visual inspection is unavailable (PDF/unsupported/missing file), returns not available.
    """
    if file_path is None:
        return {
            'mark_detected': None,
            'details': 'Automated visual analysis is not available; no image source provided.',
            'confidence': 'low',
        }

    img = None
    should_close = False
    original_frame = None
    try:
        from PIL import Image
        if hasattr(file_path, 'size') and hasattr(file_path, 'crop'):
            img = file_path
        else:
            p = Path(file_path)
            if not p.exists() or p.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}:
                return {
                    'mark_detected': None,
                    'details': 'Automated visual analysis is not available for this file type; only text evidence was evaluated.',
                    'confidence': 'low',
                }
            img = Image.open(p)
            should_close = True

        page_index = max(0, int(page or 1) - 1)
        if page_index >= getattr(img, 'n_frames', 1):
            return {'mark_detected': None, 'details': 'The identified page is not available in this image source.', 'confidence': 'low'}
        if getattr(img, 'n_frames', 1) > 1:
            original_frame = img.tell()
            img.seek(page_index)
        img_w, img_h = img.size
        if not bbox or not isinstance(bbox, (list, tuple, dict)):
            return {'mark_detected': None, 'details': 'No grounded signing-area location is available; inspect the document manually.', 'confidence': 'low'}
        elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            bx, by, bw, bh = bbox
            w_sig = min(1.0, max(bw * 1.5, 0.25))
            h_sig = min(0.20, max(bh * 2.5, 0.06))
            x_sig = max(0.0, bx - (w_sig - bw) / 2.0)
            y_sig = max(0.0, by - h_sig)
        elif isinstance(bbox, dict):
            bx = bbox.get('x', 0.5)
            by = bbox.get('y', 0.8)
            bw = bbox.get('width', 0.3)
            bh = bbox.get('height', 0.05)
            w_sig = min(1.0, max(bw * 1.5, 0.25))
            h_sig = min(0.20, max(bh * 2.5, 0.06))
            x_sig = max(0.0, bx - (w_sig - bw) / 2.0)
            y_sig = max(0.0, by - h_sig)
        else:
            return {'mark_detected': None, 'details': 'Invalid signing-area location; inspect the document manually.', 'confidence': 'low'}

        left = int(x_sig * img_w)
        top = int(y_sig * img_h)
        right = min(img_w, int((x_sig + w_sig) * img_w))
        bottom = min(img_h, int((y_sig + h_sig) * img_h))

        if right <= left or bottom <= top:
            return {
                'mark_detected': None,
                'details': 'Invalid signature bounding box coordinates.',
                'confidence': 'low',
            }

        crop = img.crop((left, top, right, bottom)).convert('L')
        hist = crop.histogram()
        total = sum(hist) or 1
        mean = sum(i * c for i, c in enumerate(hist)) / total
        variance = sum(((i - mean) ** 2) * c for i, c in enumerate(hist)) / total
        stddev = variance ** 0.5

        dark_threshold = max(30, int(mean - 25))
        dark_pixels = sum(hist[:dark_threshold])
        stroke_ratio = dark_pixels / total

        sig_bbox = [round(x_sig, 3), round(y_sig, 3), round(w_sig, 3), round(h_sig, 3)]

        if stroke_ratio >= 0.003 and stddev >= 7.0:
            return {
                'mark_detected': True,
                'details': 'Non-background pixel content detected in the expected signature area.',
                'confidence': 'medium',
                'signature_bbox': sig_bbox,
                'stroke_ratio': round(stroke_ratio, 4),
                'contrast_stddev': round(stddev, 2),
            }
        else:
            return {
                'mark_detected': False,
                'details': 'No observable visual mark detected in the expected signature area.',
                'confidence': 'medium',
                'signature_bbox': sig_bbox,
                'stroke_ratio': round(stroke_ratio, 4),
                'contrast_stddev': round(stddev, 2),
            }
    except Exception as exc:
        return {
            'mark_detected': None,
            'details': f'Visual analysis encountered an error: {exc}',
            'confidence': 'low',
        }
    finally:
        if img and original_frame is not None and not should_close:
            img.seek(original_frame)
        if should_close and img:
            try:
                img.close()
            except Exception:
                pass


def _check_signatory_role(
    raw_text: str,
    normalized_corpus: str,
    role_spec: Any,
    *,
    extraction: dict[str, Any] | None = None,
    file_path: Path | str | Any = None,
) -> dict[str, Any]:
    """Checks for presence of a specific signatory role in text and inspects visual area.

    Verifies:
    1. The presence of a recognized signatory role label/alias.
    2. An adjacent or underlying authorized name (inline or next line).
    3. Observable mark in expected signature area when image evidence is available.
    Excludes instructional sentences ('shall be prepared by'), budget headers ('Prepared Budget'),
    and empty signature lines without a name.
    """
    if isinstance(role_spec, dict):
        role_key = role_spec.get('role_key') or role_spec.get('role') or 'signatory'
        label = role_spec.get('label') or STANDARD_SIGNATORY_ROLES.get(role_key, {}).get('label') or role_key.replace('_', ' ').title()
        aliases = role_spec.get('aliases') or STANDARD_SIGNATORY_ROLES.get(role_key, {}).get('aliases') or [label.lower()]
    elif isinstance(role_spec, str):
        role_key = role_spec.strip().lower()
        std = STANDARD_SIGNATORY_ROLES.get(role_key)
        if std:
            label = std['label']
            aliases = std['aliases']
        else:
            label = role_key.replace('_', ' ').title()
            aliases = [role_key.replace('_', ' ')]
    else:
        role_key = 'signatory'
        label = 'Signatory'
        aliases = ['prepared by', 'approved by']

    safe_key = re.sub(r'[^a-z0-9_]+', '_', role_key)

    modal_clause = re.compile(
        r'\b(?:shall\s+be|must\s+be|to\s+be|should\s+be|will\s+be|is\s+to\s+be|needs?\s+to\s+be)\b',
        re.IGNORECASE,
    )
    instruction_target = re.compile(
        r'\b(?:the\s+)?(?:implementing\s+office|contractor|lgu|designated\s+engineer|agency|consultant)\b',
        re.IGNORECASE,
    )
    budget_or_heading = re.compile(
        r'\b(?:budget|cost|estimate|schedule|plan|appropriation|allocation|program)\b',
        re.IGNORECASE,
    )
    all_role_labels = re.compile(
        r'\b(?:prepared|reviewed|approved|certified|noted|attested|checked|verified|inihanda|sinuri|pinagtibay|pinatunayan|pinansin)\b',
        re.IGNORECASE,
    )
    structural_field = re.compile(
        r'\b(?:date|signature|designation|title|position)\s*[:\-—–]',
        re.IGNORECASE,
    )
    official_titles = re.compile(
        r'\b(?:municipal\s+engineer|city\s+engineer|provincial\s+engineer|project\s+engineer|'
        r'municipal\s+mayor|city\s+mayor|provincial\s+governor|governor|vice\s+mayor|'
        r'bac\s+chairperson|bac\s+chairman|bac\s+member|authorized\s+representative|'
        r'punong\s+barangay|barangay\s+captain|head\s+of\s+procuring\s+entity|hope)\b',
        re.IGNORECASE,
    )

    def _is_valid_name(text: str) -> bool:
        if not text:
            return False
        clean = text.strip(' \t:-—–_')
        if len(clean) < 2:
            return False
        if clean.lower() in ('by', 'by:', 'ni', 'ni:'):
            return False
        if re.search(r'^(?:\[|\(?\s*(?:name\b|printed\s+name\b|none\b|n/?a\b|not\s+applicable\b|tbd\b|to\s+follow\b|pending\b))', clean, re.I):
            return False
        if re.match(r'^(?:this|the|please|submit|attach|provide|ensure|all|for)\b', clean, re.I):
            return False
        if all_role_labels.search(clean):
            return False
        if instruction_target.search(clean):
            return False
        if official_titles.search(clean):
            return False
        if budget_or_heading.search(clean):
            return False
        if re.match(r'^(?:php|₱|\$)\s*[\d,]+', clean, re.IGNORECASE):
            return False
        if re.search(r'\b(?:date|signature|designation|title|position)\b', clean, re.IGNORECASE):
            return False
        return bool(re.search(r'[a-zA-Z]{2,}', clean))

    raw_lines = raw_text.splitlines()
    cleaned_lines = []
    for l in raw_lines:
        cl = re.sub(r'\bb\s+y\b', 'by', l, flags=re.IGNORECASE)
        cl = re.sub(r'\b8y\b', 'by', cl, flags=re.IGNORECASE)
        cleaned_lines.append(cl)

    sorted_aliases = sorted(aliases, key=len, reverse=True)
    detected_snippet = None

    for alias in sorted_aliases:
        is_colon_alias = alias.endswith(':')
        base_alias = alias.rstrip(':').strip()
        if is_colon_alias:
            alias_regex = re.compile(rf'(?<!\w){re.escape(base_alias)}\s*[:\-]', re.IGNORECASE)
        else:
            alias_regex = re.compile(rf'(?<!\w){re.escape(base_alias)}(?!\w)(?:\s*[:\-])?', re.IGNORECASE)

        for idx, line in enumerate(cleaned_lines):
            match = alias_regex.search(line)
            if not match:
                continue

            # Skip instruction modal clauses
            if modal_clause.search(line):
                continue

            after_match = line[match.end():].strip(' \t:-—–')

            # Skip budget or cost table headers
            if budget_or_heading.match(after_match):
                continue

            # Skip instruction targets
            if instruction_target.search(after_match):
                continue

            # Check inline name on same line
            # If line is a continuous paragraph (e.g. from whitespace normalization),
            # test the candidate name up to the next role label or structural
            # field keyword (Date, Signature, etc.) if any.
            inline_cand = after_match

            # Try to find a boundary: either another role label, an official title,
            # or a structural keyword that _is_valid_name would reject.
            next_role_match = all_role_labels.search(after_match)
            next_struct_match = structural_field.search(after_match)
            next_title_match = official_titles.search(after_match)

            # Pick the earliest boundary
            boundary_pos = None
            if next_role_match:
                boundary_pos = next_role_match.start()
            if next_struct_match:
                sp = next_struct_match.start()
                if boundary_pos is None or sp < boundary_pos:
                    boundary_pos = sp
            if next_title_match:
                tp = next_title_match.start()
                if boundary_pos is None or tp < boundary_pos:
                    boundary_pos = tp

            if boundary_pos is not None and boundary_pos > 0:
                bounded_cand = after_match[:boundary_pos].strip(' \t:-—–_')
                if _is_valid_name(bounded_cand):
                    detected_snippet = f"{match.group(0).strip()} {bounded_cand}"
                    break
            elif _is_valid_name(inline_cand):
                detected_snippet = line.strip()
                break

            # Check next lines if inline text is empty or underline
            if not after_match or re.match(r'^[\-_=.\s]+$', after_match):
                lookahead_idx = idx + 1
                found_next_name = None
                while lookahead_idx < len(cleaned_lines) and lookahead_idx <= idx + 4:
                    cand = cleaned_lines[lookahead_idx].strip()
                    lookahead_idx += 1
                    if not cand:
                        continue
                    if re.match(r'^[\-_=.\s]{3,}$', cand):
                        continue
                    if _is_valid_name(cand):
                        found_next_name = cand
                        break
                    else:
                        break

                if found_next_name:
                    detected_snippet = f'{line.strip()} {found_next_name}'
                    break

        if detected_snippet:
            break

    if detected_snippet:
        text_locations = (extraction.get('metadata') or {}).get('text_locations') or [] if extraction else []
        loc_info = _find_text_location_for_snippet(text_locations, detected_snippet) if text_locations else None
        page = loc_info.get('page') if loc_info else None
        bbox = loc_info.get('bbox') if loc_info else None
        visual_info = _inspect_signature_area(file_path, page=page, bbox=bbox)
        mark_det = visual_info.get('mark_detected')

        if mark_det is True:
            explanation = (
                f'Signatory role "{label}" detected ("{detected_snippet}"). '
                'Non-background pixel content detected in the expected signature area. '
                'Automated analysis cannot determine whether the visible mark is an authentic handwritten signature or official seal; '
                'manual reviewer verification is required.'
            )
        elif mark_det is False:
            explanation = (
                f'Signatory role "{label}" detected ("{detected_snippet}"), '
                'but no observable visual mark was detected in the expected signature area. '
                'Reviewer must inspect document for handwritten signature or official mark.'
            )
        else:
            explanation = (
                f'Signatory role "{label}" detected ("{detected_snippet}"). '
                'Automated visual analysis is not available for this document format/extraction; '
                'manual verification of signature is required.'
            )

        return {
            'key': f'signatory_{safe_key}',
            'label': label,
            'role_key': role_key,
            'check_type': 'signatory',
            'state': 'detected',
            'snippet': detected_snippet,
            'page': page,
            'bbox': bbox,
            'explanation': explanation,
            'text_evidence': {
                'role_label': label,
                'snippet': detected_snippet,
                'page': page,
                'bbox': bbox,
            },
            'visual_evidence': visual_info,
            'human_verification_required': True,
            'deficiency_category': 'missing_signature_notarization',
            'finding_observation': None,
            'corrective_instruction': None,
        }
    else:
        return {
            'key': f'signatory_{safe_key}',
            'label': label,
            'role_key': role_key,
            'check_type': 'signatory',
            'state': 'not_detected',
            'snippet': None,
            'page': None,
            'bbox': None,
            'explanation': f'Expected signatory role "{label}" was not detected in document text.',
            'text_evidence': None,
            'visual_evidence': {
                'mark_detected': None,
                'details': 'Cannot evaluate signature mark: required signatory text was not detected.',
                'confidence': 'low',
            },
            'human_verification_required': True,
            'deficiency_category': 'missing_signature_notarization',
            'finding_observation': (
                f'The required "{label}" signatory block was not detected in the readable document text. '
                'Automated analysis cannot verify handwritten signatures or physical stamps; manual verification required.'
            ),
            'corrective_instruction': (
                f'Reviewer must inspect the document for the "{label}" signatory block, authorized name, '
                'and physical or digital signature.'
            ),
        }


def _check_certification(
    raw_text: str,
    normalized_corpus: str,
    custom_phrases: list[str] | None = None,
    *,
    extraction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Checks for certification wording without asserting mark authenticity.

    Excludes narrative instruction mentions (e.g. 'shall submit a certified true copy',
    'must be certified true copy', checklist items).
    """
    key = 'certification'
    label = 'Certified True Copy / Certification'
    check_type = 'certification'
    deficiency_category = 'missing_signature_notarization'
    missing_msg = 'Expected certification phrase (e.g. Certified True Copy) was not detected.'
    missing_instruction = 'Ensure the document contains an official certification mark or statement.'

    phrases = list(STANDARD_CERTIFICATION_PHRASES)
    if custom_phrases:
        phrases.extend(p for p in custom_phrases if p)

    instruction_verbs = re.compile(
        r'\b(?:shall|must|should|to|will)\s+(?:submit|provide|attach|furnish|present|require)\s+(?:a\s+)?',
        re.IGNORECASE,
    )
    modal_be = re.compile(
        r'\b(?:shall|must|should|is\s+to|needs?\s+to)\s+be\s+(?:a\s+)?',
        re.IGNORECASE,
    )
    checklist_header = re.compile(
        r'\b(?:checklist|requirements|table\s+of\s+contents)\b',
        re.IGNORECASE,
    )

    detected_snippet = None

    for phrase in phrases:
        norm_p = normalize_text(phrase)
        if not norm_p:
            continue

        for start_pos, end_pos in _document_phrase_matches(raw_text, phrase):
            line_start = raw_text.rfind('\n', 0, start_pos)
            line_start = 0 if line_start == -1 else line_start + 1
            line_text_before = raw_text[line_start:start_pos]

            if re.search(r'^\s*(?:\d+[\.\)]|[-*•])\s+', raw_text[line_start:]):
                prev_text = raw_text[max(0, line_start - 200):line_start]
                if checklist_header.search(prev_text):
                    continue

            if instruction_verbs.search(line_text_before) or modal_be.search(line_text_before):
                continue
            if re.search(r'\b(?:shall|must|should|will)\s+(?:be\s+)?$', line_text_before, re.I):
                continue
            if _negated_evidence(raw_text, start_pos, end_pos):
                continue

            detected_snippet = _extract_line_snippet(raw_text, start_pos, end_pos)
            break

        if detected_snippet:
            break

    if detected_snippet:
        text_locations = (extraction.get('metadata') or {}).get('text_locations') or [] if extraction else []
        loc_info = _find_text_location_for_snippet(text_locations, detected_snippet) if text_locations else None
        page = loc_info.get('page') if loc_info else None
        bbox = loc_info.get('bbox') if loc_info else None
        return {
            'key': key,
            'label': label,
            'check_type': check_type,
            'state': 'detected',
            'snippet': detected_snippet,
            'page': page,
            'bbox': bbox,
            'explanation': f'{label} detected in document text.',
            'human_verification_required': True,
            'deficiency_category': deficiency_category,
            'finding_observation': None,
            'corrective_instruction': None,
        }
    else:
        return {
            'key': key,
            'label': label,
            'check_type': check_type,
            'state': 'not_detected',
            'snippet': None,
            'page': None,
            'bbox': None,
            'explanation': missing_msg,
            'deficiency_category': deficiency_category,
            'finding_observation': missing_msg,
            'corrective_instruction': missing_instruction,
        }


def _check_notarization(
    raw_text: str,
    normalized_corpus: str,
    custom_phrases: list[str] | None = None,
    *,
    extraction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Checks notarial wording without asserting authenticity or legal validity.

    Requires either:
    1. Strong notarial marker ('subscribed and sworn', 'notary public', 'jurat',
       'acknowledgement', 'notarial seal') OR
    2. Notarial register cluster ('Doc. No.' AND ('Page No.' OR 'Book No.' OR 'Series of 20xx'))
    Excludes instructional mentions (e.g. 'shall be notarized', 'must be notarized').
    """
    key = 'notarization'
    label = 'Notarization / Jurat'
    check_type = 'notarization'
    deficiency_category = 'missing_signature_notarization'
    missing_msg = 'Expected notarization / jurat block was not detected in the document text.'
    missing_instruction = 'Inspect the document for the required notarization or jurat. If absent, provide the required notarized copy with completed register details.'

    strong_markers = [
        'subscribed and sworn',
        'subscribed & sworn',
        'notary public',
        'notarial seal',
        'jurat',
        'acknowledgement',
        'acknowledgment',
    ]
    if custom_phrases:
        strong_markers.extend(p for p in custom_phrases if p)

    instruction_patterns = [
        r'\b(?:shall|must|should|to|will)\s+(?:be\s+)?notarized\b',
        r'\b(?:must|shall)\s+be\s+submitted\s+with\s+notarization\b',
        r'\bchecklist\b[^\n]*\bnotari[a-z]+\b',
        r'\b(?:shall|must|should|to|will|required\s+to)\s+(?:be\s+)?(?:signed\s+before|executed\s+before|submitted\s+to|certified\s+by)\s+(?:a\s+)?notary\b',
        r'\b(?:requirement|condition)\s+of\s+notarization\b',
        r'\bcopy\s+of\s+(?:the\s+)?[^\n]*notarized\b',
        r'\bcopy\s+of\s+(?:the\s+)?[^\n]*notary\s+public\b',
    ]

    # A heading or empty register is not completed notarial evidence. Match
    # each local block independently so instructions elsewhere cannot hide it.
    def register_populated(window):
        return bool(re.search(r'\bdoc\.?\s*no\.?\s*[:#-]?\s*\d+', window, re.I) and (
            re.search(r'\bpage\.?\s*no\.?\s*[:#-]?\s*\d+', window, re.I)
            or re.search(r'\bbook\.?\s*no\.?\s*[:#-]?\s*(?:\d+|[IVXLCDM]+)\b', window, re.I)
            or re.search(r'\bseries\s+(?:of\s+)?[1-9]\d{3}\b', window, re.I)
        ))

    detected_snippet = None
    incomplete_snippet = None
    for marker in strong_markers:
        for start, end in _document_phrase_matches(raw_text, marker):
            line_start = raw_text.rfind('\n', 0, start) + 1
            line_end = raw_text.find('\n', end)
            line = raw_text[line_start:line_end if line_end >= 0 else len(raw_text)]
            if _negated_evidence(raw_text, start, end) or any(re.search(pat, line, re.I) for pat in instruction_patterns):
                continue
            window = raw_text[max(0, start - 240):end + 240]
            normalized_marker = normalize_text(marker)
            if normalized_marker in {'subscribed and sworn', 'subscribed & sworn'} and re.search(r'_{3,}|\[(?:date|name|day|month|year)\]', window, re.I) and not register_populated(window):
                incomplete_snippet = _extract_line_snippet(raw_text, start, end)
                continue
            if normalized_marker in {'acknowledgment', 'acknowledgement', 'jurat', 'notarial seal', 'notary public'}:
                sworn_clause = re.search(r'\bsubscribed\s+(?:and|&)\s+sworn\b', window, re.I)
                unfilled = re.search(r'_{3,}|\[(?:date|name|day|month|year)\]', window, re.I)
                if not register_populated(window) and (not sworn_clause or unfilled):
                    if normalized_marker not in {'acknowledgment', 'acknowledgement'}:
                        incomplete_snippet = _extract_line_snippet(raw_text, start, end)
                    continue
            detected_snippet = _extract_line_snippet(raw_text, start, end)
            break
        if detected_snippet:
            break

    if not detected_snippet:
        for match in re.finditer(r'\bdoc\.?\s*no\.?', raw_text, re.I):
            window = raw_text[max(0, match.start() - 40):match.end() + 240]
            if register_populated(window) and not any(re.search(pat, window, re.I) for pat in instruction_patterns):
                detected_snippet = _extract_line_snippet(raw_text, match.start(), match.end(), padding=100)
                break

    if detected_snippet:
        text_locations = (extraction.get('metadata') or {}).get('text_locations') or [] if extraction else []
        loc_info = _find_text_location_for_snippet(text_locations, detected_snippet) if text_locations else None
        page = loc_info.get('page') if loc_info else None
        bbox = loc_info.get('bbox') if loc_info else None
        return {
            'key': key,
            'label': label,
            'check_type': check_type,
            'state': 'detected',
            'snippet': detected_snippet,
            'page': page,
            'bbox': bbox,
            'explanation': 'Notarial text detected. A reviewer must inspect the completed block and required marks.',
            'human_verification_required': True,
            'deficiency_category': deficiency_category,
            'finding_observation': None,
            'corrective_instruction': None,
        }
    else:
        return {
            'key': key,
            'label': label,
            'check_type': check_type,
            'state': 'needs_review' if incomplete_snippet else 'not_detected',
            'snippet': incomplete_snippet,
            'page': None,
            'bbox': None,
            'explanation': 'Notarial wording was found, but a completed notarial block could not be verified.' if incomplete_snippet else missing_msg,
            'human_verification_required': bool(incomplete_snippet),
            'deficiency_category': deficiency_category,
            'finding_observation': 'Notarial wording was found, but a completed notarial block could not be verified.' if incomplete_snippet else missing_msg,
            'corrective_instruction': missing_instruction,
        }


def _check_phrase_group(
    raw_text: str,
    normalized_corpus: str,
    *,
    phrases: list[str],
    key: str,
    label: str,
    check_type: str,
    deficiency_category: str,
    missing_msg: str,
    missing_instruction: str,
) -> dict[str, Any]:
    """Checks whether any phrase in a phrase list is present in the text."""
    detected_snippet = None
    for phrase in phrases:
        match = _match_document_phrase(raw_text, phrase)
        if match:
            detected_snippet = _extract_line_snippet(raw_text, *match)
            break

    if detected_snippet:
        return {
            'key': key,
            'label': label,
            'check_type': check_type,
            'state': 'detected',
            'snippet': detected_snippet,
            'explanation': f'{label} detected in document text.',
            'deficiency_category': deficiency_category,
            'finding_observation': None,
            'corrective_instruction': None,
        }
    else:
        return {
            'key': key,
            'label': label,
            'check_type': check_type,
            'state': 'not_detected',
            'snippet': None,
            'explanation': missing_msg,
            'deficiency_category': deficiency_category,
            'finding_observation': missing_msg,
            'corrective_instruction': missing_instruction,
        }


def _valid_calendar_date(value):
    text = value.lower().replace(',', ' ').replace('.', '')
    text = re.sub(r'(?<=\d)(?:st|nd|rd|th)\b', '', text)
    text = re.sub(r'\b(?:day\s+of|of)\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    months = {name: index for index, name in enumerate(
        ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), 1)}
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
            date.fromisoformat(text)
            return True
        if re.fullmatch(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}', text):
            first, second, year = map(int, re.split(r'[/\-]', text))
            for month, day in ((first, second), (second, first)):
                try:
                    date(year, month, day)
                    return True
                except ValueError:
                    continue
            return False
        parts = text.split()
        if len(parts) == 2 and parts[0][:3] in months:
            date(int(parts[1]), months[parts[0][:3]], 1)
            return True
        if len(parts) == 3:
            if parts[0][:3] in months:
                date(int(parts[2]), months[parts[0][:3]], int(parts[1]))
            else:
                date(int(parts[2]), months[parts[1][:3]], int(parts[0]))
            return True
    except (ValueError, KeyError):
        pass
    return False


def _check_date(raw_text: str, *, extraction: dict[str, Any] | None = None) -> dict[str, Any]:
    """Require a real calendar date, not merely a date-shaped string."""
    invalid_values = []
    valid_match = None
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(raw_text):
            if _valid_calendar_date(match.group(0)):
                valid_match = valid_match or match
            elif match.group(0) not in invalid_values:
                invalid_values.append(match.group(0))

    if valid_match:
        matched_date = valid_match.group(0)
        text_locations = ((extraction or {}).get('metadata') or {}).get('text_locations') or []
        loc_info = _find_text_location_for_snippet(text_locations, matched_date) if text_locations else None
        return {
            'key': 'document_date', 'label': 'Document Date', 'check_type': 'date',
            'state': 'detected', 'snippet': _extract_line_snippet(raw_text, valid_match.start(), valid_match.end()),
            'page': loc_info.get('page') if loc_info else None,
            'bbox': loc_info.get('bbox') if loc_info else None,
            'detected_value': matched_date, 'invalid_values': invalid_values,
            'explanation': f'Date "{matched_date}" detected in document text.',
            'deficiency_category': 'other_documented_defect',
            'finding_observation': None, 'corrective_instruction': None,
        }
    return {
        'key': 'document_date', 'label': 'Document Date', 'check_type': 'date',
        'state': 'not_detected', 'snippet': None, 'page': None, 'bbox': None,
        'detected_value': None, 'invalid_values': invalid_values,
        'explanation': 'No valid calendar date was detected in the readable document text.',
        'deficiency_category': 'other_documented_defect',
        'finding_observation': 'No recognizable valid date was detected in the readable document text. Reviewer should inspect for handwritten, stamped, or non-standard dates.',
        'corrective_instruction': 'Inspect the execution or issuance date. If it is missing or incorrect, provide the intended date in a readable format.',
    }
