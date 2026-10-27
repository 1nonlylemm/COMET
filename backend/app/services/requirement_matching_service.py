import re
from functools import lru_cache

from app.models import ProgramPhase, Project, ProjectRequirement, Requirement
from app.services.import_field_catalog import normalize_label


IGNORED_PHASE_NAMES = {'imported requirements'}
MATCH_THRESHOLD = 0.72
EXACT_MATCH_THRESHOLD = 0.95
TOKEN_STOPWORDS = {
    'a',
    'an',
    'and',
    'as',
    'fa',
    'fas',
    'for',
    'in',
    'lgu',
    'lgus',
    'of',
    'on',
    'or',
    'project',
    'projects',
    'the',
    'to',
    'with',
}
TITLE_SMALL_WORDS = {
    'a',
    'an',
    'and',
    'as',
    'at',
    'but',
    'by',
    'for',
    'from',
    'in',
    'nor',
    'of',
    'on',
    'or',
    'per',
    'the',
    'to',
    'upon',
    'with',
}
ACRONYM_TOKENS = {
    'ABC',
    'AC',
    'AIP',
    'APMV',
    'BTR',
    'COA',
    'CSO',
    'DBM',
    'DED',
    'DILG',
    'DPWH',
    'DRR',
    'DRRAP',
    'DRSL',
    'FA',
    'FALGU',
    'G3P',
    'GGG',
    'GEF',
    'IP',
    'ISF',
    'ITB',
    'LBC',
    'LCE',
    'LDDAP',
    'LDIP',
    'LFC',
    'LGU',
    'LGUS',
    'LGSF',
    'MGB',
    'MT',
    'NADAI',
    'NCA',
    'NNC',
    'NOA',
    'NTP',
    'ODF',
    'PCR',
    'PBBM',
    'PDIP',
    'PDMU',
    'POW',
    'QAAR',
    'RA',
    'RBME',
    'RO',
    'RLIP',
    'RROW',
    'RSSA',
    'SAFPB',
    'SARO',
    'SBDP',
    'SB',
    'SBR',
    'SGLG',
    'SGLGIF',
    'SORD',
    'SWA',
    'WASH',
}
SPECIAL_TITLE_TOKENS = {
    'lgus': 'LGUs',
}


class RequirementMatchContext:
    def __init__(self, program_id):
        self.program_id = program_id
        self._requirements = None
        self._project_requirements = None

    @property
    def requirements(self):
        if self._requirements is None:
            self._requirements = (
                Requirement.query
                .join(ProgramPhase, Requirement.phase_id == ProgramPhase.id)
                .filter(ProgramPhase.program_id == self.program_id)
                .all()
            )
        return self._requirements

    @property
    def project_requirements(self):
        if self._project_requirements is None:
            self._project_requirements = (
                ProjectRequirement.query
                .join(Project, ProjectRequirement.project_id == Project.id)
                .filter(Project.program_id == self.program_id)
                .all()
            )
        return self._project_requirements


def find_requirement_match(program_id, imported_name, annex_reference=None, match_context=None):
    matches = find_requirement_candidates(
        program_id,
        imported_name,
        annex_reference=annex_reference,
        include_project_snapshots=True,
        min_score=MATCH_THRESHOLD,
        match_context=match_context,
    )
    matches = [item for item in matches if item.get('requirement')]
    if not matches:
        return None

    best = matches[0]
    if len(matches) > 1 and best['score'] - matches[1]['score'] < 0.05:
        if best['score'] >= 0.97 and best['score'] > matches[1]['score']:
            return best['requirement']
        return None
    return best['requirement']


