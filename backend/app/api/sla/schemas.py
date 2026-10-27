VALID_DEADLINE_TYPES = ('notice_of_eligibility_5day', 'standard_15day', 'custom_sla', 'rectification_period')


def validate_sla_create(data):
    errors = {}
    if not data.get('project_id'):
        errors['project_id'] = 'Project is required'
    elif not isinstance(data['project_id'], int):
        errors['project_id'] = 'Project ID must be an integer'
    if not data.get('deadline_type'):
        errors['deadline_type'] = 'Deadline type is required'
    elif data['deadline_type'] not in VALID_DEADLINE_TYPES:
        errors['deadline_type'] = f'Must be one of: {", ".join(VALID_DEADLINE_TYPES)}'
    if not data.get('trigger_date'):
        errors['trigger_date'] = 'Trigger date is required'
    if not data.get('deadline_date'):
        errors['deadline_date'] = 'Deadline date is required'
    if 'sla_working_days' in data and data['sla_working_days'] is not None:
        if not isinstance(data['sla_working_days'], int) or data['sla_working_days'] < 1:
            errors['sla_working_days'] = 'Must be a positive integer'
    if 'project_requirement_id' in data and data['project_requirement_id'] is not None:
        if not isinstance(data['project_requirement_id'], int):
            errors['project_requirement_id'] = 'Must be an integer'
    return errors if errors else None


def validate_sla_update(data):
    errors = {}
    if not data:
        errors['general'] = 'At least one field is required'
    if 'deadline_type' in data and data['deadline_type'] not in VALID_DEADLINE_TYPES:
        errors['deadline_type'] = f'Must be one of: {", ".join(VALID_DEADLINE_TYPES)}'
    if 'sla_working_days' in data and data['sla_working_days'] is not None:
        if not isinstance(data['sla_working_days'], int) or data['sla_working_days'] < 1:
            errors['sla_working_days'] = 'Must be a positive integer'
    if 'deadline_date' in data and data['deadline_date']:
        pass  # valid string date
    if 'notes' in data and data['notes'] and len(data['notes']) > 2000:
        errors['notes'] = 'Notes must be 2000 characters or less'
    if 'escalation_triggered' in data and data['escalation_triggered'] is not None:
        if not isinstance(data['escalation_triggered'], bool):
            errors['escalation_triggered'] = 'escalation_triggered must be true or false'
    return errors if errors else None


def validate_sla_resolve(data):
    errors = {}
    if data.get('notes') and len(data['notes']) > 2000:
        errors['notes'] = 'Notes must be 2000 characters or less'
    return errors if errors else None
