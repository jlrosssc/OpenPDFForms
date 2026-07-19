from __future__ import annotations

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
            urls.append(f"renders/{render_dir.name}/{image_path.name}")
    return urls, page_sizes


_WIDGET_TYPE_MAP = {
    fitz.PDF_WIDGET_TYPE_TEXT: FieldType.text,
    fitz.PDF_WIDGET_TYPE_CHECKBOX: FieldType.checkbox,
    fitz.PDF_WIDGET_TYPE_RADIOBUTTON: FieldType.radio,
    fitz.PDF_WIDGET_TYPE_COMBOBOX: FieldType.dropdown,
    fitz.PDF_WIDGET_TYPE_LISTBOX: FieldType.listbox,
    fitz.PDF_WIDGET_TYPE_SIGNATURE: FieldType.digital_signature,
}


def import_existing_fields(source_pdf: Path) -> list[FormField] | None:
    """Import a PDF's own existing AcroForm fields, e.g. one built in Adobe Acrobat.

    Returns None if the PDF has no form fields at all, so the caller can
    fall back to the heuristic detect_fields(). When real fields already
    exist, guessing new candidates on top of them (detect_fields' job for
    flat/scanned PDFs) would only produce a worse, redundant set -- wrong
    types, generic names, no dropdown options, no signature fields -- so
    real fields always take priority over heuristic detection.
    """
    with fitz.open(source_pdf) as doc:
        if not doc.is_form_pdf:
            return None

        fields: list[FormField] = []
        used_names: dict[str, int] = {}
        radio_groups: dict[str, str] = {}

        def next_type_name(field_type: FieldType) -> str:
            prefix = _field_name_prefix(field_type)
            count = used_names.get(prefix, 0) + 1
            used_names[prefix] = count
            return f"{prefix}_{count}"

        def radio_group_name(original_name: str) -> str:
            key = original_name or "radio_group"
            if key not in radio_groups:
                radio_groups[key] = f"radio_group_{len(radio_groups) + 1}"
            return radio_groups[key]

        for page_index, page in enumerate(doc):
            for widget in page.widgets():
                field_type = _WIDGET_TYPE_MAP.get(widget.field_type, FieldType.text)
                label = (widget.field_label or widget.field_name or "").strip()
                required = bool(widget.field_flags and widget.field_flags & 2)
                read_only = bool(widget.field_flags and widget.field_flags & 1)
                no_export = bool(widget.field_flags and widget.field_flags & 4)
                group = radio_group_name(widget.field_name) if field_type == FieldType.radio else ""
                rect = widget.rect

                fields.append(
                    FormField(
                        id=uuid.uuid4().hex,
                        page=page_index,
                        type=field_type,
                        name=next_type_name(field_type),
                        x=round(float(rect.x0), 2),
                        y=round(float(rect.y0), 2),
                        width=round(float(rect.width), 2),
                        height=round(float(rect.height), 2),
                        label=label[:60],
                        tooltip=label,
                        required=required,
                        read_only=read_only,
                        no_export=no_export,
                        default_value=str(widget.field_value or "") if widget.field_value else "",
                        options=list(widget.choice_values or []) if field_type in (FieldType.dropdown, FieldType.listbox) else [],
                        group=group,
                        font_size=widget.text_fontsize or 10,
                        multiline=field_type == FieldType.text
                        and bool(widget.field_flags and widget.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE),
                    )
                )

        return fields or None


def detect_fields(source_pdf: Path, document_id: str) -> list[FormField]:
    fields: list[FormField] = []
    with fitz.open(source_pdf) as doc:
        for page_index, page in enumerate(doc):
            page_fields = _detect_page_fields(page, page_index)
            fields.extend(apply_field_hooks(page_fields, HookContext(document_id=document_id, source_pdf=source_pdf, page_index=page_index)))
    return fields


def _detect_page_fields(page: fitz.Page, page_index: int) -> list[FormField]:
    text_lines = _extract_text_lines(page)
    if _looks_like_instruction_page(text_lines):
        return []
    vector_fields = _detect_vector_form_fields(page, page_index, text_lines)
    if len(vector_fields) >= 5:
        return _dedupe_fields(vector_fields)

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
            if not _is_likely_form_label(text):
                continue
            available = page_width - x1 - 36.0
            if available >= 90.0 and len(text) <= 55:
                fields.append(_field(page_index, FieldType.text, x1 + 8.0, y0 - 2.0, min(available, 260.0), max(16.0, y1 - y0 + 4), text.rstrip(":")))
    return fields


