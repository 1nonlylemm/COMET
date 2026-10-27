VALID_PROGRAM_TYPES = ('infrastructure', 'non_infrastructure', 'hybrid')
VALID_REQ_TYPES = ('document', 'certificate', 'resolution', 'financial', 'engineering', 'inspection', 'other')
VALID_PHASE_TYPES = ('pre_implementation', 'implementation', 'completion')
VALID_DOCUMENT_CATEGORIES = (
    'monthly_progress_report',
    'form_3',
    'form_3_mov',
    'project_exception_report',
    'apm_template',
    'non_infra_monitoring_evidence',
    'signed_distribution_list',
    'acknowledgement_receipt',
    'beneficiary_tracking_record',
    'turnover_photos',
    'delivery_invoice',
    'final_swa',
    'final_inspection_report',
    'certificate_of_final_acceptance',
    'final_sord',
    'proof_of_return_of_funds',
)


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _clean_text(value):
    return str(value).strip() if value is not None else ''


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_bool_field(data, errors, field):
    if field in data and not isinstance(data[field], bool):
        errors[field] = f'{field} must be true or false'


def validate_program_create(data):
    errors = {}
    if _blank(data.get('name')):
        errors['name'] = 'Program name is required'
    if _blank(data.get('code')):
        errors['code'] = 'Program code is required'
    elif len(_clean_text(data.get('code'))) > 20:
        errors['code'] = 'Code must be 20 characters or less'
    if _blank(data.get('program_type')):
        errors['program_type'] = 'Program type is required'
    elif data['program_type'] not in VALID_PROGRAM_TYPES:
        errors['program_type'] = f'Must be one of: {", ".join(VALID_PROGRAM_TYPES)}'
    return errors if errors else None


def validate_program_update(data):
    errors = {}
    if not data:
        errors['general'] = 'At least one field is required'
    if 'name' in data and _blank(data.get('name')):
        errors['name'] = 'Program name cannot be blank'
    if 'code' in data and _blank(data.get('code')):
        errors['code'] = 'Program code cannot be blank'
    if 'program_type' in data and data['program_type'] not in VALID_PROGRAM_TYPES:
        errors['program_type'] = f'Must be one of: {", ".join(VALID_PROGRAM_TYPES)}'
    if 'code' in data and not _blank(data.get('code')) and len(_clean_text(data.get('code'))) > 20:
        errors['code'] = 'Code must be 20 characters or less'
    _validate_bool_field(data, errors, 'is_active')
    return errors if errors else None


def validate_cycle_create(data):
    errors = {}
    if _blank(data.get('name')):
        errors['name'] = 'Cycle name is required'
    if data.get('fiscal_year') is None:
        errors['fiscal_year'] = 'Fiscal year is required'
    elif not _is_int(data['fiscal_year']) or data['fiscal_year'] < 2000 or data['fiscal_year'] > 2100:
        errors['fiscal_year'] = 'Fiscal year must be between 2000 and 2100'
    if _blank(data.get('cycle_code')):
        errors['cycle_code'] = 'Cycle code is required'
    elif len(_clean_text(data.get('cycle_code'))) > 80:
        errors['cycle_code'] = 'Cycle code must be 80 characters or less'
    return errors if errors else None


def validate_cycle_update(data):
    errors = {}
    if not data:
        errors['general'] = 'At least one field is required'
    if 'name' in data and _blank(data.get('name')):
        errors['name'] = 'Cycle name cannot be blank'
    if 'fiscal_year' in data:
        if not _is_int(data['fiscal_year']) or data['fiscal_year'] < 2000 or data['fiscal_year'] > 2100:
            errors['fiscal_year'] = 'Fiscal year must be between 2000 and 2100'
    if 'cycle_code' in data and _blank(data.get('cycle_code')):
        errors['cycle_code'] = 'Cycle code cannot be blank'
    if 'cycle_code' in data and not _blank(data.get('cycle_code')) and len(_clean_text(data.get('cycle_code'))) > 80:
        errors['cycle_code'] = 'Cycle code must be 80 characters or less'
    _validate_bool_field(data, errors, 'is_active')
    return errors if errors else None


def validate_cycle_clone(data):
    errors = {}
    if data.get('fiscal_year') is None:
        errors['fiscal_year'] = 'Fiscal year is required'
    elif not _is_int(data['fiscal_year']) or data['fiscal_year'] < 2000 or data['fiscal_year'] > 2100:
        errors['fiscal_year'] = 'Fiscal year must be between 2000 and 2100'
    if 'name' in data and _blank(data.get('name')):
        errors['name'] = 'Cycle name cannot be blank'
    if 'cycle_code' in data and _blank(data.get('cycle_code')):
        errors['cycle_code'] = 'Cycle code cannot be blank'
    if 'cycle_code' in data and not _blank(data.get('cycle_code')) and len(_clean_text(data.get('cycle_code'))) > 80:
        errors['cycle_code'] = 'Cycle code must be 80 characters or less'
    return errors if errors else None


