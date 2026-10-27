import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.extensions import db
from app.models import DocumentFile, Project, ProjectRequirement, Submission
from app.services import document_compliance_service


VALIDATION_VERSION = "seeded-documentary-compliance-validation-2026.05.24"

TARGET_FAMILIES = (
    "nadai_fund_transfer",
    "detailed_engineering_estimate",
    "program_of_works",
    "billing_package",
    "official_receipt",
    "certification",
    "resolution",
    "progress_report",
)

REFERENCE_POLICY_FINDINGS = {
    "no_checker_reference",
    "prior_year_reference_available",
    "prior_year_reference_used",
}

MAPPING_SCAN_FINDINGS = {"mapping_scan_missing"}

ADVISORY_GATE_FINDINGS = REFERENCE_POLICY_FINDINGS | MAPPING_SCAN_FINDINGS

FIELD_COMPARISON_KEYS = (
    "project_title",
    "lgu",
    "fiscal_year",
    "amount",
    "reference_number",
    "vendor_or_payee",
    "date",
)

FIELD_COMPARISON_KEYS_BY_FAMILY = {
    "nadai_fund_transfer": ("project_title", "lgu", "fiscal_year", "amount", "reference_number", "date"),
    "detailed_engineering_estimate": ("project_title", "lgu", "fiscal_year", "amount", "reference_number", "date"),
    "program_of_works": ("project_title", "lgu", "fiscal_year", "amount", "reference_number", "date"),
    "billing_package": ("project_title", "lgu", "amount", "reference_number", "vendor_or_payee", "date"),
    "official_receipt": ("lgu", "amount", "reference_number", "vendor_or_payee", "date"),
    "certification": ("project_title", "lgu", "fiscal_year", "reference_number", "date"),
    "resolution": ("project_title", "lgu", "fiscal_year", "reference_number", "date"),
    "progress_report": ("project_title", "lgu", "fiscal_year", "amount", "reference_number", "date"),
}


def select_representative_seed_cases(
    *,
    fiscal_years=(2023, 2024),
    families=TARGET_FAMILIES,
    limit_per_family=1,
    fallback_to_any_year=True,
):
    """Select seeded demo submissions for checker validation.

    The preferred sample comes from the requested FY range. If a document family
    is not present there, the selector can fall back to another seeded year so
    the report makes coverage gaps visible instead of silently skipping them.
    """
    requested_years = {int(year) for year in fiscal_years or []}
    target_families = tuple(families or TARGET_FAMILIES)
    documents = (
        DocumentFile.query
        .filter_by(is_primary=True)
        .order_by(DocumentFile.id.asc())
        .all()
    )
    candidates_by_family = {family: [] for family in target_families}

    for document in documents:
        case = _case_from_document(document)
        if not case or case["family"] not in candidates_by_family:
            continue
        candidates_by_family[case["family"]].append(case)

    selected = []
    for family in target_families:
        candidates = candidates_by_family.get(family) or []
        preferred = [
            {**case, "selection_scope": "requested_year"}
            for case in candidates
            if case.get("fiscal_year") in requested_years
        ]
        fallback = [
            {**case, "selection_scope": "fallback_year"}
            for case in candidates
            if case.get("fiscal_year") not in requested_years
        ]
        pool = preferred or (fallback if fallback_to_any_year else [])
        selected.extend(pool[:max(int(limit_per_family or 1), 1)])

    return selected


def run_seeded_validation(
    *,
    user_id,
    output_root,
    fiscal_years=(2023, 2024),
    families=TARGET_FAMILIES,
    limit_per_family=1,
    fallback_to_any_year=True,
):
    cases = select_representative_seed_cases(
        fiscal_years=fiscal_years,
        families=families,
        limit_per_family=limit_per_family,
        fallback_to_any_year=fallback_to_any_year,
    )
    evaluated_cases = []
    for case in cases:
        try:
            checker_result = document_compliance_service.run_submission_check(
                case["submission_id"],
                user_id,
            )
        except document_compliance_service.DocumentComplianceError as exc:
            checker_result = _error_result(exc)
        evaluated_cases.append(evaluate_validation_case(case, checker_result))

    report = build_validation_report(
        evaluated_cases,
        fiscal_years=fiscal_years,
        families=families,
    )
    paths = write_validation_report(report, output_root)
    return {**paths, "summary": report["summary"], "cases": evaluated_cases}


