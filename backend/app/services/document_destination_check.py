"""Compare explicit document identity with the destination, independently of ranking."""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone

DESTINATION_CHECKER_VERSION = '2026.10.22'


def _normal(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', str(value or ''))
                    if not unicodedata.combining(c)).lower()
    value = re.sub(r'\bsta\.?\s+', 'santa ', value)
    value = re.sub(r'\bsto\.?\s+', 'santo ', value)
    value = re.sub(r'\bbrgy\.?\s+', 'barangay ', value)
    return ' '.join(re.findall(r'\w+', value))


def _lgu(value):
    val = _normal(value)
    val = re.sub(r'^(?:the\s+)?(?:local\s+government\s+unit|lgu)\s+(?:of\s+)?', '', val)
    val = re.sub(r'^(?:city\s+government|municipal\s+government|provincial\s+government)\s+(?:of\s+)?', '', val)
    val = re.sub(r'^(?:municipality|city|province)\s+(?:of\s+)?', '', val)
    val = re.sub(r'\s+(?:city\s+government|municipal\s+government|provincial\s+government)$', '', val)
    val = re.sub(r'\s+(?:city|municipality|province|lgu)$', '', val)
    val = re.sub(r'\b(?:city|municipality|municipal|provincial|government|lgu|of|the)\b', '', val)
    return ' '.join(re.findall(r'\w+', val))


def _same(observed, expected, normal=_normal):
    a, b = normal(observed), normal(expected)
    # Similar town names, project codes and titles with different barangays must
    # never pass merely because most characters coincide.
    return bool(a and b and a == b)


_DISPLAY_MARKER_TOKENS = frozenset({'testing', 'test', 'demo', 'qa', 'sample', 'staging', 'dev'})
_DISPLAY_MARKER_PATTERN = re.compile(
    r'^\s*(?:\[|\()(' + '|'.join(_DISPLAY_MARKER_TOKENS) + r')(?:\]|\))\s*[-:]?\s*|\s*[-:]?\s*(?:\[|\()(' + '|'.join(_DISPLAY_MARKER_TOKENS) + r')(?:\]|\))\s*$',
    re.I
)


def strip_display_markers(text):
    """Strip explicit test/demo/staging markers without stripping substantive brackets or barangays."""
    if not text:
        return ''
    s = str(text).strip()
    changed = True
    while changed:
        new_s = _DISPLAY_MARKER_PATTERN.sub('', s).strip()
        changed = (new_s != s)
        s = new_s
    return s


def canonical_project_titles(project):
    """Resolve approved canonical titles and aliases for a project.

    Conservative policy:
    - Never globally strips arbitrary brackets (e.g. preserves [Phase 1], [Brgy. San Antonio]).
    - Strips whitelisted test/demo environment markers only.
    - Preserves approved aliases if configured on the project.
    - Returns a deterministically sorted list of unique title variants.
    """
    raw_name = getattr(project, 'project_name', None) or ''
    titles = set()
    if raw_name:
        titles.add(raw_name)
        clean = strip_display_markers(raw_name)
        if clean:
            titles.add(clean)

    canonical = getattr(project, 'canonical_title', None)
    if canonical:
        titles.add(canonical)
        clean_c = strip_display_markers(canonical)
        if clean_c:
            titles.add(clean_c)

    custom_fields = getattr(project, 'custom_fields', None) or {}
    if isinstance(custom_fields, dict):
        cf_canonical = custom_fields.get('canonical_title')
        if cf_canonical:
            titles.add(cf_canonical)
            clean_cf = strip_display_markers(cf_canonical)
            if clean_cf:
                titles.add(clean_cf)
        approved = custom_fields.get('approved_aliases') or custom_fields.get('aliases') or []
        if isinstance(approved, list):
            for alias in approved:
                if alias:
                    titles.add(str(alias))
                    clean_a = strip_display_markers(str(alias))
                    if clean_a:
                        titles.add(clean_a)

    return sorted(set(str(t).strip() for t in titles if t and str(t).strip()))


