"""AWS Textract/Rekognition adapters for documentary compliance.

These adapters keep AWS output advisory: they summarize provider signals for
audit and scoring context, but never decide compliance by themselves.
"""

from __future__ import annotations

import io
from pathlib import Path

from .base import BaseProviderAdapter, ProviderError, ProviderResult


DEFAULT_REGION = 'ap-southeast-1'
DEFAULT_MAX_SYNC_BYTES = 10 * 1024 * 1024
DEFAULT_TEXTRACT_FEATURE_TYPES = ('TABLES', 'FORMS', 'SIGNATURES', 'LAYOUT')
DEFAULT_REKOGNITION_MAX_LABELS = 20
DEFAULT_REKOGNITION_MIN_CONFIDENCE = 70.0
DEFAULT_LOCATION_LANGUAGE = 'en'


class AwsTextractAnalyzeDocumentAdapter(BaseProviderAdapter):
    name = 'aws-textract'

    def __init__(
        self,
        *,
        client=None,
        config=None,
        region=DEFAULT_REGION,
        feature_types=None,
        max_sync_bytes=DEFAULT_MAX_SYNC_BYTES,
        max_pages=None,
    ):
        self.client = client
        self.config = config
        self.region = region or DEFAULT_REGION
        self.feature_types = list(feature_types or DEFAULT_TEXTRACT_FEATURE_TYPES)
        self.max_sync_bytes = int(max_sync_bytes or DEFAULT_MAX_SYNC_BYTES)
        raw_max_pages = max_pages if max_pages is not None else _config_value(
            config, 'DOCUMENT_AWS_TEXTRACT_MAX_PAGES', _config_value(config, 'DOCUMENT_OCR_MAX_PAGES', 5)
        )
        self.max_pages = int(raw_max_pages) if raw_max_pages is not None else None

    def analyze_document(self, file_path):
        client = self.client or _boto3_client('textract', config=self.config, region=self.region)
        pages, total_document_pages = _extract_document_pages(
            file_path,
            max_bytes=self.max_sync_bytes,
            max_pages=self.max_pages,
        )
        all_blocks = []
        model_version = ''
        per_page_summaries = []

        for page_num, page_bytes in pages:
            response = _call_provider(
                lambda bytes_=page_bytes: client.analyze_document(
                    Document={'Bytes': bytes_},
                    FeatureTypes=self.feature_types,
                )
            )
            version = str(response.get('AnalyzeDocumentModelVersion') or '')
            if version:
                model_version = version
            blocks = response.get('Blocks') or []
            all_blocks.extend(blocks)
            per_page_summaries.append({
                'page': page_num,
                'block_count': len(blocks),
                'line_count': _count_blocks(blocks, 'LINE'),
                'table_count': _count_blocks(blocks, 'TABLE'),
                'key_value_set_count': _count_blocks(blocks, 'KEY_VALUE_SET'),
                'signature_count': _count_blocks(blocks, 'SIGNATURE'),
                'confidence': _average_confidence(blocks),
            })

        payload = {
            'api': 'AnalyzeDocument',
            'model_version': model_version,
            'feature_types': self.feature_types,
            'block_count': len(all_blocks),
            'page_count': len(pages),
            'total_document_pages': total_document_pages,
            'line_count': _count_blocks(all_blocks, 'LINE'),
            'table_count': _count_blocks(all_blocks, 'TABLE'),
            'key_value_set_count': _count_blocks(all_blocks, 'KEY_VALUE_SET'),
            'signature_count': _count_blocks(all_blocks, 'SIGNATURE'),
        }
        forms = _extract_textract_forms(all_blocks)
        if forms:
            payload['forms'] = forms
        if len(pages) > 1:
            payload['per_page_summary'] = per_page_summaries

        return ProviderResult(
            name=self.name,
            version=model_version,
            region=self.region,
            confidence=_average_confidence(all_blocks),
            payload=payload,
        )


