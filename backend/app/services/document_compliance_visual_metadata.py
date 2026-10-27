"""EXIF/photo metadata extraction for visual documentary evidence.

The compliance checker uses this as advisory context only. Missing or stripped
EXIF data is common for photos sent through messaging apps, so this module
returns notes instead of raising findings by itself.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


_IMAGE_MIME_PREFIX = 'image/'
_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}

_TAG_MAKE = 271
_TAG_MODEL = 272
_TAG_ORIENTATION = 274
_TAG_DATETIME = 306
_TAG_SOFTWARE = 305
_TAG_DATETIME_ORIGINAL = 36867
_TAG_DATETIME_DIGITIZED = 36868
_TAG_GPS_INFO = 34853

_GPS_LATITUDE_REF = 1
_GPS_LATITUDE = 2
_GPS_LONGITUDE_REF = 3
_GPS_LONGITUDE = 4
_GPS_ALTITUDE_REF = 5
_GPS_ALTITUDE = 6
_GPS_TIME_STAMP = 7
_GPS_IMG_DIRECTION_REF = 16
_GPS_IMG_DIRECTION = 17
_GPS_DATE_STAMP = 29


def extract_photo_metadata(file_path, *, mime_type=None, reverse_geocoder=None):
    """Return useful embedded photo metadata for image evidence, or ``None``.

    ``reverse_geocoder`` is an optional callable accepting ``(latitude,
    longitude)`` and returning a dict like ``{'address': '...', 'provider':
    'aws-location'}``. It is injected so AWS/network behavior remains outside
    the local EXIF parser.
    """
    if not _is_image_like(mime_type=mime_type, file_path=file_path):
        return None

    image = _open_image(file_path)
    if image is None:
        return {
            'metadata_available': False,
            'captured_at': None,
            'captured_at_source': None,
            'camera': {},
            'image': {},
            'gps': None,
            'notes': ['Photo metadata could not be read because the image could not be opened.'],
        }

    try:
        width, height = image.size
        exif = _get_exif(image)
        gps_ifd = _get_gps_ifd(exif)
        captured_at, captured_at_source = _captured_at(exif)
        gps = _gps_payload(gps_ifd, reverse_geocoder=reverse_geocoder)
        camera = _camera_payload(exif)
        notes = _metadata_notes(exif, captured_at, gps)
        return {
            'metadata_available': bool(exif),
            'captured_at': captured_at,
            'captured_at_source': captured_at_source,
            'camera': camera,
            'image': {
                'width': int(width),
                'height': int(height),
                'orientation': _clean_int(_exif_get(exif, _TAG_ORIENTATION)),
            },
            'gps': gps,
            'notes': notes,
        }
    finally:
        try:
            image.close()
        except Exception:
            pass


def _is_image_like(*, mime_type, file_path):
    if mime_type and str(mime_type).lower().startswith(_IMAGE_MIME_PREFIX):
        return True
    if file_path is None:
        return False
    try:
        return Path(file_path).suffix.lower() in _IMAGE_EXTENSIONS
    except (TypeError, ValueError):
        return False


def _open_image(file_path):
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


def _get_exif(image):
    try:
        exif = image.getexif()
    except Exception:
        return {}
    return exif or {}


def _get_gps_ifd(exif):
    if not exif:
        return {}
    try:
        gps = exif.get_ifd(_TAG_GPS_INFO)
        if gps:
            return gps
    except Exception:
        pass
    gps = _exif_get(exif, _TAG_GPS_INFO)
    return gps if isinstance(gps, dict) else {}


def _captured_at(exif):
    candidates = (
        (_TAG_DATETIME_ORIGINAL, 'EXIF DateTimeOriginal'),
        (_TAG_DATETIME_DIGITIZED, 'EXIF DateTimeDigitized'),
        (_TAG_DATETIME, 'EXIF DateTime'),
    )
    for tag, source in candidates:
        parsed = _parse_exif_datetime(_exif_get(exif, tag))
        if parsed:
            return parsed, source
    return None, None


def _camera_payload(exif):
    payload = {}
    for key, tag in (('make', _TAG_MAKE), ('model', _TAG_MODEL), ('software', _TAG_SOFTWARE)):
        value = _clean_text(_exif_get(exif, tag))
        if value:
            payload[key] = value
    return payload


def _gps_payload(gps_ifd, *, reverse_geocoder=None):
    if not gps_ifd:
        return None
    latitude = _dms_to_decimal(_gps_get(gps_ifd, _GPS_LATITUDE), _gps_get(gps_ifd, _GPS_LATITUDE_REF))
    longitude = _dms_to_decimal(_gps_get(gps_ifd, _GPS_LONGITUDE), _gps_get(gps_ifd, _GPS_LONGITUDE_REF))
    if latitude is None or longitude is None:
        return None

    payload = {
        'latitude': round(latitude, 7),
        'longitude': round(longitude, 7),
        'source': 'EXIF GPSInfo',
    }
    altitude = _gps_altitude(gps_ifd)
    if altitude is not None:
        payload['altitude_m'] = round(altitude, 2)
    direction = _ratio_to_float(_gps_get(gps_ifd, _GPS_IMG_DIRECTION))
    if direction is not None:
        payload['image_direction_degrees'] = round(direction, 2)
        direction_ref = _clean_text(_gps_get(gps_ifd, _GPS_IMG_DIRECTION_REF))
        if direction_ref:
            payload['image_direction_ref'] = direction_ref
    timestamp = _gps_timestamp(gps_ifd)
    if timestamp:
        payload['timestamp_utc'] = timestamp

    if reverse_geocoder:
        try:
            resolved = reverse_geocoder(latitude, longitude)
        except Exception as exc:
            payload['reverse_geocode_error'] = str(exc)[:200]
        else:
            _attach_resolved_address(payload, resolved)
    return payload


def _attach_resolved_address(payload, resolved):
    if not isinstance(resolved, dict):
        return
    address = _clean_text(resolved.get('address') or resolved.get('label'))
    if address:
        payload['resolved_address'] = address
        payload['resolved_address_source'] = _clean_text(resolved.get('provider')) or 'reverse_geocoder'
    if resolved.get('distance_m') is not None:
        try:
            payload['resolved_address_distance_m'] = round(float(resolved.get('distance_m')), 2)
        except (TypeError, ValueError):
            pass
    place = resolved.get('place')
    if isinstance(place, dict) and place:
        payload['resolved_place'] = {
            str(key): value
            for key, value in place.items()
            if value not in (None, '')
        }
    error = _clean_text(resolved.get('error'))
    if error and not address:
        payload['reverse_geocode_error'] = error


def _metadata_notes(exif, captured_at, gps):
    notes = []
    if not exif:
        notes.append('No embedded EXIF photo metadata was found; some apps strip capture time and GPS data.')
        return notes
    if not captured_at:
        notes.append('No embedded capture timestamp was found.')
    if not gps:
        notes.append('No embedded GPS coordinates were found.')
    return notes


def _parse_exif_datetime(value):
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ('%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return text


def _gps_timestamp(gps_ifd):
    date_text = _clean_text(_gps_get(gps_ifd, _GPS_DATE_STAMP))
    time_value = _gps_get(gps_ifd, _GPS_TIME_STAMP)
    if not date_text or not time_value or len(time_value) < 3:
        return None
    try:
        hour = int(_ratio_to_float(time_value[0]) or 0)
        minute = int(_ratio_to_float(time_value[1]) or 0)
        second = int(_ratio_to_float(time_value[2]) or 0)
        date_value = datetime.strptime(date_text, '%Y:%m:%d')
        return date_value.replace(hour=hour, minute=minute, second=second).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (TypeError, ValueError):
        return None


def _gps_altitude(gps_ifd):
    altitude = _ratio_to_float(_gps_get(gps_ifd, _GPS_ALTITUDE))
    if altitude is None:
        return None
    try:
        ref = int(_gps_get(gps_ifd, _GPS_ALTITUDE_REF) or 0)
    except (TypeError, ValueError):
        ref = 0
    return -altitude if ref == 1 else altitude


def _dms_to_decimal(value, ref):
    if not value or len(value) < 3:
        return None
    degrees = _ratio_to_float(value[0])
    minutes = _ratio_to_float(value[1])
    seconds = _ratio_to_float(value[2])
    if degrees is None or minutes is None or seconds is None:
        return None
    decimal = degrees + minutes / 60 + seconds / 3600
    ref_text = _clean_text(ref).upper()
    if ref_text.startswith(('S', 'W')):
        decimal *= -1
    return decimal


def _ratio_to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            denominator = float(value[1])
            if denominator == 0:
                return None
            return float(value[0]) / denominator
        except (TypeError, ValueError):
            return None
    return None


def _gps_get(gps_ifd, tag):
    try:
        return gps_ifd.get(tag)
    except AttributeError:
        return None


def _exif_get(exif, tag):
    try:
        return exif.get(tag)
    except AttributeError:
        return None


def _clean_text(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        try:
            value = value.decode('utf-8', errors='ignore')
        except Exception:
            value = str(value)
    return str(value).strip()


def _clean_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
