def validate_magic_link_create(data):
    errors = {}
    if not isinstance(data, dict):
        errors['general'] = 'Request body must be an object'
        return errors

    notice_id = data.get('notice_id')
    project_id = data.get('project_id')
    if notice_id is None and project_id is None:
        errors['notice_id'] = 'notice_id or project_id is required'

    if notice_id is not None and (not isinstance(notice_id, int) or notice_id < 1):
        errors['notice_id'] = 'notice_id must be a positive integer'

    if project_id is not None and (not isinstance(project_id, int) or project_id < 1):
        errors['project_id'] = 'project_id must be a positive integer'

    expires_in_days = data.get('expires_in_days')
    if expires_in_days is not None and (not isinstance(expires_in_days, int) or expires_in_days < 1):
        errors['expires_in_days'] = 'expires_in_days must be a positive integer'

    for field in ('intended_recipient_name', 'intended_recipient_role'):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors[field] = f'{field} must be a string'

    return errors if errors else None
