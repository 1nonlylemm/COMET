"""Document identity gates for already-authorized candidates, never acceptance rules."""
import re

# Printed titles, not incidental terms such as "accepted", "completed", or "notary".
# Keep multiple identities when real page boundaries expose a document bundle.
IDENTITIES = {
    'notice_to_proceed': (r'\bnotice\s+to\s+proceed\b', r'notice\s+to\s+proceed|commencement\s+order'),
    'notice_of_award': (r'\bnotice\s+of\s+award\b', r'notice\s+of\s+award'),
    'contract_agreement': (r'\b(?:contract\s+agreement|articles\s+of\s+agreement)\b', r'contract\s+agreement|articles\s+of\s+agreement'),
    'purchase_order': (r'\bpurchase\s+order\b', r'purchase\s+order'),
    'delivery_receipt': (r'\bdelivery\s+receipt\b', r'delivery\s+receipt|engine\s+stencil'),
    'inspection_report': (r'\binspection\s+(?:and|&)\s+acceptance\s+report\b', r'inspection.*acceptance|\biar\b'),
    'motor_vehicle_authority': (r'\bauthority\s+to\s+purchase\s+(?:a\s+)?motor\s+vehicles?\b', r'authority.*purchase.*(?:motor|vehicle)|\bapmv\b'),
    'project_profile': (r'\bproject\s+(?:profile|proposal)\b', r'project\s+(?:profile|proposal)'),
    'completion_certificate': (r'\bcertificate\s+of\s+(?:completion|final\s+acceptance\s+(?:and|&)\s+completion)\b', r'certificate\s+of\s+completion'),
    'turnover_acceptance': (r'\bcertificate\s+of\s+(?:completion\s+and\s+turnover\s*/?\s*acceptance|acceptance)\b', r'(?:turnover|certificate).*acceptance|acceptance.*(?:turnover|certificate)'),
    'vehicle_registration': (r'\b(?:certificate\s+of\s+registration|official\s+receipt)\b', r'(?:lto|vehicle).*registration|\bor\s*[/&-]\s*cr\b|official\s+receipt.*certificate\s+of\s+registration'),
    'final_acceptance': (r'\bcertificate\s+of\s+final\s+acceptance\b', r'final\s+acceptance'),
    'project_completion_report': (r'\bproject\s+completion\s+report\b', r'project\s+completion\s+report|\bpcr\b'),
    'sord': (r'\bstatement\s+of\s+receipts?\s+and\s+disbursements?\b', r'statement\s+of\s+receipts?|\bsord\b'),
    'qaar': (r'\bquality\s+assurance\s+assessment\s+report\b|\bQAAR\b', r'quality\s+assurance|\bqaar\b'),
    'nadai': (r'\bnotice\s+of\s+authority\s+to\s+debit\s+account\s+issued\b', r'\bnadai\b|notice\s+of\s+authority\s+to\s+debit'),
    'procurement_posting': (r'\b(?:invitation\s+to\s+bid|bid\s+notice\s+abstract)\b', r'procurement.*(?:posting|bid)|philgeps|invitation\s+to\s+bid'),
    'program_of_works': (r'\bprogram(?:me)?\s+of\s+works?\b', r'program(?:me)?\s+of\s+works?'),
    'engineering_design': (r'\bdetailed\s+engineering\s+design\b', r'detailed\s+engineering|\bded\b'),
    'photo_documentation': (r'\b(?:project\s+)?photo\s+documentation\b', r'photo.*documentation|before.*after\s+photos|turnover\s+photos'),
    'resolution': (r'\bresolution\s+(?:no\.?|authorizing|approving|endorsing)\b', r'resolution|sanggunian'),
    'inspection_checklist': (r'\b(?:post[ -]delivery\s+(?:vehicle\s+)?inspection\s+checklist|pre[ -]procurement\s+(?:vehicle\s+)?checklist)\b', r'inspection\s+checklist|pre[ -]procurement.*checklist|appendix\s*(?:18|19)'),
    'work_accomplishment': (r'\b(?:final\s+)?statement\s+of\s+work\s+accomplished\b', r'statement\s+of\s+work\s+accomplished|\bswa\b'),
    'monthly_progress': (r'\bmonthly\s+progress\s+report\b', r'monthly\s+progress\s+report|(?:monthly|quarterly).*progress|progress.*utilization'),
    'contractor_billing': (r'\b(?:progress|final|contractor)\s+billing\b', r'\b(?:progress|final|contractor)\s+billing\b'),
    'investment_program': (r'\b(?:annual\s+investment\s+program|local\s+development\s+investment\s+program)\b', r'annual\s+investment|local\s+development\s+investment|\baip\b|\bldip\b'),
    'receipt_confirmation': (r'\bconfirmation\s+(?:of|on)\s+(?:the\s+)?(?:receipt\s+of\s+funds?|fund\s+receipt)\b', r'confirmation|official\s+receipt'),
    'trust_transfer': (r'\b(?:proof|certification)\s+of\s+transfer\s+to\s+(?:the\s+)?(?:LGU\s+)?trust\s+(?:fund|account)\b', r'trust\s+(?:fund|account)'),
    'bank_statement': (r'\b(?:account\s+statement|statement\s+of\s+account)\b', r'bank\s+statement|statement\s+of\s+account'),
}