class AwsTextractAnalyzeExpenseAdapter(BaseProviderAdapter):
    name = 'aws-textract-analyze-expense'

    def __init__(
        self,
        *,
        client=None,
        config=None,
        region=DEFAULT_REGION,
        max_sync_bytes=DEFAULT_MAX_SYNC_BYTES,
        max_pages=None,
    ):
        self.client = client
        self.config = config
        self.region = region or DEFAULT_REGION
        self.max_sync_bytes = int(max_sync_bytes or DEFAULT_MAX_SYNC_BYTES)
        raw_max_pages = max_pages if max_pages is not None else _config_value(
            config, 'DOCUMENT_AWS_TEXTRACT_MAX_PAGES', _config_value(config, 'DOCUMENT_OCR_MAX_PAGES', 5)
        )
        self.max_pages = int(raw_max_pages) if raw_max_pages is not None else None

    def analyze_expense(self, file_path):
        client = self.client or _boto3_client('textract', config=self.config, region=self.region)
        pages, total_document_pages = _extract_document_pages(
            file_path,
            max_bytes=self.max_sync_bytes,
            max_pages=self.max_pages,
        )
        all_documents = []
        model_version = ''
        per_page_summaries = []

        for page_num, page_bytes in pages:
            response = _call_provider(
                lambda bytes_=page_bytes: client.analyze_expense(
                    Document={'Bytes': bytes_}
                )
            )
            version = str(response.get('AnalyzeExpenseModelVersion') or '')
            if version:
                model_version = version
            documents = response.get('ExpenseDocuments') or []
            all_documents.extend(documents)
            per_page_summaries.append({
                'page': page_num,
                'expense_document_count': len(documents),
                'summary_field_count': sum(len(document.get('SummaryFields') or []) for document in documents),
                'line_item_group_count': sum(len(document.get('LineItemGroups') or []) for document in documents),
                'confidence': _average_confidence(documents),
            })

        payload = {
            'api': 'AnalyzeExpense',
            'model_version': model_version,
            'expense_document_count': len(all_documents),
            'page_count': len(pages),
            'total_document_pages': total_document_pages,
            'summary_field_count': sum(len(document.get('SummaryFields') or []) for document in all_documents),
            'line_item_group_count': sum(len(document.get('LineItemGroups') or []) for document in all_documents),
        }
        forms = _extract_expense_forms(all_documents)
        if forms:
            payload['forms'] = forms
        if len(pages) > 1:
            payload['per_page_summary'] = per_page_summaries

        return ProviderResult(
            name=self.name,
            version=model_version,
            region=self.region,
            confidence=_average_confidence(all_documents),
            payload=payload,
        )


class AwsRekognitionAdapter(BaseProviderAdapter):
    name = 'aws-rekognition'

    def __init__(
        self,
        *,
        client=None,
        config=None,
        region=DEFAULT_REGION,
        max_sync_bytes=DEFAULT_MAX_SYNC_BYTES,
        max_labels=DEFAULT_REKOGNITION_MAX_LABELS,
        min_confidence=DEFAULT_REKOGNITION_MIN_CONFIDENCE,
    ):
        self.client = client
        self.config = config
        self.region = region or DEFAULT_REGION
        self.max_sync_bytes = int(max_sync_bytes or DEFAULT_MAX_SYNC_BYTES)
        self.max_labels = int(max_labels or DEFAULT_REKOGNITION_MAX_LABELS)
        self.min_confidence = float(min_confidence or DEFAULT_REKOGNITION_MIN_CONFIDENCE)

    def detect_objects(self, image_path):
        client = self.client or _boto3_client('rekognition', config=self.config, region=self.region)
        response = _call_provider(
            lambda: client.detect_labels(
                Image={'Bytes': _read_document_bytes(image_path, max_bytes=self.max_sync_bytes)},
                Features=['GENERAL_LABELS', 'IMAGE_PROPERTIES'],
                MaxLabels=self.max_labels,
                MinConfidence=self.min_confidence,
            )
        )
        labels = response.get('Labels') or []
        return ProviderResult(
            name=self.name,
            version=str(response.get('LabelModelVersion') or ''),
            region=self.region,
            confidence=_average_confidence(labels),
            payload={
                'api': 'DetectLabels',
                'model_version': str(response.get('LabelModelVersion') or ''),
                'label_count': len(labels),
                'labels': [_label_summary(label) for label in labels[:12]],
            },
        )


