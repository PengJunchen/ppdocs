from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class EngineInfo(BaseModel):
    name: str
    supported_formats: list[str]
    healthy: bool = False


class ParseRequest(BaseModel):
    engine: str = "auto"
    timeout: int = 300
    options: dict[str, Any] = Field(default_factory=dict)


class ContentItemResponse(BaseModel):
    type: str = "unknown"
    text: str = ""
    text_level: int = 0
    page_idx: int = 0
    bbox: list[float] = Field(default_factory=list)
    reading_order: int = 0
    img_path: str = ""
    table_body: str = ""
    table_caption: list[str] = Field(default_factory=list)
    table_footnote: list[str] = Field(default_factory=list)
    image_caption: list[str] = Field(default_factory=list)
    text_format: str = ""
    sub_type: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class ImageInfoResponse(BaseModel):
    filename: str = ""
    source_path: str = ""


class TableInfoResponse(BaseModel):
    html: str = ""
    caption: list[str] = Field(default_factory=list)
    footnote: list[str] = Field(default_factory=list)
    page_idx: int = 0


class EquationInfoResponse(BaseModel):
    latex: str = ""
    text_format: str = "latex"
    page_idx: int = 0


class ParseResultResponse(BaseModel):
    document_id: str = ""
    engine: str = ""
    content_list: list[ContentItemResponse] = Field(default_factory=list)
    markdown: str = ""
    images: list[ImageInfoResponse] = Field(default_factory=list)
    tables: list[TableInfoResponse] = Field(default_factory=list)
    equations: list[EquationInfoResponse] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    filename: str = ""
    engine: str = ""
    created_at: str = ""
    updated_at: str = ""
    error: str = ""
    result: Optional[ParseResultResponse] = None
    process_result: Optional[ProcessResponse] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    engines: list[EngineInfo] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    code: str = "ERROR"
    message: str = ""
    detail: str = ""


class OutlineNodeResponse(BaseModel):
    id: str = ""
    title: str = ""
    level: int = 1
    page_start: int = 0
    page_end: Optional[int] = None
    parent_id: Optional[str] = None
    children: list[OutlineNodeResponse] = Field(default_factory=list)
    element_count: int = 0
    markdown: str = ""
    image_count: int = 0
    table_count: int = 0
    equation_count: int = 0


class OutlineResponse(BaseModel):
    document_id: str = ""
    title: str = ""
    nodes: list[OutlineNodeResponse] = Field(default_factory=list)
    total_chapters: int = 0


class SplitResponse(BaseModel):
    outline: OutlineResponse
    element_conservation: dict[str, Any] = Field(default_factory=dict)


class OCRResultResponse(BaseModel):
    text: str = ""
    confidence: float = 0.0
    word_count: int = 0


class VLMDescriptionResponse(BaseModel):
    description: str = ""
    image_type: str = ""
    key_info: list[str] = Field(default_factory=list)
    model: str = ""


class EnhancedImageResponse(BaseModel):
    path: str = ""
    page: int = 0
    bbox: list[float] = Field(default_factory=list)
    ocr: Optional[OCRResultResponse] = None
    vlm_description: Optional[VLMDescriptionResponse] = None
    image_caption: list[str] = Field(default_factory=list)


class ImageEnhanceResponse(BaseModel):
    document_id: str = ""
    enhanced_images: list[EnhancedImageResponse] = Field(default_factory=list)
    total_images: int = 0
    ocr_enabled: bool = False
    vlm_enabled: bool = False


class DocumentMetadataResponse(BaseModel):
    title: str = ""
    subject: str = ""
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    document_type: str = ""
    language: str = ""
    quality_assessment: str = ""


class ChapterAnalysisResponse(BaseModel):
    chapter_id: str = ""
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    relations: list[dict[str, str]] = Field(default_factory=list)


class CrossChapterRelationResponse(BaseModel):
    source: str = ""
    target: str = ""
    relation_type: str = ""
    description: str = ""


class LLMReadResponse(BaseModel):
    document_id: str = ""
    metadata: DocumentMetadataResponse = Field(default_factory=DocumentMetadataResponse)
    chapters: list[ChapterAnalysisResponse] = Field(default_factory=list)
    cross_chapter_relations: list[CrossChapterRelationResponse] = Field(default_factory=list)
    model: str = ""


class KGRelationResponse(BaseModel):
    source: str = ""
    target: str = ""
    relation_type: str = ""
    description: str = ""
    weight: float = 1.0


class KGInsertResultResponse(BaseModel):
    document_id: str = ""
    total_chunks: int = 0
    total_entities: int = 0
    total_relations: int = 0
    insert_time: float = 0.0
    errors: list[str] = Field(default_factory=list)


class KGBuildResponse(BaseModel):
    document_id: str = ""
    total_chapters: int = 0
    total_chunks: int = 0
    insert_results: list[KGInsertResultResponse] = Field(default_factory=list)
    cross_chapter_relations: list[KGRelationResponse] = Field(default_factory=list)
    build_time: float = 0.0
    errors: list[str] = Field(default_factory=list)


class KGQueryRequest(BaseModel):
    query: str = ""
    mode: str = "hybrid"


class KGQueryResponse(BaseModel):
    query: str = ""
    mode: str = "hybrid"
    answer: str = ""
    source_chunks: list[str] = Field(default_factory=list)
    source_entities: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class SearchRequest(BaseModel):
    query: str = ""
    top_k: int = 5
    chapter_id: str = ""
    score_threshold: float = 0.0


class SearchResultResponse(BaseModel):
    chunk_id: str = ""
    text: str = ""
    score: float = 0.0
    document_id: str = ""
    chapter_id: str = ""
    chapter_title: str = ""
    chunk_type: str = "chapter"


class SearchResponse(BaseModel):
    document_id: str = ""
    query: str = ""
    total_results: int = 0
    results: list[SearchResultResponse] = Field(default_factory=list)


class StageResultResponse(BaseModel):
    stage: str = ""
    success: bool = False
    duration: float = 0.0
    error: str = ""


class ProcessResponse(BaseModel):
    document_id: str = ""
    total_duration: float = 0.0
    stages: list[StageResultResponse] = Field(default_factory=list)
    outline: Optional[dict[str, Any]] = None
    enhance_result: Optional[dict[str, Any]] = None
    reading_result: Optional[dict[str, Any]] = None
    kg_result: Optional[dict[str, Any]] = None
    vector_result: Optional[dict[str, Any]] = None
    errors: list[str] = Field(default_factory=list)