def _titles(text):
    found = set()
    for page in str(text or '').split('\f'):
        header = re.sub(r'\s+', ' ', page[:1200])
        for identity, (pattern, _) in IDENTITIES.items():
            if identity == 'contractor_billing' and not any(re.fullmatch(
                    r'\s*(?:\d+(?:\.\d+)?\s*%\s*)?(?:progress|final|contractor)\s+billing'
                    r'(?:\s+(?:statement|package|request))?\s*(?:no\.?\s*[:#]?\s*[\w-]+)?\s*',
                    line, re.I) for line in page[:1200].splitlines()):
                continue
            if identity == 'vehicle_registration' and not re.search(
                    r'\b(?:land\s+transportation\s+office|lto|motor\s+vehicle|chassis|engine\s+(?:no|number))\b', page, re.I):
                continue
            if identity == 'motor_vehicle_authority' and not re.search(
                    r'^\s*authority\s+to\s+purchase\s+(?:a\s+)?motor\s+vehicles?\b',
                    page[:1200], re.I | re.M):
                continue
            for match in re.finditer(pattern, header, re.I):
                if (identity == 'vehicle_registration'
                        and re.match(r'official\s+receipt', match.group(0), re.I)
                        and not re.search(r'\b(?:land\s+transportation\s+office|lto)\b', page, re.I)):
                    continue
                prefix = header[max(0, match.start() - 100):match.start()]
                if not re.search(r'\b(?:attach\w*|enclos\w*|submit\w*|requir\w*|request\w*|refer\w*|copy\s+of|pursuant\s+to|under|per)\b.{0,65}$', prefix, re.I):
                    found.add(identity)
                    break
    return found


def completed_trust_transfer(text):
    """Retain transfer evidence in a receipt letter only when transfer is attested.

    A promise, request, negation or a reference to an enclosed form is not a
    completed transfer. This is documentary identity, not verified compliance.
    """
    for clause in re.split(r'(?<!\d)[.!?;]|\f', str(text or '')):
        compact = re.sub(r'\s+', ' ', clause)
        if re.search(r'\b(?:not|never|cannot|unable|unverified|pending|attach\w*|enclos\w*|template|quote\w*|request\w*)\b', compact, re.I):
            continue
        if re.search(r'\b(?:funds?|amounts?|balances?|proceeds)\b.{0,80}'
                     r'\b(?:(?:have|has|had)\s+been|were|was)\s+(?:duly\s+)?transferred\b'
                     r'.{0,180}\btrust\s+(?:fund|account)\b', compact, re.I):
            return True
    return False


def motor_vehicle_authority(text):
    first_page = str(text or '').split('\f')[0]
    # An APMV mentioned in policy instructions or a request is not an issued
    # authority. Require the operative grant, allowing a common OCR t/l error.
    return bool(re.search(r'\bAPMV\b', first_page, re.I)
                and re.search(r'\b(?:is|are)\s+hereby\s+au(?:thor|lhor)i[sz]ed\s+to\s+purchase\b',
                              re.sub(r'\s+', ' ', first_page), re.I))