SUPPORTED_TEXTRACT_EXTENSIONS = frozenset({'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff'})
SUPPORTED_TEXTRACT_MIME_TYPES = frozenset({
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/tiff',
})
UNSUPPORTED_TEXTRACT_EXTENSIONS = frozenset({
    '.docx',
    '.doc',
    '.xlsx',
    '.xls',
    '.csv',
    '.txt',
})
UNSUPPORTED_TEXTRACT_MIME_TYPES = frozenset({
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    'text/plain',
    'text/csv',
})


def is_supported_textract_format(*, file_name=None, mime_type=None, file_path=None):
    """Return whether the specified file format is supported by AWS Textract.

    AWS Textract accepts PDF, PNG, JPEG, and TIFF documents. Word documents (.docx, .doc),
    spreadsheets, and plain text files are unsupported and will fail with
    UnsupportedDocumentException if dispatched.

    Validation rules:
    1. If neither MIME type nor file extension is available, return False (fail-closed).
    2. If both MIME type and file extension are available:
       Both must be valid supported formats that agree; conflicting, unsupported, or unknown combinations return False.
    3. If only one signal is available:
       Returns True only if that signal is in the supported set; unsupported or unknown returns False.
    """
    raw_mime = str(mime_type or '').strip().lower()
    has_mime = bool(raw_mime)

    suffix = ''
    if file_name:
        suffix = Path(str(file_name)).suffix.lower()
    elif file_path:
        suffix = Path(str(file_path)).suffix.lower()
    has_suffix = bool(suffix)

    # Rule 1: Neither signal exists -> fail closed
    if not has_mime and not has_suffix:
        return False

    is_supported_mime = raw_mime in SUPPORTED_TEXTRACT_MIME_TYPES
    is_supported_suffix = suffix in SUPPORTED_TEXTRACT_EXTENSIONS

    # Rule 2: Both signals exist -> both must be supported and mutually consistent
    if has_mime and has_suffix:
        if not (is_supported_mime and is_supported_suffix):
            return False
        # Mutually consistent format categories
        if raw_mime == 'application/pdf' and suffix != '.pdf':
            return False
        if raw_mime.startswith('image/') and suffix == '.pdf':
            return False
        return True

    # Rule 3: Only MIME exists
    if has_mime:
        return is_supported_mime

    # Rule 4: Only extension exists
    return is_supported_suffix


def configured_adapters(
    config,
    *,
    evidence_type,
    file_name=None,
    mime_type=None,
    file_path=None,
    document_file=None,
):
    if not _config_bool(config, 'DOCUMENT_AWS_ENABLED'):
        return []

    if document_file is not None:
        file_name = file_name or getattr(document_file, 'file_name', None)
        mime_type = mime_type or getattr(document_file, 'mime_type', None)
        file_path = file_path or getattr(document_file, 'file_path', None)

    region = _config_value(config, 'DOCUMENT_AWS_REGION', DEFAULT_REGION)
    max_sync_bytes = int(_config_value(config, 'DOCUMENT_AWS_MAX_SYNC_BYTES', DEFAULT_MAX_SYNC_BYTES))
    evidence_type = str(evidence_type or '').strip().lower()

    if evidence_type == 'progress_photo':
        if not _config_bool(config, 'DOCUMENT_AWS_REKOGNITION_ENABLED', default=True):
            return []
        return [
            AwsRekognitionAdapter(
                config=config,
                region=region,
                max_sync_bytes=max_sync_bytes,
                max_labels=int(_config_value(config, 'DOCUMENT_AWS_REKOGNITION_MAX_LABELS', DEFAULT_REKOGNITION_MAX_LABELS)),
                min_confidence=float(_config_value(config, 'DOCUMENT_AWS_REKOGNITION_MIN_CONFIDENCE', DEFAULT_REKOGNITION_MIN_CONFIDENCE)),
            )
        ]

    if not _config_bool(config, 'DOCUMENT_AWS_TEXTRACT_ENABLED', default=True):
        return []

    if not is_supported_textract_format(file_name=file_name, mime_type=mime_type, file_path=file_path):
        return []

    max_pages_raw = _config_value(
        config, 'DOCUMENT_AWS_TEXTRACT_MAX_PAGES', _config_value(config, 'DOCUMENT_OCR_MAX_PAGES', 5)
    )
    max_pages = int(max_pages_raw) if max_pages_raw is not None else 5

    if evidence_type in {'official_receipt', 'billing_package'}:
        return [
            AwsTextractAnalyzeExpenseAdapter(
                config=config,
                region=region,
                max_sync_bytes=max_sync_bytes,
                max_pages=max_pages,
            )
        ]

    return [
        AwsTextractAnalyzeDocumentAdapter(
            config=config,
            region=region,
            max_sync_bytes=max_sync_bytes,
            feature_types=_config_value(config, 'DOCUMENT_AWS_TEXTRACT_FEATURE_TYPES', DEFAULT_TEXTRACT_FEATURE_TYPES),
            max_pages=max_pages,
        )
    ]


