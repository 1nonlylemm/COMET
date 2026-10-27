"""Documentary Layout and Structural Format Integrity Checker for COMET.

Phase 3.1: Detects objective, machine-observable layout and formatting anomalies:
1. Mixed Page Orientations (e.g. Portrait vs Landscape)
2. Inconsistent Page Dimensions across multi-page sheets
3. Blank Page Interruption (intermediate empty page between content pages)
4. Empty or Fragmented Structural Sections (when configured in checker_config)

Adheres strictly to COMET Reviewer Assistant principles:
- Emits purely observational statements describing detectable geometry/text
- Never enforces subjective styling (no arbitrary margins, fonts, or colors)
- Never claims "incorrect template", "wrong format", or "document non-compliant"
- Unconfigured layout expectations produce no requirement-specific findings
- Categorizes findings under layout_structural_integrity
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services import document_compliance_rule_engine as rule_engine


def _safe_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def extract_pdf_page_stats(pdf_path_or_reader: Any) -> list[dict[str, Any]]:
    """Extracts per-page dimension, rotation, and content metrics from a PDF file or reader."""
    if not pdf_path_or_reader:
        return []

    reader = None
    if hasattr(pdf_path_or_reader, 'pages'):
        reader = pdf_path_or_reader
    else:
        try:
            from pypdf import PdfReader
            p = Path(pdf_path_or_reader)
            if p.exists():
                reader = PdfReader(str(p))
        except Exception:
            return []

    if not reader or not hasattr(reader, 'pages'):
        return []

    page_stats = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            raw_w = _safe_float(getattr(page.mediabox, 'width', None)) or 612.0
            raw_h = _safe_float(getattr(page.mediabox, 'height', None)) or 792.0
            rot = int(page.get('/Rotate', 0) or 0) % 360

            # Compute effective viewport width and height accounting for rotation
            if rot in (90, 270):
                eff_w, eff_h = raw_h, raw_w
            else:
                eff_w, eff_h = raw_w, raw_h

            orientation = 'landscape' if eff_w > eff_h else 'portrait'
            p_text = (page.extract_text() or '').strip()
            p_images = getattr(page, 'images', []) or []

            page_stats.append({
                'page_number': idx,
                'width': round(eff_w, 1),
                'height': round(eff_h, 1),
                'raw_width': round(raw_w, 1),
                'raw_height': round(raw_h, 1),
                'rotation': rot,
                'orientation': orientation,
                'char_count': len(p_text),
                'image_count': len(p_images),
            })
        except Exception:
            continue

    return page_stats


def evaluate_document_layout(
    pdf_path_or_reader: Any = None,
    text: str = '',
    *,
    checker_config: dict[str, Any] | None = None,
    page_stats: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Evaluates multi-page document layout and configured structural sections.

    Returns:
        List of canonical findings satisfying the Phase 3.0 contract.
    """
    findings: list[dict[str, Any]] = []
    config = checker_config or {}

    stats = page_stats
    if stats is None and pdf_path_or_reader is not None:
        stats = extract_pdf_page_stats(pdf_path_or_reader)

    # 1. Multi-Page Geometry Checks (only apply when multiple pages exist)
    if stats and len(stats) > 1:
        # A. Mixed Page Orientation Check
        findings.extend(_check_mixed_orientations(stats))

        # B. Inconsistent Page Dimensions Check
        findings.extend(_check_page_dimensions(stats))

        # C. Blank Page Interruption Check
        findings.extend(_check_blank_page_interruption(stats))

    # 2. Configured Structural Section Check (strictly requirement-driven)
    required_sections = list(config.get('required_sections') or [])
    if required_sections and text:
        findings.extend(_check_empty_structural_sections(text, required_sections))

    return findings


