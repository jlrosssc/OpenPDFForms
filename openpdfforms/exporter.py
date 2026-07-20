from __future__ import annotations

import base64
import re
from pathlib import Path

import fitz

from .models import ConditionRule, FieldType, FormField

FIELD_FLAG_READ_ONLY = 1
FIELD_FLAG_REQUIRED = 2
FIELD_FLAG_NO_EXPORT = 4
CHOICE_FLAG_MULTI_SELECT = 1 << 21
ANNOT_FLAG_HIDDEN = 2
ANNOT_FLAG_PRINT = 4
BORDER_STYLES = {
    "solid": "/S",
    "dashed": "/D",
    "beveled": "/B",
    "inset": "/I",
    "underline": "/U",
}
TEXT_ALIGNMENTS = {"left": 0, "center": 1, "right": 2}


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

DATE_FORMATS = {
    "mm/dd/yyyy",
    "m/d/yyyy",
    "yyyy-mm-dd",
    "mmmm d, yyyy",
    "mm/dd/yyyy HH:MM",
    "mm/dd/yyyy h:MM tt",
    "yyyy-mm-dd HH:MM:ss",
}

BUTTON_ACTION_SCRIPTS = {
    "clear_form": "this.resetForm();",
    "print": "this.print({bUI: true, bSilent: false, bShrinkToFit: true});",
    "submit": 'app.alert("Configure a submit URL with a custom Acrobat script before using this button in production.");',
}

BASE_DOCUMENT_TYPES = {FieldType.static_text, FieldType.whiteout, FieldType.static_image}


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


def _date_format(field: FormField) -> str:
    return field.date_format if field.date_format in DATE_FORMATS else "mm/dd/yyyy"


def _date_auto_fill_script(field: FormField) -> str:
    return f'event.value = util.printd("{_date_format(field)}", new Date());'


def _button_action_script(field: FormField, fields: list[FormField]) -> str:
    if field.button_script:
        return field.button_script
    if field.button_action == "reset_page":
        names = [
            _escape_js_string(item.name)
            for item in fields
            if item.page == field.page and item.name != field.name and not item.read_only
        ]
        if not names:
            return ""
        return "this.resetForm([" + ", ".join(f'"{name}"' for name in names) + "]);"
    return BUTTON_ACTION_SCRIPTS.get(field.button_action, "")


def _draw_base_document_object(page: fitz.Page, field: FormField) -> None:
    rect = fitz.Rect(field.x, field.y, field.x + field.width, field.y + field.height)
    if field.type == FieldType.whiteout:
        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
        return
    if field.type == FieldType.static_image:
        if not field.signature_data_url:
            return
        try:
            _header, encoded = field.signature_data_url.split(",", 1)
            page.insert_image(rect, stream=base64.b64decode(encoded), keep_proportion=True, overlay=True)
        except Exception:
            return
        return

    text = field.default_value or field.label or ""
    if not text:
        return
    if field.background_color:
        fill_rgb = _hex_to_rgb(field.background_color)
        if fill_rgb:
            page.draw_rect(rect, color=fill_rgb, fill=fill_rgb, overlay=True)
    page.insert_textbox(
        rect,
        text,
        fontname="helv",
        fontsize=field.font_size or 10,
        color=(0, 0, 0),
        align=TEXT_ALIGNMENTS.get(field.text_alignment, 0),
        overlay=True,
    )


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


def _pdf_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", value)
    return safe or "Choice"


def _strip_catalog_key(doc: fitz.Document, key: str) -> None:
    """Fully delete a top-level key from the document catalog's object text.

    xref_set_key(..., "null") only sets the PDF null object -- spec-equivalent
    to absence, but the key literally remains in the serialized bytes (e.g.
    "/Perms null"). Acrobat has been observed to be stricter here than other
    tools, so keys are excised from the object text entirely rather than
    relying on that equivalence.
    """
    catalog_xref = doc.pdf_catalog()
    catalog_text = doc.xref_object(catalog_xref)
    key_start = catalog_text.find(f"/{key}")
    if key_start == -1:
        return
    cursor = key_start + len(key) + 1
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
        next_key = catalog_text.find("/", cursor)
        cursor = next_key if next_key != -1 else catalog_text.rfind(">>")
    doc.update_object(catalog_xref, catalog_text[:key_start] + catalog_text[cursor:])


