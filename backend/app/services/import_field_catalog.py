import re


CANONICAL_FIELDS = {
    'program_cycle.fiscal_year': ['funding year', 'fiscal year', 'fy'],
    'project.source_project_code': ['project code', 'subaybayan code'],
    'project.project_name': ['project title', 'project name', 'proposed project title', 'name of project'],
    'project.budget_amount': ['national allocation', 'allocation', 'budget amount', 'total project cost', 'saro amount', 'amount per saro'],
    'project.location': ['project location', 'location', 'exact location', 'location beneficiaries', 'location/ beneficiaries'],
    'project.target_beneficiaries': ['target beneficiaries', 'beneficiaries', 'beneficiaries number of households', 'actual household served'],
    'project.mode_of_implementation': ['mode of implementation', 'procurement type', 'procurement'],
    'project.implementation_period': ['implementation period', 'project start timeline'],
    'project.overall_status': ['project status', 'status', 'actual status', 'status in subaybayan system'],
    'lgu.province': ['province', 'province/ huc'],
    'lgu.name': ['lgu', 'implementing lgu', 'city municipality barangay', 'city/ municipality', 'city/municipality', 'city / municipality / barangay'],
    'lgu.municipality': ['municipality', 'city', 'lgu'],
    'lgu.level': ['lgu level', 'level', 'implementing unit'],
    'monitoring.physical_completion_pct': ['physical accomplishment', 'physical accomplishment pct', 'physical'],
    'monitoring.financial_accomplishment_pct': ['financial accomplishment', 'financial accomplishment pct'],
    'monitoring.obligation_amount': ['obligation', 'total obligation'],
    'monitoring.disbursement_amount': ['disbursement', 'total disbursement'],
    'completion.physical_completion_date': ['physical completion date', 'date completed'],
}

CHECKLIST_HINTS = {
    'annex', 'sbr', 'resolution', 'ldip', 'aip', 'ded', 'pow', 'permit', 'clearance',
    'certificate', 'certification', 'report', 'photo', 'photos', 'inspection', 'warranty',
    'completion', 'acceptance', 'geotagged', 'mgb', 'phivolcs', 'ecc', 'rrow',
    'confirmation', 'proof', 'transfer', 'defects', 'deficiencies', 'test results',
    'apmv', 'contract', 'itb', 'mt', 'noa', 'ntp', 'qaar', 'rssa', 'sord', 'swa',
}

PROJECT_CODE_HEADER_HINTS = {'code', 'id', 'reference', 'ref', 'number', 'no', 'subaybayan'}
PROJECT_CODE_SAMPLE_BLOCKERS = {
    'description', 'title', 'location', 'beneficiary', 'beneficiaries', 'scope',
    'remarks', 'status', 'name', 'particulars', 'narrative',
}


def normalize_label(value):
    if value is None:
        return ''
    text = str(value).strip().lower()
    text = text.replace('&', ' and ')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def match_canonical_field(header_path, sample_values=None):
    labels = [normalize_label(item) for item in header_path or [] if normalize_label(item)]
    combined = normalize_label(' '.join(labels))
    if not combined:
        return None

    for field, synonyms in CANONICAL_FIELDS.items():
        for synonym in synonyms:
            normalized_synonym = normalize_label(synonym)
            if normalized_synonym and (normalized_synonym == combined or normalized_synonym in labels):
                return {'target_field': field, 'confidence': 0.98, 'reason': 'exact header synonym'}

    for field, synonyms in CANONICAL_FIELDS.items():
        for synonym in synonyms:
            normalized_synonym = normalize_label(synonym)
            if _safe_phrase_match(normalized_synonym, combined):
                return {'target_field': field, 'confidence': 0.84, 'reason': 'combined header synonym'}

    if (
        sample_values
        and _can_infer_project_code_from_samples(combined)
        and any(_looks_like_project_code(value) for value in sample_values)
    ):
        return {'target_field': 'project.source_project_code', 'confidence': 0.78, 'reason': 'sample value pattern'}

    return None


def suggest_column_role(header_path, sample_values=None):
    labels = [normalize_label(item) for item in header_path or [] if normalize_label(item)]
    combined = normalize_label(' '.join(labels))
    if any(hint in combined.split() or hint in combined for hint in CHECKLIST_HINTS):
        return 'requirement'
    if sample_values and _is_checklist_like(sample_values):
        return 'requirement'
    if sample_values and _is_date_like(sample_values):
        return 'custom_date_field'
    if sample_values and _is_amount_like(sample_values):
        return 'custom_numeric_field'
    return 'custom_field'


def _looks_like_project_code(value):
    if value is None:
        return False
    text = str(value).strip()
    if text.startswith('='):
        return False
    if not re.search(r'\d', text):
        return False
    if text.count('-') < 2 and not re.search(r'\b(FA|G3P|SAFPB|FALGU|LGSF)[A-Z0-9-]*\b', text, re.IGNORECASE):
        return False
    return bool(re.search(r'\b(FA|G3P|SAFPB|FALGU|LGSF)[A-Z0-9-]{4,}\b|[A-Z]{2,}[A-Z0-9]*-\d[\w-]*-\d[\w-]*', text, re.IGNORECASE))


def _can_infer_project_code_from_samples(combined_header):
    if not combined_header:
        return True
    words = set(combined_header.split())
    if words & PROJECT_CODE_SAMPLE_BLOCKERS:
        return False
    return bool(words & PROJECT_CODE_HEADER_HINTS)


def _safe_phrase_match(needle, haystack):
    if not needle:
        return False
    if len(needle.split()) < 2:
        return False
    return re.search(rf'(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])', haystack) is not None


def _is_checklist_like(values):
    normalized = {normalize_label(value) for value in values if value is not None}
    checklist_values = {'true', 'false', 'submitted', 'not applicable', 'n a', 'no submission', 'ongoing application', 'on going application'}
    if not normalized:
        return False
    matches = normalized & checklist_values
    return bool(matches) and len(normalized - checklist_values) <= max(0, len(normalized) // 3)


def _is_date_like(values):
    return any(hasattr(value, 'isoformat') for value in values if value is not None)


def _is_amount_like(values):
    numeric = [value for value in values if isinstance(value, (int, float))]
    return len(numeric) >= 2
