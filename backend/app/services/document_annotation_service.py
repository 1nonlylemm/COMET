"""Annotation payload builder for documentary compliance findings.

The compliance checker stores findings as the source of truth. This service
derives a stable, page-relative annotation payload from those findings so the
review UI can draw highlights without adding another persistence table for the
first implementation slice.
"""


DEFAULT_BBOX_TYPE = 'detected_text'


def build_annotations(findings):
    """Return normalized page annotations derived from finding locations.

    Supported location shapes:
    - ``bbox`` as ``{"x", "y", "width", "height"}`` in normalized units.
    - ``bbox`` as ``[x, y, width, height]`` in normalized units.
    - ``bbox`` values in 0..100 percentages.
    - absolute coordinates when ``page_width`` and ``page_height`` are present.

    Locations that cannot be normalized are still returned with
    ``renderable == False`` and ``source_bbox`` so reviewers can see that the
    checker had location metadata even if the UI cannot safely draw it.
    """
    annotations = []
    for finding_number, finding in enumerate(findings or [], 1):
        if not isinstance(finding, dict):
            continue
        locations = finding.get('locations') or []
        for index, location in enumerate(locations):
            if not isinstance(location, dict):
                continue
            page = _positive_int(location.get('page'))
            if page is None and not location.get('resolution_state'):
                continue

            bbox, source_bbox = _normalize_bbox(location)
            renderable = bbox is not None
            bbox_type = location.get('bbox_type') or location.get('type') or DEFAULT_BBOX_TYPE
            if _skip_default_annotation(finding, location, bbox_type):
                continue
            if not renderable and bbox_type in {'page_issue', 'whole_page'} and 'bbox' not in location:
                bbox = {'x': 0.0, 'y': 0.0, 'width': 1.0, 'height': 1.0}
                renderable = True

            location_message = location.get('message')
            location_detail = location.get('detail')
            annotation = {
                'id': f'{finding.get("id") or "finding"}:{index}',
                'finding_id': finding.get('id'),
                'page': page,
                'severity': finding.get('severity') or 'info',
                'category': finding.get('category'),
                'message': location_message or finding.get('message'),
                'detail': location_detail if location_message else finding.get('detail'),
                'bbox': bbox,
                'bbox_type': bbox_type,
                'reason': location.get('reason'),
                'renderable': renderable,
            }
            for key in ('matched_text', 'field', 'label'):
                if location.get(key) is not None:
                    annotation[key] = location.get(key)
            if location.get('resolution_state'):
                annotation['finding_number'] = finding_number
            for key in ('text', 'context_before', 'context_after', 'occurrence_index', 'char_start', 'char_end',
                        'offset', 'length', 'issue_index', 'geometry_source', 'resolution_state', 'boxes'):
                if key in location:
                    annotation[key] = location[key]
            if source_bbox is not None and bbox is None:
                annotation['source_bbox'] = source_bbox
            annotations.append(annotation)
    return annotations


def _skip_default_annotation(finding, location, bbox_type):
    matched_text = str(location.get('matched_text') or '').strip()
    if matched_text:
        return False

    finding_id = str(finding.get('id') or '')
    message = str(finding.get('message') or '').lower()
    if finding_id.startswith('field_missing:'):
        return True
    if finding_id.startswith('format_profile_missing'):
        return True
    if bbox_type == 'expected_zone' and ('missing' in finding_id or 'not found' in message):
        return True
    return False


def _normalize_bbox(location):
    raw_bbox = location.get('bbox')
    if raw_bbox is None:
        return None, None

    values = _bbox_values(raw_bbox)
    if values is None:
        return None, raw_bbox

    page_width = _positive_float(location.get('page_width') or location.get('width'))
    page_height = _positive_float(location.get('page_height') or location.get('height'))
    x, y, width, height = values

    if _is_normalized(values):
        return _clamped_bbox(x, y, width, height), None

    if _is_percentage_bbox(values):
        return _clamped_bbox(x / 100, y / 100, width / 100, height / 100), None

    if page_width and page_height:
        return _clamped_bbox(x / page_width, y / page_height, width / page_width, height / page_height), None

    return None, raw_bbox


def _bbox_values(raw_bbox):
    if isinstance(raw_bbox, dict):
        candidates = [
            raw_bbox.get('x'),
            raw_bbox.get('y'),
            raw_bbox.get('width', raw_bbox.get('w')),
            raw_bbox.get('height', raw_bbox.get('h')),
        ]
    elif isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
        candidates = raw_bbox
    else:
        return None

    values = []
    for value in candidates:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if numeric < 0:
            return None
        values.append(numeric)
    return values


def _is_normalized(values):
    x, y, width, height = values
    return max(values) <= 1 and x + width <= 1.05 and y + height <= 1.05


def _is_percentage_bbox(values):
    x, y, width, height = values
    return max(values) <= 100 and x + width <= 100.5 and y + height <= 100.5


def _clamped_bbox(x, y, width, height):
    x = _clamp(x)
    y = _clamp(y)
    width = max(0.0, min(1.0 - x, float(width)))
    height = max(0.0, min(1.0 - y, float(height)))
    return {
        'x': round(x, 4),
        'y': round(y, 4),
        'width': round(width, 4),
        'height': round(height, 4),
    }


def _clamp(value):
    return max(0.0, min(1.0, float(value)))


def _positive_int(value):
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None


def _positive_float(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None
