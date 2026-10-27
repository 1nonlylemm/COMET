import json
import re
import shutil
import unicodedata
from collections import Counter
from pathlib import Path


SUPPORTED_REFERENCE_EXTENSIONS = {
    '.bmp',
    '.csv',
    '.doc',
    '.docx',
    '.jpeg',
    '.jpg',
    '.pdf',
    '.png',
    '.tif',
    '.tiff',
    '.xls',
    '.xlsm',
    '.xlsx',
}

TABLE_HEAVY_FAMILIES = {
    'billing_package',
    'detailed_engineering_estimate',
    'program_of_works',
    'progress_report',
}

DOCUMENT_FAMILY_PATTERNS = (
    ('nadai_fund_transfer', (
        r'\bnadai\b',
        r'\bauthority\s+to\s+debit\b',
        r'\bnotice\s+of\s+cash\s+allocation\b',
        r'\bproof\s+of\s+fund\s+transfer\b',
    )),
    ('billing_package', (
        r'\bsord\b',
        r'\bstatement\s+of\s+receipts?\s+and\s+disbursements?\b',
        r'\bliquidation\b',
        r'\bbilling\b',
        r'\binvoice\b',
    )),
    ('official_receipt', (
        r'\bofficial\s+receipt\b',
        r'\bor\s+no\b',
        r'\breceipt\b',
    )),
    ('program_of_works', (
        r'\bprogram\s+of\s+works?\b',
        r'\bpow\b',
        r'\bbill\s+of\s+quantities\b',
    )),
    ('detailed_engineering_estimate', (
        r'\bdetailed\s+engineering\b',
        r'\bded\b',
        r'\bestimate\b',
        r'\bquantity\s+takeoff\b',
    )),
    ('resolution', (
        r'\bresolution\b',
        r'\bsanggunian\b',
        r'\bsangguniang\b',
    )),
    ('certification', (
        r'\bcertification\b',
        r'\bcertificate\b',
    )),
    ('progress_report', (
        r'\bprogress\s+report\b',
        r'\baccomplishment\s+report\b',
        r'\bmonthly\s+report\b',
        r'\butilization\s+report\b',
    )),
    ('progress_photo', (
        r'\bphoto\s+documentation\b',
        r'\bprogress\s+photo\b',
        r'\bphotographs?\b',
        r'\bbefore\s+and\s+after\b',
    )),
)


def inventory_reference_roots(roots, *, max_files=None):
    """Build a sanitized manifest from local documentary reference folders."""
    files = []
    for root in roots or []:
        root_path = Path(root)
        if not root_path.exists():
            continue
        root_key = slugify(root_path.name).replace('-', '_')
        for path in sorted(_iter_reference_files(root_path), key=lambda item: str(item).lower()):
            if max_files and len(files) >= max_files:
                break
            relative_path = _relative_posix(path, root_path)
            entry = _manifest_entry(path, root_path, root_key, relative_path)
            files.append(entry)

    return {
        'version': 'documentary-reference-patterns-2026.05.23',
        'source_policy': {
            'use_original_files_as_seed_attachments': False,
            'use_original_files_as_pattern_references_only': True,
            'store_portable_pattern_source_only': True,
        },
        'summary': _summary(files),
        'files': files,
    }


def write_pattern_inventory(inventory, *, report_root, seed_asset_root, reset=False):
    """Write sanitized reports and portable seed-asset pattern profiles."""
    report_root = Path(report_root)
    seed_asset_root = Path(seed_asset_root)
    if reset:
        _safe_reset(report_root, expected_marker='documentary_reference_pattern_inventory')
        _safe_reset(seed_asset_root, expected_marker='documentary_patterns')
    report_root.mkdir(parents=True, exist_ok=True)
    seed_asset_root.mkdir(parents=True, exist_ok=True)

    manifest = list((inventory or {}).get('files') or [])
    seed_payload = {
        'version': (inventory or {}).get('version'),
        'source_policy': (inventory or {}).get('source_policy') or {},
        'profiles': [_seed_profile(item) for item in manifest],
    }
    _write_json(report_root / 'source_file_manifest.json', {
        'version': (inventory or {}).get('version'),
        'summary': (inventory or {}).get('summary') or {},
        'files': manifest,
    })
    _write_json(seed_asset_root / 'reference_pattern_profiles.json', seed_payload)
    (report_root / 'requirement_family_summary.md').write_text(
        _family_summary_markdown(inventory or {}),
        encoding='utf-8',
    )
    return {
        'report_root': str(report_root),
        'seed_asset_root': str(seed_asset_root),
        'manifest_count': len(manifest),
        'profile_count': len(seed_payload['profiles']),
    }