def evaluate_validation_case(case, checker_result):
    ground_truth = case.get("ground_truth") or {}
    expected_fields = ground_truth.get("expected_extracted_fields") or {}
    finding_ids = [
        item.get("id")
        for item in checker_result.get("findings") or []
        if item.get("id")
    ]
    field_matches = _field_expectation_matches(expected_fields, checker_result, family=case.get("family"))
    field_expectation_passed = all(field_matches.values()) if field_matches else False
    expected_status = ground_truth.get("expected_status")
    actual_status = checker_result.get("status")
    status_matches = bool(expected_status and actual_status == expected_status)
    false_approval = actual_status == "ready_for_approval" and expected_status != "ready_for_approval"
    reference_only = _blocked_only_by_reference_policy(
        expected_status=expected_status,
        actual_status=actual_status,
        finding_ids=finding_ids,
    )
    advisory_gate_only = _blocked_only_by_advisory_gate(
        expected_status=expected_status,
        actual_status=actual_status,
        finding_ids=finding_ids,
    )
    mapping_scan_gap = bool(set(finding_ids or []) & MAPPING_SCAN_FINDINGS)
    false_return = (
        expected_status == "ready_for_approval"
        and actual_status in {"likely_return", "invalid_evidence", "check_failed"}
        and not advisory_gate_only
    )

    return {
        **case,
        "checker_result_id": checker_result.get("id"),
        "expected_status": expected_status,
        "actual_status": actual_status,
        "recommended_action": checker_result.get("recommended_action"),
        "score": checker_result.get("score"),
        "finding_ids": finding_ids,
        "field_expectation_matches": field_matches,
        "field_expectation_passed": field_expectation_passed,
        "status_matches_ground_truth": status_matches,
        "blocked_only_by_reference_policy": reference_only,
        "blocked_only_by_advisory_gate": advisory_gate_only,
        "mapping_scan_gap": mapping_scan_gap,
        "false_approval": false_approval,
        "false_return": false_return,
        "passed": field_expectation_passed and not false_approval and not false_return,
        "advisory_only": True,
    }


def build_validation_report(cases, *, fiscal_years=(2023, 2024), families=TARGET_FAMILIES):
    evaluated = list(cases or [])
    summary = {
        "validation_version": VALIDATION_VERSION,
        "total_cases": len(evaluated),
        "field_passed_cases": sum(1 for item in evaluated if item.get("field_expectation_passed")),
        "status_matched_cases": sum(1 for item in evaluated if item.get("status_matches_ground_truth")),
        "false_approvals": sum(1 for item in evaluated if item.get("false_approval")),
        "false_returns": sum(1 for item in evaluated if item.get("false_return")),
        "reference_policy_gaps": sum(1 for item in evaluated if item.get("blocked_only_by_reference_policy")),
        "mapping_scan_gaps": sum(1 for item in evaluated if item.get("mapping_scan_gap")),
        "advisory_gate_gaps": sum(1 for item in evaluated if item.get("blocked_only_by_advisory_gate")),
        "fallback_year_cases": sum(1 for item in evaluated if item.get("selection_scope") == "fallback_year"),
        "requested_fiscal_years": [int(year) for year in fiscal_years or []],
        "target_families": list(families or TARGET_FAMILIES),
    }
    summary["field_accuracy"] = (
        summary["field_passed_cases"] / summary["total_cases"]
        if summary["total_cases"] else 0
    )
    summary["status_match_rate"] = (
        summary["status_matched_cases"] / summary["total_cases"]
        if summary["total_cases"] else 0
    )
    return {
        "validation_version": VALIDATION_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "summary": summary,
        "cases": evaluated,
        "advisory_only": True,
    }


def write_validation_report(report, output_root):
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "seeded_checker_accuracy_report.json"
    markdown_path = output_root / "seeded_checker_accuracy_report.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    return {
        "json_report_path": str(json_path),
        "markdown_report_path": str(markdown_path),
    }


def _case_from_document(document):
    stored_object = document.stored_object
    metadata = stored_object.object_metadata if stored_object else {}
    metadata = metadata or {}
    if not metadata.get("seed_demo"):
        return None
    family = metadata.get("documentary_requirement_family")
    if not family:
        return None
    submission = document.submission
    requirement = submission.project_requirement if submission else None
    project = requirement.project if requirement else None
    if not project:
        return None
    ground_truth = _load_ground_truth(document, metadata)
    return {
        "case_id": f"{project.fiscal_year}:{project.source_project_code}:{family}:{submission.id}",
        "family": family,
        "submission_id": submission.id,
        "document_file_id": document.id,
        "file_name": document.file_name,
        "file_path": document.file_path,
        "ground_truth_path": _ground_truth_path(document, metadata),
        "ground_truth": ground_truth,
        "project_id": project.id,
        "project_name": project.project_name,
        "source_project_code": project.source_project_code,
        "fiscal_year": project.fiscal_year,
        "lgu_name": project.lgu.name if project.lgu else None,
        "requirement_id": requirement.id,
        "requirement_name": requirement.requirement_name,
        "requirement_status": requirement.status,
        "pattern_source": metadata.get("pattern_source"),
    }


def _load_ground_truth(document, metadata):
    path_value = _ground_truth_path(document, metadata)
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _ground_truth_path(document, metadata):
    path_value = metadata.get("ground_truth_path")
    if path_value:
        return str(path_value)
    if document.file_path:
        return str(Path(document.file_path).with_suffix(".ground_truth.json"))
    return None


