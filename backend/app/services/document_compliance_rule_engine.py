import re
from pathlib import Path


# Effective scoring policy version. Bump whenever a behavior-affecting change
# lands (cap stack edit, weight rebalance, new finding category, etc.) so each
# persisted score_details payload carries the version it was scored under.
POLICY_VERSION = 'comet-checker-2026.10.20-r1.1-honesty'

# 7 General Review Categories (Locked in Phase 2)
CATEGORY_FILE_DOCUMENT_QUALITY = 'file_document_quality'
CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY = 'layout_structural_integrity'
CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE = 'required_information_keyword_occurrence'
CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE = 'signatory_official_mark_evidence'
CATEGORY_DATE_TEMPORAL_CONSISTENCY = 'date_temporal_consistency'
CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY = 'internal_cross_document_consistency'
CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY = 'calculation_arithmetic_consistency'

REVIEW_CATEGORIES = {
    CATEGORY_FILE_DOCUMENT_QUALITY,
    CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
    CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
    CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE,
    CATEGORY_DATE_TEMPORAL_CONSISTENCY,
    CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY,
    CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY,
}

REVIEW_CATEGORY_LABELS = {
    CATEGORY_FILE_DOCUMENT_QUALITY: 'File & Document Quality',
    CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY: 'Layout & Structural Integrity',
    CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE: 'Required Information & Keyword Occurrence',
    CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE: 'Signatory & Official-Mark Evidence',
    CATEGORY_DATE_TEMPORAL_CONSISTENCY: 'Date & Temporal Consistency',
    CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY: 'Internal & Cross-Document Consistency',
    CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY: 'Calculation & Arithmetic Consistency',
}


SUPPORTED_EVIDENCE_TYPES = {
    'generic_document',
    'official_receipt',
    'nadai_fund_transfer',
    'progress_photo',
    'program_of_works',
    'detailed_engineering_estimate',
    'billing_package',
    'resolution',
    'certification',
    'progress_report',
    'signature_or_stamp_page',
}

DEFAULT_EVIDENCE_TYPE = 'generic_document'
VISUAL_EVIDENCE_TYPES = {'progress_photo'}

SCORE_DIMENSIONS = {
    'file_health': 10,
    'readability_ocr': 15,
    'evidence_type_mapping': 15,
    'required_content_fields': 25,
    'format_template_layout': 20,
    'project_lgu_context': 10,
    'language_clarity': 5,
}

EVIDENCE_TYPE_WEIGHTS = {
    'generic_document': SCORE_DIMENSIONS,
    'official_receipt': {
        'file_health': 10,
        'readability_ocr': 20,
        'evidence_type_mapping': 15,
        'required_content_fields': 30,
        'format_template_layout': 15,
        'project_lgu_context': 10,
        'language_clarity': 0,
    },
    'nadai_fund_transfer': {
        'file_health': 6,
        'readability_ocr': 15,
        'evidence_type_mapping': 12,
        'required_content_fields': 35,
        'format_template_layout': 12,
        'project_lgu_context': 20,
        'language_clarity': 0,
    },
    'progress_photo': {
        'file_health': 80,
        'readability_ocr': 0,
        'evidence_type_mapping': 0,
        'required_content_fields': 0,
        'format_template_layout': 0,
        'project_lgu_context': 20,
        'language_clarity': 0,
    },
    'program_of_works': {
        'file_health': 8,
        'readability_ocr': 12,
        'evidence_type_mapping': 12,
        'required_content_fields': 30,
        'format_template_layout': 25,
        'project_lgu_context': 8,
        'language_clarity': 5,
    },
    'detailed_engineering_estimate': {
        'file_health': 8,
        'readability_ocr': 12,
        'evidence_type_mapping': 12,
        'required_content_fields': 30,
        'format_template_layout': 25,
        'project_lgu_context': 8,
        'language_clarity': 5,
    },
    'billing_package': {
        'file_health': 8,
        'readability_ocr': 17,
        'evidence_type_mapping': 15,
        'required_content_fields': 30,
        'format_template_layout': 15,
        'project_lgu_context': 12,
        'language_clarity': 3,
    },
    'resolution': {
        'file_health': 8,
        'readability_ocr': 12,
        'evidence_type_mapping': 12,
        'required_content_fields': 30,
        'format_template_layout': 18,
        'project_lgu_context': 10,
        'language_clarity': 10,
    },
    'certification': {
        'file_health': 8,
        'readability_ocr': 12,
        'evidence_type_mapping': 12,
        'required_content_fields': 30,
        'format_template_layout': 18,
        'project_lgu_context': 10,
        'language_clarity': 10,
    },
    'progress_report': {
        'file_health': 8,
        'readability_ocr': 15,
        'evidence_type_mapping': 12,
        'required_content_fields': 27,
        'format_template_layout': 18,
        'project_lgu_context': 10,
        'language_clarity': 10,
    },
    'signature_or_stamp_page': {
        'file_health': 20,
        'readability_ocr': 25,
        'evidence_type_mapping': 25,
        'required_content_fields': 10,
        'format_template_layout': 10,
        'project_lgu_context': 10,
        'language_clarity': 0,
    },
}

