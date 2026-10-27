"""Conservative, document-derived identity evidence for project discovery.

No expected destinations, benchmark labels, filenames or per-project exceptions
belong here. These helpers deliberately do not consult the requirement catalog.
"""
import re
import unicodedata


def normalize(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', text)
    text = re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()
    text = re.sub(r'\bsta\b', 'santa', text)
    return re.sub(r'\bsto\b', 'santo', text)


def contains(text, phrase):
    return bool(phrase and re.search(r'\b' + re.escape(phrase) + r'\b', text))


def project_text(value):
    """Normalize domain title abbreviations without altering codes or LGUs."""
    text = normalize(value)
    text = re.sub(r'\bfarm\s+to\s+market\s+roads?\b', 'farm to market road', text)
    return re.sub(r'\bfmr\b', 'farm to market road', text)


def project_title_phrase_match(candidate_title, document_text):
    """Return review evidence when an explicit, normalized title phrase occurs.

    The phrase is intentionally not a project-resolution score: common project
    descriptions such as "multipurpose building" can identify a candidate
    family but cannot identify a unique project or phase on their own.
    """
    title = normalize(candidate_title)
    corpus = normalize(document_text)
    aliases = {'multipurpose building': ('multipurpose building', 'mpb')}
    return [phrase for phrase, forms in aliases.items()
            if contains(title, phrase) and any(contains(corpus, form) for form in forms)]


_PROJECT_ALIAS_STOPWORDS = {
    'a', 'an', 'and', 'at', 'by', 'for', 'from', 'in', 'into', 'of', 'on',
    'or', 'the', 'to', 'with', 'project', 'phase', 'program', 'fund', 'funds',
    'lgu', 'municipality', 'municipal', 'city', 'province', 'barangay',
}


def project_metadata_phrase_matches(custom_fields, document_text):
    """Find exact registered project aliases present in the document.

    Aliases only retrieve review candidates: they never add confidence or
    resolve a project. Free-form notes and other flexible project fields are
    deliberately excluded because they are not consistently identity data.
    """
    corpus = project_text(document_text)
    fields = custom_fields if isinstance(custom_fields, dict) else {}
    candidates = []
    for key in ('project_aliases', 'alternate_project_names', 'alternate_names', 'aliases'):
        value = fields.get(key)
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, (list, tuple)):
            candidates.extend(item for item in value if isinstance(item, str))

    matches = set()
    for candidate in candidates:
        words = project_text(candidate).split()
        informative = [word for word in words
                       if len(word) >= 3 and word not in _PROJECT_ALIAS_STOPWORDS
                       and not re.fullmatch(r'\d+', word)]
        phrase = ' '.join(words)
        if (len(words) >= 2 and len(informative) >= 2
                and contains(corpus, phrase)):
            matches.add(phrase)
    return sorted(matches)


def possible_duplicate_project_groups(project_candidates):
    """Identify candidate rows with the same identity fields but different codes.

    This is a catalog-quality warning only. It must never collapse IDs, alter
    scores, or change resolution status because source codes may represent
    legitimate distinct records that need an administrator's review.
    """
    grouped = {}
    for candidate in project_candidates or []:
        title = project_text(candidate.get('project_name'))
        locality = locality_name(candidate.get('lgu_name'))
        program = normalize(candidate.get('program_code') or candidate.get('program_name'))
        fiscal_year = str(candidate.get('fiscal_year') or '').strip()
        project_kind = normalize(candidate.get('project_kind'))
        if not all((title, locality, program, fiscal_year)):
            continue
        key = (title, locality, program, fiscal_year, project_kind)
        grouped.setdefault(key, []).append(candidate)

    warnings = []
    for candidates in grouped.values():
        codes = {normalize(item.get('source_project_code') or item.get('project_code')
                           or item.get('subaybayan_project_code'))
                 for item in candidates}
        codes.discard('')
        if len(candidates) < 2 or len(codes) < 2:
            continue
        warnings.append({
            'project_name': candidates[0].get('project_name'),
            'lgu_name': candidates[0].get('lgu_name'),
            'program_name': candidates[0].get('program_name'),
            'fiscal_year': candidates[0].get('fiscal_year'),
            'projects': sorted(({
                'project_id': item.get('project_id'),
                'project_code': item.get('source_project_code') or item.get('project_code')
                or item.get('subaybayan_project_code'),
            } for item in candidates), key=lambda item: (item['project_code'] or '', item['project_id'] or 0)),
        })
    return warnings


