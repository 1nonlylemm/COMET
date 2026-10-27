from collections import OrderedDict
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import LguCluster, LguProfile, Program, Project, ProjectRequirement, User
from app.models.escalation import SlaDeadline
from app.models.field_inspection import QaarInspection, QaarWorkFinding
from app.models.completion import CompletionMilestone, GoogleDrivePush
from app.models.completion_extras import CompletionDocumentRecord
from app.models.monitoring_extras import (
    BeneficiaryEvidenceRecord,
    MonthlyProgressReport,
    NonInfraMonitoringRecord,
)
from app.models.workflow import (
    RequirementWorkflowTransition,
    RequirementDeficiency,
    DEFICIENCY_CATEGORIES,
    DEFICIENCY_RESOLUTION_STATES,
    WORKFLOW_STATES,
)
from app.services import access_service, working_day_service
from app.services.fiscal_year_scope import apply_project_fiscal_year
from app.services.project_service import resolve_effective_project_kind
from app.services.project_status import (
    CANONICAL_PROJECT_STATUSES,
    normalize_project_status,
    project_status_label,
)
from app.services.sla_service import filter_active_compliance_deadlines

WORKFLOW_ACTIONS = (
    'submit',
    'verify',
    'staff_approve',
    'provincial_approve',
    'return_for_revision',
    'resubmit',
)

PROJECT_PHASES = (
    'pre_implementation',
    'implementation',
    'completion',
)


def _workflow_action_label(action):
    labels = {
        'submit': 'Submit',
        'verify': 'Verify',
        'staff_approve': 'Staff Approve',
        'provincial_approve': 'Provincial Approve',
        'return_for_revision': 'Return for Revision',
        'resubmit': 'Resubmit',
    }
    return labels.get(action, action.replace('_', ' ').title() if action else 'Unknown')


def _project_phase_label(phase):
    labels = {
        'pre_implementation': 'Pre-Implementation',
        'implementation': 'Implementation',
        'completion': 'Completion',
    }
    return labels.get(phase, phase.replace('_', ' ').title() if phase else 'Unknown')


def _project_phase_tone(phase):
    tones = {
        'pre_implementation': 'info',
        'implementation': 'warning',
        'completion': 'success',
    }
    return tones.get(phase, 'neutral')


SLIPPAGE_TIERS = (
    'critical',
    'delayed',
    'slightly_delayed',
    'on_track',
    'unreported',
)

SLIPPAGE_TIER_CONFIG = {
    'critical': {
        'label': 'Critical Delay (< -15 pp)',
        'short_label': 'Critical Delay',
        'range': '< -15 pp',
        'tone': 'rose',
    },
    'delayed': {
        'label': 'Delayed (-15 pp to < -5 pp)',
        'short_label': 'Delayed',
        'range': '-15 pp to < -5 pp',
        'tone': 'amber',
    },
    'slightly_delayed': {
        'label': 'Slightly Delayed (-5 pp to < 0 pp)',
        'short_label': 'Slightly Delayed',
        'range': '-5 pp to < 0 pp',
        'tone': 'yellow',
    },
    'on_track': {
        'label': 'On Track / Ahead (≥ 0 pp)',
        'short_label': 'On Track',
        'range': '≥ 0 pp',
        'tone': 'emerald',
    },
    'unreported': {
        'label': 'Unreported / Incomplete MPR',
        'short_label': 'Unreported',
        'range': 'N/A',
        'tone': 'slate',
    },
}

QAAR_SEVERITIES = ('severe', 'major', 'minor')
QAAR_SEVERITY_CONFIG = {
    'severe': {'label': 'Severe Defect', 'tone': 'rose'},
    'major': {'label': 'Major Defect', 'tone': 'amber'},
    'minor': {'label': 'Minor Defect', 'tone': 'yellow'},
    'unclassified': {'label': 'Unclassified', 'tone': 'slate'},
}

EVIDENCE_TYPE_LABELS = {
    'signed_distribution_list': 'Signed Distribution List',
    'acknowledgement_receipt': 'Acknowledgement Receipt',
    'beneficiary_tracking_record': 'Beneficiary Tracking Record',
    'turnover_photos': 'Turnover Photos',
    'delivery_invoice': 'Delivery Invoice',
}


def _determine_slippage_tier(variance_pct):
    if variance_pct is None:
        return 'unreported'
    try:
        val = float(variance_pct)
    except (ValueError, TypeError):
        return 'unreported'
    if val < -15.0:
        return 'critical'
    elif val < -5.0:
        return 'delayed'
    elif val < 0.0:
        return 'slightly_delayed'
    else:
        return 'on_track'


def _schedule_variance(mpr):
    """Report actual minus target, in percentage points; never trust stale stored variance.

    MPR writes store target minus actual. Historical imports have also stored the
    opposite sign, so use the source percentages whenever both are available.
    """
    if mpr is None:
        return None
    if mpr.target_to_date_pct is not None and mpr.actual_to_date_pct is not None:
        return float(mpr.actual_to_date_pct - mpr.target_to_date_pct)
    return None


REQUIREMENT_STATUSES = ('pending', 'under_review', 'compliant', 'non_compliant', 'waived')
PROGRESS_BANDS = (
    {'key': 'zero', 'label': '0%', 'min': 0, 'max': 0},
    {'key': 'early', 'label': '>0–<50%', 'min': 1, 'max': 49},
    {'key': 'mid', 'label': '50–<90%', 'min': 50, 'max': 89},
    {'key': 'near_complete', 'label': '90–<100%', 'min': 90, 'max': 99},
    {'key': 'complete', 'label': '100%', 'min': 100, 'max': 100},
    {'key': 'unreported', 'label': 'Not reported', 'min': None, 'max': None},
)


def get_monitoring_updates_report(
    user_id,
    fiscal_year=None,
    program_id=None,
    cluster_id=None,
    lgu_id=None,
    status=None,
    selected_project_ids=None,
    search=None,
):
    projects = _visible_projects(
        user_id=user_id,
        fiscal_year=fiscal_year,
        program_id=program_id,
        cluster_id=cluster_id,
        lgu_id=lgu_id,
        status=status,
        selected_project_ids=selected_project_ids,
        search=search,
    )
    project_ids = [project.id for project in projects]
    document_counts = _document_counts_by_project(project_ids)
    mprs_by_project = _latest_mprs_by_project(project_ids)
    non_infra_by_project = _non_infra_records_by_project(project_ids)
    milestones_by_project = _milestones_by_project(project_ids)
    completion_docs_by_project = _completion_docs_by_project(project_ids)
    pushes_by_project = _latest_drive_pushes_by_project(project_ids)
    project_rows = [
        _serialize_project_row(
            project,
            document_counts.get(project.id, _empty_document_counts()),
            mpr=mprs_by_project.get(project.id),
            non_infra_records=non_infra_by_project.get(project.id, []),
            milestone=milestones_by_project.get(project.id),
            completion_docs=completion_docs_by_project.get(project.id, []),
            latest_push=pushes_by_project.get(project.id),
        )
        for project in projects
    ]
    for row in project_rows:
        row.update(_project_health_payload(row))
    documentary_summary = _documentary_summary(document_counts)
    risk_rows = _risk_rows(project_rows)

    return {
        'scope': _scope_payload(user_id, fiscal_year, projects),
        'filters': {
            'fiscal_year': fiscal_year,
            'program_id': program_id,
            'cluster_id': cluster_id,
            'lgu_id': lgu_id,
            'status': status,
        },
        'analytics_summary': _analytics_summary(project_rows, documentary_summary, risk_rows),
        'progress_summary': _progress_summary(project_rows),
        'cluster_analytics': _cluster_analytics(project_rows),
        'program_analytics': _program_analytics(project_rows),
        'lgu_analytics': _lgu_analytics(project_rows),
        'risk_rows': risk_rows,
        'status_summary': _status_summary(project_rows),
        'documentary_summary': documentary_summary,
        'cluster_summary': _cluster_summary(project_rows),
        'program_years': _program_years(project_rows),
        'project_rows': project_rows,
    }


def _visible_projects(
    user_id,
    fiscal_year=None,
    program_id=None,
    cluster_id=None,
    lgu_id=None,
    status=None,
    selected_project_ids=None,
    search=None,
):
    query = (
        Project.query
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .options(
            joinedload(Project.lgu).joinedload(LguProfile.cluster),
            joinedload(Project.program),
            joinedload(Project.program_cycle),
        )
    )
    query = access_service.restrict_project_query(query, user_id)
    query = apply_project_fiscal_year(query, fiscal_year)

    if program_id is not None:
        query = query.filter(Project.program_id == program_id)
    if cluster_id is not None:
        access_service.ensure_cluster_access(cluster_id, user_id)
        query = query.filter(LguProfile.cluster_id == cluster_id)
    if lgu_id is not None:
        access_service.ensure_lgu_access(lgu_id, user_id)
        query = query.filter(Project.lgu_id == lgu_id)
    if status:
        normalized_status = normalize_project_status(status, default=status)
        query = query.filter(Project.overall_status == normalized_status)

    if selected_project_ids is not None:
        query = query.filter(Project.id.in_(selected_project_ids))
    projects = (
        query
        .order_by(Project.fiscal_year.desc(), Project.project_name.asc(), Project.id.asc())
        .all()
    )

    if search and search.strip():
        needle = search.strip().casefold()
        projects = [p for p in projects if any(needle in str(value or '').casefold() for value in (
            p.project_name, p.source_project_code, p.subaybayan_project_code,
            p.lgu.name if p.lgu else None, p.lgu.cluster.name if p.lgu and p.lgu.cluster else 'PGL / Unclustered',
            p.program.name if p.program else None, _remarks(p),
        ))]
    return projects


def _scope_payload(user_id, fiscal_year, projects):
    scope = access_service.get_access_scope(user_id)
    return {
        'role': scope['role'],
        'unrestricted': scope['unrestricted'],
        'cluster_ids': scope['cluster_ids'],
        'fiscal_year': fiscal_year,
        'total_projects': len(projects),
    }


def _latest_mprs_by_project(project_ids):
    if not project_ids:
        return {}
    subquery = (
        db.session.query(
            MonthlyProgressReport.project_id.label('project_id'),
            func.max(MonthlyProgressReport.reporting_period).label('max_period'),
        )
        .filter(MonthlyProgressReport.project_id.in_(project_ids))
        .group_by(MonthlyProgressReport.project_id)
        .subquery()
    )
    rows = (
        db.session.query(MonthlyProgressReport)
        .join(
            subquery,
            (MonthlyProgressReport.project_id == subquery.c.project_id)
            & (MonthlyProgressReport.reporting_period == subquery.c.max_period),
        )
        .all()
    )
    return {r.project_id: r for r in rows}


def _non_infra_records_by_project(project_ids):
    if not project_ids:
        return {}
    records = (
        NonInfraMonitoringRecord.query
        .filter(NonInfraMonitoringRecord.project_id.in_(project_ids))
        .all()
    )
    by_project = {}
    for r in records:
        if r.project_id not in by_project:
            by_project[r.project_id] = []
        by_project[r.project_id].append(r)
    return by_project


def _milestones_by_project(project_ids):
    if not project_ids:
        return {}
    milestones = CompletionMilestone.query.filter(CompletionMilestone.project_id.in_(project_ids)).all()
    return {m.project_id: m for m in milestones}


def _completion_docs_by_project(project_ids):
    if not project_ids:
        return {}
    docs = (
        CompletionDocumentRecord.query
        .filter(CompletionDocumentRecord.project_id.in_(project_ids))
        .options(joinedload(CompletionDocumentRecord.project_requirement))
        .all()
    )
    by_project = {}
    for d in docs:
        if d.project_id not in by_project:
            by_project[d.project_id] = []
        by_project[d.project_id].append(d)
    return by_project


