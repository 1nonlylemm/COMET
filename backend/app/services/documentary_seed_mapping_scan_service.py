from decimal import Decimal

from app.extensions import db
from app.models import DocumentFile, NlpScanResult
from app.services.documentary_seed_reference_profile_service import TARGET_SEED_PROFILE_FAMILIES, _load_ground_truth


def seed_mapping_scans_from_seed_documents(
    *,
    user_id=None,
    fiscal_years=None,
    families=TARGET_SEED_PROFILE_FAMILIES,
    commit=True,
):
    """Seed accepted OCR/NLP mapping scans for generated demo documents."""
    selected_years = {int(year) for year in fiscal_years or []}
    selected_families = set(families or TARGET_SEED_PROFILE_FAMILIES)
    created = 0
    updated = 0
    skipped = 0
    scans = []

    documents = (
        DocumentFile.query
        .filter_by(is_primary=True)
        .order_by(DocumentFile.id.asc())
        .all()
    )
    for document in documents:
        payload = _scan_payload_from_document(
            document,
            selected_years=selected_years,
            selected_families=selected_families,
            user_id=user_id,
        )
        if not payload:
            skipped += 1
            continue

        scan = _existing_seed_scan(document.submission_id)
        if not scan:
            scan = NlpScanResult(submission_id=document.submission_id, is_seed_data=True)
            db.session.add(scan)
            created += 1
        else:
            scan.is_seed_data = True
            updated += 1

        for key, value in payload.items():
            setattr(scan, key, value)
        db.session.flush()
        scans.append({
            "id": scan.id,
            "submission_id": scan.submission_id,
            "project_requirement_id": scan.suggested_project_requirement_id,
            "family": scan.classification_label,
        })

    if commit:
        db.session.commit()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total_seed_scans": len(scans),
        "scans": scans,
    }


def _scan_payload_from_document(document, *, selected_years, selected_families, user_id):
    metadata = (document.stored_object.object_metadata if document.stored_object else {}) or {}
    if not metadata.get("seed_demo"):
        return None
    family = metadata.get("documentary_requirement_family")
    if not family or family not in selected_families:
        return None
    submission = document.submission
    requirement = submission.project_requirement if submission else None
    project = requirement.project if requirement else None
    if not requirement or not project:
        return None
    if selected_years and project.fiscal_year not in selected_years:
        return None

    ground_truth = _load_ground_truth(document, metadata)
    extracted_text = "\n".join(
        str(value)
        for value in (
            ground_truth.get("expected_project"),
            ground_truth.get("expected_lgu"),
            ground_truth.get("expected_fiscal_year"),
            ground_truth.get("expected_reference_number"),
            ground_truth.get("expected_amount"),
        )
        if value not in (None, "")
    )
    return {
        "suggested_requirement_id": requirement.requirement_id,
        "suggested_project_requirement_id": requirement.id,
        "confidence_score": Decimal("0.9800"),
        "extracted_text": extracted_text,
        "matched_keywords": [
            requirement.requirement_name,
            project.project_name,
            project.source_project_code,
            family,
        ],
        "classification_label": family,
        "is_accepted": True,
        "scan_metadata": {
            "seed_demo": True,
            "seed_demo_mapping_scan": True,
            "generated_document_file_id": document.id,
            "ground_truth_document_id": ground_truth.get("document_id"),
            "source": "generated_seed_document",
            "advisory_only": True,
        },
        "reviewed_by": int(user_id) if user_id is not None else None,
        "review_notes": "Verified documentary compliance mapping against standard PDMU intake checklist requirements.",
    }


def _existing_seed_scan(submission_id):
    scans = (
        NlpScanResult.query
        .filter_by(submission_id=submission_id)
        .order_by(NlpScanResult.id.asc())
        .all()
    )
    for scan in scans:
        metadata = scan.scan_metadata or {}
        if metadata.get("seed_demo_mapping_scan"):
            return scan
    return None
