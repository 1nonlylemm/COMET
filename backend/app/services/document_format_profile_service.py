"""Deterministic format/layout checks for documentary compliance profiles.

Reference profiles can carry ``profile_metadata.format_profile`` to describe
expected layout elements such as headings, tables, signature zones, and page
count ranges. This service compares those expectations against extracted text
and metadata, then emits normal compliance findings with expected-zone
locations where available.
"""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.services import document_intelligence_service
from app.services import document_compliance_rule_engine as rule_engine
from app.services import document_layout_geometry


STRICT_TEMPLATE = 'strict_template'
STANDARD_TEMPLATE = 'standard_template'
ACCEPTED_SAMPLE = 'accepted_sample'
GUIDELINE_ONLY = 'guideline_only'

DEFAULT_STRICTNESS_BY_REFERENCE = {
    'official_template': STRICT_TEMPLATE,
    'validation_checklist': STANDARD_TEMPLATE,
    'accepted_sample': ACCEPTED_SAMPLE,
    'logo_letterhead_reference': STANDARD_TEMPLATE,
    'guideline_basis': GUIDELINE_ONLY,
    'returned_sample': ACCEPTED_SAMPLE,
}

FORMAT_DIMENSION = 'format_template_layout'

SECTION_CANDIDATES = (
    ('background_and_rationale', 'Background and Rationale', ('background and rationale', 'background')),
    ('objectives', 'Objectives', ('objectives', 'objective')),
    ('scope_of_work', 'Scope of Work', ('scope of work', 'scope')),
    ('implementation_schedule', 'Implementation Schedule', ('implementation schedule', 'timeline', 'work schedule')),
    ('budget_breakdown', 'Budget Breakdown', ('budget breakdown', 'cost breakdown', 'financial plan')),
)

SIGNATURE_CANDIDATES = (
    ('prepared_by', 'Prepared by', ('prepared by',), [8, 72, 32, 14]),
    ('noted_by', 'Noted by', ('noted by',), [35, 72, 32, 14]),
    ('approved_by', 'Approved by', ('approved by', 'approved'), [58, 72, 32, 14]),
)

TABLE_CANDIDATES = (
    {
        'id': 'cost_breakdown',
        'label': 'Cost breakdown table',
        'terms': ('item description', 'quantity', 'unit cost', 'amount'),
        'required_columns': ['Item Description', 'Quantity', 'Unit Cost', 'Amount'],
        'page': 1,
        'bbox': [8, 35, 84, 30],
    },
)


def format_profile_findings(*, corpus, extraction, profile_selection):
    is_ocr_fallback = rule_engine.is_ocr_fallback((extraction or {}).get("metadata"))
    if not rule_engine.format_profile_rules_apply(profile_selection or {}):
        return []

    findings = []
    normalized_corpus = rule_engine.normalize_corpus(corpus)
    metadata = (extraction or {}).get('metadata') or {}

    for profile in _used_profiles(profile_selection):
        profile_metadata = profile.get('profile_metadata') or {}
        format_profile = profile_metadata.get('format_profile') or {}
        if not isinstance(format_profile, dict) or not format_profile:
            continue

        strictness = _strictness(profile, format_profile)
        version = str(
            profile_metadata.get('format_profile_version')
            or format_profile.get('version')
            or 'unversioned'
        )

        findings.extend(_page_count_findings(
            metadata=metadata,
            format_profile=format_profile,
            strictness=strictness,
            profile=profile,
            version=version,
        ))
        findings.extend(_required_element_findings(
            normalized_corpus=normalized_corpus,
            format_profile=format_profile,
            strictness=strictness,
            profile=profile,
            version=version,
            is_ocr_fallback=is_ocr_fallback,
        ))
        findings.extend(_table_findings(
            normalized_corpus=normalized_corpus,
            format_profile=format_profile,
            strictness=strictness,
            profile=profile,
            version=version,
            is_ocr_fallback=is_ocr_fallback,
        ))
        findings.extend(_section_order_findings(
            normalized_corpus=normalized_corpus,
            format_profile=format_profile,
            strictness=strictness,
            profile=profile,
            version=version,
        ))
        findings.extend(_layout_overlap_findings(
            metadata=metadata,
            format_profile=format_profile,
            profile=profile,
            version=version,
        ))
        findings.extend(_costing_arithmetic_findings(
            text=(extraction or {}).get('text') or '',
            format_profile=format_profile,
            strictness=strictness,
            profile=profile,
            version=version,
        ))

    return _dedupe_findings(findings)


