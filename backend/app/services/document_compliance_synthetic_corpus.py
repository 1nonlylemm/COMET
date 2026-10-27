import json
import re
import shutil
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app.services import document_annotation_service
from app.services import document_compliance_field_evidence as field_evidence_service
from app.services import document_compliance_metrics as evaluation_metrics
from app.services import document_compliance_photo_evidence as photo_evidence_service
from app.services import document_compliance_rule_engine as rule_engine


CORPUS_VERSION = 'synthetic-documentary-corpus-2026.05.23'
TEXT_LOCATION_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'/-]*")

DEFAULT_EXPECTED_CONTEXT = {
    'project_name': 'Construction of Potable Water Storage and Distribution Support Facility',
    'source_project_code': 'LGSF-2025-BINAN-001',
    'fiscal_year': 2025,
    'lgu_name': 'City of Biñan',
    'lgu_municipality': 'Biñan',
    'lgu_province': 'Laguna',
    'budget_amount': '2500000.00',
    'reference_number': 'ADA-2025-09-001234',
    'requirement_name': 'NADAI Certification',
    'annex_reference': 'NADAI',
}

FIELD_ZONE_LIBRARY = {
    'project_title': {
        'field': 'project_title',
        'label': 'Project title',
        'page': 1,
        'bbox': [12, 18, 54, 8],
    },
    'lgu': {
        'field': 'lgu',
        'label': 'LGU / implementing office',
        'page': 1,
        'bbox': [12, 28, 38, 7],
    },
    'amount': {
        'field': 'amount',
        'label': 'Project amount / cost',
        'page': 1,
        'bbox': [56, 42, 32, 7],
    },
    'reference_number': {
        'field': 'reference_number',
        'label': 'Reference number',
        'page': 1,
        'bbox': [62, 18, 28, 8],
    },
    'date': {
        'field': 'date',
        'label': 'Document date',
        'page': 1,
        'bbox': [62, 28, 24, 6],
    },
}


