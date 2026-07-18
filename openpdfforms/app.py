from __future__ import annotations

from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .detector import detect_fields, render_pdf_pages
from .exporter import export_fillable_pdf
from .models import DocumentInfo, ExportRequest, ExportResponse, FillSignRequest, PreviewResponse, ProjectSaveRequest, ProjectSummary
from .signing import CA_CERT_PATH, apply_field_values, ensure_root_ca, sign_field
from .storage import (
    EXPORT_ROOT,
    RENDER_ROOT,
    UPLOAD_ROOT,
    document_upload_path,
    ensure_data_dirs,
    export_path,
    new_document_id,
    preview_path,
    project_path,
    reset_render_dir,
    working_pdf_path,
)


app = FastAPI(title="OpenPDFForms", root_path=os.environ.get("OPENPDFFORMS_ROOT_PATH", ""))
ensure_data_dirs()


@app.middleware("http")
async def no_cache_for_app_shell(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.mount("/renders", StaticFiles(directory=RENDER_ROOT), name="renders")


STATIC_DIR = Path(__file__).parent / "static"


def _asset_version() -> str:
    """Content hash of the static assets, so a query-string version changes
    exactly when the files do -- forcing a fresh fetch even if a CDN in
    front of this app (e.g. Cloudflare) overrides Cache-Control on static
    file extensions and serves a stale copy for hours after a deploy.
    """
    hasher = hashlib.sha256()
    for name in ("app.js", "styles.css"):
        hasher.update((STATIC_DIR / name).read_bytes())
    return hasher.hexdigest()[:10]


@app.get("/")
def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    version = _asset_version()
    html = html.replace('href="static/styles.css"', f'href="static/styles.css?v={version}"')
    html = html.replace('src="static/app.js"', f'src="static/app.js?v={version}"')
    return HTMLResponse(html)


@app.post("/api/documents", response_model=DocumentInfo)
async def upload_document(file: UploadFile = File(...)) -> DocumentInfo:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload a PDF file.")

    document_id = new_document_id()
    source_path = document_upload_path(document_id, file.filename)
    with source_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    render_dir = reset_render_dir(document_id)
    render_urls, page_sizes = render_pdf_pages(source_path, render_dir)
    fields = detect_fields(source_path, document_id)
    return DocumentInfo(
        document_id=document_id,
        filename=file.filename,
        page_count=len(page_sizes),
        page_sizes=page_sizes,
        render_urls=render_urls,
        fields=fields,
    )


@app.post("/api/documents/{document_id}/export", response_model=ExportResponse)
def export_document(document_id: str, request: ExportRequest) -> ExportResponse:
    matches = list(UPLOAD_ROOT.glob(f"{document_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Document not found.")
    output_path = export_path(document_id)
    export_fillable_pdf(matches[0], output_path, request.fields)
    return ExportResponse(download_url=f"api/documents/{document_id}/download")


@app.get("/api/documents/{document_id}/download")
def download_document(document_id: str) -> FileResponse:
    output_path = export_path(document_id)
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Export not found.")
    return FileResponse(output_path, media_type="application/pdf", filename=output_path.name)


@app.post("/api/documents/{document_id}/preview", response_model=PreviewResponse)
def preview_document(document_id: str, request: ExportRequest) -> PreviewResponse:
    """Render the document with current field values applied, without exporting or signing.

    Builds into a throwaway preview PDF/render dir (never export_path or
    working_pdf_path) so sampling a look at the document can't clobber a
    real export or an in-progress signed copy.
    """
    matches = list(UPLOAD_ROOT.glob(f"{document_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Document not found.")

    preview_pdf = preview_path(document_id)
    export_fillable_pdf(matches[0], preview_pdf, request.fields)
    apply_field_values(preview_pdf, preview_pdf, request.fields)

    render_dir = reset_render_dir(f"{document_id}-preview")
    render_urls, _ = render_pdf_pages(preview_pdf, render_dir)
    return PreviewResponse(render_urls=render_urls)


@app.post("/api/documents/{document_id}/fill-and-sign", response_model=ExportResponse)
def fill_and_sign(document_id: str, request: FillSignRequest) -> ExportResponse:
    matches = list(UPLOAD_ROOT.glob(f"{document_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Document not found.")

    working = working_pdf_path(document_id)
    if not working.exists():
        export_fillable_pdf(matches[0], working, request.fields)

    filled = working.with_name(f"{working.stem}-filling.pdf")
    apply_field_values(working, filled, request.fields)
    sign_field(
        filled,
        working,
        field_name=request.sign_field_name,
        kind=request.kind,
        signer_name=request.signer_name,
        reason=request.reason,
        location=request.location,
        signature_image_data_url=request.signature_image_data_url,
    )
    filled.unlink(missing_ok=True)
    return ExportResponse(download_url=f"api/documents/{document_id}/download-working")


@app.get("/api/documents/{document_id}/download-working")
def download_working_document(document_id: str) -> FileResponse:
    working = working_pdf_path(document_id)
    if not working.exists():
        raise HTTPException(status_code=404, detail="No filled or signed copy yet.")
    return FileResponse(working, media_type="application/pdf", filename=f"{document_id}-signed.pdf")


@app.get("/api/trust-certificate")
def download_trust_certificate() -> FileResponse:
    """Serve only the root CA's public certificate -- never the private key.

    Installing this file as a trusted root (macOS Keychain, Windows
    Certificate Manager, etc.) is what makes E Sign signatures produced by
    this server validate as trusted rather than merely tamper-evident.
    """
    ensure_root_ca()
    return FileResponse(CA_CERT_PATH, media_type="application/x-x509-ca-cert", filename="openpdfforms-trust-root.pem")


@app.put("/api/projects/{document_id}", response_model=ProjectSummary)
def save_project(document_id: str, request: ProjectSaveRequest) -> ProjectSummary:
    matches = list(UPLOAD_ROOT.glob(f"{document_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Document not found.")
    updated_at = datetime.now(timezone.utc).isoformat()
    payload = request.model_dump(mode="json")
    payload["document_id"] = document_id
    payload["updated_at"] = updated_at
    path = project_path(document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ProjectSummary(document_id=document_id, filename=request.filename, updated_at=updated_at)


@app.get("/api/projects", response_model=list[ProjectSummary])
def list_projects() -> list[ProjectSummary]:
    projects: list[ProjectSummary] = []
    for path in sorted(project_path("*").parent.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        projects.append(
            ProjectSummary(
                document_id=payload.get("document_id") or path.stem,
                filename=payload.get("filename") or path.stem,
                updated_at=payload.get("updated_at") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            )
        )
    return projects


@app.get("/api/projects/{document_id}", response_model=DocumentInfo)
def open_project(document_id: str) -> DocumentInfo:
    path = project_path(document_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DocumentInfo.model_validate(payload)
