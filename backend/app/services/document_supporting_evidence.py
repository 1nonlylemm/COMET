"""Current-submission attachment evidence; never silently clears a primary-file defect."""
from datetime import timezone

from app.services import document_compliance_evidence_checker as checker


def _items(relation):
    if relation is None:
        return []
    return relation.all() if hasattr(relation, 'all') else list(relation)


def current_supporting_files(submission, primary):
    versions = _items(getattr(submission, 'versions', None))
    current_number = getattr(submission, 'current_version', None)
    target = next((v for v in versions if v.version_number == current_number), None)
    if target is None and versions:
        target = max(versions, key=lambda v: (v.version_number, v.id or 0))
    older = [v for v in versions if v is not target]
    old_objects = {v.stored_object_id for v in older if v.stored_object_id is not None}
    old_paths = {str(v.file_path) for v in older if v.file_path}
    cutoff = getattr(target, 'uploaded_at', None) if target else None

    def timestamp(value):
        return value.replace(tzinfo=timezone.utc).timestamp() if value and value.tzinfo is None else value.timestamp() if value else None

    files = []
    for file in _items(getattr(submission, 'document_files', None)):
        if file.id == primary.id:
            continue
        if getattr(file, 'stored_object_id', None) in old_objects or str(getattr(file, 'file_path', '')) in old_paths:
            continue
        if target:
            created = getattr(file, 'created_at', None)
            # Without a version association or timestamp, applicability is unknown.
            if not created or not cutoff or timestamp(created) < timestamp(cutoff):
                continue
        files.append(file)
    return sorted(files, key=lambda file: file.id)


def inspect_supporting_evidence(submission, primary, config, extract, checks):
    files = current_supporting_files(submission, primary)
    reviewed, unavailable = [], []
    candidates = {}
    for file in files:
        try:
            extraction = extract(file)
            result = checker.evaluate_document_evidence(extraction.get('text') or '', config, extraction=extraction)
        except Exception:
            unavailable.append({'document_file_id': file.id, 'file_name': file.file_name})
            continue
        reviewed.append({'document_file_id': file.id, 'file_name': file.file_name})
        metadata = extraction.get('metadata') or {}
        if not str(extraction.get('text') or '').strip() or metadata.get('extraction_incomplete') or metadata.get('coverage_unknown') or metadata.get('unreadable_pages'):
            unavailable.append({'document_file_id': file.id, 'file_name': file.file_name})
        for check in result['evidence_checks']:
            if check['state'] == 'detected':
                candidates.setdefault(check['key'], []).append({
                    'document_file_id': file.id, 'file_name': file.file_name,
                    'page': check.get('page'), 'snippet': check.get('snippet'),
                })
    # Retain the distinction between primary evidence and supporting candidates.
    updated = []
    for original in checks:
        check = dict(original)
        if check['state'] in {'not_detected', 'needs_review'} and (candidates.get(check['key']) or unavailable):
            check['state'] = 'needs_review'
            check['human_verification_required'] = True
            check['supporting_evidence'] = candidates.get(check['key'], [])
            names = ', '.join(item['file_name'] for item in check['supporting_evidence'])
            check['explanation'] = (f'{check["label"]} was not verified in the primary file. Related wording appears in {names}; confirm whether it satisfies this requirement.'
                                    if names else f'{check["label"]} could not be verified across all attachments because some files could not be analyzed.')
            check['finding_observation'] = check['explanation']
            check['corrective_instruction'] = 'Inspect the primary document and the supporting attachments. Request a correction only after confirming the required evidence is absent or inapplicable.'
        updated.append(check)
    return updated, {'reviewed_files': reviewed, 'unavailable_files': unavailable}