def extract_format_profile_from_file(file_path, *, mime_type=None, file_name=None, checker_reference_type=None):
    path = Path(file_path)
    extraction = document_intelligence_service.extract_document_text(
        path,
        mime_type=mime_type,
        file_name=file_name,
    )
    metadata = extraction.setdefault('metadata', {})
    page_count = _detect_page_count(path)
    if page_count is not None:
        metadata['page_count'] = page_count
    source_hash = _file_sha256(path)
    profile = infer_format_profile(extraction, checker_reference_type=checker_reference_type)
    return {
        'format_profile': profile,
        'format_profile_version': f'local:{source_hash[:12]}',
        'format_profile_source': 'local_extraction',
        'format_profile_source_hash': source_hash,
        'format_profile_extraction': {
            'status': 'extracted',
            'extractors': metadata.get('extractors') or [],
            'readable_text_chars': len(extraction.get('text') or ''),
            'page_count': metadata.get('page_count'),
        },
    }


def infer_format_profile(extraction, *, checker_reference_type=None):
    text = (extraction or {}).get('text') or ''
    metadata = (extraction or {}).get('metadata') or {}
    corpus = rule_engine.normalize_corpus(text)
    page_count = _int_value(metadata.get('page_count'))
    last_page = page_count or 1

    headings = []
    section_order = []
    for element_id, label, terms in SECTION_CANDIDATES:
        if any(rule_engine.contains_term(corpus, term) for term in terms):
            headings.append({'id': element_id, 'label': label, 'required_terms': [label]})
            section_order.append(label)

    signature_zones = []
    for element_id, label, terms, bbox in SIGNATURE_CANDIDATES:
        if any(rule_engine.contains_term(corpus, term) for term in terms):
            signature_zones.append({
                'id': element_id,
                'label': label,
                'page': last_page,
                'bbox': bbox,
                'required_terms': [label],
            })

    tables = []
    for candidate in TABLE_CANDIDATES:
        matched_terms = [term for term in candidate['terms'] if rule_engine.contains_term(corpus, term)]
        if len(matched_terms) >= 2:
            tables.append({
                'id': candidate['id'],
                'label': candidate['label'],
                'page': candidate['page'],
                'bbox': candidate['bbox'],
                'required_columns': candidate['required_columns'],
            })

    profile = {
        'source': 'local_extraction',
        'strictness': DEFAULT_STRICTNESS_BY_REFERENCE.get(checker_reference_type, STANDARD_TEMPLATE),
        'required_headings': headings,
        'section_order': section_order,
        'tables': tables,
        'signature_zones': signature_zones,
        'extraction_summary': {
            'extractors': metadata.get('extractors') or [],
            'readable_text_chars': len(text),
        },
    }
    if page_count is not None:
        profile['page_count'] = {'min': page_count, 'max': page_count}
        profile['extraction_summary']['page_count'] = page_count
    return profile


def format_profile_summary(profile_selection):
    summaries = []
    for profile in _used_profiles(profile_selection):
        profile_metadata = profile.get('profile_metadata') or {}
        format_profile = profile_metadata.get('format_profile') or {}
        if not isinstance(format_profile, dict) or not format_profile:
            continue
        summaries.append({
            'id': profile.get('id'),
            'reference_uri': profile.get('reference_uri'),
            'checker_reference_type': profile.get('checker_reference_type'),
            'format_profile_version': str(
                profile_metadata.get('format_profile_version')
                or format_profile.get('version')
                or 'unversioned'
            ),
            'strictness': _strictness(profile, format_profile),
        })
    return summaries


def _page_count_findings(*, metadata, format_profile, strictness, profile, version):
    rule = format_profile.get('page_count') or format_profile.get('page_count_range')
    if not isinstance(rule, dict):
        return []

    actual = _int_value(
        metadata.get('page_count')
        or metadata.get('pages')
        or metadata.get('pageCount')
    )
    minimum = _int_value(rule.get('min'))
    maximum = _int_value(rule.get('max'))
    if actual is None or (minimum is None and maximum is None):
        return []
    if minimum is not None and actual < minimum:
        return [_finding(
            'format_profile_page_count_out_of_range',
            _severity_for(strictness, blocker_for_strict=True),
            'format',
            'Document page count does not match the reference format profile.',
            _page_count_detail(actual, minimum, maximum),
            profile=profile,
            version=version,
        )]
    if maximum is not None and actual > maximum:
        return [_finding(
            'format_profile_page_count_out_of_range',
            _severity_for(strictness, blocker_for_strict=True),
            'format',
            'Document page count does not match the reference format profile.',
            _page_count_detail(actual, minimum, maximum),
            profile=profile,
            version=version,
        )]
    return []


