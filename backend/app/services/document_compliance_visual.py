"""Phase-1 visual evidence analysis for the documentary compliance checker.

Implements the §8 phase-1 visual checks (image quality, blank/blur, darkness,
low-resolution, page completeness) using Pillow only. The module is deliberately
narrow: it never raises out, never calls external services, and returns ``None``
when the input is not image-derived so the rule engine and existing extractor
keep their old fast paths unchanged.

Phases 2–4 from §8 (signature/stamp/seal/logo detection, scene/object detection,
project-context comparison) are out of scope for this module.
"""

from __future__ import annotations

from pathlib import Path


_IMAGE_MIME_PREFIX = 'image/'
_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'}

# Threshold tuning — all derived from a 0..255 grayscale scale.
# Increasing or decreasing any of these counts as a behavior-affecting change
# and should bump POLICY_VERSION in the rule engine.
_BLANK_STDDEV_THRESHOLD = 4.0
_LOW_QUALITY_STDDEV_THRESHOLD = 12.0
_DARKNESS_THRESHOLD = 35.0      # mean luminance below this is "dark"
_BLUR_VARIANCE_THRESHOLD = 25.0  # neighbor-difference variance below this is "blurry"
_LOW_RESOLUTION_PIXEL_FLOOR = 200_000  # ~ 500x400 px


def analyze_visual_evidence(extraction, *, mime_type, file_path):
    """Return the §8 phase-1 visual summary, or ``None`` to skip.

    Args:
        extraction: The dict returned by ``document_intelligence_service.extract_document_text``.
            The analyzer reads ``extraction['metadata']['extractors']`` to detect
            OCR-derived input when MIME type is unhelpful.
        mime_type: The submission file's MIME type, when known.
        file_path: A filesystem :class:`~pathlib.Path` to the file to analyze.

    Returns:
        Dict with the keys documented in §8 (``image_quality``, ``blank_or_near_blank``,
        ``low_resolution``, ``blur_score``, ``darkness_score``, ``notes``), or ``None``
        when the file is not image-derived.

    The function never raises. Pillow load failures degrade to a
    ``image_quality == 'unreadable'`` summary so the service can emit a
    deterministic blocker finding.
    """
    if not _is_image_like(extraction, mime_type=mime_type, file_path=file_path):
        return None
    image = _open_image(file_path)
    if image is None:
        return {
            'image_quality': 'unreadable',
            'blank_or_near_blank': True,
            'low_resolution': True,
            'blur_score': 0.0,
            'darkness_score': 0.0,
            'notes': ['Visual analysis could not load the image.'],
        }
    try:
        return _measure_image(image)
    finally:
        try:
            image.close()
        except Exception:
            pass


def _is_image_like(extraction, *, mime_type, file_path):
    if mime_type and str(mime_type).lower().startswith(_IMAGE_MIME_PREFIX):
        return True
    if file_path is not None:
        try:
            suffix = Path(file_path).suffix.lower()
        except (TypeError, ValueError):
            suffix = ''
        if suffix in _IMAGE_EXTENSIONS:
            return True
    metadata = (extraction or {}).get('metadata') or {}
    extractors = metadata.get('extractors') or []
    if extractors and all(name == 'tesseract' for name in extractors):
        return True
    return False


def _open_image(file_path):
    if file_path is None:
        return None
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        path = Path(file_path)
    except (TypeError, ValueError):
        return None
    if not path.exists():
        return None
    try:
        image = Image.open(path)
        image.load()
        return image
    except Exception:
        return None


def _measure_image(image):
    width, height = image.size
    pixel_count = max(1, int(width) * int(height))
    grayscale = image.convert('L') if image.mode != 'L' else image

    histogram = grayscale.histogram()
    total = sum(histogram) or 1
    mean = sum(index * count for index, count in enumerate(histogram)) / total
    variance = sum(((index - mean) ** 2) * count for index, count in enumerate(histogram)) / total
    stddev = variance ** 0.5

    blur_score = _estimate_blur(grayscale)
    notes = []

    blank = stddev <= _BLANK_STDDEV_THRESHOLD
    low_resolution = pixel_count < _LOW_RESOLUTION_PIXEL_FLOOR

    if blank:
        notes.append('Image is blank or near-blank (very low contrast).')
    elif stddev <= _LOW_QUALITY_STDDEV_THRESHOLD:
        notes.append('Image has low contrast; may be hard to read.')

    if mean < _DARKNESS_THRESHOLD:
        notes.append('Image is unusually dark; review the scan exposure.')

    if blur_score < _BLUR_VARIANCE_THRESHOLD:
        notes.append('Image looks blurry; reviewer should request a sharper scan.')

    if low_resolution:
        notes.append(f'Image resolution is low ({width}x{height} px).')

    if blank:
        image_quality = 'unreadable'
    elif (
        stddev <= _LOW_QUALITY_STDDEV_THRESHOLD
        or mean < _DARKNESS_THRESHOLD
        or blur_score < _BLUR_VARIANCE_THRESHOLD
        or low_resolution
    ):
        image_quality = 'low_quality'
    else:
        image_quality = 'acceptable'

    return {
        'image_quality': image_quality,
        'blank_or_near_blank': bool(blank),
        'low_resolution': bool(low_resolution),
        'blur_score': round(float(blur_score), 2),
        'darkness_score': round(float(mean), 2),
        'contrast_stddev': round(float(stddev), 2),
        'notes': notes,
    }


def _estimate_blur(grayscale):
    """Cheap blur proxy.

    True Laplacian variance would need NumPy; instead we sample neighboring
    pixels along a scaled-down image and compute variance of differences. This
    is sufficient to distinguish acceptably sharp scans from severely blurred
    ones, which is all phase 1 needs.
    """
    width, height = grayscale.size
    long_edge = max(width, height)
    target = 256 if long_edge > 256 else long_edge
    if long_edge == 0:
        return 0.0
    if target != long_edge:
        scale = target / long_edge
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        try:
            from PIL import Image
            resample = Image.Resampling.BILINEAR
        except Exception:
            resample = 2  # PIL.Image.BILINEAR fallback
        try:
            sample = grayscale.resize(new_size, resample=resample)
        except Exception:
            return 0.0
    else:
        sample = grayscale

    pixels = sample.load()
    sample_width, sample_height = sample.size
    if sample_width < 2 or sample_height < 2:
        return 0.0

    diffs = []
    step = max(1, sample_width // 64)
    for y in range(0, sample_height - 1, step):
        for x in range(0, sample_width - 1, step):
            here = pixels[x, y]
            right = pixels[x + 1, y]
            below = pixels[x, y + 1]
            diffs.append(here - right)
            diffs.append(here - below)

    if not diffs:
        return 0.0
    mean = sum(diffs) / len(diffs)
    variance = sum((value - mean) ** 2 for value in diffs) / len(diffs)
    return variance
