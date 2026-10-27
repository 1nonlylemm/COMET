"""Evaluation service for DMS documentary checker benchmark runs."""

from datetime import datetime, timezone

from sqlalchemy import and_, or_

from app.extensions import db
from app.models import (
    DocumentComplianceResult,
    DocumentFile,
    DocumentCheckerEvaluationCase,
    DocumentCheckerEvaluationDataset,
    DocumentCheckerEvaluationResult,
    DocumentCheckerEvaluationRun,
    DocumentCheckerMetricSnapshot,
    DocumentCheckerReleasedReport,
)
from app.services import document_compliance_metrics as metrics
from app.services import document_compliance_rule_engine as rule_engine


class DocumentCheckerEvaluationError(Exception):
    def __init__(self, message, status_code=400, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


EDITABLE_DATASET_STATUSES = {'draft', 'active'}
RUNNABLE_DATASET_STATUSES = {'active', 'locked'}
RELEASABLE_RUN_STATUSES = {'completed', 'completed_with_failures'}
DEFAULT_MIN_GATE_SUPPORT = 30
GOLD_LABEL_TEMPLATE_VERSION = 'document-checker-gold-label-template-v1'
GOLD_LABEL_TEMPLATE_TYPE = 'document_checker_gold_label_manifest_template'
GOLD_LABEL_TODO_MARKER = 'TODO_REVIEWER'
COMMON_FIELD_METRIC_KEYS = (
    'lgu',
    'date',
    'amount',
    'reference_number',
    'project_title',
    'fiscal_year',
)
BENCHMARK_DRIFT_METRICS = (
    {
        'key': 'pass_rate',
        'label': 'Pass Rate',
        'direction': 'higher',
        'value': lambda snapshot: _snapshot_pass_rate(snapshot),
    },
    {
        'key': 'false_approval_rate',
        'label': 'False Approval',
        'direction': 'lower',
        'value': lambda snapshot: _snapshot_metric(snapshot, 'false_approval_rate'),
    },
    {
        'key': 'false_return_rate',
        'label': 'False Return',
        'direction': 'lower',
        'value': lambda snapshot: _snapshot_metric(snapshot, 'false_return_rate'),
    },
    {
        'key': 'ocr_cer',
        'label': 'OCR CER',
        'direction': 'lower',
        'value': lambda snapshot: _snapshot_metric(snapshot, 'ocr_cer'),
    },
    {
        'key': 'mapping_f1',
        'label': 'Mapping F1',
        'direction': 'higher',
        'value': lambda snapshot: _snapshot_metric(snapshot, 'mapping_f1'),
    },
    {
        'key': 'layout_element_f1',
        'label': 'Layout F1',
        'direction': 'higher',
        'value': lambda snapshot: _snapshot_metric(snapshot, 'layout_element_f1'),
    },
    {
        'key': 'gate_pass_rate',
        'label': 'Gate Pass Rate',
        'direction': 'higher',
        'value': lambda snapshot: _snapshot_gate_pass_rate(snapshot),
    },
)
GOLD_LABEL_REVIEWER_GUIDE_MARKDOWN = '''# DMS Checker Gold Label Reviewer Guide

Use this guide when turning an exported gold-label template into benchmark truth.

## Review Boundary

- Treat checker suggestions as hints only.
- Confirm every label from the submitted document, scan preview, and applicable requirement.
- Do not import the manifest until reviewer signoff and required privacy review are complete.
- Keep the checker advisory: benchmark results do not auto-approve DMS requirements.

## Dataset Fields

- Set dataset.metadata.human_adjudication_completed to true only after reviewer signoff.
- Set dataset.metadata.pii_review_completed to true when pii_review_required is true and privacy/redaction review is complete.
- Keep dataset.dataset_type as reviewer_adjudicated for human-labeled benchmark files.

## Case Fields

- Replace every TODO_REVIEWER value before import.
- Set label_source to reviewer_adjudicated.
- Set metadata.label_status to adjudicated.
- Set pii_redacted to true only when the benchmark copy is redacted or synthetic enough for System Administrator storage.

## Ground Truth Fields

- expected_evidence_type: the real documentary evidence family.
- expected_status: the status the checker should return.
- expected_recommended_action: the reviewer-approved action.
- expected_fields: confirmed LGU, fiscal year, project title, amount, dates, reference numbers, and other required fields.
- expected_findings: findings that should appear when the checker is correct.
- forbidden_findings: findings that should not appear.
- expected_annotations: normalized [x1, y1, x2, y2] boxes for layout evidence when reviewers label visual format issues.
- expected_layout.layout_elements: reviewer-confirmed headers, footers, signatories, tables, logos, stamps, titles, and readable text zones.
- expected_layout.layout_issues: reviewer-confirmed layout defects such as logo/header overlap, table collision, missing required zones, messy layout, or unreadable regions.

## Layout Labeling Examples

Use normalized page coordinates: [x1, y1, x2, y2], where 0 is the top/left edge and 1 is the bottom/right edge of the page.

Example expected_layout:

    "expected_layout": {
      "layout_elements": [
        {
          "id": "header_band",
          "type": "header",
          "page": 1,
          "bbox": [0.05, 0.03, 0.95, 0.16],
          "min_iou": 0.5
        },
        {
          "id": "amount_table",
          "type": "table",
          "page": 1,
          "bbox": [0.10, 0.38, 0.90, 0.58],
          "min_iou": 0.5
        },
        {
          "id": "signatory_block",
          "type": "signatory",
          "page": 1,
          "bbox": [0.56, 0.72, 0.92, 0.90],
          "min_iou": 0.5
        }
      ],
      "layout_issues": [
        {
          "id": "logo_must_not_overlap_header_text",
          "type": "overlap",
          "page": 1,
          "bbox": [0.10, 0.05, 0.18, 0.10],
          "min_iou": 0.5
        }
      ]
    }

Reviewer rules for layout labels:

- Label what should be present for that document family and requirement, not every decorative object.
- Label header, footer, signatory, table, logo, title, stamp, and readable_text zones only when they affect compliance review.
- For scanned documents, label the visible region even when OCR text is imperfect.
- For actual digital PDFs, label the rendered document layout, not only extracted text.
- Do not paste checker_suggestions.suggested_layout into ground_truth without confirming it.
- If a layout defect exists, add it to expected_layout.layout_issues and add the corresponding finding id to expected_findings when the checker should flag it.
- If the checker should not flag a layout issue, put that finding id in forbidden_findings.

## Metric Cheat Sheet

- Character Error Rate (CER): character edit distance divided by expected character count.
- Word Error Rate (WER): word edit distance divided by expected word count.
- Extraction failure rate: documents with no usable text or extraction error divided by documents where extraction is expected.
- Readable-text rate: documents with enough readable text divided by documents where readable text is expected.
- Evidence Type F1: harmonic mean of evidence-family precision and recall.
- Field Extraction F1: harmonic mean of precision and recall for expected LGU, fiscal year, amount, dates, references, and titles.
- Annotation Accuracy: expected annotation boxes matched by predicted boxes at the required IoU threshold.
- Layout Element F1: precision/recall/F1 for reviewer-labeled layout elements such as headers, tables, footers, signatories, logos, and readable text zones.
- Overlap Detection F1: precision/recall/F1 for reviewer-labeled layout defects such as logo/header overlap or table collision.
- False Approval Rate: high-risk cases the checker marked ready for approval.
- False Return Rate: valid or reviewable cases the checker incorrectly recommended for return.
- Reviewer Override Rate: live reviewer decisions that changed the checker suggestion.

## Import Check

- Search the JSON for TODO_REVIEWER before import.
- Confirm source_checker_result metadata remains for audit traceability.
- Confirm every expected_layout item has page, type or id, normalized bbox when location matters, and min_iou when the default threshold is not enough.
- Confirm the System Administration quality summary shows zero reviewer TODOs and import_ready yes.
- Import the manifest from System Administration only after the checks above pass.
'''


def utcnow():
    return datetime.now(timezone.utc)


def list_datasets(filters=None):
    filters = filters or {}
    query = DocumentCheckerEvaluationDataset.query
    if filters.get('status'):
        query = query.filter(DocumentCheckerEvaluationDataset.status == filters['status'])
    if filters.get('dataset_type'):
        query = query.filter(DocumentCheckerEvaluationDataset.dataset_type == filters['dataset_type'])
    return query.order_by(
        DocumentCheckerEvaluationDataset.created_at.desc(),
        DocumentCheckerEvaluationDataset.id.desc(),
    ).all()


def create_dataset(data, *, user_id=None):
    dataset = _build_dataset(data, user_id=user_id)
    db.session.add(dataset)
    db.session.commit()
    return dataset


def get_dataset(dataset_id):
    dataset = db.session.get(DocumentCheckerEvaluationDataset, dataset_id)
    if not dataset:
        raise DocumentCheckerEvaluationError('Evaluation dataset not found.', 404)
    return dataset


def add_case(dataset_id, data, *, user_id=None):
    del user_id
    dataset = get_dataset(dataset_id)
    if dataset.status not in EDITABLE_DATASET_STATUSES:
        raise DocumentCheckerEvaluationError('Cases can only be added to draft or active datasets.', 409)

    if DocumentCheckerEvaluationCase.query.filter_by(dataset_id=dataset.id, case_key=_case_key(data)).first():
        raise DocumentCheckerEvaluationError('Evaluation case key already exists in this dataset.', 409)

    case = _build_case(dataset, data)
    db.session.add(case)
    db.session.commit()
    return case


def update_dataset_status(dataset_id, status, *, user_id=None):
    del user_id
    dataset = get_dataset(dataset_id)
    _validate_choice(status, {'draft', 'active', 'locked', 'archived'}, 'status')
    dataset.status = status
    dataset.updated_at = utcnow()
    db.session.commit()
    return dataset


def import_manifest(data, *, user_id=None):
    data = data or {}
    dataset_payload = data.get('dataset') or {}
    cases = data.get('cases') or []
    if not isinstance(cases, list):
        raise DocumentCheckerEvaluationError('cases must be a list.', 422)
    _ensure_manifest_is_adjudicated_if_required(dataset_payload)

    dataset = _build_dataset(dataset_payload, user_id=user_id)
    case_errors = _validate_manifest_cases(
        cases,
        require_adjudicated_labels=_requires_adjudicated_gold_labels(data, dataset_payload),
    )
    if case_errors:
        raise DocumentCheckerEvaluationError(
            'Manifest case validation failed.',
            422,
            {'cases': case_errors},
        )

    created_cases = []
    try:
        db.session.add(dataset)
        for case_payload in cases:
            case = _build_case(dataset, case_payload)
            db.session.add(case)
            created_cases.append(case)
        db.session.commit()
        return {
            'dataset': serialize_dataset(dataset),
            'cases': [serialize_case(case) for case in created_cases],
        }
    except Exception:
        db.session.rollback()
        raise


def build_gold_label_template(data=None):
    data = data or {}
    result_ids = _int_list(data.get('checker_result_ids') or data.get('result_ids'))
    limit = _bounded_int(data.get('limit'), default=25, minimum=1, maximum=100)

    query = DocumentComplianceResult.query
    if result_ids:
        query = query.filter(DocumentComplianceResult.id.in_(result_ids))
        results = query.all()
        result_by_id = {item.id: item for item in results}
        results = [result_by_id[result_id] for result_id in result_ids if result_id in result_by_id]
    else:
        results = query.order_by(
            DocumentComplianceResult.created_at.desc(),
            DocumentComplianceResult.id.desc(),
        ).limit(limit).all()

    cases = [
        _gold_label_template_case(result)
        for result in results
        if result.document_file_id and result.document_file
    ]
    if not cases:
        raise DocumentCheckerEvaluationError(
            'No checker results with linked document files were found for gold-label export.',
            404,
        )

    generated_at = utcnow()
    dataset_name = (data.get('dataset_name') or 'Human-Labeled DMS Checker Gold Dataset').strip()
    dataset_version = (data.get('dataset_version') or f'gold-labels-{generated_at:%Y.%m.%d.%H%M%S}').strip()
    filename = _safe_filename(f'{dataset_name}-{dataset_version}.json')
    manifest = {
        'template_type': GOLD_LABEL_TEMPLATE_TYPE,
        'template_version': GOLD_LABEL_TEMPLATE_VERSION,
        'generated_at': _isoformat(generated_at),
        'instructions': [
            'Human reviewers must replace every TODO value before import.',
            'Confirm labels from the document itself, not from checker suggestions alone.',
            'Set dataset.metadata.human_adjudication_completed to true only after review.',
            'Set dataset.metadata.pii_review_completed to true only after privacy/redaction review.',
            'Change each case label_source to reviewer_adjudicated and metadata.label_status to adjudicated after sign-off.',
            'Keep expected_annotations as normalized [x1, y1, x2, y2] boxes when layout evidence is labeled.',
            'Use expected_layout.layout_elements for reviewer-labeled headers, footers, signatories, tables, logos, and readable text zones.',
            'Use expected_layout.layout_issues for reviewer-labeled layout defects such as logo/header overlaps or messy table collisions.',
        ],
        'allowed_values': {
            'expected_evidence_type': sorted(rule_engine.SUPPORTED_EVIDENCE_TYPES),
            'expected_status': sorted(metrics.SUPPORTED_CHECKER_STATUSES),
            'expected_recommended_action': sorted(metrics.SUPPORTED_RECOMMENDED_ACTIONS),
            'label_confidence': ['low', 'medium', 'high'],
            'label_source': ['reviewer_adjudicated'],
            'metadata.label_status': ['adjudicated'],
            'expected_layout.layout_elements.type': [
                'header',
                'footer',
                'logo',
                'readable_text',
                'signatory',
                'stamp',
                'table',
                'title',
            ],
            'expected_layout.layout_issues.type': [
                'overlap',
                'collision',
                'missing_required_zone',
                'messy_layout',
                'unreadable_region',
            ],
        },
        'dataset': {
            'name': dataset_name,
            'description': 'Human-adjudicated benchmark labels for DMS checker accuracy testing.',
            'dataset_type': data.get('dataset_type') or 'reviewer_adjudicated',
            'version': dataset_version,
            'status': 'draft',
            'metadata': {
                'source': 'gold_label_template_export',
                'template_version': GOLD_LABEL_TEMPLATE_VERSION,
                'requires_human_adjudication': True,
                'human_adjudication_completed': False,
                'source_checker_result_ids': [case['metadata']['source_checker_result']['id'] for case in cases],
                'pii_review_required': True,
                'pii_review_completed': False,
            },
        },
        'cases': cases,
    }
    return {
        'filename': filename,
        'content_type': 'application/json',
        'manifest': manifest,
        'quality_summary': _gold_label_quality_summary(manifest),
    }


def list_gold_label_source_results(filters=None):
    filters = filters or {}
    limit = _bounded_int(filters.get('limit'), default=10, minimum=1, maximum=50)
    results = (
        DocumentComplianceResult.query
        .filter(DocumentComplianceResult.document_file_id.isnot(None))
        .order_by(
            DocumentComplianceResult.created_at.desc(),
            DocumentComplianceResult.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return [
        serialize_gold_label_source_result(result)
        for result in results
        if result.document_file is not None
    ]


def serialize_gold_label_source_result(result):
    document_file = result.document_file
    requirement = result.project_requirement
    project = requirement.project if requirement else None
    lgu = project.lgu if project else None
    findings = result.findings or []
    return {
        'id': result.id,
        'checker_result_id': result.id,
        'document_file_id': result.document_file_id,
        'submission_id': result.submission_id,
        'project_requirement_id': result.project_requirement_id,
        'file_name': document_file.file_name if document_file else None,
        'download_url': (
            f'/api/projects/files/{result.document_file_id}/download'
            if result.document_file_id else None
        ),
        'score': float(result.score) if result.score is not None else None,
        'status': result.status,
        'recommended_action': result.recommended_action,
        'checker_version': result.checker_version,
        'created_at': _isoformat(result.created_at),
        'finding_count': len(findings) if isinstance(findings, list) else 0,
        'requirement': {
            'id': requirement.id,
            'name': requirement.requirement_name,
            'annex_reference': requirement.annex_reference,
        } if requirement else None,
        'project': {
            'id': project.id,
            'name': project.project_name,
            'fiscal_year': project.fiscal_year,
            'lgu_id': project.lgu_id,
            'lgu_name': lgu.name if lgu else None,
        } if project else None,
    }


def build_completed_gold_label_sample():
    generated_at = utcnow()
    case_key = 'completed-gold-label-sample-001'
    expected_fields = {
        'lgu': 'Municipality of Santa Cruz',
        'fiscal_year': 2026,
        'amount': '1000.00',
        'reference_number': 'OR-2026-0001',
        'project_title': 'Barangay Road Improvement',
    }
    expected_layout = {
        'layout_elements': [
            {
                'id': 'sample_header_band',
                'type': 'header',
                'page': 1,
                'bbox': [0.05, 0.03, 0.95, 0.16],
                'min_iou': 0.5,
            },
            {
                'id': 'sample_amount_table',
                'type': 'table',
                'page': 1,
                'bbox': [0.10, 0.38, 0.90, 0.58],
                'min_iou': 0.5,
            },
            {
                'id': 'sample_signatory_block',
                'type': 'signatory',
                'page': 1,
                'bbox': [0.56, 0.72, 0.92, 0.90],
                'min_iou': 0.5,
            },
        ],
        'layout_issues': [
            {
                'id': 'logo_must_not_overlap_header_text',
                'type': 'overlap',
                'page': 1,
                'bbox': [0.10, 0.05, 0.18, 0.10],
                'min_iou': 0.5,
            },
        ],
    }
    manifest = {
        'template_type': GOLD_LABEL_TEMPLATE_TYPE,
        'template_version': GOLD_LABEL_TEMPLATE_VERSION,
        'sample_type': 'completed_gold_label_manifest_sample',
        'generated_at': _isoformat(generated_at),
        'dataset': {
            'name': 'Completed Reviewer Gold Labels Sample',
            'description': 'Valid completed sample for reviewer-adjudicated DMS checker benchmark labels.',
            'dataset_type': 'reviewer_adjudicated',
            'version': 'sample-v1',
            'status': 'active',
            'metadata': {
                'source': 'gold_label_template_export',
                'template_version': GOLD_LABEL_TEMPLATE_VERSION,
                'sample_manifest': True,
                'requires_human_adjudication': True,
                'human_adjudication_completed': True,
                'pii_review_required': True,
                'pii_review_completed': True,
            },
        },
        'cases': [
            {
                'case_key': case_key,
                'document_family': 'official_receipt',
                'ground_truth': {
                    'schema_version': metrics.GROUND_TRUTH_SCHEMA_VERSION,
                    'case_key': case_key,
                    'expected_evidence_type': 'official_receipt',
                    'expected_status': 'review_required',
                    'expected_recommended_action': 'review_required',
                    'expected_fields': expected_fields,
                    'expected_findings': ['layout_overlap:logo_must_not_overlap_header_text'],
                    'forbidden_findings': ['field_missing:amount'],
                    'expected_annotations': [
                        {
                            'finding_id': 'layout_header_present',
                            'page': 1,
                            'bbox': [0.05, 0.03, 0.95, 0.16],
                            'min_iou': 0.5,
                        },
                    ],
                    'expected_layout': expected_layout,
                },
                'pii_redacted': True,
                'label_source': 'reviewer_adjudicated',
                'label_confidence': 'high',
                'metadata': {
                    'label_status': 'adjudicated',
                    'reviewer_notes': 'Sample only. Replace with reviewer-confirmed evidence from the real document.',
                    'source_checker_result': {
                        'id': 'sample-checker-result',
                        'status': 'review_required',
                        'recommended_action': 'review_required',
                        'score': 88,
                    },
                    'fixture_checker_output': {
                        'status': 'review_required',
                        'recommended_action': 'review_required',
                        'extracted_fields': expected_fields,
                        'findings': [
                            {
                                'id': 'layout_overlap:logo_must_not_overlap_header_text',
                                'severity': 'warning',
                                'locations': [
                                    {
                                        'page': 1,
                                        'bbox': {'x': 0.10, 'y': 0.05, 'width': 0.08, 'height': 0.05},
                                    },
                                ],
                            },
                        ],
                        'score_details': {
                            'evidence_type': 'official_receipt',
                            'policy_version': rule_engine.POLICY_VERSION,
                        },
                        'layout': {
                            'layout_elements': expected_layout['layout_elements'],
                        },
                        'annotations': [
                            {
                                'finding_id': 'layout_header_present',
                                'page': 1,
                                'bbox': [0.05, 0.03, 0.95, 0.16],
                            },
                        ],
                    },
                },
            },
        ],
    }
    return {
        'filename': 'dms-checker-completed-gold-label-sample.json',
        'content_type': 'application/json',
        'manifest': manifest,
        'quality_summary': _gold_label_quality_summary(manifest),
    }


def build_gold_label_reviewer_guide():
    return {
        'filename': 'dms-checker-gold-label-reviewer-guide.md',
        'content_type': 'text/markdown',
        'markdown': GOLD_LABEL_REVIEWER_GUIDE_MARKDOWN,
        'guide_version': GOLD_LABEL_TEMPLATE_VERSION,
    }


def list_runs(filters=None):
    filters = filters or {}
    query = DocumentCheckerEvaluationRun.query
    if filters.get('dataset_id'):
        query = query.filter(DocumentCheckerEvaluationRun.dataset_id == filters['dataset_id'])
    if filters.get('status'):
        query = query.filter(DocumentCheckerEvaluationRun.status == filters['status'])
    return query.order_by(
        DocumentCheckerEvaluationRun.created_at.desc(),
        DocumentCheckerEvaluationRun.id.desc(),
    ).all()


def create_run(dataset_id, data, *, user_id=None):
    dataset = get_dataset(dataset_id)
    if dataset.status not in RUNNABLE_DATASET_STATUSES:
        raise DocumentCheckerEvaluationError('Benchmark runs require an active or locked dataset.', 409)

    data = data or {}
    run_name = (data.get('run_name') or f'{dataset.name} {dataset.version} benchmark').strip()
    if not run_name:
        raise DocumentCheckerEvaluationError('run_name is required.', 422)

    run = DocumentCheckerEvaluationRun(
        dataset_id=dataset.id,
        run_name=run_name,
        status='queued',
        checker_version=(data.get('checker_version') or 'document_compliance_v1').strip(),
        rule_policy_version=(data.get('rule_policy_version') or rule_engine.POLICY_VERSION).strip(),
        provider_config=_json_object(data.get('provider_config')),
        reference_profile_snapshot=_json_object(data.get('reference_profile_snapshot')),
        started_by=_optional_int(user_id),
        run_metadata=_json_object(data.get('metadata') or data.get('run_metadata')),
    )
    db.session.add(run)
    db.session.commit()
    return run


def get_run(run_id):
    run = db.session.get(DocumentCheckerEvaluationRun, run_id)
    if not run:
        raise DocumentCheckerEvaluationError('Evaluation run not found.', 404)
    return run


def get_result(result_id):
    result = db.session.get(DocumentCheckerEvaluationResult, result_id)
    if not result:
        raise DocumentCheckerEvaluationError('Evaluation result not found.', 404)
    return result


def build_run_report(run_id):
    run = get_run(run_id)
    dataset = run.dataset
    metrics_payload = run.summary_metrics or {}
    gates = metrics_payload.get('gates') or []
    failed_results = run.results.filter_by(passed=False).order_by(DocumentCheckerEvaluationResult.id.asc()).all()
    title = f'DMS Checker Evaluation Report - {run.run_name}'
    lines = [
        f'# {title}',
        '',
        'This report is internal evaluation evidence for COMET System Administrators and capstone review. It is advisory and must not approve live DMS submissions automatically.',
        '',
        '## Run Context',
        '',
        f'- Dataset: {dataset.name} `{dataset.version}`',
        f'- Dataset type: {dataset.dataset_type}',
        f'- Dataset status: {dataset.status}',
        f'- Run status: {run.status}',
        f'- Checker version: {run.checker_version or "Not recorded"}',
        f'- Rule policy version: {run.rule_policy_version or "Not recorded"}',
        f'- Started at: {_isoformat(run.started_at) or "Not started"}',
        f'- Completed at: {_isoformat(run.completed_at) or "Not completed"}',
        '',
        '## Summary Metrics',
        '',
        _markdown_table(
            ['Metric', 'Value'],
            [
                ['Total cases', metrics_payload.get('total_cases')],
                ['Passed cases', metrics_payload.get('passed_cases')],
                ['Failed cases', metrics_payload.get('failed_cases')],
                ['Status match rate', _format_percent(metrics_payload.get('status_match_rate'))],
                ['False approval rate', _format_percent(metrics_payload.get('false_approval_rate'))],
                ['False return rate', _format_percent(metrics_payload.get('false_return_rate'))],
                ['Evidence type F1', _format_percent((metrics_payload.get('evidence_type') or {}).get('f1'))],
                ['Mapping F1', _format_percent(metrics_payload.get('mapping_f1'))],
                ['Mapping support', metrics_payload.get('mapping_support')],
                ['Mapping top-k accuracy', _format_percent(metrics_payload.get('mapping_top_k_accuracy'))],
                ['False mapping rate', _format_percent(metrics_payload.get('false_mapping_rate'))],
                ['OCR Character Error Rate', _format_percent(metrics_payload.get('ocr_cer'))],
                ['OCR CER labeled support', metrics_payload.get('ocr_cer_support')],
                ['OCR Word Error Rate', _format_percent(metrics_payload.get('ocr_wer'))],
                ['OCR WER labeled support', metrics_payload.get('ocr_wer_support')],
                ['Readable-text rate', _format_percent(metrics_payload.get('readable_text_rate'))],
                ['Readable-text support', metrics_payload.get('readable_text_support')],
                ['OCR extraction failure rate', _format_percent(metrics_payload.get('ocr_extraction_failure_rate'))],
                ['OCR extraction failure support', metrics_payload.get('ocr_extraction_failure_support')],
                ['OCR confidence average', _format_percent(metrics_payload.get('ocr_confidence_average'))],
                ['Field precision', _format_percent(metrics_payload.get('field_precision'))],
                ['Field recall', _format_percent(metrics_payload.get('field_recall'))],
                ['Annotation location accuracy', _format_percent(metrics_payload.get('annotation_location_accuracy'))],
                ['Layout element F1', _format_percent(metrics_payload.get('layout_element_f1'))],
                ['Layout element labeled support', metrics_payload.get('layout_element_support')],
                ['Overlap detection F1', _format_percent(metrics_payload.get('overlap_detection_f1'))],
                ['Overlap issue labeled support', metrics_payload.get('overlap_detection_support')],
                ['Format blocker false-positive rate', _format_percent(metrics_payload.get('format_blocker_false_positive_rate'))],
            ],
        ),
    ]
    lines.extend(_benchmark_drift_report_lines(run))

    field_rows = _field_breakdown_rows(metrics_payload)
    if field_rows:
        lines.extend([
            '',
            '## Field Extraction Breakdown',
            '',
            _markdown_table(
                ['Field', 'Precision', 'Recall', 'F1', 'Support'],
                field_rows,
            ),
            '',
        ])

    compliance_rows = _compliance_quality_rows(metrics_payload)
    if compliance_rows:
        lines.extend([
            '',
            '## Compliance Quality Breakdown',
            '',
            _markdown_table(
                ['Risk', 'Count', 'Support', 'Rate'],
                compliance_rows,
            ),
            '',
        ])

    blocker_rows = _blocker_finding_rows(metrics_payload)
    if blocker_rows:
        lines.extend([
            '## Blocker Finding Breakdown',
            '',
            _markdown_table(
                ['Finding', 'False positives', 'False negatives'],
                blocker_rows,
            ),
            '',
        ])

    lines.extend([
        '',
        '## Accuracy Gates',
        '',
    ])
    if gates:
        lines.append(_markdown_table(
            ['Gate', 'Status', 'Actual', 'Target', 'Support', 'Message'],
            [
                [
                    gate.get('label') or gate.get('id'),
                    gate.get('status'),
                    _format_metric_value(gate.get('actual')),
                    gate.get('target') or 'Not set',
                    gate.get('support'),
                    gate.get('message') or '',
                ]
                for gate in gates
            ],
        ))
    else:
        lines.append('No accuracy gates were recorded for this run.')

    lines.extend([
        '',
        '## Failed Cases',
        '',
    ])
    if failed_results:
        lines.append(_markdown_table(
            ['Case', 'Family', 'Expected', 'Predicted', 'Reasons'],
            [
                [
                    result.case.case_key if result.case else result.case_id,
                    result.case.document_family if result.case else '',
                    ((result.metric_breakdown or {}).get('status') or {}).get('expected_status'),
                    ((result.metric_breakdown or {}).get('status') or {}).get('predicted_status'),
                    ', '.join(result.failure_reasons or []),
                ]
                for result in failed_results
            ],
        ))
    else:
        lines.append('No failed benchmark cases were recorded.')

    lines.extend([
        '',
        '## Governance Notes',
        '',
        '- Benchmark reports are advisory measurement artifacts.',
        '- Reviewer feedback metrics are operational signals and are separate from benchmark accuracy.',
        '- A passing benchmark must not bypass human reviewer authority.',
        '',
    ])
    markdown = '\n'.join(lines)
    return {
        'filename': f'dms-checker-evaluation-run-{run.id}.md',
        'content_type': 'text/markdown',
        'markdown': markdown,
    }


def _system_history(metadata, key):
    history = metadata.get(key)
    if not isinstance(history, list):
        return []
    return [item for item in history if isinstance(item, dict)]


def _record_release_history(metadata, *, released_by, released_at, report_version, notes):
    history = _system_history(metadata, 'release_history')
    history.append({
        'released_by': released_by,
        'released_at': released_at,
        'report_version': report_version,
        'notes': notes,
    })
    metadata['release_history'] = history[-50:]


def _record_revocation_history(metadata, *, revoked_by, revoked_at, report_version, notes):
    history = _system_history(metadata, 'revocation_history')
    history.append({
        'revoked_by': revoked_by,
        'revoked_at': revoked_at,
        'report_version': report_version,
        'notes': notes,
    })
    metadata['revocation_history'] = history[-50:]


def _merged_release_metadata(existing_metadata, incoming_metadata):
    existing_metadata = existing_metadata or {}
    incoming_metadata = incoming_metadata or {}
    metadata = {
        **existing_metadata,
        **incoming_metadata,
    }
    metadata['release_history'] = _system_history(existing_metadata, 'release_history')
    metadata['revocation_history'] = _system_history(existing_metadata, 'revocation_history')
    return metadata


def release_run_report(run_id, data=None, *, user_id=None):
    run = get_run(run_id)
    if run.status not in RELEASABLE_RUN_STATUSES:
        raise DocumentCheckerEvaluationError('Only completed benchmark runs can be released.', 409)

    data = data or {}
    now = utcnow()
    releaser_id = _optional_int(user_id)
    report_version = str(data.get('report_version') or f'run-{run.id}-v1').strip()
    release_notes = data.get('release_notes')
    if release_notes is not None:
        release_notes = str(release_notes).strip() or None

    snapshot = get_run_metric_snapshot(run.id)
    metadata_input = data.get('metadata') if 'metadata' in data else data.get('release_metadata')
    release_metadata = _json_object(metadata_input)
    release_metadata.setdefault('dataset_id', run.dataset_id)
    release_metadata.setdefault('checker_version', run.checker_version)
    release_metadata.setdefault('rule_policy_version', run.rule_policy_version)
    if snapshot:
        release_metadata.setdefault('metric_snapshot_id', snapshot.id)

    release = DocumentCheckerReleasedReport.query.filter_by(run_id=run.id).first()
    metadata = _merged_release_metadata(release.release_metadata if release else {}, release_metadata)
    _record_release_history(
        metadata,
        released_by=releaser_id,
        released_at=_isoformat(now),
        report_version=report_version,
        notes=release_notes,
    )
    if release:
        release.status = 'released'
        release.report_version = report_version or release.report_version
        if 'release_notes' in data:
            release.release_notes = release_notes
        release.release_metadata = metadata
        release.released_by = releaser_id
        release.released_at = now
        release.updated_at = now
    else:
        release = DocumentCheckerReleasedReport(
            run_id=run.id,
            status='released',
            report_version=report_version or 'v1',
            release_notes=release_notes,
            release_metadata=metadata,
            released_by=releaser_id,
            released_at=now,
        )
        db.session.add(release)

    db.session.commit()
    return release


def revoke_run_report(run_id, data=None, *, user_id=None):
    release = DocumentCheckerReleasedReport.query.filter_by(run_id=run_id).first()
    if not release:
        raise DocumentCheckerEvaluationError('Released benchmark report not found.', 404)
    if release.status != 'released':
        raise DocumentCheckerEvaluationError('Benchmark report release is already revoked.', 409)

    data = data or {}
    now = utcnow()
    revoker_id = _optional_int(user_id)
    revocation_notes = data.get('revocation_notes')
    if revocation_notes is not None:
        revocation_notes = str(revocation_notes).strip() or None

    metadata_input = data.get('metadata') if 'metadata' in data else data.get('release_metadata')
    metadata = _merged_release_metadata(release.release_metadata or {}, _json_object(metadata_input))
    revoked_at = _isoformat(now)
    metadata['revoked_by'] = revoker_id
    metadata['revoked_at'] = revoked_at
    if 'revocation_notes' in data:
        metadata['revocation_notes'] = revocation_notes

    _record_revocation_history(
        metadata,
        revoked_by=revoker_id,
        revoked_at=revoked_at,
        report_version=release.report_version,
        notes=revocation_notes,
    )

    release.status = 'revoked'
    release.release_metadata = metadata
    release.updated_at = now
    db.session.commit()
    return release


def list_released_reports(filters=None):
    filters = filters or {}
    limit = _bounded_int(filters.get('limit'), default=20, minimum=1, maximum=100)
    query = DocumentCheckerReleasedReport.query.filter_by(status='released')
    if filters.get('run_id'):
        query = query.filter(DocumentCheckerReleasedReport.run_id == filters['run_id'])
    if filters.get('dataset_id'):
        query = query.join(DocumentCheckerEvaluationRun).filter(
            DocumentCheckerEvaluationRun.dataset_id == filters['dataset_id']
        )
    return query.order_by(
        DocumentCheckerReleasedReport.released_at.desc(),
        DocumentCheckerReleasedReport.id.desc(),
    ).limit(limit).all()


def get_released_report(run_id):
    release = DocumentCheckerReleasedReport.query.filter_by(run_id=run_id, status='released').first()
    if not release:
        raise DocumentCheckerEvaluationError('Released benchmark report not found.', 404)
    return release


def is_run_report_released(run_id):
    return DocumentCheckerReleasedReport.query.filter_by(run_id=run_id, status='released').first() is not None


def get_run_metric_snapshot(run_id):
    return DocumentCheckerMetricSnapshot.query.filter_by(run_id=run_id).order_by(
        DocumentCheckerMetricSnapshot.created_at.desc(),
        DocumentCheckerMetricSnapshot.id.desc(),
    ).first()


def _previous_metric_snapshot(snapshot):
    if not snapshot:
        return None
    query = DocumentCheckerMetricSnapshot.query.filter(
        DocumentCheckerMetricSnapshot.dataset_id == snapshot.dataset_id,
        DocumentCheckerMetricSnapshot.id != snapshot.id,
    )
    if snapshot.created_at:
        query = query.filter(or_(
            DocumentCheckerMetricSnapshot.created_at < snapshot.created_at,
            and_(
                DocumentCheckerMetricSnapshot.created_at == snapshot.created_at,
                DocumentCheckerMetricSnapshot.id < snapshot.id,
            ),
        ))
    return query.order_by(
        DocumentCheckerMetricSnapshot.created_at.desc(),
        DocumentCheckerMetricSnapshot.id.desc(),
    ).first()


def _benchmark_drift_report_lines(run):
    current_snapshot = get_run_metric_snapshot(run.id)
    previous_snapshot = _previous_metric_snapshot(current_snapshot)
    lines = [
        '',
        '## Benchmark Drift',
        '',
    ]
    if not current_snapshot:
        lines.append('No metric snapshot was recorded for this run, so drift could not be calculated.')
        return lines
    if not previous_snapshot:
        lines.append('No previous benchmark snapshot was available for this dataset, so drift could not be calculated.')
        return lines

    lines.extend([
        'This comparison treats the exported run as the current approved benchmark and the previous snapshot for the same dataset as the baseline.',
        '',
        f'- Current snapshot: {_snapshot_label(current_snapshot)}',
        f'- Previous snapshot: {_snapshot_label(previous_snapshot)}',
        '',
        _markdown_table(
            ['Metric', 'Current', 'Previous', 'Delta', 'Direction', 'Assessment'],
            _benchmark_drift_rows(current_snapshot, previous_snapshot),
        ),
    ])
    return lines


def _benchmark_drift_rows(current_snapshot, previous_snapshot):
    rows = []
    for definition in BENCHMARK_DRIFT_METRICS:
        current_value = _to_float(definition['value'](current_snapshot))
        previous_value = _to_float(definition['value'](previous_snapshot))
        delta = (
            current_value - previous_value
            if current_value is not None and previous_value is not None
            else None
        )
        rows.append([
            definition['label'],
            _format_percent(current_value),
            _format_percent(previous_value),
            _format_point_delta(delta),
            'Lower is better' if definition['direction'] == 'lower' else 'Higher is better',
            _drift_assessment(delta, definition['direction']),
        ])
    return rows


def _snapshot_metric(snapshot, key):
    if not snapshot:
        return None
    return (snapshot.metrics or {}).get(key)


def _snapshot_pass_rate(snapshot):
    metric_value = _snapshot_metric(snapshot, 'pass_rate')
    if metric_value is not None:
        return metric_value
    metrics_payload = snapshot.metrics or {}
    return _safe_ratio(metrics_payload.get('passed_cases') or 0, metrics_payload.get('total_cases') or 0)


def _snapshot_gate_pass_rate(snapshot):
    if not snapshot:
        return None
    gates = [
        gate
        for gate in (snapshot.gates or [])
        if str(gate.get('status') or '').lower() != 'not_applicable'
    ]
    if not gates:
        return None
    passed = sum(1 for gate in gates if str(gate.get('status') or '').lower() == 'passed')
    return _safe_ratio(passed, len(gates))


def _snapshot_label(snapshot):
    label = f'Run #{snapshot.run_id}' if snapshot.run_id else f'Snapshot #{snapshot.id}'
    timestamp = _isoformat(snapshot.created_at)
    return f'{label} ({timestamp})' if timestamp else label


def _format_point_delta(value):
    value = _to_float(value)
    if value is None:
        return 'Not measured'
    sign = '+' if value > 0 else '-' if value < 0 else ''
    return f'{sign}{abs(value) * 100:.1f} pp'


def _drift_assessment(delta, direction):
    delta = _to_float(delta)
    if delta is None:
        return 'Not measured'
    if abs(delta) < 0.001:
        return 'Stable'
    improved = delta < 0 if direction == 'lower' else delta > 0
    return 'Improved' if improved else 'Regressed'


def run_evaluation(run_id, *, checker_runner=None, user_id=None, min_gate_support=DEFAULT_MIN_GATE_SUPPORT):
    run = get_run(run_id)
    if run.status == 'running':
        raise DocumentCheckerEvaluationError('Evaluation run is already running.', 409)
    if run.status in {'completed', 'completed_with_failures'} and run.results.count():
        raise DocumentCheckerEvaluationError('Evaluation run has already completed.', 409)

    starter_id = _optional_int(user_id)
    cases = run.dataset.cases.order_by(DocumentCheckerEvaluationCase.id.asc()).all()
    run.status = 'running'
    if starter_id is not None:
        run.started_by = starter_id
    run.started_at = run.started_at or utcnow()
    db.session.commit()

    results = []
    try:
        for case in cases:
            results.append(evaluate_case(run, case, checker_runner=checker_runner))
        summary = aggregate_results(results)
        summary['gates'] = evaluate_accuracy_gates(summary, min_support=min_gate_support)
        run.summary_metrics = summary
        run.completed_at = utcnow()
        run.status = 'completed' if summary.get('failed_cases') == 0 else 'completed_with_failures'
        snapshot = DocumentCheckerMetricSnapshot(
            dataset_id=run.dataset_id,
            run_id=run.id,
            snapshot_type='latest_run',
            metrics=summary,
            gates=summary['gates'],
            created_by=run.started_by,
        )
        db.session.add(snapshot)
        db.session.commit()
        return run
    except Exception:
        db.session.rollback()
        failed_run = db.session.get(DocumentCheckerEvaluationRun, run_id)
        if failed_run:
            failed_run.status = 'failed'
            failed_run.completed_at = utcnow()
            db.session.commit()
        raise


def evaluate_case(run, case, *, checker_runner=None):
    checker_result_id = None
    try:
        checker_output = _run_checker_for_case(case, run, checker_runner=checker_runner)
        checker_result_id = _checker_result_id(checker_output)
        metric_breakdown = metrics.compare_checker_output(case.ground_truth or {}, checker_output)
        passed = bool(metric_breakdown.get('passed'))
        failure_reasons = _failure_reasons(metric_breakdown)
    except Exception as exc:
        checker_output = {
            'status': 'check_failed',
            'recommended_action': 'manual_review',
            'error': str(exc),
        }
        metric_breakdown = {
            'case_key': case.case_key,
            'passed': False,
            'error': str(exc),
        }
        passed = False
        failure_reasons = ['checker_exception']

    result = DocumentCheckerEvaluationResult(
        run_id=run.id,
        case_id=case.id,
        checker_result_id=checker_result_id,
        expected_output=case.ground_truth or {},
        predicted_output=checker_output,
        metric_breakdown=metric_breakdown,
        passed=passed,
        failure_reasons=failure_reasons,
    )
    db.session.add(result)
    db.session.flush()
    return result


def aggregate_results(results):
    results = list(results or [])
    breakdowns = [result.metric_breakdown or {} for result in results]
    total_cases = len(results)
    passed_cases = sum(1 for result in results if result.passed)
    failed_cases = total_cases - passed_cases

    status_items = [item.get('status') or {} for item in breakdowns]
    false_approval_count = sum(1 for item in status_items if item.get('false_approval'))
    false_return_count = sum(1 for item in status_items if item.get('false_return'))
    false_approval_support = sum(
        1 for item in status_items
        if item.get('expected_status') and item.get('expected_status') != 'ready_for_approval'
    )
    false_return_support = sum(
        1 for item in status_items
        if item.get('expected_status') in {'ready_for_approval', 'review_required'}
    )
    status_match_count = sum(1 for item in status_items if item.get('status_match'))

    evidence_type = _aggregate_evidence_type(breakdowns)
    mapping = _aggregate_mapping(breakdowns)
    ocr = _aggregate_ocr(breakdowns)
    fields = _aggregate_fields(breakdowns)
    findings = _aggregate_findings(breakdowns)
    compliance_quality = _aggregate_compliance_quality(results)
    annotations = _aggregate_annotations(breakdowns)
    layout = _aggregate_layout(breakdowns)
    format_blockers = _aggregate_format_blockers(results)
    scanned_image_safety = _aggregate_scanned_image_safety(results)
    advisory_boundary = _aggregate_advisory_boundary(results)

    return {
        'total_cases': total_cases,
        'completed_cases': total_cases,
        'passed_cases': passed_cases,
        'failed_cases': failed_cases,
        'pass_rate': _safe_ratio(passed_cases, total_cases),
        'status_match_rate': _safe_ratio(status_match_count, total_cases),
        'false_approval_count': false_approval_count,
        'false_approval_support': false_approval_support,
        'false_approval_rate': _safe_ratio(false_approval_count, false_approval_support),
        'false_return_count': false_return_count,
        'false_return_support': false_return_support,
        'false_return_rate': _safe_ratio(false_return_count, false_return_support),
        'critical_blocker_false_positive_count': findings['critical_blocker_false_positive_count'],
        'critical_blocker_false_positive_support': findings['critical_blocker_false_positive_support'],
        'critical_blocker_false_positive_rate': findings['critical_blocker_false_positive_rate'],
        'critical_blocker_false_negative_count': findings['critical_blocker_false_negative_count'],
        'critical_blocker_false_negative_support': findings['critical_blocker_false_negative_support'],
        'critical_blocker_false_negative_rate': findings['critical_blocker_false_negative_rate'],
        'compliance_quality': compliance_quality,
        'blocker_false_positive_count': compliance_quality['blocker_false_positive']['count'],
        'blocker_false_positive_support': compliance_quality['blocker_false_positive']['support'],
        'blocker_false_positive_rate': compliance_quality['blocker_false_positive']['rate'],
        'blocker_false_negative_count': compliance_quality['blocker_false_negative']['count'],
        'blocker_false_negative_support': compliance_quality['blocker_false_negative']['support'],
        'blocker_false_negative_rate': compliance_quality['blocker_false_negative']['rate'],
        'evidence_type': evidence_type,
        'mapping': mapping,
        'mapping_f1': mapping['aggregate']['f1'],
        'mapping_precision': mapping['aggregate']['precision'],
        'mapping_recall': mapping['aggregate']['recall'],
        'mapping_support': mapping['aggregate']['support'],
        'mapping_top_k_accuracy': mapping['top_k_accuracy'],
        'mapping_top_k_support': mapping['top_k_support'],
        'false_mapping_count': mapping['false_mapping_count'],
        'false_mapping_rate': mapping['false_mapping_rate'],
        'false_mapping_support': mapping['false_mapping_support'],
        'ocr': ocr,
        'ocr_cer': ocr['cer'],
        'ocr_cer_support': ocr['cer_support'],
        'ocr_wer': ocr['wer'],
        'ocr_wer_support': ocr['wer_support'],
        'readable_text_rate': ocr['readable_text_rate'],
        'readable_text_support': ocr['readable_text_support'],
        'ocr_extraction_failure_count': ocr['extraction_failure_count'],
        'ocr_extraction_failure_rate': ocr['extraction_failure_rate'],
        'ocr_extraction_failure_support': ocr['extraction_failure_support'],
        'ocr_confidence_average': ocr['confidence_average'],
        'fields': fields,
        'field_precision': fields['aggregate']['precision'],
        'field_precision_support': fields['aggregate']['true_positive'] + fields['aggregate']['false_positive'],
        'field_recall': fields['aggregate']['recall'],
        'field_recall_support': fields['aggregate']['support'],
        **_field_flat_metrics(fields),
        'annotations': annotations,
        'annotation_location_accuracy': annotations['accuracy'],
        'annotation_location_support': annotations['support'],
        'layout': layout,
        'layout_element_f1': layout['elements']['aggregate']['f1'],
        'layout_element_support': layout['elements']['aggregate']['support'],
        'overlap_detection_f1': layout['overlap_issues']['aggregate']['f1'],
        'overlap_detection_support': layout['overlap_issues']['aggregate']['support'],
        'format_blocker_false_positive_count': format_blockers['false_positive_count'],
        'format_blocker_false_positive_rate': format_blockers['false_positive_rate'],
        'format_blocker_false_positive_support': format_blockers['support'],
        'scanned_unavailable_ready_count': scanned_image_safety['ready_count'],
        'scanned_unavailable_support': scanned_image_safety['support'],
        'advisory_override_count': advisory_boundary['override_count'],
        'advisory_override_support': advisory_boundary['support'],
    }


def evaluate_accuracy_gates(summary, *, min_support=DEFAULT_MIN_GATE_SUPPORT):
    summary = summary or {}
    evidence_type = summary.get('evidence_type') or {}
    return [
        _gate_at_least(
            'evidence_type_f1',
            'Evidence type classification F1',
            evidence_type.get('f1'),
            0.90,
            evidence_type.get('support'),
            min_support,
        ),
        _gate_at_least(
            'mapping_f1',
            'Document mapping F1',
            summary.get('mapping_f1'),
            0.90,
            summary.get('mapping_support'),
            min_support,
        ),
        _gate_at_least(
            'mapping_top_k_accuracy',
            'Document mapping top-k accuracy',
            summary.get('mapping_top_k_accuracy'),
            0.95,
            summary.get('mapping_top_k_support'),
            min_support,
        ),
        _gate_at_most(
            'false_mapping_rate',
            'False mapping rate',
            summary.get('false_mapping_rate'),
            0.05,
            summary.get('false_mapping_support'),
            min_support,
        ),
        _gate_at_most(
            'critical_blocker_false_positive_rate',
            'Critical blocker false-positive rate',
            summary.get('critical_blocker_false_positive_rate'),
            0.05,
            summary.get('critical_blocker_false_positive_support'),
            min_support,
        ),
        _gate_at_most(
            'critical_blocker_false_negative_rate',
            'Critical blocker false-negative rate',
            summary.get('critical_blocker_false_negative_rate'),
            0.05,
            summary.get('critical_blocker_false_negative_support'),
            min_support,
        ),
        _gate_at_most(
            'ocr_cer',
            'OCR Character Error Rate',
            summary.get('ocr_cer'),
            0.05,
            summary.get('ocr_cer_support'),
            min_support,
        ),
        _gate_at_most(
            'ocr_wer',
            'OCR Word Error Rate',
            summary.get('ocr_wer'),
            0.10,
            summary.get('ocr_wer_support'),
            min_support,
        ),
        _gate_at_least(
            'readable_text_rate',
            'Readable-text rate',
            summary.get('readable_text_rate'),
            0.95,
            summary.get('readable_text_support'),
            min_support,
        ),
        _gate_at_most(
            'ocr_extraction_failure_rate',
            'OCR extraction failure rate',
            summary.get('ocr_extraction_failure_rate'),
            0.05,
            summary.get('ocr_extraction_failure_support'),
            min_support,
        ),
        _gate_at_least(
            'field_precision',
            'LGU/date/amount/reference field precision',
            summary.get('field_precision'),
            0.90,
            summary.get('field_precision_support'),
            min_support,
        ),
        _gate_at_most(
            'format_blocker_false_positive_rate',
            'Format blocker false-positive rate',
            summary.get('format_blocker_false_positive_rate'),
            0.08,
            summary.get('format_blocker_false_positive_support'),
            min_support,
        ),
        _gate_at_least(
            'annotation_location_accuracy',
            'Annotation location accuracy',
            summary.get('annotation_location_accuracy'),
            0.90,
            summary.get('annotation_location_support'),
            min_support,
        ),
        _gate_at_least(
            'layout_element_f1',
            'Layout element detection F1',
            summary.get('layout_element_f1'),
            0.85,
            summary.get('layout_element_support'),
            min_support,
        ),
        _gate_at_least(
            'overlap_detection_f1',
            'Layout overlap detection F1',
            summary.get('overlap_detection_f1'),
            0.85,
            summary.get('overlap_detection_support'),
            min_support,
        ),
        _zero_count_gate(
            'scanned_image_safety',
            'No ready result when scanned/image-only extraction is unavailable',
            summary.get('scanned_unavailable_ready_count'),
            summary.get('scanned_unavailable_support'),
            min_support,
        ),
        _zero_count_gate(
            'advisory_boundary',
            'Provider/LLM advisory output never overrides deterministic status',
            summary.get('advisory_override_count'),
            summary.get('advisory_override_support'),
            min_support,
        ),
    ]


def get_summary(filters=None):
    filters = filters or {}
    query = DocumentCheckerMetricSnapshot.query
    if filters.get('dataset_id'):
        query = query.filter(DocumentCheckerMetricSnapshot.dataset_id == filters['dataset_id'])
    latest_snapshot = query.order_by(
        DocumentCheckerMetricSnapshot.created_at.desc(),
        DocumentCheckerMetricSnapshot.id.desc(),
    ).first()
    return {
        'dataset_count': DocumentCheckerEvaluationDataset.query.count(),
        'case_count': DocumentCheckerEvaluationCase.query.count(),
        'run_count': DocumentCheckerEvaluationRun.query.count(),
        'latest_snapshot': serialize_metric_snapshot(latest_snapshot) if latest_snapshot else None,
    }


def list_failed_results(filters=None):
    filters = filters or {}
    limit = min(int(filters.get('limit') or 50), 200)
    query = DocumentCheckerEvaluationResult.query.filter_by(passed=False)
    if filters.get('run_id'):
        query = query.filter(DocumentCheckerEvaluationResult.run_id == filters['run_id'])
    if filters.get('dataset_id'):
        query = query.join(DocumentCheckerEvaluationRun).filter(
            DocumentCheckerEvaluationRun.dataset_id == filters['dataset_id']
        )
    return query.order_by(
        DocumentCheckerEvaluationResult.created_at.desc(),
        DocumentCheckerEvaluationResult.id.desc(),
    ).limit(limit).all()


def list_metric_trends(filters=None):
    filters = filters or {}
    limit = min(int(filters.get('limit') or 50), 200)
    query = DocumentCheckerMetricSnapshot.query
    if filters.get('dataset_id'):
        query = query.filter(DocumentCheckerMetricSnapshot.dataset_id == filters['dataset_id'])
    return query.order_by(
        DocumentCheckerMetricSnapshot.created_at.desc(),
        DocumentCheckerMetricSnapshot.id.desc(),
    ).limit(limit).all()


def get_reviewer_feedback_summary(filters=None):
    filters = filters or {}
    del filters
    results = DocumentComplianceResult.query.filter(
        DocumentComplianceResult.score_details.isnot(None)
    ).all()
    counts = {
        'accept_checker_result': 0,
        'override_approve': 0,
        'override_return': 0,
        'mark_false_positive': 0,
        'mark_checker_missed_evidence': 0,
    }
    reason_counts = {}
    total = 0
    for result in results:
        decision = ((result.score_details or {}).get('reviewer_decision') or {})
        decision_key = decision.get('decision')
        if not decision_key:
            continue
        total += 1
        if decision_key in counts:
            counts[decision_key] += 1
        for reason in decision.get('reason_codes') or []:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    override_total = (
        counts['override_approve']
        + counts['override_return']
        + counts['mark_false_positive']
        + counts['mark_checker_missed_evidence']
    )
    return {
        'total_reviewer_decisions': total,
        'accepted_checker_result': counts['accept_checker_result'],
        'override_approve': counts['override_approve'],
        'override_return': counts['override_return'],
        'checker_false_positive': counts['mark_false_positive'],
        'checker_missed_evidence': counts['mark_checker_missed_evidence'],
        'acceptance_rate': _safe_ratio(counts['accept_checker_result'], total),
        'override_rate': _safe_ratio(override_total, total),
        'top_reason_codes': [
            {'reason_code': reason, 'count': count}
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def serialize_dataset(dataset):
    if not dataset:
        return None
    return {
        'id': dataset.id,
        'name': dataset.name,
        'description': dataset.description,
        'dataset_type': dataset.dataset_type,
        'version': dataset.version,
        'status': dataset.status,
        'metadata': dataset.dataset_metadata or {},
        'case_count': dataset.cases.count() if dataset.id else 0,
        'run_count': dataset.runs.count() if dataset.id else 0,
        'created_by': dataset.created_by,
        'created_at': _isoformat(dataset.created_at),
        'updated_at': _isoformat(dataset.updated_at),
    }


def serialize_case(case):
    if not case:
        return None
    return {
        'id': case.id,
        'dataset_id': case.dataset_id,
        'document_file_id': case.document_file_id,
        'case_key': case.case_key,
        'document_family': case.document_family,
        'requirement_id': case.requirement_id,
        'program_id': case.program_id,
        'fiscal_year': case.fiscal_year,
        'ground_truth': case.ground_truth or {},
        'pii_redacted': case.pii_redacted,
        'label_source': case.label_source,
        'label_confidence': case.label_confidence,
        'metadata': case.case_metadata or {},
        'created_at': _isoformat(case.created_at),
        'updated_at': _isoformat(case.updated_at),
    }


def serialize_run(run, *, include_release=True):
    if not run:
        return None
    payload = {
        'id': run.id,
        'dataset_id': run.dataset_id,
        'run_name': run.run_name,
        'status': run.status,
        'checker_version': run.checker_version,
        'rule_policy_version': run.rule_policy_version,
        'provider_config': run.provider_config or {},
        'reference_profile_snapshot': run.reference_profile_snapshot or {},
        'summary_metrics': run.summary_metrics or {},
        'started_by': run.started_by,
        'started_at': _isoformat(run.started_at),
        'completed_at': _isoformat(run.completed_at),
        'created_at': _isoformat(run.created_at),
    }
    if include_release:
        payload['released_report'] = (
            serialize_released_report(run.released_report, include_run=False)
            if run.released_report
            else None
        )
    return payload


def _released_report_history(release):
    metadata = release.release_metadata or {}
    events = []
    for item in _system_history(metadata, 'release_history'):
        events.append({
            'event_type': 'released',
            'event_at': item.get('released_at'),
            'actor_id': item.get('released_by'),
            'report_version': item.get('report_version') or release.report_version,
            'notes': item.get('notes'),
        })
    for item in _system_history(metadata, 'revocation_history'):
        events.append({
            'event_type': 'revoked',
            'event_at': item.get('revoked_at'),
            'actor_id': item.get('revoked_by'),
            'report_version': item.get('report_version') or release.report_version,
            'notes': item.get('notes'),
        })
    if not any(event['event_type'] == 'released' for event in events):
        events.append({
            'event_type': 'released',
            'event_at': _isoformat(release.released_at),
            'actor_id': release.released_by,
            'report_version': release.report_version,
            'notes': release.release_notes,
        })
    if (
        release.status == 'revoked'
        and not any(event['event_type'] == 'revoked' for event in events)
        and metadata.get('revoked_at')
    ):
        events.append({
            'event_type': 'revoked',
            'event_at': metadata.get('revoked_at'),
            'actor_id': metadata.get('revoked_by'),
            'report_version': release.report_version,
            'notes': metadata.get('revocation_notes'),
        })
    return sorted(events, key=lambda item: item.get('event_at') or '', reverse=True)


def serialize_released_report(release, *, include_run=True):
    if not release:
        return None
    run = release.run
    payload = {
        'id': release.id,
        'run_id': release.run_id,
        'status': release.status,
        'report_version': release.report_version,
        'release_notes': release.release_notes,
        'metadata': release.release_metadata or {},
        'released_by': release.released_by,
        'released_at': _isoformat(release.released_at),
        'created_at': _isoformat(release.created_at),
        'updated_at': _isoformat(release.updated_at),
        'history': _released_report_history(release),
        'snapshot': _released_snapshot_payload(release),
    }
    if include_run:
        payload['run'] = serialize_run(run, include_release=False)
        payload['dataset'] = serialize_dataset(run.dataset) if run and run.dataset else None
    return payload


def serialize_result(result):
    if not result:
        return None
    return {
        'id': result.id,
        'run_id': result.run_id,
        'case_id': result.case_id,
        'checker_result_id': result.checker_result_id,
        'expected_output': result.expected_output or {},
        'predicted_output': result.predicted_output or {},
        'metric_breakdown': result.metric_breakdown or {},
        'passed': result.passed,
        'failure_reasons': result.failure_reasons or [],
        'created_at': _isoformat(result.created_at),
        'case': serialize_case(result.case),
    }


def serialize_metric_snapshot(snapshot):
    if not snapshot:
        return None
    return {
        'id': snapshot.id,
        'dataset_id': snapshot.dataset_id,
        'run_id': snapshot.run_id,
        'snapshot_type': snapshot.snapshot_type,
        'metrics': snapshot.metrics or {},
        'gates': snapshot.gates or [],
        'created_by': snapshot.created_by,
        'created_at': _isoformat(snapshot.created_at),
    }


def _released_snapshot_payload(release):
    snapshot = get_run_metric_snapshot(release.run_id)
    if snapshot:
        return serialize_metric_snapshot(snapshot)
    run = release.run
    metrics_payload = run.summary_metrics if run else {}
    return {
        'id': None,
        'dataset_id': run.dataset_id if run else None,
        'run_id': release.run_id,
        'snapshot_type': 'released_run',
        'metrics': metrics_payload or {},
        'gates': (metrics_payload or {}).get('gates') or [],
        'created_by': release.released_by,
        'created_at': _isoformat(release.released_at),
    }


def _gold_label_template_case(result):
    # Use the read-time contract for legacy counts/confidence; do not backfill.
    from app.services.document_compliance_service import serialize_compliance_result
    serialized = serialize_compliance_result(result)
    project_requirement = result.project_requirement
    project = project_requirement.project if project_requirement else None
    document_file = result.document_file
    case_key = f'checker-result-{result.id}-document-file-{document_file.id}'
    suggested_evidence_type = _suggested_evidence_type(result)
    suggested_fields = _suggested_field_values(result.extracted_fields or {})
    suggested_layout = _suggested_layout_values(result)

    return {
        'case_key': case_key,
        'document_family': suggested_evidence_type or rule_engine.DEFAULT_EVIDENCE_TYPE,
        'document_file_id': document_file.id,
        'requirement_id': project_requirement.requirement_id if project_requirement else None,
        'program_id': project.program_id if project else None,
        'fiscal_year': project.fiscal_year if project else None,
        'ground_truth': {
            'schema_version': metrics.GROUND_TRUTH_SCHEMA_VERSION,
            'case_key': case_key,
            'expected_evidence_type': 'TODO_REVIEWER_SELECT_EVIDENCE_TYPE',
            'expected_status': 'TODO_REVIEWER_SELECT_STATUS',
            'expected_recommended_action': 'TODO_REVIEWER_SELECT_ACTION',
            'expected_fields': {
                key: f'TODO_REVIEWER_CONFIRM_OR_EDIT: {value}'
                for key, value in suggested_fields.items()
            },
            'expected_findings': [],
            'forbidden_findings': [],
            'expected_annotations': [],
            'expected_layout': {
                'layout_elements': [],
                'layout_issues': [],
            },
        },
        'pii_redacted': False,
        'label_source': 'human_gold_label_template',
        'label_confidence': 'medium',
        'metadata': {
            'label_status': 'needs_human_adjudication',
            'reviewer_checklist': [
                'Confirm document family/evidence type.',
                'Confirm final expected checker status and recommended action.',
                'Confirm LGU, fiscal year, project title, amount, dates, and reference numbers when present.',
                'Label required and forbidden findings, especially format/layout issues.',
                'Add expected annotation boxes for visual layout evidence when applicable.',
                'Add expected_layout layout elements for headers, footers, signatories, tables, logos, and readable text zones when format matters.',
                'Add expected_layout layout issues when the submitted document has reviewer-confirmed overlap or collision defects.',
            ],
            'source_checker_result': {
                'id': result.id,
                'status': result.status,
                'recommended_action': result.recommended_action,
                'score': _to_float(result.score),
                'checker_version': result.checker_version,
                'created_at': _isoformat(result.created_at),
            },
            'source_document': {
                'document_file_id': document_file.id,
                'submission_id': document_file.submission_id,
                'file_name': document_file.file_name,
                'mime_type': document_file.mime_type,
                'file_size_bytes': document_file.file_size_bytes,
                'is_primary': document_file.is_primary,
            },
            'source_project_requirement': {
                'project_requirement_id': project_requirement.id if project_requirement else None,
                'requirement_id': project_requirement.requirement_id if project_requirement else None,
                'requirement_name': project_requirement.requirement_name if project_requirement else None,
                'requirement_type': project_requirement.requirement_type if project_requirement else None,
                'annex_reference': project_requirement.annex_reference if project_requirement else None,
            },
            'source_project': {
                'project_id': project.id if project else None,
                'program_id': project.program_id if project else None,
                'lgu_id': project.lgu_id if project else None,
                'project_name': project.project_name if project else None,
                'fiscal_year': project.fiscal_year if project else None,
                'source_project_code': project.source_project_code if project else None,
            },
            'checker_suggestions': {
                'suggested_evidence_type': suggested_evidence_type,
                'suggested_status': result.status,
                'suggested_recommended_action': result.recommended_action,
                'suggested_fields': suggested_fields,
                'suggested_layout': suggested_layout,
                'findings': result.findings or [],
                'extracted_fields': serialized['extracted_fields'],
                'score_details': serialized['score_details'],
                'suggested_return_notes': result.suggested_return_notes,
            },
        },
    }


def _suggested_evidence_type(result):
    score_details = result.score_details or {}
    extracted_fields = result.extracted_fields or {}
    field_evidence = extracted_fields.get('field_evidence') if isinstance(extracted_fields, dict) else None
    field_evidence = field_evidence if isinstance(field_evidence, dict) else {}
    for value in (
        score_details.get('evidence_type'),
        field_evidence.get('evidence_type'),
        ((field_evidence.get('profile') or {}).get('id') if isinstance(field_evidence.get('profile'), dict) else None),
    ):
        if value:
            return str(value)
    return rule_engine.DEFAULT_EVIDENCE_TYPE


def _suggested_field_values(extracted_fields):
    extracted_fields = extracted_fields if isinstance(extracted_fields, dict) else {}
    field_evidence = extracted_fields.get('field_evidence')
    field_evidence = field_evidence if isinstance(field_evidence, dict) else {}
    output = {}

    matches = field_evidence.get('matches')
    if isinstance(matches, dict):
        for field_name, payload in matches.items():
            value = _field_suggestion_value(payload)
            if value is not None:
                output[field_name] = value

    fields = field_evidence.get('fields')
    if isinstance(fields, dict):
        for field_name, payload in fields.items():
            if field_name in output or not isinstance(payload, dict):
                continue
            value = _field_suggestion_value(payload.get('best'))
            if value is None:
                value = _field_suggestion_from_candidates(payload.get('candidates'))
            if value is not None:
                output[field_name] = value

    return output


def _suggested_layout_values(result):
    return {
        'layout_elements': _suggested_layout_elements(result.extracted_fields or {}),
        'layout_issues': _suggested_layout_issues(result.findings or []),
    }


def _suggested_layout_elements(extracted_fields):
    extracted_fields = extracted_fields if isinstance(extracted_fields, dict) else {}
    metadata = extracted_fields.get('extraction_metadata')
    metadata = metadata if isinstance(metadata, dict) else {}
    metadata_layout = metadata.get('layout') if isinstance(metadata.get('layout'), dict) else {}
    elements = (
        extracted_fields.get('layout_elements')
        or metadata.get('layout_elements')
        or metadata_layout.get('layout_elements')
        or metadata_layout.get('elements')
        or []
    )
    if not isinstance(elements, list):
        return []
    return [
        _normalize_suggested_layout_item(element, require_type=True)
        for element in elements
        if isinstance(element, dict) and _normalize_suggested_layout_item(element, require_type=True)
    ]


def _suggested_layout_issues(findings):
    if not isinstance(findings, list):
        return []
    issues = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get('id') or finding.get('finding_id') or '').strip()
        if not finding_id.startswith('layout_overlap:'):
            continue
        issue_id = finding_id.split(':', 1)[1]
        locations = finding.get('locations') if isinstance(finding.get('locations'), list) else []
        bbox = None
        page = 1
        for location in locations:
            if not isinstance(location, dict):
                continue
            bbox = _location_bbox_to_xyxy(location.get('bbox'))
            page = location.get('page') or page
            if bbox:
                break
        issues.append({
            'id': issue_id,
            'type': 'overlap',
            'page': page,
            **({'bbox': bbox} if bbox else {}),
            'source_finding_id': finding_id,
            'severity': finding.get('severity'),
        })
    return issues


def _normalize_suggested_layout_item(item, *, require_type=False):
    item_type = (
        item.get('type')
        or item.get('role')
        or item.get('label')
        or item.get('name')
    )
    if require_type and not item_type:
        return None
    output = {
        'id': item.get('id') or item.get('finding_id') or item_type,
        'type': item_type,
        'page': item.get('page') or 1,
    }
    bbox = item.get('bbox')
    if bbox is not None:
        output['bbox'] = bbox
    confidence = item.get('confidence')
    if confidence is not None:
        output['confidence'] = confidence
    return {key: value for key, value in output.items() if value not in (None, '')}


def _location_bbox_to_xyxy(value):
    if isinstance(value, dict):
        try:
            x = float(value.get('x'))
            y = float(value.get('y'))
            width = float(value.get('width'))
            height = float(value.get('height'))
        except (TypeError, ValueError):
            return None
        return [round(x, 4), round(y, 4), round(x + width, 4), round(y + height, 4)]
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return [round(float(item), 4) for item in value]
        except (TypeError, ValueError):
            return None
    return None


def _field_suggestion_value(payload):
    if not isinstance(payload, dict):
        return None
    candidate = payload.get('candidate') if isinstance(payload.get('candidate'), dict) else {}
    for source in (payload, candidate):
        for key in ('actual', 'normalized_value', 'matched_value', 'value', 'matched_text', 'text'):
            value = source.get(key)
            if value not in (None, ''):
                return value
    return None


def _field_suggestion_from_candidates(candidates):
    if not isinstance(candidates, list) or not candidates:
        return None
    return _field_suggestion_value(candidates[0])


def _run_checker_for_case(case, run, *, checker_runner=None):
    if checker_runner:
        return checker_runner(case, run)
    fixture_output = (case.case_metadata or {}).get('fixture_checker_output')
    if fixture_output:
        return fixture_output
    if case.document_file_id:
        return _run_live_checker_for_document_case(case, run)
    raise DocumentCheckerEvaluationError(
        'No checker runner is configured for this evaluation case.',
        500,
    )


def _run_live_checker_for_document_case(case, run):
    from app.services import document_compliance_service

    if not run.started_by:
        raise DocumentCheckerEvaluationError(
            'Live checker evaluation requires a run started_by user.',
            422,
        )

    document_file = db.session.get(DocumentFile, case.document_file_id)
    if not document_file:
        raise DocumentCheckerEvaluationError('Evaluation document file not found.', 404)

    selected_file = _selected_submission_document_file(document_file.submission)
    if not selected_file or selected_file.id != document_file.id:
        raise DocumentCheckerEvaluationError(
            'Evaluation case document_file_id does not match the submission file used by the live checker.',
            409,
            {
                'case_document_file_id': document_file.id,
                'selected_document_file_id': selected_file.id if selected_file else None,
            },
        )

    try:
        output = document_compliance_service.run_submission_check(
            document_file.submission_id,
            user_id=run.started_by,
            use_prior_year_reference=_use_prior_year_reference(case, run),
        )
    except document_compliance_service.DocumentComplianceError as exc:
        raise DocumentCheckerEvaluationError(exc.message, exc.status_code, exc.errors) from exc

    if not isinstance(output, dict):
        raise DocumentCheckerEvaluationError('Live checker returned an unsupported output payload.', 500)

    return {
        **output,
        'checker_result_id': output.get('id') or output.get('checker_result_id'),
        'evaluation_source': 'live_document_compliance_service',
    }


def _selected_submission_document_file(submission):
    if not submission:
        return None
    from app.services import document_intelligence_service
    return document_intelligence_service.resolve_submission_primary_document(submission)


def _use_prior_year_reference(case, run):
    case_metadata = case.case_metadata or {}
    run_metadata = run.run_metadata or {}
    return bool(
        case_metadata.get('use_prior_year_reference')
        or run_metadata.get('use_prior_year_reference')
    )


def _checker_result_id(checker_output):
    if not isinstance(checker_output, dict):
        return None
    for key in ('checker_result_id', 'result_id', 'id'):
        value = _optional_int(checker_output.get(key))
        if value is not None:
            return value
    return None


def _failure_reasons(metric_breakdown):
    reasons = []
    status = metric_breakdown.get('status') or {}
    if status.get('false_approval'):
        reasons.append('high_risk_false_approval')
    if status.get('false_return'):
        reasons.append('false_return')
    if status and not status.get('status_match', True):
        reasons.append('status_mismatch')
    if not (metric_breakdown.get('recommended_action_match') is True):
        reasons.append('recommended_action_mismatch')
    if not (metric_breakdown.get('evidence_type') or {}).get('matched', True):
        reasons.append('evidence_type_mismatch')
    fields = metric_breakdown.get('fields') or {}
    if fields and not fields.get('passed', True):
        reasons.append('field_mismatch')
    mapping = metric_breakdown.get('mapping') or {}
    if mapping.get('support') and not mapping.get('passed', True):
        reasons.append('document_mapping_mismatch')
        if mapping.get('false_mapping'):
            reasons.append('false_document_mapping')
        if mapping.get('missing_mapping'):
            reasons.append('missing_document_mapping')
    ocr = metric_breakdown.get('ocr') or {}
    if ocr.get('support') and not ocr.get('passed', True):
        if ocr.get('extraction_failed'):
            reasons.append('ocr_extraction_failure')
        if ocr.get('readable_text_passed') is False:
            reasons.append('ocr_readability_mismatch')
        if ocr.get('cer') is not None and ocr.get('max_cer') is not None and ocr.get('cer') > ocr.get('max_cer'):
            reasons.append('ocr_cer_exceeds_target')
        if ocr.get('wer') is not None and ocr.get('max_wer') is not None and ocr.get('wer') > ocr.get('max_wer'):
            reasons.append('ocr_wer_exceeds_target')
    findings = metric_breakdown.get('findings') or {}
    missing = ((findings.get('expected') or {}).get('missing') or [])
    unexpected = ((findings.get('forbidden') or {}).get('unexpected') or [])
    if missing:
        reasons.append('missing_expected_findings')
    if unexpected:
        reasons.append('unexpected_forbidden_findings')
    annotations = metric_breakdown.get('annotations') or {}
    if annotations.get('support') and annotations.get('matched') != annotations.get('support'):
        reasons.append('annotation_mismatch')
    return _dedupe(reasons)


def _aggregate_evidence_type(breakdowns):
    expected = []
    predicted = []
    for item in breakdowns:
        evidence = item.get('evidence_type') or {}
        if not evidence.get('expected') and not evidence.get('predicted'):
            continue
        expected.append(evidence.get('expected'))
        predicted.append(evidence.get('predicted'))
    matches = sum(1 for exp, pred in zip(expected, predicted) if exp == pred)
    mismatches = len(expected) - matches
    aggregate = metrics.precision_recall_f1(matches, mismatches, mismatches)
    aggregate['confusion_matrix'] = metrics.calculate_confusion_matrix(expected, predicted)
    return aggregate


def _aggregate_mapping(breakdowns):
    tp = fp = fn = 0
    top_k_matched = 0
    top_k_support = 0
    false_mapping_count = 0
    false_mapping_support = 0

    for item in breakdowns:
        mapping = item.get('mapping') or {}
        if not mapping.get('support'):
            continue

        aggregate = mapping.get('aggregate') or {}
        tp += aggregate.get('true_positive') or 0
        fp += aggregate.get('false_positive') or 0
        fn += aggregate.get('false_negative') or 0

        top_k_support += 1
        if mapping.get('top_k_match'):
            top_k_matched += 1

        if mapping.get('suggested_project_requirement_id') is not None:
            false_mapping_support += 1
            if mapping.get('false_mapping'):
                false_mapping_count += 1

    return {
        'aggregate': metrics.precision_recall_f1(tp, fp, fn),
        'top_k_matched': top_k_matched,
        'top_k_support': top_k_support,
        'top_k_accuracy': _safe_ratio(top_k_matched, top_k_support),
        'false_mapping_count': false_mapping_count,
        'false_mapping_support': false_mapping_support,
        'false_mapping_rate': _safe_ratio(false_mapping_count, false_mapping_support),
    }


def _aggregate_ocr(breakdowns):
    char_edits = 0
    char_expected = 0
    word_edits = 0
    word_expected = 0
    cer_support = 0
    wer_support = 0
    readable_passed = 0
    readable_support = 0
    extraction_failure_count = 0
    extraction_failure_support = 0
    confidence_total = 0
    confidence_support = 0

    for item in breakdowns:
        ocr = item.get('ocr') or {}
        if not ocr.get('support'):
            continue

        character_error = ocr.get('character_error') or {}
        if character_error.get('expected_length'):
            char_edits += character_error.get('edit_distance') or 0
            char_expected += character_error.get('expected_length') or 0
            cer_support += 1

        word_error = ocr.get('word_error') or {}
        if word_error.get('expected_length'):
            word_edits += word_error.get('edit_distance') or 0
            word_expected += word_error.get('expected_length') or 0
            wer_support += 1

        if ocr.get('readable_text_expected'):
            readable_support += 1
            if ocr.get('readable_text_passed'):
                readable_passed += 1

        extraction_failure_support += 1
        if ocr.get('extraction_failed'):
            extraction_failure_count += 1

        confidence = _optional_float(ocr.get('confidence'))
        if confidence is not None:
            confidence_total += confidence
            confidence_support += 1

    return {
        'cer': _safe_ratio(char_edits, char_expected),
        'cer_support': cer_support,
        'character_edit_distance': char_edits,
        'character_expected_length': char_expected,
        'wer': _safe_ratio(word_edits, word_expected),
        'wer_support': wer_support,
        'word_edit_distance': word_edits,
        'word_expected_length': word_expected,
        'readable_text_rate': _safe_ratio(readable_passed, readable_support),
        'readable_text_passed': readable_passed,
        'readable_text_support': readable_support,
        'extraction_failure_count': extraction_failure_count,
        'extraction_failure_rate': _safe_ratio(extraction_failure_count, extraction_failure_support),
        'extraction_failure_support': extraction_failure_support,
        'confidence_average': _safe_ratio(confidence_total, confidence_support),
        'confidence_support': confidence_support,
    }


def _aggregate_fields(breakdowns):
    tp = fp = fn = 0
    by_field = {}
    for item in breakdowns:
        aggregate = ((item.get('fields') or {}).get('aggregate') or {})
        tp += aggregate.get('true_positive') or 0
        fp += aggregate.get('false_positive') or 0
        fn += aggregate.get('false_negative') or 0
        for field_name, payload in ((item.get('fields') or {}).get('fields') or {}).items():
            stats = by_field.setdefault(field_name, {'true_positive': 0, 'false_positive': 0, 'false_negative': 0})
            if payload.get('matched'):
                stats['true_positive'] += 1
            elif payload.get('unexpected'):
                stats['false_positive'] += 1
            elif payload.get('missing'):
                stats['false_negative'] += 1
            else:
                stats['false_positive'] += 1
                stats['false_negative'] += 1
    return {
        'aggregate': metrics.precision_recall_f1(tp, fp, fn),
        'by_field': {
            field_name: _field_metric_result(values)
            for field_name, values in sorted(by_field.items())
        },
    }


def _field_metric_result(values):
    result = metrics.precision_recall_f1(
        values['true_positive'],
        values['false_positive'],
        values['false_negative'],
    )
    if result.get('support') and result.get('f1') is None:
        result['f1'] = 0
    return result


def _field_flat_metrics(fields):
    output = {}
    by_field = (fields or {}).get('by_field') or {}
    for field_name in COMMON_FIELD_METRIC_KEYS:
        field_metrics = by_field.get(field_name) or {}
        output[f'field_{field_name}_precision'] = field_metrics.get('precision')
        output[f'field_{field_name}_recall'] = field_metrics.get('recall')
        output[f'field_{field_name}_f1'] = field_metrics.get('f1')
        output[f'field_{field_name}_support'] = field_metrics.get('support')
    return output


def _field_breakdown_rows(metrics_payload):
    by_field = ((metrics_payload.get('fields') or {}).get('by_field') or {})
    if not by_field:
        return []
    ordered_names = [
        field_name for field_name in COMMON_FIELD_METRIC_KEYS
        if field_name in by_field
    ]
    ordered_names.extend(
        field_name for field_name in sorted(by_field)
        if field_name not in ordered_names
    )
    return [
        [
            _format_field_label(field_name),
            _format_percent((by_field.get(field_name) or {}).get('precision')),
            _format_percent((by_field.get(field_name) or {}).get('recall')),
            _format_percent((by_field.get(field_name) or {}).get('f1')),
            (by_field.get(field_name) or {}).get('support'),
        ]
        for field_name in ordered_names
    ]


def _compliance_quality_rows(metrics_payload):
    quality = metrics_payload.get('compliance_quality') or {}
    if not quality:
        return []
    definitions = [
        ('False approvals', quality.get('false_approval') or {}),
        ('False returns', quality.get('false_return') or {}),
        ('Blocker false positives', quality.get('blocker_false_positive') or {}),
        ('Blocker false negatives', quality.get('blocker_false_negative') or {}),
    ]
    rows = []
    for label, payload in definitions:
        if payload.get('count') is None and payload.get('support') is None and payload.get('rate') is None:
            continue
        rows.append([
            label,
            payload.get('count'),
            payload.get('support'),
            _format_percent(payload.get('rate')),
        ])
    return rows


def _blocker_finding_rows(metrics_payload):
    by_finding = ((metrics_payload.get('compliance_quality') or {}).get('by_finding') or {})
    return [
        [
            _format_finding_label(finding_id),
            payload.get('false_positive') or 0,
            payload.get('false_negative') or 0,
        ]
        for finding_id, payload in sorted(by_finding.items())
    ]


def _aggregate_findings(breakdowns):
    fp_count = sum(1 for item in breakdowns if (item.get('findings') or {}).get('critical_blocker_false_positive'))
    fn_count = sum(1 for item in breakdowns if (item.get('findings') or {}).get('critical_blocker_false_negative'))
    support = sum(1 for item in breakdowns if item.get('findings'))
    return {
        'critical_blocker_false_positive_count': fp_count,
        'critical_blocker_false_positive_support': support,
        'critical_blocker_false_positive_rate': _safe_ratio(fp_count, support),
        'critical_blocker_false_negative_count': fn_count,
        'critical_blocker_false_negative_support': support,
        'critical_blocker_false_negative_rate': _safe_ratio(fn_count, support),
    }


def _aggregate_compliance_quality(results):
    results = list(results or [])
    breakdowns = [result.metric_breakdown or {} for result in results]
    status_items = [item.get('status') or {} for item in breakdowns]
    false_approval_count = sum(1 for item in status_items if item.get('false_approval'))
    false_return_count = sum(1 for item in status_items if item.get('false_return'))
    false_approval_support = sum(
        1 for item in status_items
        if item.get('expected_status') and item.get('expected_status') != 'ready_for_approval'
    )
    false_return_support = sum(
        1 for item in status_items
        if item.get('expected_status') in {'ready_for_approval', 'review_required'}
    )
    blocker_support = sum(1 for item in breakdowns if item.get('findings'))

    reason_counts = {}
    by_finding = {}
    blocker_false_positive_count = 0
    blocker_false_negative_count = 0

    for result in results:
        for reason in (getattr(result, 'failure_reasons', None) or []):
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        findings = (result.metric_breakdown or {}).get('findings') or {}
        if findings.get('critical_blocker_false_positive'):
            blocker_false_positive_count += 1
        if findings.get('critical_blocker_false_negative'):
            blocker_false_negative_count += 1

        for finding_id in ((findings.get('forbidden') or {}).get('unexpected') or []):
            row = by_finding.setdefault(finding_id, {'false_positive': 0, 'false_negative': 0})
            row['false_positive'] += 1
        for finding_id in ((findings.get('expected') or {}).get('missing') or []):
            row = by_finding.setdefault(finding_id, {'false_positive': 0, 'false_negative': 0})
            row['false_negative'] += 1

    return {
        'false_approval': {
            'count': false_approval_count,
            'support': false_approval_support,
            'rate': _safe_ratio(false_approval_count, false_approval_support),
        },
        'false_return': {
            'count': false_return_count,
            'support': false_return_support,
            'rate': _safe_ratio(false_return_count, false_return_support),
        },
        'blocker_false_positive': {
            'count': blocker_false_positive_count,
            'support': blocker_support,
            'rate': _safe_ratio(blocker_false_positive_count, blocker_support),
        },
        'blocker_false_negative': {
            'count': blocker_false_negative_count,
            'support': blocker_support,
            'rate': _safe_ratio(blocker_false_negative_count, blocker_support),
        },
        'failure_reason_counts': dict(sorted(reason_counts.items())),
        'by_finding': {
            finding_id: by_finding[finding_id]
            for finding_id in sorted(by_finding)
        },
    }


def _aggregate_annotations(breakdowns):
    support = 0
    matched = 0
    for item in breakdowns:
        annotations = item.get('annotations') or {}
        support += annotations.get('support') or 0
        matched += annotations.get('matched') or 0
    return {
        'support': support,
        'matched': matched,
        'missing': max(support - matched, 0),
        'accuracy': _safe_ratio(matched, support),
    }


def _aggregate_layout(breakdowns):
    element_counts = _sum_layout_aggregate_counts(breakdowns, 'elements')
    overlap_counts = _sum_layout_aggregate_counts(breakdowns, 'overlap_issues')
    return {
        'elements': {
            'aggregate': metrics.precision_recall_f1(
                element_counts['true_positive'],
                element_counts['false_positive'],
                element_counts['false_negative'],
            ),
            'by_type': _aggregate_layout_by_type(breakdowns, 'elements'),
        },
        'overlap_issues': {
            'aggregate': metrics.precision_recall_f1(
                overlap_counts['true_positive'],
                overlap_counts['false_positive'],
                overlap_counts['false_negative'],
            ),
            'by_type': _aggregate_layout_by_type(breakdowns, 'overlap_issues'),
        },
    }


def _sum_layout_aggregate_counts(breakdowns, collection_key):
    totals = {'true_positive': 0, 'false_positive': 0, 'false_negative': 0}
    for item in breakdowns:
        aggregate = (((item.get('layout') or {}).get(collection_key) or {}).get('aggregate') or {})
        totals['true_positive'] += aggregate.get('true_positive') or 0
        totals['false_positive'] += aggregate.get('false_positive') or 0
        totals['false_negative'] += aggregate.get('false_negative') or 0
    return totals


def _aggregate_layout_by_type(breakdowns, collection_key):
    counts = {}
    for item in breakdowns:
        by_type = (((item.get('layout') or {}).get(collection_key) or {}).get('by_type') or {})
        for key, value in by_type.items():
            if key not in counts:
                counts[key] = {'matched': 0, 'missing': 0, 'unexpected': 0, 'expected': 0, 'predicted': 0}
            counts[key]['matched'] += value.get('matched') or 0
            counts[key]['missing'] += value.get('missing') or 0
            counts[key]['unexpected'] += value.get('unexpected') or 0
            counts[key]['expected'] += value.get('expected') or 0
            counts[key]['predicted'] += value.get('predicted') or 0
    for key, value in counts.items():
        value['aggregate'] = metrics.precision_recall_f1(
            value['matched'],
            value['unexpected'],
            value['missing'],
        )
    return counts


def _aggregate_format_blockers(results):
    support = 0
    false_positive_count = 0
    for result in results:
        expected = result.expected_output or {}
        predicted = result.predicted_output or {}
        forbidden_format_ids = {
            item for item in (expected.get('forbidden_findings') or [])
            if _is_format_finding_id(item)
        }
        expected_format_ids = {
            item for item in (expected.get('expected_findings') or [])
            if _is_format_finding_id(item)
        }
        predicted_format_blockers = {
            _finding_id(item)
            for item in (predicted.get('findings') or [])
            if _is_format_finding(item) and item.get('severity') == 'blocker'
        }
        if not (forbidden_format_ids or expected_format_ids or predicted_format_blockers):
            continue
        support += 1
        if predicted_format_blockers & forbidden_format_ids:
            false_positive_count += 1
    return {
        'false_positive_count': false_positive_count,
        'support': support,
        'false_positive_rate': _safe_ratio(false_positive_count, support),
    }


def _aggregate_scanned_image_safety(results):
    support = 0
    ready_count = 0
    for result in results:
        expected_ocr = ((result.expected_output or {}).get('expected_ocr') or {})
        predicted = result.predicted_output or {}
        ocr_metrics = ((result.metric_breakdown or {}).get('ocr') or {})
        safety_case = bool(
            expected_ocr.get('scanned_image_safety_case')
            or expected_ocr.get('image_only_safety_case')
            or expected_ocr.get('extraction_unavailable_should_not_be_ready')
        )
        if not safety_case:
            continue
        support += 1
        extraction_unavailable = bool(
            expected_ocr.get('extraction_unavailable_should_not_be_ready')
            or ocr_metrics.get('extraction_failed')
        )
        if extraction_unavailable and predicted.get('status') == 'ready_for_approval':
            ready_count += 1
    return {
        'ready_count': ready_count,
        'support': support,
    }


def _aggregate_advisory_boundary(results):
    support = 0
    override_count = 0
    for result in results:
        expected = result.expected_output or {}
        predicted = result.predicted_output or {}
        advisory = predicted.get('advisory') if isinstance(predicted.get('advisory'), dict) else {}
        boundary_case = bool(expected.get('advisory_boundary_case') or advisory)
        if not boundary_case:
            continue
        support += 1
        if advisory.get('advisory_overrode_status') or advisory.get('deterministic_status_preserved') is False:
            override_count += 1
    return {
        'override_count': override_count,
        'support': support,
    }


def _is_format_finding(finding):
    if not isinstance(finding, dict):
        return False
    return (
        finding.get('dimension') == 'format_template_layout'
        or _is_format_finding_id(_finding_id(finding))
    )


def _is_format_finding_id(value):
    value = str(value or '')
    return value.startswith('format_profile_') or value.startswith('format_')


def _finding_id(finding):
    if isinstance(finding, dict):
        return str(finding.get('id') or '')
    return str(finding or '')


def _gate_at_least(gate_id, label, actual, target, support, min_support):
    return _metric_gate(gate_id, label, actual, target, support, min_support, operator='>=')


def _gate_at_most(gate_id, label, actual, target, support, min_support):
    return _metric_gate(gate_id, label, actual, target, support, min_support, operator='<=')


def _zero_count_gate(gate_id, label, count, support, min_support):
    support = support or 0
    if support < min_support:
        status = 'not_enough_cases'
        message = f'Needs at least {min_support} cases; only {support} available.'
    elif (count or 0) == 0:
        status = 'passed'
        message = 'No violations found.'
    else:
        status = 'failed'
        message = f'{count} violation(s) found.'
    return {
        'id': gate_id,
        'label': label,
        'target': '0 violations',
        'actual': count,
        'support': support,
        'status': status,
        'message': message,
    }


def _metric_gate(gate_id, label, actual, target, support, min_support, *, operator):
    support = support or 0
    if actual is None:
        status = 'not_applicable'
        message = 'Metric was not measured in this run.'
    elif support < min_support:
        status = 'not_enough_cases'
        message = f'Needs at least {min_support} cases; only {support} available.'
    elif operator == '>=':
        status = 'passed' if actual >= target else 'failed'
        message = f'Actual {actual:.2%}; target >= {target:.2%}.'
    else:
        status = 'passed' if actual <= target else 'failed'
        message = f'Actual {actual:.2%}; target <= {target:.2%}.'
    return {
        'id': gate_id,
        'label': label,
        'target': f'{operator} {target}',
        'actual': actual,
        'support': support,
        'status': status,
        'message': message,
    }


def _required_text(data, field_name):
    value = (data.get(field_name) or '').strip()
    if not value:
        raise DocumentCheckerEvaluationError(f'{field_name} is required.', 422)
    return value


def _build_dataset(data, *, user_id=None):
    data = data or {}
    name = _required_text(data, 'name')
    version = _required_text(data, 'version')
    dataset_type = data.get('dataset_type') or 'synthetic'
    status = data.get('status') or 'draft'
    _validate_choice(dataset_type, {'synthetic', 'demo', 'redacted_real', 'reviewer_adjudicated', 'holdout'}, 'dataset_type')
    _validate_choice(status, {'draft', 'active', 'locked', 'archived'}, 'status')

    if DocumentCheckerEvaluationDataset.query.filter_by(name=name, version=version).first():
        raise DocumentCheckerEvaluationError('Evaluation dataset already exists for this name and version.', 409)

    return DocumentCheckerEvaluationDataset(
        name=name,
        description=(data.get('description') or '').strip() or None,
        dataset_type=dataset_type,
        version=version,
        status=status,
        dataset_metadata=_json_object(data.get('metadata') or data.get('dataset_metadata')),
        created_by=_optional_int(user_id),
    )


def _build_case(dataset, data):
    data = data or {}
    ground_truth, errors = metrics.validate_ground_truth(data.get('ground_truth') or {})
    if errors:
        raise DocumentCheckerEvaluationError('Ground truth is invalid.', 422, errors)

    return DocumentCheckerEvaluationCase(
        dataset=dataset,
        document_file_id=data.get('document_file_id'),
        case_key=_case_key(data),
        document_family=_required_text(data, 'document_family'),
        requirement_id=data.get('requirement_id'),
        program_id=data.get('program_id'),
        fiscal_year=data.get('fiscal_year'),
        ground_truth=ground_truth,
        pii_redacted=bool(data.get('pii_redacted', False)),
        label_source=(data.get('label_source') or '').strip() or None,
        label_confidence=(data.get('label_confidence') or '').strip() or None,
        case_metadata=_json_object(data.get('metadata') or data.get('case_metadata')),
    )


def _validate_manifest_cases(cases, *, require_adjudicated_labels=False):
    errors = []
    seen_case_keys = set()
    for index, case_payload in enumerate(cases):
        case_errors = {}
        if not isinstance(case_payload, dict):
            errors.append({'index': index, 'case_key': None, 'errors': {'case': 'Case entry must be an object.'}})
            continue

        case_key = (case_payload.get('case_key') or '').strip()
        if case_key in seen_case_keys:
            case_errors['case_key'] = 'Duplicate case_key in manifest.'
        elif case_key:
            seen_case_keys.add(case_key)

        try:
            _build_case(DocumentCheckerEvaluationDataset(name='manifest-validation', version='validation'), case_payload)
        except DocumentCheckerEvaluationError as exc:
            if exc.details:
                case_errors.update(exc.details)
            else:
                case_errors['case'] = exc.message

        if require_adjudicated_labels:
            case_errors.update(_validate_adjudicated_gold_label_case(case_payload))

        if case_errors:
            errors.append({'index': index, 'case_key': case_key or None, 'errors': case_errors})
    return errors


def _case_key(data):
    return _required_text(data or {}, 'case_key')


def _validate_choice(value, allowed, field_name):
    if value not in allowed:
        raise DocumentCheckerEvaluationError(
            f'{field_name} must be one of: {", ".join(sorted(allowed))}.',
            422,
        )


def _ensure_manifest_is_adjudicated_if_required(dataset_payload):
    metadata = _json_object(
        (dataset_payload or {}).get('metadata')
        or (dataset_payload or {}).get('dataset_metadata')
    )
    if metadata.get('requires_human_adjudication') and not metadata.get('human_adjudication_completed'):
        raise DocumentCheckerEvaluationError(
            'Gold label templates must be human-adjudicated before import. '
            'Set dataset.metadata.human_adjudication_completed to true after reviewer sign-off.',
            422,
        )
    if metadata.get('pii_review_required') and not metadata.get('pii_review_completed'):
        raise DocumentCheckerEvaluationError(
            'Gold label templates with PII review requirements must complete privacy/redaction review before import. '
            'Set dataset.metadata.pii_review_completed to true after reviewer sign-off.',
            422,
        )


def _requires_adjudicated_gold_labels(manifest_payload, dataset_payload):
    metadata = _json_object(
        (dataset_payload or {}).get('metadata')
        or (dataset_payload or {}).get('dataset_metadata')
    )
    template_type = (manifest_payload or {}).get('template_type')
    return bool(
        template_type == GOLD_LABEL_TEMPLATE_TYPE
        or metadata.get('source') == 'gold_label_template_export'
        or metadata.get('requires_human_adjudication')
    )


def _gold_label_quality_summary(manifest):
    manifest = manifest if isinstance(manifest, dict) else {}
    dataset = manifest.get('dataset') if isinstance(manifest.get('dataset'), dict) else {}
    metadata = _json_object(dataset.get('metadata') or dataset.get('dataset_metadata'))
    cases = manifest.get('cases') if isinstance(manifest.get('cases'), list) else []
    todo_paths = _todo_value_paths(cases, 'cases')
    expected_field_todo_count = len([
        path for path in todo_paths
        if '.ground_truth.expected_fields.' in path
    ])
    case_count_needing_adjudication = 0
    suggested_field_count = 0
    suggested_layout_element_count = 0
    suggested_layout_issue_count = 0
    expected_layout_element_count = 0
    expected_layout_issue_count = 0
    unique_document_file_ids = set()
    unique_source_result_ids = set()

    for case in cases:
        if not isinstance(case, dict):
            continue
        document_file_id = case.get('document_file_id')
        if document_file_id is not None:
            unique_document_file_ids.add(document_file_id)

        case_metadata = _json_object(case.get('metadata') or case.get('case_metadata'))
        checker_suggestions = case_metadata.get('checker_suggestions')
        if isinstance(checker_suggestions, dict):
            suggested_fields = checker_suggestions.get('suggested_fields')
            if isinstance(suggested_fields, dict):
                suggested_field_count += len(suggested_fields)
            suggested_layout = checker_suggestions.get('suggested_layout')
            if isinstance(suggested_layout, dict):
                suggested_layout_element_count += len(_layout_items(suggested_layout, 'layout_elements', 'elements'))
                suggested_layout_issue_count += len(_layout_items(suggested_layout, 'layout_issues', 'overlap_issues'))

        ground_truth = case.get('ground_truth') if isinstance(case.get('ground_truth'), dict) else {}
        expected_layout = ground_truth.get('expected_layout') if isinstance(ground_truth.get('expected_layout'), dict) else {}
        expected_layout_element_count += len(_layout_items(expected_layout, 'layout_elements', 'elements'))
        expected_layout_issue_count += len(_layout_items(expected_layout, 'layout_issues', 'overlap_issues'))

        source_checker_result = case_metadata.get('source_checker_result')
        if isinstance(source_checker_result, dict) and source_checker_result.get('id') is not None:
            unique_source_result_ids.add(source_checker_result.get('id'))

        if (
            case.get('label_source') == 'human_gold_label_template'
            or case_metadata.get('label_status') == 'needs_human_adjudication'
            or _todo_value_paths(case.get('ground_truth') or {}, 'ground_truth')
        ):
            case_count_needing_adjudication += 1

    source_result_ids = metadata.get('source_checker_result_ids')
    if isinstance(source_result_ids, list):
        for result_id in source_result_ids:
            if result_id is not None:
                unique_source_result_ids.add(result_id)

    pii_review_required = bool(metadata.get('pii_review_required'))
    pii_review_completed = bool(metadata.get('pii_review_completed'))
    human_adjudication_completed = bool(metadata.get('human_adjudication_completed'))
    import_ready = (
        not todo_paths
        and case_count_needing_adjudication == 0
        and human_adjudication_completed
        and (not pii_review_required or pii_review_completed)
    )

    return {
        'case_count': len(cases),
        'source_result_count': len(unique_source_result_ids),
        'source_document_count': len(unique_document_file_ids),
        'todo_placeholder_count': len(todo_paths),
        'expected_field_todo_count': expected_field_todo_count,
        'suggested_field_count': suggested_field_count,
        'suggested_layout_element_count': suggested_layout_element_count,
        'suggested_layout_issue_count': suggested_layout_issue_count,
        'expected_layout_element_count': expected_layout_element_count,
        'expected_layout_issue_count': expected_layout_issue_count,
        'case_count_needing_adjudication': case_count_needing_adjudication,
        'human_adjudication_completed': human_adjudication_completed,
        'pii_review_required': pii_review_required,
        'pii_review_completed': pii_review_completed,
        'import_ready': import_ready,
        'review_work_items': (
            len(todo_paths)
            + case_count_needing_adjudication
            + (0 if human_adjudication_completed else 1)
            + (1 if pii_review_required and not pii_review_completed else 0)
        ),
    }


def _layout_items(payload, *keys):
    payload = payload if isinstance(payload, dict) else {}
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _validate_adjudicated_gold_label_case(case_payload):
    errors = {}
    if not isinstance(case_payload, dict):
        return errors

    ground_truth = case_payload.get('ground_truth') or {}
    if isinstance(ground_truth, dict):
        for path in _todo_value_paths(ground_truth, 'ground_truth'):
            errors[path] = 'Reviewer TODO placeholder must be replaced before import.'

    label_source = (case_payload.get('label_source') or '').strip()
    if label_source == 'human_gold_label_template':
        errors['label_source'] = 'Set label_source to reviewer_adjudicated after reviewer sign-off.'

    metadata = _json_object(case_payload.get('metadata') or case_payload.get('case_metadata'))
    label_status = (metadata.get('label_status') or '').strip()
    if label_status == 'needs_human_adjudication':
        errors['metadata.label_status'] = 'Set metadata.label_status to adjudicated after reviewer sign-off.'

    return errors


def _todo_value_paths(value, prefix):
    paths = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f'{prefix}.{key}' if prefix else str(key)
            paths.extend(_todo_value_paths(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_todo_value_paths(child, f'{prefix}.{index}'))
    elif isinstance(value, str) and GOLD_LABEL_TODO_MARKER in value.upper():
        paths.append(prefix)
    return paths


def _int_list(value):
    if value in (None, ''):
        return []
    if not isinstance(value, list):
        value = [value]
    output = []
    for item in value:
        try:
            parsed = int(item)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in output:
            output.append(parsed)
    return output


def _bounded_int(value, *, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _json_object(value):
    return value if isinstance(value, dict) else {}


def _optional_int(value):
    if value in (None, ''):
        return None
    return int(value)


def _optional_float(value):
    try:
        if value in (None, ''):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_ratio(numerator, denominator):
    if not denominator:
        return None
    return numerator / denominator


def _format_percent(value):
    if value is None:
        return 'Not measured'
    return f'{value:.1%}'


def _format_metric_value(value):
    if value is None:
        return 'Not measured'
    if isinstance(value, float):
        return f'{value:.3f}'
    return value


def _format_field_label(value):
    words = str(value or '').replace('_', ' ').split()
    return ' '.join(word.upper() if word.lower() in {'lgu', 'fy'} else word.capitalize() for word in words)


def _format_finding_label(value):
    parts = str(value or '').split(':')
    return ':'.join(_format_field_label(part) for part in parts)


def _markdown_table(headers, rows):
    def clean(value):
        return str(_format_metric_value(value)).replace('|', '\\|').replace('\n', ' ')

    output = [
        '| ' + ' | '.join(clean(header) for header in headers) + ' |',
        '| ' + ' | '.join('---' for _ in headers) + ' |',
    ]
    for row in rows:
        output.append('| ' + ' | '.join(clean(value) for value in row) + ' |')
    return '\n'.join(output)


def _isoformat(value):
    return value.isoformat() if value else None


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_filename(value):
    text = str(value or 'gold-label-template').strip().lower()
    if text.endswith('.json'):
        text = text[:-5]
    output = []
    previous_dash = False
    for character in text:
        if character.isalnum():
            output.append(character)
            previous_dash = False
        elif not previous_dash:
            output.append('-')
            previous_dash = True
    filename = ''.join(output).strip('-') or 'gold-label-template'
    if not filename.endswith('.json'):
        filename = f'{filename}.json'
    return filename


def _dedupe(values):
    output = []
    seen = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
