import re
import unicodedata
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from app.services import document_compliance_rule_engine as rule_engine
from app.services.document_destination_check import lgu_expected_variants


FIELD_ALIASES = {
    'project_title': [
        'project',
        'project name',
        'project title',
        'project description',
        'program project activity',
        'purpose',
        'particulars',
    ],
    'project_code': [
        'project code',
        'project id',
        'project no',
        'project number',
        'source project code',
    ],
    'lgu': [
        'lgu',
        'local government unit',
        'city',
        'municipality',
        'province',
        'recipient lgu',
    ],
    'fiscal_year': [
        'fy',
        'fiscal year',
        'gaa year',
        'chargeable against',
        'funding year',
    ],
    'amount': [
        'amount',
        'allocation',
        'project cost',
        'credited amount',
        'amount credited',
        'fund transfer',
        'financial assistance',
    ],
    'reference_number': [
        'or no',
        'o r no',
        'official receipt no',
        'receipt no',
        'invoice no',
        'billing no',
        'check no',
        'sord no',
        'ada no',
        'ada number',
        'authority to debit account',
        'nca no',
        'nca number',
        'nta no',
        'nta number',
        'reference no',
        'reference number',
    ],
    'date': ['date', 'date prepared', 'prepared date', 'document date', 'date issued', 'issued on', 'received on'],
    'signatory': ['signed by', 'approved by', 'certified by', 'prepared by'],
    'office': ['office', 'agency', 'department', 'bureau'],
    'subject': ['subject', 'title', 're'],
    'location': ['location', 'barangay', 'city', 'municipality', 'province'],
    'requirement_type': [
        'requirement',
        'requirement type',
        'documentary requirement',
        'documentary requirement type',
        'document type',
        'nadai',
        'nadai certification',
        'notice of authority to debit account issued',
        'authority to debit account',
        'proof of transfer',
        'trust fund',
        'fund receipt',
        'notice of cash allocation',
        'official receipt',
        'receipt',
        'invoice',
        'billing',
        'liquidation',
        'sord',
    ],
    'vendor_or_payee': ['payee', 'vendor', 'supplier', 'received from', 'paid to', 'merchant'],
}

OCR_CORRECTIONS = {
    'bifian': 'binan',
    'biiian': 'binan',
    'biflan': 'binan',
    'binan': 'binan',
    'bman': 'binan',
    'nadai1': 'nadai',
    'nada1': 'nadai',
    'nadal': 'nadai',
    'lguu': 'lgu',
    'arnount': 'amount',
    'arnounts': 'amounts',
    'fiscalyear': 'fiscal year',
    'gaa': 'gaa',
    '0ffice': 'office',
}

NADAI_PROFILE = {
    'id': 'nadai_fund_transfer',
    'label': 'NADAI / fund transfer',
    'required_fields': ['lgu', 'fiscal_year', 'amount', 'reference_number'],
    'advisory_fields': ['project_title', 'date', 'office', 'signatory', 'location'],
    'strict_fields': ['reference_number', 'fiscal_year', 'amount'],
}

OFFICIAL_RECEIPT_PROFILE = {
    'id': 'official_receipt',
    'label': 'Official receipt / financial receipt',
    'required_fields': ['date', 'amount', 'reference_number'],
    'advisory_fields': ['vendor_or_payee', 'lgu', 'location'],
    'strict_fields': ['reference_number'],
}

BILLING_PACKAGE_PROFILE = {
    'id': 'billing_package',
    'label': 'Billing / liquidation package',
    'required_fields': ['date', 'amount', 'reference_number'],
    'advisory_fields': ['vendor_or_payee', 'lgu', 'project_title', 'location'],
    'strict_fields': ['reference_number'],
}

CERTIFICATION_PROFILE = {
    'id': 'certification',
    'label': 'Certification',
    'required_fields': ['lgu', 'date', 'signatory'],
    'advisory_fields': ['project_title', 'office', 'location'],
    'strict_fields': [],
}

RESOLUTION_PROFILE = {
    'id': 'resolution',
    'label': 'Resolution',
    'required_fields': ['reference_number', 'date', 'lgu'],
    'advisory_fields': ['project_title', 'signatory', 'office', 'location'],
    'strict_fields': ['reference_number'],
}

PROGRAM_OF_WORKS_PROFILE = {
    'id': 'program_of_works',
    'label': 'Program of Works',
    'required_fields': ['project_title', 'lgu', 'amount', 'signatory'],
    'advisory_fields': ['date', 'office', 'location'],
    'strict_fields': ['amount'],
}

DED_PROFILE = {
    'id': 'detailed_engineering_estimate',
    'label': 'Detailed Engineering Design / Estimate',
    'required_fields': ['project_title', 'lgu', 'amount'],
    'advisory_fields': ['date', 'signatory', 'office', 'location'],
    'strict_fields': ['amount'],
}

PROGRESS_REPORT_PROFILE = {
    'id': 'progress_report',
    'label': 'Progress / accomplishment report',
    'required_fields': ['project_title', 'lgu', 'date'],
    'advisory_fields': ['signatory', 'office', 'amount', 'location'],
    'strict_fields': [],
}

FIELD_EVIDENCE_PROFILES = {
    NADAI_PROFILE['id']: NADAI_PROFILE,
    OFFICIAL_RECEIPT_PROFILE['id']: OFFICIAL_RECEIPT_PROFILE,
    BILLING_PACKAGE_PROFILE['id']: BILLING_PACKAGE_PROFILE,
    CERTIFICATION_PROFILE['id']: CERTIFICATION_PROFILE,
    RESOLUTION_PROFILE['id']: RESOLUTION_PROFILE,
    PROGRAM_OF_WORKS_PROFILE['id']: PROGRAM_OF_WORKS_PROFILE,
    DED_PROFILE['id']: DED_PROFILE,
    PROGRESS_REPORT_PROFILE['id']: PROGRESS_REPORT_PROFILE,
}

_FIELD_ZONE_COLLECTION_KEYS = (
    'field_zones',
    'field_locations',
    'expected_field_zones',
    'required_fields',
)

_FIELD_ZONE_ALIASES = {
    'amount_paid': 'amount',
    'allocated_amount': 'amount',
    'allocation': 'amount',
    'budget_amount': 'amount',
    'credited_amount': 'amount',
    'fund_transfer_amount': 'amount',
    'project_cost': 'amount',
    'total_amount': 'amount',
    'total_project_cost': 'amount',
    'fy': 'fiscal_year',
    'funding_year': 'fiscal_year',
    'gaa_year': 'fiscal_year',
    'lgu_name': 'lgu',
    'local_government_unit': 'lgu',
    'municipality': 'lgu',
    'project_code': 'project_code',
    'project_id': 'project_code',
    'project_no': 'project_code',
    'project_number': 'project_code',
    'or_no': 'reference_number',
    'or_number': 'reference_number',
    'official_receipt_no': 'reference_number',
    'official_receipt_number': 'reference_number',
    'receipt_no': 'reference_number',
    'receipt_number': 'reference_number',
    'reference': 'reference_number',
    'reference_no': 'reference_number',
    'resolution_no': 'reference_number',
    'resolution_number': 'reference_number',
    'project': 'project_title',
    'project_name': 'project_title',
    'project_description': 'project_title',
    'project_title': 'project_title',
    'prepared_by': 'signatory',
    'approved_by': 'signatory',
    'certified_by': 'signatory',
}

