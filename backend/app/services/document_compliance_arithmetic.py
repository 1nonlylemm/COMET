"""Documentary Arithmetic and Calculation Consistency Checker for COMET.

Phase 3.1: Expands deterministic arithmetic checking across uploaded documents.
Evaluates:
1. Quantity × Unit Cost = Expected Line Total vs Stated Line Total
2. Line-Item Sum vs Stated Subtotal
3. Subtotal Sum vs Stated Grand Total
4. Line-Item Sum vs Stated Grand Total (Financial Reconciliation)

Adheres strictly to the COMET Reviewer Assistant principles:
- Emits factual observations, never compliance verdicts
- Never silently repairs documents or infers missing numbers
- Preserves currency formatting and original extracted values in evidence
- Rejects ambiguous OCR tokens to prevent false positives
- Categorizes findings under calculation_arithmetic_consistency
"""

from __future__ import annotations

import hashlib
import re
import math
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services import document_compliance_rule_engine as rule_engine


# Regex for amounts in Philippine Peso / general currency
CURRENCY_PREFIX = r'(?:php|p|₱|\$)?\s*'
AMOUNT_PATTERN = r'[\d,]+(?:\.\d{2})?'


def _parse_clean_decimal(value_str: Any) -> Decimal | None:
    """Parses a string into Decimal, rejecting ambiguous or malformed tokens."""
    if value_str is None:
        return None
    val = str(value_str).strip()
    if not val:
        return None
    # Strip currency symbols and whitespace
    clean = re.sub(r'^(?:php|p|₱|\$)\s*', '', val, flags=re.IGNORECASE).strip()
    # Reject tokens with unexpected alpha characters (e.g. OCR confusion '25O00' or '12B')
    if re.search(r'[a-df-z]', clean, re.IGNORECASE):
        return None
    # Reject multiple decimal points
    if clean.count('.') > 1:
        return None
    # Remove thousand-separator commas
    clean = clean.replace(',', '')
    try:
        dec = Decimal(clean)
        return dec
    except (InvalidOperation, ValueError):
        return None


def _safe_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _find_text_location_for_snippet(text_locations: list[dict[str, Any]], snippet: str) -> dict[str, Any] | None:
    """Locate a substantial, unique token sequence on one known page."""
    import unicodedata

    def tokens(value):
        folded = ''.join(c for c in unicodedata.normalize('NFKD', str(value or '')).casefold()
                         if not unicodedata.combining(c))
        return re.findall(r'[^\W_]+', folded, re.UNICODE)

    expected = tokens(snippet)
    if not expected:
        return None
    words = []
    for location in text_locations or []:
        if not isinstance(location, dict):
            continue
        try:
            page = int(location.get('page'))
        except (ValueError, TypeError):
            continue
        if page > 0:
            words.extend((token, page, location) for token in tokens(location.get('text')))
    matches = {}
    for index, (word, page, _) in enumerate(words):
        for offset, token in enumerate(expected):
            if word != token:
                continue
            length = 0
            while index + length < len(words) and offset + length < len(expected):
                actual, actual_page, _ = words[index + length]
                if actual_page != page or actual != expected[offset + length]:
                    break
                length += 1
            if len(expected) == 1:
                if len(word) < 4 or word in {'total', 'report', 'prepared', 'approved', 'date', 'page'}:
                    continue
            elif length < 2 or (length / len(expected) < 0.6 and length < 8):
                continue
            key = (index, index + length, page)
            matches[key] = length
    if not matches:
        return None
    best_length = max(matches.values())
    best = [key for key, length in matches.items() if length == best_length]
    # Repeated evidence is ambiguous even if its wording is identical.
    if len(best) != 1:
        return None
    start, end, page = best[0]
    locations = {id(location): location for _, _, location in words[start:end]}.values()
    boxes = []
    for location in locations:
        box = location.get('bbox')
        if isinstance(box, dict):
            box = [box.get('x'), box.get('y'), box.get('width'), box.get('height')]
        if isinstance(box, (list, tuple)) and len(box) == 4:
            try:
                box = [float(value) for value in box]
                if all(math.isfinite(value) for value in box) and box[2] > 0 and box[3] > 0:
                    boxes.append(box)
            except (ValueError, TypeError):
                pass
    bbox = None
    if boxes:
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        right, bottom = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
        bbox = [round(left, 4), round(top, 4), round(right - left, 4), round(bottom - top, 4)]
    return {'page': page, 'bbox': bbox}