FINDING_DIMENSIONS = {
    'content': 'required_content_fields',
    'format': 'format_template_layout',
    'mapping': 'evidence_type_mapping',
    'reference': 'format_template_layout',
    'summary': 'file_health',
    'readability': 'readability_ocr',
    'context': 'project_lgu_context',
    'language': 'language_clarity',
}

CONTEXT_FIELD_POLICY = {
    'generic_document': {
        'lgu_name': 'warning',
        'project_title': 'warning',
        'fiscal_year': 'warning',
        'requirement_label': 'warning',
    },
    'official_receipt': {
        'lgu_name': 'warning',
        'project_title': 'info',
        'fiscal_year': 'info',
        'requirement_label': 'info',
    },
    'billing_package': {
        'lgu_name': 'warning',
        'project_title': 'info',
        'fiscal_year': 'info',
        'requirement_label': 'info',
    },
    'nadai_fund_transfer': {
        'lgu_name': 'warning',
        'project_title': 'info',
        'fiscal_year': 'warning',
        'requirement_label': 'warning',
    },
    'progress_photo': {
        'lgu_name': 'not_applicable',
        'project_title': 'not_applicable',
        'fiscal_year': 'not_applicable',
        'requirement_label': 'not_applicable',
    },
}

PHOTO_EVIDENCE_PATTERNS = (
    r'\bphoto\b',
    r'\bphotos\b',
    r'\bphotograph\b',
    r'\bphotographs\b',
    r'\bphotographic\b',
    r'\bphoto\s+documentation\b',
    r'\bphoto\s+evidence\b',
    r'\bbefore\s+after\b',
    r'\bbefore\s+and\s+after\b',
    r'\bproject\s+photo\b',
    r'\bprogress\s+photo\b',
)

NADAI_FUND_TRANSFER_PATTERNS = (
    r'\bnadai\b',
    r'\bn\s+a\s+d\s+a\s+i\b',
    r'\bnotice\s+of\s+authority\s+to\s+debit\s+account\b',
    r'\bauthority\s+to\s+debit\s+account\b',
    r'\bproof\s+of\s+fund\s+transfer\b',
    r'\btransfer\s+to\s+lgu\s+trust\s+fund\b',
    r'\blgu\s+trust\s+fund\b',
    r'\bconfirmation\s+of\s+fund\s+receipt\b',
    r'\breceipt\s+of\s+fund\b',
    r'\bnotice\s+of\s+cash\s+allocation\b',
)

OFFICIAL_RECEIPT_PATTERNS = (
    r'\bofficial\s+receipt\b',
    r'\bo\s*r\s*(?:no|number)?\b',
    r'\breceipt\s+no\b',
)

BILLING_PACKAGE_PATTERNS = (
    r'\bbilling\b',
    r'\binvoice\b',
    r'\bliquidation\b',
    r'\bstatement\s+of\s+receipts\s+and\s+disbursements\b',
    r'\bsord\b',
    r'\bstatement\s+of\s+disbursement\b',
)

CERTIFICATION_PATTERNS = (
    r'\bcertification\b',
    r'\bcertificate\b',
)

RESOLUTION_PATTERNS = (
    r'\bresolution\b',
    r'\bsanggunian\b',
    r'\bsangguniang\b',
    r'\bsb\s+resolution\b',
)

METADATA_LIST_KEYS = {
    'required_terms',
    'required_sections',
    'disallowed_terms',
    'allowed_extensions',
}


