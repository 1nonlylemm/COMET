"""Pure metric helpers for documentary checker evaluation.

This module intentionally avoids Flask, database, and provider state so metric
tests can run quickly and benchmark summaries can be reproduced.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from app.services import document_compliance_rule_engine as rule_engine


GROUND_TRUTH_SCHEMA_VERSION = 'document_checker_ground_truth_v1'

SUPPORTED_CHECKER_STATUSES = {
    'ready_for_approval',
    'review_required',
    'likely_return',
    'invalid_evidence',
    'check_failed',
}

SUPPORTED_RECOMMENDED_ACTIONS = {
    'approve_ready',
    'review_required',
    'return_for_revision',
    'manual_review',
}

RETURN_STATUSES = {'likely_return', 'invalid_evidence'}

FIELD_ALIAS_GROUPS = {
    'lgu': {'lgu', 'lgu_name', 'municipality', 'province'},
    'date': {'date', 'document_date', 'receipt_date'},
    'amount': {'amount', 'budget_amount', 'total_amount'},
    'reference_number': {'reference_number', 'receipt_number', 'ada_number', 'nca_number', 'nta_number'},
    'project_title': {'project_title', 'project_name', 'title'},
    'fiscal_year': {'fiscal_year', 'fy', 'year'},
}

FIELD_ALIAS_LOOKUP = {
    alias: canonical
    for canonical, aliases in FIELD_ALIAS_GROUPS.items()
    for alias in aliases
}


def levenshtein_distance(expected, actual):
    return _edit_distance(list(expected or ''), list(actual or ''))


def calculate_cer(expected, actual):
    expected = expected or ''
    actual = actual or ''
    edit_distance = levenshtein_distance(expected, actual)
    expected_length = len(expected)
    return {
        'edit_distance': edit_distance,
        'expected_length': expected_length,
        'actual_length': len(actual),
        'cer': _safe_ratio(edit_distance, expected_length),
    }


def calculate_wer(expected, actual):
    expected_tokens = _word_tokens(expected)
    actual_tokens = _word_tokens(actual)
    edit_distance = _edit_distance(expected_tokens, actual_tokens)
    expected_length = len(expected_tokens)
    return {
        'edit_distance': edit_distance,
        'expected_length': expected_length,
        'actual_length': len(actual_tokens),
        'wer': _safe_ratio(edit_distance, expected_length),
    }


def calculate_ocr_metrics(expected_ocr, predicted_ocr):
    expected_ocr = _as_dict(expected_ocr)
    predicted_ocr = _as_dict(predicted_ocr)

    reference_text = _ocr_reference_text(expected_ocr)
    predicted_text = _ocr_predicted_text(predicted_ocr)
    min_readable_chars = _optional_int(expected_ocr.get('min_readable_text_chars'))
    readable_expected = expected_ocr.get('readable_text_expected')
    if readable_expected is None:
        readable_expected = bool(reference_text or min_readable_chars)
    readable_expected = bool(readable_expected)

    readable_text_chars = _optional_int(predicted_ocr.get('readable_text_chars'))
    if readable_text_chars is None:
        readable_text_chars = len(predicted_text or '')
    extraction_failed = bool(predicted_ocr.get('extraction_failed'))
    if readable_expected and readable_text_chars == 0 and not (predicted_text or '').strip():
        extraction_failed = True

    character_error = calculate_cer(reference_text, predicted_text) if reference_text else None
    word_error = calculate_wer(reference_text, predicted_text) if reference_text else None
    readable_text_passed = None
    if readable_expected:
        minimum = min_readable_chars if min_readable_chars is not None else 1
        readable_text_passed = readable_text_chars >= minimum and not extraction_failed

    max_cer = _optional_float(expected_ocr.get('max_cer'))
    max_wer = _optional_float(expected_ocr.get('max_wer'))
    threshold_passed = True
    if max_cer is not None and character_error and character_error.get('cer') is not None:
        threshold_passed = threshold_passed and character_error['cer'] <= max_cer
    if max_wer is not None and word_error and word_error.get('wer') is not None:
        threshold_passed = threshold_passed and word_error['wer'] <= max_wer

    support = 1 if (reference_text or readable_expected or expected_ocr) else 0
    passed = True
    if support:
        passed = (
            threshold_passed
            and not extraction_failed
            and readable_text_passed is not False
        )

    return {
        'support': support,
        'text_support': 1 if reference_text else 0,
        'character_error': character_error,
        'word_error': word_error,
        'cer': character_error.get('cer') if character_error else None,
        'wer': word_error.get('wer') if word_error else None,
        'readable_text_expected': readable_expected,
        'readable_text_passed': readable_text_passed,
        'readable_text_chars': readable_text_chars,
        'min_readable_text_chars': min_readable_chars,
        'extraction_failed': extraction_failed,
        'confidence': _optional_float(predicted_ocr.get('confidence')),
        'max_cer': max_cer,
        'max_wer': max_wer,
        'passed': passed,
    }


def calculate_mapping_metrics(expected_mapping, predicted_mapping):
    expected_mapping = _as_dict(expected_mapping)
    predicted_mapping = _as_dict(predicted_mapping)

    expected_id = _optional_int(
        expected_mapping.get('project_requirement_id')
        or expected_mapping.get('expected_project_requirement_id')
        or expected_mapping.get('target_project_requirement_id')
    )
    suggested_id = _optional_int(
        predicted_mapping.get('suggested_project_requirement_id')
        or predicted_mapping.get('project_requirement_id')
        or predicted_mapping.get('target_project_requirement_id')
    )
    top_k = _optional_int(expected_mapping.get('top_k') or predicted_mapping.get('top_k')) or 3
    candidate_ids = _mapping_candidate_ids(predicted_mapping, suggested_id=suggested_id)
    top_k_candidates = candidate_ids[:top_k] if top_k > 0 else candidate_ids
    candidate_rank = _candidate_rank(expected_id, candidate_ids)

    support = 1 if expected_id is not None else 0
    exact_match = bool(support and suggested_id == expected_id)
    top_k_match = bool(support and expected_id in top_k_candidates)
    false_mapping = bool(support and suggested_id is not None and not exact_match)
    missing_mapping = bool(support and suggested_id is None)
    unexpected_mapping = bool(not support and suggested_id is not None)

    true_positive = 1 if exact_match else 0
    false_positive = 1 if false_mapping or unexpected_mapping else 0
    false_negative = 1 if support and not exact_match else 0

    return {
        'support': support,
        'expected_project_requirement_id': expected_id,
        'suggested_project_requirement_id': suggested_id,
        'candidate_project_requirement_ids': candidate_ids,
        'candidate_rank': candidate_rank,
        'top_k': top_k,
        'top_k_match': top_k_match if support else None,
        'exact_match': exact_match if support else None,
        'false_mapping': false_mapping,
        'missing_mapping': missing_mapping,
        'unexpected_mapping': unexpected_mapping,
        'aggregate': precision_recall_f1(true_positive, false_positive, false_negative),
        'passed': not support or exact_match,
    }


def precision_recall_f1(tp, fp, fn):
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None:
        f1 = 0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        'true_positive': tp,
        'false_positive': fp,
        'false_negative': fn,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'support': tp + fn,
    }


def calculate_status_metrics(expected_status, predicted_status):
    expected_status = _clean_token(expected_status)
    predicted_status = _clean_token(predicted_status)
    status_match = expected_status == predicted_status
    false_approval = (
        predicted_status == 'ready_for_approval'
        and expected_status != 'ready_for_approval'
    )
    false_return = (
        expected_status in {'ready_for_approval', 'review_required'}
        and predicted_status in RETURN_STATUSES
    )
    return {
        'expected_status': expected_status,
        'predicted_status': predicted_status,
        'status_match': status_match,
        'false_approval': false_approval,
        'false_return': false_return,
    }


def calculate_field_metrics(expected_fields, predicted_fields):
    expected_fields = _canonical_field_map(_as_dict(expected_fields))
    predicted_fields = _canonical_field_map(_flatten_predicted_fields(predicted_fields))

    fields = {}
    tp = 0
    fp = 0
    fn = 0
    expected_keys = set(expected_fields)
    predicted_keys = set(predicted_fields)

    for field_name in sorted(expected_keys):
        expected_payload = expected_fields.get(field_name) or {}
        predicted_payload = predicted_fields.get(field_name) or {}
        expected_value = expected_payload.get('value')
        predicted_present = field_name in predicted_fields and _has_value(predicted_payload.get('value'))
        predicted_value = predicted_payload.get('value')
        matched = predicted_present and _normalize_field_value(field_name, expected_value) == _normalize_field_value(field_name, predicted_value)

        if matched:
            tp += 1
        elif predicted_present:
            fp += 1
            fn += 1
        else:
            fn += 1

        fields[field_name] = {
            'expected': expected_value,
            'predicted': predicted_value,
            'expected_field_name': expected_payload.get('source_field_name') or field_name,
            'predicted_field_name': predicted_payload.get('source_field_name'),
            'matched': bool(matched),
            'missing': not predicted_present,
        }

    for field_name in sorted(predicted_keys - expected_keys):
        predicted_payload = predicted_fields.get(field_name) or {}
        if not _has_value(predicted_payload.get('value')):
            continue
        fp += 1
        fields[field_name] = {
            'expected': None,
            'predicted': predicted_payload.get('value'),
            'expected_field_name': None,
            'predicted_field_name': predicted_payload.get('source_field_name') or field_name,
            'matched': False,
            'unexpected': True,
        }

    return {
        'fields': fields,
        'aggregate': precision_recall_f1(tp, fp, fn),
        'passed': fp == 0 and fn == 0,
    }


def calculate_finding_metrics(expected_findings, forbidden_findings, predicted_findings):
    expected_ids = _unique_clean_list(expected_findings)
    forbidden_ids = _unique_clean_list(forbidden_findings)
    predicted_items = [
        item for item in (predicted_findings or [])
        if isinstance(item, dict) and _clean_token(item.get('id'))
    ]
    predicted_ids = _unique_clean_list([item.get('id') for item in predicted_items])
    predicted_severity_by_id = {
        _clean_token(item.get('id')): _clean_token(item.get('severity'))
        for item in predicted_items
    }

    matched = [item for item in expected_ids if item in predicted_ids]
    missing = [item for item in expected_ids if item not in predicted_ids]
    unexpected = [item for item in forbidden_ids if item in predicted_ids]

    critical_blocker_false_positive = any(
        predicted_severity_by_id.get(item) == 'blocker'
        for item in unexpected
    )
    critical_blocker_false_negative = bool(missing)

    return {
        'expected': {
            'total': len(expected_ids),
            'matched': matched,
            'missing': missing,
        },
        'forbidden': {
            'total': len(forbidden_ids),
            'unexpected': unexpected,
        },
        'predicted_ids': predicted_ids,
        'critical_blocker_false_positive': critical_blocker_false_positive,
        'critical_blocker_false_negative': critical_blocker_false_negative,
        'passed': not missing and not unexpected,
    }


def bbox_iou(expected_bbox, predicted_bbox):
    expected = _coerce_bbox(expected_bbox)
    predicted = _coerce_bbox(predicted_bbox)
    if not expected or not predicted:
        return 0

    x1 = max(expected[0], predicted[0])
    y1 = max(expected[1], predicted[1])
    x2 = min(expected[2], predicted[2])
    y2 = min(expected[3], predicted[3])
    intersection_width = max(0, x2 - x1)
    intersection_height = max(0, y2 - y1)
    intersection = intersection_width * intersection_height
    expected_area = max(0, expected[2] - expected[0]) * max(0, expected[3] - expected[1])
    predicted_area = max(0, predicted[2] - predicted[0]) * max(0, predicted[3] - predicted[1])
    union = expected_area + predicted_area - intersection
    return _safe_ratio(intersection, union) or 0


def calculate_annotation_metrics(expected_annotations, predicted_annotations):
    expected_annotations = [item for item in (expected_annotations or []) if isinstance(item, dict)]
    predicted_annotations = [item for item in (predicted_annotations or []) if isinstance(item, dict)]

    items = []
    matched = 0
    for expected in expected_annotations:
        finding_id = _clean_token(expected.get('finding_id') or expected.get('id'))
        page = expected.get('page')
        threshold = _to_float(expected.get('min_iou'), default=0.5)
        candidates = [
            predicted for predicted in predicted_annotations
            if _clean_token(predicted.get('finding_id') or predicted.get('id')) == finding_id
            and predicted.get('page') == page
        ]
        best_iou = 0
        best_candidate = None
        for candidate in candidates:
            candidate_iou = bbox_iou(expected.get('bbox'), candidate.get('bbox'))
            if candidate_iou > best_iou:
                best_iou = candidate_iou
                best_candidate = candidate
        item_matched = bool(best_candidate) and best_iou >= threshold
        if item_matched:
            matched += 1
        items.append({
            'finding_id': finding_id,
            'page': page,
            'matched': item_matched,
            'iou': best_iou,
            'min_iou': threshold,
        })

    support = len(expected_annotations)
    return {
        'support': support,
        'matched': matched,
        'missing': support - matched,
        'accuracy': _safe_ratio(matched, support),
        'items': items,
    }


def calculate_layout_metrics(expected_layout, predicted_layout):
    expected_layout = _as_dict(expected_layout)
    predicted_layout = _as_dict(predicted_layout)

    elements = _compare_layout_items(
        _layout_collection(expected_layout, 'layout_elements', 'elements'),
        _layout_collection(predicted_layout, 'layout_elements', 'elements'),
        key_getter=_layout_item_type,
    )
    overlap_issues = _compare_layout_items(
        _layout_collection(expected_layout, 'layout_issues', 'overlap_issues'),
        _layout_collection(predicted_layout, 'layout_issues', 'overlap_issues'),
        key_getter=_layout_item_id,
    )
    support = elements['aggregate']['support'] + overlap_issues['aggregate']['support']
    return {
        'support': support,
        'elements': elements,
        'overlap_issues': overlap_issues,
        'passed': (
            elements['aggregate']['false_positive'] == 0
            and elements['aggregate']['false_negative'] == 0
            and overlap_issues['aggregate']['false_positive'] == 0
            and overlap_issues['aggregate']['false_negative'] == 0
        ),
    }


def calculate_confusion_matrix(expected_labels, predicted_labels):
    expected_labels = [_clean_token(item) for item in (expected_labels or [])]
    predicted_labels = [_clean_token(item) for item in (predicted_labels or [])]
    labels = sorted({item for item in expected_labels + predicted_labels if item})
    matrix = {
        expected: {predicted: 0 for predicted in labels}
        for expected in labels
    }
    for expected, predicted in zip(expected_labels, predicted_labels):
        if expected not in matrix:
            matrix[expected] = {label: 0 for label in labels}
        if predicted not in matrix[expected]:
            matrix[expected][predicted] = 0
        matrix[expected][predicted] += 1
    return {
        'labels': labels,
        'matrix': matrix,
        'total': min(len(expected_labels), len(predicted_labels)),
    }


def validate_ground_truth(payload):
    cleaned = dict(payload or {})
    errors = {}

    for field_name in ('schema_version', 'case_key', 'expected_evidence_type', 'expected_status', 'expected_recommended_action'):
        value = cleaned.get(field_name)
        if isinstance(value, str):
            cleaned[field_name] = value.strip()
        if not cleaned.get(field_name):
            errors[field_name] = 'This field is required.'

    if cleaned.get('schema_version') and cleaned.get('schema_version') != GROUND_TRUTH_SCHEMA_VERSION:
        errors['schema_version'] = f'Unsupported schema version. Expected {GROUND_TRUTH_SCHEMA_VERSION}.'

    evidence_type = _clean_token(cleaned.get('expected_evidence_type'))
    if evidence_type and evidence_type not in rule_engine.SUPPORTED_EVIDENCE_TYPES:
        errors['expected_evidence_type'] = 'Unsupported evidence type.'

    status = _clean_token(cleaned.get('expected_status'))
    if status and status not in SUPPORTED_CHECKER_STATUSES:
        errors['expected_status'] = 'Unsupported checker status.'

    action = _clean_token(cleaned.get('expected_recommended_action'))
    if action and action not in SUPPORTED_RECOMMENDED_ACTIONS:
        errors['expected_recommended_action'] = 'Unsupported recommended action.'

    for index, annotation in enumerate(cleaned.get('expected_annotations') or []):
        bbox = annotation.get('bbox') if isinstance(annotation, dict) else None
        if not _is_normalized_bbox(bbox):
            errors[f'expected_annotations.{index}.bbox'] = 'Expected a normalized bbox [x1, y1, x2, y2] between 0 and 1.'

    _validate_expected_ocr(cleaned.get('expected_ocr'), errors)
    _validate_expected_mapping(cleaned.get('expected_mapping'), errors)
    _validate_expected_layout(cleaned.get('expected_layout'), errors)

    return cleaned, errors


def compare_checker_output(ground_truth, checker_output):
    ground_truth = ground_truth or {}
    checker_output = checker_output or {}

    expected_evidence_type = _clean_token(ground_truth.get('expected_evidence_type'))
    predicted_evidence_type = _predicted_evidence_type(checker_output)
    status = calculate_status_metrics(
        ground_truth.get('expected_status'),
        checker_output.get('status'),
    )
    fields = calculate_field_metrics(
        ground_truth.get('expected_fields') or {},
        checker_output.get('extracted_fields') or {},
    )
    mapping = calculate_mapping_metrics(
        ground_truth.get('expected_mapping') or {},
        _predicted_mapping_output(checker_output),
    )
    ocr = calculate_ocr_metrics(
        ground_truth.get('expected_ocr') or {},
        _predicted_ocr_output(checker_output),
    )
    findings = calculate_finding_metrics(
        ground_truth.get('expected_findings') or [],
        ground_truth.get('forbidden_findings') or [],
        checker_output.get('findings') or [],
    )
    annotations = calculate_annotation_metrics(
        ground_truth.get('expected_annotations') or [],
        checker_output.get('annotations') or [],
    )
    layout = calculate_layout_metrics(
        ground_truth.get('expected_layout') or {},
        _predicted_layout_output(checker_output),
    )
    expected_action = _clean_token(ground_truth.get('expected_recommended_action'))
    predicted_action = _clean_token(checker_output.get('recommended_action'))
    evidence_type_match = expected_evidence_type == predicted_evidence_type

    passed = (
        status['status_match']
        and expected_action == predicted_action
        and evidence_type_match
        and fields['passed']
        and mapping['passed']
        and ocr['passed']
        and findings['passed']
        and not status['false_approval']
        and not status['false_return']
    )

    if annotations['support']:
        passed = passed and annotations['matched'] == annotations['support']
    if layout['support']:
        passed = passed and layout['passed']

    return {
        'case_key': ground_truth.get('case_key'),
        'evidence_type': {
            'expected': expected_evidence_type,
            'predicted': predicted_evidence_type,
            'matched': evidence_type_match,
        },
        'status': status,
        'recommended_action': {
            'expected': expected_action,
            'predicted': predicted_action,
        },
        'recommended_action_match': expected_action == predicted_action,
        'fields': fields,
        'mapping': mapping,
        'ocr': ocr,
        'findings': findings,
        'annotations': annotations,
        'layout': layout,
        'passed': passed,
    }


def _edit_distance(expected, actual):
    expected = expected or []
    actual = actual or []
    if not expected:
        return len(actual)
    if not actual:
        return len(expected)

    previous = list(range(len(actual) + 1))
    for i, expected_item in enumerate(expected, start=1):
        current = [i]
        for j, actual_item in enumerate(actual, start=1):
            insertion = current[j - 1] + 1
            deletion = previous[j] + 1
            substitution = previous[j - 1] + (expected_item != actual_item)
            current.append(min(insertion, deletion, substitution))
        previous = current
    return previous[-1]


def _word_tokens(value):
    return _normalize_text(value).split()


def _normalize_text(value):
    value = '' if value is None else str(value)
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r'\s+', ' ', value)
    return value.strip().lower()


def _clean_token(value):
    return _normalize_text(value).replace(' ', '_') if value is not None else None


def _safe_ratio(numerator, denominator):
    if denominator == 0:
        return None
    return numerator / denominator


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _optional_int(value):
    try:
        if value is None or value == '':
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value):
    parsed = _to_float(value)
    return parsed


def _has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _canonical_field_name(field_name):
    cleaned = _clean_token(field_name)
    return FIELD_ALIAS_LOOKUP.get(cleaned, cleaned)


def _canonical_field_map(field_values):
    canonical = {}
    for field_name, value in _as_dict(field_values).items():
        canonical_name = _canonical_field_name(field_name)
        if not canonical_name:
            continue
        if canonical_name in canonical and _has_value(canonical[canonical_name].get('value')):
            continue
        canonical[canonical_name] = {
            'source_field_name': field_name,
            'value': value,
        }
    return canonical


def _flatten_predicted_fields(predicted_fields):
    predicted_fields = _as_dict(predicted_fields)
    flattened = {}

    ignored_keys = {
        'expected',
        'presence',
        'extraction_metadata',
        'file_name',
        'mime_type',
        'readable_text_chars',
        'latest_scan_id',
        'latest_scan_suggested_project_requirement_id',
        'language_quality',
        'visual_summary',
        'photo_metadata',
        'photo_evidence_checks',
        'visual_evidence_summary',
    }

    for key, value in predicted_fields.items():
        if key in ignored_keys:
            continue
        if key == 'field_evidence' and isinstance(value, dict):
            flattened.update(_flatten_field_evidence(value))
            continue
        if isinstance(value, dict) and 'value' in value:
            flattened[key] = value.get('value')
        elif not isinstance(value, (dict, list)):
            flattened[key] = value

    return flattened


def _flatten_field_evidence(field_evidence):
    flattened = {}

    matches = field_evidence.get('matches')
    if isinstance(matches, dict):
        for key, value in matches.items():
            if not isinstance(value, dict):
                continue
            field_value = _field_evidence_value(value)
            if _has_value(field_value):
                flattened[key] = field_value

    fields = field_evidence.get('fields')
    if isinstance(fields, dict):
        for key, value in fields.items():
            if key in flattened or not isinstance(value, dict):
                continue
            field_value = _field_evidence_value(value.get('best'))
            if not _has_value(field_value):
                field_value = _first_candidate_value(value.get('candidates'))
            if _has_value(field_value):
                flattened[key] = field_value

    ignored_keys = {
        'aliases_version',
        'evidence_type',
        'field_zones',
        'fields',
        'matches',
        'ocr_corrections_version',
        'profile',
    }
    for key, value in field_evidence.items():
        if key in ignored_keys:
            continue
        if isinstance(value, dict):
            if 'matched_value' in value:
                flattened[key] = value.get('matched_value')
            elif 'value' in value:
                flattened[key] = value.get('value')
            elif value.get('candidates') and isinstance(value.get('candidates'), list):
                field_value = _first_candidate_value(value.get('candidates'))
                if _has_value(field_value):
                    flattened[key] = field_value
        elif not isinstance(value, list):
            flattened[key] = value
    return flattened


def _field_evidence_value(value):
    if not isinstance(value, dict):
        return None
    candidate = value.get('candidate') if isinstance(value.get('candidate'), dict) else {}
    for key in ('actual', 'matched_value', 'normalized_value', 'value', 'matched_text', 'text'):
        if _has_value(value.get(key)):
            return value.get(key)
    for key in ('normalized_value', 'matched_text', 'value', 'text'):
        if _has_value(candidate.get(key)):
            return candidate.get(key)
    return None


def _first_candidate_value(candidates):
    if not isinstance(candidates, list) or not candidates:
        return None
    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        return None
    return (
        first_candidate.get('normalized_value')
        or first_candidate.get('matched_text')
        or first_candidate.get('value')
        or first_candidate.get('text')
    )


def _normalize_field_value(field_name, value):
    field_name = _clean_token(field_name) or ''
    if value is None:
        return None
    if field_name in {'lgu', 'lgu_name', 'municipality', 'province'}:
        return _normalize_text(value)
    if field_name in {'date', 'document_date', 'receipt_date'}:
        return _normalize_date(value)
    if field_name in {'amount', 'budget_amount', 'total_amount'}:
        return _normalize_amount(value)
    if field_name in {'reference_number', 'receipt_number', 'ada_number', 'nca_number', 'nta_number'}:
        return re.sub(r'[^a-z0-9]', '', _normalize_text(value))
    return _normalize_text(value)


def _normalize_date(value):
    text = _normalize_text(value)
    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text)
    formats = (
        '%Y-%m-%d',
        '%B %d, %Y',
        '%b %d, %Y',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%m-%d-%Y',
        '%d-%m-%Y',
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _normalize_amount(value):
    text = str(value)
    cleaned = re.sub(r'[^0-9.\-]', '', text)
    if cleaned in {'', '.', '-', '-.'}:
        return _normalize_text(value)
    try:
        return Decimal(cleaned).quantize(Decimal('0.01'))
    except InvalidOperation:
        return _normalize_text(value)


def _unique_clean_list(values):
    output = []
    seen = set()
    for value in values or []:
        cleaned = _clean_token(value)
        if cleaned and cleaned not in seen:
            output.append(cleaned)
            seen.add(cleaned)
    return output


def _coerce_bbox(value):
    if isinstance(value, dict):
        x = _to_float(value.get('x'))
        y = _to_float(value.get('y'))
        width = _to_float(value.get('width'))
        height = _to_float(value.get('height'))
        if None in {x, y, width, height}:
            return None
        return [x, y, x + width, y + height]
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    numbers = [_to_float(item) for item in value]
    if any(item is None for item in numbers):
        return None
    x1, y1, x2, y2 = numbers
    if x2 < x1 or y2 < y1:
        x2 = x1 + max(0, x2)
        y2 = y1 + max(0, y2)
    return [x1, y1, x2, y2]


def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_normalized_bbox(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return False
    numbers = [_to_float(item) for item in value]
    if any(item is None for item in numbers):
        return False
    x1, y1, x2, y2 = numbers
    return (
        0 <= x1 <= 1
        and 0 <= y1 <= 1
        and 0 <= x2 <= 1
        and 0 <= y2 <= 1
        and x2 >= x1
        and y2 >= y1
    )


def _validate_expected_ocr(expected_ocr, errors):
    if expected_ocr in (None, ''):
        return
    if not isinstance(expected_ocr, dict):
        errors['expected_ocr'] = 'Expected an object with OCR benchmark labels.'
        return
    if expected_ocr.get('reference_text') is not None and not isinstance(expected_ocr.get('reference_text'), str):
        errors['expected_ocr.reference_text'] = 'Expected reviewer-transcribed OCR reference text.'
    min_chars = expected_ocr.get('min_readable_text_chars')
    if min_chars is not None:
        parsed = _optional_int(min_chars)
        if parsed is None or parsed < 0:
            errors['expected_ocr.min_readable_text_chars'] = 'Expected a non-negative integer.'
    if expected_ocr.get('readable_text_expected') is not None and not isinstance(expected_ocr.get('readable_text_expected'), bool):
        errors['expected_ocr.readable_text_expected'] = 'Expected true or false.'
    for field_name in ('max_cer', 'max_wer'):
        value = expected_ocr.get(field_name)
        if value is not None:
            parsed = _optional_float(value)
            if parsed is None or parsed < 0:
                errors[f'expected_ocr.{field_name}'] = 'Expected a non-negative number.'


def _validate_expected_mapping(expected_mapping, errors):
    if expected_mapping in (None, ''):
        return
    if not isinstance(expected_mapping, dict):
        errors['expected_mapping'] = 'Expected an object with document mapping benchmark labels.'
        return
    expected_id = expected_mapping.get('project_requirement_id') or expected_mapping.get('expected_project_requirement_id')
    if expected_id is not None and _optional_int(expected_id) is None:
        errors['expected_mapping.project_requirement_id'] = 'Expected an integer project requirement id.'
    top_k = expected_mapping.get('top_k')
    if top_k is not None:
        parsed = _optional_int(top_k)
        if parsed is None or parsed <= 0:
            errors['expected_mapping.top_k'] = 'Expected a positive integer.'


def _validate_expected_layout(expected_layout, errors):
    if expected_layout in (None, ''):
        return
    if not isinstance(expected_layout, dict):
        errors['expected_layout'] = 'Expected expected_layout to be an object.'
        return

    layout_keys = {
        'layout_elements': 'element',
        'elements': 'element',
        'layout_issues': 'issue',
        'overlap_issues': 'issue',
    }
    for key, item_kind in layout_keys.items():
        if key not in expected_layout:
            continue
        items = expected_layout.get(key)
        if not isinstance(items, list):
            errors[f'expected_layout.{key}'] = 'Expected a list of layout entries.'
            continue
        for index, item in enumerate(items):
            path = f'expected_layout.{key}.{index}'
            if not isinstance(item, dict):
                errors[path] = 'Expected a layout entry object.'
                continue
            bbox = item.get('bbox')
            if bbox is not None and not _is_normalized_bbox(bbox):
                errors[f'{path}.bbox'] = 'Expected a normalized bbox [x1, y1, x2, y2] between 0 and 1.'
            page = item.get('page')
            if page is not None and _layout_page_number(page) is None:
                errors[f'{path}.page'] = 'Expected page to be a positive integer.'
            min_iou = item.get('min_iou')
            if min_iou is not None and not _is_ratio(min_iou):
                errors[f'{path}.min_iou'] = 'Expected min_iou to be between 0 and 1.'
            if item_kind == 'element' and not _layout_item_type(item):
                errors[f'{path}.type'] = 'Expected a layout element type, role, or label.'
            if item_kind == 'issue' and not _layout_item_id(item):
                errors[f'{path}.id'] = 'Expected a layout issue id, finding_id, type, role, or label.'


def _layout_page_number(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 1 else None


def _is_ratio(value):
    parsed = _to_float(value)
    return parsed is not None and 0 <= parsed <= 1


def _layout_collection(payload, *keys):
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _compare_layout_items(expected_items, predicted_items, *, key_getter):
    expected_items = list(expected_items or [])
    predicted_items = list(predicted_items or [])
    matched_expected = set()
    matched_predicted = set()
    matches = []

    for expected_index, expected in enumerate(expected_items):
        expected_key = key_getter(expected)
        if not expected_key:
            continue
        best_index = None
        best_iou = -1
        for predicted_index, predicted in enumerate(predicted_items):
            if predicted_index in matched_predicted:
                continue
            if key_getter(predicted) != expected_key:
                continue
            if _layout_page(predicted) != _layout_page(expected):
                continue
            iou = _layout_iou(expected, predicted)
            if iou >= _layout_min_iou(expected) and iou > best_iou:
                best_index = predicted_index
                best_iou = iou
        if best_index is None:
            continue
        matched_expected.add(expected_index)
        matched_predicted.add(best_index)
        matches.append({
            'key': expected_key,
            'expected_id': _layout_item_id(expected),
            'predicted_id': _layout_item_id(predicted_items[best_index]),
            'page': _layout_page(expected),
            'iou': best_iou,
        })

    true_positive = len(matches)
    false_negative = max(len(expected_items) - true_positive, 0)
    false_positive = max(len(predicted_items) - true_positive, 0)
    return {
        'aggregate': precision_recall_f1(true_positive, false_positive, false_negative),
        'matched_items': matches,
        'by_type': _layout_counts_by_key(
            expected_items,
            predicted_items,
            matched_expected,
            matched_predicted,
            key_getter=key_getter,
        ),
    }


def _layout_counts_by_key(expected_items, predicted_items, matched_expected, matched_predicted, *, key_getter):
    keys = sorted({
        key_getter(item)
        for item in list(expected_items or []) + list(predicted_items or [])
        if key_getter(item)
    })
    counts = {}
    for key in keys:
        expected_indexes = [
            index for index, item in enumerate(expected_items)
            if key_getter(item) == key
        ]
        predicted_indexes = [
            index for index, item in enumerate(predicted_items)
            if key_getter(item) == key
        ]
        matched = sum(1 for index in expected_indexes if index in matched_expected)
        missing = sum(1 for index in expected_indexes if index not in matched_expected)
        unexpected = sum(1 for index in predicted_indexes if index not in matched_predicted)
        counts[key] = {
            'expected': len(expected_indexes),
            'predicted': len(predicted_indexes),
            'matched': matched,
            'missing': missing,
            'unexpected': unexpected,
            'aggregate': precision_recall_f1(matched, unexpected, missing),
        }
    return counts


def _layout_iou(expected, predicted):
    expected_bbox = expected.get('bbox') if isinstance(expected, dict) else None
    predicted_bbox = predicted.get('bbox') if isinstance(predicted, dict) else None
    if expected_bbox is None:
        return 1
    return bbox_iou(expected_bbox, predicted_bbox)


def _layout_min_iou(item):
    return _to_float((item or {}).get('min_iou'), default=0.5)


def _predicted_mapping_output(checker_output):
    checker_output = checker_output if isinstance(checker_output, dict) else {}
    explicit = (
        checker_output.get('mapping')
        or checker_output.get('document_mapping')
        or checker_output.get('nlp_mapping')
        or {}
    )
    output = dict(explicit) if isinstance(explicit, dict) else {}
    extracted_fields = checker_output.get('extracted_fields') if isinstance(checker_output.get('extracted_fields'), dict) else {}
    score_details = checker_output.get('score_details') if isinstance(checker_output.get('score_details'), dict) else {}
    metadata = extracted_fields.get('extraction_metadata') if isinstance(extracted_fields.get('extraction_metadata'), dict) else {}

    if output.get('suggested_project_requirement_id') is None:
        for source in (checker_output, extracted_fields, score_details, metadata):
            value = (
                source.get('suggested_project_requirement_id')
                or source.get('latest_scan_suggested_project_requirement_id')
                or source.get('project_requirement_id')
            )
            if value is not None:
                output['suggested_project_requirement_id'] = value
                break

    if not isinstance(output.get('candidate_rankings'), list):
        for source in (checker_output, extracted_fields, score_details, metadata):
            candidates = (
                source.get('candidate_rankings')
                or source.get('mapping_candidates')
                or source.get('candidates')
            )
            if isinstance(candidates, list):
                output['candidate_rankings'] = candidates
                break

    return output


def _mapping_candidate_ids(predicted_mapping, *, suggested_id=None):
    candidates = predicted_mapping.get('candidate_rankings')
    if not isinstance(candidates, list):
        candidates = predicted_mapping.get('mapping_candidates')
    if not isinstance(candidates, list):
        candidates = predicted_mapping.get('candidates')
    if not isinstance(candidates, list):
        candidates = []

    output = []
    seen = set()
    for item in candidates:
        if isinstance(item, dict):
            value = (
                item.get('project_requirement_id')
                or item.get('suggested_project_requirement_id')
                or item.get('id')
            )
        else:
            value = item
        parsed = _optional_int(value)
        if parsed is not None and parsed not in seen:
            output.append(parsed)
            seen.add(parsed)

    if suggested_id is not None and suggested_id not in seen:
        output.insert(0, suggested_id)
    return output


def _candidate_rank(expected_id, candidate_ids):
    if expected_id is None:
        return None
    for index, candidate_id in enumerate(candidate_ids or [], start=1):
        if candidate_id == expected_id:
            return index
    return None


def _ocr_reference_text(expected_ocr):
    for key in ('reference_text', 'gold_text', 'expected_text', 'transcribed_text'):
        value = expected_ocr.get(key)
        if _has_value(value):
            return str(value)
    return ''


def _ocr_predicted_text(predicted_ocr):
    for key in ('text', 'ocr_text', 'extracted_text', 'readable_text', 'raw_text'):
        value = predicted_ocr.get(key)
        if _has_value(value):
            return str(value)
    return ''


def _predicted_ocr_output(checker_output):
    checker_output = checker_output if isinstance(checker_output, dict) else {}
    explicit = (
        checker_output.get('ocr')
        or checker_output.get('ocr_metrics')
        or checker_output.get('ocr_result')
        or {}
    )
    output = dict(explicit) if isinstance(explicit, dict) else {}
    extracted_fields = checker_output.get('extracted_fields') if isinstance(checker_output.get('extracted_fields'), dict) else {}
    metadata = extracted_fields.get('extraction_metadata') if isinstance(extracted_fields.get('extraction_metadata'), dict) else {}

    for key in ('text', 'ocr_text', 'extracted_text', 'readable_text', 'raw_text'):
        if not _has_value(output.get(key)) and _has_value(checker_output.get(key)):
            output[key] = checker_output.get(key)
        if not _has_value(output.get(key)) and _has_value(extracted_fields.get(key)):
            output[key] = extracted_fields.get(key)
        if not _has_value(output.get(key)) and _has_value(metadata.get(key)):
            output[key] = metadata.get(key)

    if output.get('readable_text_chars') is None and extracted_fields.get('readable_text_chars') is not None:
        output['readable_text_chars'] = extracted_fields.get('readable_text_chars')
    if output.get('confidence') is None:
        for key in ('ocr_confidence', 'average_confidence', 'confidence'):
            if metadata.get(key) is not None:
                output['confidence'] = metadata.get(key)
                break
    if output.get('extraction_failed') is None:
        for key in ('ocr_failed', 'extraction_failed', 'failed'):
            if metadata.get(key) is not None:
                output['extraction_failed'] = metadata.get(key)
                break

    return output


def _layout_item_type(item):
    return _clean_token((item or {}).get('type') or (item or {}).get('role') or (item or {}).get('label'))


def _layout_item_id(item):
    value = _clean_token((item or {}).get('id') or (item or {}).get('finding_id') or _layout_item_type(item))
    if isinstance(value, str) and value.startswith('layout_overlap:'):
        return value.split(':', 1)[1]
    return value


def _layout_page(item):
    try:
        return int((item or {}).get('page') or 1)
    except (TypeError, ValueError):
        return 1


def _predicted_layout_output(checker_output):
    checker_output = checker_output if isinstance(checker_output, dict) else {}
    explicit = checker_output.get('layout') or checker_output.get('predicted_layout') or {}
    explicit = explicit if isinstance(explicit, dict) else {}
    extracted_fields = checker_output.get('extracted_fields') if isinstance(checker_output.get('extracted_fields'), dict) else {}
    metadata = extracted_fields.get('extraction_metadata') if isinstance(extracted_fields.get('extraction_metadata'), dict) else {}
    metadata_layout = metadata.get('layout') if isinstance(metadata.get('layout'), dict) else {}

    layout_elements = (
        explicit.get('layout_elements')
        or explicit.get('elements')
        or metadata.get('layout_elements')
        or metadata_layout.get('layout_elements')
        or metadata_layout.get('elements')
        or []
    )
    layout_issues = (
        explicit.get('layout_issues')
        or explicit.get('overlap_issues')
        or []
    )
    derived_issues = _layout_issues_from_findings(checker_output.get('findings') or [])
    return {
        'layout_elements': layout_elements if isinstance(layout_elements, list) else [],
        'layout_issues': [
            item for item in list(layout_issues if isinstance(layout_issues, list) else []) + derived_issues
            if isinstance(item, dict)
        ],
    }


def _layout_issues_from_findings(findings):
    issues = []
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        finding_id = _clean_token(finding.get('id'))
        if not isinstance(finding_id, str) or not finding_id.startswith('layout_overlap:'):
            continue
        locations = finding.get('locations') if isinstance(finding.get('locations'), list) else []
        if not locations:
            issues.append({'id': finding_id, 'page': 1})
            continue
        for location in locations:
            if not isinstance(location, dict):
                continue
            issues.append({
                'id': finding_id,
                'page': _layout_page(location),
                'bbox': location.get('bbox'),
            })
    return issues


def _predicted_evidence_type(checker_output):
    score_details = checker_output.get('score_details') if isinstance(checker_output, dict) else {}
    score_details = score_details if isinstance(score_details, dict) else {}
    evidence_type = score_details.get('evidence_type')
    if not evidence_type:
        extracted_fields = checker_output.get('extracted_fields') if isinstance(checker_output, dict) else {}
        if isinstance(extracted_fields, dict):
            evidence_type = extracted_fields.get('evidence_type')
    return _clean_token(evidence_type)
