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
    signature = "signature"
    date = "date"


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
    options: list[str] = Field(default_factory=list)
    group: str = ""
    value: str = ""
    signature_data_url: str = ""


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    page_count: int
    page_sizes: list[tuple[float, float]]
    render_urls: list[str]
    fields: list[FormField]


class ExportRequest(BaseModel):
    fields: list[FormField]


class ExportResponse(BaseModel):
    download_url: str


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
