import re

from app.services import document_compliance_rule_engine as rule_engine


PHOTO_CHECKLIST_KEYS = {
    'require_capture_time',
    'require_gps',
    'require_resolved_address',
    'required_scene_labels',
    'required_visual_labels',
    'expected_scene_labels',
    'min_label_confidence',
}


def evaluate_photo_evidence(
    *,
    extraction,
    provider_metadata,
    profile_selection=None,
    checker_config=None,
    evidence_type=None,
):
    """Evaluate explicit progress-photo checklist metadata.

    Active source of truth is requirement checker_config.
    DocumentReferenceProfile is historical compatibility only and does not influence active review.
    """
    ev_type = (
        evidence_type
        or (checker_config or {}).get('evidence_type')
        or rule_engine.evidence_type_from_profile_selection(profile_selection)
    )
    if not rule_engine.is_visual_evidence_type(ev_type):
        return {'findings': [], 'checks': {}}

    checklist = _photo_checklist(checker_config=checker_config, profile_selection=profile_selection)
    if not checklist:
        return {'findings': [], 'checks': {}}

    extraction = extraction or {}
    photo_metadata = extraction.get('photo_metadata') or {}
    labels = _provider_labels(provider_metadata, min_confidence=checklist.get('min_label_confidence'))
    checks = {}
    findings = []

    if checklist.get('require_capture_time'):
        present = bool(photo_metadata.get('captured_at'))
        checks['capture_time'] = {
            'status': 'present' if present else 'missing',
            'actual': photo_metadata.get('captured_at'),
            'source': photo_metadata.get('captured_at_source'),
        }
        if not present:
            findings.append(rule_engine.finding(
                'photo_capture_time_missing',
                'warning',
                rule_engine.CATEGORY_DATE_TEMPORAL_CONSISTENCY,
                'Photo evidence does not include embedded capture time metadata.',
                'The profile requires capture time metadata. Reviewer should confirm the photo date through other evidence before accepting it.',
                rule='missing_photo_capture_time',
                dimension='project_lgu_context',
                deficiency_category='date_temporal_defect',
                finding_observation='Photo evidence does not include embedded capture time metadata.',
                corrective_instruction='Confirm the photo date through other evidence or provide timestamped photo evidence.',
                automation_level='automated_with_review',
                locations=_whole_image_locations(),
            ))

    if checklist.get('require_gps'):
        gps = photo_metadata.get('gps') or {}
        present = gps.get('latitude') is not None and gps.get('longitude') is not None
        checks['gps'] = {
            'status': 'present' if present else 'missing',
            'actual': _gps_actual(gps),
        }
        if not present:
            findings.append(rule_engine.finding(
                'photo_gps_missing',
                'warning',
                rule_engine.CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
                'Photo evidence does not include embedded GPS coordinates.',
                'The profile requires GPS metadata. Reviewer should confirm project location through signboard text, transmittal context, or other supporting evidence.',
                rule='missing_photo_gps',
                dimension='project_lgu_context',
                deficiency_category='other_documented_defect',
                finding_observation='Photo evidence does not include embedded GPS coordinates.',
                corrective_instruction='Confirm project location through signboard text or geotagged progress photos.',
                automation_level='automated_with_review',
                locations=_whole_image_locations(),
            ))

    if checklist.get('require_resolved_address'):
        gps = photo_metadata.get('gps') or {}
        present = bool(gps.get('resolved_address'))
        checks['resolved_address'] = {
            'status': 'present' if present else 'missing',
            'actual': gps.get('resolved_address'),
            'source': gps.get('resolved_address_source'),
        }
        if not present:
            findings.append(rule_engine.finding(
                'photo_resolved_address_missing',
                'warning',
                rule_engine.CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
                'Photo GPS metadata does not include a resolved address.',
                'The profile requires a human-readable location. Reviewer should confirm the coordinates or project location manually.',
                rule='missing_photo_address',
                dimension='project_lgu_context',
                deficiency_category='other_documented_defect',
                finding_observation='Photo GPS metadata does not include a resolved address.',
                corrective_instruction='Confirm coordinates or project location manually before accepting.',
                automation_level='human_verification',
                locations=_whole_image_locations(),
            ))

    required_labels = _required_labels(checklist)
    if required_labels:
        actual_names = [item['name'] for item in labels]
        matched = [
            expected for expected in required_labels
            if any(_label_matches(expected, actual) for actual in actual_names)
        ]
        present = bool(matched)
        checks['scene_labels'] = {
            'status': 'present' if present else 'missing',
            'expected': required_labels,
            'actual': actual_names,
            'matched': matched,
            'min_confidence': _min_label_confidence(checklist),
        }
        if not present:
            findings.append(rule_engine.finding(
                'photo_scene_label_missing',
                'warning',
                rule_engine.CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
                'Photo evidence scene labels do not match the configured project-photo checklist.',
                (
                    f'Expected at least one of: {", ".join(required_labels)}. '
                    f'Detected labels: {", ".join(actual_names) or "none"}. '
                    'Scene labels are advisory and must be confirmed by the reviewer.'
                ),
                rule='missing_photo_scene_labels',
                dimension='evidence_type_mapping',
                deficiency_category='other_documented_defect',
                finding_observation='Photo evidence scene labels do not match the configured project-photo checklist.',
                corrective_instruction='Visually verify photo scene elements and project relevance.',
                automation_level='human_verification',
                locations=_whole_image_locations(),
            ))


    return {'findings': findings, 'checks': checks}


