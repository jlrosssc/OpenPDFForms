from __future__ import annotations

import shutil
import uuid
from pathlib import Path


DATA_ROOT = Path("data")
UPLOAD_ROOT = DATA_ROOT / "uploads"
RENDER_ROOT = DATA_ROOT / "renders"
EXPORT_ROOT = DATA_ROOT / "exports"
PROJECT_ROOT = DATA_ROOT / "projects"


def ensure_data_dirs() -> None:
    for path in (UPLOAD_ROOT, RENDER_ROOT, EXPORT_ROOT, PROJECT_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def new_document_id() -> str:
    return uuid.uuid4().hex


def document_upload_path(document_id: str, filename: str) -> Path:
    suffix = Path(filename).suffix.lower() or ".pdf"
    return UPLOAD_ROOT / f"{document_id}{suffix}"


def document_render_dir(document_id: str) -> Path:
    return RENDER_ROOT / document_id


def reset_render_dir(document_id: str) -> Path:
    render_dir = document_render_dir(document_id)
    if render_dir.exists():
        shutil.rmtree(render_dir)
    render_dir.mkdir(parents=True, exist_ok=True)
    return render_dir


def export_path(document_id: str) -> Path:
    return EXPORT_ROOT / f"{document_id}-fillable.pdf"


def project_path(document_id: str) -> Path:
    return PROJECT_ROOT / f"{document_id}.json"
