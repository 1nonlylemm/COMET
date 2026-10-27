def validate_completion_update(data):
    errors = {}
    for field in ('physical_completion_pct', 'punchlist_items_total', 'punchlist_items_resolved'):
        if field in data and data[field] is not None:
            value = data[field]
            if field == 'physical_completion_pct':
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors[field] = 'physical_completion_pct must be a JSON number'
                    continue
                if value < 0 or value > 100:
                    errors[field] = 'physical_completion_pct must be between 0 and 100'
                continue

            if isinstance(value, bool) or not isinstance(value, int):
                errors[field] = f'{field} must be a JSON integer'
                continue
            if value < 0:
                errors[field] = f'{field} must be non-negative'

    for field in (
        'has_certificate_of_completion',
        'is_final_swa_applicable',
        'has_final_swa',
        'has_annex_j',
        'is_vault_ready',
        'final_approval',
    ):
        if field in data and not isinstance(data[field], bool):
            errors[field] = f'{field} must be a boolean'

    if 'final_swa_applicability_reason' in data:
        if data['final_swa_applicability_reason'] is not None and not isinstance(data['final_swa_applicability_reason'], str):
            errors['final_swa_applicability_reason'] = 'final_swa_applicability_reason must be a string'

    if 'punchlist_items_total' in data and 'punchlist_items_resolved' in data:
        total = data.get('punchlist_items_total')
        resolved = data.get('punchlist_items_resolved')
        if total is not None and resolved is not None:
            try:
                if int(resolved) > int(total):
                    errors['punchlist_items_resolved'] = 'Resolved punchlist items cannot exceed the total'
            except (TypeError, ValueError):
                pass

    return errors if errors else None
