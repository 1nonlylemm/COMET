from app.constants.roles import INTERNAL_USER_ROLES


def _role_error():
    return f'Must be one of: {", ".join(INTERNAL_USER_ROLES)}'


def validate_register(data):
    errors = {}
    if not data.get('email'):
        errors['email'] = 'Email is required'
    elif '@' not in data.get('email', ''):
        errors['email'] = 'Invalid email format'

    if not data.get('password'):
        errors['password'] = 'Password is required'
    elif len(data.get('password', '')) < 8:
        errors['password'] = 'Password must be at least 8 characters'

    if not data.get('first_name'):
        errors['first_name'] = 'First name is required'
    if not data.get('last_name'):
        errors['last_name'] = 'Last name is required'

    role = data.get('role', 'staff')
    if role not in INTERNAL_USER_ROLES:
        errors['role'] = _role_error()

    return errors if errors else None


def validate_admin_user_create(data):
    errors = {}
    if not data.get('email'):
        errors['email'] = 'Email is required'
    elif '@' not in data.get('email', ''):
        errors['email'] = 'Invalid email format'

    if not data.get('first_name'):
        errors['first_name'] = 'First name is required'
    if not data.get('last_name'):
        errors['last_name'] = 'Last name is required'

    role = data.get('role')
    if not role:
        errors['role'] = 'Role is required'
    elif role not in INTERNAL_USER_ROLES:
        errors['role'] = _role_error()

    cluster_ids = data.get('cluster_ids')
    if cluster_ids is not None and not isinstance(cluster_ids, list):
        errors['cluster_ids'] = 'cluster_ids must be an array of cluster IDs'
    lgu_ids = data.get('lgu_ids')
    if lgu_ids is not None and not isinstance(lgu_ids, list):
        errors['lgu_ids'] = 'lgu_ids must be an array of LGU IDs'

    return errors if errors else None


def validate_change_role(data):
    errors = {}
    role = data.get('role') if data else None
    if not role:
        errors['role'] = 'Role is required'
    elif role not in INTERNAL_USER_ROLES:
        errors['role'] = _role_error()

    cluster_ids = data.get('cluster_ids') if data else None
    if cluster_ids is not None and not isinstance(cluster_ids, list):
        errors['cluster_ids'] = 'cluster_ids must be an array of cluster IDs'
    lgu_ids = data.get('lgu_ids') if data else None
    if lgu_ids is not None and not isinstance(lgu_ids, list):
        errors['lgu_ids'] = 'lgu_ids must be an array of LGU IDs'

    return errors if errors else None


def validate_toggle_active(data):
    errors = {}
    if not data or 'is_active' not in data:
        errors['is_active'] = 'is_active is required'
    elif not isinstance(data.get('is_active'), bool):
        errors['is_active'] = 'is_active must be true or false'
    return errors if errors else None


def validate_login(data):
    errors = {}
    if not data.get('email'):
        errors['email'] = 'Email is required'
    if not data.get('password'):
        errors['password'] = 'Password is required'
    return errors if errors else None


COMMON_PASSWORDS_BLACKLIST = {
    'password', 'password123', 'password1234', '12345678', '123456789', '1234567890',
    'admin123', 'admin1234', 'qwertyuiop', 'welcome123', 'letmein123', 'changeme123',
    'comet123456', 'p@ssword123', 'p@ssw0rd123', 'administrator', 'iloveyou123',
    'secret123', 'foobar123', 'password1234!', 'password12345!', 'password12345678!',
    'admin1234567!', 'admin12345678!', 'welcome12345!'
}


def validate_password_strength(password, user_identifier=None, email=None):
    if not password:
        return 'Password is required'
    if len(password) < 12:
        return 'Password must be at least 12 characters'
    if not any(c.isupper() for c in password):
        return 'Password must contain at least one uppercase letter'
    if not any(c.islower() for c in password):
        return 'Password must contain at least one lowercase letter'
    if not any(c.isdigit() for c in password):
        return 'Password must contain at least one number'
    if not any(not c.isalnum() for c in password):
        return 'Password must contain at least one special character'
    if password.lower() in COMMON_PASSWORDS_BLACKLIST:
        return 'Password is too common or easily guessable'
    identifier = user_identifier or email
    if identifier:
        localpart = identifier.split('@')[0].lower()
        if len(localpart) >= 3 and localpart in password.lower():
            return 'Password must not contain parts of your email address'
    return None


def validate_change_password(data, user_email=None):
    errors = {}
    if not data or not data.get('current_password'):
        errors['current_password'] = 'Current password is required'
    if not data or not data.get('new_password'):
        errors['new_password'] = 'New password is required'
    else:
        pwd_error = validate_password_strength(data.get('new_password'), user_identifier=user_email)
        if pwd_error:
            errors['new_password'] = pwd_error
    return errors if errors else None


def validate_forgot_password(data):
    errors = {}
    if not data or not data.get('email'):
        errors['email'] = 'Email is required'
    elif '@' not in data.get('email', ''):
        errors['email'] = 'Invalid email format'
    return errors if errors else None


def validate_reset_password(data):
    errors = {}
    if not data or not data.get('token'):
        errors['token'] = 'Reset token is required'
    if not data or not data.get('new_password'):
        errors['new_password'] = 'New password is required'
    else:
        pwd_error = validate_password_strength(data.get('new_password'))
        if pwd_error:
            errors['new_password'] = pwd_error
    return errors if errors else None


def validate_mfa_verify(data):
    errors = {}
    if not data or (not data.get('code') and not data.get('recovery_code')):
        errors['code'] = 'Verification code or recovery code is required'
    return errors if errors else None


def validate_step_up(data):
    errors = {}
    if not data or not data.get('password'):
        errors['password'] = 'Password is required'
    return errors if errors else None


def validate_update_profile(data):
    errors = {}
    if 'email' in data and data['email'] and '@' not in data['email']:
        errors['email'] = 'Invalid email format'
    return errors if errors else None