def locality_name(value):
    text = normalize(value)
    text = re.sub(r'^(?:(?:municipal|city|provincial) government(?: of)? |'
                  r'(?:municipality|city|province)(?: of)? )', '', text)
    return re.sub(r' (?:city|municipality|province)$', '', text).strip()


def locality_aliases(value):
    """Catalog-derived spellings, including a common scanned ñ -> fi error.

    Do not fuzzy-match arbitrary place names or rewrite every occurrence of fi.
    The OCR alternative is available only for a catalog name containing ñ.
    """
    aliases = {locality_name(value)}
    if 'ñ' in str(value or '').lower():
        aliases.add(locality_name(str(value).replace('Ñ', 'FI').replace('ñ', 'fi')))
    return aliases - {''}


def canonical_localities(values, known_lgus):
    if known_lgus is None:
        return values
    aliases = [(alias, locality_name(name)) for name in known_lgus if name
               for alias in locality_aliases(name)]
    canonical = set()
    for value in values:
        matches = [(alias, name) for alias, name in aliases
                   if value == alias or value.startswith(alias + ' ')]
        if matches:
            longest = max(len(alias) for alias, _ in matches)
            canonical.update(name for alias, name in matches if len(alias) == longest)
    return canonical


def issuer_localities(text):
    """Read the letterhead, stopping before recipient/body/document sections.

    A supplier's address or a body reference to another LGU must not become an
    issuing authority. Multiple letterheads remain ambiguous rather than being
    arbitrarily collapsed to one LGU.
    """
    issuers = set()
    headings = re.compile(
        r'^(?:notice (?:of|to)|purchase order|delivery receipt|inspection|'
        r'project profile|annual investment|local development|certification|official receipt|received from|registered owner|'
        r'certificate|to\b|dear\b|supplier\b|recipient\b|address\b|subject\b|'
        r'mr\b|mrs\b|ms\b|attention\b|approved variation|name of project|location\b|date\b)'
    )
    for raw_line in str(text or '')[:1600].splitlines()[:16]:
        line = normalize(raw_line)
        if headings.search(line):
            break
        if re.match(r'^(?:(?:municipal|city|provincial) government of |'
                    r'(?:municipality|city|province) of )', line):
            name = locality_name(line)
            # A provincial letterhead does not identify a municipal project.
            if not re.match(r'^(?:provincial government|province) ', line) and name:
                issuers.add(name)
    return issuers


def vehicle_registration_parties(text):
    """Read named government parties on an LTO registration instrument.

    An owner or payer identifies an LGU for review retrieval, never a unique
    vehicle/project. LTO branch addresses and bare place mentions are excluded.
    """
    parties = set()
    for page in str(text or '').split('\f'):
        corpus = normalize(page)
        lines = [normalize(line) for line in page.splitlines() if line.strip()]
        if not (any(re.fullmatch(r'(?:land transportation office|lto)', line) for line in lines[:15])
                and re.search(r'\b(?:certificate of registration|official receipt|duly registered|details of first registration)\b', corpus)
                and re.search(r'\b(?:plate no|chassis|vehicle type|motor vehicle)\b', corpus)):
            continue
        for index, line in enumerate(lines):
            explicit = re.match(r'^(?:name of (?:the )?registered owner|registered owner|received from)\b\s*(.*)', line)
            value = explicit.group(1) if explicit else line
            if explicit and not value and index + 1 < len(lines):
                value = lines[index + 1]
            # Government entity names only; supplier names, addresses and LTO
            # field-office cities must not establish an asset's destination.
            match = re.match(r'^((?:municipal|city|provincial) government of .+?)(?:\s+c\s+\d|\s+tin\b|$)', value)
            previous = lines[index - 1] if index else ''
            if match and not re.match(r'^(?:supplier|vendor|seller|previous owner)\b', previous):
                parties.add(locality_name(match.group(1)))
    return parties


