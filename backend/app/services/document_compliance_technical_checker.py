"""Technical Document Integrity Checker for COMET.

Phase R7.1A: Evaluates document content presence, document readability,
and text extraction quality as technical/usability checks, distinct from
documentary compliance decisions.

Distinguishes three fundamental document-content states:
1. content_present_readable: Meaningful content and enough machine-readable
   text for evidence checking.
2. visual_content_only: Meaningful visual content (photos, scanned certs,
   image-based PDFs) with little or no machine-readable text. Technical status
   is needs_review (NOT blank).
3. blank_or_empty: Genuinely blank PDF, blank image, empty DOCX/XLSX,
   whitespace-only, or zero-byte file. Technical status is blocker. Downstream
   evidence checks are suppressed.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from app.services import document_compliance_visual as visual_service
from app.services import document_compliance_rule_engine as rule_engine



# Configurable Internal Thresholds (defensible and adjustable)
READABILITY_PAGE_RATIO_THRESHOLD = 0.60  # At least 60% of text pages must be readable
MIN_READABLE_PAGE_TEXT_CHARS = 50       # Minimum characters on a page to qualify as readable text
MIN_READABLE_DOCUMENT_CHARS = 40        # Minimum characters for single-page/plain text documents
BLANK_CONTRAST_STDDEV_THRESHOLD = 4.0   # Grayscale contrast stddev <= 4.0 is blank
IMAGE_ASPECT_RATIO_MIN = 0.1            # Avoid corrupted 0-dimension images

# The Three Document-Content States (R7.1A §2)
STATE_CONTENT_PRESENT_READABLE = 'content_present_readable'
STATE_VISUAL_CONTENT_ONLY = 'visual_content_only'
STATE_BLANK_OR_EMPTY = 'blank_or_empty'

VALID_DOCUMENT_STATES = {
    STATE_CONTENT_PRESENT_READABLE,
    STATE_VISUAL_CONTENT_ONLY,
    STATE_BLANK_OR_EMPTY,
}


def evaluate_technical_integrity(
    *,
    document_file: Any = None,
    extraction: dict[str, Any] | None = None,
    file_path: Path | str | None = None,
    requirement: Any = None,
    checker_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate document content presence, readability, text extraction, and layout.

    Returns:
        dict containing:
            - 'document_state': one of STATE_CONTENT_PRESENT_READABLE,
                                STATE_VISUAL_CONTENT_ONLY, STATE_BLANK_OR_EMPTY
            - 'technical_checks': list of 3 structured checks:
                1. document_content (Content Presence)
                2. document_readability (Readability)
                3. text_extraction (Text Extraction)
            - 'technical_summary': detailed metrics dict
            - 'is_blank': bool
            - 'is_visual_only': bool
            - 'findings': list of technical and layout findings (blocker if blank, etc.)
    """
    extraction = extraction or {}
    metadata = extraction.get('metadata') or {}
    text = str(extraction.get('text') or '').strip()
    file_name = getattr(document_file, 'file_name', '') or metadata.get('file_name', '')
    mime_type = getattr(document_file, 'mime_type', '') or metadata.get('mime_type', '')
    file_size = (
        getattr(document_file, 'file_size_bytes', None)
        if document_file and getattr(document_file, 'file_size_bytes', None) is not None
        else (Path(file_path).stat().st_size if file_path and Path(file_path).exists() else None)
    )

    path_obj = Path(file_path) if file_path and Path(file_path).exists() else None

    # Step 1: Analyze file format specifics
    analysis = _analyze_document(
        path=path_obj,
        file_name=file_name,
        mime_type=mime_type,
        file_size=file_size,
        text=text,
        extraction=extraction,
    )

    # Step 2: Determine document state
    document_state = analysis['document_state']
    is_blank = (document_state == STATE_BLANK_OR_EMPTY)
    is_visual_only = (document_state == STATE_VISUAL_CONTENT_ONLY)

    # Inject extracted char count into analysis so _build_technical_checks can use it
    analysis['extracted_char_count'] = len(text)

    # Step 3: Build the three standard technical checks
    checks = _build_technical_checks(document_state, analysis)

    # Step 4: Build findings (technical integrity + objective multi-page layout)
    findings = _build_technical_findings(document_state, analysis)

    if not is_blank:
        from app.services import document_compliance_layout as layout_service
        layout_findings = layout_service.evaluate_document_layout(
            pdf_path_or_reader=path_obj,
            text=text,
            checker_config=checker_config,
            page_stats=analysis.get('page_stats'),
        )
        findings.extend(layout_findings)

    summary = {
        'document_state': document_state,
        'is_blank': is_blank,
        'is_visual_only': is_visual_only,
        'total_pages': analysis.get('total_pages', 1),
        'text_pages': analysis.get('text_pages', 0),
        'photo_pages': analysis.get('photo_pages', 0),
        'readable_pages': analysis.get('readable_pages', 0),
        'blank_pages': analysis.get('blank_pages', 0),
        'readability_ratio': analysis.get('readability_ratio', 1.0),
        'extracted_char_count': len(text),
        'extractors_used': metadata.get('extractors', []),
        'details': analysis.get('details', ''),
    }

    return {
        'document_state': document_state,
        'technical_checks': checks,
        'technical_summary': summary,
        'is_blank': is_blank,
        'is_visual_only': is_visual_only,
        'findings': findings,
    }


