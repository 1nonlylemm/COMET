from datetime import date

from app.services.project_status import CANONICAL_PROJECT_STATUSES, normalize_project_status


VALID_PHASES = ('pre_implementation', 'implementation', 'completion')
VALID_STATUSES = CANONICAL_PROJECT_STATUSES
VALID_REQ_STATUSES = ('pending', 'under_review', 'compliant', 'non_compliant', 'waived')
VALID_SUBMISSION_SOURCES = ('dms_ingestion', 'direct_upload', 'field_upload', 'api_push')
VALID_PROJECT_KINDS = (
    'infrastructure',
    'goods',
    'vehicle',
    'financial_assistance',
)
VALID_MONITORING_APPLICABILITY = ('qaar', 'non_infra_template', 'none', 'mixed')
VALID_QAAR_CATEGORIES = ('WSS', 'DRR', 'LRS')
VALID_SUBAYBAYAN_ENROLLMENT_STATUSES = ('not_started', 'pending', 'enrolled', 'delayed', 'not_required')


def validate_project_create(data):
    errors = {}
    if not data.get('lgu_id'):
        errors['lgu_id'] = 'LGU is required'
    elif not isinstance(data['lgu_id'], int):
        errors['lgu_id'] = 'LGU ID must be an integer'
    if not data.get('program_id'):
        errors['program_id'] = 'Program is required'
    elif not isinstance(data['program_id'], int):
        errors['program_id'] = 'Program ID must be an integer'
    if 'program_cycle_id' in data and data['program_cycle_id'] is not None and not isinstance(data['program_cycle_id'], int):
        errors['program_cycle_id'] = 'Program cycle ID must be an integer'
    if not data.get('project_name'):
        errors['project_name'] = 'Project name is required'
    elif len(data['project_name']) > 300:
        errors['project_name'] = 'Project name must be 300 characters or less'
    if not data.get('fiscal_year'):
        errors['fiscal_year'] = 'Fiscal year is required'
    elif not isinstance(data['fiscal_year'], int) or data['fiscal_year'] < 2000 or data['fiscal_year'] > 2100:
        errors['fiscal_year'] = 'Fiscal year must be between 2000 and 2100'
    if 'current_phase' in data and data['current_phase'] not in VALID_PHASES:
        errors['current_phase'] = f'Must be one of: {", ".join(VALID_PHASES)}'
    if 'overall_status' in data and data['overall_status'] not in VALID_STATUSES:
        errors['overall_status'] = f'Must be one of: {", ".join(VALID_STATUSES)}'
    _validate_project_code(data, errors)
    _validate_monitoring_profile_fields(data, errors)
    if 'budget_amount' in data and data['budget_amount'] is not None:
        try:
            val = float(data['budget_amount'])
            if val < 0:
                errors['budget_amount'] = 'Budget must be non-negative'
        except (ValueError, TypeError):
            errors['budget_amount'] = 'Budget must be a valid number'
    if 'physical_completion_pct' in data and data['physical_completion_pct'] is not None:
        try:
            val = float(data['physical_completion_pct'])
            if val < 0 or val > 100:
                errors['physical_completion_pct'] = 'Must be between 0 and 100'
        except (ValueError, TypeError):
            errors['physical_completion_pct'] = 'Must be a valid number'
    _validate_project_date_fields(data, errors)
    return errors if errors else None


def validate_project_update(data):
    errors = {}
    if not data:
        errors['general'] = 'At least one field is required'
    for field, label in (('lgu_id', 'LGU'), ('program_id', 'Program')):
        if field in data and (type(data[field]) is not int or data[field] <= 0):
            errors[field] = f'{label} ID must be a positive integer'
    if 'project_name' in data and data['project_name']:
        if len(data['project_name']) > 300:
            errors['project_name'] = 'Project name must be 300 characters or less'
    if 'fiscal_year' in data:
        if not isinstance(data['fiscal_year'], int) or data['fiscal_year'] < 2000 or data['fiscal_year'] > 2100:
            errors['fiscal_year'] = 'Fiscal year must be between 2000 and 2100'
    if 'program_cycle_id' in data and data['program_cycle_id'] is not None and not isinstance(data['program_cycle_id'], int):
        errors['program_cycle_id'] = 'Program cycle ID must be an integer'
    if 'current_phase' in data and data['current_phase'] not in VALID_PHASES:
        errors['current_phase'] = f'Must be one of: {", ".join(VALID_PHASES)}'
    if 'overall_status' in data:
        raw_status = data['overall_status']
        if raw_status is None:
            errors['overall_status'] = 'overall_status cannot be null'
        else:
            norm_status = normalize_project_status(raw_status, default=raw_status)
            if str(norm_status).strip().lower() == 'completed':
                errors['overall_status'] = 'Project completion must be processed through the completion closeout service'
            elif norm_status not in VALID_STATUSES:
                errors['overall_status'] = f'Must be one of: {", ".join(VALID_STATUSES)}'
    _validate_project_code(data, errors)
    _validate_monitoring_profile_fields(data, errors)
    if 'budget_amount' in data and data['budget_amount'] is not None:
        try:
            val = float(data['budget_amount'])
            if val < 0:
                errors['budget_amount'] = 'Budget must be non-negative'
        except (ValueError, TypeError):
            errors['budget_amount'] = 'Budget must be a valid number'
    if 'physical_completion_pct' in data and data['physical_completion_pct'] is not None:
        try:
            val = float(data['physical_completion_pct'])
            if val < 0 or val > 100:
                errors['physical_completion_pct'] = 'Must be between 0 and 100'
        except (ValueError, TypeError):
            errors['physical_completion_pct'] = 'Must be a valid number'
    _validate_project_date_fields(data, errors)
    return errors if errors else None