def contractor_billing_purpose(text):
    """A payment cover can state the purpose of an attached billing packet.

    Inspect only the first three pages and require a payment instrument plus
    an operative payment-purpose clause. An enclosure list or ordinary project
    progress report does not establish a contractor billing request.
    """
    cover = re.sub(r'\s+', ' ', '\f'.join(str(text or '').split('\f')[:3])[:6000])
    return bool(re.search(r'\bdisbursement\s+vouchers?\b', cover, re.I)
        and re.search(r'\bfor\s+payment\s+of\s*:?\s*(?:\d+(?:\.\d+)?\s*%\s*)?'
                      r'(?:progress|final|contractor)\s+billing\b', cover, re.I))


def primary_identities(text):
    first = str(text or '').split('\f')[0]
    identities = _titles(first)
    if motor_vehicle_authority(first):
        identities.add('motor_vehicle_authority')
    if completed_trust_transfer(first):
        identities.add('trust_transfer')
    if 'nadai' not in identities and attested_fund_receipt(first):
        identities.add('fund_receipt_confirmation')
    if contractor_billing_purpose(text):
        identities.add('contractor_billing')
    return identities


def primary_structure(text):
    identities = primary_identities(text)
    if 'contractor_billing' in identities:
        return 'contractor_billing'
    if 'nadai' not in identities and attested_fund_receipt(text):
        return 'fund_receipt_confirmation'
    if 'motor_vehicle_authority' in identities and 'project_profile' not in identities:
        return 'motor_vehicle_authority'
    if 'trust_transfer' in identities and identities <= {'trust_transfer', 'receipt_confirmation'}:
        return 'trust_transfer'
    structures = identities & {
        'inspection_report', 'purchase_order', 'notice_of_award', 'notice_to_proceed',
        'contract_agreement', 'delivery_receipt', 'project_profile', 'procurement_posting',
    }
    return next(iter(structures)) if len(identities) == len(structures) == 1 else None


def supported_roles(candidate):
    text = str(candidate.get('requirement_name') or '')
    roles = {identity for identity, (_, pattern) in IDENTITIES.items() if re.search(pattern, text, re.I)}
    if is_fund_receipt_requirement(candidate):
        roles.add('fund_receipt_confirmation')
    if candidate.get('document_category') == 'monthly_progress_report':
        roles.add('monthly_progress')
    return roles


def is_fund_receipt_requirement(candidate):
    """Identify the requirement for an LGU attesting receipt of grant funds.

    Generic transaction receipts and billing/invoice requirements are excluded
    even when their titles contain "official receipt".
    """
    name = re.sub(r'\s+', ' ', str(candidate.get('requirement_name') or '')).lower()
    return bool(
        re.search(r'\b(?:confirmation|confirmed|lgu)\b', name)
        and re.search(r'\bfunds?\b', name)
        and re.search(r'\breceipt\b', name)
        and not re.search(r'\b(?:billing|invoice)\b', name)
    )


def attested_fund_receipt(text):
    """Recognize a completed receipt, never a request or future undertaking."""
    for clause in re.split(r'(?<!\d)[.!?;]|\f', str(text or '')):
        compact = re.sub(r'\s+', ' ', clause)
        if re.search(r'\b(?:not|never|pending|request\w*|will|shall|attach\w*|enclos\w*)\b', compact, re.I):
            continue
        if (re.search(r'\b(?:certif\w*|confirm\w*|acknowledg\w*)\b', compact, re.I)
                and re.search(r'\b(?:funds?|amount|allocation|proceeds)\b', compact, re.I)
                and re.search(r'\b(?:(?:has|have|had)\s+been|was|were)\s+(?:duly\s+)?(?:received|credited)\b', compact, re.I)):
            return True
    return False


