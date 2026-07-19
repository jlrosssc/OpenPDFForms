from __future__ import annotations

import re
from pathlib import Path

import fitz

from .models import ConditionRule, FieldType, FormField

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


def _escape_js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _condition_js_test(rule: ConditionRule) -> str:
    """Build a null-safe Acrobat JS boolean test for one if/then rule.

    Guards every comparison with a "field exists" check: a rule can
    reference a field that was later renamed or removed, and
    this.getField(...) returning null would otherwise throw inside the
    viewer's JS engine rather than just not matching.
    """
    source = _escape_js_string(rule.source_field)
    value = _escape_js_string(rule.value)
    get = f'this.getField("{source}")'
    if rule.operator == "checked":
        comparison = f'{get}.value == "Yes"'
    elif rule.operator == "not_checked":
        comparison = f'{get}.value != "Yes"'
    elif rule.operator == "empty":
        comparison = f'{get}.value == ""'
    elif rule.operator == "not_empty":
        comparison = f'{get}.value != ""'
    elif rule.operator == "not_equals":
        comparison = f'{get}.value != "{value}"'
    elif rule.operator == "contains":
        comparison = f'{get}.value.indexOf("{value}") !== -1'
    else:
        comparison = f'{get}.value == "{value}"'
    return f'({get} != null && {comparison})'


def _build_condition_script(field: FormField) -> str:
    """Compile a field's if/then rules into an Acrobat-compatible Calculate script.

    Runs only in PDF viewers with a JS engine (Adobe Acrobat/Reader);
    other viewers simply won't execute it, leaving the field as a normal
    editable text field -- see the field_flags note in export_fillable_pdf
    for why it's deliberately left editable rather than read-only.
    """
    lines = []
    for index, rule in enumerate(field.conditions):
        keyword = "if" if index == 0 else "else if"
        output = _escape_js_string(rule.output)
        lines.append(f'{keyword} {_condition_js_test(rule)} {{ event.value = "{output}"; }}')
    default_output = _escape_js_string(field.condition_default)
    lines.append(f'else {{ event.value = "{default_output}"; }}')
    return "\n".join(lines)


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


def _escape_pdf_string(value: str) -> str:
    return value.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def export_fillable_pdf(source_pdf: Path, output_pdf: Path, fields: list[FormField]) -> None:
    signature_field_names = [
        field.name for field in fields if field.type in (FieldType.signature, FieldType.digital_signature)
    ]

    with fitz.open(source_pdf) as doc:
        # A source PDF may carry a /Perms /UR3 entry (Adobe "Reader Extensions"
        # usage-rights signature, e.g. from Adobe LiveCycle) -- a cryptographic
        # signature over a specific byte range of that *original* file. Rebuilding
        # the document's fields (below) completely changes its byte layout, so that
        # signature becomes stale and no longer validates against the new content.
        # Verified against a real Adobe-processed form: Acrobat's own field
        # detector ("Prepare a form") found zero fields in a document carrying this
        # stale signature, despite the AcroForm/Fields structure itself checking out
        # clean under independent inspection. A broken rights signature is worse
        # than none, so it's removed outright rather than left dangling.
        #
        # xref_set_key(..., "null") only sets the value to the PDF null object --
        # spec-equivalent to absence, but the key literally remains in the
        # serialized bytes ("/Perms null"). Given Acrobat is demonstrably stricter
        # here than other tools, the key is fully deleted from the object text
        # instead of relying on that equivalence.
        catalog_xref = doc.pdf_catalog()
        catalog_text = doc.xref_object(catalog_xref)
        perms_start = catalog_text.find("/Perms")
        if perms_start != -1:
            cursor = perms_start + len("/Perms")
            while catalog_text[cursor] in " \t\r\n":
                cursor += 1
            if catalog_text[cursor : cursor + 2] == "<<":
                depth = 0
                while cursor < len(catalog_text):
                    if catalog_text[cursor : cursor + 2] == "<<":
                        depth += 1
                        cursor += 2
                    elif catalog_text[cursor : cursor + 2] == ">>":
                        depth -= 1
                        cursor += 2
                        if depth == 0:
                            break
                    else:
                        cursor += 1
            else:
                cursor = catalog_text.find("/", cursor)
                if cursor == -1:
                    cursor = catalog_text.rfind(">>")
            doc.update_object(catalog_xref, catalog_text[:perms_start] + catalog_text[cursor:])

        # If source_pdf already has its own AcroForm fields (e.g. it was built in
        # Adobe Acrobat and imported via import_existing_fields), strip them first --
        # otherwise every field in `fields` gets added as a *new* widget alongside
        # the original one it came from, doubling every field under the same name.
        for page in doc:
            for widget in list(page.widgets()):
                page.delete_widget(widget)

        # delete_widget() only removes page-level widget *annotations* -- a radio
        # group's parent Field object (which holds /Kids but is not itself a page
        # annotation, so page.widgets() never sees it) is untouched by that loop and
        # is left orphaned in the AcroForm's /Fields array. Verified against a real
        # Acrobat-made form: those leftover parents, still carrying the original
        # field names, coexisted with our freshly-added same-named fields as TWO
        # separate top-level entries -- which is exactly the invalid duplicate-name
        # structure that made Adobe Reader fail to recognize any field in the form.
        # Since the whole field list is rebuilt from `fields` right below, the
        # simplest correct fix is clearing /Fields outright rather than trying to
        # track down every orphan.
        acro_entry = doc.xref_get_key(doc.pdf_catalog(), "AcroForm")
        if acro_entry[0] == "xref":
            doc.xref_set_key(int(acro_entry[1].split()[0]), "Fields", "[]")

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
                if field.conditions:
                    # Left editable (no read-only flag) so the field still works as a
                    # plain text field in viewers that don't run PDF JavaScript.
                    widget.script_calc = _build_condition_script(field)
                elif field.calc_operation in CALC_OPERATIONS and field.calc_fields:
                    names = ", ".join(f'"{name}"' for name in field.calc_fields)
                    widget.script_calc = (
                        f'AFSimple_Calculate("{CALC_OPERATIONS[field.calc_operation]}", new Array({names}));'
                    )

            annot = page.add_widget(widget)

            if field.type in (FieldType.signature, FieldType.digital_signature):
                # SigFieldLock: tells any spec-compliant viewer (Acrobat, Reader, etc.)
                # to lock other fields the moment *this* field is actually signed with a
                # real digital ID -- entirely client-side, no dependency on this app's
                # own server-side signing. Excludes other signature fields (rather than
                # locking everything) so a form with multiple signature lines can still
                # be signed by different people at different times.
                other_names = [name for name in signature_field_names if name != field.name]
                names_pdf = " ".join(f"({_escape_pdf_string(name)})" for name in other_names)
                doc.xref_set_key(annot.xref, "Lock", f"<< /Type /SigFieldLock /Action /Exclude /Fields [{names_pdf}] >>")

        _consolidate_radio_groups(doc)

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_pdf, deflate=True, garbage=4)


