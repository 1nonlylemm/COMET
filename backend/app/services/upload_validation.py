import mimetypes
import os
from pathlib import Path
import zipfile


GENERIC_MIME_TYPES = {'application/octet-stream', 'binary/octet-stream'}

MAX_ARCHIVE_ENTRIES = 500
MAX_MEMBER_UNCOMPRESSED_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_TOTAL_UNCOMPRESSED_BYTES = 60 * 1024 * 1024   # 60 MB
MAX_COMPRESSION_RATIO = 100


from io import BytesIO


class UploadValidationError(ValueError):
    """Raised when an uploaded file fails format, mime-type, or signature constraints."""
    def __init__(self, message, status_code=422):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ArchiveSecurityError(UploadValidationError):
    """Raised when an uploaded archive or OOXML container fails security constraints."""
    pass


MAX_UPLOAD_FILENAME_CHARS = 180
MAX_UPLOAD_FILENAME_BYTES = 200


def validate_upload_filename(filename, error_factory=None, label='File'):
    """Validates and sanitizes an uploaded filename.
    Ensures that the filename is non-empty, contains safe characters, and does not exceed
    the maximum length/byte constraints required for filesystem and storage key safety (NAME_MAX=255).
    """
    def _raise(msg, code=422):
        if error_factory is None:
            raise UploadValidationError(msg, status_code=code)
        try:
            raise error_factory(msg, code)
        except TypeError:
            raise error_factory(msg)

    if not filename or not str(filename).strip():
        _raise(f'{label} is required.')

    raw_str = str(filename).strip()
    # Normalize path separators across OS platforms to strip traversal components
    normalized = raw_str.replace('\\', '/')
    base_name = Path(normalized).name

    # Check length and byte size of raw input
    raw_encoded = raw_str.encode('utf-8', errors='replace')
    if len(raw_str) > MAX_UPLOAD_FILENAME_CHARS or len(raw_encoded) > MAX_UPLOAD_FILENAME_BYTES:
        _raise(
            f'{label} name is too long ({len(raw_str)} characters). Maximum allowed length is {MAX_UPLOAD_FILENAME_CHARS} characters or {MAX_UPLOAD_FILENAME_BYTES} bytes.'
        )

    from werkzeug.utils import secure_filename
    sanitized = secure_filename(base_name)
    if not sanitized:
        _raise(f'{label} name is invalid.')

    encoded = sanitized.encode('utf-8', errors='replace')
    if len(sanitized) > MAX_UPLOAD_FILENAME_CHARS or len(encoded) > MAX_UPLOAD_FILENAME_BYTES:
        _raise(
            f'{label} name is too long ({len(sanitized)} characters). Maximum allowed length is {MAX_UPLOAD_FILENAME_CHARS} characters.'
        )

    return sanitized


def _measure_upload_size(upload):
    if upload is None:
        return 0
    if isinstance(upload, (bytes, bytearray)):
        return len(upload)
    content_length = getattr(upload, 'content_length', None)
    if content_length is not None and int(content_length) > 0:
        return int(content_length)

    stream = getattr(upload, 'stream', None)
    if stream is None:
        if hasattr(upload, 'seek') and hasattr(upload, 'tell'):
            stream = upload
        else:
            return 0

    try:
        position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size_bytes = stream.tell()
        stream.seek(position)
        return int(size_bytes)
    except (AttributeError, OSError):
        return 0


