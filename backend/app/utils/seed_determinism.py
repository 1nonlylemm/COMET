"""Centralized Seed Determinism and Stable Artifact Naming Helpers for COMET.

Provides a fixed, frozen UTC reference instant for demonstration dataset seeding
and deterministic, collision-resistant artifact filename generation.
"""

from datetime import date, datetime, timezone
import hashlib
from typing import Optional, Union

# Fixed UTC seed anchor reference instant: CY 2026 Mid-Year Reference Date (June 1, 2026, 00:00:00 UTC)
SEED_REFERENCE_TIME: datetime = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
SEED_REFERENCE_DATE: date = date(2026, 6, 1)


def get_seed_reference_time() -> datetime:
    """Return the fixed UTC reference instant for demonstration dataset seeding."""
    return SEED_REFERENCE_TIME


def get_seed_reference_date() -> date:
    """Return the fixed calendar date for demonstration dataset seeding."""
    return SEED_REFERENCE_DATE


def generate_deterministic_seed_filename(
    project_identifier: Union[str, int, None],
    requirement_identifier: Union[str, int, None],
    version_number: int = 1,
    extension: str = "pdf",
    prefix: str = "seed_",
) -> str:
    """Generate a deterministic, collision-resistant filename for demonstration seed artifacts.

    Derives a stable 32-character hexadecimal SHA-256 hash from:
      - Project code or stable identifier
      - Canonical requirement name or code
      - Version / revision number

    Prefixed with 'seed_' by default to distinguish from runtime user uploads (uuid4-based)
    and guarantee non-collision with user-uploaded files.

    Args:
        project_identifier: Source project code (e.g. 'FALGU-2026-SCRUZ-01') or project ID.
        requirement_identifier: Canonical requirement name or requirement code.
        version_number: 1-indexed version number (e.g. 1, 2).
        extension: File extension without or with leading dot (default 'pdf').
        prefix: Filename prefix (default 'seed_').

    Returns:
        Deterministic filename string (e.g. 'seed_4a9f...b2.pdf').
    """
    clean_proj = str(project_identifier or "").strip()
    clean_req = str(requirement_identifier or "").strip()
    v_num = int(version_number) if version_number else 1
    ext = extension.lstrip(".")

    seed_key = f"{clean_proj}:{clean_req}:v{v_num}"
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}{digest}.{ext}"
