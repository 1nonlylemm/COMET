"""Self-hosted LanguageTool provider for documentary language checks.

The provider is intentionally optional and local-first. It calls a configured
LanguageTool HTTP endpoint only when enabled, then normalizes the returned
matches into COMET's advisory language-quality issue shape.
"""

from __future__ import annotations

import json
import re
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_LANGUAGE_TOOL_URL = 'http://languagetool:8010/v2/check'
DEFAULT_LANGUAGE = 'en-US'
DEFAULT_TIMEOUT_SECONDS = 8
DEFAULT_MAX_CHARS = 12000
DEFAULT_MIN_CONFIDENCE = 0.6

PHILIPPINE_ADMINISTRATIVE_TERMS = frozenset({
    'lgus',
    'brgy',
    'poblacion',
    'sanggunian',
    'sangguniang',
    'barangay',
    'bayan',
    'lungsod',
    'sitio',
    'purok',
    'punong',
    'kapitana',
    'kagawad',
    'lgsf-falgu',
    'lgsffalgu',
    'rbme-rlip',
    'rbmerlip',
    'rbme',
    'rlip',
})

PHILIPPINE_LEGAL_CONTRACT_TERMS = frozenset({
    'witnesseth',
    'conforme',
})

FORBIDDEN_GLOBAL_IGNORE_TERMS = frozenset({
    'fy',
    'conforme',
    'witnesseth',
})

CONTEXT_DEPENDENT_ACRONYMS = frozenset({
    'pow', 'sord', 'ded', 'mov', 'mpr', 'cofa', 'swa', 'fir', 'bac', 'abc', 'ada', 'twg', 'sb', 'coa', 'dof', 'btr', 'gaa',
})

DEFAULT_IGNORE_TERMS = {
    'barangay',
    'bayan',
    'blgf',
    'dbm',
    'dilg',
    'dpwh',
    'drrm',
    'drrmf',
    'falgu',
    'inihanda',
    'lddap',
    'lgsf',
    'lgu',
    'nadai',
    'nca',
    'nnc',
    'nta',
    'pdmu',
    'pinagtibay',
    'punong',
    'sangguniang',
    'saro',
    'subaybayan',
    *PHILIPPINE_ADMINISTRATIVE_TERMS,
}

NOISY_RULE_PATTERNS = (
    'STYLE',
    'TYPOGRAPHY',
    'CASING',
    'CAPITALIZATION',
    'UPPERCASE_SENTENCE_START',
    'EN_CAPITALIZATION',
    'PUNCTUATION_PARAGRAPH_END',
    'COMMA_PARENTHESIS_WHITESPACE',
    'WHITESPACE_RULE',
    'READABILITY',
    'SENTENCE_FRAGMENT',
    'FRAGMENT',
    'SHORT_PHRASE',
    'PASSIVE_VOICE',
    'PLAIN_ENGLISH',
    'WORDINESS',
)


def _is_noisy_rule(rule_id, category_name):
    combined = f'{rule_id or ""} {category_name or ""}'.upper()
    return any(pat in combined for pat in NOISY_RULE_PATTERNS)


