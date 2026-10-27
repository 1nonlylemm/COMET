"""Conservative identity evidence; suggestions never establish compliance."""
import re
import json

ROLE_PATTERNS = {
    'nadai': r'\bnotice\s+of\s+authority\s+to\s+debit\s+account\s+issued\b',
    'receipt': r'\b(?:certif\w*|confirm\w*|acknowledg\w*).{0,180}\b(?:receiv\w*|receipt)\b',
    'trust_transfer': r'\b(?:transfer\w*|record\w*).{0,180}\btrust\s+(?:fund|account)\b|\bauthority\s+for\s+fund\s+transfer\b.{0,180}\btrust\s+fund\b',
    'bank_statement': r'\b(?:statement\s+of\s+account|account\s+statement)\b',
}
REQUIREMENT_PATTERNS = {
    'nadai': r'\bnadai\b',
    'receipt': r'\b(?:confirmation|official\s+receipt)\b',
    'trust_transfer': r'\btrust\s+(?:fund|account)\b',
    'bank_statement': r'\bbank\s+statement\b|\bstatement\s+of\s+account\b',
}


def is_fund_return_requirement(candidate):
    if candidate.get('document_category') == 'proof_of_return_of_funds':
        return True
    return bool(re.search(
        r'\b(?:return|reversion)\b.{0,70}\b(?:funds?|subsidy|balances?)\b|\bfund\s+reversion\b',
        str(candidate.get('requirement_name') or ''), re.I))


def has_fund_return_identity(text):
    """Require readable identity evidence, not a filename or completion references."""
    header = re.sub(r'\s+', ' ', str(text or '')[:1800])
    unused = r'(?:unutili[sz]ed|unused|unexpended|unspent|surplus)'
    titles = re.finditer(
        rf'\b(?:proof|certification|certificate)\s+(?:of|on)\s+(?:the\s+)?(?:return|reversion)\s+of\s+{unused}\b'
        rf'|\bcertification\s+of\s+{unused}\s+(?:funds?|subsidy|balances?)\s+reversion\b', header, re.I)
    for title in titles:
        preceding = header[max(0, title.start() - 90):title.start()]
        if not re.search(r'\b(?:attach\w*|enclos\w*|submit\w*|requir\w*|supporting|copy\s+of|refer\w*)\b.{0,65}$',
                         preceding, re.I):
            return True
    return bool(re.search(r'\b(?:official\s+receipt|collection\s+confirmation)\b', header, re.I)
                and re.search(rf'\breturn\s+of\s+{unused}\s+(?:funds?|subsidy|balances?)\b', header, re.I)
                and re.search(r'\b(?:treasury|BTr)\b', header, re.I))


def roles(text):
    text = str(text or '')
    # A late reference to an enclosed NADAI does not make the cover letter a NADAI.
    found = [role for role, pattern in ROLE_PATTERNS.items()
             if re.search(pattern, text[:600] if role == 'nadai' else text, re.I | re.S)]
    # Bank forms place the credit account far below the printed transfer title.
    if ('trust_transfer' not in found
            and re.search(r'\bauthority\s+for\s+fund\s+transfer\b', text[:600], re.I)
            and re.search(r'\btrust\s+fund\b', text, re.I)):
        found.append('trust_transfer')
    return found


def procurement_ambiguities(text, candidates, suggested):
    """Expose overlapping catalog entries without deciding their equivalence."""
    if not suggested or not re.search(
            r'\b(?:invitation\s+to\s+bid|bid\s+notice\s+abstract|invitation\s+for\s+bids)\b',
            text[:2000], re.I):
        return []
    selected_project = suggested.get('project_id')
    groups = {'generic': [], 'goods': []}
    for candidate in candidates:
        # Never present an alternative from a different or unknown project.
        if selected_project is None or candidate.get('project_id') != selected_project:
            continue
        name = candidate.get('requirement_name', '')
        if not re.search(r'\bprocurement\s+posting\b', name, re.I):
            continue
        group = 'goods' if re.search(r'\bgoods\b', name, re.I) else 'generic'
        # Infrastructure or other named subtypes are not generic alternatives.
        if group == 'generic' and not re.match(r'^\s*procurement\s+posting\b', name, re.I):
            continue
        groups[group].append(candidate)
    options = groups['generic'] + groups['goods']
    if not all(groups.values()) or not any(
            c['project_requirement_id'] == suggested.get('project_requirement_id') for c in options):
        return []
    return [{'kind': 'generic_goods_procurement_posting',
             'equivalence_status': 'requires_policy_review',
             'alternatives': [{key: c.get(key) for key in
                 ('project_id', 'project_requirement_id', 'requirement_id', 'requirement_name')}
                 for c in options]}]


