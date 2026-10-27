from datetime import date
from urllib.parse import urlparse


VALID_GUIDELINE_TYPES = {
    'memorandum',
    'circular',
    'annex',
    'local_budget_circular',
    'omnibus_guideline',
    'other',
}


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _is_positive_integer(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip()) > 0
    return False


def _is_valid_date(value):
    if isinstance(value, date):
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        date.fromisoformat(value.strip())
    except ValueError:
        return False
    return True


def _is_external_reference(value):
    parsed = urlparse(value)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _validate_length(data, errors, field, label, limit):
    value = data.get(field)
    if isinstance(value, str) and len(value.strip()) > limit:
        errors[field] = f'{label} must be {limit} characters or less'


def validate_guideline_payload(data, partial=False):
    errors = {}

    if not partial or 'program_id' in data:
        if _is_blank(data.get('program_id')):
            errors['program_id'] = 'Program is required'
        elif not _is_positive_integer(data.get('program_id')):
            errors['program_id'] = 'Select a valid program'

    if not partial or 'title' in data:
        if _is_blank(data.get('title')):
            errors['title'] = 'Title is required'

    if not partial and _is_blank(data.get('guideline_type')):
        errors['guideline_type'] = 'Type is required'
    elif 'guideline_type' in data:
        guideline_type = data.get('guideline_type')
        if _is_blank(guideline_type):
            errors['guideline_type'] = 'Type is required'
        elif guideline_type not in VALID_GUIDELINE_TYPES:
            errors['guideline_type'] = 'Select a supported reference type'

    if 'effective_date' in data and not _is_blank(data.get('effective_date')) and not _is_valid_date(data.get('effective_date')):
        errors['effective_date'] = 'Effective date must use YYYY-MM-DD'

    if 'file_path' in data and not _is_blank(data.get('file_path')):
        reference = str(data.get('file_path')).strip()
        if not _is_external_reference(reference):
            errors['file_path'] = 'Use an http:// or https:// URL, or upload the file instead'

    _validate_length(data, errors, 'title', 'Title', 500)
    _validate_length(data, errors, 'reference_number', 'Reference number', 100)
    _validate_length(data, errors, 'issuing_body', 'Issuing body', 200)
    _validate_length(data, errors, 'file_name', 'File name', 500)
    _validate_length(data, errors, 'file_path', 'Reference URL', 1000)

    return errors if errors else None
