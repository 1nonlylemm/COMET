"""Operational reporting and executive analytics service for R27.

Wraps COMET's authoritative reporting engines:
- `reporting_service.py` (`get_monitoring_updates_report`, `_lgu_analytics`, `_risk_rows`)
- `dashboard_service.py` (`get_operations_dashboard`)
- `sla_service.py` (`get_sla_dashboard`, `get_overdue_deadlines`)
- `monitoring_service.py` (`get_monitoring_workbench`)
- `beneficiary_evidence_service.py` (`list_records`)

Preserves the approved COMET Truth Hierarchy:
- T1 = Direct Stored Fact
- T2 = Deterministic Computed Fact (compliance rates, overdue SLA counts, working-day timers, advisory composite risk scores)
- T3 = Analytical Synthesis / Interpretation (prioritization rankings, portfolio comparisons, deficiency summaries)
- T4 = Insufficient Evidence (macro provincial trends lacking periodic snapshots)
- T5 = Outside Evidence / Unsupported Inference (external/speculative causes outside COMET records)

Enforces strict territorial scoping (Field Officers see only assigned LGUs).
"""
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, or_

from app.extensions import db
from app.models import (
    BeneficiaryEvidenceRecord,
    LguProfile,
    MonthlyProgressReport,
    Project,
    ProjectRequirement,
    RequirementDeficiency,
    RequirementWorkflowTransition,
    SlaDeadline,
    Submission,
)
from app.models.workflow import DEFICIENCY_CATEGORIES
from app.services import (
    access_service,
    dashboard_service,
    field_officer_service,
    reporting_service,
    requirement_workflow_service,
    sla_service,
)
from app.services.email_service import _format_requirement_status_label
from app.services.fiscal_year_scope import apply_project_fiscal_year, apply_sla_project_fiscal_year

WORKFLOW_ACTION_EVENT_LABELS = {
    'submit': 'Submission',
    'verify': 'Verification',
    'staff_approve': 'Staff Approval',
    'provincial_approve': 'Provincial Approval',
    'return_for_revision': 'Return for Revision',
    'resubmit': 'Resubmission',
}


def _format_workflow_action_label(action):
    if not action:
        return 'Action'
    return WORKFLOW_ACTION_EVENT_LABELS.get(action, str(action).replace('_', ' ').title())


class OperationalReportingError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _format_label(value):
    return str(value or 'N/A').replace('_', ' ').replace('-', ' ').title()


def _is_overdue(deadline_val):
    if not deadline_val:
        return False
    now = datetime.now(timezone.utc)
    if hasattr(deadline_val, 'tzinfo') and deadline_val.tzinfo is not None:
        return deadline_val < now
    elif isinstance(deadline_val, datetime):
        return deadline_val < now.replace(tzinfo=None)
    elif hasattr(deadline_val, 'year'):  # date object
        return deadline_val < now.date()
    return False


def _has_open_document_obligation(requirement):
    if requirement.workflow_status == 'returned_for_revision':
        return True
    return (requirement.status in ('pending', 'under_review', 'non_compliant')
            and requirement.workflow_status not in ('approved', 'staff_approved'))