def check_text(text, *, config=None, readability_confidence=1.0, http_post=None):
    """Return normalized LanguageTool issues or ``None`` when disabled.

    All provider failures are returned as metadata-shaped results instead of
    raising, so intake and compliance checking never depend on the local
    LanguageTool server being available.
    """
    config = config or {}
    if not _config_bool(config, 'DOCUMENT_LANGUAGE_TOOL_ENABLED', default=False):
        return None

    confidence = _safe_float(readability_confidence, 1.0)
    min_confidence = _config_float(config, 'DOCUMENT_LANGUAGE_TOOL_MIN_CONFIDENCE', DEFAULT_MIN_CONFIDENCE)
    if confidence < min_confidence:
        return {
            'provider': 'languagetool',
            'status': 'skipped',
            'reason': 'readability_confidence_below_threshold',
            'readability_confidence': round(confidence, 2),
            'issues': [],
        }

    source_text = str(text or '').strip()
    if not source_text or len(source_text) < 40:
        return {
            'provider': 'languagetool',
            'status': 'skipped',
            'reason': 'insufficient_readable_text',
            'issues': [],
        }

    max_chars = max(_config_int(config, 'DOCUMENT_LANGUAGE_TOOL_MAX_CHARS', DEFAULT_MAX_CHARS), 1)
    checked_text = source_text[:max_chars]
    language = _config_value(config, 'DOCUMENT_LANGUAGE_TOOL_LANGUAGE', DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE
    url = _config_value(config, 'DOCUMENT_LANGUAGE_TOOL_URL', DEFAULT_LANGUAGE_TOOL_URL) or DEFAULT_LANGUAGE_TOOL_URL
    timeout = max(_config_int(config, 'DOCUMENT_LANGUAGE_TOOL_TIMEOUT_SECONDS', DEFAULT_TIMEOUT_SECONDS), 1)

    request = _language_tool_request(url, checked_text, language)
    try:
        response = (http_post or _http_post)(request, timeout)
        payload = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            'provider': 'languagetool',
            'status': 'error',
            'language': language,
            'url': _safe_url_label(url),
            'error': str(exc)[:300],
            'issues': [],
        }

    grounding_map = config.get('GROUNDING_TERMS_MAP') or {}
    phrase_entities = config.get('GROUNDING_PHRASE_ENTITIES') or []
    issues, suppressed_issues = _normalize_matches(
        payload.get('matches') or [],
        checked_text,
        ignore_terms=_ignore_terms(config),
        grounding_map=grounding_map,
        phrase_entities=phrase_entities,
        max_issues=None,
    )
    return {
        'provider': 'languagetool',
        'status': 'ok',
        'language': language,
        'detected_language': _detected_language(payload),
        'url': _safe_url_label(url),
        'checked_chars': len(checked_text),
        'truncated': len(source_text) > len(checked_text),
        'match_count': len(issues),
        'issues': issues[:50],
        'suppressed_issues': suppressed_issues,
    }


def _language_tool_request(url, text, language):
    body = urlencode({
        'language': language,
        'text': text,
    }).encode('utf-8')
    return Request(
        url,
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'},
        method='POST',
    )


def _http_post(request, timeout):
    return urlopen(request, timeout=timeout)


TABLE_HEADER_WORDS = frozenset({
    'QUANTITY', 'UNIT', 'COST', 'TOTAL', 'PRICE', 'AMOUNT', 'ITEM',
    'DESCRIPTION', 'DATE', 'NUMBER', 'STATUS', 'TYPE', 'PHP', 'NO', 'REF',
    'RECEIVED', 'DOCUMENT',
})


def _is_repetition_rule(rule_id):
    normalized = str(rule_id or '').upper()
    return bool('REPEAT' in normalized or 'REPETITION' in normalized)


def _is_extraction_artifact(matched_text, rule_id=None):
    raw = str(matched_text or '').strip()
    if not raw:
        return False

    # Font kerning split: single letter separated by whitespace from the rest of the word (e.g. 'T ank', 'T oyota', 'T wo')
    if re.match(r'^[A-Za-z]\s+[a-z]{2,}$', raw):
        return True

    # Split hyphen with irregular whitespace (e.g. 'project- related')
    if str(rule_id or '').upper() == 'EN_SPLIT_WORDS_HYPHEN' or re.search(r'\w+-\s+\w+', raw):
        return True

    # Fused table column headers / form fields (PascalCase / CamelCase transition e.g. 'Typedocument', 'DescriptionQuantity', 'ReceivedPHP')
    if re.search(r'[a-z][A-Z]', raw):
        return True

    # Concatenation of known table headers (e.g. 'QUANTITYUNIT', 'COSTTOTAL', 'Typedocument')
    upper_raw = raw.upper()
    if len(raw) >= 6 and upper_raw.isalpha():
        for word in TABLE_HEADER_WORDS:
            if upper_raw.startswith(word) and len(upper_raw) > len(word):
                remainder = upper_raw[len(word):]
                if remainder in TABLE_HEADER_WORDS:
                    return True

    return False