def _extract_meaningful_words(text: str) -> list[str]:
    """Extracts words of 3+ alphabetical characters from text.

    Distinguishes meaningful text from pure symbol, whitespace, or digit noise.
    """
    return re.findall(r'[A-Za-z]{3,}', text)


def _analyze_document(
    *,
    path: Path | None,
    file_name: str,
    mime_type: str,
    file_size: int | None,
    text: str,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Inspects available signals to determine document structure and state."""
    # Check 1: Zero-byte or missing file content
    if file_size == 0 or (path and path.exists() and path.stat().st_size == 0):
        return {
            'document_state': STATE_BLANK_OR_EMPTY,
            'total_pages': 0,
            'text_pages': 0,
            'photo_pages': 0,
            'readable_pages': 0,
            'blank_pages': 0,
            'readability_ratio': 0.0,
            'details': 'File size is 0 bytes.',
        }

    metadata = extraction.get('metadata') or {}
    ext = (Path(file_name).suffix.lower() if file_name else (path.suffix.lower() if path else ''))
    mime = str(mime_type or '').lower()

    # Check 2: Image formats (png, jpg, jpeg, tif, etc.)
    if ext in {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'} or mime.startswith('image/'):
        return _analyze_image_file(path, text, extraction)

    # Check 3: PDF documents
    if ext == '.pdf' or mime == 'application/pdf':
        return _analyze_pdf_file(path, text, extraction)

    # Check 4: DOCX documents
    if ext == '.docx' or 'docx' in mime:
        return _analyze_docx_file(path, text)

    # Check 5: XLSX documents
    if ext in {'.xlsx', '.xlsm'} or 'spreadsheet' in mime or 'excel' in mime:
        return _analyze_xlsx_file(path, text)

    # Check 6: Plain text / other formats
    cleaned = re.sub(r'\s+', ' ', text).strip()
    words = _extract_meaningful_words(cleaned)
    if not cleaned or len(words) == 0:
        return {
            'document_state': STATE_BLANK_OR_EMPTY,
            'total_pages': 1,
            'text_pages': 1,
            'photo_pages': 0,
            'readable_pages': 0,
            'blank_pages': 1,
            'readability_ratio': 0.0,
            'details': 'Document contains no meaningful text or documentary content.',
        }

    return {
        'document_state': STATE_CONTENT_PRESENT_READABLE,
        'total_pages': 1,
        'text_pages': 1,
        'photo_pages': 0,
        'readable_pages': 1,
        'blank_pages': 0,
        'readability_ratio': 1.0,
        'details': f'Plain text extracted successfully ({len(cleaned)} characters).',
    }


def _analyze_image_file(
    path: Path | None,
    text: str,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Analyzes an image file for blankness, visual content, and OCR readability."""
    visual_summary = extraction.get('visual_summary')
    if visual_summary is None and path and path.exists():
        visual_summary = visual_service.analyze_visual_evidence(
            extraction,
            mime_type='image/png',
            file_path=path,
        )

    # Is the image blank or near-blank (low contrast)?
    if visual_summary:
        if visual_summary.get('blank_or_near_blank'):
            return {
                'document_state': STATE_BLANK_OR_EMPTY,
                'total_pages': 1,
                'text_pages': 0,
                'photo_pages': 0,
                'readable_pages': 0,
                'blank_pages': 1,
                'readability_ratio': 0.0,
                'details': 'Image has near-zero contrast (completely blank or solid color).',
            }

    # If Pillow is available and no visual summary exists, measure contrast directly
    if path and path.exists():
        try:
            from PIL import Image
            with Image.open(path) as img:
                res = visual_service._measure_image(img)
                if res.get('blank_or_near_blank'):
                    return {
                        'document_state': STATE_BLANK_OR_EMPTY,
                        'total_pages': 1,
                        'text_pages': 0,
                        'photo_pages': 0,
                        'readable_pages': 0,
                        'blank_pages': 1,
                        'readability_ratio': 0.0,
                        'details': 'Image has near-zero contrast (blank image).',
                    }
        except Exception:
            pass

    # The image is not blank — meaningful visual content exists.
    # Check if OCR extracted meaningful text
    cleaned_text = re.sub(r'\s+', ' ', text).strip()
    words = [w for w in re.findall(r'[A-Za-z]{3,}', cleaned_text)]
    has_readable_ocr = len(cleaned_text) >= MIN_READABLE_DOCUMENT_CHARS and len(words) >= 4

    if has_readable_ocr:
        return {
            'document_state': STATE_CONTENT_PRESENT_READABLE,
            'total_pages': 1,
            'text_pages': 1,
            'photo_pages': 0,
            'readable_pages': 1,
            'blank_pages': 0,
            'readability_ratio': 1.0,
            'details': f'Scanned image with successful OCR extraction ({len(cleaned_text)} characters).',
        }

    # Meaningful image, but little or no text -> visual_content_only
    return {
        'document_state': STATE_VISUAL_CONTENT_ONLY,
        'total_pages': 1,
        'text_pages': 0,
        'photo_pages': 1,
        'readable_pages': 0,
        'blank_pages': 0,
        'readability_ratio': 1.0,
        'details': 'Visual content detected (photograph or image without extractable machine-readable text).',
    }


def _analyze_pdf_file(
    path: Path | None,
    text: str,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Analyzes a PDF document at page level for text, photos, and blank pages."""
    metadata = extraction.get('metadata') or {}
    total_pages = metadata.get('page_count') or 1

    # If file exists, inspect pypdf reader pages
    page_stats = []
    if path and path.exists():
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            total_pages = len(reader.pages)
            for p_idx, page in enumerate(reader.pages, start=1):
                p_text = (page.extract_text() or '').strip()
                p_images = getattr(page, 'images', []) or []
                img_count = len(p_images)
                char_count = len(p_text)
                words = _extract_meaningful_words(p_text)
                # Quality-based readability: a page is readable if text extraction
                # succeeded and produced at least one meaningful word.  This separates
                # "how much text exists" from "whether the text can be read."
                has_meaningful_text = len(words) >= 1
                is_readable = has_meaningful_text
                is_photo_page = (img_count > 0 and not has_meaningful_text)
                is_blank_page = (not has_meaningful_text and img_count == 0)

                raw_w = getattr(page.mediabox, 'width', None)
                raw_h = getattr(page.mediabox, 'height', None)
                try:
                    eff_w = float(raw_w) if raw_w else 612.0
                    eff_h = float(raw_h) if raw_h else 792.0
                except (TypeError, ValueError):
                    eff_w, eff_h = 612.0, 792.0
                rot = int(page.get('/Rotate', 0) or 0) % 360
                if rot in (90, 270):
                    eff_w, eff_h = eff_h, eff_w
                orientation = 'landscape' if eff_w > eff_h else 'portrait'

                page_stats.append({
                    'page_number': p_idx,
                    'char_count': char_count,
                    'image_count': img_count,
                    'is_readable': is_readable,
                    'is_photo_page': is_photo_page,
                    'is_blank_page': is_blank_page,
                    'width': round(eff_w, 1),
                    'height': round(eff_h, 1),
                    'rotation': rot,
                    'orientation': orientation,
                })
        except Exception:
            pass

    # If we couldn't parse page-by-page, fallback to document-level signals
    if not page_stats:
        cleaned = re.sub(r'\s+', ' ', text).strip()
        words = _extract_meaningful_words(cleaned)
        ocr_images = metadata.get('ocr_image_count', 0)

        if (not cleaned or len(words) == 0) and ocr_images == 0:
            return {
                'document_state': STATE_BLANK_OR_EMPTY,
                'total_pages': total_pages,
                'text_pages': total_pages,
                'photo_pages': 0,
                'readable_pages': 0,
                'blank_pages': total_pages,
                'readability_ratio': 0.0,
                'details': 'PDF contains no meaningful text and no embedded images.',
            }
        elif (not cleaned or len(words) == 0) and ocr_images > 0:
            return {
                'document_state': STATE_VISUAL_CONTENT_ONLY,
                'total_pages': total_pages,
                'text_pages': 0,
                'photo_pages': total_pages,
                'readable_pages': 0,
                'blank_pages': 0,
                'readability_ratio': 1.0,
                'details': f'PDF contains {ocr_images} embedded images but no machine-readable text was extracted.',
            }
        else:
            return {
                'document_state': STATE_CONTENT_PRESENT_READABLE,
                'total_pages': total_pages,
                'text_pages': total_pages,
                'photo_pages': 0,
                'readable_pages': total_pages,
                'blank_pages': 0,
                'readability_ratio': 1.0,
                'details': f'PDF text successfully extracted ({len(cleaned)} characters).',
            }

    # Page-by-page breakdown
    photo_pages = sum(1 for p in page_stats if p['is_photo_page'])
    blank_pages = sum(1 for p in page_stats if p['is_blank_page'])
    readable_pages = sum(1 for p in page_stats if p['is_readable'])
    text_pages = len(page_stats) - photo_pages - blank_pages

    # If every page is blank
    if blank_pages == len(page_stats):
        return {
            'document_state': STATE_BLANK_OR_EMPTY,
            'total_pages': len(page_stats),
            'text_pages': 0,
            'photo_pages': 0,
            'readable_pages': 0,
            'blank_pages': blank_pages,
            'readability_ratio': 0.0,
            'details': f'All {len(page_stats)} page(s) in the PDF are blank (no meaningful text, no images).',
        }

    # If all non-blank pages are photo/image only and no readable text
    if readable_pages == 0 and photo_pages > 0:
        # Check if OCR extracted text from embedded images across the document
        cleaned = re.sub(r'\s+', ' ', text).strip()
        words = _extract_meaningful_words(cleaned)
        if len(cleaned) >= MIN_READABLE_DOCUMENT_CHARS and len(words) >= 4:
            # Scanned document with successful OCR
            return {
                'document_state': STATE_CONTENT_PRESENT_READABLE,
                'total_pages': len(page_stats),
                'text_pages': len(page_stats),
                'photo_pages': 0,
                'readable_pages': len(page_stats),
                'blank_pages': blank_pages,
                'readability_ratio': 1.0,
                'details': f'Scanned PDF document with successful OCR text extraction ({len(cleaned)} characters).',
            }
        return {
            'document_state': STATE_VISUAL_CONTENT_ONLY,
            'total_pages': len(page_stats),
            'text_pages': 0,
            'photo_pages': photo_pages,
            'readable_pages': 0,
            'blank_pages': blank_pages,
            'readability_ratio': 1.0,
            'details': f'PDF consists of {photo_pages} visual/photo page(s) with no extractable text.',
        }

    # Document has text pages. Calculate readability ratio on meaningful text pages.
    # Denominator = text_pages + any text-intended pages (excludes legitimate photo pages)
    denominator = max(1, text_pages + (1 if text_pages == 0 and readable_pages > 0 else 0))
    readability_ratio = round(readable_pages / denominator, 2)

    if readability_ratio >= READABILITY_PAGE_RATIO_THRESHOLD:
        doc_state = STATE_CONTENT_PRESENT_READABLE
        if denominator <= 1:
            details = 'Readable content detected.'
        else:
            details = (
                f'{readable_pages} of {denominator} text page(s) readable ({round(readability_ratio * 100)}%). '
                f'Sufficient readable content detected.'
            )
        if photo_pages > 0:
            details += f' ({photo_pages} photo/visual page(s) recognized as documentary media).'
    else:
        # Substantial portion cannot be read
        doc_state = STATE_CONTENT_PRESENT_READABLE  # content is present, but readability check will flag needs_review
        details = (
            f'Only {readable_pages} of {denominator} text page(s) readable ({round(readability_ratio * 100)}%). '
            f'Substantial portion of text cannot be reliably read.'
        )

    return {
        'document_state': doc_state,
        'total_pages': len(page_stats),
        'text_pages': denominator,
        'photo_pages': photo_pages,
        'readable_pages': readable_pages,
        'blank_pages': blank_pages,
        'readability_ratio': readability_ratio,
        'details': details,
        'page_stats': page_stats,
    }


def _analyze_docx_file(path: Path | None, text: str) -> dict[str, Any]:
    """Analyzes a DOCX document for text and embedded media."""
    cleaned = re.sub(r'\s+', ' ', text).strip()
    has_media = False
    if path and path.exists():
        try:
            with zipfile.ZipFile(path) as archive:
                has_media = any(f.startswith('word/media/') for f in archive.namelist())
        except Exception:
            pass

    if not cleaned and not has_media:
        return {
            'document_state': STATE_BLANK_OR_EMPTY,
            'total_pages': 1,
            'text_pages': 1,
            'photo_pages': 0,
            'readable_pages': 0,
            'blank_pages': 1,
            'readability_ratio': 0.0,
            'details': 'DOCX contains no text and no embedded media.',
        }

    if not cleaned and has_media:
        return {
            'document_state': STATE_VISUAL_CONTENT_ONLY,
            'total_pages': 1,
            'text_pages': 0,
            'photo_pages': 1,
            'readable_pages': 0,
            'blank_pages': 0,
            'readability_ratio': 1.0,
            'details': 'DOCX contains embedded images/photos but no document body text.',
        }

    return {
        'document_state': STATE_CONTENT_PRESENT_READABLE,
        'total_pages': 1,
        'text_pages': 1,
        'photo_pages': 1 if has_media else 0,
        'readable_pages': 1,
        'blank_pages': 0,
        'readability_ratio': 1.0,
        'details': f'DOCX text successfully extracted ({len(cleaned)} characters).',
    }


def _analyze_xlsx_file(path: Path | None, text: str) -> dict[str, Any]:
    """Analyzes an XLSX document for populated cell data."""
    cleaned = re.sub(r'\s+', ' ', text).strip()
    has_cell_data = False
    if path and path.exists():
        try:
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
            for sheet in wb.worksheets[:5]:
                for row in sheet.iter_rows(max_row=30, max_col=20, values_only=True):
                    if any(v not in (None, '') for v in row):
                        has_cell_data = True
                        break
                if has_cell_data:
                    break
            wb.close()
        except Exception:
            has_cell_data = bool(cleaned)
    else:
        has_cell_data = bool(cleaned)

    if not has_cell_data and not cleaned:
        return {
            'document_state': STATE_BLANK_OR_EMPTY,
            'total_pages': 1,
            'text_pages': 1,
            'photo_pages': 0,
            'readable_pages': 0,
            'blank_pages': 1,
            'readability_ratio': 0.0,
            'details': 'Spreadsheet contains no data cells.',
        }

    return {
        'document_state': STATE_CONTENT_PRESENT_READABLE,
        'total_pages': 1,
        'text_pages': 1,
        'photo_pages': 0,
        'readable_pages': 1,
        'blank_pages': 0,
        'readability_ratio': 1.0,
        'details': f'Spreadsheet data extracted successfully ({len(cleaned)} characters).',
    }


def _build_technical_checks(document_state: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Builds the 3 standard technical checks (Content, Readability, Text Extraction)."""
    checks = []
    ratio = analysis.get('readability_ratio', 1.0)
    details = analysis.get('details', '')

    # 1. Content Presence Check
    if document_state == STATE_CONTENT_PRESENT_READABLE:
        checks.append({
            'key': 'document_content',
            'label': 'Document Content',
            'check_type': 'technical_content_presence',
            'state': 'detected',
            'status': 'passed',
            'message': 'Meaningful content detected',
            'detail': details or 'Document contains meaningful documentary content.',
        })
    elif document_state == STATE_VISUAL_CONTENT_ONLY:
        checks.append({
            'key': 'document_content',
            'label': 'Document Content',
            'check_type': 'technical_content_presence',
            'state': 'detected',
            'status': 'passed',
            'message': 'Visual content detected',
            'detail': details or 'Visual documentary content detected (photographs or scanned media).',
        })
    else:  # STATE_BLANK_OR_EMPTY
        checks.append({
            'key': 'document_content',
            'label': 'Document Content',
            'check_type': 'technical_content_presence',
            'state': 'failed',
            'status': 'blocker',
            'message': 'No meaningful content detected',
            'detail': details or 'The submitted document appears to contain no meaningful content.',
        })

    # 2. Readability Check
    if document_state == STATE_CONTENT_PRESENT_READABLE:
        if ratio >= READABILITY_PAGE_RATIO_THRESHOLD:
            checks.append({
                'key': 'document_readability',
                'label': 'Readability',
                'check_type': 'technical_readability',
                'state': 'sufficient',
                'status': 'passed',
                'message': 'Sufficient readable content detected',
                'detail': details,
            })
        else:
            checks.append({
                'key': 'document_readability',
                'label': 'Readability',
                'check_type': 'technical_readability',
                'state': 'needs_review',
                'status': 'needs_review',
                'message': 'Substantial portion of text could not be reliably read',
                'detail': details,
            })
    elif document_state == STATE_VISUAL_CONTENT_ONLY:
        checks.append({
            'key': 'document_readability',
            'label': 'Readability',
            'check_type': 'technical_readability',
            'state': 'needs_review',
            'status': 'needs_review',
            'message': 'Text could not be reliably extracted. Manual visual verification required.',
            'detail': 'Document contains visual media without machine-readable text.',
        })
    else:  # STATE_BLANK_OR_EMPTY
        checks.append({
            'key': 'document_readability',
            'label': 'Readability',
            'check_type': 'technical_readability',
            'state': 'failed',
            'status': 'blocker',
            'message': 'Document contains no readable content',
            'detail': 'Cannot evaluate readability for an empty or blank submission.',
        })

    # 3. Text Extraction Check
    char_count = analysis.get('extracted_char_count', 0)
    if document_state == STATE_CONTENT_PRESENT_READABLE:
        if char_count > 0:
            checks.append({
                'key': 'text_extraction',
                'label': 'Text Extraction',
                'check_type': 'technical_text_extraction',
                'state': 'successful',
                'status': 'passed',
                'message': 'Text successfully extracted',
                'detail': f"Extracted {char_count} character(s) across readable pages.",
            })
        else:
            checks.append({
                'key': 'text_extraction',
                'label': 'Text Extraction',
                'check_type': 'technical_text_extraction',
                'state': 'limited',
                'status': 'needs_review',
                'message': 'No machine-readable text extracted',
                'detail': 'Content was detected but text could not be extracted for automated review.',
            })
    elif document_state == STATE_VISUAL_CONTENT_ONLY:
        checks.append({
            'key': 'text_extraction',
            'label': 'Text Extraction',
            'check_type': 'technical_text_extraction',
            'state': 'limited',
            'status': 'needs_review',
            'message': 'Text unavailable / visual-only submission',
            'detail': 'Machine-readable text could not be extracted; visual review required.',
        })
    else:  # STATE_BLANK_OR_EMPTY
        checks.append({
            'key': 'text_extraction',
            'label': 'Text Extraction',
            'check_type': 'technical_text_extraction',
            'state': 'failed',
            'status': 'blocker',
            'message': 'Submission cannot be evaluated automatically',
            'detail': 'No extractable text or visual elements found in the submitted file.',
        })

    return checks


def _build_technical_findings(document_state: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Builds technical findings (blocker for blank, needs_verification for visual-only)."""
    findings = []
    ratio = analysis.get('readability_ratio', 1.0)

    if document_state == STATE_BLANK_OR_EMPTY:
        findings.append(rule_engine.finding(
            'technical_blank_document',
            'blocker',
            rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
            'The submitted document appears to contain no meaningful content.',
            analysis.get('details') or 'The file is blank or contains no readable text or visual content.',
            rule='blank_document',
            dimension='file_health',
            deficiency_category='scan_quality_defect',
            finding_observation='The submitted document is blank or empty and cannot be evaluated.',
            corrective_instruction='Please upload a complete, legible file containing the required documentary submission.',
            automation_level='automated_with_review',
        ))
    elif document_state == STATE_VISUAL_CONTENT_ONLY:
        findings.append(rule_engine.finding(
            'technical_visual_content_only',
            'needs_verification',
            rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
            'Visual content detected, but readable text could not be reliably extracted. Manual review required.',
            analysis.get('details') or 'Review the visual submission manually for required signatories, dates, or certifications.',
            rule='visual_content_only',
            dimension='file_health',
            deficiency_category='scan_quality_defect',
            finding_observation='Visual content detected, but readable text could not be reliably extracted.',
            corrective_instruction='Review the visual submission manually for required content or provide a clearer digital document.',
            automation_level='human_verification',
        ))
    elif document_state == STATE_CONTENT_PRESENT_READABLE and ratio < READABILITY_PAGE_RATIO_THRESHOLD:
        findings.append(rule_engine.finding(
            'technical_partially_unreadable',
            'warning',
            rule_engine.CATEGORY_FILE_DOCUMENT_QUALITY,
            'A substantial portion of the document text could not be reliably read.',
            analysis.get('details') or 'Review document scans for degraded or illegible pages.',
            rule='partially_unreadable',
            dimension='file_health',
            deficiency_category='scan_quality_defect',
            finding_observation=f'Only {round(ratio * 100)}% of document text pages could be reliably read.',
            corrective_instruction='Ensure all pages are clearly scanned and fully legible before resubmitting.',
            automation_level='automated_with_review',
        ))

    return findings