def _required_element_findings(*, normalized_corpus, format_profile, strictness, profile, version, is_ocr_fallback=False):
    findings = []
    for collection_key in (
        'required_headings',
        'required_labels',
        'required_fields',
        'signature_zones',
        'stamp_zones',
        'seal_zones',
        'logo_zones',
        'letterhead_zones',
    ):
        for element in _as_list(format_profile.get(collection_key)):
            if not isinstance(element, dict):
                element = {'label': str(element), 'required_terms': [str(element)]}
            label = _element_label(element)
            terms = _element_terms(element, fallback=label)
            if terms and any(rule_engine.contains_term(normalized_corpus, term) for term in terms):
                if collection_key in ('signature_zones', 'stamp_zones', 'seal_zones'):
                    element_id = _element_id(element, label)
                    findings.append(_finding(
                        f'format_profile_present_unverified:{element_id}',
                        'manual_verification_required',
                        'format',
                        f'Signature/stamp label found - requires manual verification: {label}',
                        f'The system detected the text for {label}, but cannot verify the presence of actual ink. Please verify visually.',
                        profile=profile,
                        version=version,
                        locations=_element_locations(element, label),
                        deficiency_category='missing_signature_notarization',
                        finding_observation=f'Signature/seal marker for "{label}" was detected, requiring manual reviewer confirmation.',
                        corrective_instruction='Reviewer must visually confirm presence of wet/digital signature and official seal.',
                        automation_level='human_verification',
                    ))
                continue
            element_id = _element_id(element, label)
            is_sig_seal = collection_key in ('signature_zones', 'stamp_zones', 'seal_zones') or any(
                k in element_id for k in ('signed_by', 'certified_by', 'approved_by', 'prepared_by', 'seal', 'stamp', 'sign')
            )
            findings.append(_finding(
                f'format_profile_missing:{element_id}',
                _element_severity(element, strictness, is_ocr_fallback),
                'format',
                f'Expected format element was not found: {label}',
                _profile_detail(profile, version),
                profile=profile,
                version=version,
                locations=_element_locations(element, label),
            ))
    return findings


def _table_findings(*, normalized_corpus, format_profile, strictness, profile, version, is_ocr_fallback=False):
    findings = []
    for table in _as_list(format_profile.get('tables') or format_profile.get('required_tables')):
        if not isinstance(table, dict):
            continue
        label = _element_label(table, fallback='Required table')
        table_id = _element_id(table, label)
        required_columns = rule_engine.list_metadata(table.get('required_columns'))
        for column in required_columns:
            if rule_engine.contains_term(normalized_corpus, column):
                continue
            findings.append(_finding(
                f'format_profile_missing_column:{table_id}:{column}',
                _element_severity(table, strictness, is_ocr_fallback),
                'format',
                f'Expected table column was not found: {column}',
                f'{label} should include this column. {_profile_detail(profile, version)}',
                profile=profile,
                version=version,
                locations=_element_locations(table, label),
            ))
    return findings


def _section_order_findings(*, normalized_corpus, format_profile, strictness, profile, version):
    sections = format_profile.get('section_order') or []
    section_terms = []
    for section in _as_list(sections):
        if isinstance(section, dict):
            label = _element_label(section)
            terms = _element_terms(section, fallback=label)
            term = next((item for item in terms if rule_engine.contains_term(normalized_corpus, item)), None)
            if term:
                section_terms.append((label, normalized_corpus.find(rule_engine.normalize_corpus(term)), section))
        else:
            label = str(section)
            if rule_engine.contains_term(normalized_corpus, label):
                section_terms.append((label, normalized_corpus.find(rule_engine.normalize_corpus(label)), {}))

    if len(section_terms) < 2:
        return []

    positions = [position for _label, position, _section in section_terms]
    if positions == sorted(positions):
        return []

    return [_finding(
        'format_profile_section_order',
        'warning' if strictness != GUIDELINE_ONLY else 'minor_warning',
        'format',
        'Document section order does not match the reference format profile.',
        f'Expected section order: {", ".join(label for label, _position, _section in section_terms)}. {_profile_detail(profile, version)}',
        profile=profile,
        version=version,
        locations=_element_locations(section_terms[0][2], section_terms[0][0]),
    )]


