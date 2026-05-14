from __future__ import annotations

import logging
import time
from typing import Any, Optional

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.core.kg.lightrag_adapter import BaseKGBridge, DummyKGBridge
from doc_parser.core.kg.models import (
    KGBuildResult,
    KGInsertResult,
    KGQueryMode,
    KGQueryResult,
    KGRelation,
)
from doc_parser.core.reader.models import CrossChapterRelation

logger = logging.getLogger(__name__)


class KGBuilderConfig:
    def __init__(
        self,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        include_metadata: bool = True,
        include_entities: bool = True,
        max_content_length: int = 8000,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.include_metadata = include_metadata
        self.include_entities = include_entities
        self.max_content_length = max_content_length


class KGBuilder:
    def __init__(
        self,
        kg_bridge: Optional[BaseKGBridge] = None,
        config: Optional[KGBuilderConfig] = None,
    ):
        self._bridge = kg_bridge or DummyKGBridge()
        self._config = config or KGBuilderConfig()

    async def build(
        self,
        outline: DocumentOutline,
        cross_relations: Optional[list[CrossChapterRelation]] = None,
    ) -> KGBuildResult:
        start = time.time()
        chapters = outline.get_all_chapters()
        insert_results: list[KGInsertResult] = []
        errors: list[str] = []
        total_chunks = 0

        for chapter in chapters:
            content = self._build_chapter_content(chapter, outline.document_id)
            if not content.strip():
                continue

            metadata = self._build_chapter_metadata(chapter, outline)

            result = await self._bridge.insert(
                content=content,
                doc_id=outline.document_id,
                metadata=metadata,
            )
            insert_results.append(result)
            total_chunks += result.total_chunks
            errors.extend(result.errors)

        kg_relations: list[KGRelation] = []
        if cross_relations:
            kg_relations = self._build_cross_chapter_relations(
                cross_relations, outline.document_id
            )
            relation_content = self._build_relation_content(kg_relations)
            if relation_content:
                rel_result = await self._bridge.insert(
                    content=relation_content,
                    doc_id=outline.document_id,
                    metadata={"type": "cross_chapter_relations"},
                )
                insert_results.append(rel_result)
                total_chunks += rel_result.total_chunks
                errors.extend(rel_result.errors)

        return KGBuildResult(
            document_id=outline.document_id,
            total_chapters=len(chapters),
            total_chunks=total_chunks,
            insert_results=insert_results,
            cross_chapter_relations=kg_relations,
            build_time=time.time() - start,
            errors=errors,
        )

    async def query(
        self,
        query_text: str,
        mode: KGQueryMode = KGQueryMode.HYBRID,
    ) -> KGQueryResult:
        return await self._bridge.query(query_text, mode=mode)

    def _build_chapter_content(
        self, chapter: OutlineNode, document_id: str
    ) -> str:
        parts: list[str] = []

        header = f"# {chapter.title}"
        if self._config.include_metadata:
            page_info = f" (pages {chapter.page_start}"
            if chapter.page_end is not None:
                page_info += f"-{chapter.page_end}"
            page_info += ")"
            header += page_info
        parts.append(header)

        if chapter.markdown:
            content = chapter.markdown[:self._config.max_content_length]
            parts.append(content)

        images_data = chapter.metadata.get("images", [])
        for img in images_data:
            if isinstance(img, dict):
                desc_parts: list[str] = []
                vlm = img.get("vlm_description", {})
                if isinstance(vlm, dict) and vlm.get("description"):
                    desc_parts.append(vlm["description"])
                ocr = img.get("ocr", {})
                if isinstance(ocr, dict) and ocr.get("text"):
                    desc_parts.append(f"[OCR: {ocr['text'][:200]}]")
                if desc_parts:
                    parts.append(f"[Image: {'; '.join(desc_parts)}]")

        return "\n\n".join(parts)

    def _build_chapter_metadata(
        self, chapter: OutlineNode, outline: DocumentOutline
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "chapter_id": chapter.id,
            "chapter_title": chapter.title,
            "level": chapter.level,
            "page_start": chapter.page_start,
            "page_end": chapter.page_end,
            "document_id": outline.document_id,
        }

        if self._config.include_entities:
            analysis = chapter.metadata.get("analysis", {})
            if isinstance(analysis, dict):
                entities = analysis.get("entities", [])
                if entities:
                    metadata["entities"] = entities

        if chapter.image_count > 0:
            metadata["image_count"] = chapter.image_count
        if chapter.table_count > 0:
            metadata["table_count"] = chapter.table_count

        return metadata

    def _build_cross_chapter_relations(
        self,
        relations: list[CrossChapterRelation],
        document_id: str,
    ) -> list[KGRelation]:
        kg_relations: list[KGRelation] = []
        for r in relations:
            kg_relations.append(KGRelation(
                source=r.source,
                target=r.target,
                relation_type=r.relation_type,
                description=r.description,
                source_id=document_id,
            ))
        return kg_relations

    def _build_relation_content(self, relations: list[KGRelation]) -> str:
        if not relations:
            return ""
        parts: list[str] = ["# Cross-Chapter Relations"]
        for r in relations:
            parts.append(
                f"- {r.source} --[{r.relation_type}]--> {r.target}: {r.description}"
            )
        return "\n".join(parts)
