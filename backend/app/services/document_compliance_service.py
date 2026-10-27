import json
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from flask import current_app, has_app_context
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    DEFICIENCY_CATEGORIES,
    DocumentComplianceResult,
    DocumentFile,
    DocumentReferenceProfile,
    NlpScanResult,
    Program,
    ProgramCycle,
    ProjectRequirement,
    Requirement,
    Submission,
)
from app.services import (
    access_service,
    audit_service,
    document_annotation_service,
    document_format_profile_service,
    document_intelligence_service,
    document_language_tool_provider as language_tool_provider,
    library_service,
    object_storage_service,
)
from app.services import document_compliance_rule_engine as rule_engine
from app.services import document_supporting_evidence
from app.services import document_compliance_field_evidence as field_evidence_service
from app.services import document_compliance_evidence_checker as evidence_checker
from app.services import document_compliance_language_quality as language_quality_service
from app.services import document_compliance_photo_evidence as photo_evidence_service
from app.services import document_compliance_technical_checker as technical_checker
from app.services import document_compliance_visual as visual_service
from app.services import document_compliance_visual_metadata as visual_metadata_service
from app.services import document_compliance_explanation as explanation_service
from app.services import document_compliance_grounding as grounding_service
from app.services import document_language_geometry as language_geometry
from app.services.document_compliance_providers import ProviderError, ProviderResult
from app.services.document_compliance_providers import registry as provider_registry
from app.services.document_compliance_providers import aws as aws_providers
from app.services.document_compliance_providers import collect_provider_metadata


CHECKER_VERSION = 'document_compliance_v3_evidence_review'
CHECKER_REFERENCE_TYPES = {
    'official_template',
    'accepted_sample',
    'returned_sample',
    'guideline_basis',
    'logo_letterhead_reference',
    'validation_checklist',
}
REFERENCE_PROFILE_STATUSES = {'draft', 'active', 'superseded', 'archived'}
REVIEWER_DECISIONS = {
    'accept_checker_result',
    'override_approve',
    'override_return',
    'mark_false_positive',
    'mark_checker_missed_evidence',
}
REVIEW_REASON_CODES = {
    'missing_amount',
    'wrong_lgu',
    'unreadable_scan',
    'wrong_project',
    'missing_signature',
    'obsolete_template',
    'incomplete_attachment',
    'checker_false_positive',
    'checker_missed_evidence',
    'no_issue',
}


class DocumentComplianceError(Exception):
    def __init__(self, message, status_code=400, errors=None):
        self.message = message
        self.status_code = status_code
        self.errors = errors or {}
        super().__init__(message)


def run_submission_check(submission_id, user_id, *, use_prior_year_reference=False, evidence=None):
    submission = _submission_with_access(submission_id, user_id)
    document_file = _primary_document_file(submission)
    if document_file is None:
        raise DocumentComplianceError('No documentary file is available for compliance checking.', 409)
    evidence_file_id = getattr(evidence, 'document_file_id', None)
    if evidence_file_id is not None and evidence_file_id != document_file.id:
        raise DocumentComplianceError('The extracted evidence belongs to a different document version. Re-run extraction for the current primary file.', 409)

    requirement = submission.project_requirement
    if requirement is None or requirement.project is None:
        raise DocumentComplianceError('Submission is not linked to a project requirement.', 409)

    if evidence is not None:
        extraction = evidence.to_extraction_payload()
        if 'visual_summary' not in extraction or 'photo_metadata' not in extraction:
            if document_file.stored_object is not None:
                with object_storage_service.temporary_file(document_file.stored_object) as temp_path:
                    _attach_visual_context(extraction, document_file=document_file, file_path=temp_path)
            elif document_file.file_path and Path(document_file.file_path).exists():
                _attach_visual_context(extraction, document_file=document_file, file_path=Path(document_file.file_path))
            if 'visual_summary' in extraction and evidence.visual_summary is None:
                evidence.visual_summary = extraction['visual_summary']
            if 'photo_metadata' in extraction and evidence.photo_metadata is None:
                evidence.photo_metadata = extraction['photo_metadata']
    else:
        extraction = _extract_text(document_file)
    scan = _latest_scan(submission)
    # Phase 2.1: Requirement checker_config is the authoritative source of truth.
    # DocumentReferenceProfile is retained for historical compatibility only and has zero influence on active review.
    checker_config = evidence_checker.resolve_requirement_checker_configuration(requirement)
    active_evidence_type = (
        checker_config.get('evidence_type')
        or rule_engine.infer_evidence_type_from_requirement(
            requirement_name=requirement.requirement_name,
            requirement_type=requirement.requirement_type,
            annex_reference=requirement.annex_reference,
            custom_fields=getattr(requirement, 'custom_fields', None),
        )
        or rule_engine.DEFAULT_EVIDENCE_TYPE
    )
    # Phase 2.2: DocumentReferenceProfile is strictly historical compatibility only.
    # New Document Review Assistant runs do NOT query reference profiles.
    profile_selection = None
    provider_metadata, provider_findings = _collect_provider_outputs(
        document_file=document_file,
        extraction=extraction,
        profile_selection=profile_selection,
        evidence_type=active_evidence_type,
    )
    textract_forms = []
    if evidence and evidence.provider_forms:
        textract_forms.extend(evidence.provider_forms)
    for p_item in provider_metadata:
        forms = (p_item.get('raw_payload') or {}).get('forms') or []
        if forms:
            textract_forms.extend(forms)
    if evidence is not None:
        evidence.provider_forms = textract_forms

    field_evidence = field_evidence_service.extract_field_evidence(
        extraction.get('text') or '',
        file_name=document_file.file_name,
        expected=_expected_field_context(submission),
        evidence_type=active_evidence_type,
        checker_config=checker_config,
        text_locations=(extraction.get('metadata') or {}).get('text_locations'),
        extraction_metadata=extraction.get('metadata') or {},
        provider_forms=textract_forms,
    )

    # Phase R7.1A: Technical Document Integrity Checks
    local_eval_path = None
    if document_file.file_path and Path(document_file.file_path).exists():
        local_eval_path = Path(document_file.file_path)

    technical_eval = technical_checker.evaluate_technical_integrity(
        document_file=document_file,
        extraction=extraction,
        file_path=local_eval_path,
        requirement=requirement,
        checker_config=checker_config,
    )
    technical_checks = technical_eval.get('technical_checks', [])
    technical_summary = technical_eval.get('technical_summary', {})
    document_state = technical_eval.get('document_state', technical_checker.STATE_CONTENT_PRESENT_READABLE)
    is_blank = technical_eval.get('is_blank', False)

    # Phase R6 & R7.1A: Evaluate Requirement-Driven Documentary Evidence & Coverage
    analysis_coverage = _build_analysis_coverage(extraction, document_file)

    findings = _build_findings(
        submission=submission,
        document_file=document_file,
        extraction=extraction,
        latest_scan=scan,
        profile_selection=profile_selection,
        use_prior_year_reference=use_prior_year_reference,
        field_evidence=field_evidence,
        evidence=evidence,
        technical_eval=technical_eval,
        checker_config=checker_config,
        evidence_type=active_evidence_type,
    )
    language_findings = [f for f in findings if f.get('id') == 'language_quality_review']
    if language_findings and 'pdf' in str(document_file.mime_type or '').lower():
        def attach_language_geometry(path):
            for item in language_findings:
                item['locations'] = language_geometry.resolve_language_geometry(
                    item.get('locations') or [], path,
                    max_pages=analysis_coverage.get('pages_analyzed') or 20,
                )
        if document_file.stored_object is not None:
            with object_storage_service.temporary_file(document_file.stored_object) as path:
                attach_language_geometry(path)
        elif local_eval_path is not None:
            attach_language_geometry(local_eval_path)

    photo_evidence_result = photo_evidence_service.evaluate_photo_evidence(
        extraction=extraction,
        provider_metadata=provider_metadata,
        checker_config=checker_config,
        evidence_type=active_evidence_type,
    )
    findings.extend(provider_findings)
    findings.extend(photo_evidence_result.get('findings') or [])
    photo_evidence_checks = photo_evidence_result.get('checks') or {}
    if photo_evidence_checks:
        extraction['photo_evidence_checks'] = photo_evidence_checks
    visual_evidence_summary = _build_visual_evidence_summary(
        extraction=extraction,
        provider_metadata=provider_metadata,
        photo_evidence_checks=photo_evidence_checks,
        evidence_type=active_evidence_type,
    )
    if visual_evidence_summary:
        extraction['visual_evidence_summary'] = visual_evidence_summary
        findings.append(_finding(
            'visual_evidence_summary',
            'info',
            'summary',
            'Visual evidence summary was generated for this photo requirement.',
            visual_evidence_summary.get('description'),
        ))
    supporting_summary = {'reviewed_files': [], 'unavailable_files': []}
    if is_blank:
        # Phase R7.1A: Suppress downstream evidence checks when document is blank!
        evidence_checks = []
        evidence_summary = {
            'total_required': 0,
            'required_count': 0,
            'detected_count': 0,
            'not_detected_count': 0,
            'missing_count': 0,
            'all_required_detected': False,
            'is_blank': True,
            'status_message': 'Document contains no meaningful content; evidence checks suppressed',
        }
        evidence_findings = []
    else:
        evidence_eval = evidence_checker.evaluate_document_evidence(
            extraction.get('text') or '',
            checker_config=checker_config,
            file_name=document_file.file_name,
            extraction=extraction,
            file_path=local_eval_path,
            analysis_coverage=analysis_coverage,
        )
        evidence_checks = evidence_eval.get('evidence_checks', [])
        if evidence_checks:
            evidence_checks, supporting_summary = document_supporting_evidence.inspect_supporting_evidence(
                submission, document_file, checker_config, _extract_text, evidence_checks,
            )
            evidence_eval = evidence_checker.summarize_evidence_checks(evidence_checks)
        evidence_summary = evidence_eval.get('evidence_summary', {})
        evidence_findings = evidence_eval.get('findings', [])
        for item in evidence_findings:
            if item.get('requirement_basis'):
                item['requirement_basis'].update(requirement_name=requirement.requirement_name, annex_reference=requirement.annex_reference)

    findings.extend(evidence_findings)
    for item in findings:
        item.setdefault('document_file_id', document_file.id)
        item.setdefault('file_name', document_file.file_name)
    if any(item.get('id') != 'basic_checks_passed' for item in findings):
        findings = [item for item in findings if item.get('id') != 'basic_checks_passed']
    findings = rule_engine.deduplicate_findings(findings)
    findings = [map_finding_to_deficiency(f, requirement=requirement, project=requirement.project) for f in findings]

    # Phase 3.2: Plain-Language Reviewer Explanation & Guidance Layer
    allow_ai = current_app.config.get(
        'DOCUMENT_CHECKER_ENABLE_LLM_EXPLANATION',
        not current_app.config.get('TESTING', False),
    )
    explanation_payload = explanation_service.generate_document_explanation(
        findings,
        document_context={
            'file_name': getattr(document_file, 'file_name', None),
            'requirement_name': getattr(requirement, 'requirement_name', None) or getattr(requirement, 'title', None),
            'project_kind': getattr(getattr(requirement, 'project', None), 'project_type', None),
        },
        user_id=user_id,
        allow_ai=allow_ai,
    )
    findings = explanation_service.enrich_findings_with_explanation(findings, explanation_payload)

    findings_count = rule_engine.summarize_findings(findings)

    # Phase 2.4: Active review builds neutral summary directly; no scoring math executed.
    score_details = rule_engine.build_review_summary(
        findings,
        evidence_type=active_evidence_type,
        requirement_checks_configured=evidence_checker.requirement_checks_configured(checker_config),
    )
    score_details = _with_reviewer_decision_policy(score_details)
    # Phase 1, 2.3 & 2.4: Storage Sentinel & Neutral Review Contract
    # Physical DB score=100.00 is a storage compatibility sentinel satisfying schema constraints.
    # No score_band or overall_score is generated for active reviews.
    score_details['review_mode'] = 'manual_evaluation'
    score_details['analysis_coverage'] = analysis_coverage
    score_details['findings_count'] = findings_count
    format_profiles = document_format_profile_service.format_profile_summary(profile_selection)
    if format_profiles:
        score_details = {**score_details, 'format_profiles': format_profiles}
    suggested_notes = _suggest_return_notes(findings, profile_selection)

    if provider_metadata:
        score_details = {**score_details, 'provider_metadata': provider_metadata}
    if visual_evidence_summary:
        score_details = {**score_details, 'visual_evidence_summary': visual_evidence_summary}

    score_details['technical_checks'] = technical_checks
    score_details['supporting_evidence_summary'] = supporting_summary
    score_details['technical_summary'] = technical_summary
    score_details['document_state'] = document_state
    score_details['evidence_checks'] = evidence_checks
    score_details['evidence_summary'] = evidence_summary
    score_details['checker_configuration'] = checker_config
    score_details['explanation'] = explanation_payload

    extracted_fields = _extracted_field_summary(
        submission=submission,
        document_file=document_file,
        extraction=extraction,
        latest_scan=scan,
        field_evidence=field_evidence,
    )
    extracted_fields['technical_checks'] = technical_checks
    extracted_fields['technical_summary'] = technical_summary
    extracted_fields['document_state'] = document_state
    extracted_fields['evidence_checks'] = evidence_checks
    extracted_fields['evidence_summary'] = evidence_summary
    extracted_fields['analysis_coverage'] = analysis_coverage
    extracted_fields['findings_count'] = findings_count
    extracted_fields['requirement_checks_configured'] = score_details['requirement_checks_configured']
    extracted_fields['explanation'] = explanation_payload

    result = DocumentComplianceResult(
        submission_id=submission.id,
        document_file_id=document_file.id,
        project_requirement_id=submission.project_requirement_id,
        score=Decimal('100.00'),
        status='review_required',
        recommended_action='manual_review',
        reference_basis={'mode': 'document_review_assistant_v2'},
        findings=findings,
        extracted_fields=extracted_fields,
        score_details=score_details,
        suggested_return_notes=suggested_notes,
        checker_version=CHECKER_VERSION,
        created_by=int(user_id) if user_id is not None else None,
    )
    db.session.add(result)
    db.session.commit()

    audit_service.log_action(
        user_id=user_id,
        action='document_compliance_check',
        entity_type='document_compliance_result',
        entity_id=result.id,
        old_value=None,
        new_value=serialize_compliance_result(result),
    )
    return serialize_compliance_result(result)