def build_corpus_cases(profile_ids=None):
    """Return deterministic synthetic checker cases with ground truth labels."""
    profile_filter = {str(item) for item in profile_ids or []}
    cases = [
        _case(
            'nadai_complete_current',
            'nadai_fund_transfer',
            'complete_current_year_reference',
            True,
            """
            NOTICE OF AUTHORITY TO DEBIT ACCOUNT ISSUED
            N.A.D.A.I. / Authority to Debit Account
            LGU: City of Bifian, Laguna
            Chargeable Against FY 2025 LGSF Financial Assistance
            Purpose: Water Storage & Distribution Support Facility Construction
            Amount Credited: PHP 2,500,000.00
            ADA No.: ADA-2025-09-001234
            Date issued: September 12, 2025
            Certified by: Maria R. Santos, City Treasurer
            """,
            {
                'lgu': 'matched',
                'fiscal_year': 'matched',
                'amount': 'matched',
                'reference_number': 'matched',
            },
            expected_findings=[],
        ),
        _case(
            'nadai_wrong_context_and_reference',
            'nadai_fund_transfer',
            'wrong_lgu_fy_amount_and_reference',
            False,
            """
            PROOF OF FUND TRANSFER TO LGU TRUST FUND
            LGU: Municipality of Mabitac, Laguna
            Chargeable against FY 2024 allocation
            Purpose: Construction of Potable Water Storage and Distribution Support Facility
            Credited Amount: PHP 2,400,000.00
            ADA No.: ADA-2025-09-001234
            Date issued: September 12, 2025
            """,
            {
                'lgu': 'mismatch',
                'fiscal_year': 'mismatch',
                'amount': 'mismatch',
                'reference_number': 'mismatch',
            },
            expected_context={'reference_number': 'ADA-2025-09-009999'},
            expected_findings=[
                'field_mismatch:lgu',
                'field_mismatch:fiscal_year',
                'field_mismatch:amount',
                'field_mismatch:reference_number',
            ],
        ),
        _case(
            'nadai_missing_transfer_fields',
            'nadai_fund_transfer',
            'missing_amount_and_transfer_reference',
            False,
            """
            NADAI Certification for City of Biñan, Laguna
            Chargeable against FY 2025.
            Purpose: Construction of Potable Water Storage and Distribution Support Facility.
            This scanned page is missing the fund transfer amount and transfer reference.
            """,
            {
                'lgu': 'matched',
                'fiscal_year': 'matched',
                'amount': 'missing',
                'reference_number': 'missing',
            },
            expected_findings=[
                'field_missing:amount',
                'field_missing:reference_number',
            ],
        ),
        _case(
            'receipt_complete_no_project_title',
            'official_receipt',
            'complete_receipt_without_project_title',
            True,
            """
            OFFICIAL RECEIPT
            OR No.: OR-2026-000345
            Date: March 14, 2026
            Payee: Municipality of Santa Cruz
            Amount Paid: PHP 125,450.75
            Particulars: materials delivered for implementation support
            """,
            {
                'date': 'found',
                'amount': 'found',
                'reference_number': 'found',
            },
            expected_context={
                'project_name': 'Drainage Canal Rehabilitation',
                'budget_amount': None,
                'reference_number': None,
            },
            forbidden_findings=['field_missing:project_title'],
        ),
        _case(
            'receipt_missing_date_amount_reference',
            'official_receipt',
            'missing_receipt_core_fields',
            False,
            """
            OFFICIAL RECEIPT
            Payee: Municipality of Santa Cruz
            Particulars: supplies for local project implementation.
            """,
            {
                'date': 'missing',
                'amount': 'missing',
                'reference_number': 'missing',
            },
            expected_context={'budget_amount': None, 'reference_number': None},
            expected_findings=[
                'field_missing:date',
                'field_missing:amount',
                'field_missing:reference_number',
            ],
            forbidden_findings=['field_missing:project_title'],
        ),
        _case(
            'receipt_wrong_reference_number',
            'official_receipt',
            'receipt_with_wrong_reference_number',
            False,
            """
            OFFICIAL RECEIPT
            OR No.: OR-2026-000345
            Date: March 14, 2026
            Payee: Municipality of Santa Cruz
            Amount Paid: PHP 125,450.75
            """,
            {
                'date': 'found',
                'amount': 'found',
                'reference_number': 'mismatch',
            },
            expected_context={
                'budget_amount': None,
                'reference_number': 'OR-2026-009999',
            },
            expected_findings=['field_mismatch:reference_number'],
            forbidden_findings=['field_mismatch:amount', 'field_missing:project_title'],
            profile_metadata={
                'format_profile': {
                    'field_zones': [
                        {
                            'field': 'reference_number',
                            'label': 'Official receipt number',
                            'page': 1,
                            'bbox': [62, 18, 28, 8],
                        },
                    ],
                },
            },
        ),
        _case(
            'billing_liquidation_complete_no_project_title',
            'billing_package',
            'complete_liquidation_package_without_project_title',
            True,
            """
            STATEMENT OF RECEIPTS AND DISBURSEMENTS
            SORD No.: SORD-2026-Q1-078
            Date Prepared: April 30, 2026
            Paid to: Laguna Builders Cooperative
            Total Liquidation: PHP 340,000.00
            Particulars: construction materials, labor, and delivery charges
            """,
            {
                'date': 'found',
                'amount': 'found',
                'reference_number': 'found',
                'vendor_or_payee': 'found',
            },
            expected_context={
                'project_name': 'Municipal Hall Repair',
                'budget_amount': None,
                'reference_number': None,
            },
            forbidden_findings=['field_missing:project_title'],
        ),
        _case(
            'billing_wrong_reference_number',
            'billing_package',
            'billing_package_with_wrong_reference_number',
            False,
            """
            LIQUIDATION REPORT AND BILLING PACKAGE
            SORD No.: SORD-2026-Q1-078
            Date Prepared: April 30, 2026
            Paid to: Laguna Builders Cooperative
            Total Billing Amount: PHP 340,000.00
            """,
            {
                'date': 'found',
                'amount': 'found',
                'reference_number': 'mismatch',
                'vendor_or_payee': 'found',
            },
            expected_context={
                'project_name': 'Municipal Hall Repair',
                'budget_amount': None,
                'reference_number': 'SORD-2026-Q1-099',
            },
            expected_findings=['field_mismatch:reference_number'],
            forbidden_findings=['field_missing:project_title'],
            profile_metadata={
                'format_profile': {
                    'field_zones': [
                        {
                            'field': 'reference_number',
                            'label': 'SORD / billing reference number',
                            'page': 1,
                            'bbox': [62, 18, 28, 8],
                        },
                    ],
                },
            },
        ),
        _case(
            'certification_complete',
            'certification',
            'complete_certification',
            True,
            """
            CERTIFICATION
            This is to certify that the City of Biñan, Laguna has no other source of funding.
            Date: April 3, 2026
            Certified by: Maria R. Santos, City Treasurer
            """,
            {
                'lgu': 'matched',
                'date': 'found',
                'signatory': 'found',
            },
        ),
        _case(
            'certification_wrong_lgu',
            'certification',
            'certification_for_wrong_lgu',
            False,
            """
            CERTIFICATION
            This is to certify that the Municipality of Mabitac, Laguna has no other source of funding.
            Date: April 3, 2026
            Certified by: Maria R. Santos, Municipal Treasurer
            """,
            {
                'lgu': 'mismatch',
                'date': 'found',
                'signatory': 'found',
            },
            expected_findings=['field_mismatch:lgu'],
            profile_metadata=_format_profile_metadata('lgu', 'date'),
        ),
        _case(
            'resolution_complete',
            'resolution',
            'complete_sanggunian_resolution',
            True,
            """
            SANGGUNIANG BAYAN RESOLUTION
            Resolution No. 2026-118
            Municipality of Santa Cruz, Laguna
            Date: May 9, 2026
            Approved by: Juan D. Reyes, Municipal Vice Mayor
            """,
            {
                'reference_number': 'found',
                'date': 'found',
                'lgu': 'matched',
            },
            expected_context={
                'lgu_name': 'Municipality of Santa Cruz',
                'lgu_municipality': 'Santa Cruz',
                'reference_number': None,
            },
        ),
        _case(
            'resolution_wrong_lgu_and_reference',
            'resolution',
            'resolution_for_wrong_lgu_and_reference',
            False,
            """
            SANGGUNIANG BAYAN RESOLUTION
            Resolution No. 2026-118
            Municipality of Mabitac, Laguna
            Date: May 9, 2026
            Approved by: Juan D. Reyes, Municipal Vice Mayor
            """,
            {
                'reference_number': 'mismatch',
                'date': 'found',
                'lgu': 'mismatch',
            },
            expected_context={
                'lgu_name': 'Municipality of Santa Cruz',
                'lgu_municipality': 'Santa Cruz',
                'reference_number': 'RESOLUTION-2026-119',
            },
            expected_findings=['field_mismatch:reference_number', 'field_mismatch:lgu'],
            profile_metadata=_format_profile_metadata('reference_number', 'lgu', 'date'),
        ),
        _case(
            'pow_complete',
            'program_of_works',
            'complete_program_of_works',
            True,
            """
            PROGRAM OF WORKS
            Project Title: Construction of Potable Water Storage and Distribution Support Facility
            LGU: City of Biñan, Laguna
            Total Project Cost: PHP 2,500,000.00
            Prepared by: Engr. Carla P. Dizon
            """,
            {
                'project_title': 'matched',
                'lgu': 'matched',
                'amount': 'matched',
                'signatory': 'found',
            },
        ),
        _case(
            'pow_wrong_project_lgu_amount',
            'program_of_works',
            'program_of_works_wrong_project_lgu_amount',
            False,
            """
            PROGRAM OF WORKS
            Project Title: Potable Water Storage Facility
            LGU: Municipality of Mabitac, Laguna
            Total Project Cost: PHP 2,400,000.00
            Prepared by: Engr. Carla P. Dizon
            """,
            {
                'project_title': 'mismatch',
                'lgu': 'mismatch',
                'amount': 'mismatch',
                'signatory': 'found',
            },
            expected_findings=[
                'field_mismatch:project_title',
                'field_mismatch:lgu',
                'field_mismatch:amount',
            ],
            profile_metadata=_format_profile_metadata('project_title', 'lgu', 'amount'),
        ),
        _case(
            'ded_missing_context',
            'detailed_engineering_estimate',
            'ded_without_project_lgu_or_amount',
            False,
            """
            DETAILED ENGINEERING DESIGN
            Plan sheets and technical notes are attached for review.
            The estimate summary page was not included in this scan.
            """,
            {
                'project_title': 'missing',
                'lgu': 'missing',
                'amount': 'missing',
            },
            expected_findings=[
                'field_missing:project_title',
                'field_missing:lgu',
                'field_missing:amount',
            ],
        ),
        _case(
            'ded_wrong_project_lgu_amount',
            'detailed_engineering_estimate',
            'ded_wrong_project_lgu_amount',
            False,
            """
            DETAILED ENGINEERING DESIGN
            Project Title: Potable Water Storage Facility
            LGU: Municipality of Mabitac, Laguna
            Total Project Cost: PHP 2,400,000.00
            Prepared by: Engr. Carla P. Dizon
            """,
            {
                'project_title': 'mismatch',
                'lgu': 'mismatch',
                'amount': 'mismatch',
            },
            expected_findings=[
                'field_mismatch:project_title',
                'field_mismatch:lgu',
                'field_mismatch:amount',
            ],
            profile_metadata=_format_profile_metadata('project_title', 'lgu', 'amount'),
        ),
        _case(
            'progress_report_complete',
            'progress_report',
            'complete_monthly_progress_report',
            True,
            """
            MONTHLY PROGRESS REPORT
            Project: Construction of Potable Water Storage and Distribution Support Facility
            Municipality of Biñan, Laguna
            Reporting Period: June 2026
            Prepared by: Monitoring Officer Ana Cruz
            """,
            {
                'project_title': 'matched',
                'lgu': 'matched',
                'date': 'found',
            },
            expected_context={'lgu_name': 'City of Biñan', 'lgu_municipality': 'Biñan'},
        ),
        _case(
            'progress_report_wrong_project_lgu',
            'progress_report',
            'progress_report_wrong_project_lgu',
            False,
            """
            MONTHLY PROGRESS REPORT
            Project: Potable Water Storage Facility
            Municipality of Mabitac, Laguna
            Reporting Period: June 2026
            Prepared by: Monitoring Officer Ana Cruz
            """,
            {
                'project_title': 'mismatch',
                'lgu': 'mismatch',
                'date': 'found',
            },
            expected_context={'lgu_name': 'City of Biñan', 'lgu_municipality': 'Biñan'},
            expected_findings=['field_mismatch:project_title', 'field_mismatch:lgu'],
            profile_metadata=_format_profile_metadata('project_title', 'lgu', 'date'),
        ),
        _photo_case(
            'photo_evidence_with_metadata_and_scene',
            'complete_photo_evidence_with_metadata_and_scene',
            True,
            visual_summary={
                'image_quality': 'acceptable',
                'blank_or_near_blank': False,
                'low_resolution': False,
                'blur_score': 220.0,
                'darkness_score': 135.0,
                'notes': [],
            },
            photo_metadata={
                'metadata_available': True,
                'captured_at': '2026-05-18T10:42:13',
                'captured_at_source': 'EXIF DateTimeOriginal',
                'camera': {'make': 'Samsung', 'model': 'Galaxy A55'},
                'image': {'width': 4032, 'height': 3024, 'orientation': 1},
                'gps': {
                    'latitude': 14.4251,
                    'longitude': 121.4179,
                    'resolved_address': 'Mabitac, Laguna, Philippines',
                    'resolved_address_source': 'aws-location',
                },
                'notes': [],
            },
            provider_metadata=[
                _rekognition_metadata([
                    {'name': 'Road', 'confidence': 98.0, 'categories': ['Infrastructure']},
                    {'name': 'Construction', 'confidence': 90.0, 'categories': ['Activity']},
                ])
            ],
            expected_photo_checks={
                'capture_time': 'present',
                'gps': 'present',
                'scene_labels': 'present',
            },
        ),
        _photo_case(
            'photo_evidence_missing_metadata_and_scene',
            'missing_photo_metadata_and_required_scene',
            False,
            visual_summary={
                'image_quality': 'acceptable',
                'blank_or_near_blank': False,
                'low_resolution': False,
                'blur_score': 180.0,
                'darkness_score': 128.0,
                'notes': [],
            },
            photo_metadata={
                'metadata_available': False,
                'captured_at': None,
                'captured_at_source': None,
                'camera': {},
                'image': {'width': 1600, 'height': 1200, 'orientation': 1},
                'gps': None,
                'notes': ['No embedded EXIF photo metadata was found.'],
            },
            provider_metadata=[
                _rekognition_metadata([
                    {'name': 'Document', 'confidence': 96.0, 'categories': ['Text']},
                ])
            ],
            expected_photo_checks={
                'capture_time': 'missing',
                'gps': 'missing',
                'scene_labels': 'missing',
            },
            expected_findings=[
                'photo_capture_time_missing',
                'photo_gps_missing',
                'photo_scene_label_missing',
            ],
        ),
    ]
    if profile_filter:
        cases = [case for case in cases if case['profile_id'] in profile_filter]
    return deepcopy(cases)


