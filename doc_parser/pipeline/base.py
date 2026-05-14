from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ElementType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    EQUATION = "equation"
    CHART = "chart"
    CODE = "code"
    HEADER = "header"
    LIST = "list"
    PAGE_FOOTNOTE = "page_footnote"
    PAGE_NUMBER = "page_number"
    UNKNOWN = "unknown"


class ContentItem(BaseModel):
    type: ElementType = ElementType.UNKNOWN
    text: str = ""
    text_level: int = 0
    page_idx: int = 0
    bbox: list[float] = Field(default_factory=list)
    reading_order: int = 0

    img_path: str = ""
    content: str = ""
    sub_type: str = ""
    text_format: str = ""
    code_body: str = ""
    code_caption: list[str] = Field(default_factory=list)
    code_footnote: list[str] = Field(default_factory=list)
    table_body: str = ""
    table_caption: list[str] = Field(default_factory=list)
    table_footnote: list[str] = Field(default_factory=list)
    image_caption: list[str] = Field(default_factory=list)
    image_footnote: list[str] = Field(default_factory=list)
    chart_caption: list[str] = Field(default_factory=list)
    chart_footnote: list[str] = Field(default_factory=list)
    list_items: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class ImageInfo(BaseModel):
    filename: str = ""
    data: str = ""
    source_path: str = ""


class TableInfo(BaseModel):
    html: str = ""
    caption: list[str] = Field(default_factory=list)
    footnote: list[str] = Field(default_factory=list)
    page_idx: int = 0
    bbox: list[float] = Field(default_factory=list)
    img_path: str = ""


class EquationInfo(BaseModel):
    latex: str = ""
    text_format: str = "latex"
    page_idx: int = 0
    bbox: list[float] = Field(default_factory=list)
    img_path: str = ""


class PipelineResult(BaseModel):
    document_id: str = ""
    engine: str = ""
    content_list: list[ContentItem] = Field(default_factory=list)
    markdown: str = ""
    images: list[ImageInfo] = Field(default_factory=list)
    tables: list[TableInfo] = Field(default_factory=list)
    equations: list[EquationInfo] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_result: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class PipelineConfig(BaseModel):
    engine: str = "auto"
    timeout: int = 300
    options: dict[str, Any] = Field(default_factory=dict)
    base_url: str = ""
    api_key: str = ""


class PipelineError(Exception):
    code: str = "PIPELINE_ERROR"
    message: str = ""

    def __init__(self, message: str = "", code: str = "PIPELINE_ERROR"):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class EngineNotFound(PipelineError):
    def __init__(self, engine: str = ""):
        super().__init__(f"Engine not found: {engine}", code="ENGINE_NOT_FOUND")


class ParseFailed(PipelineError):
    def __init__(self, message: str = ""):
        super().__init__(message, code="PARSE_FAILED")


class ParseTimeout(PipelineError):
    def __init__(self, timeout: int = 0):
        super().__init__(f"Parse timeout after {timeout}s", code="PARSE_TIMEOUT")


class FormatNotSupported(PipelineError):
    def __init__(self, fmt: str = ""):
        super().__init__(f"Format not supported: {fmt}", code="FORMAT_NOT_SUPPORTED")


class BasePipeline(ABC):
    engine_name: str = "base"
    supported_formats: list[str] = []

    def __init__(self, config: PipelineConfig):
        self.config = config

    @abstractmethod
    async def parse(self, file_path: str, **kwargs: Any) -> PipelineResult:
        pass

    @abstractmethod
    async def parse_bytes(self, data: bytes, filename: str, **kwargs: Any) -> PipelineResult:
        pass

    def get_supported_formats(self) -> list[str]:
        return list(self.supported_formats)

    def supports_format(self, filename: str) -> bool:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in self.supported_formats

    async def health_check(self) -> bool:
        return True

    def _validate_format(self, filename: str) -> None:
        if not self.supports_format(filename):
            raise FormatNotSupported(
                f"{self.engine_name} does not support: {filename}"
            )