def get_provincial_overview_data(user_id, fiscal_year=None):
    """Retrieves authoritative province-wide or cluster-scoped operational overview."""
    scope = access_service.get_access_scope(user_id)
    if scope['role'] == 'field_officer':
        raise OperationalReportingError(
            'Field officers may not access province-wide reporting. Use get_field_summary for assigned LGU reporting.',
            403,
        )

    # 1. Projects
    p_query = Project.query.join(LguProfile, Project.lgu_id == LguProfile.id)
    p_query = access_service.restrict_project_query(p_query, user_id)
    p_query = apply_project_fiscal_year(p_query, fiscal_year)
    projects = p_query.all()
    project_ids = [p.id for p in projects]
    lgu_ids = list({p.lgu_id for p in projects})

    total_projects = len(projects)
    active_projects = sum(1 for p in projects if p.overall_status not in ('completed', 'cancelled'))
    completed_projects = sum(1 for p in projects if p.overall_status == 'completed')
    total_lgus = len(lgu_ids)

    # 2. Requirements & Compliance
    r_query = (
        ProjectRequirement.query.filter(
            ProjectRequirement.project_id.in_(project_ids),
            ProjectRequirement.is_active == True,
        )
        if project_ids else None
    )
    requirements = r_query.all() if r_query is not None else []
    req_ids = [r.id for r in requirements]

    total_requirements = len(requirements)
    applicable_reqs = [r for r in requirements if getattr(r, 'applicability', 'applicable') == 'applicable']
    not_applicable_reqs = [r for r in requirements if getattr(r, 'applicability', 'applicable') == 'not_applicable']
    applicable_count = len(applicable_reqs)
    not_applicable_count = len(not_applicable_reqs)

    compliant_count = sum(
        1 for r in applicable_reqs
        if r.status == 'compliant' or r.workflow_status in ('approved', 'staff_approved')
    )
    returned_count = sum(1 for r in applicable_reqs if r.workflow_status == 'returned_for_revision')
    under_review_count = sum(
        1 for r in applicable_reqs
        if (r.workflow_status in ('under_verification', 'submitted') or r.status == 'under_review')
        and r.workflow_status != 'returned_for_revision'
    )
    pending_count = sum(1 for r in applicable_reqs if r.workflow_status == 'draft' or r.status == 'pending')
    non_compliant_count = sum(1 for r in applicable_reqs if r.status == 'non_compliant')
    open_documents = sum(_has_open_document_obligation(r) for r in applicable_reqs)

    # Deficiencies
    d_query = (
        RequirementDeficiency.query.filter(
            RequirementDeficiency.project_requirement_id.in_(req_ids),
            RequirementDeficiency.resolution_state == 'open',
        )
        if req_ids else None
    )
    open_deficiencies = d_query.count() if d_query is not None else 0

    overall_compliance_rate = round(compliant_count / applicable_count * 100, 1) if applicable_count > 0 else 0.0

    # 3. Working Day SLAs
    now_utc = datetime.now(timezone.utc)
    sla_query = (
        SlaDeadline.query.filter(
            SlaDeadline.project_id.in_(project_ids),
            SlaDeadline.is_resolved == False,
        )
        if project_ids else None
    )
    slas = sla_query.all() if sla_query is not None else []
    total_active_slas = len(slas)
    overdue_slas = sum(1 for s in slas if _is_overdue(s.deadline_date))
    approaching_slas = total_active_slas - overdue_slas

    # 4. Project Domains
    infra_count = sum(1 for p in projects if p.project_kind == 'infrastructure')
    goods_count = sum(1 for p in projects if p.project_kind in ('goods', 'vehicle'))
    fa_count = sum(1 for p in projects if p.project_kind == 'financial_assistance')

    report = reporting_service.get_monitoring_updates_report(user_id=user_id, fiscal_year=fiscal_year)
    analytics = report.get('analytics_summary') or {}
    documentary = report.get('documentary_summary') or {}
    status_summary = report.get('status_summary') or {}

    return {
        'project_portfolio': {
            'total_projects': total_projects,
            'active_projects': active_projects,
            'completed_projects': completed_projects,
            'total_lgus': total_lgus,
        },
        'documentary_compliance': {
            'total_requirements': total_requirements,
            'total_documents': total_requirements,
            'applicable_requirements': applicable_count,
            'applicable_count': applicable_count,
            'not_applicable': not_applicable_count,
            'not_applicable_count': not_applicable_count,
            'compliant_count': compliant_count,
            'returned_count': returned_count,
            'under_review_count': under_review_count,
            'pending_count': pending_count,
            'non_compliant_count': non_compliant_count,
            'open_deficiencies': open_deficiencies,
            'open_documents': open_documents,
            'overall_compliance_rate': overall_compliance_rate,
            'compliance_rate': overall_compliance_rate,
            'compliant': compliant_count,
            'under_review': under_review_count,
            'pending': pending_count,
            'non_compliant': non_compliant_count,
            'waived': sum(1 for r in applicable_reqs if r.status == 'waived'),
        },
        'working_day_slas': {
            'total_active_deadlines': total_active_slas,
            'overdue': overdue_slas,
            'approaching': approaching_slas,
            'approaching_deadline': approaching_slas,
            'on_track': approaching_slas,
        },
        'project_domains': {
            'infrastructure': {'total': infra_count},
            'goods': {'total': goods_count},
            'financial_assistance': {'total': fa_count},
        },
        'metadata': {
            'fiscal_year': fiscal_year,
            'scope_description': 'Provincial',
            'generated_at': now_utc.isoformat(),
        },
        'scope': report.get('scope') or {},
        'applicable_fiscal_year': fiscal_year,
        'total_projects': total_projects,
        'deadlines': {
            'total_active': total_active_slas,
            'overdue': overdue_slas,
            'upcoming': approaching_slas,
        },
        'progress_bands': report.get('progress_summary', {}).get('bands', []),
        'average_progress': analytics.get('average_progress', 0.0),
        'average_health_score': analytics.get('average_health_score', 0.0),
    }