def evaluate_document_arithmetic(
    text: str,
    *,
    extraction: dict[str, Any] | None = None,
    field_evidence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluates extracted document text for arithmetic consistency.

    Checks:
    1. Quantity × Unit Cost vs Stated Line Total
    2. Line Items vs Stated Subtotal
    3. Stated Subtotals vs Stated Grand Total
    4. Line Items vs Stated Grand Total (if no subtotals present)

    Returns:
        List of canonical findings satisfying Phase 3.0 contract.
    """
    if not text:
        return []

    raw_text = str(text)
    extraction = extraction or {}
    text_locations = (extraction.get('metadata') or {}).get('text_locations') or []

    findings: list[dict[str, Any]] = []

    # 1. Quantity × Unit Cost Checks
    qty_findings = _check_quantity_unit_cost(raw_text, text_locations=text_locations)
    findings.extend(qty_findings)

    # 2. Subtotal and Grand Total Checks
    total_findings = _check_subtotals_and_totals(raw_text, text_locations=text_locations)
    findings.extend(total_findings)

    return findings


def _check_quantity_unit_cost(raw_text: str, *, text_locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detects line items containing Quantity, Unit Cost, and Stated Total."""
    findings = []
    lines = raw_text.splitlines()

    # Pattern 1: Explicit labels (Qty, Unit Cost, Total)
    # E.g. "Qty: 12, Unit Cost: ₱25,000.00, Total: ₱325,000.00"
    # or "Quantity: 10 | Unit Price: ₱500.00 | Total: ₱5,000.00"
    labeled_pattern = re.compile(
        r'(?:qty|quantity)[:\s]+(\d+(?:\.\d+)?)\s*(?:units?|pcs?|pieces?|sets?|lots?|pax|ls|box|boxes)?\s*[,;|]?\s*'
        r'(?:unit\s+(?:cost|price)|rate|price)[:\s]+(?:php|p|₱|\$)?\s*([\d,]+(?:\.\d{2})?)\s*[,;|]?\s*'
        r'(?:total|amount|line\s+total)[:\s]+(?:php|p|₱|\$)?\s*([\d,]+(?:\.\d{2})?)',
        re.IGNORECASE,
    )

    # Pattern 2: Multiplier / At-symbol syntax
    # E.g. "12 units @ ₱25,000.00 = ₱325,000.00" or "10 x ₱500.00 = ₱5,500.00"
    mult_pattern = re.compile(
        r'\b(\d+(?:\.\d+)?)\s*(?:units?|pcs?|pieces?|sets?|lots?|pax|ls|box|boxes)?\s*'
        r'(?:@|x|\*)\s*(?:php|p|₱|\$)?\s*([\d,]+(?:\.\d{2})?)\s*(?:=|:|total|amount|\s)\s*(?:php|p|₱|\$)?\s*([\d,]+(?:\.\d{2})?)\b',
        re.IGNORECASE,
    )

    # Pattern 3: Tabular line format
    # E.g. "Item 1 | 12 | 25,000.00 | 325,000.00"
    tabular_pattern = re.compile(
        r'(?:item\s*\d+|[A-Z0-9\.\-]+)\s*[\t\|]\s*(\d+(?:\.\d+)?)\s*[\t\|]\s*(?:php|p|₱|\$)?\s*([\d,]+\.\d{2})\s*[\t\|]\s*(?:php|p|₱|\$)?\s*([\d,]+\.\d{2})',
        re.IGNORECASE,
    )

    seen_signatures = set()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        matches = []
        for pat in (labeled_pattern, mult_pattern, tabular_pattern):
            for m in pat.finditer(stripped):
                matches.append(m)

        for m in matches:
            raw_qty, raw_cost, raw_total = m.group(1), m.group(2), m.group(3)
            qty = _parse_clean_decimal(raw_qty)
            unit_cost = _parse_clean_decimal(raw_cost)
            stated_total = _parse_clean_decimal(raw_total)

            if qty is None or unit_cost is None or stated_total is None:
                continue

            if qty <= Decimal('0') or unit_cost <= Decimal('0') or stated_total <= Decimal('0'):
                continue

            # Deterministic calculation
            expected_total = qty * unit_cost
            diff = abs(expected_total - stated_total)

            sig = (raw_qty, raw_cost, raw_total)
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)

            # If difference exceeds ₱1.00 (accounting for penny rounding)
            if diff > Decimal('1.00'):
                loc_info = _find_text_location_for_snippet(text_locations, stripped) or {}
                page = loc_info.get('page') or 1
                bbox = loc_info.get('bbox')
                hash_key = hashlib.md5(f'{qty}_{unit_cost}_{stated_total}_{page}'.encode()).hexdigest()[:8]

                qty_display = f'{qty:g}'
                obs = (
                    f'Extracted quantity {qty_display} × unit cost ₱{unit_cost:,.2f} = ₱{expected_total:,.2f}, '
                    f'while the stated line total is ₱{stated_total:,.2f}. Difference: ₱{diff:,.2f}.'
                )
                action = (
                    f'Verify the line item calculation for quantity {qty_display} at ₱{unit_cost:,.2f} '
                    f'and reconcile with the stated total ₱{stated_total:,.2f}.'
                )

                findings.append(rule_engine.finding(
                    f'arithmetic_mismatch_qty_cost_{hash_key}',
                    'warning',
                    rule_engine.CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY,
                    f'Quantity × unit cost calculation does not match stated line total: ₱{expected_total:,.2f} vs ₱{stated_total:,.2f}.',
                    obs,
                    rule='quantity_unit_cost_arithmetic_mismatch',
                    deficiency_category='financial_reconciliation_defect',
                    finding_observation=obs,
                    corrective_instruction=action,
                    automation_level='automated_with_review',
                    confidence='high',
                    page=page,
                    bbox=bbox,
                    evidence_text=stripped,
                    reviewer_action=action,
                    provenance={'source': 'document_compliance_arithmetic', 'check': 'quantity_unit_cost'},
                ))

    return findings