def _check_mixed_orientations(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detects unexpected mixed portrait and landscape page orientations."""
    findings = []
    portraits = [p['page_number'] for p in stats if p.get('orientation') == 'portrait']
    landscapes = [p['page_number'] for p in stats if p.get('orientation') == 'landscape']

    if portraits and landscapes:
        # Identify the minority orientation
        if len(landscapes) <= len(portraits):
            minority_pages = landscapes
            min_orient = 'landscape'
            maj_orient = 'portrait'
            maj_pages = portraits
        else:
            minority_pages = portraits
            min_orient = 'portrait'
            maj_orient = 'landscape'
            maj_pages = landscapes

        def _format_page_list(pages: list[int], cap: bool = False) -> str:
            if not pages:
                return ''
            sing_pref = 'Page' if cap else 'page'
            plur_pref = 'Pages' if cap else 'pages'
            if len(pages) == 1:
                return f'{sing_pref} {pages[0]}'
            if len(pages) == 2:
                return f'{plur_pref} {pages[0]} and {pages[1]}'
            return f'{plur_pref} {", ".join(str(p) for p in pages[:-1])}, and {pages[-1]}'

        min_str = _format_page_list(minority_pages, cap=True)
        maj_str = _format_page_list(maj_pages, cap=False)

        obs = (
            f'{min_str} uses {min_orient} orientation while {maj_str} use {maj_orient} orientation.'
        )
        action = (
            f'Reviewer should inspect {min_orient} page(s) ({", ".join(str(p) for p in minority_pages)}) '
            'to verify readable orientation and document presentation layout.'
        )

        findings.append(rule_engine.finding(
            f'mixed_page_orientation_p{minority_pages[0]}',
            'info',
            rule_engine.CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
            f'Document contains mixed page orientations ({min_orient} vs {maj_orient}).',
            obs,
            rule='mixed_page_orientation',
            deficiency_category='scan_quality_defect',
            finding_observation=obs,
            corrective_instruction=action,
            automation_level='automated_with_review',
            confidence='high',
            page=minority_pages[0],
            reviewer_action=action,
            provenance={'source': 'document_compliance_layout', 'check': 'mixed_orientations'},
        ))

    return findings


def _check_page_dimensions(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detects inconsistent page dimensions across multi-page sheets."""
    findings = []
    if len(stats) < 2:
        return findings

    base_p = stats[0]
    base_w, base_h = base_p.get('width', 612.0), base_p.get('height', 792.0)
    base_short = min(base_w, base_h)
    base_long = max(base_w, base_h)

    differing_pages = []
    for p in stats[1:]:
        pw, ph = p.get('width', 612.0), p.get('height', 792.0)
        p_short = min(pw, ph)
        p_long = max(pw, ph)

        # Flag if short or long dimension varies by more than 15% (ignoring orientation swaps)
        if abs(p_short - base_short) / max(base_short, 1.0) > 0.15 or abs(p_long - base_long) / max(base_long, 1.0) > 0.15:
            differing_pages.append(p)

    if differing_pages:
        first_diff = differing_pages[0]
        obs = (
            f'Document contains varying page dimensions (e.g., Page 1: {int(base_w)}×{int(base_h)} pt, '
            f'Page {first_diff["page_number"]}: {int(first_diff["width"])}×{int(first_diff["height"])} pt). '
            'Reviewer should inspect for mis-sized or spliced sheets.'
        )
        action = 'Verify that multi-page document dimensions are consistent and no sheet content was clipped.'

        findings.append(rule_engine.finding(
            f'inconsistent_page_dimensions_p{first_diff["page_number"]}',
            'info',
            rule_engine.CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
            'Document contains inconsistent page dimensions across sheets.',
            obs,
            rule='inconsistent_page_dimensions',
            deficiency_category='scan_quality_defect',
            finding_observation=obs,
            corrective_instruction=action,
            automation_level='automated_with_review',
            confidence='high',
            page=first_diff['page_number'],
            reviewer_action=action,
            provenance={'source': 'document_compliance_layout', 'check': 'inconsistent_dimensions'},
        ))

    return findings


def _check_blank_page_interruption(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detects an intermediate blank page between populated content pages."""
    findings = []
    if len(stats) < 3:
        return findings

    for idx in range(1, len(stats) - 1):
        curr = stats[idx]
        prev = stats[idx - 1]
        nxt = stats[idx + 1]

        curr_empty = (curr.get('char_count', 0) == 0 and curr.get('image_count', 0) == 0)
        prev_has_content = (prev.get('char_count', 0) > 0 or prev.get('image_count', 0) > 0)
        nxt_has_content = (nxt.get('char_count', 0) > 0 or nxt.get('image_count', 0) > 0)

        if curr_empty and prev_has_content and nxt_has_content:
            p_num = curr.get('page_number', idx + 1)
            prev_num = prev.get('page_number', idx)
            nxt_num = nxt.get('page_number', idx + 2)

            obs = (
                f'Page {p_num} appears blank with no detectable text or image content '
                f'between populated pages {prev_num} and {nxt_num}.'
            )
            action = (
                f'Reviewer must inspect page {p_num} to ensure no required document content '
                'was omitted or failed to scan.'
            )

            findings.append(rule_engine.finding(
                f'blank_page_interruption_p{p_num}',
                'warning',
                rule_engine.CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
                f'Blank page detected interrupting document content at page {p_num}.',
                obs,
                rule='blank_page_interruption',
                deficiency_category='missing_attachment',
                finding_observation=obs,
                corrective_instruction=action,
                automation_level='automated_with_review',
                confidence='high',
                page=p_num,
                reviewer_action=action,
                provenance={'source': 'document_compliance_layout', 'check': 'blank_page_interruption'},
            ))

    return findings


def _check_empty_structural_sections(text: str, required_sections: list[str]) -> list[dict[str, Any]]:
    """Checks whether a configured required section title exists without associated content."""
    findings = []
    if not text or not required_sections:
        return findings

    headings = []
    for section in dict.fromkeys(required_sections):
        name = str(section).strip()
        if not name:
            continue
        # A contents entry or a reference in prose is not the section itself.
        pattern = re.compile(rf'^[ \t]*(?:\d+(?:\.\d+)*[.)]?[ \t]+)?{re.escape(name)}(?=[ \t\r]*(?::|$))[^\S\n]*:?', re.I | re.M)
        for match in pattern.finditer(text):
            remainder = text[match.end():].split('\n', 1)[0]
            if re.match(r'\s*(?:\.{2,}|[. \t]+\d+\s*$)', remainder):
                continue
            headings.append((match.start(), match.end(), name, match))
    headings.sort(key=lambda entry: entry[0])

    for section in dict.fromkeys(required_sections):
        sec_name = str(section).strip()
        occurrences = [entry for entry in headings if entry[2] == sec_name]
        if not occurrences:
            continue
        empty_occurrences = []
        for start, end, _, match in occurrences:
            following = next((entry[0] for entry in headings if entry[0] >= end), len(text))
            section_content = text[end:following].strip()
            next_numbered = re.search(r'^\s*\d+(?:\.\d+)*[.)]\s+[A-Z][^\n|\t]{0,80}:\s*$', section_content, re.M)
            if next_numbered:
                section_content = section_content[:next_numbered.start()]
            # Count data, not column labels or arbitrary numbers of English words.
            meaningful = re.sub(r'\b(?:n/a|not applicable|to be (?:provided|completed)|pending|tbd)\b', '', section_content, flags=re.I)
            meaningful = re.sub(r'\b(?:item|description|quantity|qty|unit|price|cost|total|amount|signature|name|designation|date)\b', '', meaningful, flags=re.I)
            meaningful = re.sub(r'[_|.\-:;,/\[\]()]+', ' ', meaningful)
            has_data = bool(re.search(r'[^\W_]{2,}|\d|[✓✔☑]|\b[Xx]\b', meaningful, re.UNICODE))
            if not has_data:
                empty_occurrences.append(match)
        # A repeated header with populated content supersedes its empty occurrence.
        is_empty_or_fragmented = len(empty_occurrences) == len(occurrences)
        match = occurrences[0][3]

        if is_empty_or_fragmented:
            clean_sec = re.sub(r'[^a-z0-9_]+', '_', sec_name.lower()).strip('_')
            obs = (
                f'Configured \'{sec_name}\' section title was detected, '
                'but no associated content was detected before the next major section.'
            )
            action = (
                f'Reviewer should verify that the \'{sec_name}\' section contains all '
                'required narrative, tables, or attachments.'
            )

            findings.append(rule_engine.finding(
                f'empty_structural_section_{clean_sec}',
                'warning',
                rule_engine.CATEGORY_LAYOUT_STRUCTURAL_INTEGRITY,
                f'Configured \'{sec_name}\' section appears empty or fragmented.',
                obs,
                rule='empty_structural_section',
                deficiency_category='missing_attachment',
                finding_observation=obs,
                corrective_instruction=action,
                automation_level='automated_with_review',
                confidence='high',
                evidence_text=match.group(0),
                reviewer_action=action,
                provenance={'source': 'document_compliance_layout', 'check': 'empty_structural_section'},
            ))

    return findings