def validate_ooxml_container(file_or_path, expected_kind='any'):
    """Validates that an OOXML archive (DOCX/XLSX/PPTX) is structurally sound, safe from decompression bombs,
    does not contain path traversal member names, and contains the required internal structure.
    """
    archive = None
    close_archive = False
    try:
        if isinstance(file_or_path, (bytes, bytearray)):
            archive = zipfile.ZipFile(BytesIO(file_or_path), 'r')
            close_archive = True
        elif isinstance(file_or_path, (str, Path)):
            archive = zipfile.ZipFile(str(file_or_path), 'r')
            close_archive = True
        elif hasattr(file_or_path, 'read') and hasattr(file_or_path, 'seek'):
            pos = file_or_path.tell()
            file_or_path.seek(0)
            archive = zipfile.ZipFile(file_or_path, 'r')
            close_archive = True
        elif hasattr(file_or_path, 'stream') and hasattr(file_or_path.stream, 'read') and hasattr(file_or_path.stream, 'seek'):
            pos = file_or_path.stream.tell()
            file_or_path.stream.seek(0)
            archive = zipfile.ZipFile(file_or_path.stream, 'r')
            close_archive = True
        else:
            raise ArchiveSecurityError('Invalid input provided for archive validation.')

        infolist = archive.infolist()
        if not infolist:
            raise ArchiveSecurityError('Archive contains no files.')

        if len(infolist) > MAX_ARCHIVE_ENTRIES:
            raise ArchiveSecurityError(f'Archive exceeds maximum member count ({len(infolist)} > {MAX_ARCHIVE_ENTRIES}).')

        total_uncompressed = 0
        names = set()

        for info in infolist:
            normalized_name = info.filename.replace('\\', '/')
            parts = [p for p in normalized_name.split('/') if p]
            if '..' in parts or normalized_name.startswith('/') or (len(parts) > 0 and ':' in parts[0]):
                raise ArchiveSecurityError(f'Archive contains illegal entry path: {info.filename}')

            if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                raise ArchiveSecurityError(f'Archive member {info.filename} exceeds maximum size limit.')

            total_uncompressed += info.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise ArchiveSecurityError('Total uncompressed archive size exceeds safety threshold.')

            if info.compress_size > 0 and info.file_size > 1024:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_COMPRESSION_RATIO:
                    raise ArchiveSecurityError(f'Archive member {info.filename} exceeds compression ratio limit ({ratio:.1f}:1).')

            names.add(normalized_name)

        if '[Content_Types].xml' not in names:
            raise ArchiveSecurityError('Archive is missing required OOXML [Content_Types].xml manifest.')

        if expected_kind == 'docx':
            if not any(n.startswith('word/') for n in names) and 'word/document.xml' not in names:
                raise ArchiveSecurityError('Archive does not contain Word document structures.')
        elif expected_kind == 'xlsx':
            if not any(n.startswith('xl/') for n in names) and 'xl/workbook.xml' not in names:
                raise ArchiveSecurityError('Archive does not contain Excel workbook structures.')
        elif expected_kind == 'pptx':
            if not any(n.startswith('ppt/') for n in names):
                raise ArchiveSecurityError('Archive does not contain PowerPoint structures.')

        return True
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as exc:
        raise ArchiveSecurityError(f'Corrupt or unreadable archive: {exc}') from exc
    finally:
        if archive and close_archive:
            try:
                archive.close()
            except Exception:
                pass
        if hasattr(file_or_path, 'seek'):
            try:
                file_or_path.seek(0)
            except Exception:
                pass
        elif hasattr(file_or_path, 'stream') and hasattr(file_or_path.stream, 'seek'):
            try:
                file_or_path.stream.seek(0)
            except Exception:
                pass


OOXML_MIME_BY_EXTENSION = {
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}

OLE_MIME_BY_EXTENSION = {
    'doc': 'application/msword',
    'xls': 'application/vnd.ms-excel',
    'ppt': 'application/vnd.ms-powerpoint',
}