_STOPWORDS = {
    'a',
    'an',
    'and',
    'for',
    'in',
    'into',
    'of',
    'on',
    'or',
    'the',
    'to',
    'with',
}
_YEAR_RE = re.compile(
    r'(?:(?:fy|fiscal\s+year|gaa\s+year|gaa|funding\s+year|chargeable\s+against)\D{0,25})'
    r'(20\d{2})',
    re.IGNORECASE,
)
_ANY_YEAR_RE = re.compile(r'\b(20\d{2})\b')
_AMOUNT_RE = re.compile(
    r'(?:(?:php|p|\u20b1|peso(?:s)?)[\s_:.-]*)'
    r'([0-9][0-9,\s]*(?:\.\d{1,2})?)'
    r'|'
    r'([0-9][0-9,\s]*(?:\.\d{1,2})?)\s*(?:php|pesos?)',
    re.IGNORECASE,
)
_LABELED_AMOUNT_RE = re.compile(
    r'\b(?:amount\s+paid|total\s+amount|paid\s+amount|project\s+cost|'
    r'receipts\s+of\s+funds|total\s+receipts|total\s+available\s+funds|'
    r'amount|allocation|total|payment)\s*[:\-]?\s*'
    r'[_\s]*(?:(?:php|p|\u20b1|peso(?:s)?)[\s_:.-]*)?'
    r'([0-9][0-9,\s]*(?:\.\d{1,2})?)',
    re.IGNORECASE,
)
_REFERENCE_RE = re.compile(
    r'\b(ADA|NCA|NTA|LDDAP|SARO)\s*(?:NO\.?|NUMBER|#)?\s*[:#-]?\s*'
    r'([A-Z0-9][A-Z0-9\-\/]{3,})',
    re.IGNORECASE,
)
_RECEIPT_REFERENCE_RE = re.compile(
    r'\b(O\.?\s*R\.?|OR|OFFICIAL\s+RECEIPT|RECEIPT|INVOICE|BILLING|BILL|SORD|CHECK)'
    r'\s*(?:NO\.?|NUMBER|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9\-\/]{2,})',
    re.IGNORECASE,
)
_RESOLUTION_REFERENCE_RE = re.compile(
    r'\b(RESOLUTION|RES)\s*(?:NO\.?|NUMBER|#)?\s*[:#-]?\s*(\d{2,4}[A-Z0-9\-\/]{1,})',
    re.IGNORECASE,
)
_GENERIC_DOCUMENT_REFERENCE_RE = re.compile(
    r'\b(?:REFERENCE|REF\.?|DOCUMENT\s+NO\.?|CONTROL\s+NO\.?)'
    r'\s*(?:NO\.?|NUMBER|#)?\s*[:#-]?\s*'
    r'((?:CERT|DED|POW|PRG|PROG|REP|SORD|OR|ADA|NCA|NTA|RES)'
    r'[\s\-\/]*20\d{2}[\s\-\/]*[A-Z0-9]{2,})',
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r'\b(?:'
    r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
    r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    r'\s+\d{1,2},?\s+20\d{2}'
    r'|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
    r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    r'\s+20\d{2}'
    r'|\d{1,2}[/-]\d{1,2}[/-]20\d{2}'
    r'|20\d{2}[/-]\d{1,2}[/-]\d{1,2}'
    r')\b',
    re.IGNORECASE,
)
_LGU_LINE_RE = re.compile(
    r'\b(?:lgu|recipient\s+lgu|local\s+government\s+unit)\s*[:\-]\s*([^\n\r;]+)',
    re.IGNORECASE,
)
_LGU_NAME_RE = re.compile(
    r'\b((?:City|Municipality|Province)\s+of\s+[A-Za-zñÑ .\'-]{2,80}?)'
    r'(?=,?\s+Laguna\b|[\n\r;,.]|\s+FY\b|\s+Purpose\b|\s+Amount\b|$)'
    r'(?:,?\s+Laguna)?',
    re.IGNORECASE,
)
_SIGNATURE_BLOCK_RE = re.compile(
    r'(?m)^\s*([A-Z][A-Z .\'-]{4,80})\s*\r?\n'
    r'\s*([A-Za-z][A-Za-z .\'/-]{3,90})\s*\r?\n'
    r'\s*(?:Prepared|Reviewed|Approved|Certified|Noted)\s+by\b',
)
_SIGNATORY_TITLE_TERMS = (
    r'Municipal|City|Provincial|Local|Project|Monitoring|Budget|Planning|Treasurer|'
    r'Engineer|Officer|Chief|Executive|Mayor|Vice\s+Mayor|Accountant|Administrator|'
    r'Coordinator|Director'
)
_SIGNATURE_INLINE_BLOCK_RE = re.compile(
    r'\b([A-Z]{2,}(?:\s+[A-Z]\s*\.?)*\s+[A-Z]{2,}(?:\s+[A-Z]{2,})?)\s+'
    rf'(({_SIGNATORY_TITLE_TERMS})(?:\s+(?:{_SIGNATORY_TITLE_TERMS})){{0,4}})\s+'
    r'(?:Prepared|Reviewed|Approved|Certified|Noted)\s+by\b'
)


def extract_field_evidence(
    text,
    *,
    file_name=None,
    expected=None,
    evidence_type=None,
    profile_selection=None,
    checker_config=None,
    text_locations=None,
    extraction_metadata=None,
    provider_forms=None,
):
    """Extract field candidates and expected-value matches from document text."""
    expected = dict(expected or {})
    if checker_config is not None:
        cfg = dict(checker_config)
        field_zones = _field_zones_from_checker_config(cfg)
    else:
        cfg = {}
        profile_selection = profile_selection or {}
        field_zones = _field_zones_from_profile_selection(profile_selection)
    profile_selection = profile_selection or {}
    evidence_type = evidence_type or cfg.get('evidence_type') or rule_engine.evidence_type_from_profile_selection(profile_selection)
    profile = _profile_for_evidence_type(evidence_type)
    raw_text = str(text or '')
    corpus = '\n'.join(part for part in (file_name or '', raw_text) if part)
    normalized_corpus = normalize_text(corpus)
    label_value_candidates = _label_value_pair_candidates(corpus, expected, evidence_type)

    fields = {
        'requirement_type': _requirement_type_candidates(normalized_corpus, evidence_type),
        'lgu': _lgu_candidates(corpus, expected),
        'fiscal_year': _fiscal_year_candidates(corpus),
        'amount': _amount_candidates(corpus),
        'reference_number': _reference_number_candidates(corpus),
        'date': _date_candidates(corpus),
        'project_title': _project_title_candidates(corpus, expected),
        'project_code': [],
        'vendor_or_payee': _label_candidates(corpus, 'vendor_or_payee'),
        'signatory': _label_candidates(corpus, 'signatory'),
        'office': _label_candidates(corpus, 'office'),
        'subject': _label_candidates(corpus, 'subject'),
        'location': _label_candidates(corpus, 'location'),
    }
    for candidate in label_value_candidates:
        fields.setdefault(candidate.get('field'), []).append(candidate)
    if provider_forms:
        for form_item in provider_forms:
            if not isinstance(form_item, dict):
                continue
            k = (form_item.get('key') or '').strip().lower()
            v = (form_item.get('value') or '').strip()
            conf = float(form_item.get('confidence') or 0.0)
            if not k or not v or conf < 0.80:
                continue
            bbox = form_item.get('value_bbox') or form_item.get('bbox')
            if any(date_alias in k for date_alias in ('date', 'invoice_date', 'receipt_date', 'issued')):
                cand = _candidate('date', v, v, conf, 'Extracted from provider form key-value pair.', 'provider_form')
                cand['source'] = 'aws_textract'
                cand['provider'] = 'aws_textract'
                cand['bbox'] = bbox
                fields.setdefault('date', []).append(cand)
            elif any(amt_alias in k for amt_alias in ('amount', 'total', 'subtotal', 'net_amount')):
                normalized_amt = _normalize_amount(v)
                if normalized_amt is not None:
                    cand = _candidate('amount', v, normalized_amt, conf, 'Extracted from provider form key-value pair.', 'provider_form')
                    cand['source'] = 'aws_textract'
                    cand['provider'] = 'aws_textract'
                    cand['bbox'] = bbox
                    fields.setdefault('amount', []).append(cand)
    if text_locations:
        fields = _enrich_candidates_with_text_locations(fields, text_locations)
    fields = {field: _dedupe_candidates(candidates) for field, candidates in fields.items()}
    fields = {
        field: {
            'best': _best_candidate(candidates),
            'candidates': candidates[:8],
        }
        for field, candidates in fields.items()
        if candidates
    }

    matches = _build_matches(fields, expected)
    extractors = (extraction_metadata or {}).get('extractors') or []
    is_ocr_fallback = rule_engine.is_ocr_fallback(extraction_metadata)

    return {
        'profile': profile,
        'evidence_type': evidence_type,
        'fields': fields,
        'matches': matches,
        'field_zones': field_zones,
        'is_ocr_fallback': is_ocr_fallback,
        'aliases_version': 'field_aliases_2026.05.24',
        'ocr_corrections_version': 'ocr_corrections_2026.05.23',
    }