def _field_expectation_matches(expected_fields, checker_result, *, family=None):
    evidence = (
        (checker_result.get("extracted_fields") or {})
        .get("field_evidence")
        or {}
    )
    matches = evidence.get("matches") or {}
    fields = evidence.get("fields") or {}
    results = {}
    for field in _field_comparison_keys(family):
        expected = expected_fields.get(field)
        if expected in (None, ""):
            continue
        match = matches.get(field) or {}
        field_payload = fields.get(field) or {}
        results[field] = _field_value_matches(field, expected, match, field_payload)
    return results


def _field_value_matches(field, expected, match, field_payload):
    if match.get("status") == "matched":
        return True
    actual_values = [
        match.get("actual"),
        match.get("normalized_value"),
        (match.get("candidate") or {}).get("normalized_value"),
        (field_payload.get("best") or {}).get("normalized_value"),
        (field_payload.get("best") or {}).get("matched_text"),
    ]
    for candidate in field_payload.get("candidates") or []:
        actual_values.extend([
            candidate.get("normalized_value"),
            candidate.get("matched_text"),
        ])
    expected_normalized = _normalize_expected(field, expected)
    return any(
        _normalize_expected(field, value) == expected_normalized
        for value in actual_values
        if value not in (None, "")
    )


def _field_comparison_keys(family):
    return FIELD_COMPARISON_KEYS_BY_FAMILY.get(family, FIELD_COMPARISON_KEYS)


def _blocked_only_by_reference_policy(*, expected_status, actual_status, finding_ids):
    if expected_status != "ready_for_approval" or actual_status != "review_required":
        return False
    ids = set(finding_ids or [])
    return bool(ids & REFERENCE_POLICY_FINDINGS) and ids.issubset(ADVISORY_GATE_FINDINGS)


def _blocked_only_by_advisory_gate(*, expected_status, actual_status, finding_ids):
    if expected_status != "ready_for_approval" or actual_status != "review_required":
        return False
    ids = set(finding_ids or [])
    return bool(ids) and ids.issubset(ADVISORY_GATE_FINDINGS)


def _normalize_expected(field, value):
    if field == "amount":
        return _normalize_amount(value)
    if field == "fiscal_year":
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return str(value or "").strip()
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _normalize_amount(value):
    text = str(value or "")
    cleaned = re.sub(r"[^0-9.]", "", text)
    try:
        return f"{Decimal(cleaned):.2f}"
    except Exception:
        return text.strip()


def _error_result(exc):
    return {
        "status": "check_failed",
        "recommended_action": "manual_review",
        "score": 0,
        "findings": [{
            "id": "validation_checker_error",
            "severity": "blocker",
            "message": getattr(exc, "message", str(exc)),
        }],
        "extracted_fields": {},
    }


def _markdown_report(report):
    summary = report.get("summary") or {}
    lines = [
        "# Seeded Documentary Compliance Validation Report",
        "",
        f"Validation version: `{report.get('validation_version')}`",
        f"Generated at: `{report.get('generated_at')}`",
        "",
        "## Summary",
        "",
        f"- Total cases: {summary.get('total_cases', 0)}",
        f"- Field-passed cases: {summary.get('field_passed_cases', 0)}",
        f"- Field accuracy: {summary.get('field_accuracy', 0):.2%}",
        f"- Status-matched cases: {summary.get('status_matched_cases', 0)}",
        f"- Status match rate: {summary.get('status_match_rate', 0):.2%}",
        f"- False approvals: {summary.get('false_approvals', 0)}",
        f"- False returns: {summary.get('false_returns', 0)}",
        f"- Reference-policy gaps: {summary.get('reference_policy_gaps', 0)}",
        f"- Mapping-scan gaps: {summary.get('mapping_scan_gaps', 0)}",
        f"- Advisory-gate gaps: {summary.get('advisory_gate_gaps', 0)}",
        f"- Fallback-year cases: {summary.get('fallback_year_cases', 0)}",
        "",
        "## Cases",
        "",
        "| Family | FY | Project | Requirement | Expected | Actual | Score | Fields | Policy gap |",
        "| --- | ---: | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for item in report.get("cases") or []:
        lines.append(
            "| {family} | {fy} | {project} | {requirement} | {expected} | {actual} | {score:.2f} | {fields} | {gap} |".format(
                family=item.get("family"),
                fy=item.get("fiscal_year"),
                project=_pipe_safe(item.get("project_name")),
                requirement=_pipe_safe(item.get("requirement_name")),
                expected=item.get("expected_status"),
                actual=item.get("actual_status"),
                score=float(item.get("score") or 0),
                fields="pass" if item.get("field_expectation_passed") else "review",
                gap="yes" if item.get("blocked_only_by_reference_policy") else "no",
            )
        )
    lines.extend([
        "",
        "This report is advisory validation evidence only. Human reviewers retain final authority over documentary compliance decisions.",
        "",
    ])
    return "\n".join(lines)


def _pipe_safe(value):
    return str(value or "").replace("|", "\\|")


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
