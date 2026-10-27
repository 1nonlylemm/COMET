import re
from dataclasses import dataclass

from app.services.import_field_catalog import normalize_label


STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'by', 'for', 'from', 'in', 'into',
    'is', 'it', 'near', 'of', 'on', 'or', 'please', 'show', 'the', 'to',
    'with',
}

SYNONYMS = {
    'bldg': {'building'},
    'brgy': {'barangay'},
    'budget': {'allocation', 'amount', 'cost'},
    'complete': {'completed', 'completion'},
    'complied': {'compliant'},
    'doc': {'document', 'documentary'},
    'docs': {'document', 'documents', 'documentary'},
    'fy': {'fiscal', 'year'},
    'lgus': {'lgu'},
    'municipal': {'municipality'},
    'mun': {'municipality'},
    'pending': {'open'},
    'preimplementation': {'pre', 'implementation', 'pre_implementation'},
    'requirements': {'requirement'},
    'road': {'rd'},
    'roads': {'road'},
    'st': {'street'},
}

PHASE_ALIASES = {
    'pre': 'pre_implementation',
    'preimplementation': 'pre_implementation',
    'pre_implementation': 'pre_implementation',
    'implementation': 'implementation',
    'implementing': 'implementation',
    'completion': 'completion',
    'completed': 'completion',
    'closeout': 'completion',
}

STATUS_ALIASES = {
    'active': 'ongoing',
    'completed': 'completed',
    'complete': 'completed',
    'ongoing': 'ongoing',
    'on-going': 'ongoing',
    'notstarted': 'not_yet_started',
    'not_started': 'not_yet_started',
    'notyetstarted': 'not_yet_started',
    'cancelled': 'cancelled',
    'canceled': 'cancelled',
    'suspended': 'cancelled',
    'terminated': 'cancelled',
    'pending': 'pending',
    'review': 'under_review',
    'underreview': 'under_review',
    'under_review': 'under_review',
    'compliant': 'compliant',
    'complied': 'compliant',
    'noncompliant': 'non_compliant',
    'non_compliant': 'non_compliant',
    'waived': 'waived',
}


@dataclass(frozen=True)
class ParsedSearchQuery:
    raw: str
    normalized: str
    tokens: tuple[str, ...]
    sql_tokens: tuple[str, ...]
    status_terms: tuple[str, ...]
    phase_terms: tuple[str, ...]
    fiscal_years: tuple[int, ...]

    @property
    def is_empty(self):
        return not self.tokens and not self.status_terms and not self.phase_terms and not self.fiscal_years


def parse_search_query(value):
    raw = str(value or '').strip()
    normalized = normalize_text(raw)
    words = [item for item in normalized.split() if item and item not in STOPWORDS]

    tokens = []
    for word in words:
        if len(word) == 1 and not word.isdigit():
            continue
        tokens.append(word)

    status_terms = []
    phase_terms = []
    fiscal_years = []
    for token in tokens:
        compact = token.replace('_', '')
        status = STATUS_ALIASES.get(token) or STATUS_ALIASES.get(compact)
        if status and status not in status_terms:
            status_terms.append(status)
        phase = PHASE_ALIASES.get(token) or PHASE_ALIASES.get(compact)
        if phase and phase not in phase_terms:
            phase_terms.append(phase)
        if re.fullmatch(r'(?:19|20)\d{2}', token):
            year = int(token)
            if year not in fiscal_years:
                fiscal_years.append(year)

    expanded = []
    for token in tokens:
        for candidate in expand_token(token):
            if len(candidate) >= 2 and candidate not in expanded:
                expanded.append(candidate)

    return ParsedSearchQuery(
        raw=raw,
        normalized=normalized,
        tokens=tuple(tokens),
        sql_tokens=tuple(expanded[:20]),
        status_terms=tuple(status_terms),
        phase_terms=tuple(phase_terms),
        fiscal_years=tuple(fiscal_years),
    )


def normalize_text(value):
    return normalize_label(value)


def project_code_query(parsed):
    """Keep structured identifiers whole without assuming their record type."""
    value = parsed.raw.strip(' "\'')
    if re.fullmatch(r'[a-zA-Z0-9]+(?:[-_/][a-zA-Z0-9]+){2,}', value) and any(c.isdigit() for c in value):
        return value.casefold()
    return None


def expand_token(token):
    token = normalize_text(token)
    if not token:
        return set()
    variants = {token}
    variants.update(SYNONYMS.get(token, set()))
    for source, targets in SYNONYMS.items():
        if token in targets:
            variants.add(source)
    return variants


def flatten_values(value):
    if value is None:
        return []
    if isinstance(value, dict):
        flattened = []
        for key, item in value.items():
            flattened.extend(flatten_values(key))
            flattened.extend(flatten_values(item))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for item in value:
            flattened.extend(flatten_values(item))
        return flattened
    return [str(value)]