def evaluate_case(case):
    """Run one synthetic case through field extraction and advisory scoring."""
    if case.get('profile_id') == 'progress_photo':
        return _evaluate_photo_case(case)

    expected_context = dict(case.get('expected_context') or {})
    profile_selection = _profile_selection(case)
    evidence = field_evidence_service.extract_field_evidence(
        case.get('document_text') or '',
        file_name=case.get('file_name'),
        expected=expected_context,
        evidence_type=case.get('profile_id'),
        profile_selection=profile_selection,
        text_locations=case.get('text_locations') or _synthetic_text_locations(case.get('document_text')),
    )
    findings = field_evidence_service.build_profile_findings(evidence)
    score, status, action, score_details = rule_engine.score_findings(
        findings,
        profile_selection,
    )
    field_statuses = _field_statuses(evidence)
    finding_ids = [item.get('id') for item in findings]
    annotations = document_annotation_service.build_annotations(findings)
    blocker_ids = [
        item.get('id')
        for item in findings
        if item.get('severity') == 'blocker'
    ]
    ground_truth = case.get('ground_truth') or {}
    expected_field_statuses = ground_truth.get('expected_field_statuses') or {}
    field_matches = {
        field: field_statuses.get(field) == expected_status
        for field, expected_status in expected_field_statuses.items()
    }
    missing_expected_findings = [
        finding_id
        for finding_id in ground_truth.get('expected_findings') or []
        if finding_id not in finding_ids
    ]
    unexpected_findings = [
        finding_id
        for finding_id in ground_truth.get('forbidden_findings') or []
        if finding_id in finding_ids
    ]
    expected_flag_free = bool(
        ground_truth.get('expected_flag_free')
        if ground_truth.get('expected_flag_free') is not None
        else ground_truth.get('expected_ready')
    )
    is_flag_free = not any(f.get('severity') in {'blocker', 'warning'} for f in findings)
    passed = (
        is_flag_free == expected_flag_free
        and all(field_matches.values())
        and not missing_expected_findings
        and not unexpected_findings
    )
    return {
        'case_id': case.get('case_id'),
        'profile_id': case.get('profile_id'),
        'scenario': case.get('scenario'),
        'expected_flag_free': expected_flag_free,
        'is_flag_free': is_flag_free,
        'expected_ready': expected_flag_free,
        'actual_ready': is_flag_free,
        'expected_bucket': case.get('expected_bucket'),
        'actual_status': status,
        'recommended_action': action,
        'score': score,
        'score_details': score_details,
        'field_statuses': field_statuses,
        'field_expectation_matches': field_matches,
        'findings': findings,
        'finding_ids': finding_ids,
        'annotations': annotations,
        'annotation_count': len(annotations),
        'blocker_ids': blocker_ids,
        'missing_expected_findings': missing_expected_findings,
        'unexpected_findings': unexpected_findings,
        'passed': passed,
        'field_evidence': evidence,
    }


