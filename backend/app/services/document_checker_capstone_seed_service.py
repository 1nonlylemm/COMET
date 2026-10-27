"""Capstone-ready seed data for the DMS checker evaluation workspace."""

from copy import deepcopy

from app.extensions import db
from app.models import (
    DocumentCheckerEvaluationDataset,
    DocumentCheckerEvaluationRun,
    DocumentCheckerReleasedReport,
    User,
)
from app.services import document_compliance_evaluation_service as evaluation_service
from app.services import document_compliance_rule_engine as rule_engine
from app.services import document_compliance_service
from app.services import document_compliance_synthetic_corpus as synthetic_corpus


CAPSTONE_DATASET_NAME = 'Capstone E2E DMS Checker Benchmark'
CAPSTONE_DATASET_VERSION = '2026.06.06-e2e'
DEFAULT_CASE_TARGET = 60
DEFAULT_MIN_GATE_SUPPORT = evaluation_service.DEFAULT_MIN_GATE_SUPPORT


def seed_capstone_e2e_benchmark(*, user_email=None, user_id=None, case_target=DEFAULT_CASE_TARGET, reset=False):
    """Seed a complete System Administration checker benchmark demo.

    The seeded data is synthetic and local-safe, but it mirrors the workflow shape
    expected by capstone evaluators: labeled document cases, OCR/transcript labels,
    document-to-requirement mapping labels, format/layout labels, completed runs,
    trend snapshots, accuracy gates, and a released benchmark report.
    """
    actor = _resolve_actor(user_email=user_email, user_id=user_id)
    actor_id = actor.id if actor else None

    existing = DocumentCheckerEvaluationDataset.query.filter_by(
        name=CAPSTONE_DATASET_NAME,
        version=CAPSTONE_DATASET_VERSION,
    ).first()
    if existing and reset:
        run_ids = [run.id for run in existing.runs.all()]
        if run_ids:
            releases = DocumentCheckerReleasedReport.query.filter(
                DocumentCheckerReleasedReport.run_id.in_(run_ids)
            ).all()
            for release in releases:
                db.session.delete(release)
            db.session.flush()
        db.session.delete(existing)
        db.session.commit()
        existing = None

    if existing:
        return _seed_result(existing, created=False)

    manifest = build_capstone_e2e_manifest(case_target=case_target)
    imported = evaluation_service.import_manifest(manifest, user_id=actor_id)
    dataset = evaluation_service.get_dataset(imported['dataset']['id'])

    baseline_run = _create_and_start_run(
        dataset.id,
        'Capstone E2E baseline benchmark',
        actor_id=actor_id,
        cycle='baseline',
    )
    latest_run = _create_and_start_run(
        dataset.id,
        'Capstone E2E reviewer workflow validation',
        actor_id=actor_id,
        cycle='latest_validation',
    )
    release = evaluation_service.release_run_report(
        latest_run.id,
        {
            'report_version': 'capstone-e2e-2026.06.06',
            'release_notes': (
                'Capstone end-to-end benchmark seeded for System Administration. '
                'Synthetic cases exercise OCR, document mapping, field extraction, '
                'reviewer safety, and layout/format gates.'
            ),
            'metadata': {
                'capstone_demo': True,
                'baseline_run_id': baseline_run.id,
                'latest_run_id': latest_run.id,
                'workflow_coverage': _workflow_coverage_metadata(),
            },
        },
        user_id=actor_id,
    )
    evaluation_service.update_dataset_status(dataset.id, 'locked', user_id=actor_id)
    dataset = evaluation_service.get_dataset(dataset.id)

    return _seed_result(
        dataset,
        created=True,
        baseline_run=baseline_run,
        latest_run=latest_run,
        release=release,
    )