def _detect_vector_form_fields(page: fitz.Page, page_index: int, lines: list[dict]) -> list[FormField]:
    horizontal, vertical, rects = _vector_geometry(page)
    if len(horizontal) < 8 or len(vertical) < 4:
        return []

    fields: list[FormField] = []
    for line in lines:
        text = line["text"].strip()
        if not _is_likely_form_label(text):
            continue
        cell = _find_cell_for_label(line["bbox"], horizontal, vertical)
        if not cell:
            continue
        left, top, right, bottom = cell
        x0, _y0, _x1, y1 = line["bbox"]
        if right - left < 28 or bottom - top < 16:
            continue
        if left > page.rect.width * 0.75 and right - left < 100 and bottom - top > 70:
            continue
        if _is_likely_checkbox_label(text):
            continue
        field_top = max(float(y1) + 2.0, top + 11.0)
        field_bottom = bottom - 3.0
        if field_bottom - field_top < 12.0:
            field_top = max(top + 10.0, field_bottom - 12.0)
        if field_bottom - field_top < 7:
            continue
        field_left = left + 4.0
        if text.strip() == "$":
            continue
        if text.startswith("$"):
            field_left = max(field_left, x0 + 10.0)
        fields.append(_field(page_index, FieldType.text, field_left, field_top, right - field_left - 4.0, field_bottom - field_top, text.rstrip(":")))

    for rect in rects:
        x0, y0, x1, y1 = rect
        width = x1 - x0
        height = y1 - y0
        if not (7 <= width <= 16 and 7 <= height <= 16 and 0.75 <= width / max(height, 1) <= 1.35):
            continue
        right_label = _nearest_right_label(lines, x0, y0, height)
        left_label = _nearest_left_label(lines, x0, y0, height)
        label = right_label if _is_likely_checkbox_label(right_label) else left_label
        if label and _is_likely_checkbox_label(label):
            fields.append(_field(page_index, FieldType.checkbox, x0, y0, width, height, label))

    return fields


def _vector_geometry(page: fitz.Page) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[tuple[float, float, float, float]]]:
    horizontal: list[tuple[float, float, float]] = []
    vertical: list[tuple[float, float, float]] = []
    rects: list[tuple[float, float, float, float]] = []

    def add_line(x0: float, y0: float, x1: float, y1: float) -> None:
        if abs(y0 - y1) <= 1.0 and abs(x1 - x0) >= 6.0:
            horizontal.append((round((y0 + y1) / 2, 1), round(min(x0, x1), 1), round(max(x0, x1), 1)))
        elif abs(x0 - x1) <= 1.0 and abs(y1 - y0) >= 6.0:
            vertical.append((round((x0 + x1) / 2, 1), round(min(y0, y1), 1), round(max(y0, y1), 1)))

    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                add_line(float(p1.x), float(p1.y), float(p2.x), float(p2.y))
            elif item[0] == "re":
                rect = item[1]
                x0, y0, x1, y1 = float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)
                rects.append((round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)))
                add_line(x0, y0, x1, y0)
                add_line(x0, y1, x1, y1)
                add_line(x0, y0, x0, y1)
                add_line(x1, y0, x1, y1)

    return _merge_lines(horizontal), _merge_lines(vertical), rects


def _merge_lines(lines: list[tuple[float, float, float]], tolerance: float = 1.2) -> list[tuple[float, float, float]]:
    merged: list[tuple[float, float, float]] = []
    for fixed, start, end in sorted(lines):
        for idx, (existing_fixed, existing_start, existing_end) in enumerate(merged):
            if abs(fixed - existing_fixed) <= tolerance and start <= existing_end + tolerance and end >= existing_start - tolerance:
                merged[idx] = (
                    round((existing_fixed + fixed) / 2, 1),
                    round(min(existing_start, start), 1),
                    round(max(existing_end, end), 1),
                )
                break
        else:
            merged.append((fixed, start, end))
    return merged


