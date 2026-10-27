import os
from datetime import datetime, timezone
from flask import current_app, render_template
from sqlalchemy import or_

from app.extensions import db
from app.models.lgu import LguCluster, LguProfile
from app.models.program import Program
from app.models.project import ProjectRequirement
from app.services import reporting_service
from app.services.reporting_visuals import status_pie_svg, documentary_breakdown, STATUS_COLORS


def _chunk_pairs(items):
    pairs = []
    for i in range(0, len(items), 2):
        pairs.append((items[i], items[i + 1] if i + 1 < len(items) else None))
    return pairs


def _filter_by_search(rows, search_term, search_keys):
    if not search_term:
        return rows
    term = search_term.strip().casefold()
    filtered = []
    for row in rows:
        match = False
        for key in search_keys:
            val = row.get(key)
            if val and term in str(val).casefold():
                match = True
                break
        if match:
            filtered.append(row)
    return filtered


def generate_reports_analytics_pdf(
    user_id,
    *,
    tabs=None,
    scope='filtered',
    risk_detail='executive',
    orientation='landscape',
    record_detail='summary',
    include_appendix=None,
    filters=None,
):
    """
    Generate an official PDF export of the Reports & Analytics dashboard.
    
    :param user_id: Authenticated user ID.
    :param tabs: List of tabs to include: ['analytics', 'monitoring', 'documents', 'risk'].
    :param scope: 'filtered' (respect current filters) or 'all' (unfiltered province-wide).
    :param risk_detail: 'executive' (top 10 cards + index table) or 'comprehensive' (all cards).
    :param orientation: 'landscape' (default) or 'portrait'.
    :param filters: Dict with keys: fiscal_year, program_id, cluster_id, status, search.
    :return: tuple of (pdf_bytes, filename)
    """
    filters = filters or {}
    raw_tabs = tabs or ['monitoring', 'documents']
    normalized_tabs = []
    for tab in raw_tabs:
        if tab in ('monitoring', 'documents'):
            if tab not in normalized_tabs:
                normalized_tabs.append(tab)
        elif tab == 'analytics':
            if 'monitoring' not in normalized_tabs:
                normalized_tabs.append('monitoring')
            if 'documents' not in normalized_tabs:
                normalized_tabs.append('documents')
        elif tab == 'risk':
            if 'documents' not in normalized_tabs:
                normalized_tabs.append('documents')
    included_tabs = set(normalized_tabs)

    fiscal_year = filters.get('fiscal_year')
    search_query = str(filters.get('search') or '').strip() if scope == 'filtered' else ''

    if scope == 'all':
        report_data = reporting_service.get_monitoring_updates_report(
            user_id=user_id,
            fiscal_year=fiscal_year,
        )
        deep_dive_data = reporting_service.get_deep_dive_analytics(
            user_id=user_id,
            fiscal_year=fiscal_year,
        )
        scope_label = f"All authorized projects · FY {fiscal_year or 'All'}"
    else:
        cluster_id = filters.get('cluster_id')
        program_id = filters.get('program_id')
        lgu_id = filters.get('lgu_id')
        status = filters.get('status')
        report_data = reporting_service.get_monitoring_updates_report(
            user_id=user_id,
            fiscal_year=fiscal_year,
            program_id=program_id,
            cluster_id=cluster_id,
            lgu_id=lgu_id,
            status=status,
            selected_project_ids=filters.get('project_ids'),
            search=search_query if filters.get('project_ids') is None else None,
        )
        deep_dive_data = reporting_service.get_deep_dive_analytics(
            user_id=user_id,
            fiscal_year=fiscal_year,
            program_id=program_id,
            cluster_id=cluster_id,
            lgu_id=lgu_id,
            status=status,
            selected_project_ids=filters.get('project_ids'),
            search=search_query if filters.get('project_ids') is None else None,
        )
        active_parts = []
        if lgu_id:
            try:
                lgu = db.session.get(LguProfile, int(lgu_id))
                if lgu and lgu.name:
                    active_parts.append(lgu.name)
                else:
                    active_parts.append(f"LGU {lgu_id}")
            except (ValueError, TypeError):
                active_parts.append(str(lgu_id))
        if cluster_id:
            try:
                cluster = db.session.get(LguCluster, int(cluster_id))
                if cluster and cluster.name:
                    active_parts.append(cluster.name)
                else:
                    active_parts.append(f"Cluster {cluster_id}")
            except (ValueError, TypeError):
                active_parts.append(str(cluster_id))
        if program_id:
            try:
                program = db.session.get(Program, int(program_id))
                if program and (program.code or program.name):
                    active_parts.append(program.code or program.name)
                else:
                    active_parts.append(f"Program {program_id}")
            except (ValueError, TypeError):
                active_parts.append(str(program_id))
        if fiscal_year:
            active_parts.append(f"FY {fiscal_year}")
        if status:
            active_parts.append(f"Status: {status.replace('_', ' ').title()}")
        if search_query:
            active_parts.append(f'Search: "{search_query}"')
        scope_label = f"Filtered ({', '.join(active_parts) if active_parts else 'Active View'})"

    # All aggregates and detail rows use the same authorized project cohort.
    project_rows = report_data.get('project_rows', [])
    risk_rows = report_data.get('risk_rows', [])
    lgu_analytics = report_data.get('lgu_analytics', [])
    compliance_by_program = deep_dive_data.get('compliance_by_program', [])
    return_patterns = deep_dive_data.get('return_patterns', {})

    document_rows = [p for p in project_rows if (p.get('documentary_summary', {}).get('total', 0) > 0)]

    not_applicable_requirements = []
    waived_requirements = []
    project_lookup = {p.get('project_id') or p.get('id'): p for p in project_rows if (p.get('project_id') or p.get('id'))}
    project_ids = list(project_lookup.keys())
    if project_ids:
        na_rows = (
            ProjectRequirement.query
            .filter(
                ProjectRequirement.project_id.in_(project_ids),
                ProjectRequirement.is_active == True,
                ProjectRequirement.applicability == 'not_applicable',
            )
            .order_by(ProjectRequirement.updated_at.desc(), ProjectRequirement.id.asc())
            .all()
        )
        for r in na_rows:
            proj_meta = project_lookup.get(r.project_id, {})
            not_applicable_requirements.append({
                'id': r.id,
                'requirement_name': r.requirement_name,
                'project_id': r.project_id,
                'project_name': proj_meta.get('project_name') or (r.project.project_name if r.project else None),
                'lgu_name': proj_meta.get('lgu_name') or (r.project.lgu.name if (r.project and r.project.lgu) else 'Unassigned'),
                'applicability': r.applicability,
                'applicability_label': 'Not Applicable',
                'applicability_reason': r.applicability_reason,
                'status': r.status,
            })

        w_rows = (
            ProjectRequirement.query
            .filter(
                ProjectRequirement.project_id.in_(project_ids),
                ProjectRequirement.is_active == True,
                or_(
                    ProjectRequirement.applicability == 'waived',
                    ProjectRequirement.status == 'waived',
                ),
            )
            .order_by(ProjectRequirement.updated_at.desc(), ProjectRequirement.id.asc())
            .all()
        )
        for r in w_rows:
            proj_meta = project_lookup.get(r.project_id, {})
            waiver_reason = r.waived_reason or r.applicability_reason or 'No justification provided'
            waived_requirements.append({
                'id': r.id,
                'requirement_name': r.requirement_name,
                'project_id': r.project_id,
                'project_name': proj_meta.get('project_name') or (r.project.project_name if r.project else None),
                'lgu_name': proj_meta.get('lgu_name') or (r.project.lgu.name if (r.project and r.project.lgu) else 'Unassigned'),
                'compliance_status': r.status or 'waived',
                'waived_reason': waiver_reason,
            })

    # Shape program_cluster_rows
    program_cluster_rows = []
    for py in report_data.get('program_years', []):
        for c in py.get('clusters', []):
            statuses_raw = c.get('statuses')
            if isinstance(statuses_raw, dict):
                statuses_map = statuses_raw
            elif isinstance(statuses_raw, list):
                statuses_map = {s.get('key'): s.get('count', 0) for s in statuses_raw if isinstance(s, dict)}
            else:
                statuses_map = {}
            program_cluster_rows.append({
                'program_name': py.get('program_code') or py.get('program_name') or 'Program',
                'fiscal_year': py.get('fiscal_year'),
                'cluster_name': c.get('cluster_name'),
                'total': c.get('total', 0),
                'total_allocation': c.get('total_allocation'),
                'allocation_recorded_count': c.get('allocation_recorded_count', 0),
                'allocation_missing_count': c.get('allocation_missing_count', 0),
                'allocation_complete': c.get('allocation_complete', False),
                'statuses': statuses_map,
            })
    # Risk detail partitioning
    if risk_detail == 'executive':
        top_risk_cards = risk_rows[:10]
        remaining_risk_rows = risk_rows[10:]
    else:
        top_risk_cards = risk_rows
        remaining_risk_rows = []

    risk_card_pairs = _chunk_pairs(top_risk_cards)

    now = datetime.now(timezone.utc)
    generated_at_display = now.strftime('%B %d, %Y at %I:%M %p UTC')
    date_slug = now.strftime('%Y%m%d')
    is_appendix_included = (include_appendix is True) or (record_detail == 'full')

    context = {
        'included_tabs': included_tabs,
        'scope': scope,
        'scope_label': scope_label,
        'risk_detail': risk_detail,
        'orientation': orientation,
        'record_detail': record_detail,
        'include_appendix': is_appendix_included,
        'generated_at': generated_at_display,
        'fiscal_year': fiscal_year,
        'analytics': report_data.get('analytics_summary', {}),
        'status_summary': report_data.get('status_summary', {}),
        'progress_bands': report_data.get('progress_summary', {}).get('bands', []),
        'cluster_analytics': report_data.get('cluster_analytics', []),
        'program_analytics': report_data.get('program_analytics', []),
        'lgu_analytics': lgu_analytics,
        'program_cluster_rows': program_cluster_rows,
        'document_rows': document_rows,
        'project_rows': project_rows,
        'documentary_summary': report_data.get('documentary_summary', {}),
        'not_applicable_requirements': not_applicable_requirements,
        'waived_requirements': waived_requirements,
        'risk_card_pairs': risk_card_pairs,
        'total_risk_count': len(risk_rows),
        'top_risk_cards_count': len(top_risk_cards),
        'remaining_risk_rows': remaining_risk_rows,
        # Deep Dive Analytics (Parity with Interactive Dashboard Waves 1 - 2.3)
        'deep_dive': deep_dive_data,
        'project_health': deep_dive_data.get('project_health', {}),
        'phase_distribution': deep_dive_data.get('phase_distribution', {}),
        'slippage_distribution': deep_dive_data.get('slippage_distribution', {}),
        'qaar_defects': deep_dive_data.get('qaar_defects', {}),
        'non_infra_delivery': deep_dive_data.get('non_infra_delivery', {}),
        'closeout_readiness': deep_dive_data.get('closeout_readiness', {}),
        'regional_handoff': deep_dive_data.get('regional_handoff', {}),
        'workflow_pipeline': deep_dive_data.get('workflow_pipeline', {}),
        'workflow_activity': deep_dive_data.get('workflow_activity', {}),
        'return_patterns': return_patterns,
        'deficiency_root_causes': deep_dive_data.get('deficiency_root_causes', []),
        'compliance_by_program': compliance_by_program,
    }

    context['status_pie_svg'] = status_pie_svg(context.get('status_summary', {}).get('items', []))
    context['status_colors'] = STATUS_COLORS
    context['documentary_chart'] = documentary_breakdown(context.get('documentary_summary', {}))
    html = render_template('pdf/reports_analytics.html', **context)

    try:
        from weasyprint import HTML
        from app.services.pdf_service import safe_weasyprint_url_fetcher
        pdf_bytes = HTML(string=html, base_url=current_app.root_path, url_fetcher=safe_weasyprint_url_fetcher).write_pdf()
    except (ImportError, OSError) as exc:
        current_app.logger.error('WeasyPrint rendering unavailable or failed: %s', exc)
        raise RuntimeError(f'PDF generation failed because WeasyPrint is unavailable or encountered an error: {exc}') from exc

    filename = f"Reports_Analytics_{date_slug}_{risk_detail}_{orientation}.pdf"
    return pdf_bytes, filename
