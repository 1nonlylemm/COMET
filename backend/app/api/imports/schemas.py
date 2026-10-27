def validate_template_payload(data, require_program=True):
    errors = {}
    if not data:
        errors['general'] = 'Request data is required'
        return errors
    if require_program and not data.get('program_id'):
        errors['program_id'] = 'Program is required'
    if 'program_id' in data and data.get('program_id') is not None and not isinstance(data['program_id'], int):
        errors['program_id'] = 'Program ID must be an integer'
    if 'program_cycle_id' in data and data.get('program_cycle_id') is not None and not isinstance(data['program_cycle_id'], int):
        errors['program_cycle_id'] = 'Program cycle ID must be an integer'
    if 'file_type' in data and data.get('file_type') not in {'csv', 'xlsx', 'xls'}:
        errors['file_type'] = 'File type must be csv, xlsx, or xls'
    if 'status' in data and data.get('status') not in {'draft', 'active', 'superseded', 'archived'}:
        errors['status'] = 'Invalid template status'
    for field in ('is_active', 'lock'):
        if field in data and data.get(field) is not None and not isinstance(data.get(field), bool):
            errors[field] = f'{field} must be true or false'
    return errors if errors else None