def inspect_catalog_scope(candidate):
    """Compare metadata only. A mismatch does not revoke an active snapshot."""
    candidate = candidate or {}
    scope = candidate.get('catalog_scope') or {}
    kind = str(candidate.get('project_kind') or '').strip().lower()
    result = {'status': 'unknown', 'project_kind': kind or None,
              'declared_project_kinds': None, 'source': scope.get('source'),
              'project_requirement_id': candidate.get('project_requirement_id'),
              'requirement_name': candidate.get('requirement_name')}
    if scope.get('source') != 'canonical_requirement' or 'declared_project_kinds' not in scope:
        return result
    values = scope['declared_project_kinds']
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except (TypeError, ValueError):
            # The domain model also supports legacy comma-separated kind strings.
            if values.lstrip().startswith(('[', '{')):
                return result
        if isinstance(values, str):
            values = values.split(',')
    if values is not None and (not isinstance(values, (list, tuple))
                              or not all(isinstance(value, str) for value in values)):
        return result
    normalized = None if values is None else sorted({value.strip().lower() for value in values})
    result['declared_project_kinds'] = normalized
    if kind not in ('infrastructure', 'goods', 'vehicle', 'financial_assistance'):
        return result
    result['status'] = 'matches' if (normalized is None or kind in normalized
                                    or '*' in normalized or 'all' in normalized) else 'mismatch'
    return result


def procurement_activity(text):
    """Report explicit document classification separately from funded-project kind."""
    if not re.search(r'\b(?:invitation\s+to\s+bid|bid\s+notice\s+abstract|invitation\s+for\s+bids)\b',
                     text[:2000], re.I):
        return {'classifications': [], 'evidence': []}
    signals = []
    for classification, pattern in (
            ('goods', r'\bclassification\s*:\s*goods\b|\bdelivery\s+of\s+the\s+goods\b'),
            ('infrastructure', r'\bclassification\s*:\s*(?:civil\s+works|infrastructure)\b')):
        match = re.search(pattern, text[:4000], re.I)
        if match:
            signals.append({'classification': classification, 'text': match.group(0)})
    return {'classifications': [signal['classification'] for signal in signals], 'evidence': signals}


def inspect_evidence(text, metadata, candidates, suggested, file_name):
    """Use real page boundaries only, including empty pages. Do not infer pages."""
    text = str(text or '')
    pages = []
    if '\f' in text or metadata.get('page_boundaries_preserved'):
        for number, content in enumerate(text.split('\f'), 1):
            pages.append({'page': number, 'roles': roles(content)})
    else:
        pages.append({'page': None, 'roles': roles(text)})
    distinct = {role for page in pages for role in page['roles']}
    signatures = {tuple(page['roles']) for page in pages if page['roles']}
    bundle = len(distinct) > 1 and len(signatures) > 1 and len(pages) > 1
    suggestions = []
    for page in pages:
        for role in page['roles']:
            for candidate in candidates:
                if re.search(REQUIREMENT_PATTERNS[role], candidate.get('requirement_name', ''), re.I):
                    suggestions.append({'page': page['page'], 'role': role,
                        'project_requirement_id': candidate['project_requirement_id'],
                        'requirement_id': candidate.get('requirement_id'),
                        'requirement_name': candidate.get('requirement_name')})
    reasons = []
    fund_return = has_fund_return_identity(text)
    if fund_return and not any(is_fund_return_requirement(c) for c in candidates):
        reasons.append('missing_fund_return_requirement')
    eligible_suggested = next((candidate for candidate in candidates if suggested
                              and candidate.get('project_requirement_id') == suggested.get('project_requirement_id')), None)
    scope = inspect_catalog_scope(eligible_suggested)
    if scope['status'] == 'mismatch':
        reasons.append('catalog_scope_conflict')
    ambiguities = procurement_ambiguities(text, candidates, suggested)
    if ambiguities:
        reasons.append('overlapping_procurement_requirements')
    if bundle:
        reasons.append('possible_document_bundle')
    if metadata.get('extraction_incomplete') or metadata.get('text_truncated'):
        reasons.append('incomplete_extraction')
    if metadata.get('unreadable_pages') or metadata.get('coverage_unknown'):
        reasons.append('unreadable_or_unknown_page_coverage')
    if not text.strip() and metadata.get('text_available') is False:
        reasons.append('no_readable_text')
    name = (suggested or {}).get('requirement_name', '')
    if 'nadai' in distinct and 'trust_transfer' not in distinct and not bundle and not re.search(r'\bnadai\b', name, re.I):
        if re.search(REQUIREMENT_PATTERNS['receipt']+'|'+REQUIREMENT_PATTERNS['trust_transfer'], name, re.I):
            reasons.append('document_identity_conflict')
    if 'nadai' in distinct and 'trust_transfer' not in distinct and re.search(r'confirm\w*.*receipt', file_name or '', re.I) and not re.search(r'nadai', file_name or '', re.I):
        reasons.append('filename_content_conflict')
    return {'possible_bundle': bundle, 'page_roles': pages,
            'document_identity': 'fund_return' if fund_return else None,
            'catalog_scope': scope, 'procurement_activity': procurement_activity(text),
            'requirement_ambiguities': ambiguities,
            'page_requirement_suggestions': suggestions, 'review_reasons': reasons,
            'interpretation': 'Identity evidence only; requirement acceptance requires review.'}