def build_capstone_e2e_manifest(*, case_target=DEFAULT_CASE_TARGET):
    case_target = max(int(case_target or DEFAULT_CASE_TARGET), DEFAULT_MIN_GATE_SUPPORT)
    source_manifest = synthetic_corpus.build_evaluation_manifest(
        dataset={
            'name': CAPSTONE_DATASET_NAME,
            'version': CAPSTONE_DATASET_VERSION,
            'dataset_type': 'demo',
            'status': 'active',
            'description': (
                'Capstone end-to-end DMS checker benchmark. Synthetic-but-realistic '
                'documents cover OCR, mapping, fields, reviewer safety, and layout/format checks.'
            ),
            'metadata': {
                'capstone_demo': True,
                'source': 'document_checker_capstone_seed_service',
                'case_target': case_target,
                'minimum_gate_support': DEFAULT_MIN_GATE_SUPPORT,
                'workflow_coverage': _workflow_coverage_metadata(),
            },
        },
    )
    source_cases = source_manifest['cases']
    cases = [
        _capstone_case_variant(source_cases[index % len(source_cases)], index)
        for index in range(case_target)
    ]
    source_manifest['cases'] = cases
    source_manifest['dataset']['metadata']['case_count'] = len(cases)
    source_manifest['dataset']['metadata']['document_families'] = sorted({
        case['document_family'] for case in cases
    })
    return source_manifest


def _create_and_start_run(dataset_id, run_name, *, actor_id=None, cycle):
    run = evaluation_service.create_run(
        dataset_id,
        {
            'run_name': run_name,
            'checker_version': document_compliance_service.CHECKER_VERSION,
            'rule_policy_version': rule_engine.POLICY_VERSION,
            'provider_config': {
                'ocr': 'local-text-plus-synthetic-ocr-labels',
                'document_mapping': 'synthetic-nlp-ranking',
                'layout': 'synthetic-rendered-layout-labels',
                'human_review': 'reviewer-adjudicated-demo',
            },
            'reference_profile_snapshot': {
                'source': 'synthetic_documentary_corpus',
                'policy_version': rule_engine.POLICY_VERSION,
                'template_version': evaluation_service.GOLD_LABEL_TEMPLATE_VERSION,
            },
            'metadata': {
                'capstone_demo': True,
                'simulation_cycle': cycle,
                'end_to_end_steps': _workflow_steps(),
            },
        },
        user_id=actor_id,
    )
    return evaluation_service.run_evaluation(
        run.id,
        user_id=actor_id,
        min_gate_support=DEFAULT_MIN_GATE_SUPPORT,
    )