def document_context(extracted_text, known_lgus=None):
    corpus = normalize(extracted_text)
    issuers = issuer_localities(extracted_text)
    # Explicit form fields also identify an authority, even after the title or
    # on a procurement portal printout. Never infer this role from bare addresses.
    lines = str(extracted_text or '').splitlines()
    for index, line in enumerate(lines):
        match = re.match(r'^(?:procuring entity|implementing lgu|implementing agency|lgu name|name of (?:the )?lgu|lgu|province city municipality)\b\s*(.*)', normalize(line))
        if match:
            value = match.group(1)
            if not value and index + 1 < len(lines):
                value = normalize(lines[index + 1])
                if re.match(r'^(?:project|supplier|address|date|budget|amount|title)\b', value):
                    continue
            if value:
                issuers.add(locality_name(value))
    # An explicitly named trust-fund destination on a transfer instrument is a
    # recipient role, not the bank branch, supplier, or source account's LGU.
    destinations = set()
    first_page = str(extracted_text or '').split('\f')[0]
    if any(re.match(r'^authority for fund transfer\b', normalize(line))
           for line in first_page[:1200].splitlines()):
        account_role = None
        for line in first_page.splitlines():
            normalized = normalize(line)
            if re.search(r'\bdebit\b', normalized):
                account_role = 'source'
            elif re.search(r'\bcre(?:dit|dlt|ot)\b', normalized):
                # Bounded OCR alternatives for the CREDIT account-field label.
                account_role = 'destination'
            match = re.match(r'^((?:city|municipality|municipal government|city government) of .+?)\s+trust (?:fund|account)\b', normalized)
            if account_role == 'destination' and match:
                destinations.add(locality_name(match.group(1)))
    # Unknown OCR names cannot establish an exclusive jurisdiction conflict.
    issuers = canonical_localities(issuers, known_lgus)
    destinations = canonical_localities(destinations, known_lgus)
    return {
        'corpus': corpus,
        'issuers': issuers,
        'destinations': destinations,
        'registration_parties': canonical_localities(vehicle_registration_parties(extracted_text), known_lgus),
        'fiscal_years': set(re.findall(
            r'\b(?:fiscal year|funding year|f\s*y)\s*(20\d{2})\b', corpus)),
    }


def identity_evidence(candidate, extracted_text, context=None):
    context = context if context is not None else document_context(extracted_text)
    corpus = context['corpus']
    locality = locality_name(candidate.get('lgu_name'))
    aliases = locality_aliases(candidate.get('lgu_name'))
    issuers = context['issuers']
    issuer_match = bool(locality and any(contains(name, alias) for name in issuers for alias in aliases))
    destinations = context.get('destinations', set())
    destination_match = bool(locality and any(contains(name, alias) for name in destinations for alias in aliases))
    registration_parties = context.get('registration_parties', set())
    registration_party_match = bool(locality and any(contains(name, alias)
        for name in registration_parties for alias in aliases))
    provincial = bool(re.match(r'^(?:provincial government|province) ',
                               normalize(candidate.get('lgu_name'))))
    # More than one letterhead is evidence of multiple parties/pages, not proof
    # that all other LGUs contradict the document's destination.
    issuer_conflict = bool(len(issuers) == 1 and locality and not provincial and not issuer_match)
    fiscal_years = context['fiscal_years']
    fy = str(candidate.get('fiscal_year') or '')
    return {
        'issuer_lgu_match': issuer_match,
        'issuer_lgu_conflict': issuer_conflict,
        'destination_lgu_match': destination_match,
        'registration_party_lgu_match': registration_party_match,
        'destination_lgu_conflict': bool(len(destinations) == 1 and locality and not provincial and not destination_match),
        'has_explicit_destination': bool(destinations),
        'lgu_mention': any(contains(corpus, alias) for alias in aliases),
        'fiscal_year_match': fy in fiscal_years,
        'fiscal_year_explicit': bool(fiscal_years),
    }