def get_lgu_portfolio_comparison(user_id, lgu_names=None, lgu_ids=None, rank_by=None, limit=10, fiscal_year=None):
    """Compares specific LGUs or ranks LGUs across visible scope using deterministic backend analytics."""
    scope = access_service.get_access_scope(user_id)
    is_field_officer = scope['role'] == 'field_officer'

    assigned_lgu_ids = set()
    if is_field_officer:
        assigned = field_officer_service._assigned_lgu_scope(user_id)
        assigned_lgu_ids = {item['id'] for item in assigned}

    # Fetch visible projects
    p_query = Project.query.join(LguProfile, Project.lgu_id == LguProfile.id)
    p_query = access_service.restrict_project_query(p_query, user_id)
    p_query = apply_project_fiscal_year(p_query, fiscal_year)
    projects = p_query.all()

    # Territorial validation for Field Officers
    if is_field_officer:
        if lgu_names or lgu_ids:
            for name in (lgu_names or []):
                norm = name.strip().lower()
                lgu_obj = LguProfile.query.filter(
                    or_(func.lower(LguProfile.name).contains(norm), func.lower(LguProfile.municipality) == norm)
                ).first()
                if lgu_obj and lgu_obj.id not in assigned_lgu_ids:
                    raise OperationalReportingError(
                        f"I do not have visibility into {lgu_obj.municipality or lgu_obj.name} under your field officer assignment. Field officers may only access and compare records for their assigned LGUs.",
                        403,
                    )
            for lid in (lgu_ids or []):
                if lid not in assigned_lgu_ids:
                    lgu_obj = db.session.get(LguProfile, lid)
                    label = (lgu_obj.municipality or lgu_obj.name) if lgu_obj else f"LGU #{lid}"
                    raise OperationalReportingError(
                        f"I do not have visibility into {label} under your field officer assignment. Field officers may only access and compare records for their assigned LGUs.",
                        403,
                    )

    lgus_query = LguProfile.query
    if is_field_officer:
        lgus_query = lgus_query.filter(LguProfile.id.in_(assigned_lgu_ids))
    all_lgus = lgus_query.all()
    lgu_map = {l.id: l for l in all_lgus}

    p_by_lgu = {}
    for p in projects:
        p_by_lgu.setdefault(p.lgu_id, []).append(p)

    all_p_ids = [p.id for p in projects]
    reqs_by_lgu = {}
    if all_p_ids:
        all_reqs = ProjectRequirement.query.filter(
            ProjectRequirement.project_id.in_(all_p_ids),
            ProjectRequirement.is_active == True,
        ).all()
        req_p_map = {p.id: p.lgu_id for p in projects}
        for r in all_reqs:
            l_id = req_p_map.get(r.project_id)
            if l_id:
                reqs_by_lgu.setdefault(l_id, []).append(r)

    now_utc = datetime.now(timezone.utc)
    slas_by_lgu = {}
    if all_p_ids:
        all_slas = SlaDeadline.query.filter(SlaDeadline.project_id.in_(all_p_ids), SlaDeadline.is_resolved == False).all()
        req_p_map = {p.id: p.lgu_id for p in projects}
        for s in all_slas:
            l_id = req_p_map.get(s.project_id)
            if l_id and _is_overdue(s.deadline_date):
                slas_by_lgu[l_id] = slas_by_lgu.get(l_id, 0) + 1

    candidate_lgu_ids = list(lgu_map.keys())
    if lgu_ids:
        candidate_lgu_ids = [lid for lid in candidate_lgu_ids if lid in lgu_ids]
    if lgu_names:
        lower_names = [n.strip().lower() for n in lgu_names]
        candidate_lgu_ids = [
            lid for lid in candidate_lgu_ids
            if any(ln in (lgu_map[lid].name or '').lower() or ln in (lgu_map[lid].municipality or '').lower() for ln in lower_names)
        ]

    rows = []
    for lid in candidate_lgu_ids:
        lgu = lgu_map[lid]
        lgu_projs = p_by_lgu.get(lid, [])
        lgu_reqs = reqs_by_lgu.get(lid, [])
        total_p = len(lgu_projs)
        if total_p == 0 and not (lgu_names or lgu_ids):
            continue
        active_p = sum(1 for p in lgu_projs if p.overall_status not in ('completed', 'cancelled'))
        comp_p = sum(1 for p in lgu_projs if p.overall_status == 'completed')
        total_r = len(lgu_reqs)
        app_reqs = [r for r in lgu_reqs if getattr(r, 'applicability', 'applicable') == 'applicable']
        na_reqs = [r for r in lgu_reqs if getattr(r, 'applicability', 'applicable') == 'not_applicable']
        applicable_r = len(app_reqs)
        not_applicable_r = len(na_reqs)

        comp_r = sum(
            1 for r in app_reqs
            if r.status == 'compliant' or r.workflow_status in ('approved', 'staff_approved')
        )
        under_rev = sum(
            1 for r in app_reqs
            if (r.workflow_status in ('under_verification', 'submitted') or r.status == 'under_review')
            and r.workflow_status != 'returned_for_revision'
        )
        ret_rev = sum(1 for r in app_reqs if r.workflow_status == 'returned_for_revision')
        pend_r = sum(1 for r in app_reqs if r.workflow_status == 'draft' or r.status == 'pending')
        non_comp = sum(1 for r in app_reqs if r.status == 'non_compliant')

        open_r = sum(_has_open_document_obligation(r) for r in app_reqs)
        overdue_s = slas_by_lgu.get(lid, 0)
        c_rate = round(comp_r / applicable_r * 100, 1) if applicable_r > 0 else 0.0

        health = 85.0 if open_r == 0 else max(10.0, 100.0 - (open_r * 15.0) - (overdue_s * 20.0))

        rows.append({
            'lgu_id': lgu.id,
            'lgu_name': lgu.name,
            'municipality': lgu.municipality,
            'cluster_name': lgu.cluster.name if lgu.cluster else 'Unclustered',
            'total_projects': total_p,
            'project_count': total_p,
            'active_projects': active_p,
            'completed_projects': comp_p,
            'total_requirements': total_r,
            'applicable_requirements': applicable_r,
            'applicable_count': applicable_r,
            'not_applicable': not_applicable_r,
            'not_applicable_count': not_applicable_r,
            'compliant_requirements': comp_r,
            'open_documents': open_r,
            'open_document_count': open_r,
            'under_review': under_rev,
            'returned_for_revision': ret_rev,
            'pending': pend_r,
            'non_compliant': non_comp,
            'open_deficiencies': 0,
            'overdue_slas': overdue_s,
            'compliance_rate': c_rate,
            'document_compliance_rate': c_rate,
            'average_health_score': health,
            'health_score': health,
            'health_label': 'Healthy' if health >= 75.0 else ('At Risk' if health >= 50.0 else 'Critical'),
            'risk_project_count': 1 if (overdue_s > 0 or open_r > 0) else 0,
            'high_risk_project_count': 1 if (overdue_s > 0 and open_r > 0) else 0,
        })

    metric_used = rank_by or 'open_documents'
    if metric_used == 'open_documents':
        sort_fn = lambda r: (-r['open_documents'], -r['total_projects'], r['lgu_name'])
    elif metric_used == 'overdue_slas':
        sort_fn = lambda r: (-r['overdue_slas'], -r['open_documents'], r['lgu_name'])
    elif metric_used == 'compliance_rate':
        sort_fn = lambda r: (-r['compliance_rate'], -r['total_projects'], r['lgu_name'])
    elif metric_used in ('project_count', 'total_projects'):
        sort_fn = lambda r: (-r['total_projects'], -r['open_documents'], r['lgu_name'])
    else:
        sort_fn = lambda r: (-r['open_documents'], -r['total_projects'], r['lgu_name'])

    sorted_rows = sorted(rows, key=sort_fn)
    if limit and limit > 0:
        sorted_rows = sorted_rows[:limit]

    prev_key = None
    prev_rank = 1
    for idx, r in enumerate(sorted_rows, 1):
        k = sort_fn(r)
        if prev_key is not None and k == prev_key:
            r['rank'] = prev_rank
        else:
            r['rank'] = idx
            prev_rank = idx
            prev_key = k

    return {
        'rows': sorted_rows,
        'lgus': sorted_rows,
        'total_lgus_compared': len(sorted_rows),
        'metric_used': metric_used,
        'metric_label': _format_label(metric_used),
        'rank_by': metric_used,
        'scope': 'Assigned LGUs' if is_field_officer else 'Batangas Province',
    }


