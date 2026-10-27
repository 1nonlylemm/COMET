"""Shared Document Evidence Layer for COMET Intake, Matching, and Compliance.

Provides a normalized in-memory contract so document extraction, OCR,
visual context, and provider evidence are computed once and shared
across the Documentary Matcher and Documentary Checker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DocumentEvidence:
    # 1. Identity & File Attributes
    document_file_id: int | None = None
    submission_id: int | None = None
    project_requirement_id: int | None = None
    file_name: str = ''
    file_path: str = ''
    mime_type: str = ''
    file_size_bytes: int | None = None
    file_hash_sha256: str | None = None

    # 2. Text & OCR Extraction
    extracted_text: str = ''
    page_count: int | None = None
    text_locations: list[dict[str, Any]] = field(default_factory=list)
    extractors: list[str] = field(default_factory=list)
    readability_confidence: float | None = None
    warnings: list[str] = field(default_factory=list)
    is_ocr_fallback: bool = False
    extraction_metadata: dict[str, Any] = field(default_factory=dict)

    # 3. Visual & Photo Multimodal Context
    visual_summary: dict[str, Any] | None = None
    photo_metadata: dict[str, Any] | None = None

    # 4. Matcher Semantic Signals
    suggested_project_requirement_id: int | None = None
    suggested_requirement_name: str | None = None
    confidence: float | None = None
    matcher_confidence: float | None = None
    document_family: str | None = None  # e.g. 'financial', 'engineering', 'progress_report', etc.
    classification_label: str | None = None
    candidate_rankings: list[dict[str, Any]] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    ai_reason: str | None = None
    close_call: bool = False
    semantic_conflict: bool = False

    # 5. External Provider Evidence (AWS Textract, Rekognition, LanguageTool)
    provider_metadata: list[dict[str, Any]] = field(default_factory=list)
    provider_forms: list[dict[str, Any]] = field(default_factory=list)
    provider_tables: list[dict[str, Any]] = field(default_factory=list)
    textract_forms: dict[str, Any] = field(default_factory=dict)
    textract_tables: list[dict[str, Any]] = field(default_factory=list)
    rekognition_labels: list[dict[str, Any]] = field(default_factory=list)

    # 6. Structured Field Evidence
    field_evidence: dict[str, Any] | None = None

    # 7. R26 Pre-Submission Documentary Intelligence & Advisory Checks
    document_structure: str | None = None
    project_id: int | None = None
    project_name: str | None = None
    lgu_name: str | None = None
    document_state: str | None = None
    technical_checks: list[dict[str, Any]] = field(default_factory=list)
    technical_summary: dict[str, Any] = field(default_factory=dict)
    evidence_checks: list[dict[str, Any]] = field(default_factory=list)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    is_advisory: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_extraction_payload(self) -> dict[str, Any]:
        """Compatibility adapter matching legacy extract_document_text output shape."""
        metadata: dict[str, Any] = dict(self.extraction_metadata)
        metadata.setdefault('file_name', self.file_name)
        metadata.setdefault('mime_type', self.mime_type)
        metadata.setdefault('extension', Path(self.file_name).suffix.lower().lstrip('.'))
        if self.extractors and 'extractors' not in metadata:
            metadata['extractors'] = list(self.extractors)
        elif 'extractors' not in metadata:
            metadata['extractors'] = []
        if self.warnings and 'warnings' not in metadata:
            metadata['warnings'] = list(self.warnings)
        elif 'warnings' not in metadata:
            metadata['warnings'] = []
        if self.page_count is not None:
            metadata['page_count'] = self.page_count
        if self.text_locations:
            metadata['text_locations'] = self.text_locations
        if self.readability_confidence is not None:
            metadata['readability_confidence'] = self.readability_confidence

        payload: dict[str, Any] = {
            'text': self.extracted_text,
            'metadata': metadata,
        }
        if self.visual_summary is not None:
            payload['visual_summary'] = self.visual_summary
        if self.photo_metadata is not None:
            payload['photo_metadata'] = self.photo_metadata
        return payload