def find_requirement_candidates(program_id, imported_name, annex_reference=None,
                                include_project_snapshots=True, exclude_requirement_id=None,
                                min_score=MATCH_THRESHOLD, match_context=None):
    imported_normalized = _normalized(imported_name)
    annex_normalized = _normalized(annex_reference)
    if not imported_normalized and not annex_normalized:
        return []

    candidates_by_key = {}
    requirements = (
        match_context.requirements
        if match_context is not None and match_context.program_id == program_id
        else (
            Requirement.query
            .join(ProgramPhase, Requirement.phase_id == ProgramPhase.id)
            .filter(ProgramPhase.program_id == program_id)
            .all()
        )
    )
    for requirement in requirements:
        if exclude_requirement_id and requirement.id == exclude_requirement_id:
            continue
        if _normalized(requirement.phase.name) in IGNORED_PHASE_NAMES:
            continue
        score = _requirement_match_score(imported_normalized, requirement, annex_normalized)
        _add_candidate(candidates_by_key, _candidate_from_requirement(requirement, score, 'requirement'), min_score)

    if include_project_snapshots:
        project_requirements = (
            match_context.project_requirements
            if match_context is not None and match_context.program_id == program_id
            else (
                ProjectRequirement.query
                .join(Project, ProjectRequirement.project_id == Project.id)
                .filter(Project.program_id == program_id)
                .all()
            )
        )
        for project_requirement in project_requirements:
            requirement = project_requirement.requirement
            if requirement and exclude_requirement_id and requirement.id == exclude_requirement_id:
                continue
            score = _project_requirement_match_score(imported_normalized, annex_normalized, project_requirement)
            candidate = _candidate_from_project_requirement(project_requirement, score)
            _add_candidate(candidates_by_key, candidate, min_score)

    return sorted(
        candidates_by_key.values(),
        key=lambda item: (
            item['score'],
            1 if item.get('requirement') else 0,
            -(item.get('sort_order') or 0),
        ),
        reverse=True,
    )


def standardize_requirement_name(value):
    text = re.sub(r'\s+', ' ', str(value or '').replace('_', ' ')).strip()
    if not text:
        return ''

    tokens = re.findall(r'[A-Za-z0-9]+|[^A-Za-z0-9\s]+|\s+', text)
    word_index = 0
    word_count = sum(1 for token in tokens if re.match(r'[A-Za-z0-9]+$', token))
    result = []
    for token in tokens:
        if not re.match(r'[A-Za-z0-9]+$', token):
            result.append(token)
            continue
        normalized = token.lower()
        upper = token.upper()
        if normalized in SPECIAL_TITLE_TOKENS:
            result.append(SPECIAL_TITLE_TOKENS[normalized])
        elif upper in ACRONYM_TOKENS:
            result.append('LGUs' if upper == 'LGUS' else upper)
        elif 0 < word_index < word_count - 1 and normalized in TITLE_SMALL_WORDS:
            result.append(normalized)
        else:
            result.append(normalized.capitalize())
        word_index += 1
    return ''.join(result).strip()


def standardize_annex_reference(value):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return None
    normalized = normalize_label(text)
    annex_match = re.fullmatch(r'annex\s+([a-z0-9]+)', normalized)
    if annex_match:
        return f'Annex {annex_match.group(1).upper()}'
    upper = text.upper()
    if upper in ACRONYM_TOKENS:
        return 'LGUs' if upper == 'LGUS' else upper
    return standardize_requirement_name(text)


def _add_candidate(candidates_by_key, candidate, min_score):
    if not candidate or candidate['score'] < min_score:
        return
    key = (
        f"requirement:{candidate['requirement'].id}"
        if candidate.get('requirement')
        else f"project_requirement:{candidate['project_requirement'].id}"
    )
    existing = candidates_by_key.get(key)
    if not existing or candidate['score'] > existing['score']:
        candidates_by_key[key] = candidate


def _candidate_from_requirement(requirement, score, matched_on):
    return {
        'score': score,
        'match_type': _match_type(score),
        'matched_on': matched_on,
        'requirement': requirement,
        'project_requirement': None,
        'id': requirement.id,
        'name': requirement.name,
        'phase_name': requirement.phase.name if requirement.phase else None,
        'annex_reference': requirement.annex_reference,
        'sort_order': requirement.sort_order,
    }


def _candidate_from_project_requirement(project_requirement, score):
    requirement = project_requirement.requirement
    return {
        'score': score,
        'match_type': _match_type(score),
        'matched_on': 'project_requirement',
        'requirement': requirement if requirement and _normalized(requirement.phase.name) not in IGNORED_PHASE_NAMES else None,
        'project_requirement': project_requirement,
        'id': requirement.id if requirement else project_requirement.id,
        'name': requirement.name if requirement and _normalized(requirement.phase.name) not in IGNORED_PHASE_NAMES else project_requirement.requirement_name,
        'phase_name': (
            requirement.phase.name
            if requirement and _normalized(requirement.phase.name) not in IGNORED_PHASE_NAMES
            else project_requirement.phase_name
        ),
        'annex_reference': project_requirement.annex_reference,
        'sort_order': project_requirement.sort_order,
    }