def list_submission_results(submission_id, user_id):
    submission = _submission_with_access(submission_id, user_id)
    results = (
        submission.compliance_results
        .order_by(DocumentComplianceResult.created_at.desc(), DocumentComplianceResult.id.desc())
        .all()
    )
    return [serialize_compliance_result(item) for item in results]


def review_compliance_result(result_id, *, user_id, decision=None, reason_codes=None, review_notes=None, finding_reviews=None):
    result = _compliance_result_with_access(result_id, user_id)
    project_requirement_id = result.project_requirement_id or (result.submission.project_requirement_id if result.submission else None)
    try:
        access_service.assert_project_requirement_movement_allowed(project_requirement_id)
    except access_service.AccessError as exc:
        raise DocumentComplianceError(exc.message, exc.status_code) from exc
    if finding_reviews is not None:
        if decision is not None:
            raise DocumentComplianceError('Save finding decisions separately from the overall reviewer note.', 400)
        return _record_finding_reviews(result, finding_reviews, user_id)
    decision_payload = _validate_reviewer_decision(
        decision=decision,
        reason_codes=reason_codes,
        review_notes=review_notes,
    )
    before = serialize_compliance_result(result)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    score_details = _with_reviewer_decision_policy(result.score_details or {})
    score_details['reviewer_decision'] = {
        **decision_payload,
        'reviewed_by': int(user_id) if user_id is not None else None,
        'reviewed_at': now,
        'checker_status_at_review': result.status,
        'checker_recommended_action_at_review': result.recommended_action,
        'checker_score_at_review': float(result.score) if result.score is not None else None,
        'human_final_authority': True,
        'audit_action': 'review_document_compliance_result',
    }
    result.score_details = score_details
    db.session.commit()
    after = serialize_compliance_result(result)
    audit_service.log_action(
        user_id=user_id,
        action='review_document_compliance_result',
        entity_type='document_compliance_result',
        entity_id=result.id,
        old_value=before,
        new_value=after,
    )
    return after


def _record_finding_reviews(result, updates, user_id):
    if not isinstance(updates, list) or not updates or len(updates) > 100:
        raise DocumentComplianceError('Provide between 1 and 100 finding decisions.', 400)
    known = {str(item.get('id') or item.get('finding_id')) for item in result.findings or []}
    validated, seen = [], set()
    for update in updates:
        if not isinstance(update, dict):
            raise DocumentComplianceError('Finding decisions must be objects.', 400)
        finding_id = str(update.get('finding_id') or '')
        status = update.get('status')
        note = update.get('note', '')
        if finding_id not in known or finding_id in seen:
            raise DocumentComplianceError('Finding decisions must identify unique findings from this result.', 400)
        if not isinstance(status, str) or status not in {'confirmed', 'incorrect_flag', 'needs_verification'} or not isinstance(note, str) or len(note) > 2000:
            raise DocumentComplianceError('Invalid finding decision or note (maximum 2,000 characters).', 400)
        if status == 'incorrect_flag' and not note.strip():
            raise DocumentComplianceError('Explain why this finding is an incorrect flag.', 400)
        seen.add(finding_id)
        validated.append({'finding_id': finding_id, 'status': status, 'note': note.strip()})
    before = serialize_compliance_result(result)
    details = dict(result.score_details or {})
    reviews = dict(details.get('finding_reviews') or {})
    history = list(details.get('finding_review_history') or [])
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for update in validated:
        review = {**update, 'reviewed_by': int(user_id), 'reviewed_at': now}
        reviews[update['finding_id']] = review
        history.append(review)
    details.update(finding_reviews=reviews, finding_review_history=history)
    result.score_details = details
    db.session.commit()
    after = serialize_compliance_result(result)
    audit_service.log_action(user_id=user_id, action='review_document_finding', entity_type='document_compliance_result',
                             entity_id=result.id, old_value=before, new_value=after)
    return after


def latest_result_summary(submission):
    if not submission:
        return None
    result = (
        submission.compliance_results
        .order_by(DocumentComplianceResult.created_at.desc(), DocumentComplianceResult.id.desc())
        .first()
    )
    return serialize_compliance_result(result) if result else None


def get_reference_profile(reference_uri, *, user_id, user_role):
    reference = _resolve_reference(reference_uri, user_id=user_id, user_role=user_role)
    profile = DocumentReferenceProfile.query.filter_by(reference_uri=reference['reference_uri']).first()
    return serialize_reference_profile(profile, reference=reference) if profile else {
        'reference_uri': reference['reference_uri'],
        'reference_origin': reference.get('origin'),
        'reference_type': reference.get('reference_type'),
        'configured': False,
    }


def upsert_reference_profile(reference_uri, data, *, user_id, user_role):
    _ensure_profile_write_role(user_role)
    reference = _resolve_reference(reference_uri, user_id=user_id, user_role=user_role)
    values = _validate_reference_profile_payload(data or {}, reference)
    values['profile_metadata'] = _with_auto_format_profile(
        reference,
        values,
        user_id=user_id,
        user_role=user_role,
    )

    profile = DocumentReferenceProfile.query.filter_by(reference_uri=reference['reference_uri']).first()
    action = 'update' if profile else 'create'
    before = serialize_reference_profile(profile, reference=reference) if profile else None
    if profile is None:
        profile = DocumentReferenceProfile(
            reference_uri=reference['reference_uri'],
            reference_origin=reference.get('origin'),
            reference_type=reference.get('reference_type'),
            created_by=int(user_id) if user_id is not None else None,
        )
        db.session.add(profile)

    for key, value in values.items():
        setattr(profile, key, value)
    db.session.commit()

    audit_service.log_action(
        user_id=user_id,
        action=f'{action}_document_reference_profile',
        entity_type='document_reference_profile',
        entity_id=profile.id,
        old_value=before,
        new_value=serialize_reference_profile(profile, reference=reference),
    )
    return serialize_reference_profile(profile, reference=reference)


def delete_reference_profile(reference_uri, *, commit=True):
    profile = DocumentReferenceProfile.query.filter_by(reference_uri=reference_uri).first()
    if not profile:
        return False
    db.session.delete(profile)
    if commit:
        db.session.commit()
    return True


def checker_profile_summary(reference_uri):
    profile = DocumentReferenceProfile.query.filter_by(reference_uri=reference_uri).first()
    if not profile:
        return None
    return {
        'id': profile.id,
        'configured': True,
        'checker_reference_type': profile.checker_reference_type,
        'status': profile.status,
        'program_id': profile.program_id,
        'program_cycle_id': profile.program_cycle_id,
        'requirement_id': profile.requirement_id,
        'requirement_name': profile.requirement_name,
        'requirement_type': profile.requirement_type,
        'phase_name': profile.phase_name,
        'fiscal_year': profile.fiscal_year,
        'project_kind': profile.project_kind,
    }