def normalize_corpus(value):
    normalized = str(value or '').lower()
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def contains_term(corpus, term):
    normalized_corpus = normalize_corpus(corpus)
    normalized = normalize_corpus(str(term or ''))
    if not normalized:
        return False
    if normalized in normalized_corpus:
        return True
    tokens = [token for token in normalized.split() if len(token) > 2]
    if len(tokens) <= 1:
        return False
    return all(token in normalized_corpus for token in tokens)


def any_term_present(corpus, terms):
    return any(contains_term(corpus, term) for term in terms if term)


def normalize_evidence_type(value):
    normalized = str(value or '').strip().lower()
    normalized = re.sub(r'[^a-z0-9]+', '_', normalized).strip('_')
    return normalized if normalized in SUPPORTED_EVIDENCE_TYPES else DEFAULT_EVIDENCE_TYPE


def _strict_evidence_type(value):
    """Normalize ``value`` and return it only when it resolves to a supported type.

    Returns ``None`` when the input is empty or not a recognized evidence type.
    """
    if value in (None, ''):
        return None
    normalized = str(value).strip().lower()
    normalized = re.sub(r'[^a-z0-9]+', '_', normalized).strip('_')
    return normalized if normalized in SUPPORTED_EVIDENCE_TYPES else None


def infer_evidence_type_from_requirement(
    *,
    requirement_name=None,
    requirement_type=None,
    annex_reference=None,
    custom_fields=None,
):
    """Infer an evidence type from requirement metadata when no profile exists."""
    if isinstance(custom_fields, dict):
        for key in ('evidence_type', 'checker_evidence_type', 'compliance_evidence_type'):
            inferred = _strict_evidence_type(custom_fields.get(key))
            if inferred:
                return inferred

    corpus = normalize_corpus(' '.join(
        str(value or '')
        for value in (requirement_name, requirement_type, annex_reference)
    ))
    if any(re.search(pattern, corpus) for pattern in NADAI_FUND_TRANSFER_PATTERNS):
        return 'nadai_fund_transfer'
    if any(re.search(pattern, corpus) for pattern in OFFICIAL_RECEIPT_PATTERNS):
        return 'official_receipt'
    if any(re.search(pattern, corpus) for pattern in BILLING_PACKAGE_PATTERNS):
        return 'billing_package'
    if any(re.search(pattern, corpus) for pattern in CERTIFICATION_PATTERNS):
        return 'certification'
    if any(re.search(pattern, corpus) for pattern in RESOLUTION_PATTERNS):
        return 'resolution'
    if any(re.search(pattern, corpus) for pattern in PHOTO_EVIDENCE_PATTERNS):
        return 'progress_photo'
    return None


def resolve_evidence_type(profile_selection):
    """Return ``(resolved_evidence_type, unresolved_value)`` for the selection.

    ``unresolved_value`` is ``None`` when every profile in the selection either
    omits ``evidence_type`` or supplies a recognized one. Otherwise it is the
    first unrecognized raw value encountered, so the service layer can surface
    a deterministic warning finding without having to re-walk the metadata.
    """
    profile_selection = profile_selection or {}
    fallback_value = None
    for profile in _reference_profiles_for_metadata(profile_selection):
        metadata = profile.get('profile_metadata') or {}
        raw = metadata.get('evidence_type')
        if not raw:
            continue
        normalized = _strict_evidence_type(raw)
        if normalized is not None:
            return normalized, fallback_value
        if fallback_value is None:
            fallback_value = raw
    inferred = _strict_evidence_type(profile_selection.get('inferred_evidence_type'))
    if inferred is not None:
        return inferred, fallback_value
    return DEFAULT_EVIDENCE_TYPE, fallback_value


def evidence_type_from_profile_selection(profile_selection):
    resolved, _ = resolve_evidence_type(profile_selection)
    return resolved


def context_field_severity(evidence_type, field_id):
    policy = CONTEXT_FIELD_POLICY.get(normalize_evidence_type(evidence_type), CONTEXT_FIELD_POLICY[DEFAULT_EVIDENCE_TYPE])
    severity = policy.get(field_id, 'warning')
    return None if severity == 'not_applicable' else severity


