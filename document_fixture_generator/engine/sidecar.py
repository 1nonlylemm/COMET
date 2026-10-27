"""Canonical sidecar builder conforming to schema comet.document_fixture.v1.

Strictly separates formal human adjudication policy from component-level expected results
and operational checker sentinels.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


class CanonicalSidecarBuilder:
    """Builds and serializes canonical ground-truth sidecar metadata."""

    SCHEMA_VERSION = "comet.document_fixture.v1"
    GENERATOR_VERSION = "0.1.0"

    @staticmethod
    def build_sidecar(
        *,
        fixture_id: str,
        family: str,
        requirement_id: str,
        evidence_type: str,
        project_context: dict[str, Any],
        source_provenance: dict[str, Any],
        is_flag_free: bool,
        requirement_name: str | None = None,
        expected_document_fields: dict[str, Any] | None = None,
        extracted_fields: list[str] | dict[str, Any] | None = None,
        field_matches: dict[str, str] | None = None,
        expected_findings: list[dict[str, Any]] | None = None,
        pages: list[dict[str, Any]] | None = None,
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        """Construct a validated comet.document_fixture.v1 sidecar dictionary."""
        if generated_at is None:
            generated_at = datetime.now(timezone.utc).isoformat()

        field_matches = field_matches or {}
        expected_findings = expected_findings or []
        expected_document_fields = expected_document_fields or {}
        pages = pages or [
            {
                "page": 1,
                "role": "primary_operative",
                "geometry": {
                    "width_pt": 595.28,
                    "height_pt": 841.89,
                    "orientation": "portrait",
                },
                "fields": {},
                "annotations": [],
            }
        ]

        # Verify page bounding boxes conform strictly to single [x1, y1, x2, y2]
        for p in pages:
            for field_name, fld in p.get("fields", {}).items():
                bbox = fld.get("bbox")
                if bbox is not None:
                    CanonicalSidecarBuilder.assert_valid_canonical_bbox(bbox, field_name)
            for annot in p.get("annotations", []):
                bbox = annot.get("bbox")
                if bbox is not None:
                    CanonicalSidecarBuilder.assert_valid_canonical_bbox(bbox, annot.get("label", "annotation"))

        sidecar = {
            "schema_version": CanonicalSidecarBuilder.SCHEMA_VERSION,
            "fixture_id": fixture_id,
            "generated_at": generated_at,
            "generator_version": CanonicalSidecarBuilder.GENERATOR_VERSION,
            "source_provenance": source_provenance,
            "document_identity": {
                "family": family,
                "requirement_id": requirement_id,
                **({"requirement_name": requirement_name} if requirement_name else {}),
                "evidence_type": evidence_type,
                "page_count": len(pages),
            },
            # Intended document values authored in fixture specification & template context
            "expected_document_fields": expected_document_fields,
            # Expected values in database context that COMET evaluates document against
            "project_context": project_context,
            # Formal human adjudication metadata ONLY (Strictly separate from component/checker outcomes)
            "adjudication": {
                "gold_eligible": False,  # Strict invariant: unreviewed synthetic fixture
                "adjudication_status": "synthetic_pilot",
                "policy_notes": (
                    "Synthetic test fixture generated for component validation; "
                    "requires independent human adjudication for benchmark gold eligibility."
                ),
            },
            # Expected component-level and operational checker results
            "expected_component_results": {
                "operational_status": {
                    "status": "review_required",
                    "recommended_action": "manual_review",
                    "score": 100.0,
                },
                "derived_metrics": {
                    "is_flag_free": is_flag_free,
                },
                **({"extracted_fields": extracted_fields} if extracted_fields is not None else {}),
                "field_matches": field_matches,
                "expected_findings": expected_findings,
            },
            "pages": pages,
        }

        return sidecar

    @staticmethod
    def assert_valid_canonical_bbox(bbox: Any, context: str = "") -> None:
        """Validate that bbox is a list or tuple of 4 floats: [x1, y1, x2, y2] in [0.0, 1.0]."""
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            raise ValueError(
                f"Invalid bbox format in {context}: expected 4-element list/tuple [x1, y1, x2, y2], got {bbox}"
            )
        x1, y1, x2, y2 = bbox
        for val, name in ((x1, "x1"), (y1, "y1"), (x2, "x2"), (y2, "y2")):
            if not isinstance(val, (int, float)):
                raise TypeError(f"Invalid coordinate type for {name} in {context}: {type(val)}")
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"Coordinate {name}={val} in {context} outside normalized range [0.0, 1.0]")
        if x1 > x2:
            raise ValueError(f"Invalid coordinate ordering x1 ({x1}) > x2 ({x2}) in {context}")
        if y1 > y2:
            raise ValueError(f"Invalid coordinate ordering y1 ({y1}) > y2 ({y2}) in {context}")

    @staticmethod
    def serialize_sidecar(sidecar_dict: dict[str, Any]) -> str:
        """Serialize sidecar to deterministic, sorted, indented JSON."""
        return json.dumps(sidecar_dict, indent=2, sort_keys=True)