# Bounded vocabulary sets for legal phrase signatory classification (Phase 3.28)
COMMON_PROSE_WORDS = frozenset({
    # Articles, determiners, pronouns
    'the', 'this', 'that', 'these', 'those', 'a', 'an', 'all', 'any', 'each', 'every', 'some',
    'we', 'you', 'they', 'he', 'she', 'it', 'our', 'your', 'their', 'his', 'her', 'its',
    # Verbs
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'do', 'does', 'did', 'shall', 'will', 'should', 'would', 'may', 'might', 'must', 'can', 'could',
    'require', 'requires', 'required', 'follow', 'follows', 'following', 'remain', 'remains',
    'list', 'listed', 'submit', 'submits', 'submitted', 'note', 'noted', 'notes',
    'state', 'states', 'stated', 'wrote', 'said', 'concluded', 'explained', 'correct', 'corrected',
    # Prepositions & conjunctions
    'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from', 'about', 'into', 'through',
    'after', 'before', 'under', 'above', 'between', 'and', 'or', 'but', 'because', 'although', 'if', 'when', 'where', 'as',
    # Prose nouns / adjectives commonly starting or appearing in narrative
    'document', 'documents', 'section', 'sections', 'attachment', 'attachments', 'portion', 'portions',
    'paragraph', 'paragraphs', 'clause', 'clauses', 'requirement', 'requirements', 'payment', 'payments',
    'contract', 'contracts', 'terms', 'discrepancy', 'deficiency', 'deficiencies', 'correction',
    'ordinary', 'narrative', 'please', 'kindly', 'additional', 'incomplete', 'unresolved', 'committee',
})

RECOGNIZED_SIGNATORY_HONORIFICS = (
    r'(?:(?:Engr|Atty|Hon|Mayor|Gov|Governor|Vice-Mayor|Vice\s+Mayor|Dr|Arch|Ar|Mr|Ms|Mrs|Capt|Col|Gen|Director|Dir)\.?)'
)

RECOGNIZED_SIGNATORY_ROLES = (
    r'(?:General\s+Manager|Gen\.?\s+Manager|Project\s+Manager|Managing\s+Officer|'
    r'Authorized\s+Managing\s+Officer|AMO|Proprietor|Owner|Authorized\s+Representative|'
    r'President|Vice\s+President|CEO|COO|Contractor|Municipal\s+Mayor|Provincial\s+Governor|'
    r'BAC\s+Chair(?:person|man)?|HOPE|Head\s+of\s+Procuring\s+Entity)'
)

SIGNATURE_LINE_PATTERN = re.compile(
    r'^(?:[_.\-~]{3,}|\[signature\]|\(signature\)|\(sgd\.?\)|\(SGD\.?\)|\(Sgd\.?\)|\[sgd\.?\])',
    re.IGNORECASE,
)

ELECTRONIC_SIG_PATTERN = re.compile(
    r'^/s/\s+[A-Za-z0-9À-ÿ]',
    re.IGNORECASE,
)

HONORIFIC_NAME_PATTERN = re.compile(
    rf'^(?:/s/\s+)?{RECOGNIZED_SIGNATORY_HONORIFICS}\s+[A-ZÀ-ÖØ-Þ][A-Za-z0-9À-ÿ.\'-]*(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-z0-9À-ÿ.\'-]*){{1,3}}',
    re.IGNORECASE,
)

ROLE_PATTERN = re.compile(
    rf'^{RECOGNIZED_SIGNATORY_ROLES}',
    re.IGNORECASE,
)

REPORTING_VERBS_PATTERN = re.compile(
    r'\b(?:says|wrote|concluded|states|explained|quoted|uses|contains|discussed)\b',
    re.IGNORECASE,
)

NARRATIVE_INTRO_PATTERN = re.compile(
    r'\b(?:the\s+bidder\'s|in|signed\s+as|refers\s+to|clause|mentioned)\s*$',
    re.IGNORECASE,
)