def evaluate_corpus(cases=None):
    """Evaluate all synthetic cases and return corpus-level metrics."""
    if cases is None:
        cases = build_corpus_cases()
    evaluated = [evaluate_case(case) for case in cases]
    total_field_expectations = sum(
        len(item.get('field_expectation_matches') or {})
        for item in evaluated
    )
    correct_field_expectations = sum(
        1
        for item in evaluated
        for passed in (item.get('field_expectation_matches') or {}).values()
        if passed
    )
    profile_metrics = defaultdict(lambda: {
        'total_cases': 0,
        'passed_cases': 0,
        'false_approvals': 0,
        'false_returns': 0,
    })
    for item in evaluated:
        metrics = profile_metrics[item['profile_id']]
        metrics['total_cases'] += 1
        metrics['passed_cases'] += 1 if item.get('passed') else 0
        exp_ff = item.get('expected_flag_free') if item.get('expected_flag_free') is not None else item.get('expected_ready')
        act_ff = item.get('is_flag_free') if item.get('is_flag_free') is not None else item.get('actual_ready')
        metrics['false_approvals'] += 1 if (not exp_ff and act_ff) else 0
        metrics['false_returns'] += 1 if (exp_ff and not act_ff) else 0

    false_approvals = sum(
        1 for item in evaluated
        if not (item.get('expected_flag_free') if item.get('expected_flag_free') is not None else item.get('expected_ready'))
        and (item.get('is_flag_free') if item.get('is_flag_free') is not None else item.get('actual_ready'))
    )
    false_returns = sum(
        1 for item in evaluated
        if (item.get('expected_flag_free') if item.get('expected_flag_free') is not None else item.get('expected_ready'))
        and not (item.get('is_flag_free') if item.get('is_flag_free') is not None else item.get('actual_ready'))
    )
    annotation_findings = [
        (item, finding)
        for item in evaluated
        for finding in item.get('findings') or []
        if _finding_expects_annotation(finding)
    ]
    annotation_findings_with_locations = [
        (item, finding)
        for item, finding in annotation_findings
        if _finding_has_renderable_annotation(item, finding)
    ]
    summary = {
        'total_cases': len(evaluated),
        'passed_cases': sum(1 for item in evaluated if item.get('passed')),
        'failed_cases': sum(1 for item in evaluated if not item.get('passed')),
        'false_approvals': false_approvals,
        'false_returns': false_returns,
        'field_expectations': total_field_expectations,
        'field_expectations_correct': correct_field_expectations,
        'field_accuracy': _safe_ratio(correct_field_expectations, total_field_expectations),
        'annotation_findings': len(annotation_findings),
        'annotation_findings_with_locations': len(annotation_findings_with_locations),
        'annotation_coverage': _safe_ratio(len(annotation_findings_with_locations), len(annotation_findings)),
        'profile_metrics': dict(profile_metrics),
    }
    return {
        'corpus_version': CORPUS_VERSION,
        'generated_at': _utc_now(),
        'summary': summary,
        'cases': evaluated,
    }