def _field_flags(field: FormField) -> int:
    flags = 0
    if field.read_only:
        flags |= FIELD_FLAG_READ_ONLY
    if field.required:
        flags |= FIELD_FLAG_REQUIRED
    if field.no_export:
        flags |= FIELD_FLAG_NO_EXPORT
    return flags


def _apply_widget_pdf_properties(doc: fitz.Document, xref: int, field: FormField) -> None:
    annot_flags = 0
    if field.hidden:
        annot_flags |= ANNOT_FLAG_HIDDEN
    if field.printable and not field.hidden:
        annot_flags |= ANNOT_FLAG_PRINT
    doc.xref_set_key(xref, "F", str(annot_flags))

    if field.default_value:
        escaped_default = _escape_pdf_string(field.default_value)
        doc.xref_set_key(xref, "DV", f"({escaped_default})")
        if not field.value and field.type not in (FieldType.checkbox, FieldType.radio, FieldType.signature, FieldType.initials, FieldType.digital_signature):
            doc.xref_set_key(xref, "V", f"({escaped_default})")

    alignment = TEXT_ALIGNMENTS.get(field.text_alignment)
    if alignment is not None:
        doc.xref_set_key(xref, "Q", str(alignment))

    border_style = BORDER_STYLES.get(field.border_style or "solid")
    if border_style:
        doc.xref_set_key(xref, "BS", f"<< /W 1 /S {border_style} >>")