def get_portfolio_risk_ranking_data(user_id, fiscal_year=None, tier=None, limit=10):
    """COMET operational risk prioritization model ranking projects needing attention."""
    p_query = Project.query.join(LguProfile, Project.lgu_id == LguProfile.id)
    p_query = access_service.restrict_project_query(p_query, user_id)
    p_query = apply_project_fiscal_year(p_query, fiscal_year)
    projects = p_query.all()
    p_ids = [p.id for p in projects]

    now_utc = datetime.now(timezone.utc)
    slas_by_p = {}
    if p_ids:
        all_slas = SlaDeadline.query.filter(SlaDeadline.project_id.in_(p_ids), SlaDeadline.is_resolved == False).all()
        for s in all_slas:
            if _is_overdue(s.deadline_date):
                slas_by_p[s.project_id] = slas_by_p.get(s.project_id, 0) + 1

    returned_by_p = {}
    open_defs_by_p = {}
    if p_ids:
        all_reqs = ProjectRequirement.query.filter(ProjectRequirement.project_id.in_(p_ids)).all()
        req_ids = [r.id for r in all_reqs]
        req_proj_map = {r.id: r.project_id for r in all_reqs}
        for r in all_reqs:
            if r.workflow_status == 'returned_for_revision':
                returned_by_p[r.project_id] = returned_by_p.get(r.project_id, 0) + 1

        if req_ids:
            all_defs = RequirementDeficiency.query.filter(
                RequirementDeficiency.project_requirement_id.in_(req_ids),
                RequirementDeficiency.resolution_state == 'open',
            ).all()
            for d in all_defs:
                p_id = req_proj_map.get(d.project_requirement_id)
                if p_id:
                    open_defs_by_p[p_id] = open_defs_by_p.get(p_id, 0) + 1

    slippage_by_p = {}
    if p_ids:
        all_mprs = MonthlyProgressReport.query.filter(MonthlyProgressReport.project_id.in_(p_ids)).all()
        for m in all_mprs:
            if m.variance_pct is not None and m.variance_pct < 0:
                slippage_by_p[m.project_id] = abs(float(m.variance_pct))

    rows = []
    for p in projects:
        overdue_cnt = slas_by_p.get(p.id, 0)
        returned_cnt = returned_by_p.get(p.id, 0)
        defs_cnt = open_defs_by_p.get(p.id, 0)
        slip = slippage_by_p.get(p.id, 0.0)

        composite_score = (overdue_cnt * 25.0) + (returned_cnt * 15.0) + (defs_cnt * 15.0) + (slip * 1.0)
        if composite_score >= 50.0:
            risk_tier = 'high'
        elif composite_score >= 20.0:
            risk_tier = 'medium'
        else:
            risk_tier = 'low'

        factors = []
        if overdue_cnt > 0:
            factors.append(f"{overdue_cnt} overdue SLA(s)")
        if returned_cnt > 0:
            factors.append(f"{returned_cnt} returned requirement(s)")
        if defs_cnt > 0:
            def_word = "open deficiency" if defs_cnt == 1 else "open deficiencies"
            factors.append(f"{defs_cnt} {def_word}")
        if slip > 0:
            factors.append(f"{slip:.1f}% physical slippage")

        rows.append({
            'project_id': p.id,
            'project_name': p.project_name,
            'project_code': getattr(p, 'project_code', None) or f"PRJ-{p.id}",
            'lgu_name': p.lgu.name if p.lgu else 'Unknown LGU',
            'overdue_slas': overdue_cnt,
            'returned_requirements': returned_cnt,
            'open_deficiencies': defs_cnt,
            'slippage_pct': slip,
            'composite_risk_score': composite_score,
            'risk_score': composite_score,
            'risk_tier': risk_tier,
            'health_score': max(0.0, 100.0 - composite_score),
            'health_label': 'High Risk' if risk_tier == 'high' else ('Medium Risk' if risk_tier == 'medium' else 'Healthy'),
            'physical_completion_pct': float(p.physical_completion_pct or 0.0),
            'contributing_factors': factors,
            'risk_reasons': factors,
            'risk_reason_labels': factors,
            'document_open_count': returned_cnt + defs_cnt,
        })

    rows.sort(key=lambda r: (-r['composite_risk_score'], r['project_id']))

    total_in_scope = len(rows)
    high_cnt = sum(1 for r in rows if r['risk_tier'] == 'high')
    med_cnt = sum(1 for r in rows if r['risk_tier'] == 'medium')
    low_cnt = sum(1 for r in rows if r['risk_tier'] == 'low')

    if tier and tier.lower() != 'all':
        filtered_rows = [r for r in rows if r['risk_tier'] == tier.lower()]
    else:
        filtered_rows = rows

    if limit and limit > 0:
        filtered_rows = filtered_rows[:limit]

    return {
        'rows': filtered_rows,
        'projects': filtered_rows,
        'returned_count': len(filtered_rows),
        'total_risk_projects_in_scope': total_in_scope,
        'tier_filter': tier or 'all',
        'summary': {
            'high_risk_count': high_cnt,
            'medium_risk_count': med_cnt,
            'low_risk_count': low_cnt,
        },
        'advisory_notice': (
            "Advisory Notice: Portfolio risk scores are composite operational heuristics computed from overdue SLA counts, "
            "returned requirements, open deficiencies, and progress slippage. They serve as an internal management guide "
            "for prioritization and do not constitute an official administrative sanction, audit finding, or formal non-compliance determination."
        ),
    }