def reverse_geocode_position(config, *, latitude, longitude, client=None):
    if not _config_bool(config, 'DOCUMENT_AWS_ENABLED'):
        return None
    if not _config_bool(config, 'DOCUMENT_AWS_LOCATION_ENABLED'):
        return None
    index_name = _config_value(config, 'DOCUMENT_AWS_LOCATION_PLACE_INDEX', None)
    if not index_name:
        return None

    location_client = client or _boto3_client(
        'location',
        config=config,
        region=_config_value(config, 'DOCUMENT_AWS_REGION', DEFAULT_REGION),
    )
    response = _call_provider(
        lambda: location_client.search_place_index_for_position(
            IndexName=index_name,
            Position=[float(longitude), float(latitude)],
            MaxResults=1,
            Language=_config_value(config, 'DOCUMENT_AWS_LOCATION_LANGUAGE', DEFAULT_LOCATION_LANGUAGE),
        )
    )
    results = response.get('Results') or []
    if not results:
        return None
    first = results[0] or {}
    place = first.get('Place') or {}
    return {
        'provider': 'aws-location',
        'address': str(place.get('Label') or '').strip() or None,
        'distance_m': first.get('Distance'),
        'place': {
            'municipality': place.get('Municipality'),
            'region': place.get('Region'),
            'country': place.get('Country'),
        },
    }


def _boto3_client(service_name, *, config=None, region=DEFAULT_REGION):
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except Exception as exc:  # pragma: no cover - exercised only when dependency missing
        raise ProviderError('boto3 and botocore are required for AWS document compliance providers.') from exc

    profile_name = _config_value(config, 'DOCUMENT_AWS_PROFILE_NAME', None)
    session_kwargs = {'region_name': region or DEFAULT_REGION}
    if profile_name:
        session_kwargs['profile_name'] = profile_name
    session = boto3.session.Session(**session_kwargs)
    return session.client(
        service_name,
        config=BotoConfig(
            connect_timeout=int(_config_value(config, 'DOCUMENT_AWS_CONNECT_TIMEOUT_SECONDS', 5)),
            read_timeout=int(_config_value(config, 'DOCUMENT_AWS_READ_TIMEOUT_SECONDS', 20)),
            retries={'max_attempts': int(_config_value(config, 'DOCUMENT_AWS_MAX_ATTEMPTS', 2))},
        ),
    )


def _extract_document_pages(file_path, *, max_bytes, max_pages=None):
    raw_bytes = _read_document_bytes(file_path, max_bytes=max_bytes)
    path = Path(file_path)
    if not (raw_bytes.startswith(b'%PDF') or path.suffix.lower() == '.pdf'):
        return [(1, raw_bytes)], 1

    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(io.BytesIO(raw_bytes))
        total_pages = len(reader.pages)
        if total_pages <= 1:
            return [(1, raw_bytes)], total_pages

        limit = total_pages if max_pages is None else min(total_pages, max(int(max_pages), 1))
        pages = []
        for idx in range(limit):
            writer = PdfWriter()
            writer.add_page(reader.pages[idx])
            buf = io.BytesIO()
            writer.write(buf)
            pages.append((idx + 1, buf.getvalue()))
        return pages, total_pages
    except Exception:
        return [(1, raw_bytes)], 1