# Public Laguna municipalities are a fallback for standalone inspection/tests.
# In the application the registry comes from LguProfile, including its aliases.
_LAGUNA_NAMES = (
    'Alaminos', 'Bay', 'Biñan', 'Cabuyao', 'Calamba', 'Calauan', 'Cavinti',
    'Famy', 'Kalayaan', 'Liliw', 'Los Baños', 'Luisiana', 'Lumban', 'Mabitac',
    'Magdalena', 'Majayjay', 'Nagcarlan', 'Paete', 'Pagsanjan', 'Pakil',
    'Pangil', 'Pila', 'Rizal', 'San Pablo', 'San Pedro', 'Santa Cruz',
    'Santa Rosa', 'Santa Maria', 'Siniloan', 'Victoria',
)
_LGU_LABEL = re.compile(
    r'^\s*(?:(?:implementing|recipient|beneficiary)\s+)?'
    r'(?:(?:lgu(?:\s+name)?|local government unit)(?:\s*[:|]\s*(.*)|\t+\s*(.*)|\s{2,}(.*)|\s+(?=(?:municipality|city|province|municipal\s+government|city\s+government|provincial\s+government)\s+of\b|[A-Z])(.*)|$)|'
    r'(?:city\s*/\s*municipality)(?:\s*[:|]\s*(.*)|\t+\s*(.*)|\s{2,}(.*)|\s+(?=[A-Z])(.*)|$)|'
    r'(?:municipality|city|province)(?:\s*[:|]\s*(.*)|\t+\s*(.*)|\s{2,}(.*)|$))',
    re.I
)
_OFFICIAL_LGU = re.compile(
    r'^\s*(?:(?:municipality|city|province|municipal\s+government|'
    r'city\s+government|provincial\s+government)\s+of\s+)(.+)$', re.I)
_OTHER_LABEL = re.compile(
    r'^\s*(?:project\s+(?:name|title|description)|name\s+of\s+project|'
    r'project|(?:source\s+)?project\s+(?:code|id|number|no\.?)|'
    r'document\s+type|documentary\s+requirement|requirement(?:\s+(?:name|type))?)'
    r'(?:\s*[:|]|\t|\s{2,}|$)', re.I)


def lgu_expected_variants(value):
    """Use the same accent/prefix/suffix normalizer as destination comparison."""
    base = _lgu(value)
    if not base:
        return []
    return list(dict.fromkeys([str(value).strip(), base, f'City of {base}',
                              f'{base} City', f'Municipality of {base}',
                              f'{base} Municipality', f'{base} Laguna']))


def _known_lgus():
    fallback = {_lgu(name): _lgu(name) for name in _LAGUNA_NAMES}
    from flask import current_app, has_app_context
    if not has_app_context():
        return fallback
    from app.models import LguProfile
    from sqlalchemy.exc import SQLAlchemyError
    try:
        profiles = LguProfile.query.all()
    except SQLAlchemyError:
        # A failed registry lookup cannot justify a contradictory destination.
        return {}
    registry = dict(fallback) if current_app.config.get('TESTING') else {}
    by_id = {profile.id: profile for profile in profiles}
    for profile in profiles:
        if profile.id == 31 or 'provincial' in _normal(profile.name):
            continue
        canonical_profile = by_id.get(11, profile) if profile.id == 32 else profile
        canonical = _lgu(canonical_profile.municipality or canonical_profile.name)
        for name in (profile.name, profile.municipality):
            if name:
                registry[_lgu(name)] = canonical
    return registry


def is_label(line):
    """Loose phrases ending in City/Municipality are not field labels."""
    return bool(re.match(r'^\s*[\w /().-]{1,60}\s*[:|]', line)
                or _OTHER_LABEL.match(line) or _LGU_LABEL.match(line)
                or _OFFICIAL_LGU.match(line))