def build_profile_findings(field_evidence):
    """Build deterministic findings from extracted fields for active profiles."""
    if not field_evidence:
        return []
    profile = field_evidence.get('profile') or {}
    if profile.get('id') not in FIELD_EVIDENCE_PROFILES:
        return []

    fields = field_evidence.get('fields') or {}
    matches = field_evidence.get('matches') or {}
    field_zones = field_evidence.get('field_zones') or {}
    findings = []

    is_ocr_fallback = field_evidence.get('is_ocr_fallback', False)

    for field in profile.get('required_fields') or []:
        best = (fields.get(field) or {}).get('best')
        match = matches.get(field) or {}
        if not best:
            if field == 'signatory':
                severity = 'needs_verification'
                detail = 'Signatory or signature block could not be automatically confirmed. Requires manual reviewer verification.'
            elif is_ocr_fallback:
                severity = 'needs_verification'
                detail = _missing_detail(profile, field) + ' (Unverified due to OCR scan quality)'
            else:
                severity = 'blocker'
                detail = _missing_detail(profile, field)

            findings.append(_field_finding(
                field,
                'missing',
                severity,
                f'Required {profile.get("label", "document")} field was not found: {_field_label(field)}.',
                detail,
                best=best,
                zone=field_zones.get(field),
            ))
            continue
        if profile.get('id') == NADAI_PROFILE['id'] and match.get('status') == 'mismatch':
            detail = _mismatch_detail(field, match)
            findings.append(_field_finding(
                field,
                'mismatch',
                'blocker',
                f'NADAI/fund-transfer field does not match the selected project: {_field_label(field)}.',
                detail,
                match=match,
                best=best,
                zone=field_zones.get(field),
            ))
            continue

        severity = _required_mismatch_severity(profile, field, match)
        if severity:
            findings.append(_field_finding(
                field,
                'mismatch',
                severity,
                f'{profile.get("label", "Document")} field does not match the selected project: {_field_label(field)}.',
                _mismatch_detail(field, match),
                match=match,
                best=best,
                zone=field_zones.get(field),
            ))

    project_match = matches.get('project_title') or {}
    has_project_mismatch_finding = any(item.get('id') == 'field_mismatch:project_title' for item in findings)
    if project_match.get('status') == 'mismatch' and not has_project_mismatch_finding:
        findings.append(_field_finding(
            'project_title',
            'mismatch',
            'warning',
            'Project title or purpose only weakly matches the selected project.',
            _mismatch_detail('project_title', project_match),
            match=project_match,
            best=(fields.get('project_title') or {}).get('best'),
            zone=field_zones.get('project_title'),
        ))
    return findings


def _required_mismatch_severity(profile, field, match):
    if match.get('status') != 'mismatch':
        return None

    profile_id = profile.get('id')
    if profile_id in {OFFICIAL_RECEIPT_PROFILE['id'], BILLING_PACKAGE_PROFILE['id']}:
        return 'blocker' if field == 'reference_number' else None

    blocker_fields_by_profile = {
        CERTIFICATION_PROFILE['id']: {'lgu'},
        RESOLUTION_PROFILE['id']: {'reference_number', 'lgu'},
        PROGRAM_OF_WORKS_PROFILE['id']: {'project_title', 'lgu', 'amount'},
        DED_PROFILE['id']: {'project_title', 'lgu', 'amount'},
        PROGRESS_REPORT_PROFILE['id']: {'project_title', 'lgu'},
    }
    if field in blocker_fields_by_profile.get(profile_id, set()):
        return 'blocker'
    if field in (profile.get('strict_fields') or []):
        return 'blocker'
    return None


def normalize_text(value):
    stripped = ''.join(
        char for char in unicodedata.normalize('NFKD', str(value or ''))
        if not unicodedata.combining(char)
    )
    lowered = stripped.lower()
    lowered = re.sub(r'[^a-z0-9]+', ' ', lowered)
    tokens = [OCR_CORRECTIONS.get(token, token) for token in lowered.split()]
    return re.sub(r'\s+', ' ', ' '.join(tokens)).strip()


def _profile_for_evidence_type(evidence_type):
    normalized = rule_engine.normalize_evidence_type(evidence_type)
    if normalized in FIELD_EVIDENCE_PROFILES:
        return dict(FIELD_EVIDENCE_PROFILES[normalized])
    return {
        'id': normalized,
        'label': normalized.replace('_', ' '),
        'required_fields': [],
        'advisory_fields': [],
        'strict_fields': [],
    }


def _field_zones_from_checker_config(checker_config):
    if not isinstance(checker_config, dict):
        return {}
    zones = {}
    format_profile = checker_config.get('format_profile') or {}
    for key in _FIELD_ZONE_COLLECTION_KEYS:
        source_items = format_profile.get(key) if isinstance(format_profile, dict) else None
        if not source_items and key in checker_config:
            source_items = checker_config.get(key)
        for item in _zone_items(source_items):
            field = _zone_field(item)
            if not field or field in zones:
                continue
            bbox = item.get('bbox') if item.get('bbox') is not None else item.get('expected_bbox')
            if bbox is None:
                continue
            zones[field] = dict(item)
    return zones


def _field_zones_from_profile_selection(profile_selection):
    zones = {}
    for profile_entry in _profile_entries(profile_selection):
        metadata = profile_entry.get('profile_metadata') or {}
        if not isinstance(metadata, dict):
            continue
        format_profile = metadata.get('format_profile') or {}
        if not isinstance(format_profile, dict):
            continue
        reference_uri = (
            profile_entry.get('reference_uri')
            or metadata.get('reference_uri')
            or format_profile.get('reference_uri')
        )
        for key in _FIELD_ZONE_COLLECTION_KEYS:
            for item in _zone_items(format_profile.get(key)):
                field = _zone_field(item)
                if not field or field in zones:
                    continue
                bbox = item.get('bbox') if item.get('bbox') is not None else item.get('expected_bbox')
                if bbox is None:
                    continue
                zone = dict(item)
                if reference_uri and not zone.get('reference_uri'):
                    zone['reference_uri'] = reference_uri
                zones[field] = zone
    return zones


def _enrich_candidates_with_text_locations(fields, text_locations):
    locations = _clean_text_locations(text_locations)
    if not locations:
        return fields

    enriched_fields = {}
    for field, candidates in (fields or {}).items():
        enriched_candidates = []
        for candidate in candidates or []:
            if not isinstance(candidate, dict):
                enriched_candidates.append(candidate)
                continue
            if candidate.get('bbox'):
                enriched_candidates.append(candidate)
                continue
            location = _find_text_location(locations, candidate.get('matched_text'))
            if location is None:
                location = _find_text_location(locations, candidate.get('normalized_value'))
            if location is None:
                enriched_candidates.append(candidate)
                continue
            enriched_candidates.append({
                **candidate,
                'page': location.get('page') or candidate.get('page') or 1,
                'bbox': location.get('bbox'),
                'bbox_type': location.get('bbox_type') or 'detected_text',
                'source': 'ocr_text_location',
            })
        enriched_fields[field] = enriched_candidates
    return enriched_fields


