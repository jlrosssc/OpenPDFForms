from __future__ import annotations

from pathlib import Path

import fitz

from .models import FieldType, FormField

FORMAT_SCRIPTS = {
    "number": 'AFNumber_Format(2, 0, 0, 0, "", false);',
    "integer": 'AFNumber_Format(0, 0, 0, 0, "", false);',
    "percent": "AFPercent_Format(2, 0);",
    "currency": 'AFNumber_Format(2, 0, 0, 0, "$", true);',
    "date": 'AFDate_FormatEx("mm/dd/yyyy");',
    "zip": "AFSpecial_Format(0);",
    "phone": "AFSpecial_Format(2);",
}

CALC_OPERATIONS = {
    "sum": "SUM",
    "average": "AVG",
    "product": "PRD",
    "min": "MIN",
    "max": "MAX",
}


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float] | None:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return None
    try:
        return (
            int(value[0:2], 16) / 255,
            int(value[2:4], 16) / 255,
            int(value[4:6], 16) / 255,
        )
    except ValueError:
        return None


def export_fillable_pdf(source_pdf: Path, output_pdf: Path, fields: list[FormField]) -> None:
    with fitz.open(source_pdf) as doc:
        for field in fields:
            page = doc[field.page]
            widget = fitz.Widget()
            widget.field_name = field.name
            widget.field_label = field.tooltip or field.label or field.name
            widget.rect = fitz.Rect(field.x, field.y, field.x + field.width, field.y + field.height)
            widget.text_font = "Helv"
            widget.text_fontsize = field.font_size or 10
            widget.field_flags = 2 if field.required else 0

            border_rgb = _hex_to_rgb(field.border_color)
            if border_rgb:
                widget.border_color = border_rgb
            fill_rgb = _hex_to_rgb(field.background_color)
            if fill_rgb:
                widget.fill_color = fill_rgb

            if field.type in {FieldType.text, FieldType.date}:
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                if field.type == FieldType.date:
                    widget.field_label = widget.field_label or "Date"
            elif field.type == FieldType.checkbox:
                widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
            elif field.type == FieldType.radio:
                widget.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
                widget.field_name = field.group or field.name
                widget.field_value = False
            elif field.type == FieldType.dropdown:
                widget.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
                widget.choice_values = field.options or [""]
            elif field.type == FieldType.signature:
                widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
                widget.field_label = widget.field_label or "Mock Sign"
            elif field.type == FieldType.digital_signature:
                widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
                widget.field_label = widget.field_label or "E Sign"
            else:
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT

            if widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
                if field.multiline:
                    widget.field_flags |= fitz.PDF_TX_FIELD_IS_MULTILINE
                elif field.comb and field.max_length > 0:
                    widget.field_flags |= fitz.PDF_TX_FIELD_IS_COMB
                    widget.text_maxlen = field.max_length
                if field.format in FORMAT_SCRIPTS:
                    widget.script_format = FORMAT_SCRIPTS[field.format]
                if field.calc_operation in CALC_OPERATIONS and field.calc_fields:
                    names = ", ".join(f'"{name}"' for name in field.calc_fields)
                    widget.script_calc = (
                        f'AFSimple_Calculate("{CALC_OPERATIONS[field.calc_operation]}", new Array({names}));'
                    )

            page.add_widget(widget)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_pdf, deflate=True, garbage=4)
