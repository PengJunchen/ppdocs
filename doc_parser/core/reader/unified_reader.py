from __future__ import annotations

import json
import logging
from typing import Any, Optional

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.core.reader.llm_client import BaseLLMClient, DummyLLMClient
from doc_parser.core.reader.models import (
    ChapterAnalysis,
    CrossChapterRelation,
    DocumentMetadata,
    LLMReadingResult,
)

logger = logging.getLogger(__name__)

_METADATA_PROMPT = """你是一个文档分析专家。请根据以下文档结构和内容摘要，提取文档级元数据。

## 文档目录
{outline}

## 各章节内容摘要
{summary}

## 任务
请返回严格的JSON格式（不要包含其他文字）：
{{
  "title": "文档标题",
  "subject": "主题领域",
  "summary": "200字以内文档摘要",
  "keywords": ["关键词1", "关键词2"],
  "document_type": "技术报告/学术论文/产品手册/财务报告/其他",
  "language": "zh/en/其他",
  "quality_assessment": "高/中/低"
}}"""

_CHAPTER_PROMPT = """你是一个文档分析专家。请分析以下章节内容，提取核心信息。

## 章节标题
{title}

## 章节内容
{content}

## 任务
请返回严格的JSON格式（不要包含其他文字）：
{{
  "summary": "100字以内章节摘要",
  "key_points": ["要点1", "要点2", "要点3"],
  "entities": ["实体1", "实体2"],
  "relations": [
    {{"subject": "实体A", "predicate": "关系", "object": "实体B"}}
  ]
}}"""

_CROSS_CHAPTER_PROMPT = """你是一个文档分析专家。请分析以下各章节摘要，提取跨章节的关联关系。

## 各章节摘要
{chapter_summaries}

## 任务
请返回严格的JSON格式（不要包含其他文字）：
{{
  "relations": [
    {{
      "source": "章节A标题",
      "target": "章节B标题",
      "relation_type": "引用/依赖/对比/补充",
      "description": "关系描述"
    }}
  ]
}}"""


class UnifiedReaderConfig:
    def __init__(
        self,
        content_preview_length: int = 500,
        max_images_per_chapter: int = 3,
        enable_metadata: bool = True,
        enable_chapter_analysis: bool = True,
        enable_cross_chapter: bool = True,
    ):
        self.content_preview_length = content_preview_length
        self.max_images_per_chapter = max_images_per_chapter
        self.enable_metadata = enable_metadata
        self.enable_chapter_analysis = enable_chapter_analysis
        self.enable_cross_chapter = enable_cross_chapter