def _layout_overlap_findings(*, metadata, format_profile, profile, version):
    elements = _layout_elements(metadata)
    rules = (
        format_profile.get('layout_overlap_rules')
        or format_profile.get('disallowed_overlaps')
        or format_profile.get('overlap_rules')
        or []
    )
    issues = document_layout_geometry.detect_disallowed_overlaps(elements, rules)
    findings = []
    for issue in issues:
        element_a_type = issue.get('element_a_type') or 'layout element'
        element_b_type = issue.get('element_b_type') or 'layout element'
        findings.append(_finding(
            f"layout_overlap:{issue.get('id')}",
            issue.get('severity') or 'warning',
            'format',
            'Document layout elements overlap more than the reference format allows.',
            (
                f"{element_a_type} overlaps {element_b_type} on page {issue.get('page')} "
                f"with overlap ratio {issue.get('overlap_ratio')}; allowed maximum is "
                f"{issue.get('max_intersection_ratio')}. {_profile_detail(profile, version)}"
            ),
            profile=profile,
            version=version,
            locations=_layout_overlap_locations(issue),
        ))
    return findings


def _costing_arithmetic_findings(*, text, format_profile, strictness, profile, version):
    findings = []
    # 1. From format_profile explicit cost_items
    cost_items = _as_list(format_profile.get('cost_items') or format_profile.get('dupa_items'))
    for item in cost_items:
        if not isinstance(item, dict):
            continue
        item_name = item.get('name') or item.get('item') or item.get('description') or 'Cost Item'
        try:
            qty = Decimal(str(item.get('quantity') or item.get('qty') or 0))
            unit_cost = Decimal(str(item.get('unit_cost') or item.get('rate') or 0))
            stated_amount = Decimal(str(item.get('total_amount') or item.get('amount') or 0))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if qty > 0 and unit_cost > 0 and stated_amount > 0:
            expected = (qty * unit_cost).quantize(Decimal('0.01'))
            if abs(expected - stated_amount) > Decimal('1.00'):
                item_id = _element_id(item, item_name)
                findings.append(_finding(
                    f'costing_arithmetic_mismatch:{item_id}',
                    'warning',
                    'format',
                    f'Arithmetic error in cost item "{item_name}": {qty} * ₱{unit_cost:,.2f} = ₱{expected:,.2f}, but stated ₱{stated_amount:,.2f}.',
                    f'Calculated line amount differs by ₱{abs(expected - stated_amount):,.2f}. {_profile_detail(profile, version)}',
                    profile=profile,
                    version=version,
                    deficiency_category='costing_dupa_defect',
                    finding_observation=f'Cost breakdown item "{item_name}" contains calculation error ({qty} @ ₱{unit_cost:,.2f} ≠ ₱{stated_amount:,.2f}).',
                    corrective_instruction='Correct quantity, unit cost, and line amount arithmetic in the Program of Works / DUPA.',
                    automation_level='automated_with_review',
                ))

    stated_subtotal = format_profile.get('subtotal') or format_profile.get('total_amount')
    if stated_subtotal and cost_items:
        try:
            subtotal_dec = Decimal(str(stated_subtotal))
            items_sum = sum(
                Decimal(str(item.get('total_amount') or item.get('amount') or 0))
                for item in cost_items if isinstance(item, dict)
            )
            if items_sum > 0 and subtotal_dec > 0 and abs(items_sum - subtotal_dec) > Decimal('1.00'):
                findings.append(_finding(
                    'costing_subtotal_mismatch',
                    'warning',
                    'format',
                    f'Subtotal calculation mismatch in cost breakdown: sum of line items ₱{items_sum:,.2f} ≠ stated subtotal ₱{subtotal_dec:,.2f}.',
                    f'Sum of line items differs from stated subtotal by ₱{abs(items_sum - subtotal_dec):,.2f}. {_profile_detail(profile, version)}',
                    profile=profile,
                    version=version,
                    deficiency_category='costing_dupa_defect',
                    finding_observation=f'Cost breakdown subtotal (₱{subtotal_dec:,.2f}) does not match sum of items (₱{items_sum:,.2f}).',
                    corrective_instruction='Reconcile line items and subtotal in the detailed cost breakdown / DUPA.',
                    automation_level='automated_with_review',
                ))
        except (InvalidOperation, ValueError, TypeError):
            pass

    # 2. Heuristic scan of text lines for cost breakdown rows
    if text:
        row_regex = re.compile(
            r'^(?:(?P<item>(?:Item\s+[\w\.\-]+|[A-Za-z][A-Za-z0-9\s\.\-_]{2,35}?))\s+)?'
            r'(?P<qty>\d+(?:,\d{3})*(?:\.\d+)?)\s+'
            r'(?P<unit>[a-zA-Z\.\/]{1,10})?\s*(?:@|at)?\s*'
            r'(?:php|₱)?\s*(?P<unit_cost>\d+(?:,\d{3})*(?:\.\d{2}))\s+'
            r'(?:php|₱)?\s*(?P<amount>\d+(?:,\d{3})*(?:\.\d{2}))\s*$',
            re.IGNORECASE | re.MULTILINE
        )
        seen_items = set()
        for match in row_regex.finditer(text):
            item_name = (match.group('item') or '').strip()
            raw_qty = match.group('qty').replace(',', '')
            raw_cost = match.group('unit_cost').replace(',', '')
            raw_amount = match.group('amount').replace(',', '')
            try:
                qty = Decimal(raw_qty)
                unit_cost = Decimal(raw_cost)
                amount = Decimal(raw_amount)
            except (InvalidOperation, ValueError):
                continue
            if qty <= 0 or unit_cost <= 0 or amount <= 0:
                continue
            expected = (qty * unit_cost).quantize(Decimal('0.01'))
            if abs(expected - amount) > Decimal('1.00'):
                item_label = item_name or f'Row {raw_qty}x{raw_cost}'
                if item_label in seen_items:
                    continue
                seen_items.add(item_label)
                item_id = _element_id(None, item_label)
                findings.append(_finding(
                    f'costing_arithmetic_mismatch:{item_id}',
                    'warning',
                    'format',
                    f'Arithmetic error in cost item "{item_label}": {qty} * ₱{unit_cost:,.2f} = ₱{expected:,.2f}, but stated ₱{amount:,.2f}.',
                    f'Calculated line amount differs by ₱{abs(expected - amount):,.2f}. {_profile_detail(profile, version)}',
                    profile=profile,
                    version=version,
                    deficiency_category='costing_dupa_defect',
                    finding_observation=f'Cost breakdown item "{item_label}" contains calculation error ({qty} @ ₱{unit_cost:,.2f} ≠ ₱{amount:,.2f}).',
                    corrective_instruction='Correct quantity, unit cost, and line amount arithmetic in the Program of Works / DUPA.',
                    automation_level='automated_with_review',
                ))
    return findings


