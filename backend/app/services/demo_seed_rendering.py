"""Project-aware adapter for the documentary fixture generator's shared layout.

These are illustrative demo submissions, never official forms or adjudicated gold data.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path

GENERATOR_VERSION = 'demo-document-fixtures-2026-10-20-v1'

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


def document_kind(name, family):
    name = name.lower()
    # More specific requirements precede broader document words.
    rules = (
        ('photo', ('photo', 'sticker')),
        ('beneficiary_list', ('masterlist', 'payroll', 'distribution /', 'payout schedule')),
        ('consultation', ('consultation', 'participation', 'minutes')),
        ('procurement', ('procurement', 'philgeps', 'bid evaluation')),
        ('award', ('notice of award',)),
        ('proceed', ('notice to proceed',)),
        ('contract', ('contract agreement', 'purchase order')),
        ('inspection', ('inspection', 'qaar', 'quality assurance', 'materials test')),
        ('change', ('variation', 'change order', 'suspension', 'resumption', 'defects', 'delay')),
        ('plan', ('architectural', 'as-built', 'site development', 'engineering design')),
        ('inventory', ('inventory', 'custodian', 'property transfer', 'property acknowledgement')),
        ('work_plan', ('work plan', 'proposal', 'project profile', 'project request', 'investment program', 'aip', 'monitoring plan', 'operations plan', 'o&m plan', 'sustainability')),
        ('fund_transfer', ('proof of transfer',)),
        ('certification', ('certif', 'warranty', 'clearance', 'eligibility', 'closeout')),
        ('fund_return', ('return of', 'reversion')),
        ('delivery', ('delivery receipt', 'packing list')),
        ('financial', ('receipts and disbursements', 'liquidation', 'billing', 'financial')),
        ('progress', ('progress', 'accomplishment', 'completion report', 'validation')),
        ('checklist', ('checklist', 'guidelines', 'assessment', 'rssa')),
    )
    for kind, terms in rules:
        if any(term in name for term in terms):
            return kind
    return family


def adapt_payload(payload):
    doc = deepcopy(payload)
    ctx = doc['context']
    name = str(ctx.get('requirement_name') or doc['title'])
    kind = document_kind(name, doc['family'])
    project = ctx['project_name']
    lgu = ctx['lgu_name']
    year = ctx['fiscal_year']
    amount = Decimal(str(ctx.get('amount') or 0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    money = lambda value: f'PHP {value:,.2f}'
    doc['title'] = name
    doc['meta_rows'] = [
        ('Project', project), ('Project Code', ctx.get('source_project_code')),
        ('LGU', lgu), ('Fiscal Year', f'FY {year}'),
        ('Project Allocation', money(amount)), ('Reference No.', ctx['reference_number']),
        ('Document Date', doc['generated_on']),
    ]
    seen_labels = {label.lower() for label, _ in doc['meta_rows']}
    for label, value in payload.get('meta_rows', []):
        if label.lower() not in seen_labels and value:
            doc['meta_rows'].append((label, value))
            seen_labels.add(label.lower())
    # The combined SGLG package already carries its required B1/B2 components.
    if doc.get('package_components'):
        doc['render_kind'] = 'sglg_package'
        return doc
    intro = f'Illustrative {name} for {project}, {lgu}, FY {year}.'

    is_canonical_core = (
        doc.get('family') in CORE_DOCUMENT_FAMILIES
        and (not ctx.get('requirement_name') or ctx.get('requirement_name') == doc['title'])
    )

    if is_canonical_core:
        doc['body_sections'].insert(0, {'heading': 'Documentary Requirement', 'text': intro})
        if doc.get('family') == 'billing_package' and doc.get('rows'):
            if doc['rows'][-1].get('Particulars') != 'TOTAL':
                doc['rows'].append({'Particulars': 'TOTAL', 'Reference': '', 'Amount': money(amount), 'Remarks': ''})
    else:
        text_by_kind = {
            'photo': 'Demo photo register: before implementation, implementation progress, and completion views. Images are intentionally absent; this sample does not document an actual site visit.',
            'beneficiary_list': 'Synthetic participant register. DEMO identifiers are fictional; no personal information, actual payout, or beneficiary signature is included.',
            'consultation': 'Demo agenda: project objectives, community priorities, implementation arrangements, and follow-up actions. Participants are illustrative roles, without actual attendance or signatures.',
            'procurement': 'Illustrative procurement record covering posting, bid evaluation, and recommendation. Reference identifiers are DEMO entries and do not establish an actual PhilGEPS posting or award.',
            'award': f'Demo notice of award relating to {project}. The project allocation is {money(amount)}. No actual supplier selection or procurement decision is represented.',
            'proceed': f'Demo instruction to commence the described project scope following the illustrative contract. This is not an actual notice authorizing work.',
            'contract': 'Illustrative agreement between the LGU and DEMO SUPPLIER, covering scope, delivery, payment terms, inspection, and warranty. No real contractual obligation is created.',
            'inspection': 'Illustrative inspection checklist covering scope, quantities, supporting records, and follow-up findings. No laboratory result, professional certification, or actual inspection is asserted.',
            'change': 'Illustrative workflow record covering the reason, affected work items, proposed action, and review required. This document does not resolve any existing demo deficiency or approve a variation.',
            'plan': 'Illustrative design document register covering site layout, technical scope, quantities, and cost estimates. This sample is not a construction drawing or professionally approved engineering design.',
            'inventory': 'Illustrative property record covering item description, quantity, custody, and acknowledgement. All asset identifiers use the DEMO prefix.',
            'work_plan': 'Illustrative project plan covering objectives, activities, allocation, implementation schedule, responsible roles, and monitoring indicators.',
            'certification': f'For demonstration, this document illustrates the certification described by "{name}" for {project} in {lgu}, FY {year}. No actual government officer has signed or certified this record.',
            'fund_return': 'Illustrative return-of-funds record with a DEMO remittance reference. The project allocation is shown for context and is not asserted to be the amount returned.',
            'fund_transfer': 'Illustrative LGU trust-fund transfer record with a DEMO transaction reference and reconciliation checklist. The project allocation is shown for context; no actual bank transfer or account balance is asserted.',
            'delivery': 'Illustrative delivery register: DEMO supplier, item descriptions, quantities, and receiving checklist. No actual delivery or acceptance is asserted.',
            'financial': 'Illustrative financial schedule. Amounts below are a synthetic allocation breakdown, not actual expenditure, payment, liquidation, or fund utilization.',
            'progress': 'Illustrative accomplishment record covering planned activities, progress evidence, issues, and next actions. Actual project progress and workflow status remain as recorded in COMET.',
            'checklist': 'Illustrative checklist covering required entries, documentary references, eligibility considerations, and reviewer observations. Items require human review.',
        }
        if 'no other source' in name.lower():
            text_by_kind['certification'] = f'This synthetic sample illustrates a certification that {project}, {lgu}, FY {year}, has no other source of funding for the same scope. It is unsigned and does not assert an actual funding investigation.'
        # Preserve family-specific layouts for NADAI, resolutions, POW and estimates.
        if kind not in text_by_kind:
            doc['body_sections'].insert(0, {'heading': 'Documentary Requirement', 'text': intro})
        else:
            doc['body_sections'] = [{'heading': 'Purpose and Scope', 'text': intro}, {'heading': name, 'text': text_by_kind[kind]}]
            if kind == 'financial':
                first = (amount * Decimal('.58')).quantize(Decimal('.01'))
                second = (amount * Decimal('.32')).quantize(Decimal('.01'))
                doc['table_columns'] = ['Illustrative Allocation', 'Amount']
                doc['rows'] = [{'Illustrative Allocation': label, 'Amount': money(value)} for label, value in (
                    ('Materials / goods', first), ('Labor / services', second),
                    ('Documentation / other', amount-first-second), ('TOTAL', amount))]
            else:
                labels = {
                    'photo': ['Before implementation view', 'Progress view', 'Completion view'],
                    'beneficiary_list': ['DEMO-PARTICIPANT-001', 'DEMO-PARTICIPANT-002'],
                    'inspection': ['Scope and quantities', 'Supporting records', 'Reviewer observations'],
                    'plan': ['Site / layout register', 'Technical specification', 'Estimate schedule'],
                    'procurement': ['Posting reference: DEMO-POST', 'Evaluation record: DEMO-EVAL', 'Recommendation: DEMO-REC'],
                    'work_plan': ['Objective and expected output', 'Implementation activities', 'Monitoring and sustainability'],
                }.get(kind, ['Scope and reference', 'Supporting entries', 'Reviewer observations'])
                doc['table_columns'] = ['Entry', 'Illustrative Detail']
                doc['rows'] = [{'Entry': label, 'Illustrative Detail': 'Synthetic demo entry; requires review'} for label in labels]
    doc['certification'] = ''
    doc['render_kind'] = kind
    return doc


def rendering_context(payload):
    ctx = payload['context']
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return dict(document=payload, lgu_display=ctx['lgu_name'], province=ctx.get('province') or 'Laguna',
                fixture_id=f'DEMO-{fingerprint}', requirement_id=ctx.get('project_requirement_id') or payload['family'],
                evidence_type=payload['family'], generated_at=payload['generated_on'], office='COMET Demo Documentary Submission')


def document_renderer():
    try:
        from document_fixture_generator.engine.renderer import DocumentRenderer
    except ModuleNotFoundError:
        # Support running `python backend/seed_demo.py` from a source checkout.
        import importlib.util
        source = Path(__file__).resolve().parents[3] / 'document_fixture_generator' / 'engine' / 'renderer.py'
        spec = importlib.util.spec_from_file_location('comet_fixture_renderer', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        DocumentRenderer = module.DocumentRenderer
    return DocumentRenderer()


def render_pdf(payload, output_path):
    # Production already includes WeasyPrint; Windows uses the installed Chromium.
    engine = 'chromium' if os.name == 'nt' else 'weasyprint'
    document_renderer().render_pdf('seed_document.html', rendering_context(payload),
                                  output_path=Path(output_path), engine=engine)