def _build_analysis_coverage(extraction, document_file):
    metadata = (extraction or {}).get('metadata') or {}
    total_pages = metadata.get('page_count')
    extractors = metadata.get('extractors') or []

    try:
        from flask import current_app
        max_pages = max(int(current_app.config.get('DOCUMENT_OCR_MAX_PAGES') or 3), 1)
    except Exception:
        max_pages = 3
    try:
        max_pages = max(int(metadata.get('text_page_limit') or max_pages), 1)
    except (TypeError, ValueError):
        pass

    if total_pages is not None:
        try:
            total_pages = int(total_pages)
        except (ValueError, TypeError):
            total_pages = None

    file_name = getattr(document_file, 'file_name', None) or ''
    extension = Path(file_name).suffix.lower() if file_name else ''

    if extension in {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'} or ('tesseract' in extractors and extension != '.pdf' and not total_pages):
        return {
            'pages_analyzed': 1,
            'total_pages': 1,
            'max_pages_configured': max_pages,
            'mode': 'complete_ocr',
            'is_partial': False,
            'label': 'Single Page (Complete Image OCR)',
            'unexamined_pages_count': 0,
            'notice': None,
            'extractors': extractors,
        }

    if total_pages is not None and total_pages > 0:
        try:
            processed = int(metadata.get('pages_processed', max_pages))
        except (TypeError, ValueError):
            processed = max_pages
        pages_analyzed = min(total_pages, max(0, processed))
        unreadable = metadata.get('unreadable_pages') or []
        is_partial = pages_analyzed < total_pages or bool(unreadable) or bool(metadata.get('coverage_unknown'))
        unexamined = max(0, total_pages - pages_analyzed)

        if 'pypdf_image_ocr' in extractors:
            mode = 'partial_ocr' if is_partial else 'complete_ocr'
            label = (
                f"Pages 1–{pages_analyzed} of {total_pages} (Partial OCR)"
                if is_partial else
                f"{total_pages} Page{'s' if total_pages != 1 else ''} (Complete OCR)"
            )
        elif 'pypdf' in extractors:
            mode = 'partial_vector' if is_partial else 'complete_vector'
            label = (
                f"Pages 1–{pages_analyzed} of {total_pages} (Partial Vector Scan)"
                if is_partial else
                f"{total_pages} Page{'s' if total_pages != 1 else ''} (Complete Vector Scan)"
            )
        else:
            mode = 'partial_scan' if is_partial else 'complete_scan'
            label = (
                f"Pages 1–{pages_analyzed} of {total_pages} (Partial Scan)"
                if is_partial else
                f"{total_pages} Page{'s' if total_pages != 1 else ''} (Complete Text)"
            )

        notice = None
        if is_partial:
            notice = (
                f"Analysis evaluated Pages 1–{pages_analyzed} of {total_pages}. "
                f"Pages {pages_analyzed + 1}–{total_pages} were not examined by automated checks. "
                "Reviewer inspection required for unexamined pages."
            )
            if unreadable:
                label = f'{pages_analyzed} of {total_pages} pages attempted (Some pages unreadable)'
                notice = f'Pages {", ".join(map(str, unreadable))} could not be read reliably. Inspect them in the original document.'
                if unexamined:
                    notice += f' {unexamined} additional page(s) were not examined.'

        return {
            'pages_analyzed': pages_analyzed,
            'total_pages': total_pages,
            'max_pages_configured': max_pages,
            'mode': mode,
            'is_partial': is_partial,
            'label': label,
            'unexamined_pages_count': unexamined,
            'notice': notice,
            'extractors': extractors,
        }

    if metadata.get('coverage_unknown'):
        return {'pages_analyzed': metadata.get('pages_processed', 0), 'total_pages': None,
                'max_pages_configured': max_pages, 'mode': 'unknown', 'is_partial': True,
                'label': 'Page coverage could not be verified', 'unexamined_pages_count': None,
                'notice': 'Inspect the original document; automated page coverage is unknown.'}

    return {
        'pages_analyzed': 1,
        'total_pages': 1,
        'max_pages_configured': max_pages,
        'mode': 'complete_direct',
        'is_partial': False,
        'label': 'Complete Document Text',
        'unexamined_pages_count': 0,
        'notice': None,
        'extractors': extractors,
    }


def serialize_compliance_result(result):
    if result is None:
        return None
    findings = _dedupe_findings_for_display(result.findings or [])
    raw_basis = result.reference_basis
    if isinstance(raw_basis, dict):
        reference_basis = dict(raw_basis)
    elif raw_basis:
        reference_basis = {'notes': str(raw_basis)}
    else:
        reference_basis = {}
    legacy_score_details = reference_basis.pop('score_details', None)
    score_details = result.score_details or legacy_score_details
    score_details = _with_reviewer_decision_policy(score_details or {})
    if isinstance(score_details, dict):
        score_details = dict(score_details)
        score_details.pop('score_band', None)
        score_details.pop('overall_score', None)
        score_details.pop('subscores', None)
        score_details.pop('weights', None)
        score_details.pop('applied_weights', None)
        score_details.pop('caps', None)
        score_details.pop('cap_applied', None)
        if 'review_mode' not in score_details:
            score_details['review_mode'] = 'manual_evaluation'
    if not score_details:
        score_details = None
    # Recompute from the returned findings even for legacy rows. Work on copies:
    # correcting API metadata must not backfill or dirty persisted JSON columns.
    findings_summary = rule_engine.summarize_findings(findings)
    score_details = dict(score_details or {})
    score_details['findings_count'] = findings_summary
    extracted_fields = dict(result.extracted_fields or {})
    extracted_fields['findings_count'] = findings_summary
    reviewer_decision = (score_details or {}).get('reviewer_decision')
    reviewer_decision_policy = (score_details or {}).get('reviewer_decision_policy')
    technical_checks = (score_details or {}).get('technical_checks') or (result.extracted_fields or {}).get('technical_checks') or []
    technical_summary = (score_details or {}).get('technical_summary') or (result.extracted_fields or {}).get('technical_summary') or {}
    document_state = (score_details or {}).get('document_state') or (result.extracted_fields or {}).get('document_state') or None
    evidence_checks = (score_details or {}).get('evidence_checks') or (result.extracted_fields or {}).get('evidence_checks') or []
    evidence_summary = (score_details or {}).get('evidence_summary') or (result.extracted_fields or {}).get('evidence_summary') or {}
    checker_configuration = (score_details or {}).get('checker_configuration') or (result.extracted_fields or {}).get('checker_configuration') or {}
    # Scope belongs to this saved run, never to today's requirement settings.
    if 'requirement_checks_configured' in score_details:
        configured = bool(score_details['requirement_checks_configured'])
    else:
        configured = bool(evidence_summary.get('required_count', 0) > 0 or evidence_checks)
    score_details.update(rule_engine.build_review_summary(
        findings, evidence_type=score_details.get('evidence_type'),
        requirement_checks_configured=configured))
    extracted_fields['requirement_checks_configured'] = configured
    analysis_coverage = (
        (score_details or {}).get('analysis_coverage')
        or (result.extracted_fields or {}).get('analysis_coverage')
        or None
    )
    return {
        'id': result.id,
        'submission_id': result.submission_id,
        'document_file_id': result.document_file_id,
        'project_requirement_id': result.project_requirement_id,
        'score': float(result.score) if result.score is not None else None,
        'status': result.status,
        'recommended_action': result.recommended_action,
        'reference_basis': reference_basis,
        'findings': findings,
        'annotations': document_annotation_service.build_annotations(findings),
        'score_details': score_details,
        'reviewer_decision': reviewer_decision,
        'finding_reviews': (score_details or {}).get('finding_reviews') or {},
        'reviewer_decision_policy': reviewer_decision_policy,
        'extracted_fields': extracted_fields,
        'technical_checks': technical_checks,
        'technical_summary': technical_summary,
        'document_state': document_state,
        'evidence_checks': evidence_checks,
        'supporting_evidence_summary': (score_details or {}).get('supporting_evidence_summary') or {},
        'evidence_summary': evidence_summary,
        'checker_configuration': checker_configuration,
        'requirement_checks_configured': configured,
        'analysis_coverage': analysis_coverage,
        'findings_summary': findings_summary,
        'explanation': (score_details or {}).get('explanation') or (result.extracted_fields or {}).get('explanation'),
        'review_state': 'awaiting_human_evaluation',
        'suggested_return_notes': result.suggested_return_notes,
        'checker_version': result.checker_version,
        'created_by': result.created_by,
        'created_at': result.created_at.isoformat() if result.created_at else None,
    }


def _dedupe_findings_for_display(findings):
    deduped = rule_engine.deduplicate_findings(findings or [])
    return [map_finding_to_deficiency(f) for f in deduped]


def serialize_reference_profile(profile, *, reference=None):
    if profile is None:
        return None
    return {
        'id': profile.id,
        'configured': True,
        'reference_uri': profile.reference_uri,
        'reference_origin': profile.reference_origin,
        'reference_type': profile.reference_type,
        'reference_title': reference.get('title') if isinstance(reference, dict) else None,
        'checker_reference_type': profile.checker_reference_type,
        'program_id': profile.program_id,
        'program_cycle_id': profile.program_cycle_id,
        'requirement_id': profile.requirement_id,
        'requirement_name': profile.requirement_name,
        'requirement_type': profile.requirement_type,
        'phase_name': profile.phase_name,
        'fiscal_year': profile.fiscal_year,
        'project_kind': profile.project_kind,
        'status': profile.status,
        'effective_from': profile.effective_from.isoformat() if profile.effective_from else None,
        'effective_to': profile.effective_to.isoformat() if profile.effective_to else None,
        'profile_metadata': profile.profile_metadata or {},
        'created_by': profile.created_by,
        'created_at': profile.created_at.isoformat() if profile.created_at else None,
        'updated_at': profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _submission_with_access(submission_id, user_id):
    submission = db.session.get(Submission, submission_id)
    if not submission:
        raise DocumentComplianceError('Submission not found.', 404)
    try:
        access_service.ensure_project_requirement_access(submission.project_requirement_id, user_id)
    except access_service.AccessError as exc:
        raise DocumentComplianceError(exc.message, exc.status_code) from exc
    return submission


def _compliance_result_with_access(result_id, user_id):
    result = db.session.get(DocumentComplianceResult, result_id)
    if not result:
        raise DocumentComplianceError('Document compliance result not found.', 404)
    project_requirement_id = result.project_requirement_id
    if project_requirement_id is None and result.submission is not None:
        project_requirement_id = result.submission.project_requirement_id
    try:
        access_service.ensure_project_requirement_access(project_requirement_id, user_id)
    except access_service.AccessError as exc:
        raise DocumentComplianceError(exc.message, exc.status_code) from exc
    return result


def _with_reviewer_decision_policy(score_details):
    details = dict(score_details or {})
    details.setdefault('reviewer_decision_policy', {
        'checker_output_is_advisory': True,
        'human_final_authority': True,
        'allowed_decisions': sorted(REVIEWER_DECISIONS),
        'reason_codes': sorted(REVIEW_REASON_CODES),
        'requires_reason_for_override': True,
        'audit_action': 'review_document_compliance_result',
    })
    return details


def _validate_reviewer_decision(*, decision, reason_codes=None, review_notes=None):
    errors = {}
    normalized_decision = str(decision or '').strip()
    if normalized_decision not in REVIEWER_DECISIONS:
        errors['decision'] = 'Select a supported reviewer decision.'

    normalized_reason_codes = []
    if reason_codes is None:
        reason_codes = []
    if not isinstance(reason_codes, list):
        errors['reason_codes'] = 'Reason codes must be a list.'
    else:
        for code in reason_codes:
            normalized = str(code or '').strip()
            if not normalized:
                continue
            if normalized not in REVIEW_REASON_CODES:
                errors.setdefault('reason_codes', 'Reason codes include unsupported values.')
                continue
            if normalized not in normalized_reason_codes:
                normalized_reason_codes.append(normalized)

    notes = str(review_notes or '').strip()
    if len(notes) > 2000:
        errors['review_notes'] = 'Review notes must be 2000 characters or fewer.'
    if (
        normalized_decision.startswith('override')
        and not normalized_reason_codes
        and not notes
        and 'reason_codes' not in errors
    ):
        errors['reason_codes'] = 'Override decisions require at least one reason code or review note.'

    if errors:
        raise DocumentComplianceError('Reviewer decision validation failed.', 422, errors)
    return {
        'decision': normalized_decision,
        'reason_codes': normalized_reason_codes,
        'review_notes': notes or None,
    }


def _primary_document_file(submission):
    return document_intelligence_service.resolve_submission_primary_document(submission)


def _latest_scan(submission):
    return (
        submission.nlp_results
        .order_by(NlpScanResult.scanned_at.desc(), NlpScanResult.id.desc())
        .first()
    )


def _extract_text(document_file):
    if document_file.stored_object is not None:
        with object_storage_service.temporary_file(document_file.stored_object) as temp_path:
            extraction = document_intelligence_service.extract_document_text(
                temp_path,
                mime_type=document_file.mime_type,
                file_name=document_file.file_name,
            )
            _attach_visual_context(extraction, document_file=document_file, file_path=temp_path)
            return extraction
    local_path = Path(document_file.file_path)
    extraction = document_intelligence_service.extract_document_text(
        local_path,
        mime_type=document_file.mime_type,
        file_name=document_file.file_name,
    )
    _attach_visual_context(extraction, document_file=document_file, file_path=local_path)
    return extraction


def _attach_visual_context(extraction, *, document_file, file_path):
    visual_summary = visual_service.analyze_visual_evidence(
        extraction,
        mime_type=document_file.mime_type,
        file_path=file_path,
    )
    if visual_summary is not None:
        extraction['visual_summary'] = visual_summary
    photo_metadata = visual_metadata_service.extract_photo_metadata(
        file_path,
        mime_type=document_file.mime_type,
        reverse_geocoder=_reverse_geocode_photo_position,
    )
    if photo_metadata is not None:
        extraction['photo_metadata'] = photo_metadata


def _reverse_geocode_photo_position(latitude, longitude):
    try:
        return aws_providers.reverse_geocode_position(
            current_app.config,
            latitude=latitude,
            longitude=longitude,
        )
    except ProviderError as exc:
        return {'provider': 'aws-location', 'error': str(exc)[:200]}


def _select_reference_profiles(requirement, *, use_prior_year_reference):
    project = requirement.project
    inferred_evidence_type = rule_engine.infer_evidence_type_from_requirement(
        requirement_name=requirement.requirement_name,
        requirement_type=requirement.requirement_type,
        annex_reference=requirement.annex_reference,
        custom_fields=getattr(requirement, 'custom_fields', None),
    )
    active_profiles = (
        DocumentReferenceProfile.query
        .filter(DocumentReferenceProfile.status == 'active')
        .filter(or_(
            DocumentReferenceProfile.program_id.is_(None),
            DocumentReferenceProfile.program_id == project.program_id,
        ))
        .filter(or_(
            DocumentReferenceProfile.program_cycle_id.is_(None),
            DocumentReferenceProfile.program_cycle_id == project.program_cycle_id,
        ))
        .order_by(
            DocumentReferenceProfile.fiscal_year.desc().nullslast(),
            DocumentReferenceProfile.updated_at.desc(),
            DocumentReferenceProfile.id.desc(),
        )
        .all()
    )
    matched = [profile for profile in active_profiles if _profile_matches_requirement(profile, requirement)]
    current_profiles = [
        profile for profile in matched
        if profile.fiscal_year in (None, project.fiscal_year)
    ]
    prior_profiles = [
        profile for profile in matched
        if profile.fiscal_year is not None and profile.fiscal_year < project.fiscal_year
    ]
    prior_profiles.sort(
        key=lambda item: (item.fiscal_year or 0, _datetime_sort_value(item.updated_at)),
        reverse=True,
    )

    used_profiles = current_profiles
    reference_status = 'current' if used_profiles else 'none'
    if not used_profiles and use_prior_year_reference and prior_profiles:
        latest_prior_year = prior_profiles[0].fiscal_year
        used_profiles = [profile for profile in prior_profiles if profile.fiscal_year == latest_prior_year]
        reference_status = 'prior_year'
    elif not used_profiles and prior_profiles:
        reference_status = 'prior_year_available'

    return {
        'checker_version': CHECKER_VERSION,
        'reference_status': reference_status,
        'use_prior_year_reference': bool(use_prior_year_reference),
        'inferred_evidence_type': inferred_evidence_type,
        'inferred_evidence_type_source': _evidence_type_inference_source(requirement, inferred_evidence_type),
        'current_profiles': [_profile_basis(item) for item in current_profiles],
        'used_profiles': [_profile_basis(item) for item in used_profiles],
        'prior_profiles_available': [_profile_basis(item) for item in prior_profiles[:5]],
    }


def _profile_matches_requirement(profile, requirement):
    project = requirement.project
    if profile.requirement_id and profile.requirement_id != requirement.requirement_id:
        return False
    if profile.requirement_name and not _text_equal(profile.requirement_name, requirement.requirement_name):
        return False
    if profile.requirement_type and profile.requirement_type != requirement.requirement_type:
        return False
    if profile.phase_name and not _text_equal(profile.phase_name, requirement.phase_name):
        return False
    if profile.project_kind and profile.project_kind != project.project_kind:
        return False
    return True


def _profile_basis(profile):
    return {
        'id': profile.id,
        'reference_uri': profile.reference_uri,
        'reference_origin': profile.reference_origin,
        'reference_type': profile.reference_type,
        'checker_reference_type': profile.checker_reference_type,
        'program_id': profile.program_id,
        'program_cycle_id': profile.program_cycle_id,
        'requirement_id': profile.requirement_id,
        'requirement_name': profile.requirement_name,
        'requirement_type': profile.requirement_type,
        'phase_name': profile.phase_name,
        'fiscal_year': profile.fiscal_year,
        'project_kind': profile.project_kind,
        'profile_metadata': profile.profile_metadata or {},
    }


def _evidence_type_inference_source(requirement, inferred_evidence_type):
    if not inferred_evidence_type:
        return None
    return {
        'basis': 'requirement_metadata',
        'requirement_name': requirement.requirement_name,
        'requirement_type': requirement.requirement_type,
        'annex_reference': requirement.annex_reference,
    }


def _datetime_sort_value(value):
    if not value:
        return 0
    try:
        return value.timestamp()
    except (AttributeError, OSError, OverflowError, ValueError):
        return 0


def _is_context_field_required(checker_config, field_name):
    if not checker_config or not isinstance(checker_config, dict):
        return False
    expected_list = (
        checker_config.get('expected_context_fields')
        or checker_config.get('expected_fields')
        or checker_config.get('required_context_fields')
        or []
    )
    if isinstance(expected_list, (list, tuple, set)):
        if field_name in expected_list:
            return True
        aliases = {
            'lgu_name': ['lgu', 'lgu_name', 'municipality'],
            'project_title': ['project', 'project_title', 'project_name'],
            'fiscal_year': ['year', 'fiscal_year', 'fy'],
            'requirement_label': ['requirement', 'requirement_name', 'requirement_label'],
        }
        for alias in aliases.get(field_name, []):
            if alias in expected_list:
                return True

    if checker_config.get(f'requires_{field_name}') or checker_config.get(f'check_{field_name}'):
        return True
    if field_name == 'lgu_name' and (checker_config.get('requires_lgu') or checker_config.get('check_lgu')):
        return True
    if field_name == 'project_title' and (checker_config.get('requires_project') or checker_config.get('check_project')):
        return True
    if field_name == 'fiscal_year' and (checker_config.get('requires_year') or checker_config.get('check_year')):
        return True
    if field_name == 'requirement_label' and (checker_config.get('requires_requirement') or checker_config.get('check_requirement')):
        return True

    return False


def _build_findings(
    *,
    submission,
    document_file,
    extraction,
    latest_scan,
    profile_selection=None,
    use_prior_year_reference=False,
    field_evidence=None,
    evidence=None,
    technical_eval=None,
    checker_config=None,
    evidence_type=None,
):
    requirement = submission.project_requirement
    project = requirement.project
    lgu = project.lgu if project else None
    corpus = _normalize_corpus(extraction.get('text') or '')
    if evidence_type is None:
        evidence_type = (
            (checker_config or {}).get('evidence_type')
            or rule_engine.infer_evidence_type_from_requirement(
                requirement_name=requirement.requirement_name if requirement else None,
                requirement_type=requirement.requirement_type if requirement else None,
                annex_reference=requirement.annex_reference if requirement else None,
                custom_fields=getattr(requirement, 'custom_fields', None) if requirement else None,
            )
            or rule_engine.DEFAULT_EVIDENCE_TYPE
        )
    visual_evidence = rule_engine.is_visual_evidence_type(evidence_type)
    findings = []

    # Phase R7.1A: Technical Document Integrity findings (blank, visual-only, etc.)
    if technical_eval and technical_eval.get('findings'):
        findings.extend(technical_eval['findings'])

    visual_summary = extraction.get('visual_summary')
    if visual_summary:
        notes = '; '.join(visual_summary.get('notes') or []) or None
        stddev = visual_summary.get('contrast_stddev')
        metadata = extraction.get('metadata') or {}
        is_ocr = 'tesseract' in metadata.get('extractors', [])
        word_count = metadata.get('high_confidence_word_count')

        if stddev is not None and stddev < 4.0:
            findings.append(_finding(
                'visual_quality_blocker',
                'blocker',
                rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
                'Visual analysis flagged this image as blank, unreadable, or unusable.',
                notes,
                dimension='file_health',
                locations=_whole_document_locations(
                    extraction,
                    'The whole page/image needs reviewer attention because the visual quality check could not validate it.',
                ),
            ))
        elif (stddev is not None and stddev < 12.0) or (is_ocr and word_count == 0):
            findings.append(_finding(
                'visual_quality_unverified',
                'needs_verification',
                rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
                'Visual analysis flagged this image as potentially blank or having very low contrast.',
                notes,
                dimension='file_health',
                locations=_whole_document_locations(
                    extraction,
                    'The whole page/image needs reviewer attention because the visual quality check could not validate it.',
                ),
            ))
        elif visual_summary.get('image_quality') == 'unreadable' or visual_summary.get('blank_or_near_blank'):
            findings.append(_finding(
                'visual_quality_blocker',
                'blocker',
                rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
                'Visual analysis flagged this image as blank, unreadable, or unusable.',
                notes,
                dimension='file_health',
                locations=_whole_document_locations(
                    extraction,
                    'The whole page/image needs reviewer attention because the visual quality check could not validate it.',
                ),
            ))
        elif visual_summary.get('image_quality') == 'low_quality':
            findings.append(_finding(
                'visual_quality_warning',
                'warning',
                rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
                'Visual analysis flagged this image as low quality (blur, darkness, or low resolution).',
                notes,
                dimension='file_health',
                locations=_whole_document_locations(
                    extraction,
                    'The whole page/image needs reviewer attention because blur, darkness, or low resolution may affect review.',
                ),
            ))

    readable_chars = len(extraction.get('text') or '')
    minimum_chars = (checker_config or {}).get('minimum_text_chars')
    if minimum_chars is None:
        minimum_chars = 0 if visual_evidence else 20
    is_blank = technical_eval.get('is_blank') if technical_eval else False
    is_visual_only = technical_eval.get('is_visual_only') if technical_eval else False

    if readable_chars < minimum_chars and not is_blank and not is_visual_only and not visual_evidence:
        is_ocr = rule_engine.is_ocr_fallback(extraction.get('metadata'))
        findings.append(_finding(
            'readable_text_too_short',
            'needs_verification' if is_ocr else 'blocker',
            rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
            'Extracted document text contains fewer readable characters than expected.' +
            (' (Unverified due to OCR scan quality)' if is_ocr else ''),
            f'Extracted {readable_chars} readable characters; expected at least {minimum_chars}.',
            finding_observation=f'Extracted {readable_chars} readable character(s); expected at least {minimum_chars}.' +
            (' Automated analysis could not reliably extract text due to OCR scan quality; visual review is required.' if is_ocr else ''),
            corrective_instruction='Inspect the document scan or provide a clearer digital document if text is unreadable.',
            automation_level='human_verification' if is_ocr else 'automated_with_review',
            confidence='medium' if is_ocr else 'high',
            evidence_text=f'{readable_chars} characters extracted (minimum required: {minimum_chars})',
            locations=_whole_document_locations(
                extraction,
                'No precise text location is available; highlight the rendered page so reviewers can inspect the scanned or photographed document.',
            ),
        ))

    # Phase 2: Intake mapping checks (mapping_scan_missing, mapping_mismatch,
    # low_mapping_confidence) are intake-routing / triage concerns handled
    # by IntakeTriagePage and ScanMappingCard; they are decoupled from document findings.

    field_matches = (field_evidence or {}).get('matches') or {}
    if _is_context_field_required(checker_config, 'lgu_name') and not _field_is_matched(field_matches, 'lgu'):
        _expect_term(
            findings,
            corpus,
            evidence_type,
            'lgu_name',
            'LGU name was not found in the readable document text.',
            [getattr(lgu, 'name', None), getattr(lgu, 'municipality', None), getattr(lgu, 'province', None)],
        )
    if _is_context_field_required(checker_config, 'project_title') and not _field_is_matched(field_matches, 'project_title'):
        _expect_term(
            findings,
            corpus,
            evidence_type,
            'project_title',
            'Project title was not found in the readable document text.',
            [project.project_name if project else None, project.source_project_code if project else None],
        )
    if _is_context_field_required(checker_config, 'fiscal_year') and not _field_is_matched(field_matches, 'fiscal_year'):
        _expect_term(
            findings,
            corpus,
            evidence_type,
            'fiscal_year',
            'Fiscal year was not found in the readable document text.',
            [str(project.fiscal_year) if project else None, f'FY {project.fiscal_year}' if project else None],
        )
    if _is_context_field_required(checker_config, 'requirement_label'):
        _expect_term(
            findings,
            corpus,
            evidence_type,
            'requirement_label',
            'Requirement name or type was not found in the readable document text.',
            [requirement.requirement_name, requirement.requirement_type, requirement.annex_reference],
        )

    # Phase R7.1B: Legacy reference template and format-profile findings are retired
    # from active submitted-document compliance evaluation. Documentary compliance is
    # authoritative in Phase R6-R7.1A Requirement Evidence Checker & Technical Checker.

    if not is_blank:
        # Phase 2: Package completeness checks are package-level intake concerns,
        # isolated from single-document review findings.
        findings.extend(_check_cross_document_consistency(requirement, submission, project, corpus, field_evidence))
        findings.extend(_check_financial_reconciliation(corpus, extraction, field_evidence))


    readability_confidence = _readability_confidence(extraction, latest_scan)
    is_blank = technical_eval.get('is_blank') if technical_eval else False
    is_visual_only = technical_eval.get('is_visual_only') if technical_eval else False
    extracted_text_len = len(extraction.get('text') or '')

    if is_blank or is_visual_only or extracted_text_len < 40:
        language_quality = {
            'provider': 'languagetool',
            'status': 'skipped',
            'reason': 'insufficient_readable_text',
            'issues': [],
        }
    else:
        language_quality = language_quality_service.analyze_language_quality(
            extraction.get('text') or '',
            evidence_type=evidence_type,
            readability_confidence=readability_confidence,
        )
        language_quality = language_quality_service.merge_provider_result(
            language_quality,
            language_tool_provider.check_text(
                extraction.get('text') or '',
                config=_language_tool_config(submission),
                readability_confidence=readability_confidence,
            ),
            readability_confidence=readability_confidence,
        )
    if language_quality is not None:
        # Pass through to the extracted_fields summary builder for storage.
        extraction['language_quality'] = language_quality
        if _language_quality_has_reviewable_issue(language_quality):
            language_finding = _finding(
                'language_quality_review',
                'warning',
                rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
                _language_quality_finding_message(language_quality),
                _language_quality_finding_detail(language_quality),
                locations=_language_issue_locations(extraction, language_quality),
            )
            language_finding['annotation_more_count'] = max(0, _language_annotation_count(language_quality) - 20)
            findings.append(language_finding)

    # Phase 3.19: Officeholder reviewer context evaluation (Advisory context only, no signature validation)
    grounding_ctx = grounding_service.resolve_submission_grounding(submission)
    officeholder_findings = grounding_service.resolve_officeholder_reviewer_context(
        extraction.get('text') or '',
        grounding_ctx,
    )
    for off_finding in officeholder_findings:
        findings.append(_finding(
            off_finding['finding_id'],
            off_finding['severity'],
            off_finding['category'],
            off_finding['message'],
            off_finding['detail'],
            rule=off_finding['rule'],
            provenance=off_finding['provenance'],
        ))

    if not findings and not visual_evidence:
        findings.append(_finding(
            'basic_checks_passed',
            'info',
            rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
            'No automated issues were flagged for this document.',
            'Reviewer should inspect the attachment before making a compliance decision.',
        ))
    return rule_engine.deduplicate_findings(findings)



CONTEXT_DEPENDENT_ACRONYMS = frozenset({
    'pow', 'sord', 'ded', 'mov', 'mpr', 'cofa', 'swa', 'fir', 'bac', 'abc', 'ada', 'twg', 'sb', 'coa', 'dof', 'btr', 'gaa',
})

FORBIDDEN_GLOBAL_IGNORE_TERMS = frozenset({
    'fy', 'conforme', 'witnesseth',
})


def _language_tool_config(submission=None):
    config = dict(current_app.config) if has_app_context() else {}
    grounding_ctx = grounding_service.resolve_submission_grounding(submission)
    extra_terms = set(grounding_ctx.grounded_terms_set)

    # Clean configured ignore terms from app config / environment:
    # Context-dependent short acronyms must NOT be applied globally from config/env;
    # they may only be active if grounded for this specific submission.
    # Forbidden global terms (e.g. 'fy') must NEVER be ignored globally.
    configured_raw = str(config.get('DOCUMENT_LANGUAGE_TOOL_IGNORE_TERMS') or '').strip()
    clean_configured = []
    if configured_raw:
        for item in configured_raw.split(','):
            norm_item = grounding_service.normalize_term(item)
            if not norm_item:
                continue
            if norm_item in FORBIDDEN_GLOBAL_IGNORE_TERMS:
                continue
            if norm_item in CONTEXT_DEPENDENT_ACRONYMS and norm_item not in extra_terms:
                continue
            clean_configured.append(norm_item)

    all_terms = (set(clean_configured) | extra_terms) - FORBIDDEN_GLOBAL_IGNORE_TERMS
    if all_terms:
        config['DOCUMENT_LANGUAGE_TOOL_IGNORE_TERMS'] = ','.join(sorted(all_terms))
    elif 'DOCUMENT_LANGUAGE_TOOL_IGNORE_TERMS' in config:
        config['DOCUMENT_LANGUAGE_TOOL_IGNORE_TERMS'] = ''
    config['GROUNDING_TERMS_MAP'] = grounding_ctx.grounding_map
    config['GROUNDING_PHRASE_ENTITIES'] = grounding_ctx.phrase_entities
    return config


def _language_tool_domain_ignore_terms(submission=None):
    grounding_ctx = grounding_service.resolve_submission_grounding(submission)
    return set(grounding_ctx.grounded_terms_set)


def _language_tool_term_variants(value):
    return grounding_service.term_variants(value)


def _language_tool_normalize_term(value):
    return grounding_service.normalize_term(value)


def _language_quality_finding_message(language_quality):
    if _language_tool_provider_issues(language_quality):
        return 'LanguageTool found grammar, spelling, or style issues that should be reviewed.'
    return 'Language, grammar, or spelling review found issues that should be reviewed.'


def _language_quality_finding_detail(language_quality):
    parts = []
    provider_issues = _language_tool_provider_issues(language_quality)
    if provider_issues:
        count = _language_annotation_count(language_quality)
        noun = 'issue' if count == 1 else 'issues'
        issue_details = [
            detail
            for detail in (
                _language_quality_issue_detail(issue)
                for issue in provider_issues[:5]
            )
            if detail
        ]
        if issue_details:
            suffix = f'; + {count - 5} more' if count > 5 else ''
            parts.append(
                f'LanguageTool found {count} {noun}: '
                f'{"; ".join(issue_details)}{suffix}.'
            )
        else:
            parts.append(f'LanguageTool found {count} {noun}.')

    notes = _language_quality_review_notes(language_quality)
    if notes:
        note_suffix = f'; + {len(notes) - 4} more' if len(notes) > 4 else ''
        prefix = 'Local checks also noted: ' if parts else ''
        parts.append(f'{prefix}{"; ".join(notes[:4])}{note_suffix}.')

    return ' '.join(parts) or 'Review the extracted document text for language quality issues.'


def _language_tool_provider_issues(language_quality):
    quality = language_quality or {}
    return [
        issue for issue in quality.get('annotation_issues', quality.get('issues')) or []
        if isinstance(issue, dict)
        and str(issue.get('source') or '').strip().lower() == 'languagetool'
    ]


def _language_annotation_count(language_quality):
    quality = language_quality or {}
    available = len(_language_tool_provider_issues(quality) or quality.get('issues') or [])
    return max(available, _safe_int(quality.get('annotation_issue_count')) or 0)


def _language_quality_review_notes(language_quality):
    notes = []
    for note in (language_quality or {}).get('notes') or []:
        text = _compact_language_text(note, max_chars=180)
        if not text:
            continue
        if re.match(r'^languagetool found \d+ issues?\.?$', text, flags=re.IGNORECASE):
            continue
        if text not in notes:
            notes.append(text)
    return notes


def _language_quality_issue_detail(issue):
    issue_type = str(issue.get('type') or 'language').strip().lower() or 'language'
    matched_text = _compact_language_text(issue.get('matched_text'), max_chars=80)
    suggestion = _compact_language_text(issue.get('suggestion'), max_chars=80)
    message = _compact_language_text(issue.get('message'), max_chars=120)

    if matched_text and suggestion:
        detail = f'{issue_type} "{matched_text}" -> "{suggestion}"'
    elif matched_text:
        detail = f'{issue_type} "{matched_text}"'
    elif message:
        detail = f'{issue_type} issue'
    else:
        return ''

    if message:
        detail = f'{detail} ({message})'
    return detail


def _compact_language_text(value, *, max_chars):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if len(text) <= max_chars:
        return text
    return text[:max(0, max_chars - 3)].rstrip() + '...'


def _suggest_return_notes(findings, profile_selection=None):
    actionable = [
        item for item in findings
        if item.get('severity') in {'blocker', 'warning'}
        and not _is_language_advisory(item)
    ]
    if not actionable:
        return None
    lines = ['Review the following observations and correct confirmed issues before resubmitting:']
    for item in actionable[:6]:
        detail = item.get('corrective_instruction') or item.get('reviewer_action') or item.get('detail')
        if detail:
            lines.append(f'- {item.get("message")} {detail}')
        else:
            lines.append(f'- {item.get("message")}')
    return '\n'.join(lines)


def _is_language_advisory(item):
    return rule_engine.is_advisory_finding(item)


def _extracted_field_summary(*, submission, document_file, extraction, latest_scan, field_evidence=None):
    requirement = submission.project_requirement
    project = requirement.project if requirement else None
    lgu = project.lgu if project else None
    corpus = _normalize_corpus(' '.join([
        document_file.file_name or '',
        extraction.get('text') or '',
    ]))
    summary = {
        'file_name': document_file.file_name,
        'mime_type': document_file.mime_type,
        'readable_text_chars': len(extraction.get('text') or ''),
        'extraction_metadata': extraction.get('metadata') or {},
        'expected': {
            'project_requirement_id': submission.project_requirement_id,
            'requirement_id': requirement.requirement_id if requirement else None,
            'requirement_name': requirement.requirement_name if requirement else None,
            'annex_reference': requirement.annex_reference if requirement else None,
            'project_id': project.id if project else None,
            'project_name': project.project_name if project else None,
            'source_project_code': project.source_project_code if project else None,
            'fiscal_year': project.fiscal_year if project else None,
            'lgu_name': lgu.name if lgu else None,
        },
        'presence': {
            'lgu': _any_term_present(corpus, [getattr(lgu, 'name', None), getattr(lgu, 'municipality', None), getattr(lgu, 'province', None)]),
            'project': _any_term_present(corpus, [project.project_name if project else None, project.source_project_code if project else None]),
            'fiscal_year': _any_term_present(corpus, [str(project.fiscal_year) if project else None, f'FY {project.fiscal_year}' if project else None]),
            'requirement': _any_term_present(corpus, [requirement.requirement_name if requirement else None, requirement.annex_reference if requirement else None]),
        },
        'latest_scan_id': latest_scan.id if latest_scan else None,
        'latest_scan_suggested_project_requirement_id': latest_scan.suggested_project_requirement_id if latest_scan else None,
    }
    language_quality = extraction.get('language_quality')
    if language_quality:
        summary['language_quality'] = language_quality
    visual_summary = extraction.get('visual_summary')
    if visual_summary:
        summary['visual_summary'] = visual_summary
    photo_metadata = extraction.get('photo_metadata')
    if photo_metadata:
        summary['photo_metadata'] = photo_metadata
    photo_evidence_checks = extraction.get('photo_evidence_checks')
    if photo_evidence_checks:
        summary['photo_evidence_checks'] = photo_evidence_checks
    visual_evidence_summary = extraction.get('visual_evidence_summary')
    if visual_evidence_summary:
        summary['visual_evidence_summary'] = visual_evidence_summary
    if field_evidence:
        summary['field_evidence'] = field_evidence
    grounding_ctx = grounding_service.resolve_submission_grounding(submission)
    summary['grounding_summary'] = grounding_ctx.summary_dict()
    return summary


def _expected_field_context(submission):
    requirement = submission.project_requirement if submission else None
    project = requirement.project if requirement else None
    lgu = project.lgu if project else None
    project_custom = project.custom_fields if project and isinstance(project.custom_fields, dict) else {}
    requirement_custom = requirement.custom_fields if requirement and isinstance(requirement.custom_fields, dict) else {}
    return {
        'project_requirement_id': submission.project_requirement_id if submission else None,
        'requirement_name': requirement.requirement_name if requirement else None,
        'annex_reference': requirement.annex_reference if requirement else None,
        'project_name': project.project_name if project else None,
        'source_project_code': project.source_project_code if project else None,
        'fiscal_year': project.fiscal_year if project else None,
        'budget_amount': project.budget_amount if project else None,
        'amount': project_custom.get('amount') or project_custom.get('allocation'),
        'reference_number': (
            requirement_custom.get('reference_number')
            or requirement_custom.get('ada_number')
            or project_custom.get('reference_number')
            or project_custom.get('ada_number')
            or project_custom.get('nca_number')
            or project_custom.get('nta_number')
        ),
        'lgu_name': lgu.name if lgu else None,
        'lgu_municipality': lgu.municipality if lgu else None,
        'lgu_province': lgu.province if lgu else None,
    }


def _build_visual_evidence_summary(*, extraction, provider_metadata, profile_selection=None, photo_evidence_checks=None, evidence_type=None):
    if evidence_type is None and profile_selection is not None:
        evidence_type = rule_engine.evidence_type_from_profile_selection(profile_selection)
    if not rule_engine.is_visual_evidence_type(evidence_type):
        return None

    visual_summary = extraction.get('visual_summary') or {}
    photo_metadata = extraction.get('photo_metadata') or {}
    image_quality = visual_summary.get('image_quality') or 'not assessed'
    notes = [str(item) for item in (visual_summary.get('notes') or []) if str(item).strip()]
    notes.extend(str(item) for item in (photo_metadata.get('notes') or []) if str(item).strip())
    labels = _rekognition_labels(provider_metadata)
    label_names = [item['name'] for item in labels[:6] if item.get('name')]
    metadata_sentences = _photo_metadata_sentences(photo_metadata)

    if label_names:
        label_text = ', '.join(label_names)
        description = (
            f'Photo evidence image quality is {image_quality}. '
            f'{" ".join(metadata_sentences)} '
            f'Advisory visual labels detected: {label_text}. '
            'Reviewer should still confirm visible activity, project relevance, location, timestamp, and signboard if required.'
        )
    else:
        description = (
            f'Photo evidence image quality is {image_quality}. '
            f'{" ".join(metadata_sentences)} '
            'No object or scene labels are available, so the reviewer should confirm visible activity, project relevance, location, timestamp, and signboard if required.'
        )
    description = re.sub(r'\s+', ' ', description).strip()

    summary = {
        'evidence_type': evidence_type,
        'description': description,
        'image_quality': image_quality,
        'notes': notes,
        'photo_metadata': photo_metadata or None,
        'labels': labels,
        'label_source': 'aws-rekognition' if labels else None,
        'advisory_only': True,
    }
    if photo_evidence_checks:
        summary['photo_evidence_checks'] = photo_evidence_checks
    return summary


def _photo_metadata_sentences(photo_metadata):
    if not isinstance(photo_metadata, dict) or not photo_metadata:
        return ['No embedded photo metadata was available.']
    sentences = []
    captured_at = photo_metadata.get('captured_at')
    if captured_at:
        sentences.append(f'Captured at {captured_at} from embedded metadata.')
    else:
        sentences.append('No embedded capture time was found.')

    gps = photo_metadata.get('gps') or {}
    if gps:
        latitude = gps.get('latitude')
        longitude = gps.get('longitude')
        coords = _format_coordinates(latitude, longitude)
        address = gps.get('resolved_address')
        if address:
            sentence = f'Embedded GPS resolves to {address}'
            if coords:
                sentence = f'{sentence} ({coords})'
            sentences.append(f'{sentence}.')
        elif coords:
            sentences.append(f'Embedded GPS coordinates are {coords}; no human-readable address is configured or available.')
    else:
        sentences.append('No embedded GPS coordinates were found.')

    camera = photo_metadata.get('camera') or {}
    device = ' '.join(str(camera.get(key) or '').strip() for key in ('make', 'model')).strip()
    if device:
        sentences.append(f'Camera/device metadata: {device}.')
    return sentences


def _format_coordinates(latitude, longitude):
    try:
        return f'{float(latitude):.5f}, {float(longitude):.5f}'
    except (TypeError, ValueError):
        return ''


def _rekognition_labels(provider_metadata):
    labels = []
    for item in provider_metadata or []:
        if item.get('name') != 'aws-rekognition':
            continue
        payload = item.get('payload') or {}
        for label in payload.get('labels') or []:
            name = str(label.get('name') or '').strip()
            if not name:
                continue
            labels.append({
                'name': name,
                'confidence': label.get('confidence'),
                'categories': label.get('categories') or [],
            })
    return labels


def _canonical_key(value):
    normalized = str(value or '').strip().lower()
    return re.sub(r'[^a-z0-9]+', '_', normalized).strip('_')


def _finding(
    finding_id,
    severity,
    category,
    message,
    detail=None,
    *,
    dimension=None,
    locations=None,
    deficiency_category=None,
    finding_observation=None,
    corrective_instruction=None,
    automation_level=None,
    rule=None,
    confidence='high',
    provenance=None,
    page=None,
    bbox=None,
    evidence_text=None,
    **kwargs,
):
    return rule_engine.finding(
        finding_id,
        severity,
        category,
        message,
        detail,
        dimension=dimension,
        locations=locations,
        deficiency_category=deficiency_category,
        finding_observation=finding_observation,
        corrective_instruction=corrective_instruction,
        automation_level=automation_level,
        rule=rule,
        confidence=confidence,
        provenance=provenance,
        page=page,
        bbox=bbox,
        evidence_text=evidence_text,
        **kwargs,
    )


def map_finding_to_deficiency(finding_item, requirement=None, project=None):
    """Bridge internal checker findings to the 9 COMET standardized deficiency categories."""
    if not isinstance(finding_item, dict):
        return finding_item

    item = dict(finding_item)
    fid = str(item.get('id') or '').lower()
    cat = str(item.get('category') or '').lower()
    msg = str(item.get('message') or '')
    detail = str(item.get('detail') or '')
    sev = str(item.get('severity') or 'info')

    existing_cat = item.get('deficiency_category')
    if existing_cat in DEFICIENCY_CATEGORIES and item.get('finding_observation') and item.get('corrective_instruction'):
        if not item.get('automation_level'):
            item['automation_level'] = (
                'human_verification'
                if sev in ('needs_verification', 'manual_verification_required') or existing_cat == 'missing_signature_notarization'
                else 'automated_with_review'
            )
        return item

    if (
        'statutory_clearance' in fid
        or 'clearance' in fid
        or 'ecc' in fid
        or 'cnc' in fid
        or 'water_permit' in fid
        or 'dpwh_clearance' in fid
    ):
        mapped_cat = 'missing_statutory_clearance'
        auto_level = 'automated_with_review'
        action = 'Obtain and attach the required statutory government clearance or environmental certificate.'
    elif (
        'signatory' in fid
        or 'signature' in fid
        or 'seal' in fid
        or 'stamp' in fid
        or 'notar' in fid
        or 'signed_by' in fid
        or 'certified_by' in fid
        or 'approved_by' in fid
        or 'prepared_by' in fid
        or 'signature' in msg.lower()
        or 'signatory' in msg.lower()
    ):
        mapped_cat = 'missing_signature_notarization'
        auto_level = 'human_verification'
        action = 'Reviewer must visually confirm presence of wet/digital signature and official seal, or request resubmission with required signatures.'
    elif (
        'costing_arithmetic_mismatch' in fid
        or 'dupa' in fid
        or 'cost_item' in fid
        or 'unit_cost' in fid
    ):
        mapped_cat = 'costing_dupa_defect'
        auto_level = 'automated_with_review'
        action = 'Correct quantity, unit cost, or line item arithmetic calculations in the detailed cost breakdown / DUPA.'
    elif (
        'financial_reconciliation_mismatch' in fid
        or 'amount_mismatch' in fid
        or 'sum_mismatch' in fid
        or ('amount' in fid and 'mismatch' in fid)
    ):
        mapped_cat = 'financial_reconciliation_defect'
        auto_level = 'automated_with_review'
        action = 'Reconcile line item summation against grand totals and official project allocation amounts.'
    elif (
        'cross_doc_inconsistency' in fid
        or 'mapping_mismatch' in fid
        or 'low_mapping_confidence' in fid
        or (('mismatch' in fid or 'mismatch' in msg.lower()) and any(k in fid or k in msg.lower() for k in ('project', 'lgu', 'fiscal_year', 'context')))
    ):
        mapped_cat = 'cross_document_inconsistency'
        auto_level = 'automated_with_review'
        action = 'Reconcile contradictory information across project monitoring submissions to ensure full consistency.'
    elif (
        'visual_quality' in fid
        or 'readable_text_too_short' in fid
        or 'file_extension_not_allowed' in fid
        or 'blur' in msg.lower()
        or 'unreadable' in msg.lower()
        or 'scan' in fid
    ):
        mapped_cat = 'scan_quality_defect'
        auto_level = 'automated_with_review' if 'file_extension' in fid else 'human_verification'
        action = 'Provide a high-resolution, clear, and fully legible scan or original digital document.'
    elif (
        'package_missing_attachment' in fid
        or 'missing_attachment' in fid
        or 'attachment_missing' in fid
        or 'missing_supporting_document' in fid
    ):
        mapped_cat = 'missing_attachment'
        auto_level = 'automated_with_review'
        action = 'Attach the complete missing document or required supporting component to the submission package before resubmitting.'
    elif (
        'program_non_conformity' in fid
        or 'disallowed_term_found' in fid
        or 'required_term_missing' in fid
        or 'required_section_missing' in fid
        or 'format_profile_missing_column' in fid
        or 'obsolete_template' in fid
    ):
        mapped_cat = 'program_specific_non_conformity'
        auto_level = 'automated_with_review'
        action = 'Update the document to adhere strictly to the prescribed DILG / PDMU program template guidelines.'
    else:
        mapped_cat = 'other_documented_defect'
        auto_level = 'human_verification' if sev in ('needs_verification', 'manual_verification_required') else 'automated_with_review'
        action = 'Review the noted observation and provide corrected documentary evidence.'

    item['deficiency_category'] = existing_cat if existing_cat in DEFICIENCY_CATEGORIES else mapped_cat
    if not item.get('finding_observation'):
        item['finding_observation'] = f"{msg}{f' ({detail})' if detail and len(detail) < 160 else ''}"
    if not item.get('corrective_instruction'):
        item['corrective_instruction'] = action
    if not item.get('automation_level'):
        item['automation_level'] = auto_level

    return item


def _check_package_completeness(requirement, submission, corpus, profile_selection):
    findings = []
    evidence_type = rule_engine.evidence_type_from_profile_selection(profile_selection)

    package_components = []
    req_name = str(getattr(requirement, 'requirement_name', '') or '').lower()
    req_type = str(getattr(requirement, 'requirement_type', '') or '').lower()

    if evidence_type == 'billing_package' or 'billing' in req_type or 'billing' in req_name:
        package_components = [
            ('disbursement_voucher', 'Disbursement Voucher', ['voucher', 'disbursement voucher', 'dv no', 'dv #']),
            ('progress_billing', 'Progress Billing Statement', ['progress billing', 'billing statement', 'statement of account', 'billing no']),
            ('official_receipt', 'Official Receipt / Collection Receipt', ['official receipt', 'or no', 'collection receipt', 'electronic receipt']),
            ('accomplishment_inspection_report', 'Inspection / Accomplishment Report', ['inspection report', 'accomplishment report', 'certificate of inspection', 'qaar']),
        ]
    elif evidence_type == 'program_of_works' or 'program of work' in req_name or 'pow' in req_name:
        package_components = [
            ('detailed_estimates', 'Detailed Unit Price Analysis / Estimates', ['dupa', 'detailed estimate', 'unit price analysis', 'breakdown of cost', 'bill of quantities', 'boq']),
            ('scope_or_plan', 'Approved Scope of Work / Plan', ['scope of work', 'plans and specifications', 'technical specification', 'approved plan']),
        ]

    for profile in (profile_selection.get('used_profiles') or []):
        meta = profile.get('profile_metadata') or {}
        custom_components = meta.get('mandatory_components') or meta.get('mandatory_attachments') or []
        for comp in custom_components:
            comp_name = str(comp).strip()
            comp_id = _canonical_key(comp_name)
            if not any(c[0] == comp_id for c in package_components):
                package_components.append((comp_id, comp_name, [comp_name.lower()]))

    sub_filenames = [
        str(getattr(df, 'file_name', '')).lower()
        for df in getattr(submission, 'document_files', [])
    ]
    all_evidence_text = f"{corpus} {' '.join(sub_filenames)}"

    for comp_id, comp_name, keywords in package_components:
        found = any(kw in all_evidence_text for kw in keywords)
        if not found:
            findings.append(_finding(
                f'package_missing_attachment:{comp_id}',
                'warning',
                'content',
                f'Mandatory package component missing: {comp_name}',
                f'The submitted package does not appear to contain the required component "{comp_name}".',
                dimension='required_content_fields',
                deficiency_category='missing_attachment',
                finding_observation=f'The submitted package is missing required attachment: {comp_name}.',
                corrective_instruction=f'Attach the complete {comp_name} to the submission package before resubmitting.',
                automation_level='automated_with_review',
            ))

    return findings


def _check_cross_document_consistency(requirement, submission, project, corpus, field_evidence):
    findings = []
    if not project:
        return findings

    current_accomplishment = None
    acc_matches = re.findall(r'(\d+(?:\.\d+)?)\s*%\s*(?:physical\s+)?accomplish', corpus, re.IGNORECASE)
    if not acc_matches:
        acc_matches = re.findall(r'accomplish(?:ment)?[:\s]+(\d+(?:\.\d+)?)\s*%', corpus, re.IGNORECASE)
    if acc_matches:
        try:
            current_accomplishment = float(acc_matches[0])
        except ValueError:
            current_accomplishment = None

    if current_accomplishment is not None:
        sister_reqs = ProjectRequirement.query.filter(
            ProjectRequirement.project_id == project.id,
            ProjectRequirement.id != requirement.id,
        ).all()
        for sister in sister_reqs:
            sister_sub = sister.submissions.order_by(Submission.id.desc()).first()
            if not sister_sub:
                continue
            sister_comp = sister_sub.compliance_results.order_by(DocumentComplianceResult.id.desc()).first()
            if not sister_comp:
                continue
            sister_text = (sister_comp.extracted_fields or {}).get('text') or ''
            if not sister_text and sister_sub.document_files:
                df = sister_sub.document_files[0]
                sister_text = df.file_name or ''
            s_matches = re.findall(r'(\d+(?:\.\d+)?)\s*%\s*(?:physical\s+)?accomplish', sister_text, re.IGNORECASE)
            if not s_matches:
                s_matches = re.findall(r'accomplish(?:ment)?[:\s]+(\d+(?:\.\d+)?)\s*%', sister_text, re.IGNORECASE)
            if s_matches:
                try:
                    sister_val = float(s_matches[0])
                    if abs(current_accomplishment - sister_val) > 5.0:
                        findings.append(_finding(
                            'cross_doc_inconsistency:physical_accomplishment',
                            'warning',
                            rule_engine.CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY,
                            f'Cross-document accomplishment percentage inconsistency: {current_accomplishment}% vs {sister_val}%. Values differ and require reviewer verification.',
                            f'Document states {current_accomplishment}% accomplishment, but sister requirement "{sister.requirement_name}" states {sister_val}%. Values differ and require reviewer verification.',
                            dimension='project_lgu_context',
                            deficiency_category='cross_document_inconsistency',
                            finding_observation=f'Reported physical accomplishment ({current_accomplishment}%) conflicts with sister requirement "{sister.requirement_name}" ({sister_val}%). Values differ and require reviewer verification.',
                            corrective_instruction='Reconcile physical accomplishment percentages across all submitted progress monitoring documents.',
                            automation_level='automated_with_review',
                        ))
                        break
                except ValueError:
                    pass

    project_budget = getattr(project, 'budget_amount', None) or getattr(project, 'project_cost', None)
    if project_budget and float(project_budget) > 0:
        extracted_amount_val = None
        fields = (field_evidence or {}).get('fields') or {}
        amt_candidate = (fields.get('amount') or {}).get('best') or {}
        raw_amt = amt_candidate.get('normalized_value') or amt_candidate.get('raw_value')
        if raw_amt:
            try:
                extracted_amount_val = float(re.sub(r'[^\d\.]', '', str(raw_amt)))
            except (ValueError, TypeError):
                extracted_amount_val = None

        if extracted_amount_val and extracted_amount_val > 0:
            cost = float(project_budget)
            if abs(extracted_amount_val - cost) / cost > 0.05 and 'total project cost' in corpus.lower():
                findings.append(_finding(
                    'cross_doc_inconsistency:project_cost',
                    'warning',
                    rule_engine.CATEGORY_INTERNAL_CROSS_DOCUMENT_CONSISTENCY,
                    f'Documented project cost (₱{extracted_amount_val:,.2f}) conflicts with official project cost (₱{cost:,.2f}). Values differ and require reviewer verification.',
                    f'Document states total project cost of ₱{extracted_amount_val:,.2f}, differing by more than 5% from approved allocation of ₱{cost:,.2f}. Values differ and require reviewer verification.',
                    dimension='project_lgu_context',
                    deficiency_category='cross_document_inconsistency',
                    finding_observation=f'Documented project cost (₱{extracted_amount_val:,.2f}) conflicts with official approved cost (₱{cost:,.2f}). Values differ and require reviewer verification.',
                    corrective_instruction='Verify and reconcile total project cost figures against approved project allocations.',
                    automation_level='automated_with_review',
                ))

    return findings


def _check_financial_reconciliation(corpus, extraction, field_evidence):
    text = (extraction or {}).get('text') or ''
    if not text:
        return []
    from app.services import document_compliance_arithmetic as arithmetic_service
    return arithmetic_service.evaluate_document_arithmetic(
        text,
        extraction=extraction,
        field_evidence=field_evidence,
    )




def _whole_document_locations(extraction, reason, *, max_pages=3):
    page_count = _extraction_page_count(extraction)
    return [
        {
            'page': page,
            'bbox_type': 'whole_page',
            'reason': reason,
        }
        for page in range(1, min(page_count, max_pages) + 1)
    ]


def _language_issue_locations(extraction, language_quality, *, max_locations=20):
    issues = _language_tool_provider_issues(language_quality) or (language_quality or {}).get('issues') or []
    anchors = language_geometry.issue_anchors(
        extraction.get('text') or '', issues,
        page_count=(extraction.get('metadata') or {}).get('page_count'),
        limit=min(max_locations, 20),
    )
    for anchor, issue in zip(anchors, issues):
        anchor['message'] = _language_issue_message(issue)
        anchor['reason'] = 'Language issue; only verified character geometry may be highlighted.'
    return anchors


def _metadata_text_locations(extraction):
    metadata = (extraction or {}).get('metadata') or {}
    locations = metadata.get('text_locations') or []
    if not isinstance(locations, list):
        return []
    cleaned = []
    for item in locations:
        if not isinstance(item, dict):
            continue
        page = _safe_int(item.get('page')) or 1
        text = str(item.get('text') or '').strip()
        bbox = item.get('bbox')
        if not text or not bbox:
            continue
        cleaned.append({
            **item,
            'page': page,
            'text': text,
            'normalized_text': _normalize_location_token(text),
        })
    return cleaned


def _find_text_issue_location(text_locations, matched_text):
    tokens = [
        _normalize_location_token(token)
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9'/-]*", matched_text)
    ]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None
    for index, location in enumerate(text_locations):
        if location.get('normalized_text') != tokens[0]:
            continue
        group = text_locations[index:index + len(tokens)]
        if len(group) != len(tokens):
            continue
        if any(item.get('page') != location.get('page') for item in group):
            continue
        if [item.get('normalized_text') for item in group] != tokens:
            continue
        bbox_group = _best_text_issue_segment(group)
        bbox = _union_normalized_bboxes(item.get('bbox') for item in bbox_group)
        if not bbox:
            continue
        return {
            'page': location.get('page') or 1,
            'bbox': bbox,
            'bbox_type': location.get('bbox_type') or 'detected_text',
        }
    return None


def _best_text_issue_segment(group):
    segments = []
    current = []
    for item in group:
        if current and _starts_new_text_line(current[-1], item):
            segments.append(current)
            current = [item]
        else:
            current.append(item)
    if current:
        segments.append(current)
    if not segments:
        return group
    return max(
        segments,
        key=lambda segment: (
            len(segment),
            _union_area(_union_normalized_bboxes(item.get('bbox') for item in segment)),
        ),
    )


def _starts_new_text_line(previous, current):
    previous_bbox = previous.get('bbox') if isinstance(previous, dict) else None
    current_bbox = current.get('bbox') if isinstance(current, dict) else None
    if not isinstance(previous_bbox, dict) or not isinstance(current_bbox, dict):
        return False
    try:
        previous_x = float(previous_bbox.get('x'))
        previous_y = float(previous_bbox.get('y'))
        previous_height = float(previous_bbox.get('height'))
        current_x = float(current_bbox.get('x'))
        current_y = float(current_bbox.get('y'))
        current_height = float(current_bbox.get('height'))
    except (TypeError, ValueError):
        return False
    line_height = max(previous_height, current_height, 0.001)
    return current_x < previous_x and abs(current_y - previous_y) >= line_height * 0.45


def _union_area(bbox):
    if not bbox:
        return 0.0
    return float(bbox.get('width') or 0) * float(bbox.get('height') or 0)


def _union_normalized_bboxes(bboxes):
    normalized = []
    for bbox in bboxes:
        if not isinstance(bbox, dict):
            return None
        try:
            x = float(bbox.get('x'))
            y = float(bbox.get('y'))
            width = float(bbox.get('width'))
            height = float(bbox.get('height'))
        except (TypeError, ValueError):
            return None
        normalized.append((x, y, x + width, y + height))
    if not normalized:
        return None
    left = min(item[0] for item in normalized)
    top = min(item[1] for item in normalized)
    right = max(item[2] for item in normalized)
    bottom = max(item[3] for item in normalized)
    return {
        'x': round(max(0.0, min(1.0, left)), 4),
        'y': round(max(0.0, min(1.0, top)), 4),
        'width': round(max(0.0, min(1.0, right) - max(0.0, min(1.0, left))), 4),
        'height': round(max(0.0, min(1.0, bottom) - max(0.0, min(1.0, top))), 4),
    }


def _language_issue_message(issue):
    issue_type = str(issue.get('type') or 'language').strip().lower()
    matched_text = str(issue.get('matched_text') or '').strip()
    suggestion = str(issue.get('suggestion') or '').strip()
    if issue_type == 'spelling' and matched_text and suggestion:
        return f'Spelling issue: {matched_text} -> {suggestion}.'
    if issue_type == 'grammar' and suggestion:
        return f'Grammar issue: {suggestion.rstrip(".")}.'
    return str(issue.get('message') or 'Language issue detected.').strip()


def _normalize_location_token(value):
    return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extraction_page_count(extraction):
    metadata = (extraction or {}).get('metadata') or {}
    for key in ('page_count', 'pages', 'pageCount'):
        try:
            value = int(metadata.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 1


def _readability_confidence(extraction, latest_scan):
    """Best-effort confidence (0.0–1.0) that the extracted text is reliable.

    Order of preference:
        1. Explicit ``readability_confidence`` published by the extractor.
        2. The latest NLP scan's confidence_score, when present.
        3. A heuristic fall-back: 0.85 for native PDF/DOCX text extraction,
           0.55 for OCR-only output, 1.0 for plain text.
    """
    metadata = (extraction or {}).get('metadata') or {}
    explicit = metadata.get('readability_confidence')
    try:
        if explicit is not None:
            return max(0.0, min(1.0, float(explicit)))
    except (TypeError, ValueError):
        pass

    if latest_scan is not None:
        confidence = getattr(latest_scan, 'confidence_score', None)
        try:
            if confidence is not None:
                return max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            pass

    extractors = metadata.get('extractors') or []
    if 'tesseract' in extractors and len(extractors) == 1:
        return 0.55
    if extractors:
        return 0.85
    return 1.0


def _collect_provider_outputs(*, document_file, extraction, profile_selection=None, evidence_type=None):
    """Return ``(provider_metadata, provider_findings)`` for AWS/advisory providers."""
    if evidence_type is None and profile_selection is not None:
        evidence_type = rule_engine.evidence_type_from_profile_selection(profile_selection)
    adapters = []
    file_name = (
        getattr(document_file, 'file_name', None)
        or extraction.get('file_name')
        or ((extraction.get('metadata') or {}).get('file_name'))
    )
    mime_type = (
        getattr(document_file, 'mime_type', None)
        or extraction.get('mime_type')
        or ((extraction.get('metadata') or {}).get('mime_type'))
    )
    file_path = getattr(document_file, 'file_path', None)
    if not (
        current_app.config.get('TESTING')
        and not current_app.config.get('DOCUMENT_AWS_ENABLED_FOR_TESTING')
    ):
        adapters.extend(aws_providers.configured_adapters(
            current_app.config,
            evidence_type=evidence_type,
            file_name=file_name,
            mime_type=mime_type,
            file_path=file_path,
            document_file=document_file,
        ))
    adapters.extend(
        provider_registry.get(name)
        for name in provider_registry.names()
        if provider_registry.get(name) is not None
    )
    if not adapters:
        return [], []

    def _run(file_path):
        results = []
        for adapter in adapters:
            try:
                invoked = _invoke_provider(adapter, file_path)
                if invoked is not None:
                    results.append(invoked)
            except ProviderError as exc:
                results.append(ProviderResult(
                    name=adapter.name,
                    version=getattr(adapter, 'version', '') or '',
                    region=getattr(adapter, 'region', None),
                    errors=[str(exc)[:300]],
                ))
        return results

    if document_file.stored_object is not None:
        with object_storage_service.temporary_file(document_file.stored_object) as temp_path:
            results = _run(temp_path)
    else:
        results = _run(Path(document_file.file_path))

    metadata = collect_provider_metadata(results)
    return metadata, _provider_findings(metadata, evidence_type=evidence_type)


def _invoke_provider(adapter, file_path):
    if adapter.name == 'aws-rekognition':
        return adapter.detect_objects(file_path)
    if adapter.name == 'aws-textract-analyze-expense':
        if not aws_providers.is_supported_textract_format(file_path=file_path):
            return None
        return adapter.analyze_expense(file_path)
    if adapter.name.startswith('aws-textract'):
        if not aws_providers.is_supported_textract_format(file_path=file_path):
            return None
        return adapter.analyze_document(file_path)
    return adapter.analyze_document(file_path)


def _provider_findings(provider_metadata, *, evidence_type=None):
    findings = []
    if rule_engine.is_visual_evidence_type(evidence_type):
        return findings
    for item in provider_metadata or []:
        name = item.get('name') or 'aws-provider'
        errors = item.get('errors') or []
        if errors:
            findings.append(_finding(
                f'aws_provider_failure:{name}',
                'warning',
                rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
                'AWS document analysis could not complete.',
                f'{name}: {"; ".join(str(error) for error in errors)}',
                dimension='readability_ocr',
            ))
            continue
        confidence = item.get('confidence')
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            continue
        if confidence_value < 65:
            findings.append(_finding(
                f'aws_provider_low_confidence:{name}',
                'warning',
                rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
                'AWS document analysis returned low-confidence signals.',
                f'{name} confidence is {round(confidence_value, 2)}%. Treat the provider output as advisory only.',
                dimension='readability_ocr',
            ))
    return findings


def _language_quality_has_reviewable_issue(language_quality):
    if not language_quality:
        return False
    issue_statuses = {'minor_issues', 'major_issues', 'needs_review'}
    return any(
        language_quality.get(key) in issue_statuses
        for key in ('grammar_status', 'spelling_status', 'clarity_status')
    )


def _expect_term(findings, corpus, evidence_type, finding_id, message, terms):
    if _any_term_present(corpus, terms):
        return
    severity = rule_engine.context_field_severity(evidence_type, finding_id)
    if severity is None:
        return
    detail = 'The file name may be correct, but the readable document content does not confirm this expected value.'
    if severity == 'info':
        detail = 'This evidence type does not always include this value; reviewer context may still confirm it.'
    findings.append(_finding(
        finding_id,
        severity,
        rule_engine.CATEGORY_REQUIRED_INFORMATION_KEYWORD_OCCURRENCE,
        message,
        detail,
    ))



def _field_is_matched(field_matches, field):
    return (field_matches.get(field) or {}).get('status') == 'matched'


def _any_term_present(corpus, terms):
    return any(_contains_term(corpus, term) for term in terms if term)


def _contains_term(corpus, term):
    normalized = _normalize_corpus(str(term or ''))
    if not normalized:
        return False
    if normalized in corpus:
        return True
    tokens = [token for token in normalized.split() if len(token) > 2]
    if len(tokens) <= 1:
        return False
    return all(token in corpus for token in tokens)


def _normalize_corpus(value):
    normalized = str(value or '').lower()
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


def _text_equal(left, right):
    return _normalize_corpus(left) == _normalize_corpus(right)


def _resolve_reference(reference_uri, *, user_id, user_role):
    try:
        return library_service.get_reference(reference_uri, user_id=user_id, user_role=user_role)
    except library_service.LibraryError as exc:
        raise DocumentComplianceError(exc.message, exc.status_code, exc.errors) from exc


def _with_auto_format_profile(reference, values, *, user_id, user_role):
    metadata = dict(values.get('profile_metadata') or {})
    if metadata.get('format_profile') or metadata.get('disable_auto_format_profile'):
        return metadata
    if values.get('checker_reference_type') not in {
        'official_template',
        'accepted_sample',
        'validation_checklist',
        'logo_letterhead_reference',
    }:
        return metadata

    try:
        download = library_service.get_reference_download(
            reference['reference_uri'],
            user_id=user_id,
            user_role=user_role,
        )
    except library_service.LibraryError as exc:
        metadata['format_profile_extraction'] = {
            'status': 'skipped',
            'reason': exc.message,
        }
        return metadata

    try:
        stored_object = download.get('stored_object')
        if stored_object is not None:
            with object_storage_service.temporary_file(stored_object) as temp_path:
                extracted = document_format_profile_service.extract_format_profile_from_file(
                    temp_path,
                    mime_type=download.get('mime_type'),
                    file_name=download.get('download_name'),
                    checker_reference_type=values.get('checker_reference_type'),
                )
        else:
            path = download.get('path')
            if not path:
                metadata['format_profile_extraction'] = {
                    'status': 'skipped',
                    'reason': 'Reference file is not available for local extraction.',
                }
                return metadata
            extracted = document_format_profile_service.extract_format_profile_from_file(
                path,
                mime_type=download.get('mime_type'),
                file_name=download.get('download_name'),
                checker_reference_type=values.get('checker_reference_type'),
            )
    except Exception as exc:
        metadata['format_profile_extraction'] = {
            'status': 'failed',
            'reason': str(exc)[:180],
        }
        return metadata

    metadata.update(extracted)
    return metadata


def _ensure_profile_write_role(user_role):
    if user_role not in {'admin', 'staff'}:
        raise DocumentComplianceError('Only internal reviewers can configure checker references.', 403)


def _validate_reference_profile_payload(data, reference):
    errors = {}
    checker_reference_type = str(data.get('checker_reference_type') or 'guideline_basis').strip()
    if checker_reference_type not in CHECKER_REFERENCE_TYPES:
        errors['checker_reference_type'] = 'Select a supported checker reference type.'

    status = str(data.get('status') or 'draft').strip()
    if status not in REFERENCE_PROFILE_STATUSES:
        errors['status'] = 'Select draft, active, superseded, or archived.'

    fiscal_year = _optional_int(data.get('fiscal_year'), 'fiscal_year', errors)
    if fiscal_year is not None and not 2000 <= fiscal_year <= 2100:
        errors['fiscal_year'] = 'Fiscal year must be between 2000 and 2100.'

    program_id = _optional_int(data.get('program_id'), 'program_id', errors)
    if program_id is None:
        program_id = reference.get('program_id')
    if program_id is not None and db.session.get(Program, program_id) is None:
        errors['program_id'] = 'Program not found.'

    program_cycle_id = _optional_int(data.get('program_cycle_id'), 'program_cycle_id', errors)
    if program_cycle_id is not None and db.session.get(ProgramCycle, program_cycle_id) is None:
        errors['program_cycle_id'] = 'Program cycle not found.'

    requirement_id = _optional_int(data.get('requirement_id'), 'requirement_id', errors)
    requirement = db.session.get(Requirement, requirement_id) if requirement_id else None
    if requirement_id is not None and requirement is None:
        errors['requirement_id'] = 'Requirement not found.'

    metadata = _coerce_metadata(data.get('profile_metadata'), errors)
    effective_from = _optional_date(data.get('effective_from'), 'effective_from', errors)
    effective_to = _optional_date(data.get('effective_to'), 'effective_to', errors)
    if effective_from and effective_to and effective_to < effective_from:
        errors['effective_to'] = 'End date cannot be earlier than start date.'

    if errors:
        raise DocumentComplianceError('Checker reference profile validation failed.', 422, errors)

    return {
        'reference_origin': reference.get('origin'),
        'reference_type': reference.get('reference_type'),
        'checker_reference_type': checker_reference_type,
        'program_id': program_id,
        'program_cycle_id': program_cycle_id,
        'requirement_id': requirement_id,
        'requirement_name': _clean_optional_text(data.get('requirement_name')) or (requirement.name if requirement else None),
        'requirement_type': _clean_optional_text(data.get('requirement_type')) or (requirement.requirement_type if requirement else None),
        'phase_name': _clean_optional_text(data.get('phase_name')) or (requirement.phase.name if requirement and requirement.phase else None),
        'fiscal_year': fiscal_year,
        'project_kind': _clean_optional_text(data.get('project_kind')),
        'status': status,
        'effective_from': effective_from,
        'effective_to': effective_to,
        'profile_metadata': metadata,
    }


def _optional_int(value, field, errors):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        errors[field] = 'Must be an integer.'
        return None


def _optional_date(value, field, errors):
    if value in (None, ''):
        return None
    if hasattr(value, 'isoformat') and not isinstance(value, str):
        return value
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        errors[field] = 'Use YYYY-MM-DD.'
        return None


def _coerce_metadata(value, errors):
    if value in (None, ''):
        return {}
    if isinstance(value, dict):
        metadata = value
    elif isinstance(value, str):
        try:
            metadata = json.loads(value)
        except json.JSONDecodeError:
            errors['profile_metadata'] = 'Must be a JSON object.'
            return {}
    else:
        errors['profile_metadata'] = 'Must be a JSON object.'
        return {}
    if not isinstance(metadata, dict):
        errors['profile_metadata'] = 'Must be a JSON object.'
        return {}
    cleaned, metadata_errors = rule_engine.validate_profile_metadata(metadata)
    errors.update(metadata_errors)
    return cleaned


def _clean_optional_text(value):
    cleaned = str(value or '').strip()
    return cleaned or None
