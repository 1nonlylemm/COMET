def validate_system_config_payload(data, partial=False):
    errors = {}

    if not partial:
        if not data.get('key'):
            errors['key'] = 'key is required'
        if not data.get('value_type'):
            errors['value_type'] = 'value_type is required'

    if 'value_type' in data and data.get('value_type') not in {'string', 'integer', 'boolean', 'json', 'secret'}:
        errors['value_type'] = 'value_type must be one of: string, integer, boolean, json, secret'

    return errors if errors else None
