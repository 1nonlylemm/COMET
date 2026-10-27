from collections import OrderedDict

from app.models import LguProfile, Project
from app.services import access_service, monitoring_service, sla_service
from app.services.fiscal_year_scope import apply_project_fiscal_year
from app.services.project_status import ACTION_BUCKETS, CANONICAL_PROJECT_STATUSES, classify_monitoring_action


def get_operations_dashboard(user_id, fiscal_year=None):
    projects = _visible_projects(user_id=user_id, fiscal_year=fiscal_year)
    total_projects = len(projects)
    status_counts = _status_counts(projects)
    action_counts = _action_counts(projects)
    cluster_rows = _cluster_status_rows(projects)
    progress_bands = _progress_bands(projects)
    sla_dashboard = sla_service.get_sla_dashboard(user_id=user_id, fiscal_year=fiscal_year)
    monitoring_workbench = monitoring_service.get_monitoring_workbench(user_id=user_id, fiscal_year=fiscal_year)

    return {
        'scope': {
            'fiscal_year': fiscal_year,
            'total_projects': total_projects,
        },
        'status_summary': {
            'total': total_projects,
            'items': [
                {
                    'key': status,
                    'label': _status_label(status),
                    'count': status_counts.get(status, 0),
                    'percentage': _percentage(status_counts.get(status, 0), total_projects),
                }
                for status in CANONICAL_PROJECT_STATUSES
            ],
        },
        'cluster_status_summary': cluster_rows,
        'progress_bands': progress_bands,
        'action_summary': [
            {
                'key': bucket['key'],
                'label': bucket['label'],
                'short_label': bucket['short_label'],
                'count': action_counts.get(bucket['key'], 0),
            }
            for bucket in ACTION_BUCKETS
        ],
        'sla_summary': sla_dashboard,
        'monitoring_summary': monitoring_workbench.get('summary') or {},
    }


def _visible_projects(user_id, fiscal_year=None):
    query = Project.query.join(LguProfile, Project.lgu_id == LguProfile.id)
    query = access_service.restrict_project_query(query, user_id)
    query = apply_project_fiscal_year(query, fiscal_year)
    return query.order_by(Project.fiscal_year.desc(), Project.project_name.asc()).all()


def _status_counts(projects):
    counts = {status: 0 for status in CANONICAL_PROJECT_STATUSES}
    for project in projects:
        if project.overall_status in counts:
            counts[project.overall_status] += 1
    return counts


def _cluster_status_rows(projects):
    rows = OrderedDict()
    for project in projects:
        lgu = project.lgu
        cluster = lgu.cluster if lgu else None
        key = cluster.id if cluster else 'unclustered'
        if key not in rows:
            rows[key] = {
                'cluster_id': cluster.id if cluster else None,
                'cluster_name': cluster.name if cluster else 'PGL / Unclustered',
                'total': 0,
                'statuses': {status: 0 for status in CANONICAL_PROJECT_STATUSES},
            }
        rows[key]['total'] += 1
        if project.overall_status in rows[key]['statuses']:
            rows[key]['statuses'][project.overall_status] += 1

    return list(rows.values())


def _progress_bands(projects):
    bands = [
        {'key': 'zero', 'label': '0%', 'min': 0, 'max': 0, 'count': 0},
        {'key': 'early', 'label': '1-49%', 'min': 1, 'max': 49, 'count': 0},
        {'key': 'mid', 'label': '50-89%', 'min': 50, 'max': 89, 'count': 0},
        {'key': 'near_complete', 'label': '90-99%', 'min': 90, 'max': 99, 'count': 0},
        {'key': 'complete', 'label': '100%', 'min': 100, 'max': 100, 'count': 0},
    ]
    for project in projects:
        value = _numeric_progress(project.physical_completion_pct)
        for band in bands:
            if value >= band['min'] and value <= band['max']:
                band['count'] += 1
                break
    total = len(projects)
    return [
        {
            'key': band['key'],
            'label': band['label'],
            'count': band['count'],
            'percentage': _percentage(band['count'], total),
        }
        for band in bands
    ]


def _action_counts(projects):
    counts = {bucket['key']: 0 for bucket in ACTION_BUCKETS}
    for project in projects:
        key = classify_monitoring_action(_monitoring_text(project))
        if key in counts:
            counts[key] += 1
    return counts


def _monitoring_text(project):
    parts = [project.notes or '']
    custom_fields = project.custom_fields or {}
    if isinstance(custom_fields, dict):
        parts.extend(_flatten_custom_values(custom_fields))
    return ' '.join(str(part) for part in parts if part not in (None, ''))


def _flatten_custom_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _flatten_custom_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_custom_values(item)
    elif value not in (None, ''):
        yield str(value)


def _numeric_progress(value):
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, numeric))


def _percentage(count, total):
    if not total:
        return 0
    return round((count / total) * 100, 1)


def _status_label(status):
    labels = {
        'not_yet_started': 'Not Yet Started',
        'ongoing': 'Ongoing',
        'completed': 'Completed',
        'cancelled': 'Cancelled',
    }
    return labels.get(status, str(status or '').replace('_', ' ').title())