def _validate_project_date_fields(data, errors):
    target_start = _coerce_iso_date(data, 'target_start_date', errors)
    target_end = _coerce_iso_date(data, 'target_end_date', errors)
    actual_start = _coerce_iso_date(data, 'actual_start_date', errors)
    actual_end = _coerce_iso_date(data, 'actual_end_date', errors)
    _coerce_iso_date(data, 'nadai_received_at', errors)
    _coerce_iso_date(data, 'subaybayan_enrolled_at', errors)

    if target_start and target_end and target_end < target_start:
        errors['target_end_date'] = 'Target end date cannot be earlier than target start date'
    if actual_start and actual_end and actual_end < actual_start:
        errors['actual_end_date'] = 'Actual end date cannot be earlier than actual start date'


def _validate_monitoring_profile_fields(data, errors):
    if 'project_kind' in data and data.get('project_kind') not in (None, '') and data['project_kind'] not in VALID_PROJECT_KINDS:
        errors['project_kind'] = f'Must be one of: {", ".join(VALID_PROJECT_KINDS)}'
    if 'monitoring_applicability' in data and data.get('monitoring_applicability') not in (None, '') and data['monitoring_applicability'] not in VALID_MONITORING_APPLICABILITY:
        errors['monitoring_applicability'] = f'Must be one of: {", ".join(VALID_MONITORING_APPLICABILITY)}'
    if 'qaar_category' in data and data.get('qaar_category') not in (None, '') and data['qaar_category'] not in VALID_QAAR_CATEGORIES:
        errors['qaar_category'] = f'Must be one of: {", ".join(VALID_QAAR_CATEGORIES)}'
    if 'subaybayan_project_code' in data and data.get('subaybayan_project_code') and len(str(data['subaybayan_project_code'])) > 120:
        errors['subaybayan_project_code'] = 'SubayBayan project code must be 120 characters or less'
    if 'subaybayan_url' in data and data.get('subaybayan_url') and len(str(data['subaybayan_url'])) > 500:
        errors['subaybayan_url'] = 'SubayBayan URL must be 500 characters or less'
    if 'subaybayan_enrollment_status' in data and data.get('subaybayan_enrollment_status') not in (None, '') and data['subaybayan_enrollment_status'] not in VALID_SUBAYBAYAN_ENROLLMENT_STATUSES:
        errors['subaybayan_enrollment_status'] = f'Must be one of: {", ".join(VALID_SUBAYBAYAN_ENROLLMENT_STATUSES)}'


def _coerce_iso_date(data, field, errors):
    if field not in data or data[field] in (None, ''):
        return None
    value = data[field]
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        errors[field] = 'Use YYYY-MM-DD'
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors[field] = 'Use YYYY-MM-DD'
        return None


def validate_phase_transition(data):
    errors = {}
    if not data.get('to_phase'):
        errors['to_phase'] = 'Target phase is required'
    elif data['to_phase'] not in VALID_PHASES:
        errors['to_phase'] = f'Must be one of: {", ".join(VALID_PHASES)}'
    if not data.get('reason'):
        errors['reason'] = 'Transition reason is required'
    return errors if errors else None


def validate_project_requirement_update(data):
    errors = {}
    if not data:
        errors['general'] = 'At least one field is required'
    if 'status' in data and data['status'] not in VALID_REQ_STATUSES:
        errors['status'] = f'Must be one of: {", ".join(VALID_REQ_STATUSES)}'
    if 'workflow_status' in data:
        errors['workflow_status'] = 'workflow_status cannot be updated through this endpoint. Use authoritative workflow actions.'
    if 'applicability' in data:
        errors['applicability'] = 'applicability cannot be updated through generic update. Use the dedicated applicability action.'
    return errors if errors else None


def validate_project_requirement_applicability_update(data):
    errors = {}
    if not isinstance(data, dict):
        errors['general'] = 'Request body must be a JSON object'
        return errors
    applicability = data.get('applicability')
    if not applicability:
        errors['applicability'] = 'applicability field is required'
    elif applicability not in ('applicable', 'not_applicable'):
        errors['applicability'] = "applicability must be either 'applicable' or 'not_applicable'"
    return errors if errors else None


def validate_change_status_request_create(data):
    errors = {}
    if not data:
        errors['general'] = 'Request data is required'
        return errors

    if not data.get('requested_status'):
        errors['requested_status'] = 'Requested status is required'
    elif data['requested_status'] not in VALID_REQ_STATUSES:
        errors['requested_status'] = f'Must be one of: {", ".join(VALID_REQ_STATUSES)}'

    if not data.get('justification'):
        errors['justification'] = 'Justification is required'

    return errors if errors else None


def validate_change_status_request_review(data):
    errors = {}
    if not data:
        errors['general'] = 'Review data is required'
        return errors

    if not data.get('decision'):
        errors['decision'] = 'Decision is required'
    elif data['decision'] not in ('approved', 'rejected'):
        errors['decision'] = 'Decision must be either approved or rejected'

    return errors if errors else None


def validate_submission_create(data):
    errors = {}
    source = data.get('source', 'dms_ingestion')
    if source not in VALID_SUBMISSION_SOURCES:
        errors['source'] = f'Must be one of: {", ".join(VALID_SUBMISSION_SOURCES)}'
    return errors if errors else None


def _validate_project_code(data, errors):
    if 'source_project_code' not in data or data['source_project_code'] is None:
        return  # Existing integrations and legacy records may have no code.
    code = data['source_project_code']
    if not isinstance(code, str) or not code.strip():
        errors['source_project_code'] = 'Project code must be a non-empty string'
    elif len(code.strip()) > 120:
        errors['source_project_code'] = 'Project code must be 120 characters or less'