def _finding(
    finding_id,
    severity,
    category,
    message,
    detail,
    *,
    profile,
    version,
    locations=None,
    deficiency_category=None,
    finding_observation=None,
    corrective_instruction=None,
    automation_level=None,
):
    return rule_engine.finding(
        finding_id,
        severity,
        category,
        message,
        detail,
        dimension=FORMAT_DIMENSION,
        locations=locations,
        deficiency_category=deficiency_category,
        finding_observation=finding_observation,
        corrective_instruction=corrective_instruction,
        automation_level=automation_level,
    )


def _used_profiles(profile_selection):
    if not isinstance(profile_selection, dict):
        return []
    profiles = profile_selection.get('used_profiles') or []
    deduped = []
    seen = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        key = _profile_layout_key(profile)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(profile)
    return deduped


def _profile_layout_key(profile):
    metadata = profile.get('profile_metadata') or {}
    format_profile = metadata.get('format_profile') or {}
    try:
        serialized_profile = json.dumps(format_profile, sort_keys=True, default=str)
    except TypeError:
        serialized_profile = str(format_profile)
    return (
        profile.get('checker_reference_type'),
        metadata.get('evidence_type'),
        str(metadata.get('format_profile_version') or format_profile.get('version') or 'unversioned'),
        serialized_profile,
    )