def _consolidate_radio_groups(doc: fitz.Document) -> None:
    """Merge same-named radio button widgets into one proper parent/Kids field.

    add_widget() creates each radio button as an independent top-level
    field; several widgets sharing the same /T (name) with no parent/kids
    relationship is ambiguous AcroForm structure. Verified against a real
    exported form: Adobe Reader failed to recognize *any* field in a
    document with this defect, while a more lenient viewer (PDF Expert)
    tolerated it. A real radio group needs one parent /FT /Btn field with
    /Kids pointing at each button annotation, and the kids carry no /T of
    their own (they inherit the parent's).
    """
    groups: dict[str, list[int]] = {}
    for page in doc:
        for widget in page.widgets():
            if widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                groups.setdefault(widget.field_name, []).append(widget.xref)
    groups = {name: xrefs for name, xrefs in groups.items() if len(xrefs) > 1}
    if not groups:
        return

    catalog = doc.pdf_catalog()
    acro_entry = doc.xref_get_key(catalog, "AcroForm")
    if acro_entry[0] == "xref":
        acro_xref = int(acro_entry[1].split()[0])
    else:
        # Inline AcroForm dict -- promote it to an indirect object first so its
        # /Fields array can be edited the same way regardless of which form it
        # started in.
        acro_xref = doc.get_new_xref()
        doc.update_object(acro_xref, acro_entry[1])
        doc.xref_set_key(catalog, "AcroForm", f"{acro_xref} 0 R")

    fields_str = doc.xref_get_key(acro_xref, "Fields")[1]
    ref_numbers = [int(n) for n in re.findall(r"(\d+) 0 R", fields_str)]

    for name, kid_xrefs in groups.items():
        parent_xref = doc.get_new_xref()
        doc.update_object(parent_xref, "<<>>")
        kid_refs_pdf = " ".join(f"{x} 0 R" for x in kid_xrefs)
        doc.xref_set_key(parent_xref, "FT", "/Btn")
        doc.xref_set_key(parent_xref, "T", f"({_escape_pdf_string(name)})")
        doc.xref_set_key(parent_xref, "Ff", "32768")
        doc.xref_set_key(parent_xref, "V", "/Off")
        doc.xref_set_key(parent_xref, "Kids", f"[{kid_refs_pdf}]")

        for kid_xref in kid_xrefs:
            doc.xref_set_key(kid_xref, "Parent", f"{parent_xref} 0 R")
            doc.xref_set_key(kid_xref, "T", "null")

        ref_numbers = [r for r in ref_numbers if r not in kid_xrefs]
        ref_numbers.append(parent_xref)

    new_fields_pdf = "[ " + " ".join(f"{r} 0 R" for r in ref_numbers) + " ]"
    doc.xref_set_key(acro_xref, "Fields", new_fields_pdf)
