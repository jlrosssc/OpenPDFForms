from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    text = "text"
    checkbox = "checkbox"
    radio = "radio"
    dropdown = "dropdown"
    listbox = "listbox"
    button = "button"
    signature = "signature"
    initials = "initials"
    digital_signature = "digital_signature"
    date = "date"


class ConditionRule(BaseModel):
    source_field: str = ""
    operator: str = "equals"
    value: str = ""
    output: str = ""


class FormField(BaseModel):
    id: str
    page: int = Field(ge=0)
    type: FieldType
    name: str
    x: float
    y: float
    width: float
    height: float
    label: str = ""
    tooltip: str = ""
    required: bool = False
    read_only: bool = False
    hidden: bool = False
    printable: bool = True
    no_export: bool = False
    default_value: str = ""
    button_action: str = ""
    button_script: str = ""
    text_alignment: str = "left"
    border_style: str = "solid"
    tab_order: int = 0
    options: list[str] = Field(default_factory=list)
    group: str = ""
    value: str = ""
    signature_data_url: str = ""
    font_size: float = 10
    auto_fit_text: bool = False
    multiline: bool = False
    comb: bool = False
    max_length: int = 0
    border_color: str = ""
    background_color: str = ""
    format: str = ""
    date_auto_fill: bool = False
    date_format: str = "mm/dd/yyyy"
    calc_operation: str = ""
    calc_fields: list[str] = Field(default_factory=list)
    conditions: list[ConditionRule] = Field(default_factory=list)
    condition_default: str = ""
    custom_script_format: str = ""
    custom_script_validate: str = ""
    custom_script_calculate: str = ""
    multi_select: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    detection_source: str = ""


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    page_count: int
    page_sizes: list[tuple[float, float]]
    render_urls: list[str]
    fields: list[FormField]


class BlankDocumentRequest(BaseModel):
    page_size: str = "letter"
    orientation: str = "portrait"
    page_count: int = Field(default=1, ge=1, le=50)
    filename: str = "Blank Form.pdf"


class ExportRequest(BaseModel):
    fields: list[FormField]


class ExportResponse(BaseModel):
    download_url: str


class PreviewResponse(BaseModel):
    render_urls: list[str]


class FillSignRequest(BaseModel):
    fields: list[FormField]
    sign_field_name: str
    kind: str
    signer_name: str = ""
    reason: str = ""
    location: str = ""
    signature_image_data_url: str = ""


class ProjectSummary(BaseModel):
    document_id: str
    filename: str
    updated_at: str


class ProjectSaveRequest(BaseModel):
    filename: str
    page_count: int
    page_sizes: list[tuple[float, float]]
    render_urls: list[str]
    fields: list[FormField]


class HookContext(BaseModel):
    document_id: str
    source_pdf: Path
    page_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