def _inspect_lgu(text, lgu_obj):
    expected = getattr(lgu_obj, 'municipality', None) or getattr(lgu_obj, 'name', None)
    base = {'field': 'lgu', 'expected': expected, 'observed': [], 'conflicts': []}
    if not expected or getattr(lgu_obj, 'id', None) == 31 or 'provincial' in _normal(expected):
        return {**base, 'status': 'not_applicable', 'reason': 'No municipal/city destination applies.'}
    registry = _known_lgus()
    province = _lgu(getattr(lgu_obj, 'province', None))

    def canonical(value):
        name = _lgu(value)
        if province and name.endswith(' ' + province):
            name = name[:-(len(province) + 1)]
        return registry.get(name)

    expected_key = canonical(expected)
    values = []
    for page, content in enumerate(text.split('\f'), 1):
        lines = content.splitlines()
        for index, line in enumerate(lines):
            label = _LGU_LABEL.match(line)
            official = _OFFICIAL_LGU.match(line)
            value = None
            if label:
                matched_groups = [v for v in label.groups() if v is not None]
                value = matched_groups[0].strip() if matched_groups else ''
                following = index + 1
                while following < len(lines) and lines[following].strip() in (':', '|', '-', '='):
                    following += 1
                if not value and following < len(lines) and not is_label(lines[following]):
                    value = lines[following].strip()
            elif official:
                value = line.strip()
            elif (index < 10 or re.match(r'^\s*(?:to|subject|re)\s*:', line, re.I)):
                # Only header/addressee/subject positions, never supplier or
                # project-title fields. Match registered names on token edges.
                if re.match(r'^\s*(?:project\s+(?:name|title|description)|prepared by|supplier|contractor|address)\s*:', line, re.I):
                    continue
                addressed = bool(re.match(r'^\s*(?:to|subject|re)\s*:', line, re.I))
                if not addressed and (':' in line or line.rstrip().endswith('.') or
                    re.match(r'^\s*(?:this|it|year\s+\d|in\s+|the\s+(?!city\b|municipality\b))', line, re.I)):
                    continue
                normalized = _normal(line)
                candidates = [key for key in registry if re.search(r'(?<!\w)' + re.escape(key) + r'(?!\w)', normalized)]
                for key in candidates:
                    values.append({'text': line.strip(), 'page': page if '\f' in text else None,
                                   'canonical': registry[key]})
            if value:
                value = value.split('|')[0].split('\t')[0].split(',')[0].strip()
                values.append({'text': value, 'page': page if '\f' in text else None,
                               'canonical': canonical(value)})
    known = [v for v in values if v['canonical']]
    observed = [{k: v[k] for k in ('text', 'page')} for v in values]
    if expected_key and any(v['canonical'] == expected_key for v in known):
        status, reason, conflicts = 'matches', 'The expected LGU is named in a destination position.', []
    elif expected_key and known:
        status, reason = 'mismatch', 'A different registered LGU is named; the expected LGU is absent from destination positions.'
        conflicts = [{k: v[k] for k in ('text', 'page')} for v in known]
    else:
        status, reason, conflicts = 'unverified', 'No registered municipal/city destination could be verified.', []
        unknown = next((v['text'] for v in values if not v['canonical']
                        and _lgu(v['text']) != province), None)
        if unknown:
            reason = f"Document names '{unknown}', which is not a registered Laguna LGU; verify manually."
    return {**base, 'observed': observed, 'status': status, 'reason': reason, 'conflicts': conflicts}


_PROSE_PREFIXES = r'(?:is|was|are|shall|will|must|should|can|may|has|have|had|of|to|for|in|on|by|with|and|or|be|not|a|the|as|from|assigned)\b'


def destination_context_payload(project, requirement=None, file_name=None, extracted_text=None):
    lgu_obj = getattr(project, 'lgu', None)
    expected_lgu = getattr(lgu_obj, 'municipality', None) or getattr(lgu_obj, 'name', None)
    expected_province = getattr(lgu_obj, 'province', None)
    expected_title = getattr(project, 'project_name', None)
    expected_code = getattr(project, 'source_project_code', None)
    expected_req = getattr(requirement, 'requirement_name', None)
    aliases = canonical_project_titles(project)

    text_hash = hashlib.sha256(extracted_text.encode('utf-8', errors='ignore')).hexdigest()[:16] if extracted_text else None

    return {
        'checker_version': DESTINATION_CHECKER_VERSION,
        'lgu': expected_lgu,
        'province': expected_province,
        'project_title': expected_title,
        'project_code': expected_code,
        'requirement': expected_req,
        'approved_titles': aliases,
        'file_name': file_name,
        'text_hash': text_hash,
    }


def context_fingerprint(context_dict):
    canonical_repr = json.dumps(context_dict, sort_keys=True, default=str)
    return hashlib.sha256(canonical_repr.encode('utf-8')).hexdigest()[:16]


