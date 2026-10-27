from base64 import b64encode
from functools import lru_cache
from html import escape
from pathlib import Path

from app.services import qaar_calculation_service, qaar_reference


VALID_OUTPUT_TYPES = {
    'report_summary',
    'project_management',
    'quality_of_works',
    'health_and_safety',
    'findings_recommendations',
    'aide_memoire',
    'notice_of_defects',
    'full_package',
}

OUTPUT_TYPE_LABELS = {
    'report_summary': 'QAAR Report Summary',
    'project_management': 'QAAR Project Management',
    'quality_of_works': 'QAAR Quality of Works',
    'health_and_safety': 'QAAR Health and Safety',
    'findings_recommendations': 'QAAR Findings and Recommendations',
    'aide_memoire': 'Aide Memoire',
    'notice_of_defects': 'Notice of Defects / Deficiencies',
    'full_package': 'QAAR Package',
}

REPORT_SUMMARY_KEYS = [
    'office_address',
    'region',
    'program_name',
    'province',
    'funded_year',
    'city_municipality',
    'implementing_unit',
    'barangay',
    'monitoring_office',
    'project_id_text',
    'project_title',
    'national_subsidy',
    'project_location',
    'project_description',
    'date_of_inspection_assessment',
    'actual_project_status',
    'planned_accomplishment_pct',
    'actual_accomplishment_pct',
    'actual_completion_date',
    'percent_slippage',
    'date_started',
    'target_completion_date',
    'project_duration',
    'time_elapsed',
    'lgu_counterpart',
    'liquidation',
    'total_project_cost',
    'balance_of_contract',
    'contractor_name',
    'contractor_address',
    'owner_name',
    'owner_contact_number',
    'pcab_license',
    'contract_amount',
]

DILG_LOGO_PATH = Path(__file__).resolve().parents[1] / 'static' / 'images' / 'dilg-logo.png'

QAAR_WIDE_TABLE_COLUMN_WIDTHS = {
    'quality_of_works': {
        'Item No.': '4.5%',
        'Unit': '5%',
        'Description': '21%',
        'Code No.': '6%',
        'Type of Defects/Damage': '11.5%',
        'Location/ Landmark': '9%',
        'Quality Issue': '8%',
        'Weight': '5%',
        'Recommendation': '14%',
        'Degree of Defect': '5.5%',
        'Rating per Degree of Defect': '5.5%',
        'Total Rating': '5%',
    },
    'findings_recommendations': {
        'Code No.': '5%',
        'Type of Defects/Damage': '16%',
        'Location/ Landmark': '10%',
        'Quality Issue': '10%',
        'Recommendation': '24%',
        'Degree of Defect': '8%',
        'Rating per Degree of Defect': '8%',
        'Total Rating': '7%',
        'TIMELINES': '6%',
        'REMARKS': '6%',
    },
}


def build_qaar_output(inspection, output_type, snapshot):
    if output_type not in VALID_OUTPUT_TYPES:
        raise ValueError(f'Invalid output_type: {output_type}')
    catalog = qaar_reference.get_catalog()
    title = output_title(inspection, output_type)
    parity = build_parity_metadata(output_type, catalog)
    sections = build_sections(inspection, output_type, snapshot, catalog)
    structured_output = {
        'output_type': output_type,
        'title': title,
        'reference': catalog['reference'],
        'parity': parity,
        'document_context': build_document_context(inspection, snapshot),
        'sections': sections,
    }
    return {
        'title': title,
        'body_text': render_text(structured_output),
        'pdf_bytes': render_pdf_bytes(structured_output),
        'filename': output_filename(inspection, output_type),
        'structured_output': structured_output,
    }


def output_title(inspection, output_type):
    project_name = inspection.project.project_name if inspection.project else f'Inspection #{inspection.id}'
    return f'{OUTPUT_TYPE_LABELS.get(output_type, output_type)} - {project_name}'


def output_filename(inspection, output_type):
    project_name = inspection.project.project_name if inspection.project else f'inspection-{inspection.id}'
    safe_project = '-'.join(str(project_name).strip().split())[:80] or f'inspection-{inspection.id}'
    return f'{OUTPUT_TYPE_LABELS.get(output_type, output_type)} - {safe_project}.pdf'


def build_parity_metadata(output_type, catalog):
    return {
        'reference_version': catalog['reference']['version'],
        'source_workbook': catalog['reference']['source_workbook'],
        'output_type': output_type,
        'pdf_evidence': {
            'path': r'C:\Users\marka\Downloads\QAAR TOOL\Feedback-Submissions\REGION VIII\NORTHERN SAMAR',
            'sample_count': 44,
            'extraction_note': 'Sample PDFs are scanned/image-only; generated-output parity must be checked visually.',
        },
        'formula_registry': qaar_calculation_service.get_formula_registry(),
        'status': 'structured_from_qaar_reference',
    }