def metadata_minimum_text_chars(profile_selection):
    """Return the minimum readable-character threshold for the readability gate.

    The floor is always at least 20 when at least one reference profile is
    configured. When no profiles are configured (general-only mode), an
    explicit ``general_only_floor`` integer on ``profile_selection`` may
    lower the threshold for evidence types where a 20-character floor is
    unrealistic (e.g. signature pages, single-line receipts). In every
    other case the threshold defaults to 20.
    """
    profile_selection = profile_selection or {}
    used = _reference_profiles_for_metadata(profile_selection)
    evidence_type = evidence_type_from_profile_selection(profile_selection)
    if is_visual_evidence_type(evidence_type):
        explicit = _first_explicit_minimum_text_chars(used)
        return explicit if explicit is not None else 0
    if used:
        for profile in used:
            metadata = profile.get('profile_metadata') or {}
            try:
                return max(20, int(metadata.get('minimum_text_chars') or 20))
            except (TypeError, ValueError):
                return 20
        return 20
    floor = profile_selection.get('general_only_floor') if isinstance(profile_selection, dict) else None
    if isinstance(floor, int) and floor >= 0:
        return floor
    return 20


def metadata_findings(corpus=None, file_name=None, profile_selection=None, checker_config=None, *, document_text=None):
    """Configuration-driven structural and phrase findings.

    In Phase 2 (Profile Decoupling):
    - DocumentReferenceProfile historical rules (file_extension_not_allowed,
      disallowed_term_found, returned_sample_reference_only, required_term_missing)
      are completely removed from active evaluation.
    - required_sections and required_phrases derive strictly from requirement checker_config.
    """
    corpus = corpus if corpus is not None else (document_text or '')
    findings = []
    cfg = dict(checker_config or {})

    # Extract required sections and phrases from checker_config
    required_sections = list(cfg.get('required_sections') or [])
    required_phrases = list(cfg.get('required_phrases') or [])

    # Check required sections -> layout_structural_integrity
    for section in sorted(set(required_sections)):
        if not contains_term(corpus, section):
            findings.append(finding(
                f'required_section_missing:{section}',
                'warning',
                CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
                f'Required document section was not detected: {section}',
                f'Include the required "{section}" section in the documentary submission.',
                rule='missing_section',
                deficiency_category='missing_attachment',
                finding_observation=f'Required document section "{section}" was not detected in the submission.',
                corrective_instruction=f'Include the required "{section}" section in the documentary submission.',
                automation_level='automated_with_review',
            ))

    # Check required phrases -> required_information_keyword_occurrence
    for phrase in sorted(set(required_phrases)):
        if not contains_term(corpus, phrase):
            findings.append(finding(
                f'required_phrase_missing:{phrase}',
                'warning',
                CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
                f'Required template phrase was not found: {phrase}',
                f'Ensure the submitted document contains the required standard phrase "{phrase}".',
                rule='missing_required_phrase',
                deficiency_category='program_specific_non_conformity',
                finding_observation=f'Required template phrase "{phrase}" was not found in the readable document text.',
                corrective_instruction=f'Ensure the submitted document contains the required standard phrase "{phrase}".',
                automation_level='automated_with_review',
            ))

    return findings


def is_visual_evidence_type(evidence_type):
    return normalize_evidence_type(evidence_type) in VISUAL_EVIDENCE_TYPES


def text_document_rules_apply(profile_selection):
    evidence_type = evidence_type_from_profile_selection(profile_selection or {})
    if not is_visual_evidence_type(evidence_type):
        return True
    return any(
        (profile.get('profile_metadata') or {}).get('apply_text_rules_to_visual_evidence') is True
        for profile in _reference_profiles_for_metadata(profile_selection or {})
    )


def format_profile_rules_apply(profile_selection):
    evidence_type = evidence_type_from_profile_selection(profile_selection or {})
    if not is_visual_evidence_type(evidence_type):
        return True
    return any(
        (profile.get('profile_metadata') or {}).get('apply_format_profile_to_visual_evidence') is True
        for profile in _reference_profiles_for_metadata(profile_selection or {})
    )


def is_advisory_finding(item):
    """Recognize advisory presentation without changing the stored severity."""
    return (
        item.get('advisory_only') is True
        or item.get('severity') == 'advisory'
        or item.get('id') == 'language_quality_review'
    )


def summarize_findings(findings):
    """Canonical counts for generation, persistence, and read-time serialization."""
    counts = dict(blocker=0, warning=0, info=0, needs_verification=0, advisory=0, all=0)
    for item in findings or []:
        counts['all'] += 1
        group = 'advisory' if is_advisory_finding(item) else item.get('severity')
        if group in counts and group != 'all':
            counts[group] += 1
    return counts