def build_evaluation_manifest(*, profile_ids=None, dataset=None):
    """Return an evaluation-service manifest for the synthetic corpus."""
    corpus_cases = build_corpus_cases(profile_ids=profile_ids)
    manifest_cases = [
        _evaluation_manifest_case(case, evaluate_case(case))
        for case in corpus_cases
    ]
    return {
        'dataset': {
            'name': 'Synthetic Documentary Corpus',
            'version': CORPUS_VERSION,
            'dataset_type': 'synthetic',
            'status': 'active',
            'description': 'Local-safe synthetic benchmark cases for the DMS checker.',
            'metadata': {
                'corpus_version': CORPUS_VERSION,
                'source': 'document_compliance_synthetic_corpus',
                'profile_ids': sorted({case['profile_id'] for case in corpus_cases}),
            },
            **(dataset or {}),
        },
        'cases': manifest_cases,
    }


def write_corpus(output_root, *, cases=None, reset=False):
    """Write synthetic documents, ground truth, manifests, and accuracy reports."""
    output_root = Path(output_root)
    if reset:
        _safe_reset_output(output_root)
    generated_root = output_root / 'generated'
    ground_truth_root = output_root / 'ground_truth'
    manifest_root = output_root / 'manifests'
    reports_root = output_root / 'reports'
    for directory in [
        generated_root / 'approved',
        generated_root / 'needs_review',
        ground_truth_root,
        manifest_root,
        reports_root,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    corpus_cases = cases or build_corpus_cases()
    manifest_cases = []
    for case in corpus_cases:
        bucket = case.get('expected_bucket') or 'needs_review'
        document_path = generated_root / bucket / case['file_name']
        ground_truth_path = ground_truth_root / f'{case["case_id"]}.json'
        _write_case_document(document_path, case)
        _write_json(ground_truth_path, _ground_truth_payload(case))
        manifest_cases.append({
            'case_id': case['case_id'],
            'profile_id': case['profile_id'],
            'scenario': case['scenario'],
            'document_path': _relative(document_path, output_root),
            'ground_truth_path': _relative(ground_truth_path, output_root),
            'expected_bucket': bucket,
            'expected_flag_free': case['ground_truth'].get('expected_flag_free', case['ground_truth'].get('expected_ready')),
            'expected_ready': case['ground_truth'].get('expected_ready'),
            'expected_field_statuses': case['ground_truth']['expected_field_statuses'],
            'expected_photo_checks': case['ground_truth'].get('expected_photo_checks') or {},
        })

    report = evaluate_corpus(corpus_cases)
    _write_json(manifest_root / 'corpus_manifest.json', {
        'corpus_version': CORPUS_VERSION,
        'case_count': len(manifest_cases),
        'cases': manifest_cases,
    })
    _write_json(manifest_root / 'generation_config.json', {
        'corpus_version': CORPUS_VERSION,
        'generated_at': report['generated_at'],
        'generator': 'app.services.document_compliance_synthetic_corpus',
        'advisory_only': True,
        'notes': [
            'Synthetic examples are safe for local validation and do not contain real beneficiary data.',
            'Checker output is advisory evidence for human reviewers; it must not approve submissions automatically.',
        ],
    })
    _write_json(reports_root / 'checker_accuracy_report.json', _serializable_report(report))
    (reports_root / 'checker_accuracy_report.md').write_text(
        _accuracy_markdown(report),
        encoding='utf-8',
    )
    (output_root / 'README.md').write_text(_readme(), encoding='utf-8')
    return {
        'output_root': str(output_root),
        'corpus_version': CORPUS_VERSION,
        'case_count': len(corpus_cases),
        'manifest_path': str(manifest_root / 'corpus_manifest.json'),
        'accuracy_report_path': str(reports_root / 'checker_accuracy_report.md'),
        'summary': report['summary'],
    }


def _case(
    case_id,
    profile_id,
    scenario,
    expected_ready,
    document_text,
    expected_field_statuses,
    *,
    expected_context=None,
    expected_findings=None,
    forbidden_findings=None,
    profile_metadata=None,
    expected_flag_free=None,
):
    context = dict(DEFAULT_EXPECTED_CONTEXT)
    context.update(expected_context or {})
    flag_free = bool(expected_flag_free if expected_flag_free is not None else expected_ready)
    bucket = 'approved' if flag_free else 'needs_review'
    case = {
        'case_id': case_id,
        'profile_id': profile_id,
        'scenario': scenario,
        'file_name': f'{case_id}.txt',
        'expected_bucket': bucket,
        'expected_context': context,
        'document_text': _clean_document_text(document_text),
        'ground_truth': {
            'expected_flag_free': flag_free,
            'expected_ready': flag_free,
            'expected_field_statuses': dict(expected_field_statuses),
            'expected_findings': list(expected_findings or []),
            'forbidden_findings': list(forbidden_findings or []),
        },
    }
    if profile_metadata:
        case['profile_metadata'] = dict(profile_metadata)
    return case


def _format_profile_metadata(*fields):
    return {
        'format_profile': {
            'field_zones': [
                dict(FIELD_ZONE_LIBRARY[field])
                for field in fields
                if field in FIELD_ZONE_LIBRARY
            ],
        },
    }


def _synthetic_text_locations(document_text):
    """Build deterministic word-level geometry for text-only synthetic cases."""
    locations = []
    lines = [
        line.strip()
        for line in str(document_text or '').splitlines()
        if line.strip()
    ]
    if not lines:
        return locations

    top = 0.08
    line_gap = 0.035
    height = 0.021
    for line_index, line in enumerate(lines):
        y = min(0.92, top + line_index * line_gap)
        line_length = max(len(line), 1)
        for match in TEXT_LOCATION_TOKEN_RE.finditer(line):
            token = match.group(0).strip()
            if not token:
                continue
            x = 0.08 + (match.start() / line_length) * 0.84
            width = max(0.014, ((match.end() - match.start()) / line_length) * 0.84)
            width = min(width, max(0.001, 0.96 - x))
            locations.append({
                'page': 1,
                'text': token,
                'bbox': {
                    'x': round(x, 4),
                    'y': round(y, 4),
                    'width': round(width, 4),
                    'height': height,
                },
                'bbox_type': 'detected_text',
            })
    return locations


def _rekognition_metadata(labels):
    return {
        'name': 'aws-rekognition',
        'version': 'synthetic',
        'region': 'local',
        'confidence': None,
        'errors': [],
        'payload': {
            'api': 'DetectLabels',
            'labels': list(labels or []),
        },
    }


def _photo_case(
    case_id,
    scenario,
    expected_ready,
    *,
    visual_summary,
    photo_metadata,
    provider_metadata,
    expected_photo_checks,
    expected_findings=None,
    expected_flag_free=None,
):
    flag_free = bool(expected_flag_free if expected_flag_free is not None else expected_ready)
    return {
        'case_id': case_id,
        'profile_id': 'progress_photo',
        'scenario': scenario,
        'file_name': f'{case_id}.jpg',
        'asset_type': 'photo',
        'expected_bucket': 'approved' if flag_free else 'needs_review',
        'expected_context': dict(DEFAULT_EXPECTED_CONTEXT),
        'document_text': (
            'Synthetic progress photo placeholder. '
            'Ground truth lives in the sidecar JSON and harness visual metadata.'
        ),
        'visual_summary': dict(visual_summary),
        'photo_metadata': dict(photo_metadata),
        'provider_metadata': list(provider_metadata or []),
        'profile_metadata': {
            'photo_evidence': {
                'require_capture_time': True,
                'require_gps': True,
                'required_scene_labels': ['Road', 'Construction'],
            },
        },
        'ground_truth': {
            'expected_flag_free': flag_free,
            'expected_ready': flag_free,
            'expected_field_statuses': {},
            'expected_photo_checks': dict(expected_photo_checks),
            'expected_findings': list(expected_findings or []),
            'forbidden_findings': [],
        },
    }


def _evaluate_photo_case(case):
    extraction = {
        'text': case.get('document_text') or '',
        'visual_summary': case.get('visual_summary') or {},
        'photo_metadata': case.get('photo_metadata') or {},
    }
    profile_selection = _profile_selection(case)
    photo_result = photo_evidence_service.evaluate_photo_evidence(
        extraction=extraction,
        provider_metadata=case.get('provider_metadata') or [],
        profile_selection=profile_selection,
    )
    findings = photo_result.get('findings') or []
    score, status, action, score_details = rule_engine.score_findings(findings, profile_selection)
    finding_ids = [item.get('id') for item in findings]
    annotations = document_annotation_service.build_annotations(findings)
    blocker_ids = [
        item.get('id')
        for item in findings
        if item.get('severity') == 'blocker'
    ]
    expected_flag_free = bool(
        (case.get('ground_truth') or {}).get('expected_flag_free')
        if (case.get('ground_truth') or {}).get('expected_flag_free') is not None
        else (case.get('ground_truth') or {}).get('expected_ready')
    )
    is_flag_free = not any(f.get('severity') in {'blocker', 'warning'} for f in findings)
    checks = photo_result.get('checks') or {}
    expected_checks = (case.get('ground_truth') or {}).get('expected_photo_checks') or {}
    check_matches = {
        key: (checks.get(key) or {}).get('status') == expected
        for key, expected in expected_checks.items()
    }
    missing_expected_findings = [
        finding_id
        for finding_id in (case.get('ground_truth') or {}).get('expected_findings') or []
        if finding_id not in finding_ids
    ]
    passed = (
        is_flag_free == expected_flag_free
        and all(check_matches.values())
        and not missing_expected_findings
    )
    return {
        'case_id': case.get('case_id'),
        'profile_id': case.get('profile_id'),
        'scenario': case.get('scenario'),
        'expected_flag_free': expected_flag_free,
        'is_flag_free': is_flag_free,
        'expected_ready': expected_flag_free,
        'actual_ready': is_flag_free,
        'expected_bucket': case.get('expected_bucket'),
        'actual_status': status,
        'recommended_action': action,
        'score': score,
        'score_details': score_details,
        'field_statuses': {},
        'field_expectation_matches': {},
        'photo_evidence_checks': checks,
        'photo_check_expectation_matches': check_matches,
        'findings': findings,
        'finding_ids': finding_ids,
        'annotations': annotations,
        'annotation_count': len(annotations),
        'blocker_ids': blocker_ids,
        'missing_expected_findings': missing_expected_findings,
        'unexpected_findings': [],
        'passed': passed,
        'field_evidence': None,
    }


def _profile_selection(case):
    profile_metadata = {
        'evidence_type': case.get('profile_id'),
        'minimum_text_chars': 20,
    }
    profile_metadata.update(case.get('profile_metadata') or {})
    return {
        'reference_status': 'current',
        'used_profiles': [
            {
                'profile_name': f'{case.get("profile_id")} synthetic validation profile',
                'checker_reference_type': 'official_template',
                'profile_metadata': profile_metadata,
            }
        ],
    }


def _finding_expects_annotation(finding):
    if not isinstance(finding, dict):
        return False
    if finding.get('severity') not in {'blocker', 'warning'}:
        return False
    finding_id = str(finding.get('id') or '')
    if finding_id.startswith('field_missing:'):
        return False
    if finding_id.startswith('format_profile_missing'):
        return False
    return True


def _finding_has_renderable_annotation(item, finding):
    finding_id = finding.get('id')
    return any(
        annotation.get('finding_id') == finding_id and annotation.get('renderable')
        for annotation in item.get('annotations') or []
    )


def _field_statuses(evidence):
    fields = evidence.get('fields') or {}
    matches = evidence.get('matches') or {}
    profile = evidence.get('profile') or {}
    statuses = {}
    for field in (profile.get('required_fields') or []) + (profile.get('advisory_fields') or []):
        match = matches.get(field) or {}
        if match.get('status') in {'matched', 'mismatch', 'missing'}:
            statuses[field] = match['status']
        elif (fields.get(field) or {}).get('best'):
            statuses[field] = 'found'
        else:
            statuses[field] = 'missing'
    return statuses


def _ground_truth_payload(case):
    return {
        'case_id': case['case_id'],
        'profile_id': case['profile_id'],
        'scenario': case['scenario'],
        'expected_context': case['expected_context'],
        'ground_truth': case['ground_truth'],
    }


def _evaluation_manifest_case(case, evaluated):
    expected_flag_free = bool(
        (case.get('ground_truth') or {}).get('expected_flag_free')
        if (case.get('ground_truth') or {}).get('expected_flag_free') is not None
        else (case.get('ground_truth') or {}).get('expected_ready')
    )
    expected_fields = _evaluation_expected_fields(case, evaluated) if expected_flag_free else {}
    annotations = [
        annotation
        for annotation in (_evaluation_annotations(evaluated.get('annotations') or []))
        if annotation.get('bbox')
    ]
    return {
        'case_key': case['case_id'],
        'document_family': case['profile_id'],
        'fiscal_year': (case.get('expected_context') or {}).get('fiscal_year'),
        'ground_truth': {
            'schema_version': evaluation_metrics.GROUND_TRUTH_SCHEMA_VERSION,
            'case_key': case['case_id'],
            'expected_evidence_type': case['profile_id'],
            'expected_status': evaluated.get('actual_status'),
            'expected_recommended_action': evaluated.get('recommended_action'),
            'expected_fields': expected_fields,
            'expected_findings': list((case.get('ground_truth') or {}).get('expected_findings') or []),
            'forbidden_findings': list((case.get('ground_truth') or {}).get('forbidden_findings') or []),
            'expected_annotations': annotations,
        },
        'pii_redacted': True,
        'label_source': 'synthetic',
        'label_confidence': 'high',
        'metadata': {
            'corpus_version': CORPUS_VERSION,
            'scenario': case.get('scenario'),
            'expected_flag_free': expected_flag_free,
            'expected_ready': expected_flag_free,
            'expected_bucket': case.get('expected_bucket'),
            'expected_field_statuses': dict((case.get('ground_truth') or {}).get('expected_field_statuses') or {}),
            'field_expectation_matches': dict(evaluated.get('field_expectation_matches') or {}),
            'document_text_chars': len(case.get('document_text') or ''),
            'fixture_checker_output': _evaluation_fixture_output(case, evaluated, annotations, expected_fields),
        },
    }


def _evaluation_fixture_output(case, evaluated, annotations, expected_fields):
    score_details = dict(evaluated.get('score_details') or {})
    score_details['evidence_type'] = case.get('profile_id')
    return {
        'status': evaluated.get('actual_status'),
        'recommended_action': evaluated.get('recommended_action'),
        'score': evaluated.get('score'),
        'score_details': score_details,
        'extracted_fields': _evaluation_extracted_fields(evaluated, expected_fields),
        'findings': list(evaluated.get('findings') or []),
        'annotations': annotations,
    }


def _evaluation_expected_fields(case, evaluated):
    expected = {}
    expected_statuses = (case.get('ground_truth') or {}).get('expected_field_statuses') or {}
    fields = ((evaluated.get('field_evidence') or {}).get('fields') or {})
    matches = ((evaluated.get('field_evidence') or {}).get('matches') or {})
    for field, expected_status in expected_statuses.items():
        if expected_status not in {'matched', 'found'}:
            continue
        match = matches.get(field) or {}
        if match.get('actual') is not None:
            expected[field] = match.get('actual')
            continue
        best = (fields.get(field) or {}).get('best') or {}
        if best.get('normalized_value') is not None:
            expected[field] = best.get('normalized_value')
        elif best.get('matched_text'):
            expected[field] = best.get('matched_text')
    return expected


def _evaluation_extracted_fields(evaluated, expected_fields):
    extracted = {}
    fields = ((evaluated.get('field_evidence') or {}).get('fields') or {})
    for field, payload in fields.items():
        if field not in expected_fields:
            continue
        best = (payload or {}).get('best') or {}
        if best.get('normalized_value') is not None:
            extracted[field] = best.get('normalized_value')
        elif best.get('matched_text'):
            extracted[field] = best.get('matched_text')
    return extracted


def _evaluation_annotations(annotations):
    output = []
    for annotation in annotations:
        bbox = _normalized_xyxy(annotation.get('bbox'))
        if not bbox:
            continue
        output.append({
            'id': annotation.get('id'),
            'finding_id': annotation.get('finding_id'),
            'page': annotation.get('page') or 1,
            'bbox': bbox,
            'label': annotation.get('field') or annotation.get('finding_id'),
        })
    return output


def _normalized_xyxy(bbox):
    if not isinstance(bbox, dict):
        return None
    x = bbox.get('x')
    y = bbox.get('y')
    width = bbox.get('width')
    height = bbox.get('height')
    if None in (x, y, width, height):
        return None
    x1 = max(0, min(float(x), 1))
    y1 = max(0, min(float(y), 1))
    x2 = max(x1, min(x1 + float(width), 1))
    y2 = max(y1, min(y1 + float(height), 1))
    return [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)]