def _clean_text_locations(text_locations):
    cleaned = []
    if not isinstance(text_locations, list):
        return cleaned
    for item in text_locations:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()
        bbox = item.get('bbox')
        if not text or not isinstance(bbox, dict):
            continue
        normalized_text = _normalize_location_token(text)
        if not normalized_text:
            continue
        cleaned.append({
            **item,
            'page': _safe_int(item.get('page')) or 1,
            'bbox': bbox,
            'bbox_type': item.get('bbox_type') or 'detected_text',
            'normalized_text': normalized_text,
        })
    return cleaned


def _find_text_location(text_locations, matched_text):
    tokens = [
        _normalize_location_token(token)
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", str(matched_text or ''))
    ]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None

    for index, location in enumerate(text_locations):
        if location.get('normalized_text') != tokens[0]:
            continue
        group = text_locations[index:index + len(tokens)]
        if len(group) != len(tokens):
            continue
        if any(item.get('page') != location.get('page') for item in group):
            continue
        if [item.get('normalized_text') for item in group] != tokens:
            continue
        segment = _best_text_location_segment(group)
        bbox = _union_normalized_bboxes(item.get('bbox') for item in segment)
        if not bbox:
            continue
        return {
            'page': location.get('page') or 1,
            'bbox': bbox,
            'bbox_type': location.get('bbox_type') or 'detected_text',
        }
    return None


def _best_text_location_segment(group):
    segments = []
    current = []
    for item in group:
        if current and _starts_new_text_line(current[-1], item):
            segments.append(current)
            current = [item]
        else:
            current.append(item)
    if current:
        segments.append(current)
    if not segments:
        return group
    return max(
        segments,
        key=lambda segment: (
            len(segment),
            _union_area(_union_normalized_bboxes(item.get('bbox') for item in segment)),
        ),
    )


def _starts_new_text_line(previous, current):
    previous_bbox = previous.get('bbox') if isinstance(previous, dict) else None
    current_bbox = current.get('bbox') if isinstance(current, dict) else None
    if not isinstance(previous_bbox, dict) or not isinstance(current_bbox, dict):
        return False
    try:
        previous_x = float(previous_bbox.get('x'))
        previous_y = float(previous_bbox.get('y'))
        previous_height = float(previous_bbox.get('height'))
        current_x = float(current_bbox.get('x'))
        current_y = float(current_bbox.get('y'))
        current_height = float(current_bbox.get('height'))
    except (TypeError, ValueError):
        return False
    line_height = max(previous_height, current_height, 0.001)
    return current_x < previous_x and abs(current_y - previous_y) >= line_height * 0.45


def _union_area(bbox):
    if not bbox:
        return 0.0
    return float(bbox.get('width') or 0) * float(bbox.get('height') or 0)


def _union_normalized_bboxes(bboxes):
    normalized = []
    for bbox in bboxes:
        if not isinstance(bbox, dict):
            return None
        try:
            x = float(bbox.get('x'))
            y = float(bbox.get('y'))
            width = float(bbox.get('width'))
            height = float(bbox.get('height'))
        except (TypeError, ValueError):
            return None
        normalized.append((x, y, x + width, y + height))
    if not normalized:
        return None
    left = min(item[0] for item in normalized)
    top = min(item[1] for item in normalized)
    right = max(item[2] for item in normalized)
    bottom = max(item[3] for item in normalized)
    return {
        'x': round(max(0.0, min(1.0, left)), 4),
        'y': round(max(0.0, min(1.0, top)), 4),
        'width': round(max(0.0, min(1.0, right) - max(0.0, min(1.0, left))), 4),
        'height': round(max(0.0, min(1.0, bottom) - max(0.0, min(1.0, top))), 4),
    }


def _normalize_location_token(value):
    return re.sub(r'[^a-z0-9]+', '', normalize_text(value))


def _profile_entries(profile_selection):
    if not isinstance(profile_selection, dict):
        return []
    entries = []
    for key in ('used_profiles', 'current_profiles', 'profiles'):
        value = profile_selection.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    if profile_selection.get('profile_metadata'):
        entries.append(profile_selection)
    return entries


def _zone_items(value):
    if isinstance(value, dict):
        items = []
        for field, zone in value.items():
            if isinstance(zone, dict):
                item = dict(zone)
                item.setdefault('field', field)
                items.append(item)
        return items
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _zone_field(item):
    for key in ('field', 'field_id', 'field_name', 'id', 'name', 'label'):
        field = _normalize_field_key(item.get(key))
        if field:
            return field
    return None


def _normalize_field_key(value):
    normalized = normalize_text(str(value or '').replace('_', ' '))
    if not normalized:
        return None
    key = normalized.replace(' ', '_')
    key = _FIELD_ZONE_ALIASES.get(key, key)
    return key if key in FIELD_ALIASES or key in {'fiscal_year', 'amount'} else None


def _requirement_type_candidates(normalized_corpus, evidence_type):
    candidates = []
    if rule_engine.normalize_evidence_type(evidence_type) == NADAI_PROFILE['id']:
        confidence = 0.95 if _contains_any(normalized_corpus, FIELD_ALIASES['requirement_type']) else 0.82
        candidates.append(_candidate(
            'requirement_type',
            'NADAI / fund transfer',
            NADAI_PROFILE['id'],
            confidence,
            'Requirement metadata or document text matches NADAI/fund-transfer aliases.',
            'inferred',
        ))
    elif rule_engine.normalize_evidence_type(evidence_type) in {'official_receipt', 'billing_package'}:
        normalized_type = rule_engine.normalize_evidence_type(evidence_type)
        profile = FIELD_EVIDENCE_PROFILES[normalized_type]
        candidates.append(_candidate(
            'requirement_type',
            profile['label'],
            normalized_type,
            0.9 if _contains_any(normalized_corpus, FIELD_ALIASES['requirement_type']) else 0.75,
            f'Requirement metadata or document text matches {profile["label"]} aliases.',
            'inferred',
        ))
    return candidates


def _lgu_candidates(corpus, expected):
    candidates = []
    for match in _LGU_LINE_RE.finditer(corpus):
        candidates.append(_candidate(
            'lgu',
            _clean_lgu_text(match.group(1)),
            _clean_lgu_text(match.group(1)),
            0.86,
            'Matched an LGU label.',
            'label',
        ))
    for match in _LGU_NAME_RE.finditer(corpus):
        candidates.append(_candidate(
            'lgu',
            _clean_lgu_text(match.group(1)),
            _clean_lgu_text(match.group(1)),
            0.82,
            'Matched a city/municipality/province phrase.',
            'alias',
        ))

    expected_variants = _lgu_expected_variants(expected)
    normalized = normalize_text(corpus)
    for variant in expected_variants:
        if normalize_text(variant) and normalize_text(variant) in normalized:
            candidates.append(_candidate(
                'lgu',
                variant,
                expected.get('lgu_name') or variant,
                0.96,
                'Matched the selected LGU or an accepted LGU alias.',
                'exact',
            ))
    return _dedupe_candidates(candidates)


def _fiscal_year_candidates(corpus):
    candidates = []
    for match in _YEAR_RE.finditer(corpus):
        candidates.append(_candidate(
            'fiscal_year',
            match.group(0),
            int(match.group(1)),
            0.96,
            'Matched a fiscal-year/GAA-year context phrase.',
            'strict_context',
        ))
    for match in _ANY_YEAR_RE.finditer(corpus):
        year = int(match.group(1))
        if any((item.get('normalized_value') == year) for item in candidates):
            continue
        candidates.append(_candidate(
            'fiscal_year',
            match.group(0),
            year,
            0.68,
            'Matched a standalone year; reviewer should confirm fiscal-year context.',
            'advisory',
        ))
    return candidates


