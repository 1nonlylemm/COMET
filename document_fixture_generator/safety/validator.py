"""Path boundary and safety validation to protect repository evaluation assets.

Enforces strict fail-closed export isolation: fixtures may only be written to
explicitly approved staging root directories and never to core application, test,
or frozen benchmark trees. Parent-prefix paths and unapproved subtrees are rejected.
"""

from __future__ import annotations

import os
from pathlib import Path


class SecurityViolationError(PermissionError):
    """Raised when an operation attempts to write to a protected or unapproved path."""


class SecurityValidator:
    """Validates export paths and file operations against isolation boundaries."""

    # Disallowed directories across the entire repository tree (normalized lowercase)
    PROTECTED_SEGMENTS = frozenset({
        "backend",
        "frontend",
        "docs",
        "others",
        "tests",
        ".git",
        ".github",
    })

    # Strictly authorized staging roots relative to project root.
    # Note: Parent prefixes (e.g. 'artifacts', 'artifacts/fixtures') are strictly forbidden.
    APPROVED_STAGING_PREFIXES = (
        ("artifacts", "fixtures", "staging"),
        ("artifacts", "fixtures", "export_staging"),
    )

    @classmethod
    def get_project_root(cls) -> Path:
        """Derive repository root by ascending from this package."""
        return Path(__file__).resolve().parent.parent.parent

    @classmethod
    def assert_safe_export_target(cls, target_path: str | Path) -> Path:
        """Validate that target_path is within an authorized staging directory.

        Fails closed with SecurityViolationError if the path touches any protected directory,
        targets parent-prefix paths, escapes the repository, or falls outside approved staging roots.
        """
        if not target_path or not str(target_path).strip():
            raise SecurityViolationError("Export path cannot be empty.")

        # Fully resolve symlinks, junctions, and relative segments to canonical absolute path
        resolved_path = Path(target_path).resolve()
        project_root = cls.get_project_root().resolve()

        # Target must be strictly within the repository workspace
        try:
            rel_parts = resolved_path.relative_to(project_root).parts
        except ValueError:
            raise SecurityViolationError(
                f"Export path '{resolved_path}' is outside the repository workspace '{project_root}'."
            )

        if not rel_parts:
            raise SecurityViolationError("Exporting directly to workspace root is prohibited.")

        # Prohibit any path that touches any protected directory segment anywhere in its path
        for part in rel_parts:
            if part.lower() in cls.PROTECTED_SEGMENTS:
                raise SecurityViolationError(
                    f"Exporting to path containing protected directory segment '{part}' is strictly prohibited. "
                    "Fixtures must only be written to approved staging roots: "
                    f"{['/'.join(p) for p in cls.APPROVED_STAGING_PREFIXES]}."
                )

        # Check if target is strictly within one of the approved staging root trees
        is_approved = False
        for prefix in cls.APPROVED_STAGING_PREFIXES:
            prefix_len = len(prefix)
            if len(rel_parts) >= prefix_len and tuple(p.lower() for p in rel_parts[:prefix_len]) == prefix:
                is_approved = True
                break

        if not is_approved:
            raise SecurityViolationError(
                f"Export path '{resolved_path}' does not match any explicitly approved staging root: "
                f"{['/'.join(p) for p in cls.APPROVED_STAGING_PREFIXES]}. "
                "Parent prefixes and unapproved directories are prohibited."
            )

        return resolved_path