def is_destination_check_stale(destination_check, project, requirement=None, file_name=None, extracted_text=None):
    """Determine whether a saved destination check was performed against outdated context or earlier parser."""
    if not destination_check or not isinstance(destination_check, dict):
        return True, ['No destination check recorded.']

    stale_reasons = []
    checker_version = destination_check.get('checker_version')
    if not checker_version or checker_version != DESTINATION_CHECKER_VERSION:
        stale_reasons.append(
            f"Checker version {checker_version or 'legacy'} differs from current {DESTINATION_CHECKER_VERSION}."
        )

    lgu_obj = getattr(project, 'lgu', None)
    current_expected = {
        'lgu': getattr(lgu_obj, 'municipality', None) or getattr(lgu_obj, 'name', None),
        'project_title': getattr(project, 'project_name', None),
        'project_code': getattr(project, 'source_project_code', None),
        'requirement': getattr(requirement, 'requirement_name', None),
    }

    checks = destination_check.get('checks', [])
    for field in ('lgu', 'project_title', 'project_code', 'requirement'):
        saved_exp = next((c.get('expected') for c in checks if c.get('field') == field), None)
        curr_exp = current_expected.get(field)
        norm_fn = _lgu if field == 'lgu' else _normal
        saved_norm = norm_fn(saved_exp) if saved_exp else ''
        curr_norm = norm_fn(curr_exp) if curr_exp else ''
        if saved_norm != curr_norm:
            if not saved_norm and curr_norm:
                stale_reasons.append(f"Expected {field} was newly set to '{curr_exp}'.")
            elif saved_norm and not curr_norm:
                stale_reasons.append(f"Expected {field} '{saved_exp}' was removed.")
            else:
                stale_reasons.append(f"Expected {field} changed from '{saved_exp}' to '{curr_exp}'.")

    # Check approved titles (aliases)
    curr_aliases = canonical_project_titles(project)
    saved_payload = destination_check.get('context_payload') or {}
    saved_aliases = saved_payload.get('approved_titles')
    if saved_aliases is not None:
        saved_aliases_sorted = sorted(set(str(a).strip() for a in saved_aliases if a and str(a).strip()))
        if saved_aliases_sorted != curr_aliases:
            stale_reasons.append("Approved project title aliases or canonical titles changed.")

    # Check file identity if provided
    saved_file = saved_payload.get('file_name')
    if file_name and saved_file and file_name != saved_file:
        stale_reasons.append(f"Document file name changed from '{saved_file}' to '{file_name}'.")

    # Check fingerprint
    if destination_check.get('context_fingerprint'):
        effective_file = file_name if saved_payload.get('file_name') is not None else None
        curr_context = destination_context_payload(project, requirement, effective_file, extracted_text)
        if extracted_text is None and saved_payload.get('text_hash'):
            curr_context['text_hash'] = saved_payload.get('text_hash')
        curr_fp = context_fingerprint(curr_context)
        if curr_fp != destination_check.get('context_fingerprint') and not stale_reasons:
            stale_reasons.append("Destination context fingerprint mismatch.")

    return bool(stale_reasons), stale_reasons