def _amount_candidates(corpus):
    candidates = []
    for match in _LABELED_AMOUNT_RE.finditer(corpus):
        normalized = _normalize_amount(match.group(1))
        if normalized is None:
            continue
        candidates.append(_candidate(
            'amount',
            match.group(0),
            normalized,
            0.95,
            'Matched a labeled amount expression.',
            'label',
        ))
    for match in _AMOUNT_RE.finditer(corpus):
        raw_amount = match.group(1) or match.group(2)
        normalized = _normalize_amount(raw_amount)
        if normalized is None:
            continue
        candidates.append(_candidate(
            'amount',
            match.group(0),
            normalized,
            0.97,
            'Matched a peso amount or credited amount expression.',
            'numeric_exact',
        ))
    return _dedupe_candidates(candidates)


def _reference_number_candidates(corpus):
    candidates = []
    for match in _REFERENCE_RE.finditer(corpus.upper()):
        prefix = match.group(1).upper()
        number = match.group(2).strip().upper().rstrip('.,;:')
        if not re.search(r'\d', number):
            continue
        normalized = number if number.startswith(prefix) else f'{prefix}-{number}'
        candidates.append(_candidate(
            'reference_number',
            match.group(0).strip(),
            normalized,
            0.99,
            f'Matched a strict {prefix} reference-number pattern.',
            'strict_pattern',
        ))
    for match in _RECEIPT_REFERENCE_RE.finditer(corpus.upper()):
        prefix = _normalize_reference_prefix(match.group(1))
        number = match.group(2).strip().upper().rstrip('.,;:')
        if not re.search(r'\d', number):
            continue
        normalized = _receipt_reference_value(prefix, number)
        candidates.append(_candidate(
            'reference_number',
            match.group(0).strip(),
            normalized,
            0.96,
            f'Matched a strict {prefix} receipt/billing reference pattern.',
            'strict_pattern',
        ))
    for match in _RESOLUTION_REFERENCE_RE.finditer(corpus.upper()):
        number = match.group(2).strip().upper().rstrip('.,;:')
        if not re.search(r'\d', number):
            continue
        candidates.append(_candidate(
            'reference_number',
            match.group(0).strip(),
            _document_reference_value('RESOLUTION', number),
            0.95,
            'Matched a strict resolution reference-number pattern.',
            'strict_pattern',
        ))
    for match in _GENERIC_DOCUMENT_REFERENCE_RE.finditer(corpus.upper()):
        number = _normalize_reference(match.group(1)).rstrip('.,;:')
        if not re.search(r'\d', number):
            continue
        candidates.append(_candidate(
            'reference_number',
            match.group(0).strip(),
            number,
            0.92,
            'Matched a controlled generic document reference-number pattern.',
            'generic_pattern',
        ))
    return _dedupe_candidates(candidates)


def _date_candidates(corpus):
    return [
        _candidate('date', match.group(0), match.group(0), 0.82, 'Matched a date expression.', 'pattern')
        for match in _DATE_RE.finditer(corpus)
    ]


def _label_value_pair_candidates(corpus, expected, evidence_type):
    candidates = []
    for pair in _extract_label_value_pairs(corpus):
        candidate = _candidate_from_label_value_pair(pair, expected, evidence_type)
        if candidate:
            candidates.append(candidate)
    return _dedupe_candidates(candidates)


def _extract_label_value_pairs(corpus):
    raw_lines = [str(line or '').strip() for line in str(corpus or '').splitlines()]
    lines = [line for line in raw_lines if line]
    pairs = []

    for index, line in enumerate(lines):
        pairs.extend(_pairs_from_single_line(line, 'table_label_value'))

        header_cells = _split_table_cells(line)
        if len(header_cells) <= 1 or index + 1 >= len(lines):
            continue
        header_fields = [_field_from_label(cell) for cell in header_cells]
        if not all(header_fields):
            continue
        value_cells = _split_table_cells(lines[index + 1])
        if len(value_cells) != len(header_fields):
            continue
        for field, label, value in zip(header_fields, header_cells, value_cells):
            if _field_from_label(value):
                continue
            pairs.append({
                'field': field,
                'label': label,
                'value': value,
                'mode': 'stacked_table_header',
            })

    for index, line in enumerate(lines[:-1]):
        if not _is_label_only_line(line):
            continue
        field = _field_from_label(line)
        next_line = lines[index + 1]
        if _is_label_only_line(next_line):
            continue
        if _pairs_from_single_line(next_line, 'nested_label_value_probe'):
            continue
        value = _trim_table_label_value(next_line)
        if value:
            pairs.append({
                'field': field,
                'label': line,
                'value': value,
                'mode': 'stacked_label_value',
            })

    return pairs


def _pairs_from_single_line(line, mode):
    cleaned = str(line or '').strip()
    if not cleaned:
        return []

    pairs = []
    cells = _split_table_cells(cleaned)
    if len(cells) >= 2:
        field = None if all(_field_from_label(cell) for cell in cells) else _field_from_label(cells[0])
        if field:
            value = _trim_table_label_value(' '.join(cells[1:]))
            if value:
                pairs.append({
                    'field': field,
                    'label': cells[0],
                    'value': value,
                    'mode': mode,
                })

    labeled_match = re.match(r'^\s*([^:\-]{2,80}?)\s*[:\-]\s*(.+?)\s*$', cleaned)
    if labeled_match:
        field = _field_from_label(labeled_match.group(1))
        value = _trim_table_label_value(labeled_match.group(2))
        if field and value:
            pairs.append({
                'field': field,
                'label': labeled_match.group(1),
                'value': value,
                'mode': 'inline_label_value',
            })

    start_match = _line_start_label_value(cleaned)
    if start_match:
        pairs.append({**start_match, 'mode': 'line_start_label_value'})

    return pairs


def _split_table_cells(line):
    return [
        cell.strip(' .,:;')
        for cell in re.split(r'\s*\|\s*|\t+|\s{2,}', str(line or '').strip())
        if cell.strip(' .,:;')
    ]


def _line_start_label_value(line):
    for field, alias in _known_label_aliases():
        pattern = re.compile(rf'^\s*{_alias_pattern(alias)}\s+(.+?)\s*$', re.IGNORECASE)
        match = pattern.match(line)
        if not match:
            continue
        value = str(line).strip() if field == 'fiscal_year' and normalize_text(alias) == 'fy' else match.group(1)
        value = _trim_table_label_value(value)
        if _plausible_label_value(field, value):
            return {
                'field': field,
                'label': alias,
                'value': value,
            }
    return None


def _is_label_only_line(line):
    cleaned = str(line or '').strip(' .,:;')
    return bool(cleaned and _field_from_label(cleaned))


def _field_from_label(label):
    normalized = normalize_text(str(label or '').replace('_', ' '))
    if not normalized:
        return None
    key = normalized.replace(' ', '_')
    if key in _FIELD_ZONE_ALIASES:
        return _FIELD_ZONE_ALIASES[key]
    for field, alias in _known_label_aliases():
        if normalized == normalize_text(alias):
            return field
    return None


def _known_label_aliases():
    aliases = []
    for field, terms in FIELD_ALIASES.items():
        for term in terms:
            aliases.append((field, term))
    aliases.extend((value, key.replace('_', ' ')) for key, value in _FIELD_ZONE_ALIASES.items())
    aliases.sort(key=lambda item: len(normalize_text(item[1])), reverse=True)
    return aliases


def _alias_pattern(alias):
    return r'\s+'.join(re.escape(part) for part in normalize_text(alias).split())


