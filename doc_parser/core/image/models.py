from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class OCRResult(BaseModel):
    text: str = ""
    confidence: float = 0.0
    language: str = ""
    word_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class VLMDescriptionResult(BaseModel):
    description: str = ""
    image_type: str = ""
    key_info: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    model: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnhancedImage(BaseModel):
    path: str = ""
    page: int = 0
    bbox: list[float] = Field(default_factory=list)
    ocr: Optional[OCRResult] = None
    vlm_description: Optional[VLMDescriptionResult] = None
    image_caption: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def has_ocr(self) -> bool:
        return self.ocr is not None and bool(self.ocr.text.strip())

    @property
    def has_vlm_description(self) -> bool:
        return self.vlm_description is not None and bool(self.vlm_description.description.strip())
