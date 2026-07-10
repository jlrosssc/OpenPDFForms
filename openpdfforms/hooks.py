from __future__ import annotations

import importlib.util
from pathlib import Path

from .models import FormField, HookContext


HOOKS_PATH = Path("hooks.py")


def _load_hooks_module():
    if not HOOKS_PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location("openpdfforms_user_hooks", HOOKS_PATH)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_field_hooks(fields: list[FormField], context: HookContext) -> list[FormField]:
    module = _load_hooks_module()
    if not module or not hasattr(module, "process_fields"):
        return fields
    processed = module.process_fields(fields, context)
    return [field if isinstance(field, FormField) else FormField.model_validate(field) for field in processed]