def title_terms(candidate, excluded):
    """Compare title words separately from identifiers, years and jurisdiction.

    Missing a tracking code should forfeit code evidence, not also reduce title
    coverage. Code matching remains a separate, stronger signal.
    """
    title = str(candidate.get('project_name') or '')
    title = re.sub(r'\b[A-Za-z]{2,}[A-Za-z0-9]*(?:[-_/][A-Za-z0-9]+)*[-_/]20\d{2}[-_/][A-Za-z0-9]+(?:[-_/][A-Za-z0-9]+)*\b', ' ', title)
    text = project_text(title)
    excluded = {word for term in excluded for word in normalize(term).split()}
    for key in ('source_project_code', 'subaybayan_project_code'):
        code = normalize(candidate.get(key))
        if code:
            text = re.sub(r'\b' + re.escape(code) + r'\b', ' ', text)
    jurisdiction = set(normalize(candidate.get('lgu_name')).split())
    return {word for word in text.split()
            if len(word) >= 3 and not re.fullmatch(r'\d+(?:m|k)?', word)
            and word not in excluded and word not in jurisdiction}


def resolution_status(ranked):
    if not ranked:
        return 'unresolved', False
    top = ranked[0]
    signals = top.get('signals', {})
    score = top['score']
    runner_score = ranked[1]['score'] if len(ranked) > 1 else 0.0
    if signals.get('project_hint_match'):
        return 'resolved', False
    if score < 0.35:
        return 'unresolved', False
    if signals.get('locality_conflict') or signals.get('program_conflict'):
        return 'ambiguous', True
    # Both alternatives already meet the strong-match tier. Capped heuristic
    # totals are not probabilities; their apparent gap cannot prove uniqueness.
    if runner_score >= 0.75:
        return 'ambiguous', True
    if not (signals.get('code_match') or signals.get('exact_title_match')):
        # A large lexical score gap cannot establish uniqueness when another
        # catalog project shares the document's actual title evidence and an
        # explicitly identified jurisdiction. Missing incidental title words
        # (batch/date/reference notes, for example) are not contradictions.
        authority = signals.get('issuer_lgu_match') or signals.get('destination_lgu_match')
        matched = set(signals.get('matched_title_terms', []))
        for other in ranked[1:]:
            alternative = other.get('signals', {})
            if (authority and other['score'] >= 0.35
                    and locality_name(top.get('lgu_name')) == locality_name(other.get('lgu_name'))
                    and (alternative.get('issuer_lgu_match') or alternative.get('destination_lgu_match'))
                    and not (alternative.get('locality_conflict') or alternative.get('program_conflict'))
                    and len(matched & set(alternative.get('matched_title_terms', []))) >= 2):
                return 'ambiguous', True
            # Cross-LGU competing evidence: when multiple candidate LGUs and projects
            # are mentioned without authoritative codes, titles or letterhead.
            if (not authority
                    and locality_name(top.get('lgu_name')) != locality_name(other.get('lgu_name'))
                    and signals.get('lgu_match') and alternative.get('lgu_match')
                    and alternative.get('distinctive_token_count', 0) >= 1
                    and alternative.get('distinctive_ratio', 0) >= 0.5
                    and not (alternative.get('locality_conflict') or alternative.get('program_conflict'))
                    and other['score'] >= 0.30):
                return 'ambiguous', True
    if score >= 0.40 and runner_score >= 0.35 and score - runner_score < 0.15:
        return 'ambiguous', True
    if score >= 0.50:
        return 'resolved', False
    # Retain moderate, corroborated evidence for requirement classification;
    # never turn a sub-threshold project into an automatic acceptance.
    corroborated = (signals.get('lgu_match')
                    and signals.get('distinctive_token_count', 0) >= 2
                    and signals.get('distinctive_ratio', 0) >= 0.5)
    title_evidence = (signals.get('distinctive_token_count', 0) >= 3
                      and signals.get('distinctive_ratio', 0) >= 0.75)
    authority_and_site = (signals.get('issuer_lgu_match')
                          and signals.get('distinctive_token_count', 0) >= 1
                          and signals.get('distinctive_ratio', 0) >= 0.5)
    if corroborated or title_evidence or authority_and_site:
        return 'ambiguous', True
    return 'unresolved', False