def _latest_drive_pushes_by_project(project_ids):
    if not project_ids:
        return {}
    pushes = (
        GoogleDrivePush.query
        .filter(GoogleDrivePush.project_id.in_(project_ids))
        .order_by(GoogleDrivePush.created_at.desc(), GoogleDrivePush.id.desc())
        .all()
    )
    latest_by_proj = {}
    for p in pushes:
        if p.project_id not in latest_by_proj:
            latest_by_proj[p.project_id] = p
    return latest_by_proj


def _completion_document_counts(project, milestone, records):
    from app.services.completion_documents_service import DOCUMENT_TYPES, _effective_applicability
    by_type = {record.document_type: record for record in records}
    total = approved = pending = 0
    for document_type in DOCUMENT_TYPES:
        record = by_type.get(document_type)
        applicability = _effective_applicability(document_type, record, milestone, project=project)
        if applicability == 'not_applicable':
            continue
        total += 1
        req = record.project_requirement if record else None
        # Match the completion service's explicit legacy-compliant compatibility rule.
        if applicability == 'required' and req and (req.workflow_status == 'approved' or req.status == 'compliant'):
            approved += 1
        else:
            pending += 1
    return total, approved, pending

def _serialize_project_row(
    project,
    document_counts,
    mpr=None,
    non_infra_records=None,
    milestone=None,
    completion_docs=None,
    latest_push=None,
):
    lgu = project.lgu
    cluster = lgu.cluster if lgu else None
    program = project.program
    cycle = project.program_cycle
    effective_kind = resolve_effective_project_kind(project)

    if effective_kind == 'infrastructure':
        non_infra_spec_status = 'not_applicable'
        non_infra_spec_label = 'Not Applicable (Infra)'
        if _schedule_variance(mpr) is not None:
            var_val = _schedule_variance(mpr)
            tier = _determine_slippage_tier(var_val)
            tier_cfg = SLIPPAGE_TIER_CONFIG.get(tier, {})
            slippage_tier = tier
            slippage_tier_label = tier_cfg.get('label', tier)
            latest_variance = var_val
            latest_period = mpr.reporting_period
        else:
            slippage_tier = 'unreported'
            slippage_tier_label = SLIPPAGE_TIER_CONFIG['unreported']['label']
            latest_variance = None
            latest_period = mpr.reporting_period if mpr else None
    else:
        slippage_tier = 'not_applicable'
        slippage_tier_label = 'Not Applicable (Non-Infra)'
        latest_variance = None
        latest_period = None
        if non_infra_records:
            if any(r.specifications_met is False for r in non_infra_records):
                non_infra_spec_status = 'not_met'
                non_infra_spec_label = 'Specifications Not Met'
            elif all(r.specifications_met is True for r in non_infra_records):
                non_infra_spec_status = 'met'
                non_infra_spec_label = 'Specifications Met'
            else:
                non_infra_spec_status = 'pending'
                non_infra_spec_label = 'Pending Verification'
        else:
            non_infra_spec_status = 'unassessed'
            non_infra_spec_label = 'Unassessed'

    # Wave 2.3 & 2.3.1: Closeout stage & readiness determination
    phys_val = _decimal_to_float(project.physical_completion_pct)
    is_phys_complete = (phys_val >= 100.0)
    is_vault_ready = bool(milestone and milestone.is_vault_ready)
    is_final_approved = bool(milestone and milestone.final_approval_at is not None)

    is_punchlist_cleared = False
    is_punchlist_blocked = False
    is_punchlist_unassessed = is_phys_complete and effective_kind == 'infrastructure' and (not milestone or milestone.punchlist_items_total is None)
    if is_phys_complete:
        if effective_kind == 'infrastructure':
            if milestone and milestone.punchlist_items_total is not None and milestone.punchlist_items_total > 0:
                resolved = milestone.punchlist_items_resolved or 0
                if resolved < milestone.punchlist_items_total:
                    is_punchlist_blocked = True
                    is_punchlist_cleared = False
                else:
                    is_punchlist_cleared = True
            else:
                is_punchlist_cleared = True
        else:
            is_punchlist_cleared = True

    docs_total, docs_approved, docs_pending = _completion_document_counts(project, milestone, completion_docs or [])
    has_pending_doc = docs_pending > 0
    is_closeout_docs_ready = is_phys_complete and not has_pending_doc
    is_closeout_docs_pending = is_phys_complete and has_pending_doc
    if not is_phys_complete:
        closeout_stage = 'in_progress'
        closeout_stage_label = 'In Progress'
    elif is_punchlist_unassessed:
        closeout_stage = 'punchlist_unassessed'
        closeout_stage_label = 'Punchlist Not Assessed'
    elif is_punchlist_blocked:
        closeout_stage = 'punchlist_unresolved'
        closeout_stage_label = 'Punchlist Unresolved'
    elif has_pending_doc:
        closeout_stage = 'docs_pending'
        closeout_stage_label = 'Closeout Docs Pending'
    elif is_final_approved:
        closeout_stage = 'final_approved'
        closeout_stage_label = 'Closeout Approved'
    elif is_vault_ready:
        closeout_stage = 'vault_ready'
        closeout_stage_label = 'Vault Ready'
    else:
        closeout_stage = 'docs_ready'
        closeout_stage_label = 'Closeout Docs Ready'

    # Wave 2.3: Regional Handoff status
    if latest_push:
        handoff_status = latest_push.push_status
        handoff_status_label = latest_push.push_status.replace('_', ' ').title()
    else:
        handoff_status = 'no_handoff'
        handoff_status_label = 'No Transmission'

    return {
        'project_id': project.id,
        'project_name': project.project_name,
        'project_code': project.source_project_code or project.subaybayan_project_code,
        'program_id': project.program_id,
        'program_name': program.name if program else None,
        'program_code': program.code if program else None,
        'program_cycle_id': project.program_cycle_id,
        'program_cycle_name': cycle.name if cycle else None,
        'fiscal_year': project.fiscal_year,
        'lgu_id': project.lgu_id,
        'lgu_name': lgu.name if lgu else None,
        'municipality': lgu.municipality if lgu else None,
        'cluster_id': cluster.id if cluster else None,
        'cluster_name': cluster.name if cluster else 'PGL / Unclustered',
        'overall_status': project.overall_status,
        'overall_status_label': project_status_label(project.overall_status),
        'project_kind': project.project_kind or 'infrastructure',
        'effective_project_kind': effective_kind,
        'progress_metric': 'physical' if effective_kind == 'infrastructure' else ('delivery' if effective_kind in ('goods', 'vehicle') else 'disbursement'),
        'progress_value': float(project.physical_completion_pct) if project.physical_completion_pct is not None else None,
        'physical_completion_pct': float(project.physical_completion_pct) if project.physical_completion_pct is not None else None,
        'budget_amount': float(project.budget_amount) if project.budget_amount is not None else None,
        'remarks': _remarks(project),
        'current_phase': project.current_phase or 'pre_implementation',
        'current_phase_label': _project_phase_label(project.current_phase or 'pre_implementation'),
        'documentary_summary': document_counts,
        'document_total_count': document_counts['total'],
        'document_applicable_count': document_counts.get('applicable', document_counts['total']),
        'document_not_applicable_count': document_counts.get('not_applicable', 0),
        'document_open_count': document_counts['open'],
        'document_compliance_rate': document_counts['compliance_rate'],
        'as_of_date': _custom_field(project, 'as_of_date', 'source_as_of_date', 'report_as_of_date'),
        'latest_variance_pct': latest_variance,
        'latest_reporting_period': latest_period,
        'slippage_tier': slippage_tier,
        'slippage_tier_label': slippage_tier_label,
        'non_infra_spec_status': non_infra_spec_status,
        'non_infra_spec_label': non_infra_spec_label,
        'closeout_stage': closeout_stage,
        'closeout_stage_label': closeout_stage_label,
        'is_physically_complete': is_phys_complete,
        'is_punchlist_cleared': is_punchlist_cleared and not is_punchlist_unassessed,
        'is_punchlist_unassessed': is_punchlist_unassessed,
        'is_closeout_docs_ready': is_closeout_docs_ready,
        'is_closeout_docs_pending': is_closeout_docs_pending,
        'is_vault_ready': is_vault_ready,
        'is_final_approved': is_final_approved,
        'handoff_status': handoff_status,
        'handoff_status_label': handoff_status_label,
    }


def _status_summary(rows):
    total = len(rows)
    counts = {status: 0 for status in CANONICAL_PROJECT_STATUSES}
    for row in rows:
        if row['overall_status'] in counts:
            counts[row['overall_status']] += 1
    return {
        'total': total,
        'items': [
            {
                'key': status,
                'label': project_status_label(status),
                'count': counts[status],
                'percentage': _percentage(counts[status], total),
            }
            for status in CANONICAL_PROJECT_STATUSES
        ],
    }


def _document_counts_by_project(project_ids):
    counts_by_project = {
        project_id: _empty_document_counts()
        for project_id in project_ids
    }
    if project_ids:
        rows = (
            db.session.query(
                ProjectRequirement.project_id,
                ProjectRequirement.status,
                ProjectRequirement.applicability,
                func.count(ProjectRequirement.id),
            )
            .filter(ProjectRequirement.project_id.in_(project_ids), ProjectRequirement.is_active.is_(True))
            .group_by(ProjectRequirement.project_id, ProjectRequirement.status, ProjectRequirement.applicability)
            .all()
        )
        for project_id, status, applicability, count in rows:
            project_counts = counts_by_project.get(project_id)
            if project_counts is None:
                continue
            project_counts['total'] += count
            if (applicability or 'applicable') == 'not_applicable':
                project_counts['not_applicable'] += count
            else:
                project_counts['applicable'] += count
                if status in project_counts:
                    project_counts[status] += count

    for counts in counts_by_project.values():
        _finalize_document_counts(counts)
    return counts_by_project


def _empty_document_counts():
    return {
        'total': 0,
        'applicable': 0,
        'not_applicable': 0,
        **{status: 0 for status in REQUIREMENT_STATUSES},
        'open': 0,
        'compliance_rate': 0.0,
    }


def _finalize_document_counts(counts):
    counts['open'] = counts['pending'] + counts['under_review'] + counts['non_compliant']
    applicable = counts.get('applicable', counts['total'])
    if applicable > 0:
        counts['compliance_rate'] = _percentage(counts['compliant'], applicable)
    else:
        counts['compliance_rate'] = 0.0


def _documentary_summary(counts_by_project):
    counts = _empty_document_counts()
    for project_counts in counts_by_project.values():
        counts['total'] += project_counts['total']
        counts['applicable'] += project_counts.get('applicable', 0)
        counts['not_applicable'] += project_counts.get('not_applicable', 0)
        for status in REQUIREMENT_STATUSES:
            counts[status] += project_counts[status]
    _finalize_document_counts(counts)

    return {
        'total': counts['total'],
        'applicable': counts['applicable'],
        'not_applicable': counts['not_applicable'],
        **{status: counts[status] for status in REQUIREMENT_STATUSES},
        'open': counts['open'],
        'compliance_rate': counts['compliance_rate'],
    }


def _cluster_summary(rows):
    clusters = OrderedDict()
    for row in rows:
        key = row['cluster_id'] if row['cluster_id'] is not None else 'unclustered'
        if key not in clusters:
            clusters[key] = {
                'cluster_id': row['cluster_id'],
                'cluster_name': row['cluster_name'],
                'total': 0,
                'statuses': {status: 0 for status in CANONICAL_PROJECT_STATUSES},
                'open_document_count': 0,
                'total_allocation': 0.0,
                'allocation_recorded_count': 0,
                'allocation_missing_count': 0,
            }
        item = clusters[key]
        item['total'] += 1
        if row['overall_status'] in item['statuses']:
            item['statuses'][row['overall_status']] += 1
        item['open_document_count'] += row['document_open_count']
        if row.get('budget_amount') is not None:
            item['total_allocation'] += float(row['budget_amount'])
            item['allocation_recorded_count'] += 1
        else:
            item['allocation_missing_count'] += 1

    result = []
    for item in clusters.values():
        item = dict(item)
        item['allocation_complete'] = (item['allocation_missing_count'] == 0 and item['total'] > 0)
        if item['allocation_recorded_count'] == 0:
            item['total_allocation'] = None
        result.append(item)
    return result