def slugify(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    normalized = normalized.encode('ascii', 'ignore').decode('ascii')
    normalized = re.sub(r'[^A-Za-z0-9]+', '-', normalized).strip('-').lower()
    return normalized or 'source'


def layout_profile_for_family(document_family):
    family = str(document_family or 'generic_document')
    table_columns = {
        'billing_package': ['Particulars', 'Reference', 'Amount', 'Remarks'],
        'program_of_works': ['Item Description', 'Quantity', 'Unit', 'Unit Cost', 'Amount'],
        'detailed_engineering_estimate': ['Work Item', 'Quantity', 'Unit', 'Direct Cost', 'Amount'],
        'progress_report': ['Activity', 'Previous', 'Current', 'Total', 'Remarks'],
    }
    profile = {
        'source': 'sanitized_reference_pattern',
        'strictness': 'standard_template',
        'page_count': {'min': 1, 'max': 4},
        'required_headings': [{'id': family, 'label': _family_label(family), 'required_terms': [_family_label(family)]}],
        'signature_zones': [
            {'id': 'prepared_by', 'label': 'Prepared by', 'page': 1, 'bbox': [8, 78, 26, 10]},
            {'id': 'reviewed_by', 'label': 'Reviewed by', 'page': 1, 'bbox': [38, 78, 26, 10]},
            {'id': 'approved_by', 'label': 'Approved by', 'page': 1, 'bbox': [68, 78, 24, 10]},
        ],
    }
    if family in table_columns:
        profile['tables'] = [{
            'id': f'{family}_main_table',
            'label': f'{_family_label(family)} table',
            'page': 1,
            'bbox': [7, 38, 86, 28],
            'required_columns': table_columns[family],
        }]
    return profile


def _iter_reference_files(root):
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_REFERENCE_EXTENSIONS:
            continue
        yield path


def _manifest_entry(path, root, root_key, relative_path):
    extension = path.suffix.lower().lstrip('.')
    family = detect_document_family(f'{relative_path} {path.name}')
    return {
        'source_root_key': root_key,
        'relative_path': relative_path,
        'portable_pattern_source': f'{root_key}:{relative_path}',
        'file_name': path.name,
        'extension': extension,
        'size_bytes': path.stat().st_size,
        'lgu_hint': _lgu_hint(relative_path),
        'fiscal_year': _fiscal_year(f'{root.name} {relative_path}'),
        'document_family': family,
        'table_candidate': _table_candidate(family, extension, relative_path),
        'page_count': _page_count(path),
        'ocr_likely_required': _ocr_likely_required(path, extension),
    }


def detect_document_family(value):
    corpus = _normalized_search_text(value)
    for family, patterns in DOCUMENT_FAMILY_PATTERNS:
        if any(re.search(pattern, corpus) for pattern in patterns):
            return family
    return 'generic_document'


def _table_candidate(family, extension, relative_path):
    if family in TABLE_HEAVY_FAMILIES:
        return True
    if extension in {'csv', 'xls', 'xlsm', 'xlsx'}:
        return True
    corpus = _normalized_search_text(relative_path)
    return any(term in corpus for term in (
        'table',
        'cost breakdown',
        'disbursement',
        'line item',
        'quantity',
        'unit cost',
    ))


def _ocr_likely_required(path, extension):
    if extension in {'jpg', 'jpeg', 'png', 'tif', 'tiff', 'bmp'}:
        return True
    if extension != 'pdf':
        return False
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        text = ' '.join((page.extract_text() or '') for page in reader.pages[:2])
    except Exception:
        return None
    return len(re.findall(r'[A-Za-z]{3,}', text)) < 8


def _page_count(path):
    if path.suffix.lower() != '.pdf':
        return 1 if path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp'} else None
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def _lgu_hint(relative_path):
    for segment in Path(relative_path).parts:
        cleaned = str(segment).strip()
        if not cleaned or cleaned.startswith('00 ') or cleaned.startswith('01 '):
            continue
        if re.search(r'\b(guidelines?|fy\s*20\d{2}|20\d{2})\b', cleaned, flags=re.IGNORECASE):
            continue
        return _portable_lgu_hint(cleaned)
    return None


def _fiscal_year(value):
    years = [int(match) for match in re.findall(r'\b(20\d{2})\b', str(value or ''))]
    return years[0] if years else None


def _summary(files):
    by_family = Counter(item['document_family'] for item in files)
    by_year = Counter(str(item['fiscal_year'] or 'unknown') for item in files)
    by_extension = Counter(item['extension'] for item in files)
    by_lgu = Counter(item['lgu_hint'] or 'unknown' for item in files)
    return {
        'total_files': len(files),
        'table_candidates': sum(1 for item in files if item.get('table_candidate')),
        'ocr_likely_required': sum(1 for item in files if item.get('ocr_likely_required') is True),
        'by_family': dict(sorted(by_family.items())),
        'by_year': dict(sorted(by_year.items())),
        'by_extension': dict(sorted(by_extension.items())),
        'top_lgus': dict(by_lgu.most_common(20)),
    }


def _seed_profile(item):
    family = item.get('document_family') or 'generic_document'
    return {
        'profile_id': f'{family}:{slugify(item.get("lgu_hint") or "unknown")}:{item.get("fiscal_year") or "unknown"}',
        'document_family': family,
        'lgu_hint': item.get('lgu_hint'),
        'fiscal_year': item.get('fiscal_year'),
        'portable_pattern_source': item.get('portable_pattern_source'),
        'extension': item.get('extension'),
        'table_candidate': bool(item.get('table_candidate')),
        'layout_profile': layout_profile_for_family(family),
    }


def _family_summary_markdown(inventory):
    summary = inventory.get('summary') or {}
    lines = [
        '# Documentary Reference Pattern Inventory',
        '',
        'This report is sanitized. Original reference files remain pattern sources only and are not seeded as demo attachments.',
        '',
        f'- Total files: {summary.get("total_files", 0)}',
        f'- Table candidates: {summary.get("table_candidates", 0)}',
        f'- OCR likely required: {summary.get("ocr_likely_required", 0)}',
        '',
        '## Families',
        '',
    ]
    for family, count in (summary.get('by_family') or {}).items():
        lines.append(f'- {family}: {count}')
    lines.extend(['', '## Years', ''])
    for year, count in (summary.get('by_year') or {}).items():
        lines.append(f'- {year}: {count}')
    lines.append('')
    return '\n'.join(lines)


def _relative_posix(path, root):
    return str(Path(path).relative_to(root)).replace('\\', '/')


def _normalized_search_text(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    normalized = normalized.encode('ascii', 'ignore').decode('ascii')
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized.lower())
    return re.sub(r'\s+', ' ', normalized).strip()


def _portable_lgu_hint(value):
    cleaned = str(value or '').replace('\ufffd', 'N').replace('Ã‘', 'N').replace('Ã±', 'n')
    normalized = unicodedata.normalize('NFKD', cleaned)
    normalized = normalized.encode('ascii', 'ignore').decode('ascii')
    normalized = re.sub(r'[^A-Za-z0-9 ]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip().upper() or None


def _family_label(family):
    labels = {
        'billing_package': 'Statement of Receipts and Disbursements',
        'nadai_fund_transfer': 'Notice of Authority to Debit Account Issued',
        'official_receipt': 'Official Receipt',
        'program_of_works': 'Program of Works',
        'detailed_engineering_estimate': 'Detailed Engineering Design / Estimate',
        'resolution': 'Sanggunian Resolution',
        'certification': 'Certification',
        'progress_report': 'Progress / Accomplishment Report',
        'progress_photo': 'Photo Documentation',
    }
    return labels.get(family, 'Documentary Requirement')


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def _safe_reset(root, *, expected_marker):
    root = Path(root).resolve()
    if root.exists():
        if expected_marker not in root.parts and expected_marker not in root.name:
            raise RuntimeError(f'Refusing to remove unexpected folder: {root}')
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
