def validate_cluster_create(data):
    errors = {}
    if not data.get('name'):
        errors['name'] = 'Cluster name is required'
    return errors if errors else None


def validate_cluster_update(data):
    errors = {}
    if not data:
        errors['general'] = 'At least one field is required'
    return errors if errors else None


def validate_lgu_create(data):
    errors = {}
    if not data.get('name'):
        errors['name'] = 'LGU name is required'
    if not data.get('municipality'):
        errors['municipality'] = 'Municipality is required'
    return errors if errors else None


def validate_lgu_update(data):
    errors = {}
    if not data:
        errors['general'] = 'At least one field is required'
    return errors if errors else None


def validate_staff_assignment(data):
    errors = {}
    if not data.get('user_id'):
        errors['user_id'] = 'User ID is required'
    if not data.get('cluster_id'):
        errors['cluster_id'] = 'Cluster ID is required'
    return errors if errors else None


def validate_field_assignment(data):
    errors = {}
    if not data.get('user_id'):
        errors['user_id'] = 'User ID is required'
    if not data.get('lgu_id'):
        errors['lgu_id'] = 'LGU ID is required'
    return errors if errors else None


def validate_lgu_toggle_active(data):
    errors = {}
    if data and 'is_active' in data and not isinstance(data.get('is_active'), bool):
        errors['is_active'] = 'is_active must be true or false'
    return errors if errors else None