def _program_years(rows):
    groups = OrderedDict()
    for row in rows:
        key = (row['program_id'], row['fiscal_year'])
        if key not in groups:
            groups[key] = {
                'program_id': row['program_id'],
                'program_name': row['program_name'],
                'program_code': row['program_code'],
                'fiscal_year': row['fiscal_year'],
                'total': 0,
                'statuses': {status: 0 for status in CANONICAL_PROJECT_STATUSES},
                'total_allocation': 0.0,
                'allocation_recorded_count': 0,
                'allocation_missing_count': 0,
                'clusters': OrderedDict(),
            }

        group = groups[key]
        group['total'] += 1
        if row['overall_status'] in group['statuses']:
            group['statuses'][row['overall_status']] += 1
        if row.get('budget_amount') is not None:
            group['total_allocation'] += float(row['budget_amount'])
            group['allocation_recorded_count'] += 1
        else:
            group['allocation_missing_count'] += 1

        cluster_key = row['cluster_id'] if row['cluster_id'] is not None else 'unclustered'
        if cluster_key not in group['clusters']:
            group['clusters'][cluster_key] = {
                'cluster_id': row['cluster_id'],
                'cluster_name': row['cluster_name'],
                'total': 0,
                'statuses': {status: 0 for status in CANONICAL_PROJECT_STATUSES},
                'total_allocation': 0.0,
                'allocation_recorded_count': 0,
                'allocation_missing_count': 0,
            }
        cluster = group['clusters'][cluster_key]
        cluster['total'] += 1
        if row['overall_status'] in cluster['statuses']:
            cluster['statuses'][row['overall_status']] += 1
        if row.get('budget_amount') is not None:
            cluster['total_allocation'] += float(row['budget_amount'])
            cluster['allocation_recorded_count'] += 1
        else:
            cluster['allocation_missing_count'] += 1

    result = []
    for group in groups.values():
        group = dict(group)
        group['allocation_complete'] = (group['allocation_missing_count'] == 0 and group['total'] > 0)
        if group['allocation_recorded_count'] == 0:
            group['total_allocation'] = None
        clusters_list = []
        for c in group['clusters'].values():
            c = dict(c)
            c['allocation_complete'] = (c['allocation_missing_count'] == 0 and c['total'] > 0)
            if c['allocation_recorded_count'] == 0:
                c['total_allocation'] = None
            clusters_list.append(c)
        group['clusters'] = clusters_list
        result.append(group)
    return result


def _analytics_summary(rows, documentary_summary, risk_rows):
    total = len(rows)
    health_counts = _health_label_counts(rows)
    recorded_allocations = [float(row['budget_amount']) for row in rows if row.get('budget_amount') is not None]
    allocation_recorded_count = len(recorded_allocations)
    allocation_missing_count = total - allocation_recorded_count
    allocation_complete = (allocation_missing_count == 0 and total > 0)
    total_allocation = sum(recorded_allocations) if allocation_recorded_count > 0 else (0.0 if total == 0 else None)

    return {
        'total_projects': total,
        'document_total_count': documentary_summary['total'],
        'document_applicable_count': documentary_summary.get('applicable', documentary_summary['total']),
        'document_not_applicable_count': documentary_summary.get('not_applicable', 0),
        'document_compliance_rate': documentary_summary['compliance_rate'],
        'open_document_count': documentary_summary['open'],
        'total_allocation': total_allocation,
        'recorded_total_allocation': sum(recorded_allocations),
        'allocation_recorded_count': allocation_recorded_count,
        'allocation_missing_count': allocation_missing_count,
        'allocation_complete': allocation_complete,
        'average_progress': _average(row['physical_completion_pct'] for row in rows),
        'average_health_score': _average(row['health_score'] for row in rows),
        'risk_project_count': len(risk_rows),
        'high_risk_project_count': sum(
            1
            for row in rows
            if row['health_label'] in ('At Risk', 'Critical')
        ),
        'zero_progress_count': sum(
            1
            for row in rows
            if row['physical_completion_pct'] is not None and _bounded_progress(row['physical_completion_pct']) == 0
        ),
        'non_compliant_project_count': sum(
            1
            for row in rows
            if document_count(row, 'non_compliant') > 0
        ),
        'completed_with_open_docs_count': sum(
            1
            for row in rows
            if row['overall_status'] == 'completed' and row['document_open_count'] > 0
        ),
        'low_progress_with_open_docs_count': sum(
            1
            for row in rows
            if _is_low_progress_with_open_documents(row)
        ),
        'healthy_project_count': health_counts['Healthy'],
        'watch_project_count': 0,
        'at_risk_project_count': health_counts['At Risk'],
        'critical_project_count': health_counts['Critical'],
    }



def _progress_summary(rows):
    total = len(rows)
    bands = [
        {
            'key': band['key'],
            'label': band['label'],
            'count': 0,
        }
        for band in PROGRESS_BANDS
    ]
    band_lookup = {band['key']: band for band in bands}

    for row in rows:
        progress = _bounded_progress(row['physical_completion_pct'])
        band_key = 'unreported' if row['physical_completion_pct'] is None else ('zero' if progress == 0 else 'early' if progress < 50 else
                    'mid' if progress < 90 else 'near_complete' if progress < 100 else 'complete')
        band_lookup[band_key]['count'] += 1

    return {
        'total': total,
        'average': _average(row['physical_completion_pct'] for row in rows),
        'bands': [
            {
                **band,
                'percentage': _percentage(band['count'], total),
            }
            for band in bands
        ],
    }


def _cluster_analytics(rows):
    groups = OrderedDict()
    for row in rows:
        key = row['cluster_id'] if row['cluster_id'] is not None else 'unclustered'
        if key not in groups:
            groups[key] = _new_analytics_group({
                'cluster_id': row['cluster_id'],
                'cluster_name': row['cluster_name'],
            })
        _add_row_to_analytics_group(groups[key], row)

    return _finalized_group_rows(
        groups,
        lambda item: (item['health_score'], -item['open_document_count'], item['cluster_name'] or ''),
    )


def _program_analytics(rows):
    groups = OrderedDict()
    for row in rows:
        key = (row['program_id'], row['fiscal_year'])
        if key not in groups:
            groups[key] = _new_analytics_group({
                'program_id': row['program_id'],
                'program_name': row['program_name'],
                'program_code': row['program_code'],
                'fiscal_year': row['fiscal_year'],
            })
        _add_row_to_analytics_group(groups[key], row)

    return _finalized_group_rows(
        groups,
        lambda item: (item['health_score'], -item['open_document_count'], item['program_name'] or ''),
    )


def _lgu_analytics(rows):
    groups = OrderedDict()
    for row in rows:
        key = row['lgu_id'] if row['lgu_id'] is not None else 'unassigned'
        if key not in groups:
            groups[key] = _new_analytics_group({
                'lgu_id': row['lgu_id'],
                'lgu_name': row['lgu_name'],
                'municipality': row['municipality'],
                'cluster_id': row['cluster_id'],
                'cluster_name': row['cluster_name'],
            })
        _add_row_to_analytics_group(groups[key], row)

    return _finalized_group_rows(
        groups,
        lambda item: (
            -item['open_document_count'],
            -item['risk_project_count'],
            -item['project_count'],
            item['lgu_name'] or '',
        ),
    )


def _new_analytics_group(base):
    return {
        **base,
        'project_count': 0,
        'statuses': {status: 0 for status in CANONICAL_PROJECT_STATUSES},
        'total_document_count': 0,
        'applicable_document_count': 0,
        'not_applicable_document_count': 0,
        'open_document_count': 0,
        'pending_document_count': 0,
        'under_review_document_count': 0,
        'non_compliant_document_count': 0,
        'compliant_document_count': 0,
        'waived_document_count': 0,
        'risk_project_count': 0,
        'high_risk_project_count': 0,
        'zero_progress_count': 0,
        '_progress_total': 0,
        '_progress_reported': 0,
        '_health_score_total': 0,
    }


def _add_row_to_analytics_group(group, row):
    group['project_count'] += 1
    if row['overall_status'] in group['statuses']:
        group['statuses'][row['overall_status']] += 1

    if row['physical_completion_pct'] is not None:
        group['_progress_total'] += _bounded_progress(row['physical_completion_pct'])
        group['_progress_reported'] += 1
    group['_health_score_total'] += row['health_score']
    group['total_document_count'] += document_count(row, 'total')
    group['applicable_document_count'] += document_count(row, 'applicable')
    group['not_applicable_document_count'] += document_count(row, 'not_applicable')
    group['open_document_count'] += row['document_open_count']
    group['pending_document_count'] += document_count(row, 'pending')
    group['under_review_document_count'] += document_count(row, 'under_review')
    group['non_compliant_document_count'] += document_count(row, 'non_compliant')
    group['compliant_document_count'] += document_count(row, 'compliant')
    group['waived_document_count'] += document_count(row, 'waived')

    if row['risk_reasons']:
        group['risk_project_count'] += 1
    if row['health_label'] in ('At Risk', 'Critical'):
        group['high_risk_project_count'] += 1
    if row['physical_completion_pct'] is not None and _bounded_progress(row['physical_completion_pct']) == 0:
        group['zero_progress_count'] += 1


def _finalized_group_rows(groups, sort_key):
    rows = []
    for group in groups.values():
        group = dict(group)
        project_count = group['project_count']
        progress_total = group.pop('_progress_total')
        progress_reported = group.pop('_progress_reported')
        health_score_total = group.pop('_health_score_total')
        group['average_progress'] = round(progress_total / progress_reported, 1) if progress_reported else None
        group['health_score'] = round(health_score_total / project_count, 1) if project_count else 0
        group['health_label'] = _health_label(group['health_score'])
        group['health_tone'] = _health_tone(group['health_score'])
        applicable_docs = group.get('applicable_document_count', group['total_document_count'])
        group['document_compliance_rate'] = _percentage(
            group['compliant_document_count'],
            applicable_docs,
        )
        rows.append(group)
    return sorted(rows, key=sort_key)


def _project_health_payload(row):
    health_score = _health_score(row)
    risk_reasons = _risk_reasons(row)
    return {
        'health_score': health_score,
        'health_label': _health_label(health_score),
        'health_tone': _health_tone(health_score),
        'risk_score': round(100 - health_score, 1),
        'risk_reasons': risk_reasons,
        'risk_reason_labels': [reason['label'] for reason in risk_reasons],
    }


def _health_score(row):
    counts = row['documentary_summary']
    applicable_documents = document_count(row, 'applicable')
    denom = applicable_documents if 'applicable' in counts else document_count(row, 'total')
    deductions = 0

    if denom > 0:
        deductions += min((document_count(row, 'open') / denom) * 35, 35)
        deductions += min((document_count(row, 'non_compliant') / denom) * 25, 25)

    progress = _bounded_progress(row['physical_completion_pct'])
    status = row['overall_status']
    if progress == 0 and status not in ('completed', 'cancelled'):
        deductions += 20
    if _is_low_progress_with_open_documents(row):
        deductions += 10
    if status == 'completed' and counts['open'] > 0:
        deductions += 10

    return round(max(0, min(100, 100 - deductions)), 1)


def _risk_reasons(row):
    reasons = []
    progress = _bounded_progress(row['physical_completion_pct'])
    status = row['overall_status']

    if document_count(row, 'non_compliant') > 0:
        reasons.append(_risk_reason('non_compliant_documents', 'Non-compliant documents', 'danger'))
    if document_count(row, 'pending') > 0:
        reasons.append(_risk_reason('pending_documents', 'Pending documents', 'warning'))
    if document_count(row, 'under_review') > 0:
        reasons.append(_risk_reason('documents_under_review', 'Documents under review', 'info'))
    if row['physical_completion_pct'] is None:
        reasons.append(_risk_reason('progress_unreported', 'Progress not reported', 'warning'))
    elif progress == 0 and status not in ('completed', 'cancelled'):
        reasons.append(_risk_reason('no_physical_progress', 'No physical progress', 'danger'))
    if _is_low_progress_with_open_documents(row):
        reasons.append(_risk_reason('low_progress_open_documents', 'Low progress with open documents', 'warning'))
    if status == 'completed' and row['document_open_count'] > 0:
        reasons.append(_risk_reason('completed_open_documents', 'Completed with open documents', 'warning'))

    return reasons