def _capstone_case_variant(source_case, index):
    case = deepcopy(source_case)
    original_key = case['case_key']
    cycle_number = (index // 19) + 1
    case_key = f'{original_key}-capstone-{index + 1:03d}'
    document_family = case['document_family']
    expected_status = (case.get('ground_truth') or {}).get('expected_status')
    has_format_issue = (index % 2 == 1) or expected_status in {'likely_return', 'invalid_evidence'}
    mapping_id = 10000 + index + 1
    ocr_text = _ocr_reference_text(case, index)
    expected_layout = _expected_layout(document_family, has_format_issue=has_format_issue)
    expected_annotations = _expected_annotations(case_key, expected_layout, has_format_issue=has_format_issue)
    fixture_output = deepcopy((case.get('metadata') or {}).get('fixture_checker_output') or {})
    expected_findings = list((case.get('ground_truth') or {}).get('expected_findings') or [])
    forbidden_findings = list((case.get('ground_truth') or {}).get('forbidden_findings') or [])

    if has_format_issue:
        expected_findings.append('format_profile_header_logo_overlap')
        fixture_output.setdefault('findings', []).append(_format_overlap_finding())
    else:
        forbidden_findings.append('format_profile_header_logo_overlap')

    case['case_key'] = case_key
    case['ground_truth'] = {
        **case['ground_truth'],
        'case_key': case_key,
        'expected_findings': _unique(expected_findings),
        'forbidden_findings': _unique(forbidden_findings),
        'expected_mapping': {
            'project_requirement_id': mapping_id,
            'top_k': 3,
        },
        'expected_ocr': {
            'reference_text': ocr_text,
            'readable_text_expected': True,
            'min_readable_text_chars': min(80, len(ocr_text)),
            'max_cer': 0.05,
            'max_wer': 0.10,
            'scanned_image_safety_case': True,
            'extraction_unavailable_should_not_be_ready': False,
        },
        'expected_annotations': expected_annotations,
        'expected_layout': expected_layout,
        'advisory_boundary_case': True,
    }
    fixture_output = _augment_fixture_output(
        fixture_output,
        mapping_id=mapping_id,
        ocr_text=ocr_text,
        expected_layout=expected_layout,
        expected_annotations=expected_annotations,
        expected_status=expected_status,
    )
    case['metadata'] = {
        **(case.get('metadata') or {}),
        'fixture_checker_output': fixture_output,
        'original_case_key': original_key,
        'capstone_case_index': index + 1,
        'capstone_cycle': cycle_number,
        'capstone_demo': True,
        'workflow': {
            'source': 'DMS Intake',
            'simulated_steps': _workflow_steps(),
            'reviewer_expected_action': case['ground_truth'].get('expected_recommended_action'),
        },
        'document_asset': {
            'file_name': f'{case_key}.pdf',
            'mime_type': 'application/pdf',
            'synthetic_document': True,
            'privacy': 'No real citizen, contractor, or beneficiary PII.',
        },
    }
    return case


def _augment_fixture_output(fixture_output, *, mapping_id, ocr_text, expected_layout, expected_annotations, expected_status):
    fixture_output = dict(fixture_output or {})
    extracted_fields = dict(fixture_output.get('extracted_fields') or {})
    extraction_metadata = dict(extracted_fields.get('extraction_metadata') or {})
    extraction_metadata.update({
        'readable_text_chars': len(ocr_text),
        'ocr_confidence': 0.97,
        'layout_elements': deepcopy(expected_layout.get('layout_elements') or []),
    })
    extracted_fields['extraction_metadata'] = extraction_metadata
    fixture_output['extracted_fields'] = extracted_fields
    fixture_output['mapping'] = {
        'suggested_project_requirement_id': mapping_id,
        'candidate_rankings': [
            {'project_requirement_id': mapping_id, 'score': 0.98},
            {'project_requirement_id': mapping_id + 5000, 'score': 0.42},
            {'project_requirement_id': mapping_id + 9000, 'score': 0.19},
        ],
        'top_k': 3,
    }
    fixture_output['ocr'] = {
        'text': ocr_text,
        'readable_text_chars': len(ocr_text),
        'confidence': 0.97,
        'extraction_failed': False,
    }
    fixture_output['layout'] = deepcopy(expected_layout)
    fixture_output['annotations'] = list(fixture_output.get('annotations') or []) + deepcopy(expected_annotations)
    fixture_output['advisory'] = {
        'provider_status_suggestion': 'ready_for_approval',
        'deterministic_status': expected_status,
        'deterministic_status_preserved': True,
        'advisory_overrode_status': False,
    }
    return fixture_output


def _expected_layout(document_family, *, has_format_issue):
    elements = [
        {'id': 'header_band', 'type': 'header', 'page': 1, 'bbox': [0.06, 0.04, 0.94, 0.15], 'min_iou': 0.5},
        {'id': 'readable_body', 'type': 'readable_text', 'page': 1, 'bbox': [0.08, 0.18, 0.92, 0.66], 'min_iou': 0.5},
        {'id': 'footer_reference', 'type': 'footer', 'page': 1, 'bbox': [0.08, 0.92, 0.92, 0.98], 'min_iou': 0.5},
    ]
    if document_family in {'official_receipt', 'billing_package', 'program_of_works', 'detailed_engineering_estimate'}:
        elements.append({'id': 'amount_table', 'type': 'table', 'page': 1, 'bbox': [0.10, 0.38, 0.90, 0.58], 'min_iou': 0.5})
    if document_family in {'certification', 'resolution', 'program_of_works', 'detailed_engineering_estimate'}:
        elements.append({'id': 'signatory_block', 'type': 'signatory', 'page': 1, 'bbox': [0.55, 0.72, 0.92, 0.88], 'min_iou': 0.5})
    issues = []
    if has_format_issue:
        issues.append({
            'id': 'header_logo_overlap',
            'type': 'overlap',
            'page': 1,
            'bbox': [0.08, 0.05, 0.23, 0.13],
            'min_iou': 0.5,
        })
    return {
        'layout_elements': elements,
        'layout_issues': issues,
    }


def _expected_annotations(case_key, expected_layout, *, has_format_issue):
    annotations = [
        {
            'id': f'{case_key}:header_band',
            'finding_id': 'layout_header_present',
            'page': 1,
            'bbox': [0.06, 0.04, 0.94, 0.15],
            'min_iou': 0.5,
            'label': 'Header band',
        },
    ]
    if has_format_issue and (expected_layout.get('layout_issues') or []):
        issue = expected_layout['layout_issues'][0]
        annotations.append({
            'id': f'{case_key}:header_logo_overlap',
            'finding_id': 'layout_overlap:header_logo_overlap',
            'page': 1,
            'bbox': issue['bbox'],
            'min_iou': 0.5,
            'label': 'Header logo overlap',
        })
    return annotations


def _format_overlap_finding():
    return {
        'id': 'format_profile_header_logo_overlap',
        'severity': 'blocker',
        'dimension': 'format_template_layout',
        'category': 'layout_overlap',
        'message': 'Header logo overlaps the official document title area.',
        'locations': [
            {
                'page': 1,
                'bbox': {'x': 0.08, 'y': 0.05, 'width': 0.15, 'height': 0.08},
            },
        ],
    }


def _ocr_reference_text(case, index):
    metadata = case.get('metadata') or {}
    scenario = metadata.get('scenario') or case.get('case_key')
    return (
        f'COMET synthetic benchmark transcript {index + 1}. '
        f'Document family {case.get("document_family")}; scenario {scenario}. '
        'The rendered file contains readable header text, body content, reference fields, '
        'required layout zones, and reviewer-visible signatory or table sections when applicable.'
    )


def _workflow_steps():
    return [
        'DMS intake receives the documentary file.',
        'NLP mapping suggests the project requirement.',
        'OCR/readable-text extraction records transcript quality.',
        'The checker evaluates fields, evidence type, findings, and layout zones.',
        'A human reviewer keeps final authority over approval or return.',
        'System Administration records benchmark metrics, gates, and release history.',
    ]


def _workflow_coverage_metadata():
    return {
        'ocr': 'CER, WER, readable-text, confidence, extraction failure safety',
        'mapping': 'precision, recall, F1, top-k, false mapping rate',
        'fields': 'LGU, date, amount, reference number, project title, fiscal year',
        'compliance': 'false approval, false return, blocker false-positive/negative',
        'layout': 'header, footer, table, signatory, readable text, overlap issue IoU',
        'reviewer_safety': 'advisory output cannot override deterministic checker status',
    }


def _resolve_actor(*, user_email=None, user_id=None):
    if user_id is not None:
        return db.session.get(User, int(user_id))
    if user_email:
        actor = User.query.filter_by(email=user_email).first()
        if actor:
            return actor
    return User.query.filter_by(role='system_admin', is_active=True).order_by(User.id.asc()).first()


def _seed_result(dataset, *, created, baseline_run=None, latest_run=None, release=None):
    latest_run = latest_run or dataset.runs.order_by(
        DocumentCheckerEvaluationRun.created_at.desc(),
        DocumentCheckerEvaluationRun.id.desc(),
    ).first()
    return {
        'created': created,
        'dataset': evaluation_service.serialize_dataset(dataset),
        'baseline_run': evaluation_service.serialize_run(baseline_run) if baseline_run else None,
        'latest_run': evaluation_service.serialize_run(latest_run) if latest_run else None,
        'release': evaluation_service.serialize_released_report(release) if release else None,
        'summary': evaluation_service.get_summary({'dataset_id': dataset.id}),
    }


def _unique(values):
    output = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        output.append(value)
        seen.add(value)
    return output
