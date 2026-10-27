import json
import hashlib
import shutil
from datetime import date
from pathlib import Path

from app.services import documentary_reference_pattern_service as pattern_service
from app.services import demo_seed_rendering


DEFAULT_CONTEXT = {
    'project_name': 'Rehabilitation of Barangay Access Road',
    'source_project_code': 'LGSF-2023-BINAN-001',
    'lgu_name': 'City of Binan',
    'fiscal_year': 2023,
    'amount': '340000.00',
    'reference_number': None,
    'vendor_or_payee': 'Laguna Builders Cooperative',
    'pattern_source': None,
}

CORE_DOCUMENT_FAMILIES = (
    'nadai_fund_transfer',
    'certification',
    'resolution',
    'official_receipt',
    'billing_package',
    'program_of_works',
    'detailed_engineering_estimate',
    'progress_report',
)

FAMILY_FILE_NAMES = {
    'nadai_fund_transfer': 'notice_of_authority_to_debit_account_issued.pdf',
    'certification': 'certification.pdf',
    'resolution': 'sanggunian_resolution.pdf',
    'official_receipt': 'official_receipt.pdf',
    'billing_package': 'statement_of_receipts_and_disbursements.pdf',
    'program_of_works': 'program_of_works.pdf',
    'detailed_engineering_estimate': 'detailed_engineering_estimate.pdf',
    'progress_report': 'progress_accomplishment_report.pdf',
}

FAMILY_REFERENCE_PREFIXES = {
    'nadai_fund_transfer': 'ADA',
    'certification': 'CERT',
    'resolution': 'RES',
    'official_receipt': 'OR',
    'billing_package': 'SORD',
    'program_of_works': 'POW',
    'detailed_engineering_estimate': 'DED',
    'progress_report': 'PRG',
}


def generate_seed_document(output_path, *, family, context=None, write_ground_truth=True, fast_mode=False):
    """Generate one safe synthetic documentary requirement sample."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _document_payload(family, context or {})
    if not fast_mode:
        payload = demo_seed_rendering.adapt_payload(payload)
        payload['generator_version'] = demo_seed_rendering.GENERATOR_VERSION
    
    cache_dir = Path(output_path).parent.parent / '.pdf_cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    if fast_mode:
        cached_dummy = cache_dir / "dummy_fast.pdf"
        if not cached_dummy.exists():
            _write_pdf(cached_dummy, "<!doctype html><html><body><h1>Dummy PDF (Fast Mode)</h1></body></html>")
        shutil.copy2(cached_dummy, output_path)
    else:
        payload_str = json.dumps(payload, sort_keys=True, default=str)
        # Template edits invalidate cached PDFs even if the project data is unchanged.
        template_root = demo_seed_rendering.document_renderer().templates_dir
        template_digest = hashlib.sha256(b''.join((template_root / name).read_bytes() for name in ('base.html', 'seed_document.html'))).hexdigest()
        payload_str += template_digest
        payload_hash = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
        cached_pdf = cache_dir / f"{payload_hash}.pdf"
        
        if cached_pdf.exists():
            shutil.copy2(cached_pdf, output_path)
        else:
            demo_seed_rendering.render_pdf(payload, cached_pdf)
            shutil.copy2(cached_pdf, output_path)

    result = {
        'document_path': str(output_path),
        'requirement_family': payload['family'],
        'layout_profile': payload['layout_profile'],
        'generator_version': payload.get('generator_version'),
    }
    if write_ground_truth:
        ground_truth_path = output_path.with_suffix('.ground_truth.json')
        _write_json(ground_truth_path, _ground_truth(payload, output_path))
        result['ground_truth_path'] = str(ground_truth_path)
    return result


def generate_seed_document_package(output_dir, *, families=None, context=None):
    """Generate a reusable package of formal seed documents with a manifest."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_families = tuple(families or CORE_DOCUMENT_FAMILIES)
    documents = []

    for family in selected_families:
        output_path = output_dir / _file_name_for_family(family)
        family_context = dict(context or {})
        family_context['pattern_source'] = (
            family_context.get('pattern_source')
            or f'sanitized_reference_pattern:{family}'
        )
        if not family_context.get('reference_number'):
            family_context['reference_number'] = _reference_number_for_family(
                family,
                family_context.get('fiscal_year') or DEFAULT_CONTEXT['fiscal_year'],
            )
        result = generate_seed_document(
            output_path,
            family=family,
            context=family_context,
            write_ground_truth=True,
        )
        ground_truth_path = Path(result['ground_truth_path'])
        documents.append({
            'requirement_family': family,
            'file_name': output_path.name,
            'ground_truth_file_name': ground_truth_path.name,
            'layout_profile': result['layout_profile'],
            'uses_original_file': False,
        })

    manifest_path = output_dir / 'documentary_seed_manifest.json'
    manifest = {
        'version': 'documentary-seed-documents-2026.05.23',
        'source_policy': {
            'use_original_files_as_seed_attachments': False,
            'use_original_files_as_pattern_references_only': True,
            'visible_document_markers': True,
            'ground_truth_sidecars_required': True,
        },
        'documents': documents,
    }
    _write_json(manifest_path, manifest)
    return {
        'output_dir': str(output_dir),
        'manifest_path': str(manifest_path),
        'document_count': len(documents),
        'documents': documents,
    }