def _risk_reason(key, label, tone):
    return {
        'key': key,
        'label': label,
        'tone': tone,
    }


def _risk_rows(rows):
    risk_rows = [
        dict(row)
        for row in rows
        if row['risk_reasons']
    ]
    return sorted(
        risk_rows,
        key=lambda row: (
            row['health_score'],
            -len(row['risk_reasons']),
            -row['document_open_count'],
            row['project_name'] or '',
        ),
    )


def _health_label(score):
    if score >= 80:
        return 'Healthy'
    if score >= 40:
        return 'At Risk'
    return 'Critical'


def _health_tone(score):
    if score >= 80:
        return 'success'
    if score >= 40:
        return 'warning'
    return 'danger'


def _health_label_counts(rows):
    counts = {
        'Healthy': 0,
        'At Risk': 0,
        'Critical': 0,
    }
    for row in rows:
        label = row.get('health_label')
        if label in counts:
            counts[label] += 1
    return counts


def _is_low_progress_with_open_documents(row):
    return (
        row['overall_status'] == 'ongoing'
        and row['physical_completion_pct'] is not None
        and _bounded_progress(row['physical_completion_pct']) < 50
        and row['document_open_count'] > 0
    )


def document_count(row, key):
    return int(row.get('documentary_summary', {}).get(key, 0) or 0)


def _remarks(project):
    return _custom_field(project, 'reporting_remarks', 'remarks', 'monitoring_remarks') or project.notes


def _custom_field(project, *keys):
    custom_fields = project.custom_fields or {}
    if not isinstance(custom_fields, dict):
        return None
    for key in keys:
        value = custom_fields.get(key)
        if value not in (None, ''):
            return _serialize_scalar(value)
    return None


def _utc_iso(value):
    if value is None:
        return None
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()


def _serialize_scalar(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip() if isinstance(value, str) else value


def _decimal_to_float(value):
    if value in (None, ''):
        return 0
    return float(value)


def _bounded_progress(value):
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, numeric))


def _average(values):
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 1)


def _percentage(count, total):
    if not total:
        return 0
    return round((count / total) * 100, 1)


def get_deep_dive_analytics(
    user_id,
    fiscal_year=None,
    program_id=None,
    cluster_id=None,
    lgu_id=None,
    status=None,
    selected_project_ids=None,
    search=None,
):
    projects = _visible_projects(
        user_id=user_id,
        fiscal_year=fiscal_year,
        program_id=program_id,
        cluster_id=cluster_id,
        lgu_id=lgu_id,
        status=status,
        selected_project_ids=selected_project_ids,
        search=search,
    )
    project_ids = [project.id for project in projects]
    document_counts = _document_counts_by_project(project_ids)
    mprs_by_project = _latest_mprs_by_project(project_ids)
    non_infra_by_project = _non_infra_records_by_project(project_ids)
    milestones_by_project = _milestones_by_project(project_ids)
    completion_docs_by_project = _completion_docs_by_project(project_ids)
    pushes_by_project = _latest_drive_pushes_by_project(project_ids)
    project_rows = [
        _serialize_project_row(
            project,
            document_counts.get(project.id, _empty_document_counts()),
            mpr=mprs_by_project.get(project.id),
            non_infra_records=non_infra_by_project.get(project.id, []),
            milestone=milestones_by_project.get(project.id),
            completion_docs=completion_docs_by_project.get(project.id, []),
            latest_push=pushes_by_project.get(project.id),
        )
        for project in projects
    ]
    for row in project_rows:
        row.update(_project_health_payload(row))

    return {
        'scope': _scope_payload(user_id, fiscal_year, projects),
        'filters': {
            'fiscal_year': fiscal_year,
            'program_id': program_id,
            'cluster_id': cluster_id,
            'lgu_id': lgu_id,
            'status': status,
        },
        'lgu_backlog': _lgu_backlog_aggregation(project_rows),
        'compliance_by_program': _compliance_by_program_aggregation(project_rows),
        'workflow_pipeline': _workflow_pipeline_aggregation(project_ids),
        'deficiency_root_causes': _deficiency_patterns_aggregation(project_ids),
        'sla_urgency': _sla_urgency_aggregation(project_ids),
        'project_health': _project_health_summary(project_rows),
        # Wave 2.1 Analytics
        'workflow_activity': _monthly_workflow_action_volume(project_ids),
        'return_patterns': _problematic_requirements_aggregation(project_ids),
        'overdue_by_lgu': _overdue_deadlines_by_lgu_aggregation(project_ids),
        'phase_distribution': _project_phase_distribution_aggregation(project_ids),
        # Wave 2.2 Analytics
        'slippage_distribution': _infrastructure_slippage_aggregation(projects, project_ids),
        'qaar_defects': _qaar_defect_severity_aggregation(project_ids),
        'non_infra_delivery': _non_infra_delivery_aggregation(projects, project_ids),
        # Wave 2.3 & 2.3.1 Analytics
        'closeout_readiness': _closeout_readiness_aggregation(
            projects,
            project_ids,
            milestones=milestones_by_project,
            completion_docs=completion_docs_by_project,
        ),
        'regional_handoff': _regional_handoff_aggregation(projects, project_ids),
    }


def _lgu_backlog_aggregation(project_rows):
    lgus = _lgu_analytics(project_rows)
    results = []
    for lgu in lgus:
        results.append({
            'lgu_id': lgu['lgu_id'],
            'lgu_name': lgu['lgu_name'] or 'Unassigned',
            'cluster_id': lgu['cluster_id'],
            'cluster_name': lgu['cluster_name'] or 'Unassigned',
            'project_count': lgu['project_count'],
            'backlog_count': lgu['open_document_count'],
            'pending_count': lgu['pending_document_count'],
            'under_review_count': lgu['under_review_document_count'],
            'non_compliant_count': lgu['non_compliant_document_count'],
            'compliant_count': lgu['compliant_document_count'],
            'waived_count': lgu['waived_document_count'],
            'not_applicable_count': lgu.get('not_applicable_document_count', 0),
            'applicable_requirements': lgu.get('applicable_document_count', lgu['total_document_count']),
            'total_requirements': lgu['total_document_count'],
            'compliance_rate': lgu['document_compliance_rate'],
        })
    return results


def _compliance_by_program_aggregation(project_rows):
    programs = OrderedDict()
    for row in project_rows:
        pid = row['program_id']
        if pid not in programs:
            programs[pid] = {
                'program_id': pid,
                'program_name': row['program_name'] or 'Unknown Program',
                'program_code': row['program_code'] or '',
                'project_count': 0,
                'compliant': 0,
                'non_compliant': 0,
                'under_review': 0,
                'pending': 0,
                'waived': 0,
                'not_applicable': 0,
                'applicable': 0,
                'total': 0,
            }
        p = programs[pid]
        p['project_count'] += 1
        p['compliant'] += document_count(row, 'compliant')
        p['non_compliant'] += document_count(row, 'non_compliant')
        p['under_review'] += document_count(row, 'under_review')
        p['pending'] += document_count(row, 'pending')
        p['waived'] += document_count(row, 'waived')
        p['not_applicable'] += document_count(row, 'not_applicable')
        p['applicable'] += document_count(row, 'applicable')
        p['total'] += document_count(row, 'total')

    results = []
    for p in programs.values():
        p['compliance_rate'] = _percentage(p['compliant'], p['applicable'])
        results.append(p)
    return sorted(results, key=lambda x: -x['total'])


def _workflow_state_label(state):
    labels = {
        'draft': 'Draft / Initial',
        'submitted': 'Submitted',
        'under_verification': 'Under Verification',
        'staff_approved': 'Staff Approved',
        'pending_provincial_approval': 'Pending Provincial Approval',
        'approved': 'Approved',
        'returned_for_revision': 'Returned for Revision',
        'resubmitted': 'Resubmitted',
    }
    return labels.get(state, state.replace('_', ' ').title())


def _workflow_pipeline_aggregation(project_ids):
    if not project_ids:
        return {
            'total': 0,
            'applicable_total': 0,
            'not_applicable_count': 0,
            'stages': [
                {'stage': state, 'label': _workflow_state_label(state), 'count': 0, 'percentage': 0, 'items': []}
                for state in WORKFLOW_STATES
            ],
            'approved_count': 0,
            'returned_count': 0,
            'in_progress_count': 0,
            'items': [],
        }

    rows = (
        db.session.query(
            ProjectRequirement.workflow_status,
            ProjectRequirement.applicability,
            func.count(ProjectRequirement.id),
        )
        .filter(ProjectRequirement.project_id.in_(project_ids), ProjectRequirement.is_active.is_(True))
        .group_by(ProjectRequirement.workflow_status, ProjectRequirement.applicability)
        .all()
    )
    raw_counts = {state: 0 for state in WORKFLOW_STATES}
    total = 0
    applicable_total = 0
    not_applicable_count = 0
    for wf_status, applicability, count in rows:
        total += count
        if (applicability or 'applicable') == 'not_applicable':
            not_applicable_count += count
        else:
            applicable_total += count
            if wf_status in raw_counts:
                raw_counts[wf_status] += count
            else:
                raw_counts['draft'] += count

    req_rows = (
        db.session.query(
            ProjectRequirement.id,
            ProjectRequirement.requirement_name,
            ProjectRequirement.status.label('compliance_status'),
            ProjectRequirement.workflow_status,
            ProjectRequirement.workflow_return_reason,
            ProjectRequirement.workflow_submitted_at,
            ProjectRequirement.updated_at,
            ProjectRequirement.applicability,
            ProjectRequirement.waived_reason,
            ProjectRequirement.applicability_reason,
            Project.id.label('project_id'),
            Project.project_name.label('project_name'),
            Project.program_id.label('program_id'),
            Program.name.label('program_name'),
            Program.code.label('program_code'),
            LguProfile.name.label('lgu_name'),
            LguProfile.cluster_id.label('cluster_id'),
        )
        .join(Project, ProjectRequirement.project_id == Project.id)
        .outerjoin(Program, Project.program_id == Program.id)
        .outerjoin(LguProfile, Project.lgu_id == LguProfile.id)
        .filter(ProjectRequirement.project_id.in_(project_ids), ProjectRequirement.is_active.is_(True))
        .order_by(ProjectRequirement.updated_at.desc())
        .all()
    )

    stage_items = {state: [] for state in WORKFLOW_STATES}
    all_items = []
    for r in req_rows:
        if (r.applicability or 'applicable') == 'not_applicable':
            continue
        wf_st = r.workflow_status if r.workflow_status in stage_items else 'draft'
        waiver_reason = r.waived_reason or (r.applicability_reason if r.applicability == 'waived' else None)
        item = {
            'id': r.id,
            'requirement_name': r.requirement_name,
            'compliance_status': r.compliance_status,
            'workflow_status': r.workflow_status or 'draft',
            'workflow_return_reason': r.workflow_return_reason,
            'waived_reason': waiver_reason,
            'waiver_or_return_reason': (
                f"Waived: {waiver_reason}" if (waiver_reason and (r.compliance_status == 'waived' or r.applicability == 'waived'))
                else (r.workflow_return_reason or (f"Waived: {waiver_reason}" if waiver_reason else None))
            ),
            'workflow_submitted_at': _utc_iso(r.workflow_submitted_at) if r.workflow_submitted_at else None,
            'updated_at': _utc_iso(r.updated_at) if r.updated_at else None,
            'project_id': r.project_id,
            'project_name': r.project_name,
            'program_id': r.program_id,
            'program_name': r.program_name or 'Unknown Program',
            'program_code': r.program_code or '',
            'lgu_name': r.lgu_name or 'Unassigned',
            'cluster_id': r.cluster_id,
        }
        stage_items[wf_st].append(item)
        all_items.append(item)

    stages = []
    for state in WORKFLOW_STATES:
        stages.append({
            'stage': state,
            'label': _workflow_state_label(state),
            'count': raw_counts[state],
            'percentage': _percentage(raw_counts[state], applicable_total),
            'items': stage_items[state],
        })

    approved_count = raw_counts['approved']
    returned_count = raw_counts['returned_for_revision']
    in_progress_count = max(0, applicable_total - approved_count)

    return {
        'total': total,
        'applicable_total': applicable_total,
        'not_applicable_count': not_applicable_count,
        'stages': stages,
        'approved_count': approved_count,
        'returned_count': returned_count,
        'in_progress_count': in_progress_count,
        'items': all_items,
    }