def starts_defects_liability(text):
    """An initial warranty undertaking is not evidence of post-DLP acceptance."""
    compact = re.sub(r'\s+', ' ', str(text or ''))
    if re.search(r'\b(?:warranty|defects?\s+liability)\s+period\s+'
                 r'(?:(?:has|have)\s+(?:already\s+)?|is\s+)(?:expired|elapsed)\b', compact, re.I):
        return False
    return bool(re.search(
        r'\b(?:warranty|defects?\s+liability)\b.{0,150}'
        r'\b(?:start(?:s|ing)?|commenc(?:e|es|ing)|begin(?:s|ning)?|from\s+(?:the\s+)?(?:date\s+of\s+)?completion)\b',
        compact, re.I))


def _exclude_post_dlp_acceptance(text):
    """Keep lifecycle evidence within each titled document in a PDF packet."""
    documents = []
    current = []
    for page in str(text or '').split('\f'):
        # Untitled pages continue the preceding document, including warranty
        # clauses printed on the next page of an acceptance certificate.
        if current and _titles(page):
            documents.append('\f'.join(current))
            current = []
        current.append(page)
    if current:
        documents.append('\f'.join(current))
    has_initial_undertaking = any(starts_defects_liability(doc) for doc in documents)
    has_separate_final_acceptance = any(
        'final_acceptance' in _titles(doc) and not starts_defects_liability(doc)
        for doc in documents
    )
    return has_initial_undertaking and not has_separate_final_acceptance


def scope_candidates(text, candidates, preserve_ids=None):
    from app.services import matcher_evidence_service as evidence
    identities = _titles(text)
    identities.update(primary_identities(text))
    # A treasury debit notice can mention crediting without becoming an LGU
    # receipt certification. Preserve that distinction for single documents.
    if attested_fund_receipt(text) and 'nadai' not in identities:
        identities.add('receipt_confirmation')
    # A multi-document financial bundle must retain all page roles. A NADAI on
    # one page does not invalidate the separate receipt/transfer on another.
    pages = str(text or '').split('\f')
    if len(pages) > 1 and 'nadai' in identities:
        role_names = {'receipt': 'receipt_confirmation', 'trust_transfer': 'trust_transfer',
                      'bank_statement': 'bank_statement', 'nadai': 'nadai'}
        identities.update(role_names[role] for page in pages for role in evidence.roles(page))
    for page in pages:
        if (re.search(r'\bauthority\s+for\s+fund\s+transfer\b', page[:600], re.I)
                and 'trust_transfer' in evidence.roles(page)):
            identities.add('trust_transfer')
    if evidence.has_fund_return_identity(text):
        # A return certification may cite SORD/completion; preserve its primary identity.
        identities = {'fund_return'}
    roles = {}
    for candidate in candidates:
        candidate_roles = supported_roles(candidate)
        if evidence.is_fund_return_requirement(candidate):
            candidate_roles.add('fund_return')
        roles[candidate['project_requirement_id']] = candidate_roles
    covered = set().union(*roles.values()) if roles else set()
    compatible = [c for c in candidates if roles[c['project_requirement_id']] & identities]
    preserve = set(preserve_ids or []) if compatible else set()
    selected = ([c for c in candidates if (roles[c['project_requirement_id']] & identities) or c['project_requirement_id'] in preserve]
                if identities else list(candidates))
    # An initial certificate cannot establish post-DLP acceptance, even with a
    # reference hint. A separate final certificate in the packet remains eligible.
    if _exclude_post_dlp_acceptance(text):
        selected = [c for c in selected if not re.search(
            r'\bafter\s+(?:the\s+)?(?:dlp|defects?\s+liability)|\bpost[ -]dlp\b',
            str(c.get('requirement_name') or ''), re.I)]
        compatible = [c for c in compatible if c in selected]
    missing = sorted(identities - covered)
    return selected, {'detected_identities': sorted(identities),
                      'eligible_count': len(candidates), 'compatible_count': len(compatible),
                      'missing_identities': missing,
                      'status': ('missing_compatible_requirement' if identities and not compatible
                                 else 'partial_type_coverage' if missing else 'compatible' if identities else 'identity_unestablished')}