def _document_payload(family, context):
    merged = dict(DEFAULT_CONTEXT)
    merged.update(context or {})
    if 'amount' not in (context or {}) and 'budget_amount' in (context or {}):
        merged['amount'] = str(context['budget_amount'])
    normalized_family = str(family or 'generic_document')
    if not merged.get('reference_number'):
        merged['reference_number'] = _reference_number_for_family(
            normalized_family,
            merged.get('fiscal_year') or DEFAULT_CONTEXT['fiscal_year'],
        )
    doc_date = (
        merged.get('document_date')
        or merged.get('generated_on')
        or date.today().isoformat()
    )
    merged['generated_on'] = doc_date
    layout_profile = pattern_service.layout_profile_for_family(normalized_family)
    spec = _family_spec(normalized_family, merged)
    payload = {
        'family': normalized_family,
        'title': spec['title'],
        'context': merged,
        'layout_profile': layout_profile,
        'meta_rows': spec['meta_rows'],
        'body_sections': spec['body_sections'],
        'table_columns': spec['table_columns'],
        'rows': spec['rows'],
        'certification': spec['certification'],
        'signatories': _signatories(merged),
        'generated_on': doc_date,
    }
    if 'package_components' in spec:
        payload['package_components'] = spec['package_components']
    return payload


def _file_name_for_family(family):
    return FAMILY_FILE_NAMES.get(family, f'{pattern_service.slugify(family)}.pdf')


def _reference_number_for_family(family, fiscal_year):
    prefix = FAMILY_REFERENCE_PREFIXES.get(family, 'DOC')
    return f'{prefix}-{fiscal_year}-001'