def _deficiency_category_label(category):
    labels = {
        'missing_attachment': 'Missing Attachment',
        'missing_signature_notarization': 'Missing Signature / Notarization',
        'cross_document_inconsistency': 'Cross-Document Inconsistency',
        'costing_dupa_defect': 'Costing / DUPA Defect',
        'missing_statutory_clearance': 'Missing Statutory Clearance',
        'program_specific_non_conformity': 'Program-Specific Non-Conformity',
        'financial_reconciliation_defect': 'Financial Reconciliation Defect',
        'scan_quality_defect': 'Scan Quality Defect',
        'other_documented_defect': 'Other Documented Defect',
    }
    return labels.get(category, category.replace('_', ' ').title())


def _deficiency_patterns_aggregation(project_ids):
    if not project_ids:
        return []

    rows = (
        db.session.query(
            RequirementDeficiency.category,
            RequirementDeficiency.resolution_state,
            func.count(RequirementDeficiency.id)
        )
        .join(ProjectRequirement, RequirementDeficiency.project_requirement_id == ProjectRequirement.id)
        .filter(ProjectRequirement.project_id.in_(project_ids))
        .group_by(RequirementDeficiency.category, RequirementDeficiency.resolution_state)
        .all()
    )

    category_map = OrderedDict()
    for cat in DEFICIENCY_CATEGORIES:
        category_map[cat] = {
            'category': cat,
            'label': _deficiency_category_label(cat),
            'total': 0,
            'open': 0,
            'resolved': 0,
            'waived': 0,
            'items': [],
        }

    for cat, res_state, count in rows:
        if cat not in category_map:
            category_map[cat] = {
                'category': cat,
                'label': _deficiency_category_label(cat),
                'total': 0,
                'open': 0,
                'resolved': 0,
                'waived': 0,
                'items': [],
            }
        category_map[cat]['total'] += count
        if res_state in ('open', 'resolved', 'waived'):
            category_map[cat][res_state] += count

    items = (
        db.session.query(
            RequirementDeficiency.id,
            RequirementDeficiency.category,
            RequirementDeficiency.finding_observation,
            RequirementDeficiency.corrective_instruction,
            RequirementDeficiency.resolution_state,
            RequirementDeficiency.resolution_notes,
            RequirementDeficiency.created_at,
            RequirementDeficiency.resolved_at,
            ProjectRequirement.id.label('project_requirement_id'),
            ProjectRequirement.requirement_name,
            Project.id.label('project_id'),
            Project.project_name.label('project_name'),
            LguProfile.name.label('lgu_name'),
        )
        .join(ProjectRequirement, RequirementDeficiency.project_requirement_id == ProjectRequirement.id)
        .join(Project, ProjectRequirement.project_id == Project.id)
        .outerjoin(LguProfile, Project.lgu_id == LguProfile.id)
        .filter(ProjectRequirement.project_id.in_(project_ids))
        .order_by(RequirementDeficiency.created_at.desc())
        .all()
    )

    for item in items:
        cat = item.category
        if cat in category_map:
            category_map[cat]['items'].append({
                'id': item.id,
                'project_id': item.project_id,
                'project_name': item.project_name,
                'lgu_name': item.lgu_name or 'Unassigned',
                'project_requirement_id': item.project_requirement_id,
                'requirement_name': item.requirement_name,
                'finding_observation': item.finding_observation,
                'corrective_instruction': item.corrective_instruction,
                'resolution_state': item.resolution_state,
                'resolution_notes': item.resolution_notes,
                'created_at': _utc_iso(item.created_at) if item.created_at else None,
                'resolved_at': _utc_iso(item.resolved_at) if item.resolved_at else None,
            })

    results = list(category_map.values())
    return sorted(results, key=lambda x: -x['total'])


def _sla_urgency_aggregation(project_ids):
    if not project_ids:
        return {
            'total_active': 0,
            'buckets': [
                {'key': 'overdue', 'label': 'Overdue', 'count': 0, 'percentage': 0, 'tone': 'danger', 'filter_param': 'overdue'},
                {'key': 'due_today', 'label': 'Due Today', 'count': 0, 'percentage': 0, 'tone': 'amber', 'filter_param': 'due_today'},
                {'key': 'due_in_3', 'label': 'Due in 1-3 Working Days', 'count': 0, 'percentage': 0, 'tone': 'warning', 'filter_param': 'report_due_3'},
                {'key': 'due_in_7', 'label': 'Due in 4-7 Working Days', 'count': 0, 'percentage': 0, 'tone': 'info', 'filter_param': 'report_due_7'},
                {'key': 'future', 'label': 'Future (>7 Working Days)', 'count': 0, 'percentage': 0, 'tone': 'neutral', 'filter_param': 'report_future'},
            ],
        }

    now_utc = datetime.now(timezone.utc)
    now_db = now_utc.replace(tzinfo=None)
    end_of_today_db = now_utc.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=None)

    day_3_aware = working_day_service.add_working_days(now_utc, 3, is_formal_deadline=False)
    day_7_aware = working_day_service.add_working_days(now_utc, 7, is_formal_deadline=False)
    day_3_db = day_3_aware.astimezone(timezone.utc).replace(tzinfo=None) if day_3_aware.tzinfo else day_3_aware
    day_7_db = day_7_aware.astimezone(timezone.utc).replace(tzinfo=None) if day_7_aware.tzinfo else day_7_aware

    query = SlaDeadline.query.filter(
        SlaDeadline.project_id.in_(project_ids),
        SlaDeadline.is_resolved == False,
    )
    query = filter_active_compliance_deadlines(query)
    active_deadlines = query.all()

    counts = {
        'overdue': 0,
        'due_today': 0,
        'due_in_3': 0,
        'due_in_7': 0,
        'future': 0,
    }

    for dl in active_deadlines:
        dt = dl.deadline_date
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

        if dt < now_db:
            counts['overdue'] += 1
        elif dt <= end_of_today_db:
            counts['due_today'] += 1
        elif dt <= day_3_db:
            counts['due_in_3'] += 1
        elif dt <= day_7_db:
            counts['due_in_7'] += 1
        else:
            counts['future'] += 1

    total_active = len(active_deadlines)

    buckets = [
        {'key': 'overdue', 'label': 'Overdue', 'count': counts['overdue'], 'percentage': _percentage(counts['overdue'], total_active), 'tone': 'danger', 'filter_param': 'overdue'},
        {'key': 'due_today', 'label': 'Due Today', 'count': counts['due_today'], 'percentage': _percentage(counts['due_today'], total_active), 'tone': 'amber', 'filter_param': 'due_today'},
        {'key': 'due_in_3', 'label': 'Due in 1-3 Working Days', 'count': counts['due_in_3'], 'percentage': _percentage(counts['due_in_3'], total_active), 'tone': 'warning', 'filter_param': 'report_due_3'},
        {'key': 'due_in_7', 'label': 'Due in 4-7 Working Days', 'count': counts['due_in_7'], 'percentage': _percentage(counts['due_in_7'], total_active), 'tone': 'info', 'filter_param': 'report_due_7'},
        {'key': 'future', 'label': 'Future (>7 Working Days)', 'count': counts['future'], 'percentage': _percentage(counts['future'], total_active), 'tone': 'neutral', 'filter_param': 'report_future'},
    ]

    return {
        'total_active': total_active,
        'buckets': buckets,
    }


def _project_health_summary(project_rows):
    total = len(project_rows)
    if not total:
        return {
            'total_projects': 0,
            'average_score': None,
            'categories': {
                'healthy': {'count': 0, 'percentage': 0, 'tone': 'success', 'label': 'Healthy (80-100)'},
                'at_risk': {'count': 0, 'percentage': 0, 'tone': 'warning', 'label': 'At Risk (40 to <80)'},
                'critical': {'count': 0, 'percentage': 0, 'tone': 'danger', 'label': 'Critical (0 to <40)'},
            },
            'risk_factors': [],
            'projects': [],
        }

    cat_counts = {'healthy': 0, 'at_risk': 0, 'critical': 0}
    scores = []
    risk_factor_counts = OrderedDict()

    for row in project_rows:
        score = row['health_score']
        scores.append(score)
        label = row['health_label']
        if label == 'Healthy':
            cat_counts['healthy'] += 1
        elif label == 'At Risk':
            cat_counts['at_risk'] += 1
        else:
            cat_counts['critical'] += 1

        for r in row.get('risk_reasons', []):
            k = r['key']
            if k not in risk_factor_counts:
                risk_factor_counts[k] = {'key': k, 'label': r['label'], 'tone': r['tone'], 'count': 0}
            risk_factor_counts[k]['count'] += 1

    projects_summary = [
        {
            'id': row['project_id'],
            'title': row['project_name'],
            'lgu_name': row['lgu_name'],
            'program_name': row['program_name'],
            'overall_status': row['overall_status'],
            'physical_completion_pct': row['physical_completion_pct'],
            'health_score': row['health_score'],
            'health_label': row['health_label'],
            'health_tone': row['health_tone'],
            'risk_reasons': row['risk_reasons'],
            'document_open_count': row['document_open_count'],
        }
        for row in sorted(project_rows, key=lambda r: r['health_score'])
    ]

    for rf in risk_factor_counts.values():
        rf['percentage'] = _percentage(rf['count'], total)

    return {
        'total_projects': total,
        'average_score': round(sum(scores) / total, 1),
        'categories': {
            'healthy': {'count': cat_counts['healthy'], 'percentage': _percentage(cat_counts['healthy'], total), 'tone': 'success', 'label': 'Healthy (80-100)'},
            'at_risk': {'count': cat_counts['at_risk'], 'percentage': _percentage(cat_counts['at_risk'], total), 'tone': 'warning', 'label': 'At Risk (40 to <80)'},
            'critical': {'count': cat_counts['critical'], 'percentage': _percentage(cat_counts['critical'], total), 'tone': 'danger', 'label': 'Critical (0 to <40)'},
        },
        'risk_factors': list(risk_factor_counts.values()),
        'projects': projects_summary,
    }


