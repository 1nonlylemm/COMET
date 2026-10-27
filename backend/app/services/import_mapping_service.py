from app.services.import_field_catalog import match_canonical_field, normalize_label, suggest_column_role


PROJECT_SHEET_TYPES = {
    'project_master',
    'implementation_monitoring',
    'pre_implementation_requirements',
    'fund_release',
    'notice_to_implement',
}

STATUS_COMPLIANT = {'true', 'submitted', 'complete', 'completed', 'compliant', '100 utilized', '100% utilized', 'enrolled'}
STATUS_PENDING = {'false', 'no submission', 'pending', 'not submitted', 'not yet submitted', 'not yet applicable', 'blank'}
STATUS_WAIVED = {'n a', 'na', 'not applicable'}
STATUS_REVIEW = {
    'ongoing application',
    'on going application',
    'under review',
    'for review',
    'endorsed',
    'returned',
    'deficient',
}
STATUS_NON_COMPLIANT = {'not cleared', 'non compliant', 'non-compliant'}


def build_mapping(profile, template=None):
    template_columns = (template.get('column_mappings') if isinstance(template, dict)
                        else getattr(template, 'column_mappings', None)) or {}
    sheet_mappings = []
    all_mappings = []

    for sheet in profile.get('sheets', []):
        sheet_mapping = {
            'sheet_name': sheet.get('name'),
            'sheet_type': sheet.get('sheet_type'),
            'field_mappings': [],
            'unmapped_columns': [],
        }
        for column in sheet.get('columns', []):
            mapping = _map_column(sheet, column, template_columns)
            if mapping.get('target_field'):
                sheet_mapping['field_mappings'].append(mapping)
                all_mappings.append(mapping)
            else:
                unmapped = {
                    'source_sheet': sheet.get('name'),
                    'source_column': column.get('column'),
                    'source_header': column.get('header'),
                    'header_path': column.get('header_path') or [],
                    'suggested_role': mapping.get('suggested_role', 'custom_field'),
                    'confidence': mapping.get('confidence', 0.35),
                }
                sheet_mapping['unmapped_columns'].append(unmapped)
                all_mappings.append(unmapped)
        sheet_mappings.append(sheet_mapping)

    return {
        'schema_signature': profile.get('schema_signature'),
        'sheet_mappings': sheet_mappings,
        'field_mappings': all_mappings,
    }


def normalize_requirement_status(value):
    normalized = normalize_label(value)
    if normalized in STATUS_COMPLIANT:
        return 'compliant'
    if normalized in STATUS_WAIVED:
        return 'waived'
    if normalized in STATUS_REVIEW:
        return 'under_review'
    if normalized in STATUS_NON_COMPLIANT:
        return 'non_compliant'
    if normalized in STATUS_PENDING or normalized == '':
        return 'pending'
    return 'under_review'


def is_project_sheet(sheet):
    return sheet.get('sheet_type') in PROJECT_SHEET_TYPES


def _map_column(sheet, column, template_columns):
    source_key = f"{sheet.get('name')}::{column.get('column')}"
    normalized_header = column.get('normalized_header') or ''
    template_mapping = template_columns.get(source_key) or template_columns.get(normalized_header)
    if template_mapping:
        return {
            'source_sheet': sheet.get('name'),
            'source_column': column.get('column'),
            'source_header': column.get('header'),
            'header_path': column.get('header_path') or [],
            'target_field': template_mapping.get('target_field'),
            'suggested_role': template_mapping.get('suggested_role'),
            'confidence': 1.0,
            'mapping_type': 'template',
        }

    match = match_canonical_field(column.get('header_path'), sample_values=column.get('sample_values'))
    if match:
        return {
            'source_sheet': sheet.get('name'),
            'source_column': column.get('column'),
            'source_header': column.get('header'),
            'header_path': column.get('header_path') or [],
            'target_field': match['target_field'],
            'confidence': match['confidence'],
            'mapping_type': 'auto',
            'reason': match['reason'],
        }

    role = suggest_column_role(column.get('header_path'), sample_values=column.get('sample_values'))
    return {
        'source_sheet': sheet.get('name'),
        'source_column': column.get('column'),
        'source_header': column.get('header'),
        'header_path': column.get('header_path') or [],
        'suggested_role': role,
        'confidence': 0.58 if role == 'requirement' else 0.35,
        'mapping_type': 'suggested',
    }