MIME_TYPES_BY_EXTENSION = {
    'pdf': {'application/pdf'},
    'doc': {'application/msword'},
    'docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
    'xls': {'application/vnd.ms-excel'},
    'xlsx': {'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},
    'ppt': {'application/vnd.ms-powerpoint'},
    'pptx': {'application/vnd.openxmlformats-officedocument.presentationml.presentation'},
    'jpg': {'image/jpeg'},
    'jpeg': {'image/jpeg'},
    'png': {'image/png'},
    'webp': {'image/webp'},
    'svg': {'image/svg+xml'},
    'csv': {'text/csv'},
}


def resolve_upload_mime_type(filename, upload, allowed_mime_types, error_factory=None, label='File'):
    if error_factory is None:
        error_factory = lambda msg: UploadValidationError(msg)

    allowed = {
        str(mime_type).strip().lower()
        for mime_type in (allowed_mime_types or ())
        if str(mime_type).strip()
    }

    # Reject 0-byte uploads
    size = _measure_upload_size(upload)
    if size == 0:
        raise error_factory(f'{label} is empty (0 bytes).')

    guessed_mime_type = (mimetypes.guess_type(filename)[0] or '').lower()
    provided_mime_type = (getattr(upload, 'mimetype', None) or '').lower()
    sniffed_mime_type = sniff_upload_mime_type(filename, upload)
    expected_for_extension = MIME_TYPES_BY_EXTENSION.get(Path(filename).suffix.lower().lstrip('.'), set())

    if not allowed:
        return sniffed_mime_type or provided_mime_type or guessed_mime_type or 'application/octet-stream'

    if sniffed_mime_type:
        actual_extension = Path(filename).suffix.lower().lstrip('.')
        if expected_for_extension and sniffed_mime_type not in expected_for_extension:
            raise error_factory(f'{label} content does not match the file extension.')
        valid_exts_for_sniffed = {
            ext for ext, mimes in MIME_TYPES_BY_EXTENSION.items() if sniffed_mime_type in mimes
        }
        if valid_exts_for_sniffed and actual_extension not in valid_exts_for_sniffed:
            raise error_factory(f'{label} content does not match the file extension.')
        if sniffed_mime_type in allowed:
            return sniffed_mime_type
        raise error_factory(f'{label} content does not match an allowed file type.')

    # If content could not be verified by sniffing and the extension requires a verifiable format, do not trust client header
    if expected_for_extension and expected_for_extension.issubset({
        'application/pdf',
        'image/png',
        'image/jpeg',
        'image/webp',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/msword',
        'application/vnd.ms-excel',
        'application/vnd.ms-powerpoint',
    }):
        raise error_factory(f'{label} content does not match the file extension.')

    if provided_mime_type and provided_mime_type not in GENERIC_MIME_TYPES and provided_mime_type not in allowed:
        raise error_factory(f'{label} MIME type is not allowed.')
    if provided_mime_type in allowed:
        return provided_mime_type
    if guessed_mime_type in allowed:
        return guessed_mime_type

    raise error_factory(f'{label} MIME type is not allowed.')


def sniff_upload_mime_type(filename, upload):
    header = _read_upload_prefix(upload)
    if not header:
        return None

    extension = Path(filename).suffix.lower().lstrip('.')
    if header.startswith(b'%PDF-'):
        return 'application/pdf'
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if header.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if header.startswith(b'RIFF') and header[8:12] == b'WEBP':
        return 'image/webp'
    if header.startswith((b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08')):
        if extension in ('docx', 'xlsx', 'pptx'):
            try:
                validate_ooxml_container(upload, expected_kind=extension)
                return OOXML_MIME_BY_EXTENSION.get(extension, 'application/zip')
            except ArchiveSecurityError:
                return 'application/octet-stream'
        return OOXML_MIME_BY_EXTENSION.get(extension, 'application/zip')
    if header.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return OLE_MIME_BY_EXTENSION.get(extension, 'application/x-ole-storage')
    if extension == 'svg' and _looks_like_svg(header):
        return 'image/svg+xml'
    if extension == 'csv' and _looks_like_text(header):
        return 'text/csv'
    if _looks_like_text(header):
        return 'text/plain'
    return 'application/octet-stream'


def _read_upload_prefix(upload, size=4096):
    if isinstance(upload, (bytes, bytearray)):
        return bytes(upload[:size])
    stream = getattr(upload, 'stream', None)
    if stream is None:
        if hasattr(upload, 'read') and hasattr(upload, 'seek'):
            stream = upload
        else:
            return b''

    try:
        position = stream.tell()
    except (AttributeError, OSError):
        position = None

    try:
        header = stream.read(size)
    finally:
        try:
            if position is not None:
                stream.seek(position)
            else:
                stream.seek(0, os.SEEK_SET)
        except (AttributeError, OSError):
            pass
    return header or b''


def _looks_like_text(header):
    if b'\x00' in header:
        return False
    try:
        header.decode('utf-8')
        return True
    except UnicodeDecodeError:
        return False


def _looks_like_svg(header):
    if not _looks_like_text(header):
        return False
    text = header.decode('utf-8', errors='ignore').lstrip().lower()
    return text.startswith('<svg') or (text.startswith('<?xml') and '<svg' in text[:500])
