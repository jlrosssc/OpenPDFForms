from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import fitz


IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
OFFICE_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".odp",
    ".ods",
    ".odt",
    ".ppt",
    ".pptx",
    ".rtf",
    ".txt",
    ".xls",
    ".xlsx",
}


class ConversionError(RuntimeError):
    pass


def convert_upload_to_pdf(source_path: Path, pdf_path: Path) -> None:
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        shutil.copyfile(source_path, pdf_path)
    elif suffix in IMAGE_EXTENSIONS:
        _image_to_pdf(source_path, pdf_path)
    elif suffix in OFFICE_EXTENSIONS:
        _office_to_pdf(source_path, pdf_path)
    else:
        supported = ", ".join(sorted(IMAGE_EXTENSIONS | OFFICE_EXTENSIONS | {".pdf"}))
        raise ConversionError(f"Unsupported upload type '{suffix or 'unknown'}'. Supported types: {supported}.")


def _image_to_pdf(source_path: Path, pdf_path: Path) -> None:
    try:
        with fitz.open(source_path) as image_doc:
            pdf_bytes = image_doc.convert_to_pdf()
        pdf_path.write_bytes(pdf_bytes)
    except Exception as exc:
        raise ConversionError(f"Could not convert image to PDF: {exc}") from exc


def _office_to_pdf(source_path: Path, pdf_path: Path) -> None:
    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice:
        raise ConversionError("Office document conversion requires LibreOffice on the server.")

    output_dir = pdf_path.parent
    command = [
        libreoffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(source_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    converted = output_dir / f"{source_path.stem}.pdf"
    if result.returncode != 0 or not converted.exists():
        message = (result.stderr or result.stdout or "LibreOffice did not create a PDF.").strip()
        raise ConversionError(f"Could not convert document to PDF: {message}")
    converted.replace(pdf_path)