def build_review_summary(findings, *, evidence_type=None, requirement_checks_configured=True):
    """Construct review metadata without score, weighting, or deduction math."""
    counts = summarize_findings(findings)

    return {
        'review_mode': 'manual_evaluation',
        'confidence_label': ('not_assessed' if not requirement_checks_configured else
                             'low' if counts['blocker'] else ('medium' if counts['warning'] else 'high')),
        'requirement_checks_configured': bool(requirement_checks_configured),
        'evidence_type': evidence_type or DEFAULT_EVIDENCE_TYPE,
        'policy_version': POLICY_VERSION,
        'findings_count': counts,
    }


def score_findings(findings, profile_selection=None, evidence_type=None):
    """Compatibility wrapper for historical callers and test suites.

    This function no longer computes a compliance score. It returns
    schema-compatible neutral metadata for historical database compatibility.
    """
    if evidence_type is None:
        evidence_type = evidence_type_from_profile_selection(profile_selection or {})
    summary = build_review_summary(findings, evidence_type=evidence_type)
    # Storage compatibility sentinels
    score = 100.0
    status = 'review_required'
    recommended_action = 'manual_review'
    # Provide backward-compatibility keys for legacy unit test callers
    weights = _weights_for_evidence_type(evidence_type)
    applied_cap = {'max_score': 100, 'reason': 'No score cap was applied.'}
    summary_compat = {
        **summary,
        'subscores': {dimension: 100 for dimension in weights},
        'weights': weights,
        'applied_weights': dict(weights),
        'caps': [applied_cap],
        'cap_applied': applied_cap,
        'top_reasons': _top_reasons(findings, applied_cap),
    }
    return score, status, recommended_action, summary_compat


def validate_profile_metadata(metadata):
    errors = {}
    cleaned = dict(metadata or {})

    evidence_type = cleaned.get('evidence_type')
    if evidence_type:
        normalized = normalize_evidence_type(evidence_type)
        canonical = _canonical_key(evidence_type)
        if normalized != canonical:
            errors['profile_metadata.evidence_type'] = (
                f'Select a supported evidence type: {", ".join(sorted(SUPPORTED_EVIDENCE_TYPES))}.'
            )
        else:
            cleaned['evidence_type'] = normalized

    for key in METADATA_LIST_KEYS:
        if key in cleaned:
            if isinstance(cleaned[key], str):
                cleaned[key] = list_metadata(cleaned[key])
            elif isinstance(cleaned[key], list):
                cleaned[key] = [str(item).strip() for item in cleaned[key] if str(item).strip()]
            else:
                errors[f'profile_metadata.{key}'] = 'Must be a list of strings.'

    if 'minimum_text_chars' in cleaned:
        try:
            minimum_text_chars = int(cleaned.get('minimum_text_chars') or 0)
        except (TypeError, ValueError):
            errors['profile_metadata.minimum_text_chars'] = 'Must be a non-negative integer.'
        else:
            if minimum_text_chars < 0:
                errors['profile_metadata.minimum_text_chars'] = 'Must be a non-negative integer.'
            else:
                cleaned['minimum_text_chars'] = minimum_text_chars

    if 'checks' in cleaned and not isinstance(cleaned.get('checks'), list):
        errors['profile_metadata.checks'] = 'Must be a list.'
    if 'score_policy' in cleaned and not isinstance(cleaned.get('score_policy'), dict):
        errors['profile_metadata.score_policy'] = 'Must be a JSON object.'
    if 'format_profile' in cleaned and not isinstance(cleaned.get('format_profile'), dict):
        errors['profile_metadata.format_profile'] = 'Must be a JSON object.'
    if 'format_profile_version' in cleaned and not isinstance(cleaned.get('format_profile_version'), str):
        errors['profile_metadata.format_profile_version'] = 'Must be text.'
    return cleaned, errors


def list_metadata(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(',') if item.strip()]
    return []


def _canonical_key(value):
    normalized = str(value or '').strip().lower()
    return re.sub(r'[^a-z0-9]+', '_', normalized).strip('_')