def _is_signatory_payload(line: str) -> bool:
    """Determine whether text following 'Conforme:' strongly resembles a signatory payload rather than prose."""
    cleaned = line.strip()
    if not cleaned:
        return False

    # 1. Signature line placeholder (e.g. ____________________, [signature], (signature))
    if SIGNATURE_LINE_PATTERN.match(cleaned):
        return True

    # Signature line fill followed by name/title (e.g. "________ Authorized Representative")
    if re.match(r'^[_.\-~]{3,}\s*(?:[A-Za-z]|$)', cleaned):
        return True

    # 2. Electronic signature notation (e.g. /s/ Juan Dela Cruz, /s/ Engr. Juan Dela Cruz)
    if ELECTRONIC_SIG_PATTERN.match(cleaned):
        words = re.findall(r'[A-Za-z]+', cleaned[3:])
        if words and not any(w.lower() in COMMON_PROSE_WORDS for w in words[:4]):
            return True

    # 3. Honorific + Name (e.g. Engr. Juan Dela Cruz, Atty. Pedro Santos, MAYOR JUAN DELA CRUZ)
    m_hon = HONORIFIC_NAME_PATTERN.match(cleaned)
    if m_hon:
        words = re.findall(r'[A-Za-z]+', m_hon.group(0))
        if words and not any(w.lower() in COMMON_PROSE_WORDS for w in words):
            return True

    # 4. Standard Signatory Title / Role (e.g. General Manager, Authorized Representative)
    m_role = ROLE_PATTERN.match(cleaned)
    if m_role:
        return True

    # 5. Standalone Proper Person Name: 2 to 4 capitalized tokens, no digits, no prose words
    m_name = re.match(r'^[A-ZÀ-ÖØ-Þ][A-Za-z0-9À-ÿ.\'-]*(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-z0-9À-ÿ.\'-]*){1,3}', cleaned)
    if m_name:
        name_str = m_name.group(0)
        tokens = [t for t in re.split(r'\s+', name_str) if t]
        if 2 <= len(tokens) <= 4:
            lower_words = [re.sub(r'[^a-zA-Z]', '', t).lower() for t in tokens if re.sub(r'[^a-zA-Z]', '', t)]
            if all(lw not in COMMON_PROSE_WORDS for lw in lower_words):
                if all(t[0].isupper() or t in ('de', 'del', 'dela', 'da', 'di', 'van', 'von', 'Jr.', 'Sr.', 'III', 'IV') for t in tokens if t[0].isalpha()):
                    return True

    return False


def _classify_conforme_context(text: str, offset: int, length: int):
    """Contextual classifier for 'conforme' signatory header usage."""
    line_start = text.rfind('\n', 0, offset)
    start_pos = 0 if line_start == -1 else line_start + 1
    preceding = text[start_pos:offset]

    if preceding.strip():
        if NARRATIVE_INTRO_PATTERN.search(preceding) or REPORTING_VERBS_PATTERN.search(preceding):
            return False, None
        prec_words = re.findall(r'[A-Za-z]+', preceding[-30:])
        if any(w.lower() in ('said', 'wrote', 'committee', 'states', 'note', 'section', 'bidder', 'clause') for w in prec_words):
            return False, None

    after_offset = offset + length
    remainder = text[after_offset:]

    # 1. Line-standing header: 'conforme' alone on its line (with optional colon/dash)
    m_linestanding = re.match(r'^[ \t]*[:\-]?\s*(?:\r?\n|$)', remainder)
    if m_linestanding:
        matched_str = text[offset:after_offset + m_linestanding.end()].strip()
        return True, matched_str or 'Conforme:'

    # 2. Same-line header with colon followed by signatory payload:
    m_delim = re.match(r'^[ \t]*:[ \t]*', remainder)
    if m_delim:
        payload_start = after_offset + m_delim.end()
        newline_pos = text.find('\n', payload_start)
        first_line = text[payload_start:newline_pos] if newline_pos != -1 else text[payload_start:]
        if newline_pos == -1 and len(first_line) > 80:
            first_line = first_line[:80]

        if _is_signatory_payload(first_line):
            matched_str = text[offset:payload_start].strip()
            return True, matched_str or 'Conforme:'

    return False, None


