import json
import re
from pathlib import Path, PureWindowsPath

from app.extensions import db
from app.models import DocumentFile, DocumentReferenceProfile
from app.services import document_compliance_rule_engine as rule_engine
from app.services import documentary_reference_pattern_service as pattern_service


TARGET_SEED_PROFILE_FAMILIES = (
    "nadai_fund_transfer",
    "detailed_engineering_estimate",
    "program_of_works",
    "billing_package",
    "official_receipt",
    "certification",
    "resolution",
    "progress_report",
    "generic_document",
    "inspection_and_acceptance",
    "apmv_acceptance_protocol",
    "drr1_equipment_checklist",
    "delivery_receipt",
    "property_transfer_report",
    "warranty_security",
    "beneficiary_payroll",
    "beneficiary_masterlist",
    "acknowledgement_receipt",
    "liquidation_report",
)


def seed_reference_profiles_from_seed_documents(
    *,
    user_id=None,
    fiscal_years=None,
    families=TARGET_SEED_PROFILE_FAMILIES,
    commit=True,
):
    """Create active checker profiles from safe generated seed attachments.

    The source Laguna files remain pattern references only. This service reads
    generated seed sidecars and stores portable format/profile metadata that the
    checker can use as an active template basis.
    """
    selected_years = {int(year) for year in fiscal_years or []}
    selected_families = set(families or TARGET_SEED_PROFILE_FAMILIES)
    created = 0
    updated = 0
    skipped = 0
    profiles = []

    for document in _seed_documents():
        payload = _profile_payload_from_document(
            document,
            selected_years=selected_years,
            selected_families=selected_families,
        )
        if not payload:
            skipped += 1
            continue

        profile = DocumentReferenceProfile.query.filter_by(reference_uri=payload["reference_uri"]).first()
        if profile is None:
            profile = DocumentReferenceProfile(
                reference_uri=payload["reference_uri"],
                reference_origin=payload["reference_origin"],
                reference_type=payload["reference_type"],
                created_by=int(user_id) if user_id is not None else None,
            )
            db.session.add(profile)
            created += 1
        else:
            updated += 1

        for key, value in payload.items():
            if key == "reference_uri":
                continue
            setattr(profile, key, value)
        db.session.flush()
        profiles.append({
            "id": profile.id,
            "reference_uri": profile.reference_uri,
            "family": payload["profile_metadata"].get("evidence_type"),
            "project_requirement_id": payload["profile_metadata"].get("project_requirement_id"),
        })

    if commit:
        db.session.commit()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total_profiles": DocumentReferenceProfile.query.count(),
        "profiles": profiles,
    }


def _seed_documents():
    return (
        DocumentFile.query
        .filter_by(is_primary=True)
        .order_by(DocumentFile.id.asc())
        .all()
    )


def _profile_payload_from_document(document, *, selected_years, selected_families):
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
    layout_profile = (
        ground_truth.get("layout_profile")
        or metadata.get("layout_profile")
        or pattern_service.layout_profile_for_family(family)
    )
    pattern_source = _safe_pattern_source(
        ground_truth.get("pattern_source") or metadata.get("pattern_source")
    )
    profile_metadata = _profile_metadata(
        family=family,
        layout_profile=layout_profile,
        pattern_source=pattern_source,
        document=document,
        requirement=requirement,
        ground_truth=ground_truth,
    )
    profile_metadata, errors = rule_engine.validate_profile_metadata(profile_metadata)
    if errors:
        profile_metadata = _profile_metadata(
            family="generic_document",
            layout_profile=layout_profile,
            pattern_source=pattern_source,
            document=document,
            requirement=requirement,
            ground_truth=ground_truth,
        )
        profile_metadata, _errors = rule_engine.validate_profile_metadata(profile_metadata)

    return {
        "reference_uri": _reference_uri(document, requirement, family),
        "reference_origin": "template",
        "reference_type": "sanitized_seed_pattern",
        "checker_reference_type": "official_template",
        "program_id": project.program_id,
        "program_cycle_id": project.program_cycle_id,
        "requirement_id": requirement.requirement_id,
        "requirement_name": requirement.requirement_name,
        "requirement_type": requirement.requirement_type,
        "phase_name": requirement.phase_name,
        "fiscal_year": project.fiscal_year,
        "project_kind": project.project_kind,
        "status": "active",
        "profile_metadata": profile_metadata,
    }


def _profile_metadata(*, family, layout_profile, pattern_source, document, requirement, ground_truth):
    metadata = {
        "evidence_type": family,
        "required_terms": _required_terms_from_layout(layout_profile),
        "format_profile": layout_profile or {},
        "format_profile_version": "sanitized_seed_layout_v1",
        "minimum_text_chars": 20,
        "pattern_source": pattern_source,
        "source_policy": {
            "use_original_files_as_seed_attachments": False,
            "use_original_files_as_pattern_references_only": True,
            "store_portable_pattern_source_only": True,
        },
        "generated_document_file_id": document.id,
        "submission_id": document.submission_id,
        "project_requirement_id": requirement.id,
        "uses_original_file": False,
        "advisory_only": True,
    }
    if ground_truth.get("document_id"):
        metadata["ground_truth_document_id"] = ground_truth.get("document_id")
    return metadata


def _required_terms_from_layout(layout_profile):
    terms = []
    for heading in (layout_profile or {}).get("required_headings") or []:
        terms.extend(heading.get("required_terms") or [])
        if heading.get("label"):
            terms.append(heading["label"])
    return list(dict.fromkeys(str(term).strip() for term in terms if str(term).strip()))


def _load_ground_truth(document, metadata):
    path_value = metadata.get("ground_truth_path")
    if not path_value and document.file_path:
        path_value = str(Path(document.file_path).with_suffix(".ground_truth.json"))
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _reference_uri(document, requirement, family):
    return f"seed-pattern:project-requirement:{requirement.id}:document:{document.id}:family:{family}"


def _safe_pattern_source(value):
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", normalized) or "/Downloads/" in normalized or "/Users/" in normalized:
        name = PureWindowsPath(text).name or Path(normalized).name or "reference-pattern"
        return f"sanitized_reference:{name}"
    return normalized