def _serializable_report(report):
    sanitized = deepcopy(report)
    for item in sanitized.get('cases') or []:
        item.pop('field_evidence', None)
        item.pop('score_details', None)
        item.pop('findings', None)
    return sanitized


def _accuracy_markdown(report):
    summary = report.get('summary') or {}
    lines = [
        '# Documentary Compliance Checker Accuracy Report',
        '',
        f'Corpus version: `{report.get("corpus_version")}`',
        f'Generated at: `{report.get("generated_at")}`',
        '',
        '## Summary',
        '',
        f'- Total cases: {summary.get("total_cases", 0)}',
        f'- Passed cases: {summary.get("passed_cases", 0)}',
        f'- Failed cases: {summary.get("failed_cases", 0)}',
        f'- False approvals: {summary.get("false_approvals", 0)}',
        f'- False returns: {summary.get("false_returns", 0)}',
        f'- Field accuracy: {summary.get("field_accuracy", 0):.2%}',
        f'- Annotation coverage: {summary.get("annotation_coverage", 0):.2%}',
        '',
        '## Cases',
        '',
        '| Case | Profile | Expected | Actual | Score | Passed |',
        '| --- | --- | --- | --- | ---: | --- |',
    ]
    for item in report.get('cases') or []:
        exp_ff = item.get('expected_flag_free') if item.get('expected_flag_free') is not None else item.get('expected_ready')
        lines.append(
            '| {case_id} | {profile_id} | {expected} | {actual} | {score:.2f} | {passed} |'.format(
                case_id=item.get('case_id'),
                profile_id=item.get('profile_id'),
                expected='flag_free' if exp_ff else 'flags_expected',
                actual=item.get('actual_status'),
                score=item.get('score') or 0,
                passed='yes' if item.get('passed') else 'no',
            )
        )
    lines.extend([
        '',
        'This report is advisory validation evidence only. Human reviewers retain final authority over documentary compliance decisions.',
        '',
    ])
    return '\n'.join(lines)