def _check_subtotals_and_totals(raw_text: str, *, text_locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detects Subtotals vs Line Items, Subtotals vs Grand Total, and Line Items vs Grand Total."""
    findings = []

    # 1. Detect stated Grand Total(s)
    grand_total_matches = list(re.finditer(
        r'(?:grand\s+total|total\s+amount|total\s+cost|total\s+disbursement|total\s+payment|stated\s+total)[:\s]+(?:php|p|₱|\$)?\s*([\d,]+(?:\.\d{2})?)',
        raw_text,
        re.IGNORECASE,
    ))

    # 2. Detect stated Subtotals (standalone lines, not item line headers)
    subtotal_matches = list(re.finditer(
        r'(?:^|[\r\n])\s*(?!item\s*\d+)(?:sub-?total|sub\s+total)[:\s]+(?:php|p|₱|\$)?\s*([\d,]+(?:\.\d{2})?)',
        raw_text,
        re.IGNORECASE,
    ))

    # A. Check Subtotal Sum vs Grand Total
    if len(subtotal_matches) >= 2 and grand_total_matches:
        subtotal_values = []
        for sm in subtotal_matches:
            val = _parse_clean_decimal(sm.group(1))
            if val is not None and val > Decimal('0.00'):
                subtotal_values.append(val)

        for gm in grand_total_matches:
            stated_gt = _parse_clean_decimal(gm.group(1))
            if stated_gt is not None and stated_gt > Decimal('0.00') and len(subtotal_values) >= 2:
                sub_sum = sum(subtotal_values)
                diff = abs(sub_sum - stated_gt)
                if diff > Decimal('1.00') and diff != stated_gt:
                    loc_info = _find_text_location_for_snippet(text_locations, gm.group(0)) or {}
                    page = loc_info.get('page') or 1
                    bbox = loc_info.get('bbox')
                    hash_key = hashlib.md5(f'{sub_sum}_{stated_gt}'.encode()).hexdigest()[:8]

                    sub_breakdown = ' + '.join(f'₱{v:,.2f}' for v in subtotal_values)
                    obs = (
                        f'Sum of extracted subtotals ({sub_breakdown} = ₱{sub_sum:,.2f}) '
                        f'does not match stated grand total (₱{stated_gt:,.2f}). Difference: ₱{diff:,.2f}.'
                    )
                    action = (
                        f'Verify the summation of document subtotals against the stated grand total (₱{stated_gt:,.2f}).'
                    )

                    findings.append(rule_engine.finding(
                        f'grand_total_arithmetic_mismatch_{hash_key}',
                        'warning',
                        rule_engine.CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY,
                        f'Sum of subtotals (₱{sub_sum:,.2f}) does not match stated grand total (₱{stated_gt:,.2f}).',
                        obs,
                        rule='grand_total_arithmetic_mismatch',
                        deficiency_category='financial_reconciliation_defect',
                        finding_observation=obs,
                        corrective_instruction=action,
                        automation_level='automated_with_review',
                        confidence='high',
                        page=page,
                        bbox=bbox,
                        evidence_text=f'Subtotals: {sub_breakdown} | Grand Total: ₱{stated_gt:,.2f}',
                        reviewer_action=action,
                        provenance={'source': 'document_compliance_arithmetic', 'check': 'subtotal_sum_vs_grand_total'},
                    ))
                    break

    # B. Check Line-Item Sum vs Subtotal
    for sm in subtotal_matches:
        stated_sub = _parse_clean_decimal(sm.group(1))
        if stated_sub is None or stated_sub <= Decimal('0.00'):
            continue

        preceding_text = raw_text[max(0, sm.start() - 2500):sm.start()]
        item_regex = re.compile(
            r'(?:^|[\r\n])\s*(?:item\s*\d+[\.:]?|\d+[\.\)]|[A-Z][a-z]+)\s+[^0-9\r\n]{1,40}?\s+(?:(?:php|p|₱|\$)\s*([\d,]+(?:\.\d{2})?)|([\d,]+\.\d{2}))',
            re.IGNORECASE,
        )
        line_amts = []
        for lm in item_regex.finditer(preceding_text):
            amt = _parse_clean_decimal(lm.group(1) or lm.group(2))
            if amt and amt > Decimal('0.00') and amt != stated_sub:
                line_amts.append(amt)

        if len(line_amts) >= 2:
            calc_sub = sum(line_amts)
            diff = abs(calc_sub - stated_sub)
            if diff > Decimal('1.00') and diff != stated_sub:
                loc_info = _find_text_location_for_snippet(text_locations, sm.group(0)) or {}
                page = loc_info.get('page') or 1
                bbox = loc_info.get('bbox')
                hash_key = hashlib.md5(f'{calc_sub}_{stated_sub}'.encode()).hexdigest()[:8]

                obs = (
                    f'Extracted line item summation (₱{calc_sub:,.2f}) does not match stated subtotal (₱{stated_sub:,.2f}). '
                    f'Difference: ₱{diff:,.2f}.'
                )
                action = f'Verify line items preceding subtotal (₱{stated_sub:,.2f}) and reconcile arithmetic.'

                findings.append(rule_engine.finding(
                    f'subtotal_arithmetic_mismatch_{hash_key}',
                    'warning',
                    rule_engine.CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY,
                    f'Line item summation (₱{calc_sub:,.2f}) does not match stated subtotal (₱{stated_sub:,.2f}).',
                    obs,
                    rule='subtotal_arithmetic_mismatch',
                    deficiency_category='financial_reconciliation_defect',
                    finding_observation=obs,
                    corrective_instruction=action,
                    automation_level='automated_with_review',
                    confidence='high',
                    page=page,
                    bbox=bbox,
                    evidence_text=sm.group(0),
                    reviewer_action=action,
                    provenance={'source': 'document_compliance_arithmetic', 'check': 'line_items_vs_subtotal'},
                ))

    # C. Check Line-Item Sum vs Grand Total (Financial Reconciliation)
    for tm in grand_total_matches:
        stated_total = _parse_clean_decimal(tm.group(1))
        if stated_total is None or stated_total <= Decimal('0.00'):
            continue

        preceding_text = raw_text[max(0, tm.start() - 2500):tm.start()]
        item_regex = re.compile(
            r'(?:^|[\r\n])\s*(?:item\s*\d+[\.:]?|\d+[\.\)]|[A-Z][a-z]+)\s+[^0-9\r\n]{1,40}?\s+(?:(?:php|p|₱|\$)\s*([\d,]+(?:\.\d{2})?)|([\d,]+\.\d{2}))',
            re.IGNORECASE,
        )
        line_amts = []
        for lm in item_regex.finditer(preceding_text):
            amt = _parse_clean_decimal(lm.group(1) or lm.group(2))
            if amt and amt > Decimal('0.00') and amt != stated_total:
                line_amts.append(amt)

        if len(line_amts) >= 2:
            calc_sum = sum(line_amts)
            diff = abs(calc_sum - stated_total)
            if diff > Decimal('1.00') and diff != stated_total:
                loc_info = _find_text_location_for_snippet(text_locations, tm.group(0)) or {}
                page = loc_info.get('page') or 1
                bbox = loc_info.get('bbox')

                obs = (
                    f'Line item summation (₱{calc_sum:,.2f}) does not match stated grand total (₱{stated_total:,.2f}). '
                    f'Extracted {len(line_amts)} line items differing by ₱{diff:,.2f}.'
                )
                action = 'Verify and correct mathematical line item summation and stated totals before resubmitting.'

                findings.append(rule_engine.finding(
                    'financial_reconciliation_mismatch',
                    'warning',
                    rule_engine.CATEGORY_CALCULATION_ARITHMETIC_CONSISTENCY,
                    f'Line item summation (₱{calc_sum:,.2f}) does not match stated total (₱{stated_total:,.2f}).',
                    obs,
                    rule='financial_reconciliation_mismatch',
                    deficiency_category='financial_reconciliation_defect',
                    finding_observation=obs,
                    corrective_instruction=action,
                    automation_level='automated_with_review',
                    confidence='high',
                    page=page,
                    bbox=bbox,
                    evidence_text=tm.group(0),
                    reviewer_action=action,
                    provenance={'source': 'document_compliance_arithmetic', 'check': 'line_items_vs_grand_total'},
                ))
                break

    return findings
