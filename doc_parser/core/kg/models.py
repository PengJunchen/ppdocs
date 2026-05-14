from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class KGQueryMode(str, Enum):
    NAIVE = "naive"
    LOCAL = "local"
    GLOBAL = "global"
    HYBRID = "hybrid"


class KGEntity(BaseModel):
    name: str = ""
    entity_type: str = ""
    description: str = ""
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGRelation(BaseModel):
    source: str = ""
    target: str = ""
    relation_type: str = ""
    description: str = ""
    weight: float = 1.0
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGInsertResult(BaseModel):
    document_id: str = ""
    total_chunks: int = 0
    total_entities: int = 0
    total_relations: int = 0
    insert_time: float = 0.0
    errors: list[str] = Field(default_factory=list)


class KGQueryResult(BaseModel):
    query: str = ""
    mode: KGQueryMode = KGQueryMode.HYBRID
    answer: str = ""
    source_chunks: list[str] = Field(default_factory=list)
    source_entities: list[str] = Field(default_factory=list)
    source_relations: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class KGBuildResult(BaseModel):
    document_id: str = ""
    total_chapters: int = 0
    total_chunks: int = 0
    insert_results: list[KGInsertResult] = Field(default_factory=list)
    cross_chapter_relations: list[KGRelation] = Field(default_factory=list)
    build_time: float = 0.0
    errors: list[str] = Field(default_factory=list)