def _classify_witnesseth_context(text: str, offset: int, length: int):
    """Contextual classifier for 'witnesseth' contract preamble usage."""
    before_char = text[offset-1] if offset > 0 else ''
    after_char = text[offset+length] if offset + length < len(text) else ''
    if before_char in ('"', "'", '“', '‘') or after_char in ('"', "'", '”', '’'):
        return False, None

    lookback_start = max(0, offset - 60)
    preceding_window = text[lookback_start:offset]

    if any(q in preceding_window[-20:] for q in ('"', "'", '“', '‘')):
        return False, None

    if REPORTING_VERBS_PATTERN.search(preceding_window):
        return False, None

    line_start = text.rfind('\n', 0, offset)
    line_start = 0 if line_start == -1 else line_start + 1
    line_preceding = text[line_start:offset]

    # Case A: Line-standing WITNESSETH on its own line
    if not line_preceding.strip():
        remainder = text[offset+length:]
        m_standalone = re.match(r'^\s*[:;,]?\s*(?:\r?\n|$)', remainder)
        if m_standalone:
            matched_str = text[offset:offset+length + m_standalone.end()].strip()
            return True, matched_str or 'WITNESSETH:'

    # Case B: Line-initial operative preamble
    if not line_preceding.strip() or line_preceding.strip().upper() == 'NOW THIS AGREEMENT':
        remainder = text[offset+length:]
        m_that = re.match(r'^\s*[,:]?\s+that\b', remainder, re.IGNORECASE)
        if m_that:
            matched_str = text[line_start:offset+length + m_that.end()].strip()
            return True, matched_str or 'WITNESSETH that'
        m_follows = re.match(r'^\s*[,:]?\s+as\s+follows\b', remainder, re.IGNORECASE)
        if m_follows:
            matched_str = text[line_start:offset+length + m_follows.end()].strip()
            return True, matched_str or 'NOW THIS AGREEMENT WITNESSETH AS FOLLOWS'

    # Case C: Preamble formula NOW THIS AGREEMENT WITNESSETH AS FOLLOWS
    match_start = offset - len('NOW THIS AGREEMENT ')
    if match_start >= 0 and text[match_start:offset].upper() == 'NOW THIS AGREEMENT ':
        remainder = text[offset+length:]
        if re.match(r'^\s*[,:]?\s+as\s+follows\b', remainder, re.IGNORECASE):
            return True, 'NOW THIS AGREEMENT WITNESSETH AS FOLLOWS'

    return False, None


def _check_legal_phrase_context(issue, text):
    """Check whether a flagged term occurs within a recognized legal phrase context.

    Restricted strictly to:
    1. "conforme" in signatory-header context (e.g. "Conforme:")
    2. "witnesseth" in contract-preamble context (e.g. "WITNESSETH that", "NOW THIS AGREEMENT WITNESSETH")
    """
    matched = _normalize_term(issue.get('matched_text'))
    if matched not in ('conforme', 'witnesseth'):
        return None

    offset = issue.get('offset', -1)
    length = issue.get('length', 0)
    if offset < 0 or length <= 0 or not text:
        return None

    if matched == 'conforme':
        is_valid, phrase = _classify_conforme_context(text, offset, length)
        if is_valid:
            return {
                'matched_text': issue.get('matched_text'),
                'type': issue.get('type'),
                'rule_id': issue.get('rule_id'),
                'offset': offset,
                'length': length,
                'grounding_source': 'LEGAL_SIGNATORY_HEADER_CONTEXT',
                'grounding_record': 'document_phrase_context',
                'grounding_classification': 'PHRASE-CONTEXT ONLY',
                'grounding_reason': 'signatory_header_conforme',
                'contextual_phrase': phrase or 'Conforme:',
                'match_kind': 'CONTEXTUAL PHRASE MATCH',
                'message': issue.get('message'),
            }
    elif matched == 'witnesseth':
        is_valid, phrase = _classify_witnesseth_context(text, offset, length)
        if is_valid:
            return {
                'matched_text': issue.get('matched_text'),
                'type': issue.get('type'),
                'rule_id': issue.get('rule_id'),
                'offset': offset,
                'length': length,
                'grounding_source': 'CONTRACT_PREAMBLE_CONTEXT',
                'grounding_record': 'document_phrase_context',
                'grounding_classification': 'PHRASE-CONTEXT ONLY',
                'grounding_reason': 'contract_preamble_witnesseth',
                'contextual_phrase': phrase or 'contract_preamble_witnesseth',
                'match_kind': 'CONTEXTUAL PHRASE MATCH',
                'message': issue.get('message'),
            }

    return None


