from openpdfforms.models import FormField, HookContext


def process_fields(fields: list[FormField], context: HookContext) -> list[FormField]:
    """Customize detected fields before they appear in the editor.

    Copy this file to hooks.py and adjust naming, filtering, or properties.
    """
    for field in fields:
        if "date" in field.name:
            field.type = "date"
        if "signature" in field.name or "sign" in field.name:
            field.type = "signature"
    return fields