def build_document_context(inspection, snapshot):
    summary = snapshot.get('report_summary') or {}
    project = inspection.project
    lgu = project.lgu if project else None
    project_budget = project.budget_amount if project and project.budget_amount is not None else ''
    return {
        'project_id': summary.get('project_id_text') or (project.source_project_code if project else ''),
        'project_title': summary.get('project_title') or (project.project_name if project else ''),
        'project_location': summary.get('project_location') or (lgu.municipality if lgu else ''),
        'program_name': summary.get('program_name') or (project.program.name if project and project.program else ''),
        'funded_year': summary.get('funded_year') or (project.fiscal_year if project else ''),
        'allocation': summary.get('total_project_cost') or summary.get('national_subsidy') or format_value(project_budget),
        'inspection_date': summary.get('date_of_inspection_assessment') or (inspection.inspection_date.isoformat() if inspection.inspection_date else ''),
        'lgu_name': lgu.name if lgu else '',
        'lgu_municipality': lgu.municipality if lgu else '',
        'lgu_province': summary.get('province') or (lgu.province if lgu else ''),
        'mayor_name': lgu.mayor_name if lgu else '',
        'region': summary.get('region') or 'CALABARZON',
        'prepared_by_name': summary.get('prepared_by_name') or '',
        'prepared_by_position': summary.get('prepared_by_position') or '',
    }


def build_sections(inspection, output_type, snapshot, catalog):
    sections = [_header_section(inspection, snapshot, catalog)]
    if output_type in {'report_summary', 'full_package'}:
        sections.append(_report_summary_section(snapshot, catalog))
        sections.append(_assessment_rating_section(snapshot))
        sections.append(_item_description_section(snapshot))
    if output_type == 'aide_memoire':
        sections.append(_report_summary_section(snapshot, catalog))
    if output_type in {'project_management', 'aide_memoire', 'full_package'}:
        sections.append(_project_management_section(snapshot))
    if output_type in {'health_and_safety', 'aide_memoire', 'full_package'}:
        sections.append(_health_safety_section(snapshot))
    if output_type in {'quality_of_works', 'findings_recommendations', 'aide_memoire', 'notice_of_defects', 'full_package'}:
        sections.append(_quality_of_works_section(snapshot, catalog))
        sections.append(_findings_recommendations_section(snapshot))
    if output_type == 'aide_memoire':
        sections.append(_aide_memoire_section())
    if output_type == 'notice_of_defects':
        sections.append(_notice_of_defects_section(snapshot))
    return sections


def render_text(structured_output):
    lines = [
        structured_output['title'],
        (
            'QAAR tool reference: '
            f"{structured_output['reference']['version']} "
            f"({structured_output['reference']['source_workbook']})"
        ),
        f"PARITY STATUS: {structured_output['parity']['status']}",
    ]
    for section in structured_output['sections']:
        lines.extend(['', section['title']])
        if section.get('summary'):
            for item in section['summary']:
                lines.append(f"{item['label']} {format_value(item.get('value'))}")
        if section.get('columns'):
            lines.append(' | '.join(section['columns']))
        for row in section.get('rows') or []:
            lines.append(' | '.join(format_value(row.get(column)) for column in section.get('columns') or row.keys()))
        if section.get('notes'):
            for note in section['notes']:
                lines.append(note)
    return '\n'.join(lines)


def render_pdf_bytes(structured_output):
    from weasyprint import HTML
    from app.services.pdf_service import safe_weasyprint_url_fetcher

    html = render_html(structured_output)
    return HTML(string=html, url_fetcher=safe_weasyprint_url_fetcher).write_pdf()