def _normalize_matches(
    matches,
    text,
    *,
    ignore_terms,
    include_extraction_artifacts=False,
    grounding_map=None,
    phrase_entities=None,
    max_issues=50,
):
    issues = []
    suppressed_issues = []
    grounding_map = grounding_map or {}
    phrase_entities = phrase_entities or []
    allowed_types = ('spelling', 'grammar', 'extraction_artifact') if include_extraction_artifacts else ('spelling', 'grammar')

    # Pre-index phrase entity occurrences in text
    phrase_spans = []
    for pe in phrase_entities:
        reg = pe.get('regex')
        if reg is None:
            raw_phrase = pe.get('raw_phrase') or ''
            words = [w for w in re.findall(r"[A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ'/-]*", raw_phrase) if w]
            if len(words) > 1:
                pattern = r'\b' + r'[\s-]+'.join(re.escape(w) for w in words) + r'\b'
                reg = re.compile(pattern, re.IGNORECASE)
                pe['regex'] = reg
        if reg:
            for m in reg.finditer(text):
                phrase_spans.append((m.start(), m.end(), pe))

    for match in matches:
        if not isinstance(match, dict):
            continue
        issue = _issue_from_match(match, text)
        if not issue:
            continue
        if issue.get('type') not in allowed_types:
            continue
        if _is_noisy_rule(issue.get('rule_id'), issue.get('category')):
            continue

        rule_id = str(issue.get('rule_id') or '').strip()
        if _is_repetition_rule(rule_id):
            issues.append(issue)
            continue

        offset = issue.get('offset', -1)
        length = issue.get('length', 0)
        end_offset = offset + length

        # 1. Phrase-aware contextual suppression check
        matched_phrase_entity = None
        if offset >= 0 and length > 0 and phrase_spans:
            for p_start, p_end, pe in phrase_spans:
                if p_start <= offset and end_offset <= p_end:
                    matched_phrase_entity = pe
                    break

        if matched_phrase_entity:
            suppressed_issues.append({
                'matched_text': issue.get('matched_text'),
                'type': issue.get('type'),
                'rule_id': issue.get('rule_id'),
                'offset': offset,
                'length': length,
                'grounding_source': matched_phrase_entity.get('source'),
                'grounding_record': matched_phrase_entity.get('record'),
                'grounding_classification': matched_phrase_entity.get('classification'),
                'grounding_reason': matched_phrase_entity.get('reason'),
                'contextual_phrase': matched_phrase_entity.get('raw_phrase'),
                'match_kind': 'CONTEXTUAL PHRASE MATCH',
                'message': issue.get('message'),
            })
            continue

        # 1b. Recognized legal phrase-context check (conforme signatory header / witnesseth preamble)
        legal_phrase_suppression = _check_legal_phrase_context(issue, text)
        if legal_phrase_suppression:
            suppressed_issues.append(legal_phrase_suppression)
            continue

        # 2. Token / Code / Admin Vocabulary check
        if _should_ignore_issue(issue, ignore_terms):
            matched = _normalize_term(issue.get('matched_text'))
            if matched and matched in grounding_map:
                info = grounding_map[matched]
                suppressed_issues.append({
                    'matched_text': issue.get('matched_text'),
                    'type': issue.get('type'),
                    'rule_id': issue.get('rule_id'),
                    'offset': offset,
                    'length': length,
                    'grounding_source': info.get('source'),
                    'grounding_record': info.get('record'),
                    'grounding_classification': info.get('classification'),
                    'grounding_reason': info.get('reason'),
                    'match_kind': 'TOKEN GROUNDED',
                    'message': issue.get('message'),
                })
            elif matched in DEFAULT_IGNORE_TERMS:
                suppressed_issues.append({
                    'matched_text': issue.get('matched_text'),
                    'type': issue.get('type'),
                    'rule_id': issue.get('rule_id'),
                    'offset': offset,
                    'length': length,
                    'grounding_source': 'COMET_STANDARD_ADMIN_VOCABULARY',
                    'grounding_record': 'system_default',
                    'grounding_classification': 'COMET-STRUCTURED',
                    'grounding_reason': 'standard_administrative_term',
                    'match_kind': 'TOKEN GROUNDED',
                    'message': issue.get('message'),
                })
            else:
                suppressed_issues.append({
                    'matched_text': issue.get('matched_text'),
                    'type': issue.get('type'),
                    'rule_id': issue.get('rule_id'),
                    'offset': offset,
                    'length': length,
                    'grounding_source': 'PROJECT_CODE_PATTERN',
                    'grounding_record': 'pattern_match',
                    'grounding_classification': 'COMET-OPERATIONAL',
                    'grounding_reason': 'project_code_format',
                    'match_kind': 'TOKEN GROUNDED',
                    'message': issue.get('message'),
                })
            continue

        issues.append(issue)
    return issues if max_issues is None else issues[:max_issues], suppressed_issues