def inspect_destination(text, project, requirement=None, file_name=None):
    """Missing identity stays unverified. Only explicit contradictory fields flag a mismatch.

    Free mentions of towns, contractors, signatories or filenames are not identity fields.
    Page numbers are retained only when extraction supplied real form-feed boundaries.
    """
    text = str(text or '')
    lgu_obj = getattr(project, 'lgu', None)
    expected = {
        'lgu': getattr(lgu_obj, 'municipality', None) or getattr(lgu_obj, 'name', None),
        'project_title': getattr(project, 'project_name', None),
        'project_code': getattr(project, 'source_project_code', None),
        'requirement': getattr(requirement, 'requirement_name', None),
    }
    patterns = {
        'lgu': None,  # Registry-backed destination inspection below.
        'project_title': (
            r'^\s*(?:project\s+(?:name|title|description)|name\s+of\s+project)'
            r'(?:'
            r'\s*[:|]\s*(.*)|'
            r'\t+\s*(.*)|'
            r'\s{2,}(.*)|'
            r'\s+(?!' + _PROSE_PREFIXES + r')([A-Za-z0-9(\[][^\n.]*?)(?<!\.)\s*$'
            r'|$)|'
            r'^\s*project(?:\s*[:|]\s*(.*)|\t+\s*(.*)|\s{2,}(.*)|\s+(?=(?:construction|rehabilitation|development|improvement|concreting|installation|provision|upgrading|repair|expansion|establishment|completion|procurement)\b)(.*))$'
        ),
        'project_code': (
            r'^\s*(?:(?:source\s+)?project\s+(?:code|id|number|no\.?))'
            r'(?:'
            r'\s*[:|]\s*(.*)|'
            r'\t+\s*(.*)|'
            r'\s{2,}(.*)|'
            r'\s+(?!' + _PROSE_PREFIXES + r')([A-Za-z0-9#][A-Za-z0-9#_\-./]{1,40})\s*$'
            r'|$)'
        ),
        'requirement': (
            r'^\s*(?:document\s+type|documentary\s+requirement|requirement\s+(?:name|type))'
            r'(?:\s*[:|]\s*(.*)|\t+\s*(.*)|\s{2,}(.*)|$)'
        ),
    }

    expected_title_variants = canonical_project_titles(project)

    checks = []
    for field, pattern in patterns.items():
        if field == 'lgu':
            checks.append(_inspect_lgu(text, lgu_obj))
            continue
        values = []
        for page, content in enumerate(text.split('\f'), 1):
            lines = content.splitlines()
            for index, line in enumerate(lines):
                match = re.match(pattern, line, re.I)
                if not match:
                    continue
                matched_groups = [v for v in match.groups() if v is not None]
                value = matched_groups[0].split('|')[0].split('\t')[0].strip() if matched_groups else ''
                next_index = index + 1
                while next_index < len(lines) and lines[next_index].strip() in (':', '|', ':-', '-', '='):
                    next_index += 1
                if not value and next_index < len(lines):
                    following = lines[next_index].strip()
                    if not is_label(following):
                        value = following
                        next_index += 1
                # Rejoin a known title split by PDF wrapping or DOCX text runs.
                if field == 'project_title' and value and expected[field]:
                    rejoin_targets = [expected[field]] + expected_title_variants + [
                        strip_display_markers(t) for t in expected_title_variants
                    ]
                    rejoin_normals = [_normal(t) for t in rejoin_targets if t]
                    while (any(norm.startswith(_normal(value) + ' ') for norm in rejoin_normals)
                           and next_index < len(lines) and lines[next_index].strip()):
                        following = lines[next_index].strip()
                        if is_label(following):
                            break
                        value += ' ' + following
                        next_index += 1
                if field == 'lgu':
                    value = value.split(',')[0].strip()
                if field == 'project_code':
                    if (re.search(r'\b(?:is|was|are|shall|will|must|should|can|may|requires|assigned|pending|determined|provided|specified)\b', value, re.I)
                            or len(value.split()) >= 4):
                        continue
                if len(value) < 3 or re.fullmatch(r'[_\-.\s]+|n/?a|none|tbd', value, re.I):
                    continue
                values.append({'text': value, 'page': page if '\f' in text else None})

        def normal(value):
            if field != 'lgu':
                return _normal(value)
            name = _lgu(value)
            province = _lgu(getattr(lgu_obj, 'province', None))
            if province and name.endswith(' ' + province):
                name = name[:-(len(province) + 1)]
            return name

        if field == 'project_title':
            def title_matches(obs_text, exp_text):
                if _same(obs_text, exp_text, normal):
                    return True
                clean_obs = strip_display_markers(obs_text)
                clean_exp = strip_display_markers(exp_text)
                if _same(clean_obs, clean_exp, normal):
                    return True
                for variant in expected_title_variants:
                    if _same(obs_text, variant, normal) or _same(clean_obs, strip_display_markers(variant), normal):
                        return True
                return False

            conflicts = [v for v in values if expected[field] and not title_matches(v['text'], expected[field])]
        else:
            conflicts = [v for v in values if expected[field] and not _same(v['text'], expected[field], normal)]

        checks.append({
            'field': field, 'expected': expected[field], 'observed': values,
            'status': 'mismatch' if conflicts else 'matches' if values and expected[field] else 'unverified',
            'conflicts': conflicts,
            'reason': ('Explicit identity differs.' if conflicts
                       else 'Identity matched.' if values and expected[field]
                       else 'No explicit identity verified.')
        })

    status = 'matches'
    if any(c['status'] == 'unverified' for c in checks if c['expected']):
        status = 'unverified'
    if any(c['status'] == 'mismatch' for c in checks):
        status = 'mismatch'

    context_payload = destination_context_payload(project, requirement, file_name, text)
    fingerprint = context_fingerprint(context_payload)
    return {
        'status': status,
        'checks': checks,
        'checker_version': DESTINATION_CHECKER_VERSION,
        'context_payload': context_payload,
        'context_fingerprint': fingerprint,
    }