def map_to_review_category(category: str | None, rule: str | None = None) -> str:
    """Map any category or rule to one of the 7 locked general review categories."""
    cat = str(category or '').lower().strip()
    r = str(rule or '').lower().strip()

    if cat in REVIEW_CATEGORIES:
        return cat

    # Rule-specific mappings take precedence
    if any(k in r for k in ('signatory', 'signature', 'seal', 'stamp', 'jurat', 'notar', 'certif')):
        return CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE
    if any(k in r for k in ('date', 'temporal', 'chronology', 'time')):
        return CATEGORY_DATE_TEMPORAL_CONSISTENCY
    if any(k in r for k in ('arithmetic', 'financial_reconciliation', 'line_item', 'dupa', 'sum_mismatch', 'costing')):
        return CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY
    if any(k in r for k in ('cross_doc', 'parity', 'accomplishment', 'project_cost')):
        return CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY
    if any(k in r for k in ('section', 'layout', 'table', 'structure')):
        return CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY
    if any(k in r for k in ('blank', 'unreadable', 'visual_quality', 'blur', 'contrast', 'text_too_short', 'scan', 'language', 'spelling', 'grammar')):
        return CATEGORY_FILE_DOCUMENT_QUALITY
    if any(k in r for k in ('lgu', 'project_title', 'fiscal_year', 'phrase', 'keyword', 'term', 'gps', 'address')):
        return CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE

    # Legacy category fallbacks
    legacy_map = {
        'readability': CATEGORY_FILE_DOCUMENT_QUALITY,
        'summary': CATEGORY_FILE_DOCUMENT_QUALITY,
        'language': CATEGORY_FILE_DOCUMENT_QUALITY,
        'technical': CATEGORY_FILE_DOCUMENT_QUALITY,
        'visual': CATEGORY_FILE_DOCUMENT_QUALITY,
        'file_document_quality': CATEGORY_FILE_DOCUMENT_QUALITY,
        'layout': CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
        'structure': CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
        'format': CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
        'reference': CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
        'layout_structural_integrity': CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
        'content': CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
        'context': CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
        'mapping': CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
        'keyword': CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
        'required_info': CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
        'required_information': CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
        'required_information_keyword_occurrence': CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
        'signatory': CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE,
        'official_mark': CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE,
        'signatory_official_mark_evidence': CATEGORY_SIGNATORY_OFFICIAL_MARK_EVIDENCE,
        'date': CATEGORY_DATE_TEMPORAL_CONSISTENCY,
        'temporal': CATEGORY_DATE_TEMPORAL_CONSISTENCY,
        'date_temporal_consistency': CATEGORY_DATE_TEMPORAL_CONSISTENCY,
        'cross_document': CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY,
        'consistency': CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY,
        'internal_cross_document_consistency': CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY,
        'arithmetic': CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY,
        'calculation': CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY,
        'financial': CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY,
        'calculation_arithmetic_consistency': CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY,
    }
    return legacy_map.get(cat, CATEGORY_FILE_DOCUMENT_QUALITY)