def _candidate_from_label_value_pair(pair, expected, evidence_type):
    field = pair.get('field')
    raw_value = _trim_table_label_value(pair.get('value'))
    if not field or not raw_value or _field_from_label(raw_value):
        return None
    if field == 'project_title' and not _is_explicit_project_label(pair.get('label')):
        return None

    normalized_value, matched_text = _normalize_label_value(field, raw_value, evidence_type)
    if normalized_value in (None, '') or not matched_text:
        return None

    confidence = _label_value_confidence(field, raw_value, expected, pair.get('mode'))
    return _candidate(
        field,
        matched_text,
        normalized_value,
        confidence,
        f'Matched {_field_label(field)} from a table or form label-value pair.',
        pair.get('mode') or 'label_value',
    )


def _normalize_label_value(field, value, evidence_type):
    cleaned = str(value or '').strip(' .,:;')
    if field == 'fiscal_year':
        match = _YEAR_RE.search(cleaned) or _ANY_YEAR_RE.search(cleaned)
        if not match:
            return None, None
        year = match.group(1)
        return int(year), match.group(0).strip()

    if field == 'amount':
        match = _AMOUNT_RE.search(cleaned)
        amount_text = match.group(0).strip() if match else cleaned
        raw_amount = (match.group(1) or match.group(2)) if match else cleaned
        amount = _normalize_amount(raw_amount)
        if amount is None:
            return None, None
        return amount, amount_text

    if field == 'reference_number':
        normalized = _reference_from_label_value(cleaned)
        return (normalized, cleaned) if normalized else (None, None)

    if field == 'date':
        match = _DATE_RE.search(cleaned)
        if not match:
            return None, None
        return match.group(0).strip(), match.group(0).strip()

    if field == 'lgu':
        value = _clean_lgu_text(cleaned)
        return (value, value) if value else (None, None)

    if field == 'requirement_type':
        normalized = _requirement_type_from_label_value(cleaned, evidence_type)
        return (normalized, cleaned) if normalized else (None, None)

    if field in {'project_title', 'project_code', 'vendor_or_payee', 'signatory', 'office', 'subject', 'location'}:
        return cleaned, cleaned

    return cleaned, cleaned


def _reference_from_label_value(value):
    value = str(value or '').strip().upper()
    if not re.search(r'\d', value):
        return None
    for pattern in (_REFERENCE_RE, _RECEIPT_REFERENCE_RE, _RESOLUTION_REFERENCE_RE, _GENERIC_DOCUMENT_REFERENCE_RE):
        match = pattern.search(value)
        if not match:
            continue
        if pattern is _REFERENCE_RE:
            prefix = match.group(1).upper()
            number = match.group(2).strip().upper().rstrip('.,;:')
            return number if number.startswith(prefix) else f'{prefix}-{number}'
        if pattern is _RECEIPT_REFERENCE_RE:
            return _receipt_reference_value(_normalize_reference_prefix(match.group(1)), match.group(2))
        if pattern is _RESOLUTION_REFERENCE_RE:
            return _document_reference_value('RESOLUTION', match.group(2))
        return _normalize_reference(match.group(1)).rstrip('.,;:')
    return _normalize_reference(value)


def _requirement_type_from_label_value(value, evidence_type):
    normalized_value = normalize_text(value)
    normalized_type = rule_engine.normalize_evidence_type(evidence_type)
    if normalized_type in FIELD_EVIDENCE_PROFILES and _contains_any(normalized_value, FIELD_ALIASES['requirement_type']):
        return normalized_type
    if 'nadai' in normalized_value or 'authority to debit account' in normalized_value:
        return NADAI_PROFILE['id']
    if 'receipt' in normalized_value or 'invoice' in normalized_value:
        return OFFICIAL_RECEIPT_PROFILE['id']
    if 'billing' in normalized_value or 'liquidation' in normalized_value or 'sord' in normalized_value:
        return BILLING_PACKAGE_PROFILE['id']
    if 'resolution' in normalized_value:
        return RESOLUTION_PROFILE['id']
    if 'program of works' in normalized_value:
        return PROGRAM_OF_WORKS_PROFILE['id']
    if 'engineering' in normalized_value or 'estimate' in normalized_value:
        return DED_PROFILE['id']
    if 'progress' in normalized_value or 'accomplishment' in normalized_value:
        return PROGRESS_REPORT_PROFILE['id']
    if 'certification' in normalized_value:
        return CERTIFICATION_PROFILE['id']
    return None


def _label_value_confidence(field, value, expected, mode):
    if field == 'project_title' and expected.get('project_name'):
        score = _token_set_confidence(expected.get('project_name'), value)
        return max(0.72, min(0.985, score))
    if mode in {'stacked_label_value', 'stacked_table_header'}:
        return 0.975
    if field in {'fiscal_year', 'amount', 'reference_number', 'date', 'project_code'}:
        return 0.985
    if field == 'requirement_type':
        return 0.96
    return 0.88


def _plausible_label_value(field, value):
    cleaned = str(value or '').strip()
    if not cleaned:
        return False
    if cleaned.startswith(('/', ':', '-')):
        return False
    if field == 'fiscal_year':
        return bool(_ANY_YEAR_RE.search(cleaned))
    if field == 'amount':
        return bool(_AMOUNT_RE.search(cleaned) or re.search(r'\d', cleaned))
    if field == 'reference_number':
        return bool(re.search(r'\d', cleaned))
    if field == 'date':
        return bool(_DATE_RE.search(cleaned))
    if field == 'project_code':
        return bool(re.search(r'\d', cleaned) and re.search(r'[A-Za-z]', cleaned))
    if field == 'lgu':
        return not normalize_text(cleaned).startswith('of ')
    if field == 'project_title':
        return len(cleaned) >= 8
    return True


def _is_explicit_project_label(label):
    return normalize_text(label) in {
        'project',
        'project name',
        'project title',
        'project description',
        'program project activity',
    }


def _project_title_candidates(corpus, expected):
    expected_title = str(expected.get('project_name') or '').strip()
    if not expected_title:
        return []

    normalized = normalize_text(corpus)
    expected_normalized = normalize_text(expected_title)
    candidates = []
    if expected_normalized and expected_normalized in normalized:
        candidates.append(_candidate(
            'project_title',
            expected_title,
            expected_title,
            0.98,
            'Matched the selected project title exactly after normalization.',
            'exact',
        ))

    for segment in _candidate_segments(corpus):
        score = _token_set_confidence(expected_title, segment)
        if score < 0.58:
            continue
        candidates.append(_candidate(
            'project_title',
            segment.strip(),
            expected_title,
            min(0.94, score),
            'Controlled project-title fuzzy match using token overlap and word-order tolerance.',
            'fuzzy',
        ))
    return _dedupe_candidates(candidates)


def _label_candidates(corpus, field):
    aliases = FIELD_ALIASES.get(field) or []
    candidates = []
    for alias in aliases:
        pattern = re.compile(rf'\b{re.escape(alias)}\b\s*[:\-]\s*([^\n\r;]+)', re.IGNORECASE)
        for match in pattern.finditer(corpus):
            value = match.group(1).strip(' .,:;')
            if value:
                candidates.append(_candidate(field, value, value, 0.74, f'Matched label alias: {alias}.', 'label'))
    if field == 'vendor_or_payee':
        table_label_pattern = re.compile(
            r'\b(?:payee\s*/\s*vendor|vendor\s*/\s*payee|paid\s+to|received\s+from)\b\s+([^\n\r;]+)',
            re.IGNORECASE,
        )
        for match in table_label_pattern.finditer(corpus):
            value = _trim_table_label_value(match.group(1)).strip(' .,:;')
            if value:
                candidates.append(_candidate(
                    field,
                    value,
                    value,
                    0.7,
                    'Matched table-style payee/vendor label without a colon.',
                    'table_label',
                ))
    if field == 'signatory':
        for match in _SIGNATURE_BLOCK_RE.finditer(corpus):
            value = _clean_signatory_block_value(match.group(1), match.group(2))
            if value:
                candidates.append(_candidate(
                    field,
                    value,
                    value,
                    0.78,
                    'Matched a signature block with the signer name above the role label.',
                    'signature_block',
                ))
        for match in _SIGNATURE_INLINE_BLOCK_RE.finditer(corpus):
            value = _clean_signatory_block_value(match.group(1), match.group(2))
            if value:
                candidates.append(_candidate(
                    field,
                    value,
                    value,
                    0.76,
                    'Matched a signature block after PDF text extraction removed line breaks.',
                    'signature_block_inline',
                ))
    return _dedupe_candidates(candidates)