def _issue_from_match(match, text):
    try:
        offset = int(match.get('offset'))
        length = int(match.get('length'))
    except (TypeError, ValueError):
        return None
    if offset < 0 or length <= 0:
        return None
    matched_text = text[offset:offset + length].strip()
    if not matched_text:
        return None

    rule = match.get('rule') if isinstance(match.get('rule'), dict) else {}
    rule_id = str(rule.get('id') or '').strip()
    replacements = match.get('replacements') if isinstance(match.get('replacements'), list) else []
    replacement = ''
    if replacements and isinstance(replacements[0], dict):
        replacement = str(replacements[0].get('value') or '').strip()
    category = rule.get('category') if isinstance(rule.get('category'), dict) else {}

    if _is_extraction_artifact(matched_text, rule_id):
        issue_type = 'extraction_artifact'
    else:
        issue_type = _issue_type(match, rule, category)

    return {
        'type': issue_type,
        'matched_text': matched_text,
        'suggestion': replacement,
        'message': str(match.get('message') or 'LanguageTool detected a language issue.').strip(),
        'offset': offset,
        'length': length,
        'rule_id': rule_id,
        'category': str(category.get('name') or category.get('id') or '').strip(),
        'source': 'languagetool',
    }


def _issue_type(match, rule, category):
    haystack = ' '.join(
        str(value or '').lower()
        for value in (
            match.get('message'),
            rule.get('id'),
            rule.get('issueType'),
            category.get('id'),
            category.get('name'),
        )
    )
    if any(token in haystack for token in ('misspell', 'typo', 'morfologik')):
        return 'spelling'
    if 'grammar' in haystack:
        return 'grammar'
    return 'style'


def _should_ignore_issue(issue, ignore_terms):
    rule_id = str(issue.get('rule_id') or '').strip()
    # Class A: Genuine duplicate-word / phrase repetitions must NEVER be ignored
    if _is_repetition_rule(rule_id):
        return False

    raw_matched = str(issue.get('matched_text') or '').strip()
    matched = _normalize_term(issue.get('matched_text'))
    if not matched:
        return False

    if matched in ignore_terms:
        return True

    # Compound hyphenated term matching (e.g. LGSF-FALGU, RBME-RLIP, Victoria-Pila)
    if '-' in raw_matched:
        parts = [p for p in raw_matched.split('-') if p.strip()]
        if parts and all(_normalize_term(p) in ignore_terms for p in parts):
            return True

    return bool(
        raw_matched.upper() == raw_matched
        and any(char.isdigit() for char in raw_matched)
        and _resembles_project_or_reference_code(raw_matched)
    )


def _resembles_project_or_reference_code(value):
    compact = str(value or '').strip()
    return bool('-' in compact or '/' in compact or any(char.isalpha() for char in compact))


def _ignore_terms(config):
    configured = _config_value(config, 'DOCUMENT_LANGUAGE_TOOL_IGNORE_TERMS', '')
    grounding_map = config.get('GROUNDING_TERMS_MAP') or {} if isinstance(config, dict) else {}
    terms = set(DEFAULT_IGNORE_TERMS) - FORBIDDEN_GLOBAL_IGNORE_TERMS
    if configured:
        for item in str(configured).split(','):
            norm = _normalize_term(item)
            if not norm or norm in FORBIDDEN_GLOBAL_IGNORE_TERMS:
                continue
            if norm in CONTEXT_DEPENDENT_ACRONYMS and norm not in grounding_map:
                continue
            terms.add(norm)
    return terms


def _detected_language(payload):
    language = payload.get('language') if isinstance(payload, dict) else {}
    if not isinstance(language, dict):
        return None
    detected = language.get('detectedLanguage')
    if not isinstance(detected, dict):
        return None
    code = str(detected.get('code') or '').strip()
    if not code:
        return None
    return {
        'code': code,
        'confidence': detected.get('confidence'),
    }


def _safe_url_label(url):
    raw = str(url or '').strip()
    if not raw:
        return ''
    return raw.split('?', 1)[0]


def _normalize_term(value):
    decomposed = unicodedata.normalize('NFKD', str(value or ''))
    without_marks = ''.join(char for char in decomposed if not unicodedata.combining(char))
    return ''.join(char.lower() for char in without_marks if char.isalnum())


def _config_value(config, key, default=None):
    if hasattr(config, 'get'):
        value = config.get(key)
        return default if value in (None, '') else value
    return default


def _config_bool(config, key, *, default=False):
    value = _config_value(config, key, None)
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _config_int(config, key, default):
    return int(_safe_float(_config_value(config, key, default), default))


def _config_float(config, key, default):
    return _safe_float(_config_value(config, key, default), default)


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
