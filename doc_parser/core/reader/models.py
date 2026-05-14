from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    title: str = ""
    subject: str = ""
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    document_type: str = ""
    language: str = ""
    quality_assessment: str = ""


class ChapterAnalysis(BaseModel):
    chapter_id: str = ""
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    relations: list[dict[str, str]] = Field(default_factory=list)


class CrossChapterRelation(BaseModel):
    source: str = ""
    target: str = ""
    relation_type: str = ""
    description: str = ""


class LLMReadingResult(BaseModel):
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    chapters: list[ChapterAnalysis] = Field(default_factory=list)
    cross_chapter_relations: list[CrossChapterRelation] = Field(default_factory=list)
    model: str = ""
    raw_response: str = ""