def _clean_signatory_block_value(name, title):
    cleaned_name = re.sub(r'\s+', ' ', str(name or '')).strip(' .,:;')
    cleaned_title = re.sub(r'\s+', ' ', str(title or '')).strip(' .,:;')
    if not cleaned_name or not cleaned_title:
        return ''
    if normalize_text(cleaned_name) in {'republic of the philippines', 'certification'}:
        return ''
    return f'{cleaned_name}, {cleaned_title}'


def _trim_table_label_value(value):
    cleaned = str(value or '').strip(' .,:;')
    if not cleaned:
        return ''
    stop_pattern = re.compile(
        r'\b(?:total\s+amount|amount\s+paid|date\s+prepared|date\s+issued|reference\s+no|'
        r'particulars|remarks|project\s+code|project\s+title|project\s+name|'
        r'project\s+(?:acquisition|construction|rehabilitation|improvement|development)|'
        r'fiscal\s+year)\b',
        re.IGNORECASE,
    )
    stop = stop_pattern.search(cleaned)
    if stop:
        cleaned = cleaned[:stop.start()]
    return cleaned.strip(' .,:;')


def _build_matches(fields, expected):
    expected_fields = {
        'project_title': expected.get('project_name'),
        'project_code': expected.get('source_project_code') or expected.get('project_code'),
        'lgu': expected.get('lgu_name') or expected.get('lgu_municipality'),
        'fiscal_year': expected.get('fiscal_year'),
        'amount': expected.get('budget_amount') or expected.get('amount'),
        'reference_number': expected.get('reference_number'),
    }
    matches = {}
    for field, expected_value in expected_fields.items():
        best = (fields.get(field) or {}).get('best')
        if expected_value in (None, ''):
            if best:
                matches[field] = {
                    'status': 'found',
                    'expected': None,
                    'actual': best.get('normalized_value'),
                    'confidence': best.get('confidence'),
                    'match_type': best.get('match_type'),
                    'reason': 'No selected-project value was available; extracted field is advisory.',
                }
            continue
        if not best:
            matches[field] = {
                'status': 'missing',
                'expected': _normalize_expected(field, expected_value),
                'actual': None,
                'confidence': 0,
                'match_type': 'missing',
                'reason': 'No candidate was extracted for this expected field.',
            }
            continue
        matches[field] = _match_expected(field, expected_value, fields[field]['candidates'])
    return matches


def _match_expected(field, expected_value, candidates):
    expected_normalized = _normalize_expected(field, expected_value)
    if field == 'reference_number':
        for candidate in candidates:
            actual = _normalize_reference(candidate.get('normalized_value'))
            if actual == expected_normalized:
                return _matched(field, expected_normalized, candidate, 'Strict reference-number match.')
        return _mismatched(field, expected_normalized, candidates[0], 'Reference numbers use exact matching; fuzzy matching is disabled.')

    if field == 'amount':
        for candidate in candidates:
            actual = _normalize_amount(candidate.get('normalized_value'))
            if actual == expected_normalized:
                return _matched(field, expected_normalized, candidate, 'Numeric amount matched after peso-format normalization.')
        return _mismatched(field, expected_normalized, candidates[0], 'Amounts must match materially after numeric normalization.')

    if field == 'fiscal_year':
        context_candidates = [
            candidate for candidate in candidates
            if candidate.get('match_type') in {
                'strict_context',
                'table_label_value',
                'inline_label_value',
                'line_start_label_value',
                'stacked_label_value',
                'stacked_table_header',
            }
        ]
        comparable_candidates = context_candidates or candidates
        for candidate in comparable_candidates:
            if _safe_int(candidate.get('normalized_value')) == _safe_int(expected_value):
                return _matched(field, _safe_int(expected_value), candidate, 'Fiscal year matched in a strict FY/GAA context.')
        return _mismatched(field, _safe_int(expected_value), comparable_candidates[0], 'Fiscal years use strict context matching.')

    if field == 'lgu':
        expected_variants = {normalize_text(value) for value in _lgu_expected_variants({'lgu_name': expected_value})}
        for candidate in candidates:
            actual_normalized = normalize_text(candidate.get('normalized_value') or candidate.get('matched_text'))
            if actual_normalized in expected_variants or any(value and value in actual_normalized for value in expected_variants):
                return _matched(field, expected_value, candidate, 'LGU matched against canonical name or accepted alias.')
        return _mismatched(field, expected_value, candidates[0], 'LGU does not match the selected project context.')

    if field == 'project_title':
        for candidate in candidates:
            actual_text = candidate.get('matched_text') or candidate.get('normalized_value')
            if _token_set_confidence(expected_value, actual_text) >= 0.80:
                return _matched(field, expected_value, candidate, 'Project title matched with controlled token overlap.')
        return _mismatched(field, expected_value, candidates[0], 'Project title or purpose only weakly overlaps the selected project.')

    if field == 'project_code':
        expected_code = _normalize_reference(expected_value)
        for candidate in candidates:
            if _normalize_reference(candidate.get('normalized_value')) == expected_code:
                return _matched(field, expected_code, candidate, 'Project code matched exactly after code normalization.')
        return _mismatched(field, expected_code, candidates[0], 'Project code does not match the selected project context.')

    return _matched(field, expected_value, candidates[0], 'Field extracted for reviewer context.')


def _matched(field, expected_value, candidate, reason):
    return {
        'status': 'matched',
        'expected': expected_value,
        'actual': candidate.get('normalized_value'),
        'confidence': candidate.get('confidence'),
        'match_type': candidate.get('match_type'),
        'candidate': candidate,
        'reason': reason,
    }


def _mismatched(field, expected_value, candidate, reason):
    return {
        'status': 'mismatch',
        'expected': expected_value,
        'actual': candidate.get('normalized_value'),
        'confidence': candidate.get('confidence'),
        'match_type': candidate.get('match_type'),
        'candidate': candidate,
        'reason': reason,
    }


def _field_finding(field, issue, severity, message, detail, *, match=None, best=None, zone=None):
    dimension = 'project_lgu_context' if field in {'lgu', 'project_title', 'fiscal_year'} else 'required_content_fields'
    
    if field == 'signatory':
        deficiency_category = 'missing_signature_notarization'
        automation_level = 'human_verification'
        finding_obs = 'Signatory or signature block could not be confirmed automatically in document text.'
        corrective_inst = 'Verify that the required wet/digital signature and official title/seal are present on the document.'
    elif field in {'lgu', 'project_title', 'fiscal_year', 'project_code'}:
        if issue == 'mismatch':
            deficiency_category = 'cross_document_inconsistency'
            finding_obs = f'Document {field.replace("_", " ")} conflicts with project context.'
            corrective_inst = 'Ensure the documentary submission references the correct project name, LGU, and fiscal year.'
        else:
            deficiency_category = 'other_documented_defect'
            finding_obs = f'Document is missing expected {field.replace("_", " ")}.'
            corrective_inst = f'Ensure the document explicitly includes the {field.replace("_", " ")}.'
        automation_level = 'automated_with_review'
    elif field == 'amount':
        if issue == 'mismatch':
            deficiency_category = 'financial_reconciliation_defect'
            finding_obs = 'Document monetary amount conflicts with the project allocation or voucher amount.'
            corrective_inst = 'Verify that the stated monetary amount matches the project allocation or voucher.'
        else:
            deficiency_category = 'other_documented_defect'
            finding_obs = 'Document monetary amount was not found in readable text.'
            corrective_inst = 'Ensure the document clearly indicates the monetary amount.'
        automation_level = 'automated_with_review'
    else:
        deficiency_category = 'other_documented_defect'
        automation_level = 'automated_with_review'
        finding_obs = f'Required field "{field.replace("_", " ")}" was {issue} in the document.'
        corrective_inst = f'Provide or verify the "{field.replace("_", " ")}" field before resubmitting.'

    return rule_engine.finding(
        f'field_{issue}:{field}',
        severity,
        'content' if issue == 'missing' else 'context',
        message,
        detail,
        dimension=dimension,
        locations=_field_locations(field, issue, match=match, best=best, zone=zone),
        deficiency_category=deficiency_category,
        finding_observation=finding_obs,
        corrective_instruction=corrective_inst,
        automation_level=automation_level,
    )


