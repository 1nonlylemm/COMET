from app.services.import_field_catalog import normalize_label


def diff_profile_against_template(profile, template):
    template_headers = _headers_from_template(template)
    profile_headers = _headers_from_profile(profile)

    template_set = set(template_headers)
    profile_set = set(profile_headers)
    added = sorted(profile_set - template_set)
    removed = sorted(template_set - profile_set)
    unchanged = sorted(template_set & profile_set)
    renamed_candidates = _renamed_candidates(added, removed)

    required_missing = [
        item for item in removed
        if any(required in item for required in ['project code', 'subaybayan code', 'project title', 'lgu'])
    ]
    if required_missing:
        suggested_action = 'cannot_import_until_fixed'
    elif added or removed or renamed_candidates:
        suggested_action = 'clone_template_with_changes'
    else:
        suggested_action = 'reuse_template'

    return {
        'base_template_id': template.id,
        'uploaded_schema_signature': profile.get('schema_signature'),
        'template_schema_signature': template.schema_signature,
        'unchanged_columns': len(unchanged),
        'new_columns': [{'header': item, 'suggested_role': 'custom_field'} for item in added],
        'removed_columns': [{'header': item, 'required': item in required_missing} for item in removed],
        'renamed_candidates': renamed_candidates,
        'required_missing': required_missing,
        'suggested_action': suggested_action,
    }


def _headers_from_profile(profile):
    headers = []
    for sheet in profile.get('sheets', []):
        for column in sheet.get('columns', []):
            header = normalize_label(column.get('header') or column.get('normalized_header'))
            if header:
                headers.append(f"{normalize_label(sheet.get('name'))}::{header}")
    return headers


def _headers_from_template(template):
    mappings = template.column_mappings or {}
    headers = []
    for key, value in mappings.items():
        source_sheet = normalize_label(value.get('source_sheet')) if isinstance(value, dict) else ''
        source_header = normalize_label(value.get('source_header')) if isinstance(value, dict) else normalize_label(key)
        if source_header:
            headers.append(f'{source_sheet}::{source_header}' if source_sheet else source_header)
    return headers


def _renamed_candidates(added, removed):
    candidates = []
    for old in removed:
        old_tokens = set(normalize_label(old).split())
        if not old_tokens:
            continue
        for new in added:
            new_tokens = set(normalize_label(new).split())
            overlap = len(old_tokens & new_tokens) / max(len(old_tokens | new_tokens), 1)
            if overlap >= 0.45:
                candidates.append({
                    'old_header': old,
                    'new_header': new,
                    'confidence': round(overlap, 2),
                })
    return sorted(candidates, key=lambda item: item['confidence'], reverse=True)[:10]