def _monthly_workflow_action_volume(project_ids):
    empty_result = {
        'months': [],
        'action_totals': {action: 0 for action in WORKFLOW_ACTIONS},
        'total_actions': 0,
        'transitions': [],
    }
    if not project_ids:
        return empty_result

    bind = db.session.get_bind()
    if bind.dialect.name == 'postgresql':
        month_col = func.to_char(RequirementWorkflowTransition.created_at, 'YYYY-MM')
    else:
        month_col = func.strftime('%Y-%m', RequirementWorkflowTransition.created_at)

    rows = (
        db.session.query(
            month_col.label('month'),
            RequirementWorkflowTransition.action,
            func.count(RequirementWorkflowTransition.id).label('count'),
        )
        .join(ProjectRequirement, RequirementWorkflowTransition.project_requirement_id == ProjectRequirement.id)
        .filter(ProjectRequirement.project_id.in_(project_ids))
        .group_by(month_col, RequirementWorkflowTransition.action)
        .order_by(month_col.asc(), RequirementWorkflowTransition.action.asc())
        .all()
    )

    month_data = OrderedDict()
    action_totals = {action: 0 for action in WORKFLOW_ACTIONS}
    total_actions = 0

    for m, action, count in rows:
        if not m:
            continue
        if m not in month_data:
            month_data[m] = {act: 0 for act in WORKFLOW_ACTIONS}
        if action in month_data[m]:
            month_data[m][action] += count
        else:
            month_data[m][action] = count
        if action in action_totals:
            action_totals[action] += count
        total_actions += count

    months_summary = []
    for m, acts in month_data.items():
        m_total = sum(acts.values())
        try:
            dt = datetime.strptime(m, '%Y-%m')
            label = dt.strftime('%b %Y')
        except ValueError:
            label = m
        months_summary.append({
            'month': m,
            'month_label': label,
            'total': m_total,
            'actions': acts,
        })

    trans_rows = (
        db.session.query(
            RequirementWorkflowTransition.id,
            month_col.label('month'),
            RequirementWorkflowTransition.action,
            RequirementWorkflowTransition.from_status,
            RequirementWorkflowTransition.to_status,
            RequirementWorkflowTransition.reason,
            RequirementWorkflowTransition.created_at,
            RequirementWorkflowTransition.project_requirement_id,
            ProjectRequirement.requirement_name,
            ProjectRequirement.status.label('compliance_status'),
            ProjectRequirement.workflow_status,
            Project.id.label('project_id'),
            Project.project_name,
            Program.name.label('program_name'),
            LguProfile.name.label('lgu_name'),
            User.first_name.label('actor_first_name'),
            User.last_name.label('actor_last_name'),
        )
        .join(ProjectRequirement, RequirementWorkflowTransition.project_requirement_id == ProjectRequirement.id)
        .join(Project, ProjectRequirement.project_id == Project.id)
        .outerjoin(Program, Project.program_id == Program.id)
        .outerjoin(LguProfile, Project.lgu_id == LguProfile.id)
        .outerjoin(User, RequirementWorkflowTransition.actor_id == User.id)
        .filter(ProjectRequirement.project_id.in_(project_ids))
        .order_by(RequirementWorkflowTransition.created_at.desc())
        .all()
    )

    serialized_transitions = [
        {
            'id': r.id,
            'month': r.month,
            'action': r.action,
            'action_label': _workflow_action_label(r.action),
            'from_status': r.from_status,
            'to_status': r.to_status,
            'reason': r.reason,
            'created_at': _utc_iso(r.created_at) if r.created_at else None,
            'project_requirement_id': r.project_requirement_id,
            'requirement_name': r.requirement_name,
            'compliance_status': r.compliance_status,
            'workflow_status': r.workflow_status,
            'project_id': r.project_id,
            'project_name': r.project_name,
            'program_name': r.program_name or 'Unknown Program',
            'lgu_name': r.lgu_name or 'Unassigned',
            'actor_name': f"{r.actor_first_name or ''} {r.actor_last_name or ''}".strip() or 'System / Anonymous',
        }
        for r in trans_rows
    ]

    return {
        'months': months_summary,
        'monthly_volume': months_summary,
        'action_totals': action_totals,
        'total_actions': total_actions,
        'transitions': serialized_transitions,
    }


def _problematic_requirements_aggregation(project_ids):
    empty_result = {
        'total_return_events': 0,
        'unique_requirements_returned': 0,
        'affected_projects_total': 0,
        'requirements': [],
    }
    if not project_ids:
        return empty_result

    summary_rows = (
        db.session.query(
            ProjectRequirement.requirement_name,
            func.count(RequirementWorkflowTransition.id).label('return_count'),
            func.count(func.distinct(RequirementWorkflowTransition.project_requirement_id)).label('unique_requirements_count'),
            func.count(func.distinct(ProjectRequirement.project_id)).label('affected_projects_count'),
            func.count(func.distinct(Project.lgu_id)).label('affected_lgus_count'),
        )
        .join(RequirementWorkflowTransition, RequirementWorkflowTransition.project_requirement_id == ProjectRequirement.id)
        .join(Project, ProjectRequirement.project_id == Project.id)
        .filter(
            ProjectRequirement.project_id.in_(project_ids),
            RequirementWorkflowTransition.action == 'return_for_revision',
        )
        .group_by(ProjectRequirement.requirement_name)
        .order_by(func.count(RequirementWorkflowTransition.id).desc(), ProjectRequirement.requirement_name.asc())
        .all()
    )

    total_return_events = sum(r.return_count for r in summary_rows)
    all_unique_req_ids = (
        db.session.query(func.distinct(RequirementWorkflowTransition.project_requirement_id))
        .join(ProjectRequirement, RequirementWorkflowTransition.project_requirement_id == ProjectRequirement.id)
        .filter(
            ProjectRequirement.project_id.in_(project_ids),
            RequirementWorkflowTransition.action == 'return_for_revision',
        )
        .count()
    )
    all_affected_proj_ids = (
        db.session.query(func.distinct(ProjectRequirement.project_id))
        .join(RequirementWorkflowTransition, RequirementWorkflowTransition.project_requirement_id == ProjectRequirement.id)
        .filter(
            ProjectRequirement.project_id.in_(project_ids),
            RequirementWorkflowTransition.action == 'return_for_revision',
        )
        .count()
    )

    event_rows = (
        db.session.query(
            RequirementWorkflowTransition.id,
            RequirementWorkflowTransition.created_at,
            RequirementWorkflowTransition.reason,
            ProjectRequirement.id.label('project_requirement_id'),
            ProjectRequirement.requirement_name,
            ProjectRequirement.status.label('current_compliance_status'),
            ProjectRequirement.workflow_status.label('current_workflow_status'),
            Project.id.label('project_id'),
            Project.project_name,
            Program.name.label('program_name'),
            LguProfile.name.label('lgu_name'),
            User.first_name.label('actor_first_name'),
            User.last_name.label('actor_last_name'),
        )
        .join(ProjectRequirement, RequirementWorkflowTransition.project_requirement_id == ProjectRequirement.id)
        .join(Project, ProjectRequirement.project_id == Project.id)
        .outerjoin(Program, Project.program_id == Program.id)
        .outerjoin(LguProfile, Project.lgu_id == LguProfile.id)
        .outerjoin(User, RequirementWorkflowTransition.actor_id == User.id)
        .filter(
            ProjectRequirement.project_id.in_(project_ids),
            RequirementWorkflowTransition.action == 'return_for_revision',
        )
        .order_by(RequirementWorkflowTransition.created_at.desc())
        .all()
    )

    events_by_req = OrderedDict()
    for e in event_rows:
        req_name = e.requirement_name
        if req_name not in events_by_req:
            events_by_req[req_name] = []
        events_by_req[req_name].append({
            'transition_id': e.id,
            'created_at': _utc_iso(e.created_at) if e.created_at else None,
            'reason': e.reason,
            'project_requirement_id': e.project_requirement_id,
            'requirement_name': e.requirement_name,
            'current_compliance_status': e.current_compliance_status,
            'current_workflow_status': e.current_workflow_status,
            'project_id': e.project_id,
            'project_name': e.project_name,
            'program_name': e.program_name or 'Unknown Program',
            'lgu_name': e.lgu_name or 'Unassigned',
            'actor_name': f"{e.actor_first_name or ''} {e.actor_last_name or ''}".strip() or 'Review Staff',
        })

    requirements_list = []
    for r in summary_rows:
        requirements_list.append({
            'requirement_name': r.requirement_name,
            'return_count': r.return_count,
            'unique_requirements_count': r.unique_requirements_count,
            'affected_projects_count': r.affected_projects_count,
            'affected_lgus_count': r.affected_lgus_count,
            'events': events_by_req.get(r.requirement_name, []),
        })

    return {
        'total_return_events': total_return_events,
        'unique_requirements_returned': all_unique_req_ids,
        'affected_projects_total': all_affected_proj_ids,
        'requirements': requirements_list,
    }


def _overdue_deadlines_by_lgu_aggregation(project_ids):
    empty_result = {
        'total_overdue': 0,
        'total_overdue_deadlines': 0,
        'affected_lgus_count': 0,
        'total_affected_lgus': 0,
        'lgus': [],
    }
    if not project_ids:
        return empty_result

    now_utc = datetime.now(timezone.utc)
    now_db = now_utc.replace(tzinfo=None)

    query = SlaDeadline.query.filter(
        SlaDeadline.project_id.in_(project_ids),
        SlaDeadline.is_resolved == False,
        SlaDeadline.deadline_date < now_db,
    )
    query = filter_active_compliance_deadlines(query)

    overdue_rows = (
        query
        .join(Project, SlaDeadline.project_id == Project.id)
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .outerjoin(LguCluster, LguProfile.cluster_id == LguCluster.id)
        .with_entities(
            LguProfile.id.label('lgu_id'),
            LguProfile.name.label('lgu_name'),
            LguCluster.id.label('cluster_id'),
            LguCluster.name.label('cluster_name'),
            func.count(SlaDeadline.id).label('overdue_count'),
            func.count(func.distinct(Project.id)).label('affected_project_count'),
        )
        .group_by(LguProfile.id, LguProfile.name, LguCluster.id, LguCluster.name)
        .order_by(func.count(SlaDeadline.id).desc(), LguProfile.name.asc())
        .all()
    )

    total_overdue = sum(r.overdue_count for r in overdue_rows)

    lgus = [
        {
            'lgu_id': r.lgu_id,
            'lgu_name': r.lgu_name,
            'cluster_id': r.cluster_id,
            'cluster_name': r.cluster_name or 'Unclustered',
            'overdue_count': r.overdue_count,
            'affected_project_count': r.affected_project_count,
        }
        for r in overdue_rows
    ]

    return {
        'total_overdue': total_overdue,
        'total_overdue_deadlines': total_overdue,
        'affected_lgus_count': len(lgus),
        'total_affected_lgus': len(lgus),
        'lgus': lgus,
    }


def _project_phase_distribution_aggregation(project_ids):
    empty_result = {
        'total_projects': 0,
        'phases': [
            {
                'phase': phase,
                'label': _project_phase_label(phase),
                'count': 0,
                'percentage': 0,
                'tone': _project_phase_tone(phase),
            }
            for phase in PROJECT_PHASES
        ],
    }
    if not project_ids:
        return empty_result

    rows = (
        db.session.query(
            Project.current_phase,
            func.count(Project.id).label('count')
        )
        .filter(Project.id.in_(project_ids))
        .group_by(Project.current_phase)
        .all()
    )

    counts = {phase: 0 for phase in PROJECT_PHASES}
    for phase, count in rows:
        if phase in counts:
            counts[phase] += count
        else:
            counts['pre_implementation'] += count

    total = sum(counts.values())

    phases = [
        {
            'phase': phase,
            'label': _project_phase_label(phase),
            'count': counts[phase],
            'percentage': _percentage(counts[phase], total),
            'tone': _project_phase_tone(phase),
        }
        for phase in PROJECT_PHASES
    ]

    return {
        'total_projects': total,
        'phases': phases,
    }