def validate_phase_create(data):
    errors = {}
    if _blank(data.get('name')):
        errors['name'] = 'Phase name is required'
    if data.get('phase_order') is None:
        errors['phase_order'] = 'Phase order is required'
    elif not _is_int(data['phase_order']) or data['phase_order'] < 1:
        errors['phase_order'] = 'Phase order must be a positive integer'
    return errors if errors else None


def validate_phase_update(data):
    errors = {}
    if not data:
        errors['general'] = 'At least one field is required'
    if 'name' in data and _blank(data.get('name')):
        errors['name'] = 'Phase name cannot be blank'
    if 'phase_order' in data and (not _is_int(data['phase_order']) or data['phase_order'] < 1):
        errors['phase_order'] = 'Phase order must be a positive integer'
    return errors if errors else None


def validate_checker_configuration(config, errors):
    if config is None:
        return
    if not isinstance(config, dict):
        errors['checker_configuration'] = 'checker_configuration must be an object'
        return

    bool_fields = ('requires_signatories', 'requires_certification', 'requires_notarization', 'requires_date')
    for field in bool_fields:
        if field in config and not isinstance(config[field], bool):
            errors[f'checker_configuration.{field}'] = f'{field} must be a boolean'

    list_fields = {
        'signatory_roles': 50,
        'custom_signatory_roles': 100,
        'certification_phrases': 150,
        'notarization_phrases': 150,
        'required_phrases': 150,
    }
    for field, max_len in list_fields.items():
        if field in config:
            val = config[field]
            if not isinstance(val, (list, tuple)):
                errors[f'checker_configuration.{field}'] = f'{field} must be a list of strings'
            else:
                if len(val) > 50:
                    errors[f'checker_configuration.{field}'] = f'{field} cannot exceed 50 items'
                    continue
                for idx, item in enumerate(val):
                    if not isinstance(item, str) or not item.strip():
                        errors[f'checker_configuration.{field}[{idx}]'] = f'Each item in {field} must be a non-empty string'
                        break
                    elif len(item.strip()) > max_len:
                        errors[f'checker_configuration.{field}[{idx}]'] = f'Items in {field} must not exceed {max_len} characters'
                        break


def validate_requirement_create(data):
    errors = {}
    if _blank(data.get('name')):
        errors['name'] = 'Requirement name is required'
    if 'requirement_type' in data and data['requirement_type'] not in VALID_REQ_TYPES:
        errors['requirement_type'] = f'Must be one of: {", ".join(VALID_REQ_TYPES)}'
    if data.get('document_category') is not None and data.get('document_category') not in VALID_DOCUMENT_CATEGORIES:
        errors['document_category'] = f'Must be one of: {", ".join(VALID_DOCUMENT_CATEGORIES)}'
    _validate_bool_field(data, errors, 'is_mandatory')
    _validate_bool_field(data, errors, 'has_sla')
    _validate_bool_field(data, errors, 'confirm_similar')
    if data.get('has_sla') and not data.get('sla_days'):
        errors['sla_days'] = 'SLA days is required when has_sla is true'
    if 'sla_days' in data and data['sla_days'] is not None:
        if not _is_int(data.get('sla_days')) or data['sla_days'] < 1:
            errors['sla_days'] = 'SLA days must be a positive integer'
    if 'checker_configuration' in data:
        validate_checker_configuration(data['checker_configuration'], errors)
    return errors if errors else None


def validate_requirement_update(data):
    errors = {}
    if not data:
        errors['general'] = 'At least one field is required'
    if 'name' in data and _blank(data.get('name')):
        errors['name'] = 'Requirement name cannot be blank'
    if 'requirement_type' in data and data['requirement_type'] not in VALID_REQ_TYPES:
        errors['requirement_type'] = f'Must be one of: {", ".join(VALID_REQ_TYPES)}'
    if 'document_category' in data and data.get('document_category') is not None and data.get('document_category') not in VALID_DOCUMENT_CATEGORIES:
        errors['document_category'] = f'Must be one of: {", ".join(VALID_DOCUMENT_CATEGORIES)}'
    _validate_bool_field(data, errors, 'is_mandatory')
    _validate_bool_field(data, errors, 'has_sla')
    _validate_bool_field(data, errors, 'confirm_similar')
    if 'has_sla' in data and data['has_sla'] and not data.get('sla_days'):
        errors['sla_days'] = 'SLA days is required when has_sla is true'
    if 'sla_days' in data and data['sla_days'] is not None:
        if not _is_int(data.get('sla_days')) or data['sla_days'] < 1:
            errors['sla_days'] = 'SLA days must be a positive integer'
    if 'checker_configuration' in data:
        validate_checker_configuration(data['checker_configuration'], errors)
    return errors if errors else None