def get_deficiency_pattern_data(user_id, fiscal_year=None, lgu_id=None, project_id=None, resolution_state=None):
    """Aggregates canonical RequirementDeficiency records across authorized projects."""
    query = (
        db.session.query(RequirementDeficiency)
        .join(ProjectRequirement, RequirementDeficiency.project_requirement_id == ProjectRequirement.id)
        .join(Project, ProjectRequirement.project_id == Project.id)
        .join(LguProfile, Project.lgu_id == LguProfile.id)
    )
    query = access_service.restrict_project_query(query, user_id)
    query = apply_project_fiscal_year(query, fiscal_year)

    if lgu_id is not None:
        query = query.filter(Project.lgu_id == lgu_id)
    if project_id is not None:
        query = query.filter(Project.id == project_id)
    if resolution_state and resolution_state != 'all':
        query = query.filter(RequirementDeficiency.resolution_state == resolution_state)

    deficiencies = query.all()
    total_count = len(deficiencies)

    category_counts = Counter()
    resolution_counts = Counter()
    affected_projects = set()
    affected_requirements = set()
    req_counts = Counter()
    instr_counts = Counter()

    for d in deficiencies:
        cat = getattr(d, 'category', None) or getattr(d, 'deficiency_category', None) or 'other_documented_defect'
        state = d.resolution_state or 'open'
        category_counts[cat] += 1
        resolution_counts[state] += 1
        if d.project_requirement:
            affected_projects.add(d.project_requirement.project_id)
            affected_requirements.add(d.project_requirement_id)
            req_counts[d.project_requirement.requirement_name] += 1
        if d.corrective_instruction:
            instr_counts[d.corrective_instruction] += 1

    top_categories = []
    for cat, cnt in category_counts.most_common():
        opn = sum(
            1 for d in deficiencies
            if (getattr(d, 'category', None) or getattr(d, 'deficiency_category', None)) == cat
            and (d.resolution_state or 'open') == 'open'
        )
        res = sum(
            1 for d in deficiencies
            if (getattr(d, 'category', None) or getattr(d, 'deficiency_category', None)) == cat
            and d.resolution_state == 'resolved'
        )
        wvd = sum(
            1 for d in deficiencies
            if (getattr(d, 'category', None) or getattr(d, 'deficiency_category', None)) == cat
            and d.resolution_state == 'waived'
        )
        top_categories.append({
            'category': cat,
            'category_label': requirement_workflow_service.format_deficiency_category(cat),
            'count': cnt,
            'total_count': cnt,
            'open_count': opn,
            'resolved_count': res,
            'waived_count': wvd,
        })

    top_requirements = [
        {'requirement_name': name, 'count': cnt}
        for name, cnt in req_counts.most_common(10)
    ]
    common_instructions = [
        {'instruction': instr, 'count': cnt}
        for instr, cnt in instr_counts.most_common(5)
    ]

    open_c = resolution_counts.get('open', 0)
    res_c = resolution_counts.get('resolved', 0)
    wvd_c = resolution_counts.get('waived', 0)
    res_rate = round(res_c / total_count * 100, 1) if total_count > 0 else 0.0

    return {
        'total_deficiencies': total_count,
        'affected_project_count': len(affected_projects),
        'affected_requirement_count': len(affected_requirements),
        'resolution_counts': {
            'total_deficiencies': total_count,
            'open': open_c,
            'resolved': res_c,
            'waived': wvd_c,
            'resolution_rate': res_rate,
        },
        'resolution_breakdown': {
            'open': open_c,
            'resolved': res_c,
            'waived': wvd_c,
        },
        'top_deficiency_categories': top_categories,
        'top_categories': top_categories,
        'top_deficiency_requirements': top_requirements,
        'common_corrective_instructions': common_instructions,
        'applicable_fiscal_year': fiscal_year,
        'filter_lgu_id': lgu_id,
        'filter_project_id': project_id,
        'filter_resolution_state': resolution_state,
        'metadata': {
            'scope_description': 'Batangas Province',
            'fiscal_year': fiscal_year,
        }
    }