def render_html(structured_output):
    if structured_output['output_type'] == 'aide_memoire':
        return render_aide_memoire_html(structured_output)
    if structured_output['output_type'] == 'notice_of_defects':
        return render_notice_html(structured_output)
    if structured_output['output_type'] == 'full_package':
        return render_full_package_html(structured_output)
    title = escape(structured_output['title'])
    reference = structured_output['reference']
    parity = structured_output['parity']
    section_html = '\n'.join(_section_html(section) for section in structured_output['sections'])
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: A4; margin: 18mm 14mm; }}
    body {{ font-family: Arial, sans-serif; color: #111827; font-size: 10.5px; line-height: 1.35; }}
    h1 {{ font-size: 18px; margin: 0 0 6px; text-align: center; }}
    {_official_header_css()}
    h2 {{ font-size: 13px; margin: 18px 0 8px; padding: 5px 7px; background: #e5e7eb; border: 1px solid #9ca3af; }}
    .meta {{ text-align: center; font-size: 9px; color: #374151; margin-bottom: 12px; }}
    .parity {{ font-size: 8.5px; color: #4b5563; border: 1px solid #d1d5db; padding: 6px; margin-bottom: 12px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 5px 0 10px; page-break-inside: auto; }}
    tr {{ page-break-inside: avoid; page-break-after: auto; }}
    th, td {{ border: 1px solid #9ca3af; padding: 4px 5px; vertical-align: top; }}
    th {{ background: #f3f4f6; font-weight: 700; text-align: left; }}
    .summary th {{ width: 30%; }}
    .note {{ font-size: 8.5px; color: #4b5563; margin: 4px 0; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <div class="meta">QAAR tool reference: {escape(str(reference.get('version') or ''))} ({escape(str(reference.get('source_workbook') or ''))})</div>
  <div class="parity">
    <strong>Parity status:</strong> {escape(str(parity.get('status') or ''))}<br>
    <strong>PDF evidence:</strong> {escape(str((parity.get('pdf_evidence') or {}).get('path') or ''))}<br>
    <strong>Evidence note:</strong> {escape(str((parity.get('pdf_evidence') or {}).get('extraction_note') or ''))}
  </div>
  {section_html}
</body>
</html>"""


def render_full_package_html(structured_output):
    reference = structured_output['reference']
    section_html = '\n'.join(
        _section_html(section, show_notes=False)
        for section in structured_output['sections']
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: A4; margin: 16mm 14mm 14mm; }}
    body {{ font-family: Arial, sans-serif; color: #111; font-size: 10px; line-height: 1.28; margin: 0; }}
    {_official_header_css()}
    .main-title {{ text-align: center; font-size: 15px; font-weight: 800; margin: 18px 0 14px; }}
    .package-meta {{ text-align: center; font-size: 9px; color: #374151; margin: -6px 0 12px; }}
    .section-block {{ margin: 0 0 12px; page-break-inside: auto; }}
    .section-block h2 {{ background: #93c47d; border: 1px solid #222; color: #111; font-size: 11px; font-weight: 800; margin: 12px 0 0; padding: 4px 6px; text-transform: uppercase; }}
    table {{ width: 100%; max-width: 100%; border-collapse: collapse; margin: 0 0 8px; page-break-inside: auto; }}
    tr {{ page-break-inside: avoid; page-break-after: auto; }}
    th, td {{ border: 1px solid #222; padding: 4px 5px; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }}
    th {{ background: #d9ead3; font-weight: 800; text-align: left; }}
    td {{ background: #fff; }}
    .summary th {{ width: 30%; }}
    .section-assessment-rating tbody tr:nth-child(3n) td,
    .section-item-description thead th,
    .section-project-management thead th,
    .section-health-and-safety thead th,
    .section-quality-of-works thead th,
    .section-findings-recommendations thead th {{ background: #d9ead3; }}
    .section-assessment-rating td:nth-child(2),
    .section-assessment-rating td:nth-child(3) {{ background: #fce4d6; font-weight: 700; text-align: center; }}
    .section-item-description td:nth-child(7),
    .section-item-description td:nth-child(8) {{ background: #fce4d6; }}
    .section-quality-of-works table,
    .section-findings-recommendations table {{ table-layout: fixed; font-size: 7.2px; line-height: 1.08; }}
    .section-quality-of-works th,
    .section-quality-of-works td,
    .section-findings-recommendations th,
    .section-findings-recommendations td {{ padding: 2px 2px; }}
    .footer {{ position: fixed; bottom: 5mm; left: 14mm; right: 14mm; font-size: 8px; color: #444; display: flex; justify-content: space-between; }}
  </style>
  <title>Quality Assurance and Assessment Report</title>
</head>
<body>
  {_official_header_html('QUALITY ASSURANCE AND ASSESSMENT REPORT', structured_output.get('document_context') or {})}
  <div class="package-meta">QAAR reference: {escape(str(reference.get('version') or ''))}</div>
  {section_html}
  <div class="footer"><span>Generated by COMET</span><span>QAAR {escape(str(reference.get('version') or ''))}</span></div>
</body>
</html>"""


def render_aide_memoire_html(structured_output):
    context = structured_output.get('document_context') or {}
    project_management_rows = _rows_from_section(structured_output, 'project_management')
    quality_rows = _rows_from_section(structured_output, 'quality_of_works')
    findings_rows = _rows_from_section(structured_output, 'findings_recommendations') or quality_rows
    health_safety_rows = _rows_from_section(structured_output, 'health_and_safety')
    report_summary = _summary_from_section(structured_output, 'report_summary')
    title_block = _official_header_html('AIDE MEMOIRE', context, annex='Annex W - Aide Memoire')
    project_box = _project_summary_box_html(context)
    findings_table = _memo_findings_table_html(
        project_management_rows,
        findings_rows,
        health_safety_rows,
        report_summary,
    )
    signature_block = _signature_block_html(context)
    return _document_html(
        'Aide Memoire',
        f"""
        {title_block}
        <table class="memo-lines">
          <tr><th>LGU:</th><td>{escape(format_value(context.get('lgu_name') or context.get('lgu_municipality')))}</td></tr>
          <tr><th>DATE OF MONITORING:</th><td>{escape(format_value(context.get('inspection_date')))}</td></tr>
          <tr><th>DATE OF AIDE MEMOIRE:</th><td>{escape(format_value(context.get('inspection_date')))}</td></tr>
        </table>
        <h3 class="center-title">SUMMARY OF FINDINGS/OBSERVATIONS/AGREEMENTS</h3>
        {project_box}
        {findings_table}
        <p class="small-italic">(Use additional sheet if necessary)</p>
        <div class="page-break"></div>
        {signature_block}
        """,
        mode='memo',
    )


def render_notice_html(structured_output):
    context = structured_output.get('document_context') or {}
    rows = _rows_from_section(structured_output, 'notice_of_defects') or _rows_from_section(structured_output, 'findings_recommendations')
    title_block = _official_header_html('NOTICE OF DEFECTS / DEFICIENCIES', context)
    project_box = _project_summary_box_html(context)
    table = _defects_table_html(rows)
    return _document_html(
        'Notice of Defects',
        f"""
        {title_block}
        <p class="notice-copy">
          The following defects/deficiencies were noted during monitoring. The LGU and contractor are advised to act on the corresponding recommendations within the indicated timelines.
        </p>
        {project_box}
        {table}
        {_signature_block_html(context, include_lgu=False)}
        """,
        mode='memo',
    )


def _document_html(title, body_html, mode='standard'):
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: A4; margin: 16mm 14mm 14mm; }}
    body {{ font-family: Arial, sans-serif; color: #111; font-size: 10.5px; line-height: 1.28; }}
    .doc {{ width: 100%; }}
    .top-annex {{ position: absolute; right: 14mm; top: 9mm; color: #c4c4c4; font-size: 10px; text-align: right; }}
    {_official_header_css()}
    .main-title {{ text-align: center; font-size: 15px; font-weight: 800; margin: 22px 0 18px; }}
    .center-title {{ text-align: center; font-size: 12px; font-weight: 800; margin: 18px 0 12px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #222; padding: 4px 5px; vertical-align: top; }}
    th {{ font-weight: 800; }}
    .memo-lines {{ margin: 0 0 16px; }}
    .memo-lines th {{ width: 25%; text-align: left; border-left: 0; border-right: 0; padding: 2px 4px; font-size: 12px; }}
    .memo-lines td {{ border-left: 0; border-right: 0; padding: 2px 4px; font-weight: 700; font-size: 12px; }}
    .project-box th {{ width: 24%; text-align: left; border-right: 0; font-weight: 700; }}
    .project-box td {{ border-left: 0; font-weight: 700; }}
    .findings th {{ text-align: center; font-size: 10px; }}
    .findings td {{ height: 34px; }}
    .category-row td {{ background: #eef6b9; font-weight: 800; text-transform: uppercase; height: auto; padding: 2px 4px; }}
    .small-italic {{ font-style: italic; font-size: 10px; margin-top: 12px; }}
    .notice-copy {{ margin: 14px 0; text-align: justify; }}
    .commitment {{ margin: 0 0 12px; font-size: 11px; }}
    .signature-table {{ margin-top: 12px; }}
    .signature-table th {{ text-align: center; }}
    .signature-table td {{ height: 24px; text-align: center; }}
    .signature-line {{ margin-top: 28px; width: 260px; text-align: center; }}
    .signature-line .line {{ border-top: 1px solid #222; padding-top: 3px; font-weight: 700; }}
    .page-break {{ page-break-before: always; }}
    .footer {{ position: fixed; bottom: 5mm; left: 14mm; right: 14mm; font-size: 8px; color: #444; display: flex; justify-content: space-between; }}
  </style>
  <title>{escape(title)}</title>
</head>
<body class="{escape(mode)}">
  <div class="doc">
    {body_html}
  </div>
  <div class="footer"><span>cc: DILG-MLGOO</span><span>Generated by COMET from QAAR v2.10a structured data</span></div>
</body>
</html>"""


def _official_header_html(title, context, annex=None):
    annex_html = f'<div class="top-annex">{escape(annex)}<br>{escape(format_value(context.get("program_name")))}</div>' if annex else ''
    logo_uri = _dilg_logo_data_uri()
    logo_html = (
        f'<img class="dilg-logo" src="{escape(logo_uri)}" alt="DILG logo">'
        if logo_uri
        else '<div class="dilg-logo-fallback">DILG</div>'
    )
    return f"""
    {annex_html}
    <div class="official-letterhead">
      {logo_html}
      <div class="agency-lines">
        <div>Republic of the Philippines</div>
        <div class="department">Department of the Interior and Local Government</div>
        <div>Region IV-A (CALABARZON)</div>
        <div>Province of Laguna</div>
      </div>
    </div>
    <div class="main-title">{escape(title)}</div>
    """


@lru_cache(maxsize=1)
def _dilg_logo_data_uri():
    try:
        logo_bytes = DILG_LOGO_PATH.read_bytes()
    except OSError:
        return ''
    return f"data:image/png;base64,{b64encode(logo_bytes).decode('ascii')}"


def _official_header_css():
    return """
    .official-letterhead { text-align: center; margin: 0 0 10px; }
    .dilg-logo { width: 64px; height: 64px; object-fit: contain; display: block; margin: 0 auto 6px; }
    .dilg-logo-fallback { width: 58px; height: 58px; border: 2px solid #9ca3af; border-radius: 50%; margin: 0 auto 7px; display: flex; align-items: center; justify-content: center; font-weight: 800; color: #111; }
    .agency-lines { text-align: center; font-size: 12px; line-height: 1.22; color: #111; }
    .agency-lines .department { font-weight: 800; font-size: 13px; }
    .main-title { text-align: center; font-size: 15px; font-weight: 800; margin: 18px 0 16px; }
    """


def _project_summary_box_html(context):
    return f"""
    <table class="project-box">
      <tr><th>Project ID:</th><td>{escape(format_value(context.get('project_id')))}</td></tr>
      <tr><th>Project Name:</th><td>{escape(format_value(context.get('project_title')))}</td></tr>
      <tr><th>Allocation:</th><td>{escape(format_value(context.get('allocation')))}</td></tr>
      <tr><th>Location:</th><td>{escape(format_value(context.get('project_location')))}</td></tr>
      <tr><th>Date Monitored:</th><td>{escape(format_value(context.get('inspection_date')))}</td></tr>
    </table>
    """


def _memo_findings_table_html(project_management_rows, quality_rows, health_safety_rows, report_summary):
    rows_html = [
        '<tr class="category-row"><td colspan="4">PROJECT MANAGEMENT</td></tr>',
    ]
    rows_html.extend(_memo_checklist_rows(project_management_rows))
    rows_html.append('<tr class="category-row"><td colspan="4">QUALITY OF WORKS / WORKMANSHIP</td></tr>')
    for row in quality_rows:
        rows_html.append(
            '<tr>'
            f'<td>{escape(format_value(row.get("Type of Defects/Damage") or row.get("Quality Issue")))}</td>'
            f'<td>{escape(format_value(row.get("Recommendation")))}</td>'
            f'<td>{escape(format_value(row.get("TIMELINES")))}</td>'
            f'<td>{escape(format_value(row.get("REMARKS")))}</td>'
            '</tr>'
        )
    rows_html.append('<tr class="category-row"><td colspan="4">TIMELINESS</td></tr>')
    rows_html.extend(_memo_timeliness_rows(report_summary))
    rows_html.append('<tr class="category-row"><td colspan="4">ASSESSMENT RATING FOR SAFETY AND HEALTH DURING THE COVID-19 PUBLIC HEALTH CRISIS</td></tr>')
    rows_html.extend(_memo_checklist_rows(health_safety_rows))
    return f"""
    <table class="findings">
      <thead>
        <tr>
          <th>FINDINGS/<br>OBSERVATIONS</th>
          <th>RECOMMENDATIONS<br>AND AGREEMENTS</th>
          <th>TIMELINES</th>
          <th>REMARKS</th>
        </tr>
      </thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
    """


def _memo_checklist_rows(rows):
    rows_html = []
    for row in rows:
        response = row.get('Remarks')
        notes = row.get('Notes')
        if not notes and not _is_actionable_checklist_response(response):
            continue
        observation = ': '.join(
            item for item in [format_value(row.get('Item')), format_value(response)] if item
        )
        rows_html.append(
            '<tr>'
            f'<td>{escape(format_value(observation))}</td>'
            f'<td>{escape(format_value(notes))}</td>'
            '<td></td><td></td>'
            '</tr>'
        )
    return rows_html


def _memo_timeliness_rows(report_summary):
    slippage = report_summary.get('% SLIPPAGE :')
    planned = report_summary.get('S-CURVE/PLANNED :')
    actual = report_summary.get('ACTUAL ACCOMPLISHMENT :')
    status = report_summary.get('ACTUAL PROJECT STATUS :')
    if not any(value not in (None, '') for value in [slippage, planned, actual, status]):
        return []
    observation_parts = []
    if status not in (None, ''):
        observation_parts.append(f'Status: {status}')
    if planned not in (None, ''):
        observation_parts.append(f'Planned: {planned}')
    if actual not in (None, ''):
        observation_parts.append(f'Actual: {actual}')
    if slippage not in (None, ''):
        observation_parts.append(f'Slippage: {slippage}')
    return [
        '<tr>'
        f'<td>{escape(format_value("; ".join(observation_parts)))}</td>'
        '<td></td><td></td><td></td>'
        '</tr>'
    ]


def _is_actionable_checklist_response(response):
    normalized = str(response or '').strip().upper()
    if not normalized:
        return False
    if normalized.endswith('%'):
        try:
            return float(normalized[:-1]) < 100
        except ValueError:
            pass
    non_actionable = {
        'YES',
        'COMPLIED',
        'COMPLIANT',
        'UPDATED',
        'AVAILABLE',
        'PRESENT',
        'ADEQUATE',
        'SATISFACTORY',
        'N/A',
        'NA',
        'NOT APPLICABLE',
    }
    return normalized not in non_actionable


def _defects_table_html(rows):
    rows_html = []
    for row in rows:
        rows_html.append(
            '<tr>'
            f'<td>{escape(format_value(row.get("Code No.")))}</td>'
            f'<td>{escape(format_value(row.get("Type of Defects/Damage")))}</td>'
            f'<td>{escape(format_value(row.get("Location/ Landmark")))}</td>'
            f'<td>{escape(format_value(row.get("Recommendation")))}</td>'
            f'<td>{escape(format_value(row.get("TIMELINES")))}</td>'
            f'<td>{escape(format_value(row.get("REMARKS")))}</td>'
            '</tr>'
        )
    return f"""
    <table class="findings">
      <thead>
        <tr>
          <th>CODE NO.</th>
          <th>TYPE OF DEFECTS/DAMAGE</th>
          <th>LOCATION / LANDMARK</th>
          <th>RECOMMENDATION</th>
          <th>TIMELINES</th>
          <th>REMARKS</th>
        </tr>
      </thead>
      <tbody>{''.join(rows_html) or '<tr><td colspan="6"></td></tr>'}</tbody>
    </table>
    """


def _signature_block_html(context, include_lgu=True):
    prepared_by = context.get('prepared_by_name') or ''
    mayor = context.get('mayor_name') or ''
    lgu = context.get('lgu_name') or context.get('lgu_municipality') or ''
    lgu_columns = """
      <th colspan="2">LGU Representatives</th>
    """ if include_lgu else ''
    lgu_rows = f"""
      <td>{escape(format_value(mayor))}</td><td>Signature</td>
    """ if include_lgu else ''
    return f"""
    <p class="commitment">I agree with the above observations and corresponding recommendations and I commit to act within the agreed timelines as stipulated above.</p>
    <table class="signature-table">
      <thead>
        <tr><th colspan="2">DILG Representatives</th>{lgu_columns}</tr>
        <tr><th>Name</th><th>Signature</th>{'<th>Name</th><th>Signature</th>' if include_lgu else ''}</tr>
      </thead>
      <tbody>
        <tr><td>{escape(format_value(prepared_by))}</td><td></td>{lgu_rows}</tr>
        <tr><td></td><td></td>{'<td></td><td></td>' if include_lgu else ''}</tr>
        <tr><td></td><td></td>{'<td></td><td></td>' if include_lgu else ''}</tr>
      </tbody>
    </table>
    {f'<div class="signature-line"><div class="line">{escape(format_value(mayor))}</div><div>MUNICIPAL MAYOR</div><div>{escape(format_value(lgu))}</div></div>' if include_lgu else ''}
    """


def _rows_from_section(structured_output, section_key):
    section = _section_by_key(structured_output, section_key)
    return section.get('rows') if section else []


def _summary_from_section(structured_output, section_key):
    section = _section_by_key(structured_output, section_key)
    return {
        item.get('label'): item.get('value')
        for item in (section or {}).get('summary') or []
    }


def _section_by_key(structured_output, section_key):
    return next(
        (section for section in structured_output.get('sections') or [] if section.get('key') == section_key),
        None,
    )


def _section_html(section, show_notes=True):
    section_key = str(section.get('key') or 'section').replace('_', '-')
    parts = [
        f'<section class="section-block section-{escape(section_key)}">',
        f"<h2>{escape(str(section['title']))}</h2>",
    ]
    if section.get('summary'):
        parts.append('<table class="summary"><tbody>')
        for item in section['summary']:
            parts.append(
                '<tr>'
                f"<th>{escape(str(item.get('label') or ''))}</th>"
                f"<td>{escape(format_value(item.get('value')))}</td>"
                '</tr>'
            )
        parts.append('</tbody></table>')
    if section.get('columns'):
        parts.append('<table>')
        colgroup_html = _section_colgroup_html(section.get('key'), section['columns'])
        if colgroup_html:
            parts.append(colgroup_html)
        parts.append('<thead><tr>')
        for column in section['columns']:
            parts.append(f'<th>{escape(str(column))}</th>')
        parts.append('</tr></thead><tbody>')
        for row in section.get('rows') or []:
            parts.append('<tr>')
            for column in section['columns']:
                parts.append(f"<td>{escape(format_value(row.get(column)))}</td>")
            parts.append('</tr>')
        if not section.get('rows'):
            parts.append(f"<tr><td colspan=\"{len(section['columns'])}\"></td></tr>")
        parts.append('</tbody></table>')
    for note in ((section.get('notes') or []) if show_notes else []):
        parts.append(f'<p class="note">{escape(str(note))}</p>')
    parts.append('</section>')
    return '\n'.join(parts)


def _section_colgroup_html(section_key, columns):
    widths = QAAR_WIDE_TABLE_COLUMN_WIDTHS.get(section_key)
    if not widths:
        return ''
    parts = ['<colgroup>']
    for column in columns:
        width = widths.get(column)
        if width:
            parts.append(f'<col style="width: {escape(width)}">')
        else:
            parts.append('<col>')
    parts.append('</colgroup>')
    return ''.join(parts)


def _header_section(inspection, snapshot, catalog):
    project = inspection.project
    lgu = project.lgu if project else None
    return {
        'key': 'qaar_header',
        'title': 'PROJECT DETAILS',
        'summary': [
            {'label': 'Project:', 'value': project.project_name if project else ''},
            {'label': 'LGU:', 'value': lgu.name if lgu else ''},
            {'label': 'Inspection date:', 'value': inspection.inspection_date.isoformat() if inspection.inspection_date else ''},
            {'label': 'Reference version:', 'value': catalog['reference']['version']},
        ],
        'notes': [_scoring_note(snapshot)],
    }


def _report_summary_section(snapshot, catalog):
    summary = snapshot.get('report_summary') or {}
    field_labels = {
        item['key']: item['label']
        for item in catalog['report_summary_fields']
    }
    return {
        'key': 'report_summary',
        'title': 'REPORT SUMMARY',
        'summary': [
            {'label': field_labels.get(key, key), 'value': summary.get(key)}
            for key in REPORT_SUMMARY_KEYS
            if key in field_labels or summary.get(key) not in (None, '')
        ],
    }


def _assessment_rating_section(snapshot):
    assessment = ((snapshot.get('scoring_summary') or {}).get('assessment_rating') or {})
    quality = assessment.get('quality') or {}
    timeliness = assessment.get('timeliness') or {}
    to_date = assessment.get('to_date') or {}
    health = assessment.get('health_and_safety') or {}
    columns = ['Component', 'Rating', 'Risk Level']
    rows = [
        {
            'Component': 'QUALITY 60% - Project Management (30%)',
            'Rating': (quality.get('project_management') or {}).get('rating_display'),
            'Risk Level': (quality.get('project_management') or {}).get('risk_level'),
        },
        {
            'Component': 'QUALITY 60% - Workmanship/Quality of Works (70%)',
            'Rating': (quality.get('quality_of_works') or {}).get('rating_display'),
            'Risk Level': (quality.get('quality_of_works') or {}).get('risk_level'),
        },
        {
            'Component': 'QUALITY 60% - Rating on Quality (Output I + Output II)',
            'Rating': (quality.get('combined_quality') or {}).get('rating_display'),
            'Risk Level': (quality.get('combined_quality') or {}).get('risk_level'),
        },
        {
            'Component': 'TIMELINESS 40%',
            'Rating': timeliness.get('rating_display'),
            'Risk Level': timeliness.get('risk_level'),
        },
        {
            'Component': 'TO DATE Assessment Rating (60% I.C + 40% II)',
            'Rating': to_date.get('rating_display'),
            'Risk Level': to_date.get('risk_level'),
        },
        {
            'Component': 'ASSESSMENT RATING FOR SAFETY AND HEALTH',
            'Rating': health.get('rating_display'),
            'Risk Level': health.get('risk_level'),
        },
    ]
    summary = [
        {'label': 'Planned/Target accomplishment:', 'value': _format_percent_value(timeliness.get('planned_target_accomplishment'))},
        {'label': 'Actual Accomplishment:', 'value': _format_percent_value(timeliness.get('actual_accomplishment'))},
        {'label': 'Variance:', 'value': _format_percent_value(timeliness.get('variance'))},
    ]
    if timeliness.get('assessment_note'):
        summary.append({'label': 'Timeliness assessment:', 'value': timeliness.get('assessment_note')})
    return {
        'key': 'assessment_rating',
        'title': 'ASSESSMENT RATING',
        'summary': summary,
        'columns': columns,
        'rows': rows,
    }


def _item_description_section(snapshot):
    work_items = snapshot.get('work_items') or []
    scored_items = {
        item.get('id'): item
        for item in ((snapshot.get('scoring_summary') or {}).get('work_items') or {}).get('items', [])
    }
    columns = ['ITEM CODES', 'DESCRIPTION', 'QUANTITY', 'INSPECTED', 'UNIT', 'UNIT COST', 'COST', 'WEIGHT']
    rows = []
    for item in work_items:
        scored = scored_items.get(item.get('id')) or {}
        rows.append({
            'ITEM CODES': item.get('item_code'),
            'DESCRIPTION': item.get('description'),
            'QUANTITY': item.get('quantity'),
            'INSPECTED': item.get('inspected_quantity'),
            'UNIT': item.get('unit'),
            'UNIT COST': item.get('unit_cost'),
            'COST': scored.get('computed_cost'),
            'WEIGHT': scored.get('computed_weight'),
        })
    return {
        'key': 'item_description',
        'title': 'ITEM DESCRIPTION',
        'columns': columns,
        'rows': rows,
    }


def _project_management_section(snapshot):
    score = ((snapshot.get('scoring_summary') or {}).get('project_management') or {})
    rows = []
    for item in snapshot.get('project_management_checks') or []:
        rows.append({
            'Item No.': item.get('official_item_no'),
            'Item': item.get('label'),
            'Remarks': item.get('response'),
            'Notes': item.get('remarks'),
            'Points': item.get('points'),
        })
    return {
        'key': 'project_management',
        'title': 'PROJECT MANAGEMENT',
        'summary': [
            {'label': 'Answered rows:', 'value': score.get('answered_rows')},
            {'label': 'Official rows:', 'value': score.get('official_rows')},
            {'label': 'Points:', 'value': score.get('points')},
            {'label': 'Max points:', 'value': score.get('max_points')},
        ],
        'columns': ['Item No.', 'Item', 'Remarks', 'Notes', 'Points'],
        'rows': rows,
    }


def _health_safety_section(snapshot):
    score = ((snapshot.get('scoring_summary') or {}).get('health_and_safety') or {})
    rows = []
    for item in snapshot.get('health_safety_checks') or []:
        rows.append({
            'Item No.': item.get('official_item_no'),
            'Item': item.get('label'),
            'Remarks': item.get('response'),
            'Notes': item.get('remarks'),
            'Points': item.get('points'),
        })
    return {
        'key': 'health_and_safety',
        'title': 'CONSTRUCTION SAFETY IMPLEMENTATION ASSESSMENT',
        'summary': [
            {'label': 'Answered rows:', 'value': score.get('answered_rows')},
            {'label': 'Official rows:', 'value': score.get('official_rows')},
            {'label': 'Points:', 'value': score.get('points')},
            {'label': 'Max points:', 'value': score.get('max_points')},
        ],
        'columns': ['Item No.', 'Item', 'Remarks', 'Notes', 'Points'],
        'rows': rows,
    }


def _quality_of_works_section(snapshot, catalog):
    columns = [item['label'] for item in catalog['quality_of_works_headers']]
    rows = _quality_rows(snapshot)
    return {
        'key': 'quality_of_works',
        'title': 'QUALITY OF WORKS',
        'columns': columns,
        'rows': rows,
    }


def _findings_recommendations_section(snapshot):
    return {
        'key': 'findings_recommendations',
        'title': 'FINDINGS AND RECOMMENDATIONS',
        'columns': [
            'Code No.',
            'Type of Defects/Damage',
            'Location/ Landmark',
            'Quality Issue',
            'Recommendation',
            'Degree of Defect',
            'Rating per Degree of Defect',
            'Total Rating',
            'TIMELINES',
            'REMARKS',
        ],
        'rows': _quality_rows(snapshot),
    }


def _aide_memoire_section():
    return {
        'key': 'aide_memoire',
        'title': 'AIDE MEMOIRE',
        'notes': [
            (
                'Aide Memoire PDF content is rendered from the structured QAAR rows: '
                'Project Management checklist issues, Findings and Recommendations, '
                'Report Summary timeliness fields, and Health and Safety checklist issues.'
            ),
        ],
    }


def _notice_of_defects_section(snapshot):
    return {
        'key': 'notice_of_defects',
        'title': 'NOTICE OF DEFECTS / DEFICIENCIES',
        'columns': [
            'Code No.',
            'Type of Defects/Damage',
            'Location/ Landmark',
            'Recommendation',
            'TIMELINES',
            'REMARKS',
        ],
        'rows': _quality_rows(snapshot),
    }


def _quality_rows(snapshot):
    work_items = {
        item.get('id'): item
        for item in snapshot.get('work_items') or []
    }
    scored_items = {
        item.get('id'): item
        for item in ((snapshot.get('scoring_summary') or {}).get('work_items') or {}).get('items', [])
    }
    scored_findings = {
        item.get('id'): item
        for item in ((snapshot.get('scoring_summary') or {}).get('quality_of_works') or {}).get('findings', [])
    }
    rows = []
    for index, finding in enumerate(snapshot.get('work_findings') or [], start=1):
        work_item = work_items.get(finding.get('work_item_id')) or {}
        scored_item = scored_items.get(finding.get('work_item_id')) or {}
        scored_finding = scored_findings.get(finding.get('id')) or {}
        rows.append({
            'Item No.': index,
            'Unit': work_item.get('unit'),
            'Description': work_item.get('description'),
            'Code No.': finding.get('defect_code'),
            'Type of Defects/Damage': finding.get('defect_description'),
            'Location/ Landmark': finding.get('location'),
            'Quality Issue': finding.get('quality_issue'),
            'Weight': scored_item.get('computed_weight'),
            'Recommendation': finding.get('recommendation'),
            'Degree of Defect': finding.get('degree_of_defect'),
            'Rating per Degree of Defect': scored_finding.get('rating_per_degree'),
            'Total Rating': scored_finding.get('computed_total_rating'),
            'TIMELINES': finding.get('timeline'),
            'REMARKS': finding.get('remarks'),
        })
    return rows


def _scoring_note(snapshot):
    scoring = snapshot.get('scoring_summary') or {}
    if scoring.get('method_note'):
        return f"QAAR scoring note: {scoring['method_note']}"
    return 'QAAR scoring note: server-side scoring was not available for this snapshot.'


def format_value(value):
    if value is None:
        return ''
    return str(value)


def _format_percent_value(value):
    if value in (None, ''):
        return ''
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if numeric_value == int(numeric_value):
        return f'{int(numeric_value)}%'
    return f'{round(numeric_value, 2)}%'