def _field_locations(field, issue, *, match=None, best=None, zone=None):
    candidate = None
    if isinstance(match, dict):
        candidate = match.get('candidate')
    candidate = candidate or best or {}
    label = _field_label(field)

    if issue == 'missing':
        return []

    page = _safe_int(candidate.get('page')) or 1
    matched_text = str(candidate.get('matched_text') or '').strip()
    location = {
        'page': page,
        'field': field,
    }
    if candidate.get('bbox'):
        location.update({
            'bbox': candidate.get('bbox'),
            'bbox_type': candidate.get('bbox_type') or 'detected_text',
            'reason': f'Extracted {label} evidence was found at this detected text location.',
        })
    elif matched_text:
        location.update({
            'bbox_type': candidate.get('bbox_type') or 'detected_text',
            'reason': f'Extracted {label} evidence text was found; highlight the matched text when document text geometry is available.',
        })
    else:
        return []
    if matched_text:
        location['matched_text'] = matched_text
    return [location]


def _expected_zone_location(field, issue, zone, *, matched_text=None):
    label = str(zone.get('label') or _field_label(field)).strip()
    reason = f'Expected {label} zone from the reference format profile.'
    if issue == 'mismatch':
        reason = f'{reason[:-1]}; extracted value did not match the selected project.'
    location = {
        'page': _safe_int(zone.get('page')) or 1,
        'bbox': zone.get('bbox') if zone.get('bbox') is not None else zone.get('expected_bbox'),
        'bbox_type': zone.get('bbox_type') or 'expected_zone',
        'reason': reason,
        'field': field,
    }
    if zone.get('label'):
        location['label'] = zone.get('label')
    if matched_text:
        location['matched_text'] = matched_text
    if zone.get('reference_uri'):
        location['reference_uri'] = zone.get('reference_uri')
    return location


def _mismatch_detail(field, match):
    expected = match.get('expected')
    actual = match.get('actual')
    reason = match.get('reason') or 'The extracted value does not match the selected project.'
    if field == 'reference_number':
        reason = f'{reason} Reference numbers are strict fields and are not fuzzy-matched.'
    return f'Expected {expected!r}; extracted {actual!r}. {reason}'


def _missing_detail(profile, field):
    if profile.get('id') == NADAI_PROFILE['id']:
        return 'This profile requires the LGU, FY/GAA year, amount, and ADA/NCA/NTA reference to be readable before the evidence can be treated as approval-ready.'
    if profile.get('id') in {'official_receipt', 'billing_package'}:
        return 'This financial evidence profile requires the receipt/billing date, amount, and receipt/invoice/reference number to be readable. Project title is not required for this evidence type.'
    return f'This profile requires {_field_label(field)} to be readable before the checker can treat the evidence as complete.'


def _field_label(field):
    return field.replace('_', ' ')


def _candidate(field, matched_text, normalized_value, confidence, reason, match_type):
    payload = {
        'field': field,
        'matched_text': str(matched_text or '').strip(),
        'normalized_value': normalized_value,
        'confidence': round(float(confidence), 4),
        'page': 1,
        'bbox': None,
        'source': 'local_text',
        'provider': 'comet-field-evidence-rules',
        'reason': reason,
        'match_type': match_type,
    }
    return payload


def _best_candidate(candidates):
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.get('confidence') or 0, reverse=True)[0]


def _dedupe_candidates(candidates):
    seen = set()
    deduped = []
    for candidate in sorted(candidates, key=lambda item: item.get('confidence') or 0, reverse=True):
        key = (candidate.get('field'), str(candidate.get('normalized_value')), candidate.get('matched_text'))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _contains_any(normalized_corpus, terms):
    return any(normalize_text(term) in normalized_corpus for term in terms)


def _candidate_segments(corpus):
    segments = []
    for line in str(corpus or '').splitlines():
        cleaned = line.strip()
        if cleaned:
            segments.append(cleaned)
    for sentence in re.split(r'[.;]', str(corpus or '')):
        cleaned = sentence.strip()
        if 10 <= len(cleaned) <= 240:
            segments.append(cleaned)
    return segments


def _token_set_confidence(expected, candidate):
    expected_tokens = _meaningful_tokens(expected)
    candidate_tokens = _meaningful_tokens(candidate)
    if not expected_tokens or not candidate_tokens:
        return 0
    overlap = expected_tokens & candidate_tokens
    overlap_score = (2 * len(overlap)) / (len(expected_tokens) + len(candidate_tokens))
    expected_sorted = ' '.join(sorted(expected_tokens))
    candidate_sorted = ' '.join(sorted(candidate_tokens))
    sequence_score = SequenceMatcher(None, expected_sorted, candidate_sorted).ratio()
    return round(max(overlap_score, sequence_score), 4)


def _meaningful_tokens(value):
    return {
        token for token in normalize_text(value).split()
        if len(token) > 2 and token not in _STOPWORDS
    }


def _lgu_expected_variants(expected):
    variants = []
    for key in ('lgu_name', 'lgu_municipality'):
        variants.extend(lgu_expected_variants(expected.get(key)))
    return [item for item in dict.fromkeys(variants) if item]


def _clean_lgu_text(value):
    cleaned = re.sub(r'\s+', ' ', str(value or '')).strip(' .,:;')
    cleaned = re.sub(r'\b(date|fy|fiscal year|amount|purpose)\b.*$', '', cleaned, flags=re.IGNORECASE).strip(' .,:;')
    return cleaned


def _normalize_expected(field, value):
    if field == 'amount':
        return _normalize_amount(value)
    if field == 'reference_number':
        return _normalize_reference(value)
    if field == 'fiscal_year':
        return _safe_int(value)
    return value


def _normalize_reference(value):
    normalized = str(value or '').strip().upper()
    normalized = re.sub(r'\s+', '', normalized)
    normalized = normalized.replace('\u2013', '-').replace('\u2014', '-')
    return normalized.strip(' .,:;')


def _normalize_reference_prefix(value):
    normalized = re.sub(r'[^A-Z0-9]+', '', str(value or '').upper())
    if normalized in {'OR', 'OFFICIALRECEIPT', 'RECEIPT'}:
        return 'OR'
    if normalized in {'BILL', 'BILLING'}:
        return 'BILL'
    return normalized or 'REF'


def _receipt_reference_value(prefix, number):
    normalized_number = _normalize_reference(number)
    if normalized_number.startswith(prefix):
        return normalized_number
    if prefix == 'OR' and normalized_number.startswith('OR'):
        return normalized_number
    return f'{prefix}-{normalized_number}'


def _document_reference_value(prefix, number):
    normalized_number = _normalize_reference(number)
    if normalized_number.startswith(prefix):
        return normalized_number
    return f'{prefix}-{normalized_number}'


def _normalize_amount(value):
    if value in (None, ''):
        return None
    raw = str(value).strip()
    raw = re.sub(r'(?i)(php|peso(?:s)?|p|\u20b1)', '', raw)
    raw = raw.replace(',', '').replace(' ', '')
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return f'{amount.quantize(Decimal("0.01"))}'


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