def _infrastructure_slippage_aggregation(projects, project_ids):
    empty_result = {
        'total_infrastructure_projects': 0,
        'total_reported_projects': 0,
        'average_variance_pct': None,
        'tiers': [
            {
                'tier': tier,
                'label': SLIPPAGE_TIER_CONFIG[tier]['label'],
                'short_label': SLIPPAGE_TIER_CONFIG[tier]['short_label'],
                'range': SLIPPAGE_TIER_CONFIG[tier]['range'],
                'count': 0,
                'percentage': 0.0,
                'tone': SLIPPAGE_TIER_CONFIG[tier]['tone'],
                'project_ids': [],
            }
            for tier in SLIPPAGE_TIERS
        ],
        'tier_counts': {tier: 0 for tier in SLIPPAGE_TIERS},
    }
    if not project_ids or not projects:
        return empty_result

    infra_projects = [p for p in projects if resolve_effective_project_kind(p) == 'infrastructure']
    infra_project_ids = [p.id for p in infra_projects]
    total_infra = len(infra_projects)
    if not total_infra:
        return empty_result

    mprs = _latest_mprs_by_project(infra_project_ids)

    tier_projects = {tier: [] for tier in SLIPPAGE_TIERS}
    reported_variances = []

    for p in infra_projects:
        mpr = mprs.get(p.id)
        if _schedule_variance(mpr) is not None:
            var_val = _schedule_variance(mpr)
            tier = _determine_slippage_tier(var_val)
            tier_projects[tier].append(p.id)
            reported_variances.append(var_val)
        else:
            tier_projects['unreported'].append(p.id)

    total_reported = len(reported_variances)
    avg_variance = round(sum(reported_variances) / total_reported, 2) if total_reported > 0 else None

    tiers = [
        {
            'tier': tier,
            'label': SLIPPAGE_TIER_CONFIG[tier]['label'],
            'short_label': SLIPPAGE_TIER_CONFIG[tier]['short_label'],
            'range': SLIPPAGE_TIER_CONFIG[tier]['range'],
            'count': len(tier_projects[tier]),
            'percentage': _percentage(len(tier_projects[tier]), total_infra),
            'tone': SLIPPAGE_TIER_CONFIG[tier]['tone'],
            'project_ids': tier_projects[tier],
        }
        for tier in SLIPPAGE_TIERS
    ]

    return {
        'total_infrastructure_projects': total_infra,
        'total_reported_projects': total_reported,
        'average_variance_pct': avg_variance,
        'tiers': tiers,
        'tier_counts': {tier: len(tier_projects[tier]) for tier in SLIPPAGE_TIERS},
    }


def _qaar_defect_severity_aggregation(project_ids):
    empty_result = {
        'total_findings': 0,
        'total_inspections': 0,
        'affected_projects_count': 0,
        'severe_count': 0,
        'major_count': 0,
        'minor_count': 0,
        'severities': [
            {
                'severity': sev,
                'label': QAAR_SEVERITY_CONFIG[sev]['label'],
                'count': 0,
                'percentage': 0.0,
                'tone': QAAR_SEVERITY_CONFIG[sev]['tone'],
            }
            for sev in QAAR_SEVERITIES
        ],
        'severity_counts': {sev: 0 for sev in QAAR_SEVERITIES},
        'findings': [],
    }
    if not project_ids:
        return empty_result

    total_inspections = (
        db.session.query(func.count(QaarInspection.id))
        .filter(QaarInspection.project_id.in_(project_ids))
        .scalar()
    ) or 0

    findings_query = (
        db.session.query(
            QaarWorkFinding,
            QaarInspection,
            Project,
            LguProfile,
        )
        .join(QaarInspection, QaarWorkFinding.inspection_id == QaarInspection.id)
        .join(Project, QaarInspection.project_id == Project.id)
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .filter(Project.id.in_(project_ids))
        .order_by(
            QaarInspection.inspection_date.desc(),
            QaarWorkFinding.sort_order.asc(),
            QaarWorkFinding.id.asc(),
        )
    )
    rows = findings_query.all()

    counts = {sev: 0 for sev in QAAR_SEVERITIES}
    unclassified_count = 0
    findings_list = []
    affected_project_ids = set()

    for finding, inspection, project, lgu in rows:
        affected_project_ids.add(project.id)
        risk = (finding.risk_level or '').strip().lower()
        if risk in counts:
            counts[risk] += 1
        else:
            unclassified_count += 1
            risk = 'unclassified'

        findings_list.append({
            'id': finding.id,
            'inspection_id': finding.inspection_id,
            'project_id': project.id,
            'project_name': project.project_name,
            'lgu_id': project.lgu_id,
            'lgu_name': lgu.name,
            'inspection_date': str(inspection.inspection_date) if inspection.inspection_date else None,
            'inspection_status': inspection.status,
            'defect_code': finding.defect_code,
            'defect_description': finding.defect_description,
            'quality_issue': finding.quality_issue,
            'degree_of_defect': finding.degree_of_defect,
            'risk_level': risk,
            'recommendation': finding.recommendation,
            'location': finding.location,
            'timeline': finding.timeline,
            'remarks': finding.remarks,
        })

    total_findings = len(findings_list)

    severities = [
        {
            'severity': sev,
            'label': QAAR_SEVERITY_CONFIG[sev]['label'],
            'count': counts[sev],
            'percentage': _percentage(counts[sev], total_findings) if total_findings > 0 else 0.0,
            'tone': QAAR_SEVERITY_CONFIG[sev]['tone'],
        }
        for sev in QAAR_SEVERITIES
    ]
    if unclassified_count > 0:
        severities.append({
            'severity': 'unclassified',
            'label': 'Unclassified',
            'count': unclassified_count,
            'percentage': _percentage(unclassified_count, total_findings),
            'tone': 'slate',
        })

    return {
        'total_findings': total_findings,
        'total_inspections': total_inspections,
        'affected_projects_count': len(affected_project_ids),
        'severe_count': counts['severe'],
        'major_count': counts['major'],
        'minor_count': counts['minor'],
        'severities': severities,
        'severity_counts': counts,
        'findings': findings_list,
    }


def _non_infra_delivery_aggregation(projects, project_ids):
    empty_result = {
        'total_non_infra_projects': 0,
        'total_monitoring_records': 0,
        'total_evidence_records': 0,
        'total_beneficiaries_assisted': 0,
        'specifications_summary': {
            'met': 0,
            'not_met': 0,
            'pending': 0,
            'total': 0,
            'compliance_rate': 0.0,
            'distinct_projects_assessed': 0,
            'met_project_ids': [],
            'not_met_project_ids': [],
            'pending_project_ids': [],
        },
        'specifications_distribution': [
            {'key': 'met', 'label': 'Specifications Met', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'project_count': 0, 'tone': 'emerald'},
            {'key': 'not_met', 'label': 'Specifications Not Met', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'project_count': 0, 'tone': 'rose'},
            {'key': 'pending', 'label': 'Pending Verification', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'project_count': 0, 'tone': 'amber'},
        ],
        'evidence_types': [
            {
                'key': k,
                'label': label,
                'record_count': 0,
                'beneficiary_count': 0,
            }
            for k, label in EVIDENCE_TYPE_LABELS.items()
        ],
        'evidence_records': [],
    }
    if not project_ids or not projects:
        return empty_result

    non_infra_projects = [p for p in projects if resolve_effective_project_kind(p) != 'infrastructure']
    non_infra_project_ids = [p.id for p in non_infra_projects]

    monitoring_records = (
        NonInfraMonitoringRecord.query
        .filter(NonInfraMonitoringRecord.project_id.in_(non_infra_project_ids))
        .all()
    )

    met_count = 0
    not_met_count = 0
    pending_count = 0
    met_project_ids = set()
    not_met_project_ids = set()
    pending_project_ids = set()

    for r in monitoring_records:
        if r.specifications_met is True:
            met_count += 1
            met_project_ids.add(r.project_id)
        elif r.specifications_met is False:
            not_met_count += 1
            not_met_project_ids.add(r.project_id)
        else:
            pending_count += 1
            pending_project_ids.add(r.project_id)

    total_mon = len(monitoring_records)
    assessed_project_ids = met_project_ids | not_met_project_ids | pending_project_ids

    evidence_records = (
        db.session.query(BeneficiaryEvidenceRecord, Project, LguProfile)
        .join(Project, BeneficiaryEvidenceRecord.project_id == Project.id)
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .filter(BeneficiaryEvidenceRecord.project_id.in_(non_infra_project_ids))
        .order_by(
            BeneficiaryEvidenceRecord.distribution_date.desc().nullslast(),
            BeneficiaryEvidenceRecord.id.desc(),
        )
        .all()
    )

    ev_type_counts = {k: 0 for k in EVIDENCE_TYPE_LABELS}
    ev_type_beneficiaries = {k: 0 for k in EVIDENCE_TYPE_LABELS}
    evidence_list = []
    total_beneficiaries = 0

    for record, proj, lgu in evidence_records:
        cnt = record.beneficiary_count or 0
        total_beneficiaries += cnt
        ev_type = record.evidence_type
        if ev_type in ev_type_counts:
            ev_type_counts[ev_type] += 1
            ev_type_beneficiaries[ev_type] += cnt

        evidence_list.append({
            'id': record.id,
            'project_id': record.project_id,
            'project_name': proj.project_name,
            'lgu_id': proj.lgu_id,
            'lgu_name': lgu.name,
            'evidence_type': record.evidence_type,
            'evidence_type_label': EVIDENCE_TYPE_LABELS.get(record.evidence_type, record.evidence_type.replace('_', ' ').title()),
            'beneficiary_count': record.beneficiary_count,
            'distribution_date': str(record.distribution_date) if record.distribution_date else None,
            'reference_number': record.reference_number,
            'description': record.description,
        })

    evidence_types_summary = [
        {
            'key': k,
            'label': label,
            'record_count': ev_type_counts[k],
            'beneficiary_count': ev_type_beneficiaries[k],
        }
        for k, label in EVIDENCE_TYPE_LABELS.items()
    ]

    return {
        'total_non_infra_projects': len(non_infra_projects),
        'total_monitoring_records': total_mon,
        'total_evidence_records': len(evidence_records),
        'total_beneficiaries_assisted': total_beneficiaries,
        'specifications_summary': {
            'met': met_count,
            'not_met': not_met_count,
            'pending': pending_count,
            'total': total_mon,
            'compliance_rate': _percentage(met_count, total_mon) if total_mon > 0 else 0.0,
            'distinct_projects_assessed': len(assessed_project_ids),
            'met_project_ids': sorted(list(met_project_ids)),
            'not_met_project_ids': sorted(list(not_met_project_ids)),
            'pending_project_ids': sorted(list(pending_project_ids)),
        },
        'specifications_distribution': [
            {
                'key': 'met',
                'label': 'Specifications Met',
                'count': met_count,
                'percentage': _percentage(met_count, total_mon) if total_mon > 0 else 0.0,
                'project_ids': sorted(list(met_project_ids)),
                'project_count': len(met_project_ids),
                'tone': 'emerald',
            },
            {
                'key': 'not_met',
                'label': 'Specifications Not Met',
                'count': not_met_count,
                'percentage': _percentage(not_met_count, total_mon) if total_mon > 0 else 0.0,
                'project_ids': sorted(list(not_met_project_ids)),
                'project_count': len(not_met_project_ids),
                'tone': 'rose',
            },
            {
                'key': 'pending',
                'label': 'Pending Verification',
                'count': pending_count,
                'percentage': _percentage(pending_count, total_mon) if total_mon > 0 else 0.0,
                'project_ids': sorted(list(pending_project_ids)),
                'project_count': len(pending_project_ids),
                'tone': 'amber',
            },
        ],
        'evidence_types': evidence_types_summary,
        'evidence_records': evidence_list,
    }


