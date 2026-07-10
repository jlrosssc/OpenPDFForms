from __future__ import annotations

import math
import re
import uuid
from pathlib import Path

import cv2
import fitz
import numpy as np

from .hooks import apply_field_hooks
from .models import FieldType, FormField, HookContext


def render_pdf_pages(source_pdf: Path, render_dir: Path, zoom: float = 1.75) -> tuple[list[str], list[tuple[float, float]]]:
    urls: list[str] = []
    page_sizes: list[tuple[float, float]] = []
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(source_pdf) as doc:
        for page_index, page in enumerate(doc):
            page_sizes.append((float(page.rect.width), float(page.rect.height)))
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = render_dir / f"page-{page_index + 1}.png"
            pix.save(image_path)
            urls.append(f"/renders/{render_dir.name}/{image_path.name}")
    return urls, page_sizes


def detect_fields(source_pdf: Path, document_id: str) -> list[FormField]:
    fields: list[FormField] = []
    with fitz.open(source_pdf) as doc:
        for page_index, page in enumerate(doc):
            page_fields = _detect_page_fields(page, page_index)
            fields.extend(apply_field_hooks(page_fields, HookContext(document_id=document_id, source_pdf=source_pdf, page_index=page_index)))
    return fields


def _detect_page_fields(page: fitz.Page, page_index: int) -> list[FormField]:
    text_lines = _extract_text_lines(page)
    fields = []
    fields.extend(_detect_text_fields_from_text(page_index, text_lines, page.rect.width))
    fields.extend(_detect_shape_fields(page, page_index, text_lines))
    return _dedupe_fields(fields)


def _extract_text_lines(page: fitz.Page) -> list[dict]:
    lines = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            lines.append({"text": text, "bbox": (float(x0), float(y0), float(x1), float(y1))})
    return lines


def _detect_text_fields_from_text(page_index: int, lines: list[dict], page_width: float) -> list[FormField]:
    fields: list[FormField] = []
    for line in lines:
        text = line["text"]
        x0, y0, x1, y1 = line["bbox"]
        if "_" in text:
            for match in re.finditer(r"_{4,}", text):
                width = max(70.0, min(260.0, match.end() - match.start()) * 6.0)
                field_x = min(page_width - width - 24.0, x0 + match.start() * 5.2)
                label = text[: match.start()].strip(" :_")
                fields.append(_field(page_index, FieldType.text, field_x, y0 - 2, width, max(16.0, y1 - y0 + 4), label))
            continue
        if text.endswith(":"):
            available = page_width - x1 - 36.0
            if available >= 90.0 and len(text) <= 55:
                fields.append(_field(page_index, FieldType.text, x1 + 8.0, y0 - 2.0, min(available, 260.0), max(16.0, y1 - y0 + 4), text.rstrip(":")))
    return fields


def _detect_shape_fields(page: fitz.Page, page_index: int, lines: list[dict]) -> list[FormField]:
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, threshold = cv2.threshold(gray, 210, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    scale_x = page.rect.width / pix.width
    scale_y = page.rect.height / pix.height
    fields: list[FormField] = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        pdf_x, pdf_y, pdf_w, pdf_h = x * scale_x, y * scale_y, w * scale_x, h * scale_y
        if 7 <= pdf_w <= 24 and 7 <= pdf_h <= 24 and 0.65 <= pdf_w / max(pdf_h, 1) <= 1.45:
            if _looks_like_box(contour):
                label = _nearest_right_label(lines, pdf_x, pdf_y, pdf_h)
                if label:
                    fields.append(_field(page_index, FieldType.checkbox, pdf_x, pdf_y, max(pdf_w, 10), max(pdf_h, 10), label))
        elif pdf_w >= 55 and 6 <= pdf_h <= 20:
            if _looks_like_horizontal_line(contour):
                label = _nearest_left_label(lines, pdf_x, pdf_y, pdf_h)
                fields.append(_field(page_index, FieldType.text, pdf_x, pdf_y - 9, min(pdf_w, 320), 18, label))
    return fields


def _looks_like_horizontal_line(contour) -> bool:
    _x, _y, w, h = cv2.boundingRect(contour)
    return w >= 4 * max(h, 1)


def _looks_like_box(contour) -> bool:
    x, y, w, h = cv2.boundingRect(contour)
    rect_area = max(w * h, 1)
    contour_area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
    return 4 <= len(approx) <= 8 and contour_area / rect_area >= 0.25


def _nearest_left_label(lines: list[dict], x: float, y: float, height: float) -> str:
    candidates = []
    center_y = y + height / 2
    for line in lines:
        text = line["text"].rstrip(":")
        x0, y0, x1, y1 = line["bbox"]
        if x1 <= x + 4 and abs(((y0 + y1) / 2) - center_y) <= 12:
            candidates.append((x - x1, text))
    return min(candidates, default=(0, ""))[1]


def _nearest_right_label(lines: list[dict], x: float, y: float, height: float) -> str:
    candidates = []
    center_y = y + height / 2
    for line in lines:
        text = line["text"].rstrip(":")
        x0, y0, _x1, y1 = line["bbox"]
        if x0 >= x and abs(((y0 + y1) / 2) - center_y) <= 12:
            candidates.append((x0 - x, text))
    return min(candidates, default=(0, ""))[1]


def _field(page: int, field_type: FieldType, x: float, y: float, width: float, height: float, label: str) -> FormField:
    clean_label = " ".join(label.split())[:60]
    name_base = re.sub(r"[^a-zA-Z0-9]+", "_", clean_label.lower()).strip("_") or f"{field_type.value}_{uuid.uuid4().hex[:6]}"
    return FormField(
        id=uuid.uuid4().hex,
        page=page,
        type=field_type,
        name=name_base,
        x=round(float(x), 2),
        y=round(float(y), 2),
        width=round(float(width), 2),
        height=round(float(height), 2),
        label=clean_label,
        tooltip=clean_label,
    )


def _dedupe_fields(fields: list[FormField]) -> list[FormField]:
    kept: list[FormField] = []
    for field in fields:
        if any(field.page == other.page and _overlap_ratio(field, other) > 0.55 for other in kept):
            continue
        kept.append(field)
    used: dict[str, int] = {}
    for field in kept:
        count = used.get(field.name, 0)
        used[field.name] = count + 1
        if count:
            field.name = f"{field.name}_{count + 1}"
    return kept


def _overlap_ratio(a: FormField, b: FormField) -> float:
    ax2, ay2 = a.x + a.width, a.y + a.height
    bx2, by2 = b.x + b.width, b.y + b.height
    inter_w = max(0.0, min(ax2, bx2) - max(a.x, b.x))
    inter_h = max(0.0, min(ay2, by2) - max(a.y, b.y))
    inter = inter_w * inter_h
    smaller = min(a.width * a.height, b.width * b.height)
    return inter / smaller if smaller else 0.0