def _readme():
    return '\n'.join([
        '# Synthetic Documentary Requirements Corpus',
        '',
        'This folder contains local-safe synthetic documents, ground truth sidecars, manifests, and checker accuracy reports.',
        '',
        'The corpus is designed to validate field extraction, alias/OCR correction, strict NADAI matching, receipt handling, photo evidence metadata, scene-label expectations, and text-profile checks without using real submitted documents.',
        '',
        'The checker remains an advisory Automated Document Review Assistant. A flag-free document indicates that no material issues or defects were flagged by automated heuristics; it does NOT constitute automated compliance approval or signoff. Human evaluators retain sole authority over all documentary decisions.',
        '',
    ])


def _clean_document_text(value):
    lines = [line.strip() for line in str(value or '').strip().splitlines()]
    return '\n'.join(line for line in lines if line) + '\n'


def _write_case_document(path, case):
    if case.get('asset_type') == 'photo':
        try:
            from PIL import Image, ImageDraw
        except Exception:
            path.write_bytes(b'COMET synthetic photo placeholder\n')
            return
        image = Image.new('RGB', (1600, 1000), color=(190, 210, 200))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 620, 1600, 1000), fill=(110, 110, 110))
        draw.rectangle((180, 560, 1420, 635), fill=(80, 80, 80))
        draw.rectangle((260, 240, 1320, 340), fill=(245, 245, 230), outline=(40, 40, 40), width=4)
        draw.text((300, 275), 'COMET SYNTHETIC PROJECT PHOTO', fill=(20, 20, 20))
        draw.text((300, 305), case.get('scenario') or case.get('case_id') or 'photo evidence', fill=(20, 20, 20))
        image.save(path, format='JPEG', quality=88)
        return
    path.write_text(_clean_document_text(case.get('document_text')), encoding='utf-8')


def _safe_reset_output(root):
    root = Path(root).resolve()
    if root.exists():
        marker = 'synthetic_documentary_requirements'
        if marker not in root.parts and marker not in root.name:
            raise RuntimeError(f'Refusing to remove unexpected output folder: {root}')
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def _relative(path, root):
    return str(Path(path).relative_to(root)).replace('\\', '/')


def _safe_ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else 0


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