def _match_type(score):
    return 'exact' if score >= EXACT_MATCH_THRESHOLD else 'similar'


def _requirement_match_score(imported_normalized, requirement, imported_annex_normalized=''):
    requirement_name = _normalized(requirement.name)
    annex_reference = _normalized(requirement.annex_reference)
    score = _label_match_score(imported_normalized, requirement_name, annex_reference)
    if imported_annex_normalized and annex_reference and imported_annex_normalized == annex_reference:
        score = max(score, 0.94)
    return score


def _project_requirement_match_score(imported_normalized, imported_annex_normalized, project_requirement):
    labels = [
        project_requirement.requirement_name,
        project_requirement.annex_reference,
    ]
    custom_fields = project_requirement.custom_fields or {}
    labels.extend([
        custom_fields.get('imported_requirement_name'),
        custom_fields.get('source_requirement_name'),
    ])
    score = max(
        _label_match_score(imported_normalized, _normalized(label), _normalized(project_requirement.annex_reference))
        for label in labels
        if label
    ) if any(labels) else 0
    if imported_annex_normalized and _normalized(project_requirement.annex_reference) == imported_annex_normalized:
        score = max(score, 0.94)
    return score


@lru_cache(maxsize=32768)
def _label_match_score(imported_normalized, requirement_name, annex_reference=''):
    imported_tokens = _tokens(imported_normalized)
    name_tokens = _tokens(requirement_name)
    annex_tokens = _tokens(annex_reference)
    scores = []

    if imported_normalized == requirement_name:
        scores.append(1.0)
    if annex_reference and imported_normalized == annex_reference:
        scores.append(0.97)
    name_acronym = _acronym(requirement_name)
    annex_acronym = _acronym(annex_reference)
    name_full_acronym = _acronym_all_words(requirement_name)
    annex_full_acronym = _acronym_all_words(annex_reference)
    acronyms = {
        acronym
        for acronym in {name_acronym, annex_acronym, name_full_acronym, annex_full_acronym}
        if len(acronym) >= 2
    }
    if imported_tokens and imported_normalized in acronyms:
        scores.append(0.96)
    if len(name_acronym) >= 2 and name_acronym in imported_tokens:
        scores.append(0.9)
    if len(annex_acronym) >= 2 and annex_acronym in imported_tokens:
        scores.append(0.9)
    if annex_tokens and _is_subset(annex_tokens, imported_tokens):
        scores.append(0.75)
    if imported_tokens and _is_subset(imported_tokens, annex_tokens):
        scores.append(0.92)
    if imported_tokens and name_tokens:
        intersection = imported_tokens & name_tokens
        overlap = len(intersection) / max(1, min(len(imported_tokens), len(name_tokens)))
        if len(intersection) >= 2 and overlap >= 0.8:
            scores.append(0.88)
        elif len(intersection) >= 2 and overlap >= 0.6:
            scores.append(0.8)
        elif len(imported_tokens) == 1 and imported_tokens <= name_tokens and len(next(iter(imported_tokens))) >= 3:
            scores.append(0.82)
    if imported_normalized and requirement_name:
        if len(imported_normalized) >= 4 and imported_normalized in requirement_name:
            scores.append(0.82)
        if len(requirement_name) >= 4 and requirement_name in imported_normalized:
            scores.append(0.84)

    return max(scores or [0])


def _tokens(value):
    return set(_ordered_tokens(value))


@lru_cache(maxsize=32768)
def _ordered_tokens(value):
    tokens = set()
    ordered = []
    for token in _normalized(value).split():
        if token in TOKEN_STOPWORDS:
            continue
        normalized = token[:-1] if len(token) > 3 and token.endswith('s') else token
        if normalized in tokens:
            continue
        tokens.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


@lru_cache(maxsize=32768)
def _acronym(value):
    return ''.join(token[0] for token in _ordered_tokens(value) if token)


@lru_cache(maxsize=32768)
def _acronym_all_words(value):
    return ''.join(token[0] for token in _normalized(value).split() if token)


def _is_subset(left, right):
    return bool(left) and left <= right


@lru_cache(maxsize=32768)
def _cached_normalize_label(value):
    return normalize_label(value)


def _normalized(value):
    if value is None:
        return ''
    return _cached_normalize_label(str(value))
