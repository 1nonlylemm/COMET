def validate_inspection_payload(data, partial=False):
    errors = {}

    if not partial:
        if not data.get('project_id'):
            errors['project_id'] = 'project_id is required'
        if not data.get('inspection_date'):
            errors['inspection_date'] = 'inspection_date is required'

    if 'status' in data and data.get('status') not in {'draft', 'submitted', 'reviewed', 'approved', 'flagged'}:
        errors['status'] = 'status must be one of: draft, submitted, reviewed, approved, flagged'
    if 'monitoring_type' in data and data.get('monitoring_type') != 'qaar':
        errors['monitoring_type'] = 'monitoring_type must be qaar'
    if 'is_site_visit' in data and data.get('is_site_visit') is not None and not isinstance(data.get('is_site_visit'), bool):
        errors['is_site_visit'] = 'is_site_visit must be true or false'
    if 'transmittal_status' in data and data.get('transmittal_status') not in {'not_required', 'pending', 'transmitted', 'acknowledged'}:
        errors['transmittal_status'] = 'transmittal_status must be one of: not_required, pending, transmitted, acknowledged'

    if 'project_id' in data and data.get('project_id') in ('', None):
        errors['project_id'] = 'project_id is required'
    if 'physical_accomplishment_pct' in data and data.get('physical_accomplishment_pct') not in (None, ''):
        try:
            value = float(data['physical_accomplishment_pct'])
        except (TypeError, ValueError):
            errors['physical_accomplishment_pct'] = 'physical_accomplishment_pct must be numeric'
        else:
            if value < 0 or value > 100:
                errors['physical_accomplishment_pct'] = 'physical_accomplishment_pct must be between 0 and 100'

    return errors if errors else None