def normalize_finding(
    finding_id=None,
    severity=None,
    category=None,
    rule=None,
    observation=None,
    *,
    evidence=None,
    locations=None,
    confidence='high',
    automation_level=None,
    reviewer_action=None,
    provenance=None,
    deficiency_category=None,
    dimension=None,
    # backward-compat keyword aliases
    message=None,
    detail=None,
    finding_observation=None,
    corrective_instruction=None,
    page=None,
    bbox=None,
    evidence_text=None,
    **kwargs,
):
    """Canonical Phase 3 normalized finding structure with backward compatibility."""
    if isinstance(finding_id, dict):
        raw = dict(finding_id)
        fid = str(raw.get('finding_id') or raw.get('id') or 'finding')
        rule_name = str(rule or raw.get('rule') or fid)
        cat = category or raw.get('category')
        sev_in = severity or raw.get('severity') or 'warning'
        obs = (
            observation
            or raw.get('observation')
            or finding_observation
            or raw.get('finding_observation')
            or message
            or raw.get('message')
            or fid
        )
        action = (
            reviewer_action
            or raw.get('reviewer_action')
            or corrective_instruction
            or raw.get('corrective_instruction')
            or detail
            or raw.get('detail')
            or 'Reviewer inspection required.'
        )
        locs = locations if locations is not None else raw.get('locations')
        ev = evidence if evidence is not None else raw.get('evidence')
        conf = confidence if confidence != 'high' else raw.get('confidence', 'high')
        auto_lvl = automation_level or raw.get('automation_level')
        prov = provenance or raw.get('provenance')
        def_cat = deficiency_category or raw.get('deficiency_category')
        dim = dimension or raw.get('dimension')
        det = detail if detail is not None else raw.get('detail')
        page_val = page if page is not None else raw.get('page')
        bbox_val = bbox if bbox is not None else raw.get('bbox')
        evidence_text_val = evidence_text if evidence_text is not None else raw.get('evidence_text')
    else:
        fid = str(finding_id or 'finding')
        rule_name = str(rule or fid)
        cat = category
        sev_in = severity or 'warning'
        obs = observation or finding_observation or message or fid
        action = reviewer_action or corrective_instruction or detail or 'Reviewer inspection required.'
        locs = locations
        ev = evidence
        conf = confidence
        auto_lvl = automation_level
        prov = provenance
        def_cat = deficiency_category
        dim = dimension
        det = detail
        page_val = page
        bbox_val = bbox
        evidence_text_val = evidence_text

    canonical_cat = map_to_review_category(cat, rule_name)

    locs = list(locs or [])
    ev = dict(ev or {})

    # Extract page, bbox, and evidence_text from evidence or locations if not explicitly supplied
    if page_val is None:
        if ev and ev.get('page') is not None:
            page_val = ev.get('page')
        elif locs and isinstance(locs[0], dict) and locs[0].get('page') is not None:
            page_val = locs[0].get('page')

    if bbox_val is None:
        if ev and (ev.get('bounding_box') is not None or ev.get('bbox') is not None):
            bbox_val = ev.get('bounding_box') if ev.get('bounding_box') is not None else ev.get('bbox')
        elif locs and isinstance(locs[0], dict) and locs[0].get('bbox') is not None:
            bbox_val = locs[0].get('bbox')

    if evidence_text_val is None:
        if ev and ev.get('text'):
            evidence_text_val = ev.get('text')
        elif locs and isinstance(locs[0], dict):
            evidence_text_val = locs[0].get('text') or locs[0].get('matched_text')

    # Keep evidence and locations synchronized with resolved coordinates
    if not ev and locs and isinstance(locs[0], dict):
        first = locs[0]
        ev = {
            'page': first.get('page', 1),
            'bounding_box': first.get('bbox'),
            'bbox_type': first.get('bbox_type', 'detected_text'),
            'text': first.get('text') or first.get('matched_text') or '',
        }
    elif ev and not locs:
        locs = [{
            'page': ev.get('page', 1),
            'bbox': ev.get('bounding_box'),
            'bbox_type': ev.get('bbox_type', 'detected_text'),
            'text': ev.get('text', ''),
        }]
    elif page_val is not None and not locs:
        locs = [{
            'page': page_val,
            'bbox': bbox_val,
            'bbox_type': 'detected_text' if bbox_val else 'whole_page',
            'text': evidence_text_val or '',
        }]
        if not ev:
            ev = {
                'page': page_val,
                'bounding_box': bbox_val,
                'bbox_type': 'detected_text' if bbox_val else 'whole_page',
                'text': evidence_text_val or '',
            }

    sev = str(sev_in).lower()
    if sev not in ('blocker', 'warning', 'info', 'needs_verification'):
        sev = 'needs_verification'

    auto_lvl = auto_lvl or (
        'human_verification'
        if sev in ('needs_verification', 'manual_verification_required')
        else 'automated_with_review'
    )

    det_final = det if det is not None else (obs or action)

    res = {
        'finding_id': fid,
        'id': fid,
        'severity': sev,
        'category': canonical_cat,
        'rule': rule_name,
        'observation': str(obs),
        'message': str(obs),
        'finding_observation': str(obs),
        'detail': det_final,
        'page': page_val,
        'bbox': bbox_val,
        'evidence_text': evidence_text_val,
        'reviewer_action': action,
        'corrective_instruction': corrective_instruction or action,
        'evidence': ev,
        'confidence': conf,
        'automation_level': auto_lvl,
        'provenance': prov or {},
        'deficiency_category': def_cat or 'other_documented_defect',
        'dimension': dim,
    }
    if locs:
        res['locations'] = locs
    return res