def _find_cell_for_label(
    bbox: tuple[float, float, float, float],
    horizontal: list[tuple[float, float, float]],
    vertical: list[tuple[float, float, float]],
) -> tuple[float, float, float, float] | None:
    x0, y0, x1, y1 = bbox
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    lefts = [x for x, vy0, vy1 in vertical if x <= cx + 1.0 and vy0 <= cy <= vy1]
    rights = [x for x, vy0, vy1 in vertical if x >= cx - 1.0 and vy0 <= cy <= vy1]
    top_lines = [(y, hx0, hx1) for y, hx0, hx1 in horizontal if y <= cy + 1.0 and hx0 <= cx <= hx1]
    bottom_lines = [(y, hx0, hx1) for y, hx0, hx1 in horizontal if y >= cy - 1.0 and hx0 <= cx <= hx1]
    if not top_lines or not bottom_lines:
        return None
    tops = [line[0] for line in top_lines]
    bottoms = [line[0] for line in bottom_lines]
    if not lefts:
        lefts = [max(line[1] for line in (top_lines + bottom_lines) if line[1] <= cx)]
    if not rights:
        right_candidates = [line[2] for line in (top_lines + bottom_lines) if line[2] >= cx]
        if right_candidates:
            rights = [min(right_candidates)]
    if not lefts or not rights:
        return None
    left, right = max(lefts), min(rights)
    top, bottom = max(tops), min(bottoms)
    if right - left < 12 or bottom - top < 10:
        return None
    return left, top, right, bottom


def _is_likely_form_label(text: str) -> bool:
    normalized = " ".join(text.strip().split())
    if not normalized or len(normalized) > 90:
        return False
    lower = normalized.lower()
    ignored = (
        "attention",
        "department of the treasury",
        "internal revenue service",
        "instructions",
        "privacy act",
        "paperwork",
        "www.",
        "form ",
        "copy ",
        "cat. no.",
        "omb no.",
    )
    if any(lower.startswith(prefix) for prefix in ignored):
        return False
    if any(phrase in lower for phrase in ("for state tax", "for recipient", "recipient's state", "recipient’s state")):
        return False
    if lower in {"$", "for", "created"}:
        return False
    signal_words = (
        "name",
        "address",
        "city",
        "state",
        "country",
        "zip",
        "tin",
        "account",
        "compensation",
        "tips",
        "tax",
        "income",
        "year",
        "void",
        "corrected",
        "payer",
        "recipient",
        "sales",
        "parachute",
        "overtime",
        "ttoc",
        "room",
        "suite",
        "telephone",
        "apt.",
    )
    return normalized.endswith(":") or any(word in lower for word in signal_words) or bool(re.match(r"^\d+[a-z]?\s+", lower))


def _is_likely_checkbox_label(text: str) -> bool:
    lower = " ".join(text.lower().split())
    if len(lower) > 90:
        return False
    return any(term in lower for term in ("void", "corrected", "direct sales", "consumer products", "checked", "$5,000", "2nd tin"))


def _looks_like_instruction_page(lines: list[dict]) -> bool:
    text = " ".join(line["text"] for line in lines[:60]).lower()
    return (
        "which revision to use for which year" in text
        or "instructions for recipient" in text
        or "instructions for payer" in text
    )


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
                if label and _is_likely_form_label(label):
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
    return FormField(
        id=uuid.uuid4().hex,
        page=page,
        type=field_type,
        name=field_type.value,
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
        prefix = _field_name_prefix(field.type)
        count = used.get(prefix, 0) + 1
        used[prefix] = count
        field.name = f"{prefix}_{count}"
    return kept


def _field_name_prefix(field_type: FieldType) -> str:
    return {
        FieldType.text: "text",
        FieldType.date: "date",
        FieldType.checkbox: "checkbox",
        FieldType.radio: "radio",
        FieldType.dropdown: "dropdown",
        FieldType.listbox: "listbox",
        FieldType.button: "button",
        FieldType.signature: "signature",
        FieldType.initials: "initials",
        FieldType.digital_signature: "esign",
    }.get(field_type, "field")


def _overlap_ratio(a: FormField, b: FormField) -> float:
    ax2, ay2 = a.x + a.width, a.y + a.height
    bx2, by2 = b.x + b.width, b.y + b.height
    inter_w = max(0.0, min(ax2, bx2) - max(a.x, b.x))
    inter_h = max(0.0, min(ay2, by2) - max(a.y, b.y))
    inter = inter_w * inter_h
    smaller = min(a.width * a.height, b.width * b.height)
    return inter / smaller if smaller else 0.0