class UnifiedReader:
    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        config: Optional[UnifiedReaderConfig] = None,
    ):
        self._llm = llm_client or DummyLLMClient()
        self._config = config or UnifiedReaderConfig()

    async def read_document(self, outline: DocumentOutline) -> LLMReadingResult:
        result = LLMReadingResult()

        if self._config.enable_metadata:
            result.metadata = await self._extract_metadata(outline)

        if self._config.enable_chapter_analysis:
            result.chapters = await self._analyze_chapters(outline)

        if self._config.enable_cross_chapter and result.chapters:
            result.cross_chapter_relations = await self._extract_cross_chapter(outline, result.chapters)

        return result

    async def _extract_metadata(self, outline: DocumentOutline) -> DocumentMetadata:
        outline_text = self._format_outline(outline)
        summary_text = self._build_document_summary(outline)

        prompt = _METADATA_PROMPT.format(outline=outline_text, summary=summary_text)
        messages = [{"role": "user", "content": prompt}]

        response = await self._llm.chat(messages)
        if not response:
            return DocumentMetadata()

        return self._parse_metadata(response)

    async def _analyze_chapters(self, outline: DocumentOutline) -> list[ChapterAnalysis]:
        chapters = outline.get_all_chapters()
        analyses: list[ChapterAnalysis] = []

        for chapter in chapters:
            if not chapter.markdown and not chapter.element_indices:
                continue

            content = chapter.markdown[:2000] if chapter.markdown else ""
            images_info = self._format_images_info(chapter)

            full_content = content
            if images_info:
                full_content += f"\n\n## 图片描述\n{images_info}"

            prompt = _CHAPTER_PROMPT.format(title=chapter.title, content=full_content)
            messages = [{"role": "user", "content": prompt}]

            response = await self._llm.chat(messages)
            analysis = self._parse_chapter_analysis(response, chapter.id)
            analyses.append(analysis)

        return analyses

    async def _extract_cross_chapter(
        self, outline: DocumentOutline, chapter_analyses: list[ChapterAnalysis]
    ) -> list[CrossChapterRelation]:
        summaries = []
        for ca in chapter_analyses:
            summaries.append(f"- {ca.chapter_id}: {ca.summary}")

        chapter_summaries = "\n".join(summaries)
        prompt = _CROSS_CHAPTER_PROMPT.format(chapter_summaries=chapter_summaries)
        messages = [{"role": "user", "content": prompt}]

        response = await self._llm.chat(messages)
        if not response:
            return []

        return self._parse_cross_chapter(response)

    def _format_outline(self, outline: DocumentOutline) -> str:
        lines: list[str] = []
        for node in outline.nodes:
            self._format_node(node, 0, lines)
        return "\n".join(lines)

    def _format_node(self, node: OutlineNode, depth: int, lines: list[str]) -> None:
        indent = "  " * depth
        page_end = node.page_end if node.page_end is not None else "?"
        lines.append(f"{indent}- {node.title} (页{node.page_start}-{page_end})")
        for child in node.children:
            self._format_node(child, depth + 1, lines)

    def _build_document_summary(self, outline: DocumentOutline) -> str:
        parts: list[str] = []
        for chapter in outline.get_all_chapters():
            preview = ""
            if chapter.markdown:
                preview = chapter.markdown[: self._config.content_preview_length]
            else:
                preview = "(无内容)"

            images_info = self._format_images_info(chapter)

            section = f"### {chapter.title} (第{chapter.page_start}-{chapter.page_end or '?'}页)\n{preview}"
            if images_info:
                section += f"\n{images_info}"
            parts.append(section)

        return "\n\n".join(parts)

    def _format_images_info(self, chapter: OutlineNode) -> str:
        images_data = chapter.metadata.get("images", [])
        if not images_data:
            return ""

        parts: list[str] = []
        for img in images_data[: self._config.max_images_per_chapter]:
            desc = ""
            if isinstance(img, dict):
                vlm = img.get("vlm_description", {})
                if isinstance(vlm, dict):
                    desc = vlm.get("description", "")[:100]
                ocr = img.get("ocr", {})
                if isinstance(ocr, dict) and ocr.get("text"):
                    desc += f" [OCR: {ocr['text'][:50]}]"
            if desc:
                parts.append(f"  - [图片]: {desc}")

        return "\n".join(parts)

    def _parse_metadata(self, response: str) -> DocumentMetadata:
        try:
            data = self._extract_json(response)
            if data:
                return DocumentMetadata(
                    title=data.get("title", ""),
                    subject=data.get("subject", ""),
                    summary=data.get("summary", ""),
                    keywords=data.get("keywords", []),
                    document_type=data.get("document_type", ""),
                    language=data.get("language", ""),
                    quality_assessment=data.get("quality_assessment", ""),
                )
        except Exception as exc:
            logger.warning("Failed to parse metadata: %s", exc)

        return DocumentMetadata()

    def _parse_chapter_analysis(self, response: str, chapter_id: str) -> ChapterAnalysis:
        if not response:
            return ChapterAnalysis(chapter_id=chapter_id)

        try:
            data = self._extract_json(response)
            if data:
                return ChapterAnalysis(
                    chapter_id=chapter_id,
                    summary=data.get("summary", ""),
                    key_points=data.get("key_points", []),
                    entities=data.get("entities", []),
                    relations=data.get("relations", []),
                )
        except Exception as exc:
            logger.warning("Failed to parse chapter analysis for %s: %s", chapter_id, exc)

        return ChapterAnalysis(chapter_id=chapter_id)

    def _parse_cross_chapter(self, response: str) -> list[CrossChapterRelation]:
        try:
            data = self._extract_json(response)
            if data and "relations" in data:
                relations = []
                for r in data["relations"]:
                    relations.append(CrossChapterRelation(
                        source=r.get("source", ""),
                        target=r.get("target", ""),
                        relation_type=r.get("relation_type", ""),
                        description=r.get("description", ""),
                    ))
                return relations
        except Exception as exc:
            logger.warning("Failed to parse cross-chapter relations: %s", exc)

        return []

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return None
