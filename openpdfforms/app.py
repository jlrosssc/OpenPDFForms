from __future__ import annotations

from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone
import os
from typing import Annotated

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    SESSION_COOKIE,
    User,
    authenticate,
    create_session,
    create_user,
    delete_session,
    delete_user,
    init_auth_db,
    list_users,
    update_user,
    user_from_session,
    users_exist,
)
from .detector import detect_fields, import_existing_fields, render_pdf_pages
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
init_auth_db()


LOGIN_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>OpenPDFForms Login</title><link rel="stylesheet" href="static/styles.css"></head>
<body class="auth-page"><main class="auth-card"><h1>OpenPDFForms</h1><p>{message}</p><form method="post" action="{action}"><label>Username<input name="username" autocomplete="username" required autofocus></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><button type="submit">{button}</button></form></main></body>
</html>"""


def _wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


async def current_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Login required.")
    return user


async def current_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


@app.middleware("http")
async def auth_and_no_cache(request: Request, call_next):
    path = request.url.path
    public = path.startswith("/static/") or path in {"/login", "/api/login", "/logout"}
    setup_allowed = not users_exist() and path in {"/setup", "/api/setup"}
    if not public and not setup_allowed:
        user = user_from_session(request.cookies.get(SESSION_COOKIE))
        if not user:
            if _wants_html(request):
                return RedirectResponse("setup" if not users_exist() else "login", status_code=303)
            return JSONResponse({"detail": "Login required."}, status_code=401)
        request.state.user = user
    response = await call_next(request)
    if path == "/" or path in {"/login", "/setup"} or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.mount("/renders", StaticFiles(directory=RENDER_ROOT), name="renders")


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/login")
def login_page() -> HTMLResponse:
    return HTMLResponse(LOGIN_HTML.format(message="Sign in to continue.", action="api/login", button="Sign In"))


@app.post("/api/login")
def login(username: Annotated[str, Form()], password: Annotated[str, Form()]) -> RedirectResponse:
    user = authenticate(username, password)
    if not user:
        return RedirectResponse("../login", status_code=303)
    response = RedirectResponse("../", status_code=303)
    response.set_cookie(SESSION_COOKIE, create_session(user.id), httponly=True, secure=False, samesite="lax", max_age=30 * 24 * 60 * 60)
    return response


@app.get("/setup")
def setup_page() -> HTMLResponse:
    if users_exist():
        return RedirectResponse("login", status_code=303)
    return HTMLResponse(LOGIN_HTML.format(message="Create the first administrator account.", action="api/setup", button="Create Admin"))


@app.post("/api/setup")
def setup_admin(username: Annotated[str, Form()], password: Annotated[str, Form()]) -> RedirectResponse:
    if users_exist():
        return RedirectResponse("../login", status_code=303)
    user = create_user(username, password, is_admin=True, active=True)
    response = RedirectResponse("../", status_code=303)
    response.set_cookie(SESSION_COOKIE, create_session(user.id), httponly=True, secure=False, samesite="lax", max_age=30 * 24 * 60 * 60)
    return response


@app.get("/logout")
def logout(request: Request) -> RedirectResponse:
    delete_session(request.cookies.get(SESSION_COOKIE, ""))
    response = RedirectResponse("login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/api/me")
def me(user: Annotated[User, Depends(current_user)]) -> dict:
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@app.get("/api/users")
def users(_: Annotated[User, Depends(current_admin)]) -> list[dict]:
    return list_users()


@app.post("/api/users")
def add_user(payload: Annotated[dict, Body()], _: Annotated[User, Depends(current_admin)]) -> dict:
    try:
        user = create_user(
            str(payload.get("username", "")),
            str(payload.get("password", "")),
            is_admin=bool(payload.get("is_admin", False)),
            active=bool(payload.get("active", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin, "active": user.active}


@app.patch("/api/users/{user_id}")
def edit_user(user_id: int, payload: Annotated[dict, Body()], admin: Annotated[User, Depends(current_admin)]) -> dict:
    if user_id == admin.id and payload.get("active") is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account.")
    try:
        user = update_user(
            user_id,
            password=str(payload["password"]) if payload.get("password") else None,
            is_admin=bool(payload["is_admin"]) if "is_admin" in payload else None,
            active=bool(payload["active"]) if "active" in payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin, "active": user.active}


@app.delete("/api/users/{user_id}")
def remove_user(user_id: int, admin: Annotated[User, Depends(current_admin)]) -> dict:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    delete_user(user_id)
    return {"ok": True}


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
    fields = import_existing_fields(source_path)
    if fields is None:
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