def _closeout_readiness_aggregation(projects, project_ids, milestones=None, completion_docs=None):
    empty_result = {
        'total_projects': 0,
        'physically_complete_count': 0,
        'pre_completion_count': 0,
        'punchlist_cleared_count': 0,
        'punchlist_unresolved_count': 0,
        'punchlist_unassessed_count': 0,
        'docs_ready_count': 0,
        'docs_pending_count': 0,
        'vault_ready_count': 0,
        'final_approved_count': 0,
        'readiness_rate': 0.0,
        'approval_rate': 0.0,
        'stages': [
            {'key': 'physically_complete', 'label': 'Physically Complete (100%)', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'tone': 'info'},
            {'key': 'punchlist_cleared', 'label': 'Punchlist Cleared', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'tone': 'yellow'},
            {'key': 'docs_ready', 'label': 'Closeout Docs Ready', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'tone': 'emerald'},
            {'key': 'docs_pending', 'label': 'Closeout Docs Pending', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'tone': 'amber'},
            {'key': 'vault_ready', 'label': 'Vault Locked / Ready', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'tone': 'purple'},
            {'key': 'final_approved', 'label': 'Final Closeout Approved', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'tone': 'emerald'},
        ],
        'projects': [],
    }
    if not project_ids or not projects:
        return empty_result

    total_projects = len(projects)
    if milestones is None:
        milestones = _milestones_by_project(project_ids)
    if completion_docs is None:
        completion_docs = _completion_docs_by_project(project_ids)

    phys_complete_ids = []
    punchlist_cleared_ids = []
    punchlist_unresolved_ids = []
    punchlist_unassessed_ids = []
    docs_ready_ids = []
    docs_pending_ids = []
    vault_ready_ids = []
    final_approved_ids = []
    closeout_projects = []

    for p in projects:
        effective_kind = resolve_effective_project_kind(p)
        phys_val = _decimal_to_float(p.physical_completion_pct)
        is_phys_complete = (phys_val >= 100.0)
        m = milestones.get(p.id)
        docs = completion_docs.get(p.id, [])

        if not is_phys_complete:
            continue

        phys_complete_ids.append(p.id)

        # Punchlist evaluation
        is_punchlist_cleared = True
        is_punchlist_blocked = False
        punchlist_status = 'exempt'

        if effective_kind == 'infrastructure':
            if m and m.punchlist_items_total is not None and m.punchlist_items_total > 0:
                resolved = m.punchlist_items_resolved or 0
                if resolved < m.punchlist_items_total:
                    is_punchlist_blocked = True
                    is_punchlist_cleared = False
                    punchlist_status = 'unresolved'
                else:
                    punchlist_status = 'cleared'
            elif m and m.punchlist_items_total == 0:
                punchlist_status = 'cleared'
            else:
                punchlist_status = 'unassessed'
                is_punchlist_cleared = False
        else:
            punchlist_status = 'exempt'

        if punchlist_status == 'unassessed':
            punchlist_unassessed_ids.append(p.id)
        elif is_punchlist_blocked:
            punchlist_unresolved_ids.append(p.id)
        else:
            punchlist_cleared_ids.append(p.id)

        # Evaluate the full matrix, including absent rows, with canonical applicability.
        docs_total_applicable, docs_approved_count, docs_pending_count = _completion_document_counts(p, m, docs)
        has_pending_doc = docs_pending_count > 0
        if has_pending_doc:
            docs_pending_ids.append(p.id)
        else:
            docs_ready_ids.append(p.id)

        is_vault = bool(m and m.is_vault_ready)
        if is_vault:
            vault_ready_ids.append(p.id)

        is_approved = bool(m and m.final_approval_at is not None)
        if is_approved:
            final_approved_ids.append(p.id)

        # Stage classification
        if punchlist_status == 'unassessed':
            stage = 'punchlist_unassessed'
            stage_label = 'Punchlist Not Assessed'
        elif is_punchlist_blocked:
            stage = 'punchlist_unresolved'
            stage_label = 'Punchlist Unresolved'
        elif has_pending_doc:
            stage = 'docs_pending'
            stage_label = 'Closeout Docs Pending'
        elif is_approved:
            stage = 'final_approved'
            stage_label = 'Closeout Approved'
        elif is_vault:
            stage = 'vault_ready'
            stage_label = 'Vault Ready'
        else:
            stage = 'docs_ready'
            stage_label = 'Closeout Docs Ready'

        closeout_projects.append({
            'id': p.id,
            'project_name': p.project_name,
            'project_code': p.source_project_code or p.subaybayan_project_code,
            'lgu_id': p.lgu_id,
            'lgu_name': p.lgu.name if p.lgu else 'Unassigned',
            'program_name': p.program.name if p.program else 'Unknown Program',
            'effective_project_kind': effective_kind,
            'physical_completion_pct': phys_val,
            'punchlist_total': m.punchlist_items_total if m else None,
            'punchlist_resolved': m.punchlist_items_resolved if m else None,
            'punchlist_status': punchlist_status,
            'docs_total': docs_total_applicable,
            'docs_approved': docs_approved_count,
            'docs_pending': docs_pending_count,
            'is_vault_ready': is_vault,
            'is_final_approved': is_approved,
            'final_approval_at': _utc_iso(m.final_approval_at) if (m and m.final_approval_at) else None,
            'closeout_stage': stage,
            'closeout_stage_label': stage_label,
        })

    total_phys = len(phys_complete_ids)
    readiness_rate = _percentage(len(docs_ready_ids), total_phys) if total_phys > 0 else 0.0
    approval_rate = _percentage(len(final_approved_ids), total_phys) if total_phys > 0 else 0.0

    stages = [
        {'key': 'punchlist_unassessed', 'label': 'Punchlist Not Assessed', 'count': len(punchlist_unassessed_ids), 'percentage': _percentage(len(punchlist_unassessed_ids), total_phys), 'project_ids': sorted(punchlist_unassessed_ids), 'tone': 'amber'},
        {
            'key': 'physically_complete',
            'label': 'Physically Complete (100%)',
            'count': total_phys,
            'percentage': _percentage(total_phys, total_projects),
            'project_ids': sorted(phys_complete_ids),
            'tone': 'info',
        },
        {
            'key': 'punchlist_cleared',
            'label': 'Punchlist Cleared',
            'count': len(punchlist_cleared_ids),
            'percentage': _percentage(len(punchlist_cleared_ids), total_phys) if total_phys > 0 else 0.0,
            'project_ids': sorted(punchlist_cleared_ids),
            'tone': 'yellow',
        },
        {
            'key': 'docs_ready',
            'label': 'Closeout Docs Ready',
            'count': len(docs_ready_ids),
            'percentage': _percentage(len(docs_ready_ids), total_phys) if total_phys > 0 else 0.0,
            'project_ids': sorted(docs_ready_ids),
            'tone': 'emerald',
        },
        {
            'key': 'docs_pending',
            'label': 'Closeout Docs Pending',
            'count': len(docs_pending_ids),
            'percentage': _percentage(len(docs_pending_ids), total_phys) if total_phys > 0 else 0.0,
            'project_ids': sorted(docs_pending_ids),
            'tone': 'amber',
        },
        {
            'key': 'vault_ready',
            'label': 'Vault Locked / Ready',
            'count': len(vault_ready_ids),
            'percentage': _percentage(len(vault_ready_ids), total_phys) if total_phys > 0 else 0.0,
            'project_ids': sorted(vault_ready_ids),
            'tone': 'purple',
        },
        {
            'key': 'final_approved',
            'label': 'Final Closeout Approved',
            'count': len(final_approved_ids),
            'percentage': _percentage(len(final_approved_ids), total_phys) if total_phys > 0 else 0.0,
            'project_ids': sorted(final_approved_ids),
            'tone': 'emerald',
        },
    ]

    return {
        'total_projects': total_projects,
        'physically_complete_count': total_phys,
        'pre_completion_count': total_projects - total_phys,
        'punchlist_cleared_count': len(punchlist_cleared_ids),
        'punchlist_unresolved_count': len(punchlist_unresolved_ids),
        'punchlist_unassessed_count': len(punchlist_unassessed_ids),
        'docs_ready_count': len(docs_ready_ids),
        'docs_pending_count': len(docs_pending_ids),
        'vault_ready_count': len(vault_ready_ids),
        'final_approved_count': len(final_approved_ids),
        'readiness_rate': readiness_rate,
        'approval_rate': approval_rate,
        'stages': stages,
        'projects': closeout_projects,
    }


def _regional_handoff_aggregation(projects, project_ids):
    empty_result = {
        'total_events': 0,
        'distinct_projects_transmitted': 0,
        'total_files_pushed': 0,
        'projects_all_completed': 0,
        'projects_with_failures': 0,
        'projects_with_pending': 0,
        'statuses': [
            {'status': 'completed', 'label': 'Completed', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'project_count': 0, 'tone': 'emerald'},
            {'status': 'in_progress', 'label': 'In Progress', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'project_count': 0, 'tone': 'amber'},
            {'status': 'pending', 'label': 'Pending', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'project_count': 0, 'tone': 'yellow'},
            {'status': 'failed', 'label': 'Failed', 'count': 0, 'percentage': 0.0, 'project_ids': [], 'project_count': 0, 'tone': 'rose'},
        ],
        'no_handoff': {
            'count': 0,
            'project_ids': [],
        },
        'transmissions': [],
    }
    if not project_ids or not projects:
        return empty_result

    push_rows = (
        db.session.query(GoogleDrivePush, Project, LguProfile, User)
        .join(Project, GoogleDrivePush.project_id == Project.id)
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .outerjoin(User, GoogleDrivePush.pushed_by == User.id)
        .filter(GoogleDrivePush.project_id.in_(project_ids))
        .order_by(GoogleDrivePush.created_at.desc(), GoogleDrivePush.id.desc())
        .all()
    )

    total_events = len(push_rows)
    transmitted_project_ids = set()
    total_files = 0

    HANDOFF_STATUS_KEYS = ('completed', 'in_progress', 'pending', 'failed')
    status_counts = {st: 0 for st in HANDOFF_STATUS_KEYS}
    status_project_ids = {st: set() for st in HANDOFF_STATUS_KEYS}

    project_pushes = {}
    transmissions_list = []

    for push, proj, lgu, actor in push_rows:
        transmitted_project_ids.add(push.project_id)
        f_count = push.files_count or 0
        total_files += f_count

        st = push.push_status
        if st in status_counts:
            status_counts[st] += 1
            status_project_ids[st].add(push.project_id)

        if push.project_id not in project_pushes:
            project_pushes[push.project_id] = []
        project_pushes[push.project_id].append(push)

        actor_name = f"{actor.first_name or ''} {actor.last_name or ''}".strip() if actor else 'System / Automated'
        transmissions_list.append({
            'id': push.id,
            'project_id': push.project_id,
            'project_name': proj.project_name,
            'project_code': proj.source_project_code or proj.subaybayan_project_code,
            'lgu_id': proj.lgu_id,
            'lgu_name': lgu.name,
            'push_status': push.push_status,
            'drive_folder_id': push.drive_folder_id,
            'drive_folder_url': push.drive_folder_url,
            'destination_path': push.destination_path,
            'files_count': f_count,
            'total_size_bytes': push.total_size_bytes,
            'error_message': push.error_message,
            'created_at': _utc_iso(push.created_at) if push.created_at else None,
            'pushed_at': _utc_iso(push.pushed_at) if push.pushed_at else None,
            'pushed_by_name': actor_name,
        })

    all_in_scope_project_ids = set(project_ids)
    no_handoff_project_ids = sorted(list(all_in_scope_project_ids - transmitted_project_ids))

    projects_all_completed = []
    projects_with_failures = []
    projects_with_pending = []

    for pid, pushes in project_pushes.items():
        statuses = [p.push_status for p in pushes]
        if 'failed' in statuses:
            projects_with_failures.append(pid)
        elif any(s in ('pending', 'in_progress') for s in statuses):
            projects_with_pending.append(pid)
        elif all(s == 'completed' for s in statuses):
            projects_all_completed.append(pid)

    HANDOFF_CONFIG = {
        'completed': {'label': 'Completed', 'tone': 'emerald'},
        'in_progress': {'label': 'In Progress', 'tone': 'amber'},
        'pending': {'label': 'Pending', 'tone': 'yellow'},
        'failed': {'label': 'Failed', 'tone': 'rose'},
    }

    statuses_summary = [
        {
            'status': st,
            'label': HANDOFF_CONFIG[st]['label'],
            'count': status_counts[st],
            'percentage': _percentage(status_counts[st], total_events) if total_events > 0 else 0.0,
            'project_ids': sorted(list(status_project_ids[st])),
            'project_count': len(status_project_ids[st]),
            'tone': HANDOFF_CONFIG[st]['tone'],
        }
        for st in HANDOFF_STATUS_KEYS
    ]

    return {
        'total_events': total_events,
        'distinct_projects_transmitted': len(transmitted_project_ids),
        'total_files_pushed': total_files,
        'projects_all_completed': len(projects_all_completed),
        'projects_with_failures': len(projects_with_failures),
        'projects_with_pending': len(projects_with_pending),
        'statuses': statuses_summary,
        'no_handoff': {
            'count': len(no_handoff_project_ids),
            'project_ids': no_handoff_project_ids,
        },
        'transmissions': transmissions_list,
    }