def finding(
    finding_id,
    severity,
    category,
    message=None,
    detail=None,
    *,
    observation=None,
    reviewer_action=None,
    dimension=None,
    locations=None,
    deficiency_category=None,
    finding_observation=None,
    corrective_instruction=None,
    automation_level=None,
    rule=None,
    evidence=None,
    confidence='high',
    provenance=None,
    page=None,
    bbox=None,
    evidence_text=None,
    **kwargs,
):
    obs = observation or finding_observation or message
    act = reviewer_action or corrective_instruction or detail
    return normalize_finding(
        finding_id=finding_id,
        severity=severity,
        category=category,
        rule=rule or finding_id,
        observation=obs,
        reviewer_action=act,
        detail=detail,
        corrective_instruction=corrective_instruction or act,
        dimension=dimension,
        locations=locations,
        evidence=evidence,
        deficiency_category=deficiency_category,
        automation_level=automation_level,
        confidence=confidence,
        provenance=provenance,
        page=page,
        bbox=bbox,
        evidence_text=evidence_text,
    )



def deduplicate_findings(findings):
    """Deduplicate findings based on composite key (id, category, severity, message, doc_id).

    Preserves original order and merges/retains richer fields (locations, detail, deficiency_category).
    Does NOT collapse findings from different documents.
    """
    if not findings:
        return []
    deduped = []
    seen = {}
    for item in findings:
        if not isinstance(item, dict):
            continue
        fid = item.get('id')
        cat = item.get('category')
        sev = item.get('severity')
        msg = item.get('message')
        doc_id = item.get('document_file_id') or item.get('file_name') or item.get('document_id')
        locs = item.get('locations') or []
        key = (fid, cat, sev, msg, doc_id)
        if key in seen:
            existing_idx = seen[key]
            # Merge richer attributes if present
            for field in ('detail', 'deficiency_category', 'finding_observation', 'corrective_instruction', 'automation_level'):
                if not deduped[existing_idx].get(field) and item.get(field):
                    deduped[existing_idx][field] = item.get(field)
            if locs:
                existing_locs = deduped[existing_idx].get('locations') or []
                for loc in locs:
                    if loc not in existing_locs:
                        existing_locs.append(loc)
                deduped[existing_idx]['locations'] = existing_locs
            continue
        seen[key] = len(deduped)
        deduped.append(dict(item))
    return deduped


def _reference_profiles_for_metadata(profile_selection):
    profile_selection = profile_selection or {}
    return profile_selection.get('used_profiles') or profile_selection.get('current_profiles') or []


def _first_explicit_minimum_text_chars(profiles):
    for profile in profiles or []:
        metadata = profile.get('profile_metadata') or {}
        if 'minimum_text_chars' not in metadata:
            continue
        try:
            return max(0, int(metadata.get('minimum_text_chars') or 0))
        except (TypeError, ValueError):
            return 0
    return None


def _weights_for_evidence_type(evidence_type):
    profile = EVIDENCE_TYPE_WEIGHTS.get(normalize_evidence_type(evidence_type), SCORE_DIMENSIONS)
    return dict(profile)


def _weighted_score(dimension_scores, weights):
    total_weight = sum(weights.values()) or 100
    total = sum((dimension_scores.get(dimension, 100) * weight) for dimension, weight in weights.items())
    return round(total / total_weight, 2)


def _score_caps(profile_selection, findings):
    # Phase 2: Reference profiles no longer impose score caps.
    return [{'max_score': 100, 'reason': 'No score cap was applied.'}]



def _confidence_label(score, applied_cap, blockers, warnings):
    if applied_cap['max_score'] < 80 or blockers:
        return 'low'
    if score >= 95 and not warnings:
        return 'high'
    return 'medium'


def _top_reasons(findings, applied_cap, *, limit=5):
    reasons = []
    seen = set()

    def _add(text):
        if not text or text in seen or len(reasons) >= limit:
            return
        reasons.append(text)
        seen.add(text)

    if applied_cap['max_score'] < 100:
        _add(applied_cap.get('reason'))
    for item in findings:
        if len(reasons) >= limit:
            break
        if item.get('severity') in {'blocker', 'warning'}:
            _add(item.get('message'))
    return reasons
def is_ocr_fallback(extraction_metadata):
    if not extraction_metadata:
        return False
    extractors = extraction_metadata.get('extractors') or []
    return 'tesseract' in extractors
