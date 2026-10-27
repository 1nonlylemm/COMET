VALID_NOTICE_TYPES = ('annex_e', 'annex_m', 'annex_n', 'annex_o')
VALID_NOTICE_STATUSES = ('draft', 'reviewed', 'sent', 'acknowledged', 'expired')
VALID_OUTPUT_FORMATS = ('html', 'pdf', 'docx')
VALID_DISPATCH_CHANNELS = ('email', 'dms', 'intranet', 'manual_print')


def validate_generate_notice_request(data):
    errors = {}
    if not isinstance(data, dict):
        errors['general'] = 'Request body must be an object'
        return errors

    if 'sla_id' in data and data['sla_id'] is not None:
        if not isinstance(data['sla_id'], int) or data['sla_id'] < 1:
            errors['sla_id'] = 'sla_id must be a positive integer'

    return errors if errors else None


def validate_notice_create(data):
    errors = {}
    if not isinstance(data, dict):
        errors['general'] = 'Request body must be an object'
        return errors

    if not data.get('project_id'):
        errors['project_id'] = 'project_id is required'
    elif not isinstance(data['project_id'], int) or data['project_id'] < 1:
        errors['project_id'] = 'project_id must be a positive integer'

    if not data.get('notice_type'):
        errors['notice_type'] = 'notice_type is required'
    elif data['notice_type'] not in VALID_NOTICE_TYPES:
        errors['notice_type'] = f'Must be one of: {", ".join(VALID_NOTICE_TYPES)}'

    if 'trigger_sla_id' in data and data['trigger_sla_id'] is not None:
        if not isinstance(data['trigger_sla_id'], int) or data['trigger_sla_id'] < 1:
            errors['trigger_sla_id'] = 'trigger_sla_id must be a positive integer'

    if 'trigger_project_requirement_id' in data and data['trigger_project_requirement_id'] is not None:
        if not isinstance(data['trigger_project_requirement_id'], int) or data['trigger_project_requirement_id'] < 1:
            errors['trigger_project_requirement_id'] = 'trigger_project_requirement_id must be a positive integer'

    if 'status' in data and data['status']:
        if str(data['status']).strip().lower() == 'sent':
            errors['status'] = 'Notices cannot be created in sent status. Use the release action to mark a notice released.'
        elif str(data['status']).strip().lower() != 'draft':
            errors['status'] = "New notices must be created with status 'draft'"

    if 'legal_findings' in data and data['legal_findings'] is not None and not isinstance(data['legal_findings'], list):
        errors['legal_findings'] = 'legal_findings must be a list'

    return errors if errors else None


def validate_notice_update(data):
    errors = {}
    if not isinstance(data, dict) or not data:
        errors['general'] = 'At least one field is required'
        return errors

    if 'status' in data and data['status'] and data['status'] not in VALID_NOTICE_STATUSES:
        errors['status'] = f'Must be one of: {", ".join(VALID_NOTICE_STATUSES)}'

    if 'legal_findings' in data and data['legal_findings'] is not None and not isinstance(data['legal_findings'], list):
        errors['legal_findings'] = 'legal_findings must be a list'

    if 'title' in data and data['title'] is not None and len(data['title']) > 500:
        errors['title'] = 'title must be 500 characters or less'

    if 'body_text' in data and data['body_text'] is not None and not isinstance(data['body_text'], str):
        errors['body_text'] = 'body_text must be a string'

    if 'final_text' in data and data['final_text'] is not None and not isinstance(data['final_text'], str):
        errors['final_text'] = 'final_text must be a string'

    if 'acknowledged_at' in data and data['acknowledged_at'] is not None and not isinstance(data['acknowledged_at'], str):
        errors['acknowledged_at'] = 'acknowledged_at must be an ISO timestamp string'

    return errors if errors else None


def validate_notice_document_params(params):
    errors = {}
    output_format = params.get('format', 'pdf')
    if output_format not in VALID_OUTPUT_FORMATS:
        errors['format'] = f'Must be one of: {", ".join(VALID_OUTPUT_FORMATS)}'
    return errors if errors else None


def validate_notice_release(data):
    errors = {}
    if not isinstance(data, dict):
        errors['general'] = 'Request body must be an object'
        return errors

    channel = data.get('channel')
    if not isinstance(channel, str) or channel not in VALID_DISPATCH_CHANNELS:
        errors['channel'] = f'channel must be one of: {", ".join(VALID_DISPATCH_CHANNELS)}'

    if 'released_at' in data and data['released_at'] is not None and not isinstance(data['released_at'], str):
        errors['released_at'] = 'released_at must be an ISO timestamp string'

    for field in ('recipient_name', 'recipient_destination', 'recipient_office', 'reference_no', 'remarks'):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors[field] = f'{field} must be a string'

    return errors if errors else None


def validate_notice_receipt(data):
    errors = {}
    if not isinstance(data, dict):
        errors['general'] = 'Request body must be an object'
        return errors

    acknowledged_at = data.get('acknowledged_at')
    if not isinstance(acknowledged_at, str) or not acknowledged_at.strip():
        errors['acknowledged_at'] = 'acknowledged_at is required as an ISO timestamp string'

    if 'remarks' in data and data['remarks'] is not None and not isinstance(data['remarks'], str):
        errors['remarks'] = 'remarks must be a string'

    return errors if errors else None


def validate_ai_draft_request(data):
    errors = {}
    if not isinstance(data, dict):
        errors['general'] = 'Request body must be an object'
        return errors

    informal_notes = data.get('informal_notes')
    if not isinstance(informal_notes, str) or not informal_notes.strip():
        errors['informal_notes'] = 'informal_notes is required'

    if 'finding_id' in data and data['finding_id'] is not None:
        if not isinstance(data['finding_id'], int) or data['finding_id'] < 1:
            errors['finding_id'] = 'finding_id must be a positive integer'

    return errors if errors else None


def validate_dispatch_request(data):
    errors = {}
    if not isinstance(data, dict):
        errors['general'] = 'Request body must be an object'
        return errors

    channel = data.get('channel')
    if not isinstance(channel, str) or channel not in VALID_DISPATCH_CHANNELS:
        errors['channel'] = f'channel must be one of: {", ".join(VALID_DISPATCH_CHANNELS)}'

    if 'magic_link_id' in data and data['magic_link_id'] is not None:
        if not isinstance(data['magic_link_id'], int) or data['magic_link_id'] < 1:
            errors['magic_link_id'] = 'magic_link_id must be a positive integer'

    for field in ('recipient_name', 'recipient_destination', 'recipient_office', 'reference_no', 'remarks'):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors[field] = f'{field} must be a string'

    return errors if errors else None