def export_fillable_pdf(source_pdf: Path, output_pdf: Path, fields: list[FormField]) -> None:
    signature_field_names = [
        field.name for field in fields if field.type in (FieldType.signature, FieldType.initials, FieldType.digital_signature)
    ]

    with fitz.open(source_pdf) as doc:
        # A source PDF may carry catalog-level entries computed for its *original*
        # content that go stale once the document's fields are rebuilt below:
        # - /Perms /UR3: an Adobe "Reader Extensions" usage-rights signature (e.g.
        #   from Adobe LiveCycle) over a specific byte range of the original file.
        #   Verified against a real Adobe-processed form: with this stale signature
        #   present, Acrobat's own field detector ("Prepare a form") found *zero*
        #   fields, despite the AcroForm/Fields structure checking out clean under
        #   independent inspection (PyMuPDF and qpdf both). A broken rights
        #   signature is worse than none.
        # - /OpenAction, /AA: catalog-level actions (e.g. a GoTo view-positioning
        #   action) that can reference page/field state from before the rebuild.
        #   Confirmed harmless in practice (a plain GoTo, no JavaScript) but
        #   triggers an unprompted Acrobat compatibility warning dialog on every
        #   open of an exported form -- unnecessary friction worth removing.
        for key in ("Perms", "OpenAction", "AA"):
            _strip_catalog_key(doc, key)

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

        for field in sorted((item for item in fields if item.type in BASE_DOCUMENT_TYPES), key=lambda item: (item.page, item.y, item.x)):
            _draw_base_document_object(doc[field.page], field)

        for field in sorted(fields, key=lambda item: (item.page, item.tab_order or 0, item.y, item.x)):
            if field.type in BASE_DOCUMENT_TYPES:
                continue
            page = doc[field.page]
            widget = fitz.Widget()
            widget.field_name = field.name
            widget.field_label = field.tooltip or field.label or field.name
            widget.rect = fitz.Rect(field.x, field.y, field.x + field.width, field.y + field.height)
            widget.text_font = "Helv"
            widget.text_fontsize = 0 if field.auto_fit_text and field.type in {FieldType.text, FieldType.date} else field.font_size or 10
            widget.field_flags = _field_flags(field)

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
            elif field.type == FieldType.listbox:
                widget.field_type = fitz.PDF_WIDGET_TYPE_LISTBOX
                widget.choice_values = field.options or [""]
                if field.multi_select:
                    widget.field_flags |= CHOICE_FLAG_MULTI_SELECT
            elif field.type == FieldType.button:
                widget.field_type = getattr(fitz, "PDF_WIDGET_TYPE_BUTTON", fitz.PDF_WIDGET_TYPE_TEXT)
                widget.field_label = widget.field_label or field.label or "Button"
                widget.script = _button_action_script(field, fields)
            elif field.type in (FieldType.signature, FieldType.initials):
                widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
                widget.field_label = widget.field_label or ("Initials" if field.type == FieldType.initials else "Mock Sign")
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
                if field.type == FieldType.date:
                    widget.script_format = f'AFDate_FormatEx("{_date_format(field)}");'
                elif field.format in FORMAT_SCRIPTS:
                    widget.script_format = FORMAT_SCRIPTS[field.format]
                if field.type == FieldType.date and field.date_auto_fill:
                    widget.script_calc = _date_auto_fill_script(field)
                elif field.conditions:
                    # Left editable (no read-only flag) so the field still works as a
                    # plain text field in viewers that don't run PDF JavaScript.
                    widget.script_calc = _build_condition_script(field)
                elif field.calc_operation in CALC_OPERATIONS and field.calc_fields:
                    names = ", ".join(f'"{name}"' for name in field.calc_fields)
                    widget.script_calc = (
                        f'AFSimple_Calculate("{CALC_OPERATIONS[field.calc_operation]}", new Array({names}));'
                    )

            # Designer-authored custom scripts take priority over any preset/generated
            # script above -- entered once at form-creation time (Inspector's Custom
            # Script section), not exposed to whoever later fills the form out. Runs
            # as real Acrobat JavaScript in any viewer that executes PDF JS.
            if field.custom_script_format:
                widget.script_format = field.custom_script_format
            if field.custom_script_validate:
                widget.script_change = field.custom_script_validate
            if field.custom_script_calculate:
                widget.script_calc = field.custom_script_calculate

            annot = page.add_widget(widget)
            _apply_widget_pdf_properties(doc, annot.xref, field)

            if field.type in (FieldType.signature, FieldType.initials, FieldType.digital_signature):
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

        for index, kid_xref in enumerate(kid_xrefs, start=1):
            # PyMuPDF creates every radio widget with the same on-state name
            # (/Yes). In a real radio group those appearance-state names must be
            # distinct; otherwise a viewer can mark multiple kids selected for a
            # single parent value. Use deterministic values so Acrobat JavaScript
            # can test this.getField("group").value against Choice1, Choice2, ...
            on_value = _pdf_name(f"Choice{index}")
            obj = doc.xref_object(kid_xref, compressed=False)
            obj = re.sub(r"(/AP\s*<<\s*/N\s*<<[^>]*?)\s/Yes(\s+\d+\s+0\s+R)", rf"\1 /{on_value}\2", obj, count=1, flags=re.S)
            doc.update_object(kid_xref, obj)
            doc.xref_set_key(kid_xref, "Parent", f"{parent_xref} 0 R")
            doc.xref_set_key(kid_xref, "T", "null")
            doc.xref_set_key(kid_xref, "AS", "/Off")
            doc.xref_set_key(kid_xref, "V", "(Off)")

        ref_numbers = [r for r in ref_numbers if r not in kid_xrefs]
        ref_numbers.append(parent_xref)

    new_fields_pdf = "[ " + " ".join(f"{r} 0 R" for r in ref_numbers) + " ]"
    doc.xref_set_key(acro_xref, "Fields", new_fields_pdf)
