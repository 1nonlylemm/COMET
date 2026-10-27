"""PDF rendering utilities and security-hardened resource fetcher for WeasyPrint."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Callable, Sequence
import urllib.parse
import urllib.request

from flask import current_app


class RestrictedResourceError(ValueError):
    """Raised when a URL or file resource requested during PDF generation is disallowed."""


ALLOWED_DATA_MIME_TYPES = frozenset({
    'image/png',
    'image/jpeg',
    'image/jpg',
    'image/webp',
})

PROHIBITED_SCHEMES = frozenset({
    'http',
    'https',
    'ftp',
    'ftps',
    'gopher',
    'dict',
    'ldap',
    'ldaps',
    'php',
    'phar',
    'expect',
    'javascript',
})


def _get_default_allowed_roots() -> list[Path]:
    """Return the list of directory paths that PDF rendering is permitted to read from."""
    roots: list[Path] = []
    try:
        app_root = Path(current_app.root_path).resolve()
        roots.append((app_root / 'static').resolve())
        roots.append((app_root / 'templates').resolve())
    except Exception:
        # Outside Flask application context (e.g., unit test or standalone script)
        pkg_root = Path(__file__).resolve().parent.parent
        roots.append((pkg_root / 'static').resolve())
        roots.append((pkg_root / 'templates').resolve())
    return roots


def safe_weasyprint_url_fetcher(
    url: str,
    *args: Any,
    allowed_roots: Sequence[str | Path] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Secure URL fetcher for WeasyPrint to eliminate SSRF and local file inclusion (LFI).

    Rules:
    1. Network schemes (http, https, ftp, etc.) and network destinations (netloc) are strictly blocked.
    2. Data URIs are permitted only for safe raster image formats (PNG, JPEG, WEBP).
    3. File paths (file:// or relative paths) are strictly restricted to approved local roots
       (app/static and app/templates by default). Local paths outside these roots are blocked.
    """
    if not url or not isinstance(url, str):
        raise RestrictedResourceError("Empty or invalid URL provided to PDF fetcher.")

    url_str = url.strip()

    # Handle data: URIs
    if url_str.startswith('data:'):
        payload = url_str[5:]
        if ',' not in payload:
            raise RestrictedResourceError("Malformed data: URL in PDF rendering.")
        meta, raw_data = payload.split(',', 1)
        parts = meta.split(';')
        mime_type = parts[0].strip().lower() if parts[0].strip() else 'text/plain'
        is_base64 = any(p.strip().lower() == 'base64' for p in parts[1:])

        if mime_type not in ALLOWED_DATA_MIME_TYPES:
            raise RestrictedResourceError(
                f"Data URL with MIME type '{mime_type}' is prohibited during PDF rendering."
            )

        if is_base64:
            try:
                content = base64.b64decode(raw_data)
            except Exception as exc:
                raise RestrictedResourceError(f"Failed to decode base64 data URL: {exc}") from exc
        else:
            content = urllib.parse.unquote_to_bytes(raw_data)

        return {
            'string': content,
            'mime_type': mime_type,
        }

    parsed = urllib.parse.urlparse(url_str)
    scheme = parsed.scheme.lower()

    # Block prohibited network schemes
    if scheme in PROHIBITED_SCHEMES:
        raise RestrictedResourceError(
            f"Network resource access via '{scheme}://' is prohibited during PDF rendering: {url_str}"
        )

    # Block any network host/destination even if scheme was omitted (e.g., //169.254.169.254)
    if parsed.netloc:
        raise RestrictedResourceError(
            f"Remote network host access to '{parsed.netloc}' is prohibited during PDF rendering."
        )

    # Handle file path resolution
    if scheme == 'file':
        raw_path = urllib.request.url2pathname(parsed.path)
    elif len(scheme) == 1 and scheme.isalpha():
        # Windows drive letter parsed as scheme, e.g., 'C:\path\to\file'
        raw_path = url_str
    elif scheme == '':
        # Relative or local filesystem path
        raw_path = parsed.path or url_str
    else:
        raise RestrictedResourceError(f"Prohibited URL scheme '{scheme}' during PDF rendering.")

    file_path = Path(raw_path)
    if not file_path.is_absolute():
        try:
            base_dir = Path(current_app.root_path).resolve()
        except Exception:
            base_dir = Path(__file__).resolve().parent.parent
        resolved_path = (base_dir / file_path).resolve()
    else:
        resolved_path = file_path.resolve()

    # Determine permitted roots
    if allowed_roots is not None:
        valid_roots = [Path(r).resolve() for r in allowed_roots]
    else:
        valid_roots = _get_default_allowed_roots()

    # Verify candidate path is inside one of the allowed roots
    is_safe = any(
        resolved_path == root or root in resolved_path.parents
        for root in valid_roots
    )

    if not is_safe:
        raise RestrictedResourceError(
            f"Access to local file outside approved directories is prohibited: {url_str}"
        )

    if not resolved_path.exists() or not resolved_path.is_file():
        raise FileNotFoundError(f"PDF asset file not found: {resolved_path}")

    mime_type, _ = mimetypes.guess_type(str(resolved_path))
    content = resolved_path.read_bytes()

    return {
        'string': content,
        'mime_type': mime_type or 'application/octet-stream',
    }