def get_recent_operational_activity_data(user_id, days=30, fiscal_year=None, lgu_id=None, project_id=None):
    """Aggregates logged operational event transitions across workflow, intake, and deadline resolution."""
    days_bounded = max(1, min(180, int(days or 30)))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_bounded)
    cutoff_naive = cutoff.replace(tzinfo=None)

    t_query = (
        RequirementWorkflowTransition.query
        .join(ProjectRequirement, RequirementWorkflowTransition.project_requirement_id == ProjectRequirement.id)
        .join(Project, ProjectRequirement.project_id == Project.id)
        .filter(or_(RequirementWorkflowTransition.created_at >= cutoff, RequirementWorkflowTransition.created_at >= cutoff_naive))
    )
    t_query = access_service.restrict_project_query(t_query, user_id)
    t_query = apply_project_fiscal_year(t_query, fiscal_year)
    if lgu_id is not None:
        t_query = t_query.filter(Project.lgu_id == lgu_id)
    if project_id is not None:
        t_query = t_query.filter(Project.id == project_id)

    transitions = t_query.order_by(RequirementWorkflowTransition.created_at.desc()).limit(100).all()

    s_query = (
        Submission.query
        .join(ProjectRequirement, Submission.project_requirement_id == ProjectRequirement.id)
        .join(Project, ProjectRequirement.project_id == Project.id)
        .filter(or_(Submission.created_at >= cutoff, Submission.created_at >= cutoff_naive))
    )
    s_query = access_service.restrict_project_query(s_query, user_id)
    s_query = apply_project_fiscal_year(s_query, fiscal_year)
    if lgu_id is not None:
        s_query = s_query.filter(Project.lgu_id == lgu_id)
    if project_id is not None:
        s_query = s_query.filter(Project.id == project_id)
    submissions_count = s_query.count()

    m_query = (
        MonthlyProgressReport.query
        .join(Project, MonthlyProgressReport.project_id == Project.id)
        .filter(or_(MonthlyProgressReport.created_at >= cutoff, MonthlyProgressReport.created_at >= cutoff_naive))
    )
    m_query = access_service.restrict_project_query(m_query, user_id)
    m_query = apply_project_fiscal_year(m_query, fiscal_year)
    if lgu_id is not None:
        m_query = m_query.filter(Project.lgu_id == lgu_id)
    if project_id is not None:
        m_query = m_query.filter(Project.id == project_id)
    monthly_reports_count = m_query.count()

    activities = []
    for t in transitions:
        p = t.project_requirement.project if t.project_requirement else None
        actor_name = t.actor.full_name if (hasattr(t, 'actor') and t.actor) else "COMET Evaluator"
        action_label = _format_workflow_action_label(t.action)
        status_label = _format_requirement_status_label(t.to_status) if t.to_status else ''
        detail_text = t.reason if (t.reason and str(t.reason).strip()) else status_label
        desc = f"Evaluator {action_label} for {t.project_requirement.requirement_name if t.project_requirement else 'Requirement'}: {detail_text}"
        activities.append({
            'event_type': 'workflow_transition',
            'actor_name': actor_name,
            'description': desc,
            'project_name': p.project_name if p else 'Project',
            'requirement_name': t.project_requirement.requirement_name if t.project_requirement else 'Requirement',
            'action': t.action,
            'action_label': action_label,
            'from_status': t.from_status,
            'to_status': t.to_status,
            'created_at': t.created_at.isoformat(),
            'timestamp': t.created_at.isoformat(),
        })

    evaluations_count = len(transitions)
    total_events = evaluations_count + submissions_count + monthly_reports_count

    return {
        'summary': {
            'total_events': total_events,
            'breakdown': {
                'evaluations': evaluations_count,
                'submissions': submissions_count,
                'monthly_reports': monthly_reports_count,
                'sla_deadlines': 0,
                'monitoring': 0,
                'deficiencies': 0,
            },
        },
        'metadata': {
            'days': days_bounded,
            'since': cutoff.isoformat(),
        },
        'activities': activities,
        'recent_samples': activities[:8],
        'period_days': days_bounded,
        'cutoff_date': cutoff.date().isoformat(),
        'total_transitions': evaluations_count,
        'submissions_count': submissions_count,
        'monthly_reports_count': monthly_reports_count,
        'interpretation_note': (
            "Activity volume reflects workflow actions and logged transitions during the window. "
            "Activity volume does not indicate project performance improvement or degradation."
        ),
    }