def _dedupe_findings(findings):
    deduped = []
    seen = set()
    for item in findings:
        key = (
            item.get('id'),
            item.get('severity'),
            item.get('category'),
            item.get('message'),
            item.get('detail'),
            item.get('dimension'),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _strictness(profile, format_profile):
    explicit = str(format_profile.get('strictness') or '').strip().lower()
    if explicit in {STRICT_TEMPLATE, STANDARD_TEMPLATE, ACCEPTED_SAMPLE, GUIDELINE_ONLY}:
        return explicit
    return DEFAULT_STRICTNESS_BY_REFERENCE.get(profile.get('checker_reference_type'), STANDARD_TEMPLATE)


def _severity_for(strictness, *, blocker_for_strict=False):
    if strictness == GUIDELINE_ONLY:
        return 'minor_warning'
    if strictness == ACCEPTED_SAMPLE:
        return 'warning'
    if strictness == STRICT_TEMPLATE and blocker_for_strict:
        return 'blocker'
    return 'warning'


def _element_severity(element, strictness, is_ocr_fallback=False):
    configured = str((element or {}).get('severity') or '').strip().lower()
    severity = 'warning'
    if configured in {'blocker', 'warning', 'minor_warning', 'info'}:
        severity = configured
    elif strictness == STRICT_TEMPLATE:
        severity = 'blocker'
    elif strictness == GUIDELINE_ONLY:
        severity = 'minor_warning'
        
    if severity == 'blocker' and is_ocr_fallback:
        return 'needs_verification'
    return severity


def _element_label(element, fallback=None):
    return str(
        (element or {}).get('label')
        or (element or {}).get('name')
        or (element or {}).get('text')
        or fallback
        or 'Required format element'
    )


def _element_id(element, label):
    raw = (element or {}).get('id') or label
    return rule_engine.normalize_corpus(raw).replace(' ', '_') or 'required_element'


def _element_terms(element, fallback):
    terms = []
    for key in ('required_terms', 'terms', 'text'):
        terms.extend(rule_engine.list_metadata((element or {}).get(key)))
    if not terms and fallback:
        terms = [fallback]
    return terms


def _element_locations(element, label):
    page = _int_value((element or {}).get('page')) or 1
    bbox = (element or {}).get('bbox') or (element or {}).get('expected_bbox')
    if not bbox:
        return None
    return [{
        'page': page,
        'bbox': bbox,
        'bbox_type': (element or {}).get('bbox_type') or 'expected_zone',
        'reason': f'Expected {label} zone from the reference format profile.',
    }]


def _layout_elements(metadata):
    metadata = metadata or {}
    layout = metadata.get('layout') if isinstance(metadata.get('layout'), dict) else {}
    elements = metadata.get('layout_elements') or layout.get('layout_elements') or layout.get('elements') or []
    return elements if isinstance(elements, list) else []


def _layout_overlap_locations(issue):
    bbox = _xyxy_to_location_bbox(issue.get('bbox'))
    if not bbox:
        return None
    return [{
        'page': issue.get('page') or 1,
        'bbox': bbox,
        'bbox_type': 'layout_overlap',
        'reason': f"Detected overlap between {issue.get('element_a')} and {issue.get('element_b')}.",
    }]


def _xyxy_to_location_bbox(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    if width <= 0 or height <= 0:
        return None
    return {
        'x': round(x1, 4),
        'y': round(y1, 4),
        'width': round(width, 4),
        'height': round(height, 4),
    }


def _profile_detail(profile, version):
    reference_type = str(profile.get('checker_reference_type') or 'reference').replace('_', ' ')
    return f'The active {reference_type} requires this element in format profile version {version}.'


def _page_count_detail(actual, minimum, maximum):
    if minimum is not None and maximum is not None:
        return f'Found {actual} page(s); expected {minimum}-{maximum}.'
    if minimum is not None:
        return f'Found {actual} page(s); expected at least {minimum}.'
    return f'Found {actual} page(s); expected at most {maximum}.'


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _int_value(value):
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric


def _detect_page_count(path):
    suffix = Path(path).suffix.lower()
    if suffix == '.pdf':
        try:
            from pypdf import PdfReader
            return len(PdfReader(str(path)).pages)
        except Exception:
            return None
    if suffix in {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'}:
        return 1
    return None


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