def _photo_checklist(checker_config=None, profile_selection=None):
    if checker_config is not None:
        checklist = {}
        cfg = checker_config
        nested = cfg.get('photo_evidence') or cfg.get('photo_checklist')
        if isinstance(nested, dict):
            checklist.update(nested)
        for key in PHOTO_CHECKLIST_KEYS:
            if key in cfg:
                checklist[key] = cfg.get(key)
        return {key: value for key, value in checklist.items() if value not in (None, '', [], {})}

    # Legacy test harness fallback ONLY when checker_config is completely omitted (None)
    checklist = {}
    for profile in _reference_profiles(profile_selection):
        metadata = profile.get('profile_metadata') or {}
        nested = metadata.get('photo_evidence')
        if isinstance(nested, dict):
            checklist.update(nested)
        for key in PHOTO_CHECKLIST_KEYS:
            if key in metadata:
                checklist[key] = metadata.get(key)
    return {key: value for key, value in checklist.items() if value not in (None, '', [], {})}


def _reference_profiles(profile_selection):
    profile_selection = profile_selection or {}
    return profile_selection.get('used_profiles') or profile_selection.get('current_profiles') or []


def _provider_labels(provider_metadata, *, min_confidence=None):
    confidence_floor = _safe_float(min_confidence, default=60.0)
    labels = []
    for item in provider_metadata or []:
        if item.get('name') != 'aws-rekognition':
            continue
        payload = item.get('payload') or {}
        for label in payload.get('labels') or []:
            name = str(label.get('name') or '').strip()
            confidence = _safe_float(label.get('confidence'), default=None)
            if not name:
                continue
            if confidence is not None and confidence < confidence_floor:
                continue
            labels.append({
                'name': name,
                'confidence': confidence,
                'categories': label.get('categories') or [],
            })
    return labels


def _required_labels(checklist):
    for key in ('required_scene_labels', 'required_visual_labels', 'expected_scene_labels'):
        labels = checklist.get(key)
        if isinstance(labels, str):
            return [item.strip() for item in labels.split(',') if item.strip()]
        if isinstance(labels, list):
            return [str(item).strip() for item in labels if str(item).strip()]
    return []


def _label_matches(expected, actual):
    expected_normalized = _normalize_label(expected)
    actual_normalized = _normalize_label(actual)
    if not expected_normalized or not actual_normalized:
        return False
    return expected_normalized == actual_normalized or expected_normalized in actual_normalized or actual_normalized in expected_normalized


def _normalize_label(value):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower())).strip()


def _gps_actual(gps):
    if not gps:
        return None
    latitude = gps.get('latitude')
    longitude = gps.get('longitude')
    if latitude is None or longitude is None:
        return None
    actual = {'latitude': latitude, 'longitude': longitude}
    if gps.get('resolved_address'):
        actual['resolved_address'] = gps.get('resolved_address')
    if gps.get('resolved_address_source'):
        actual['resolved_address_source'] = gps.get('resolved_address_source')
    return actual


def _min_label_confidence(checklist):
    return _safe_float(checklist.get('min_label_confidence'), default=60.0)


def _safe_float(value, *, default):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _whole_image_locations():
    return [
        {
            'page': 1,
            'bbox_type': 'whole_page',
            'reason': 'Photo checklist issue applies to the whole image.',
        }
    ]
