from app.services import (
    access_service,
    completion_service,
    governance_service,
    lgu_service,
    monitoring_service,
    program_service,
    project_service,
    submission_service,
)


DEFAULT_TYPES = (
    'projects',
    'intake',
    'handoff',
    'lgus',
    'programs',
    'monitoring',
    'guidelines',
    'archive',
    'completion',
)

TYPE_ROLES = {
    'handoff': {'admin', 'staff'},
}


def global_search(search, *, types=None, fiscal_year=None, user_id=None, per_type=5):
    search = str(search or '').strip()
    role = access_service.get_user_role(user_id) if user_id is not None else 'admin'
    selected_types = _types_for_role(_normalize_types(types), role)
    per_type = max(min(int(per_type or 5), 10), 1)

    groups = []
    for result_type in selected_types:
        group = _build_group(result_type, search, fiscal_year=fiscal_year, user_id=user_id, per_type=per_type)
        if group is not None:
            groups.append(group)

    total = sum(group['total'] for group in groups)
    return {
        'query': search,
        'types': selected_types,
        'groups': groups,
        'total': total,
    }


def _build_group(result_type, search, *, fiscal_year, user_id, per_type):
    builders = {
        'projects': _project_group,
        'intake': _intake_group,
        'handoff': _handoff_group,
        'lgus': _lgu_group,
        'programs': _program_group,
        'monitoring': _monitoring_group,
        'guidelines': _guideline_group,
        'archive': _archive_group,
        'completion': _completion_group,
    }
    builder = builders.get(result_type)
    if builder is None:
        return None
    return builder(search, fiscal_year=fiscal_year, user_id=user_id, per_type=per_type)


def _project_group(search, *, fiscal_year, user_id, per_type):
    result = project_service.list_projects(search=search, fiscal_year=fiscal_year, user_id=user_id, per_page=per_type)
    return _group(
        'projects',
        'Projects',
        result['total'],
        [_item(
            'project',
            item.get('id'),
            item.get('project_name'),
            _compact_parts(item.get('overall_status'), item.get('current_phase'), f"FY{item.get('fiscal_year')}" if item.get('fiscal_year') else None),
            f"/dashboard/projects/{item.get('id')}",
            item,
        ) for item in result['projects']],
    )


def _intake_group(search, *, fiscal_year, user_id, per_type):
    result = submission_service.list_intake_queue(search=search, fiscal_year=fiscal_year, user_id=user_id, per_page=per_type)
    return _group(
        'intake',
        'Documentary Intake',
        result['total'],
        [_item(
            'intake_requirement',
            item.get('id'),
            item.get('requirement_name'),
            _compact_parts(item.get('project_name'), item.get('lgu_name'), item.get('status')),
            f"/dashboard/intake?requirement_id={item.get('id')}",
            item,
        ) for item in result['items']],
    )


def _handoff_group(search, *, fiscal_year, user_id, per_type):
    result = submission_service.list_handoff_queue(search=search, fiscal_year=fiscal_year, user_id=user_id, per_page=per_type)
    return _group(
        'handoff',
        'Regional Handoff',
        result['total'],
        [_item(
            'handoff_requirement',
            item.get('id'),
            item.get('requirement_name'),
            _compact_parts(item.get('project_name'), item.get('lgu_name'), item.get('reviewed_at')),
            f"/dashboard/handoff?requirement_id={item.get('id')}",
            item,
        ) for item in result['items']],
    )


def _lgu_group(search, *, fiscal_year, user_id, per_type):
    result = lgu_service.list_lgus(search=search, user_id=user_id, per_page=per_type)
    return _group(
        'lgus',
        'LGUs',
        result['total'],
        [_item(
            'lgu',
            item.get('id'),
            item.get('name'),
            _compact_parts(item.get('municipality'), item.get('province'), item.get('cluster_name')),
            f"/dashboard/lgus/{item.get('id')}",
            item,
        ) for item in result['lgus']],
    )


