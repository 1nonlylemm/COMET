"""Seed standard Reference Library DOCX templates.

This script replaces the known office Annex M/N/O notice templates by deleting
existing matching templates and recreating them from the reference assets.
Because it deletes existing template records before recreating them, it requires
explicit destructive reset authorization.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from app import create_app
from app.models import User
from app.services import notice_service, settings_service
from app.utils.seed_safety import validate_seed_database_safety


STANDARD_NOTICE_TEMPLATES = (
    {
        "template_type": "annex_m",
        "label": "Annex M",
        "file_name": "Annex M - Notice of Non-Compliance No. 1.docx",
    },
    {
        "template_type": "annex_n",
        "label": "Annex N",
        "file_name": "Annex N - Notice of Non-Compliance No. 2.docx",
    },
    {
        "template_type": "annex_o",
        "label": "Annex O",
        "file_name": "Annex O - Notice of Non-Compliance No. 3.docx",
    },
)


@dataclass
class LocalTemplateUpload:
    path: Path

    def __post_init__(self):
        self.filename = self.path.name
        self.content_length = self.path.stat().st_size
        self.stream = BytesIO(self.path.read_bytes())

    def save(self, destination):
        self.stream.seek(0)
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with destination_path.open("wb") as target:
            shutil.copyfileobj(self.stream, target)
        self.stream.seek(0)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _candidate_asset_dirs() -> list[Path]:
    candidates = []
    configured = os.environ.get("COMET_REFERENCE_TEMPLATE_SOURCE_DIR")
    if configured:
        candidates.append(Path(configured))

    candidates.append(Path.home() / "Downloads" / "SYSTEM DEMO" / "TEMPLATES")
    candidates.append(
        _repo_root()
        / "others"
        / "reference_data"
        / "COMET Files, Forms, Annexes, and More!"
        / "Omnibus Guidelines Forms Annexes"
    )
    backend_root = Path(__file__).resolve().parent
    candidates.append(backend_root / "seed_assets" / "reference_templates")
    return candidates


def _asset_path(file_name: str) -> Path:
    for asset_dir in _candidate_asset_dirs():
        candidate = asset_dir / file_name
        if candidate.exists() and candidate.is_file():
            return candidate
    searched = ", ".join(str(path) for path in _candidate_asset_dirs())
    raise FileNotFoundError(f"Missing standard template asset {file_name!r}; searched: {searched}")


def _generated_asset_path(template_type: str, file_name: str) -> Path:
    target_dir = Path(__file__).resolve().parent / "seed_assets" / "reference_templates"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_name
    if target_path.exists() and target_path.is_file():
        return target_path

    builder = {
        "annex_m": notice_service._build_annex_m_docx_template,
        "annex_n": notice_service._build_annex_n_docx_template,
        "annex_o": notice_service._build_annex_o_docx_template,
    }.get(template_type)
    if not builder:
        raise RuntimeError(f"No standard DOCX builder is available for {template_type}.")
    builder(target_path)
    return target_path


def _template_source_path(template_type: str, file_name: str) -> tuple[Path, str]:
    try:
        return _asset_path(file_name), "asset"
    except FileNotFoundError:
        return _generated_asset_path(template_type, file_name), "generated"


def _seed_user_id(preferred_email: str = "padmin@dilgpdmu.tech") -> int:
    preferred = User.query.filter_by(email=preferred_email).first()
    if preferred:
        return int(preferred.id)
    admin = User.query.filter_by(role="admin").order_by(User.id.asc()).first()
    if admin:
        return int(admin.id)
    raise RuntimeError("Cannot seed templates because no admin user exists.")


def _existing_standard_templates(file_name: str, label: str) -> list[tuple[str, str]]:
    groups = settings_service.list_document_templates()
    matches = []
    for group in groups:
        template_type = group.get("template_type")
        for template in group.get("templates") or []:
            if template.get("file_name") == file_name or template.get("label") == label:
                template_id = template.get("id")
                if template_type and template_id:
                    matches.append((template_type, template_id))
    return matches


def seed_reference_templates(user_email: str = "padmin@dilgpdmu.tech") -> list[dict]:
    """Refresh the standard notice templates and return a compact summary."""
    validate_seed_database_safety(operation="seed_reference_templates", is_destructive=True)

    user_id = _seed_user_id(user_email)
    summary = []

    for spec in STANDARD_NOTICE_TEMPLATES:
        template_type = spec["template_type"]
        label = spec["label"]
        file_name = spec["file_name"]
        source_path, source = _template_source_path(template_type, file_name)

        removed = 0
        for existing_type, template_id in _existing_standard_templates(file_name, label):
            settings_service.delete_document_template(existing_type, template_id, user_id=user_id)
            removed += 1

        settings_service.store_document_template(
            template_type,
            upload=LocalTemplateUpload(source_path),
            user_id=user_id,
            label=label,
            placeholder_defaults={},
            is_default=True,
        )

        refreshed_group = next(
            item for item in settings_service.list_document_templates()
            if item.get("template_type") == template_type
        )
        default_template_id = refreshed_group.get("default_template_id")
        default_template = next(
            (
                item for item in refreshed_group.get("templates") or []
                if item.get("id") == default_template_id
            ),
            None,
        )
        summary.append({
            "template_type": template_type,
            "label": label,
            "file_name": file_name,
            "source": source,
            "removed_existing": removed,
            "default_template_id": default_template_id,
            "placeholder_fields": (default_template or {}).get("placeholder_fields") or [],
        })

    return summary


def main():
    app = create_app(os.environ.get("FLASK_CONFIG") or "development")
    with app.app_context():
        summary = seed_reference_templates()
        print("Seeded standard Reference Library templates:")
        for item in summary:
            fields = ", ".join(item["placeholder_fields"]) or "none detected"
            print(
                f"  {item['template_type']}: {item['file_name']} "
                f"(source={item['source']}, default={item['default_template_id']}, "
                f"placeholders={fields})"
            )


if __name__ == "__main__":
    main()