def _read_document_bytes(file_path, *, max_bytes):
    path = Path(file_path)
    size = path.stat().st_size
    if size > max_bytes:
        raise ProviderError(
            f'AWS synchronous analysis supports files up to {max_bytes} bytes in this COMET configuration; '
            f'this file is {size} bytes.'
        )
    return path.read_bytes()


def _call_provider(callback):
    try:
        return callback()
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(str(exc)[:300]) from exc


def _average_confidence(value):
    values = list(_confidence_values(value))
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _extract_textract_forms(blocks):
    block_map = {b.get('Id'): b for b in blocks if b.get('Id')}
    forms = {}
    for b in blocks:
        if b.get('BlockType') == 'KEY_VALUE_SET' and 'KEY' in (b.get('EntityTypes') or []):
            key_text = _get_relationship_text(b, block_map)
            val_text = ''
            val_conf = float(b.get('Confidence') or 100.0)
            for rel in b.get('Relationships') or []:
                if rel.get('Type') == 'VALUE':
                    for val_id in rel.get('Ids') or []:
                        val_block = block_map.get(val_id)
                        if val_block:
                            val_text = _get_relationship_text(val_block, block_map)
                            if val_block.get('Confidence') is not None:
                                val_conf = min(val_conf, float(val_block['Confidence']))
            if key_text and val_text:
                forms[key_text.strip().lower()] = {
                    'value': val_text.strip(),
                    'confidence': round(val_conf / 100.0, 4),
                }
    return forms


def _get_relationship_text(block, block_map):
    words = []
    for rel in block.get('Relationships') or []:
        if rel.get('Type') == 'CHILD':
            for child_id in rel.get('Ids') or []:
                child = block_map.get(child_id)
                if child and child.get('BlockType') == 'WORD' and child.get('Text'):
                    words.append(child['Text'])
    return ' '.join(words)


def _extract_expense_forms(documents):
    forms = {}
    for doc in documents:
        for field in doc.get('SummaryFields') or []:
            ftype = (field.get('Type') or {}).get('Text', '').strip().lower()
            fval = (field.get('ValueDetection') or {}).get('Text', '').strip()
            fconf = float((field.get('ValueDetection') or {}).get('Confidence') or 100.0)
            if ftype and fval:
                forms[ftype] = {
                    'value': fval,
                    'confidence': round(fconf / 100.0, 4),
                }
    return forms


def _confidence_values(value):
    if isinstance(value, dict):
        confidence = value.get('Confidence')
        if isinstance(confidence, (int, float)):
            yield float(confidence)
        for child in value.values():
            yield from _confidence_values(child)
    elif isinstance(value, list):
        for item in value:
            yield from _confidence_values(item)


def _count_blocks(blocks, block_type):
    return sum(1 for block in blocks if block.get('BlockType') == block_type)


def _label_summary(label):
    return {
        'name': str(label.get('Name') or ''),
        'confidence': round(float(label.get('Confidence') or 0), 2),
        'categories': [
            str(category.get('Name') or '')
            for category in (label.get('Categories') or [])
            if category.get('Name')
        ],
    }


def _config_bool(config, key, *, default=False):
    value = _config_value(config, key, default)
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _config_value(config, key, default=None):
    if config is None:
        return default
    try:
        value = config.get(key, default)
    except AttributeError:
        value = default
    return default if value in (None, '') else value


__all__ = [
    'AwsTextractAnalyzeDocumentAdapter',
    'AwsTextractAnalyzeExpenseAdapter',
    'AwsRekognitionAdapter',
    'configured_adapters',
    'is_supported_textract_format',
    'reverse_geocode_position',
]