def _program_group(search, *, fiscal_year, user_id, per_type):
    result = program_service.list_programs(search=search, fiscal_year=fiscal_year, per_page=per_type)
    return _group(
        'programs',
        'Programs',
        result['total'],
        [_item(
            'program',
            item.get('id'),
            item.get('name'),
            _compact_parts(item.get('code'), item.get('program_type')),
            f"/dashboard/programs/{item.get('id')}",
            item,
        ) for item in result['programs']],
    )


def _monitoring_group(search, *, fiscal_year, user_id, per_type):
    result = monitoring_service.list_inspections(search=search, fiscal_year=fiscal_year, user_id=user_id, per_page=per_type)
    return _group(
        'monitoring',
        'Monitoring',
        result['total'],
        [_item(
            'monitoring_inspection',
            item.get('id'),
            item.get('project_name') or f"Inspection #{item.get('id')}",
            _compact_parts(item.get('monitoring_type'), item.get('status'), item.get('inspection_date')),
            f"/dashboard/monitoring?inspection_id={item.get('id')}",
            item,
        ) for item in result['items']],
    )


def _guideline_group(search, *, fiscal_year, user_id, per_type):
    result = governance_service.list_guidelines(search=search, per_page=per_type)
    return _group(
        'guidelines',
        'Guidelines',
        result['total'],
        [_item(
            'guideline',
            item.get('id'),
            item.get('title'),
            _compact_parts(item.get('reference_number'), item.get('guideline_type'), item.get('program_name')),
            f"/dashboard/guidelines?guideline_id={item.get('id')}",
            item,
        ) for item in result['items']],
    )


def _archive_group(search, *, fiscal_year, user_id, per_type):
    result = governance_service.list_archive_records(search=search, fiscal_year=fiscal_year, user_id=user_id, per_page=per_type)
    return _group(
        'archive',
        'Archive',
        result['total'],
        [_item(
            'archive_record',
            item.get('id') or item.get('project_requirement_id'),
            item.get('requirement_name'),
            _compact_parts(item.get('project_name'), item.get('lgu_name'), item.get('status')),
            f"/dashboard/archive?requirement_id={item.get('id') or item.get('project_requirement_id')}",
            item,
        ) for item in result['items']],
    )


def _completion_group(search, *, fiscal_year, user_id, per_type):
    result = completion_service.list_completion_projects(search=search, fiscal_year=fiscal_year, user_id=user_id, per_page=per_type)
    return _group(
        'completion',
        'Completion',
        result['total'],
        [_item(
            'completion_project',
            item.get('id') or item.get('project_id'),
            item.get('project_name'),
            _compact_parts(item.get('lgu_name'), item.get('completion_status'), item.get('physical_completion_date')),
            f"/dashboard/completion?project_id={item.get('id') or item.get('project_id')}",
            item,
        ) for item in result['projects']],
    )


def _group(result_type, label, total, items):
    return {
        'type': result_type,
        'label': label,
        'total': total,
        'items': items,
    }


def _item(result_type, item_id, title, subtitle, url, raw):
    return {
        'type': result_type,
        'id': item_id,
        'title': title or f'{result_type.replace("_", " ").title()} #{item_id}',
        'subtitle': subtitle,
        'url': url,
        'raw': raw,
        'search_score': raw.get('search_score') if isinstance(raw, dict) else None,
        'matched_fields': raw.get('matched_fields') if isinstance(raw, dict) else [],
    }


def _normalize_types(types):
    if not types:
        return DEFAULT_TYPES
    if isinstance(types, str):
        values = [item.strip().lower() for item in types.split(',')]
    else:
        values = [str(item).strip().lower() for item in types]
    selected = []
    for value in values:
        if value in DEFAULT_TYPES and value not in selected:
            selected.append(value)
    return tuple(selected or DEFAULT_TYPES)


def _types_for_role(types, role):
    return tuple(
        result_type
        for result_type in types
        if role in TYPE_ROLES.get(result_type, {'admin', 'staff', 'field_officer'})
    )


def _compact_parts(*parts):
    values = [str(part) for part in parts if part not in (None, '')]
    return ' | '.join(values)
