from __future__ import annotations

from pathlib import Path
import base64

import fitz

from .models import FieldType, FormField


def export_fillable_pdf(source_pdf: Path, output_pdf: Path, fields: list[FormField]) -> None:
    with fitz.open(source_pdf) as doc:
        for field in fields:
            page = doc[field.page]
            if field.type == FieldType.signature and field.signature_data_url:
                _insert_signature_image(page, field)
                continue
            widget = fitz.Widget()
            widget.field_name = field.name
            widget.field_label = field.tooltip or field.label or field.name
            widget.rect = fitz.Rect(field.x, field.y, field.x + field.width, field.y + field.height)
            widget.text_font = "Helv"
            widget.text_fontsize = 10
            widget.field_flags = 2 if field.required else 0

            if field.type in {FieldType.text, FieldType.signature, FieldType.date}:
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                if field.type == FieldType.signature:
                    widget.field_label = widget.field_label or "Signature"
                if field.type == FieldType.date:
                    widget.field_label = widget.field_label or "Date"
            elif field.type == FieldType.checkbox:
                widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
            elif field.type == FieldType.radio:
                widget.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
                widget.field_name = field.group or field.name
            elif field.type == FieldType.dropdown:
                widget.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
                widget.choice_values = field.options or [""]
            else:
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT

            page.add_widget(widget)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_pdf, deflate=True, garbage=4)


def _insert_signature_image(page: fitz.Page, field: FormField) -> None:
    prefix = "base64,"
    if prefix not in field.signature_data_url:
        return
    image_data = base64.b64decode(field.signature_data_url.split(prefix, 1)[1])
    rect = fitz.Rect(field.x, field.y, field.x + field.width, field.y + field.height)
    page.insert_image(rect, stream=image_data, keep_proportion=True, overlay=True)
