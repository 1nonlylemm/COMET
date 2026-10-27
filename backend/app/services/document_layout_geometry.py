"""Geometry helpers for document layout checks.

The functions in this module operate on normalized page-relative bounding
boxes. They are intentionally provider-agnostic so OCR, Textract, future layout
models, and reviewer-labeled fixtures can feed the same overlap rules.
"""


DEFAULT_MAX_INTERSECTION_RATIO = 0.0
SUPPORTED_SEVERITIES = {"blocker", "warning", "minor_warning", "info"}


def boxes_intersect(a, b):
    first = _coerce_bbox(a)
    second = _coerce_bbox(b)
    if not first or not second:
        return False
    return _intersection_area(first, second) > 0


def intersection_ratio(a, b):
    first = _coerce_bbox(a)
    second = _coerce_bbox(b)
    if not first or not second:
        return 0
    intersection = _intersection_area(first, second)
    if intersection <= 0:
        return 0
    first_area = _area(first)
    second_area = _area(second)
    denominator = min(first_area, second_area)
    if denominator <= 0:
        return 0
    return round(intersection / denominator, 4)


def detect_disallowed_overlaps(elements, rules):
    elements = [item for item in (elements or []) if isinstance(item, dict)]
    rules = [item for item in (rules or []) if isinstance(item, dict)]
    issues = []

    for rule in rules:
        if rule.get("allowed") is True:
            continue
        selector_a = rule.get("element_a") or rule.get("element_a_type") or rule.get("a")
        selector_b = rule.get("element_b") or rule.get("element_b_type") or rule.get("b")
        if not selector_a or not selector_b:
            continue

        max_ratio = _float_value(rule.get("max_intersection_ratio"), DEFAULT_MAX_INTERSECTION_RATIO)
        severity = _severity(rule.get("severity"))
        rule_id = _rule_id(rule, selector_a, selector_b)
        for element_a in elements:
            if not _matches_selector(element_a, selector_a):
                continue
            for element_b in elements:
                if element_a is element_b or not _matches_selector(element_b, selector_b):
                    continue
                if _page(element_a) != _page(element_b):
                    continue
                ratio = intersection_ratio(element_a.get("bbox"), element_b.get("bbox"))
                if ratio <= max_ratio:
                    continue
                bbox = _intersection_bbox(
                    _coerce_bbox(element_a.get("bbox")),
                    _coerce_bbox(element_b.get("bbox")),
                )
                if not bbox:
                    continue
                issues.append({
                    "id": rule_id,
                    "severity": severity,
                    "page": _page(element_a),
                    "element_a": _element_name(element_a),
                    "element_b": _element_name(element_b),
                    "element_a_type": _element_type(element_a),
                    "element_b_type": _element_type(element_b),
                    "bbox": bbox,
                    "overlap_ratio": ratio,
                    "max_intersection_ratio": max_ratio,
                })

    return issues


def _coerce_bbox(value):
    if isinstance(value, dict):
        x = _float_value(value.get("x"))
        y = _float_value(value.get("y"))
        width = _float_value(value.get("width", value.get("w")))
        height = _float_value(value.get("height", value.get("h")))
        if None in {x, y, width, height}:
            return None
        return _clamp_bbox([x, y, x + width, y + height])

    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    numbers = [_float_value(item) for item in value]
    if any(item is None for item in numbers):
        return None
    x1, y1, x2, y2 = numbers
    if max(numbers) > 1:
        if max(numbers) > 100:
            return None
        x1, y1, x2, y2 = [item / 100 for item in numbers]
    if x2 < x1 or y2 < y1:
        return None
    return _clamp_bbox([x1, y1, x2, y2])


def _intersection_bbox(first, second):
    if not first or not second:
        return None
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    if x2 <= x1 or y2 <= y1:
        return None
    return [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)]


def _intersection_area(first, second):
    intersection = _intersection_bbox(first, second)
    if not intersection:
        return 0
    return _area(intersection)


def _area(bbox):
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def _matches_selector(element, selector):
    selector = _normalize(selector)
    candidates = {
        _normalize(element.get("id")),
        _normalize(element.get("type")),
        _normalize(element.get("role")),
        _normalize(element.get("label")),
        _normalize(element.get("name")),
    }
    return selector in candidates


def _element_name(element):
    return str(element.get("id") or element.get("name") or element.get("label") or _element_type(element))


def _element_type(element):
    return str(element.get("type") or element.get("role") or "layout_element")


def _rule_id(rule, selector_a, selector_b):
    raw = rule.get("id") or f"{selector_a}_must_not_overlap_{selector_b}"
    return _normalize(raw) or "layout_overlap"


def _page(element):
    try:
        return int(element.get("page") or 1)
    except (TypeError, ValueError):
        return 1


def _severity(value):
    normalized = _normalize(value)
    return normalized if normalized in SUPPORTED_SEVERITIES else "warning"


def _normalize(value):
    return str(value or "").strip().lower().replace(" ", "_")


def _float_value(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp_bbox(bbox):
    x1, y1, x2, y2 = bbox
    x1 = _clamp(x1)
    y1 = _clamp(y1)
    x2 = _clamp(x2)
    y2 = _clamp(y2)
    if x2 < x1 or y2 < y1:
        return None
    return [x1, y1, x2, y2]


def _clamp(value):
    return max(0.0, min(1.0, float(value)))