def _render_html(payload):
    context = payload['context']
    meta_rows = ''.join(
        f'<tr><td>{_escape(label)}</td><td>{_escape(value)}</td></tr>'
        for label, value in payload['meta_rows']
    )
    body_sections = ''.join(_render_body_section(section) for section in payload['body_sections'])
    table = _render_table(payload)
    signature_blocks = ''.join(
        '<div class="signature-block">'
        '<div class="signature-line"></div>'
        f'<div class="name">{_escape(item["name"])}</div>'
        f'<div>{_escape(item["title"])}</div>'
        f'<div>{_escape(item["label"])}</div>'
        '</div>'
        for item in payload['signatories']
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: letter; margin: 0.62in 0.68in; }}
    body {{ font-family: Arial, sans-serif; color: #111827; font-size: 10.2pt; }}
    .masthead {{ text-align: center; border-bottom: 2px solid #1f2937; padding-bottom: 8px; }}
    .republic {{ font-size: 9pt; font-weight: 700; }}
    .office {{ font-size: 11pt; font-weight: 700; margin-top: 2px; }}
    .suboffice {{ font-size: 9pt; margin-top: 2px; }}
    h1 {{ text-align: center; font-size: 14pt; margin: 18px 0 10px; }}
    h2 {{ font-size: 10.5pt; margin: 12px 0 5px; text-transform: uppercase; }}
    .meta {{ width: 100%; border-collapse: collapse; margin: 8px 0 14px; }}
    .meta td {{ border: 1px solid #9ca3af; padding: 5px 7px; }}
    .meta td:first-child {{ width: 27%; font-weight: 700; background: #f3f4f6; }}
    .note {{ margin: 10px 0 12px; line-height: 1.45; text-align: justify; }}
    table.ledger {{ width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 8px; }}
    .ledger th {{ border: 1px solid #111827; padding: 6px; background: #e5e7eb; font-size: 9pt; }}
    .ledger td {{ border: 1px solid #374151; padding: 6px; vertical-align: top; height: 29px; }}
    .ledger .amount {{ text-align: right; white-space: nowrap; }}
    .total-row td {{ font-weight: 700; background: #f9fafb; }}
    .certification {{ border: 1px solid #9ca3af; padding: 8px; margin-top: 12px; line-height: 1.45; }}
    .signatures {{ display: flex; justify-content: space-between; gap: 18px; margin-top: 42px; }}
    .signature-block {{ width: 32%; text-align: center; font-size: 8.5pt; }}
    .signature-line {{ border-top: 1px solid #111827; height: 8px; }}
    .name {{ font-weight: 700; text-transform: uppercase; }}
    .footer {{ position: fixed; bottom: -0.38in; left: 0; right: 0; font-size: 7.5pt; color: #6b7280; text-align: center; }}
  </style>
</head>
<body>
  <div class="masthead">
    <div class="republic">REPUBLIC OF THE PHILIPPINES</div>
    <div class="office">{_escape(context.get("lgu_name"))}</div>
    <div class="suboffice">Office of the Local Chief Executive / Municipal Treasurer</div>
    <div class="suboffice">Province of Laguna</div>
  </div>
  <h1>{_escape(payload["title"])}</h1>
  <table class="meta">
    {meta_rows}
  </table>
  {body_sections}
  {table}
  <div class="certification">{_escape(payload["certification"])}</div>
  <div class="signatures">{signature_blocks}</div>
  <div class="footer">Page 1 of 1</div>
</body>
</html>"""


def _family_spec(family, context):
    title = _title_for_family(family)
    amount = _format_money(context.get('amount'))
    reference = context.get('reference_number')
    doc_date = (
        context.get('document_date')
        or context.get('generated_on')
        or date.today().isoformat()
    )
    base_meta = [
        ('Project', context.get('project_name')),
        ('Project Code', context.get('source_project_code')),
        ('Fiscal Year', f'FY {context.get("fiscal_year")}'),
    ]
    common_meta_tail = [
        ('Total Amount', amount),
        ('Date Prepared', doc_date),
    ]
    meta_rows = base_meta + [
        ('Reference No.', reference),
        ('Payee / Vendor', context.get('vendor_or_payee')),
    ] + common_meta_tail
    body_sections = [{
        'heading': None,
        'text': 'This document presents supporting details for the project indicated above. Entries are prepared from available local records and supporting documents.',
    }]
    table_columns = _columns_for_family(family)
    certification = (
        'I hereby certify that the entries above are true and correct based on available supporting records '
        'and are aligned with the project, fiscal year, local government unit, and documentary requirement stated herein.'
    )
    rows = _rows_for_family(family, context)
    package_components = None

    if family == 'nadai_fund_transfer':
        meta_rows = base_meta + [
            ('ADA / NCA / NTA Reference', reference),
            ('Fund Source', context.get('fund_source') or 'Local Government Support Fund'),
            ('Credited Amount', amount),
            ('Purpose', context.get('purpose') or context.get('project_name')),
            ('Date Prepared', doc_date),
        ]
        body_sections = [
            {
                'heading': 'Fund Transfer Details',
                'text': f'This notice records the authority to debit account issued for {context.get("lgu_name")} under FY {context.get("fiscal_year")}.',
            },
            {
                'heading': 'Purpose',
                'text': f'The credited amount is intended for {context.get("project_name")} and shall be supported by required liquidation documents.',
            },
        ]
    elif family == 'certification':
        req_name = str(context.get('requirement_name') or '')
        if req_name in (
            'SGLG-IF Menu / Checklist of Projects',
            'SGLG-IF Checklist of Documentary Requirements (Menu of Projects)',
        ) or ('SGLG-IF' in req_name and 'Menu' in req_name):
            title = 'SGLG-IF SUBMISSION PACKAGE: LCE CERTIFICATION (ANNEX B1) & MENU / CHECKLIST OF PROJECTS (ANNEX B2)'
            meta_rows = base_meta + [
                ('Certification Reference', reference),
                ('Office', 'Office of the Local Chief Executive'),
                ('Bank Trust Account', f'Land Bank of the Philippines - SGLG-IF Trust Account (LGU {context.get("lgu_name")})'),
                ('Date Issued', doc_date),
            ] + common_meta_tail
            body_sections = [
                {
                    'heading': 'Part 1: Local Chief Executive Certification (Annex B1)',
                    'text': (
                        f'I, Local Chief Executive of {context.get("lgu_name")}, hereby certify that: '
                        f'(1) The project listed above is included in the approved Local Development Investment Program (LDIP) '
                        f'and Annual Investment Program (AIP) for CY {context.get("fiscal_year")}; '
                        f'(2) The LGU has maintained/opened a dedicated Trust Fund Account for the Seal of Good Local Governance Incentive Fund (SGLG-IF); and '
                        f'(3) The attached Menu/Checklist of Projects (Annex B2) has been duly accomplished in accordance with DILG guidelines.'
                    ),
                },
                {
                    'heading': 'Part 2: Menu / Checklist of Eligible Projects (Annex B2)',
                    'text': (
                        'The following project allocation is selected from the menu of eligible investment categories '
                        'pursuant to the SGLG-IF Omnibus Guidelines and PDMU Operations Manual.'
                    ),
                },
            ]
            table_columns = ['Eligible Project Category', 'Sector Scope', 'Proposed Allocation', 'Status / Verification']
            try:
                raw_amt = float(context.get('amount') or 0)
            except (TypeError, ValueError):
                raw_amt = 0.0
            rows = [
                {
                    'Eligible Project Category': 'Disaster Risk Reduction and Climate Change Adaptation',
                    'Sector Scope': 'Local Infrastructure / Flood Mitigation / Access Facility',
                    'Proposed Allocation': _format_money(raw_amt * 0.70),
                    'Status / Verification': 'Verified in LDIP / AIP',
                },
                {
                    'Eligible Project Category': 'Basic Essential Public Services and Social Infrastructure',
                    'Sector Scope': 'Public Safety / Emergency Response / Community Facility',
                    'Proposed Allocation': _format_money(raw_amt * 0.30),
                    'Status / Verification': 'Verified in LDIP / AIP',
                },
            ]
            certification = (
                'I hereby certify under penalty of administrative sanctions that the project details and sector selections '
                'above conform strictly to the SGLG-IF eligible menu of projects and DILG prescribed guidelines.'
            )
            package_components = [
                'Annex B1: Local Chief Executive Certification',
                'Annex B2: Menu / Checklist of Eligible Projects',
            ]
        else:
            meta_rows = base_meta + [
                ('Certification Reference', reference),
                ('Office', 'Office of the Local Chief Executive'),
                ('Date Issued', doc_date),
            ]
            body_sections = [
                {
                    'heading': None,
                    'text': f'This is to certify that {context.get("project_name")} is recorded under the official project listing of {context.get("lgu_name")} for FY {context.get("fiscal_year")}.',
                },
                {
                    'heading': 'Basis of Certification',
                    'text': 'The certification is based on project records, approved work documents, and available supporting entries on file.',
                },
                {
                    'heading': None,
                    'text': f'Issued this {doc_date} for whatever legal purpose it may serve.',
                },
            ]
        pass
    elif family == 'resolution':
        meta_rows = base_meta + [
            ('Resolution No.', reference),
            ('Session Type', 'Regular Session'),
            ('Date Adopted', doc_date),
        ]
        body_sections = [
            {
                'heading': None,
                'text': f'Excerpt from the minutes of the regular session of the Sangguniang Bayan of {context.get("lgu_name")}.',
            },
            {
                'heading': None,
                'text': f'WHEREAS, the implementation of {context.get("project_name")} supports local infrastructure and service delivery priorities;',
            },
            {
                'heading': None,
                'text': f'RESOLVED, as it is hereby resolved, to endorse the project and authorize the processing of the required documentary submissions for FY {context.get("fiscal_year")}.',
            },
        ]
    elif family == 'official_receipt':
        meta_rows = [
            ('Official Receipt No.', reference),
            ('Received from', context.get('vendor_or_payee')),
            ('Project', context.get('project_name')),
            ('Project Code', context.get('source_project_code')),
            ('Amount Received', amount),
            ('Date Paid', doc_date),
        ]
        body_sections = [{
            'heading': None,
            'text': f'Received from {context.get("vendor_or_payee")} the amount stated above as payment or reimbursement related to {context.get("project_name")}.',
        }]
    elif family == 'program_of_works':
        body_sections = [{
            'heading': 'Scope of Work',
            'text': 'The following work items summarize the approved scope, quantity, unit cost, and estimated amount for implementation.',
        }]
    elif family == 'detailed_engineering_estimate':
        body_sections = [{
            'heading': 'Detailed Cost Estimate',
            'text': 'The following estimate itemizes quantities, units, direct costs, and total amounts for engineering validation.',
        }]
    elif family == 'progress_report':
        meta_rows = base_meta + [
            ('Report Period', f'FY {context.get("fiscal_year")} Quarter 4'),
            ('Reference No.', reference),
            ('Total Amount', amount),
            ('Date Prepared', doc_date),
        ]
        body_sections = [{
            'heading': 'Accomplishment Summary',
            'text': 'The report presents previous accomplishment, current period progress, cumulative total, and remarks for validation.',
        }]
    elif family == 'billing_package':
        body_sections = [{
            'heading': None,
            'text': 'This statement summarizes receipts and disbursements for the project indicated above. Supporting entries are presented for documentary review and validation.',
        }]

    res = {
        'title': title,
        'meta_rows': meta_rows,
        'body_sections': body_sections,
        'table_columns': table_columns,
        'rows': rows,
        'certification': certification,
    }
    if package_components:
        res['package_components'] = package_components
    return res


def _render_body_section(section):
    heading = section.get('heading')
    heading_html = f'<h2>{_escape(heading)}</h2>' if heading else ''
    return f'{heading_html}<p class="note">{_escape(section.get("text"))}</p>'


def _render_table(payload):
    columns = payload.get('table_columns') or []
    rows = payload.get('rows') or []
    if not columns or not rows:
        return ''
    header_cells = ''.join(f'<th>{_escape(column)}</th>' for column in columns)
    body_rows = []
    for row in rows:
        cells = []
        for column in columns:
            class_name = ' class="amount"' if _is_amount_column(column) else ''
            cells.append(f'<td{class_name}>{_escape(row.get(column, ""))}</td>')
        body_rows.append(f'<tr>{"".join(cells)}</tr>')
    total_value = _format_money(payload['context'].get('amount'))
    total_row = ''
    total_column_index = _total_column_index(columns)
    if total_column_index is not None:
        total_cells = []
        for index, column in enumerate(columns):
            if index == 0:
                total_cells.append('<td>TOTAL</td>')
            elif index == total_column_index:
                total_cells.append(f'<td class="amount">{_escape(total_value)}</td>')
            else:
                total_cells.append('<td></td>')
        total_row = f'<tr class="total-row">{"".join(total_cells)}</tr>'
    return f"""
  <table class="ledger">
    <thead><tr>{header_cells}</tr></thead>
    <tbody>
      {''.join(body_rows)}
      {total_row}
    </tbody>
  </table>"""


def _columns_for_family(family):
    profile = pattern_service.layout_profile_for_family(family)
    tables = profile.get('tables') or []
    if tables:
        return list(tables[0].get('required_columns') or [])
    if family == 'nadai_fund_transfer':
        return ['Fund Transfer Details', 'Reference', 'Amount', 'Purpose']
    if family == 'official_receipt':
        return ['Particulars', 'Reference', 'Amount']
    return []


def _is_amount_column(column):
    return str(column or '').strip().lower() in {'amount', 'unit cost', 'direct cost', 'proposed allocation'}


def _total_column_index(columns):
    for index, column in reversed(list(enumerate(columns))):
        if str(column or '').strip().lower() == 'amount':
            return index
    for index, column in enumerate(columns):
        if _is_amount_column(column):
            return index
    return None


def _rows_for_family(family, context):
    amount = float(context.get('amount') or 0)
    if family == 'billing_package':
        return [
            {
                'Particulars': 'Construction materials and delivery charges',
                'Reference': context.get('reference_number'),
                'Amount': _format_money(amount * 0.58),
                'Remarks': 'Supported by delivery receipt',
            },
            {
                'Particulars': 'Skilled and common labor billing',
                'Reference': f'BILL-{context.get("fiscal_year")}-018',
                'Amount': _format_money(amount * 0.32),
                'Remarks': 'Certified by project engineer',
            },
            {
                'Particulars': 'Administrative and documentation support',
                'Reference': f'LIQ-{context.get("fiscal_year")}-004',
                'Amount': _format_money(amount * 0.10),
                'Remarks': 'For liquidation package',
            },
        ]
    if family == 'nadai_fund_transfer':
        return [
            {
                'Fund Transfer Details': 'Authority to debit account issued',
                'Reference': context.get('reference_number'),
                'Amount': _format_money(amount),
                'Purpose': context.get('purpose') or context.get('project_name'),
            },
            {
                'Fund Transfer Details': 'Notice of cash allocation basis',
                'Reference': f'NCA-{context.get("fiscal_year")}-042',
                'Amount': _format_money(amount),
                'Purpose': 'Project implementation and eligible disbursement',
            },
        ]
    if family == 'official_receipt':
        return [
            {
                'Particulars': 'Payment received for project-related transaction',
                'Reference': context.get('reference_number'),
                'Amount': _format_money(amount),
            },
            {
                'Particulars': 'Documentary stamp and processing fee',
                'Reference': f'OR-FEE-{context.get("fiscal_year")}-006',
                'Amount': _format_money(0),
            },
        ]
    if family == 'program_of_works':
        return [
            {
                'Item Description': 'Site clearing and mobilization',
                'Quantity': '1.00',
                'Unit': 'lot',
                'Unit Cost': _format_money(amount * 0.08),
                'Amount': _format_money(amount * 0.08),
            },
            {
                'Item Description': 'Civil works and materials',
                'Quantity': '1.00',
                'Unit': 'lot',
                'Unit Cost': _format_money(amount * 0.72),
                'Amount': _format_money(amount * 0.72),
            },
            {
                'Item Description': 'Project supervision and closeout',
                'Quantity': '1.00',
                'Unit': 'lot',
                'Unit Cost': _format_money(amount * 0.20),
                'Amount': _format_money(amount * 0.20),
            },
        ]
    if family == 'detailed_engineering_estimate':
        return [
            {
                'Work Item': 'Earthworks and preparation',
                'Quantity': '1.00',
                'Unit': 'lot',
                'Direct Cost': _format_money(amount * 0.18),
                'Amount': _format_money(amount * 0.18),
            },
            {
                'Work Item': 'Structural and architectural works',
                'Quantity': '1.00',
                'Unit': 'lot',
                'Direct Cost': _format_money(amount * 0.62),
                'Amount': _format_money(amount * 0.62),
            },
            {
                'Work Item': 'Contingencies and supervision',
                'Quantity': '1.00',
                'Unit': 'lot',
                'Direct Cost': _format_money(amount * 0.20),
                'Amount': _format_money(amount * 0.20),
            },
        ]
    if family == 'progress_report':
        return [
            {
                'Activity': 'Procurement and mobilization',
                'Previous': '20%',
                'Current': '10%',
                'Total': '30%',
                'Remarks': 'Completed preparatory activities',
            },
            {
                'Activity': 'Main civil works',
                'Previous': '35%',
                'Current': '25%',
                'Total': '60%',
                'Remarks': 'Ongoing implementation',
            },
            {
                'Activity': 'Inspection and turnover',
                'Previous': '0%',
                'Current': '10%',
                'Total': '10%',
                'Remarks': 'For final validation',
            },
        ]
    return [
        {'Particulars': 'Documentary requirement content', 'Reference': context.get('reference_number'), 'Amount': _format_money(amount), 'Remarks': 'Supporting entry'}
    ]


def _ground_truth(payload, output_path):
    context = payload['context']
    gt = {
        'document_id': output_path.stem,
        'file_name': output_path.name,
        'requirement_family': payload['family'],
        'expected_project': context.get('project_name'),
        'expected_lgu': context.get('lgu_name'),
        'expected_fiscal_year': context.get('fiscal_year'),
        'expected_amount': context.get('amount'),
        'expected_reference_number': context.get('reference_number'),
        'expected_status': 'synthetic_review_required',
        'generator_version': payload.get('generator_version'),
        'gold_eligible': False,
        'expected_extracted_fields': {
            'project_title': context.get('project_name'),
            'lgu': context.get('lgu_name'),
            'fiscal_year': context.get('fiscal_year'),
            'amount': context.get('amount'),
            'reference_number': context.get('reference_number'),
            'vendor_or_payee': context.get('vendor_or_payee'),
            'date': payload.get('generated_on'),
            'requirement_family': payload['family'],
        },
        'expected_vendor_or_payee': context.get('vendor_or_payee'),
        'layout_profile': payload['layout_profile'],
        'pattern_source': context.get('pattern_source'),
        'uses_original_file': False,
        'advisory_only': True,
    }
    if 'package_components' in payload:
        gt['package_components'] = payload['package_components']
    if payload.get('generator_version'):
        # Do not claim fields that the new illustrative layout does not contain.
        gt['expected_extracted_fields'].pop('vendor_or_payee', None)
        gt['expected_vendor_or_payee'] = None
    return gt


def _signatories(context):
    return [
        {'label': 'Prepared by', 'name': 'Maria R. Santos', 'title': 'Municipal Treasurer'},
        {'label': 'Reviewed by', 'name': 'Carla P. Dizon', 'title': 'Project Engineer'},
        {'label': 'Approved by', 'name': 'Juan D. Reyes', 'title': 'Local Chief Executive'},
    ]


def _title_for_family(family):
    if family == 'billing_package':
        return 'STATEMENT OF RECEIPTS AND DISBURSEMENTS'
    if family == 'nadai_fund_transfer':
        return 'NOTICE OF AUTHORITY TO DEBIT ACCOUNT ISSUED'
    return pattern_service.layout_profile_for_family(family)['required_headings'][0]['label'].upper()


def _write_pdf(path, html):
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover - dependency is part of backend requirements
        raise RuntimeError('WeasyPrint is required to generate documentary seed PDFs.') from exc
    from app.services.pdf_service import safe_weasyprint_url_fetcher
    HTML(string=html, url_fetcher=safe_weasyprint_url_fetcher).write_pdf(str(path))


def _format_money(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0
    return f'PHP {amount:,.2f}'


def _escape(value):
    text = str(value if value is not None else '')
    return (
        text.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
