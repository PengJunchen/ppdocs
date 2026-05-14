from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult

logger = logging.getLogger(__name__)


class BaseTOCStrategy(ABC):
    @abstractmethod
    async def extract(self, result: PipelineResult) -> DocumentOutline:
        pass

    @staticmethod
    def _make_default_outline(doc_id: str) -> DocumentOutline:
        return DocumentOutline(
            document_id=doc_id,
            nodes=[OutlineNode(id="ch_0", title="全文", level=1, page_start=0)],
        )


class StrategyA_TitleAggregation(BaseTOCStrategy):
    async def extract(self, result: PipelineResult) -> DocumentOutline:
        outline = DocumentOutline(document_id=result.document_id)
        title_items = [
            {
                "title": item.text,
                "level": item.text_level,
                "page_idx": item.page_idx,
                "reading_order": item.reading_order,
            }
            for item in result.content_list
            if item.text_level > 0
        ]

        if not title_items:
            return self._make_default_outline(result.document_id)

        outline.nodes = self._build_tree(title_items)
        return outline

    def _build_tree(self, items: list[dict]) -> list[OutlineNode]:
        root_nodes: list[OutlineNode] = []
        stack: list[tuple[int, OutlineNode]] = []
        counter = 0

        for item in items:
            node = OutlineNode(
                id=f"ch_{counter}",
                title=item["title"],
                level=item["level"],
                page_start=item["page_idx"],
            )
            counter += 1

            while stack and stack[-1][0] >= item["level"]:
                stack.pop()

            if stack:
                parent = stack[-1][1]
                parent.children.append(node)
                node.parent_id = parent.id
            else:
                root_nodes.append(node)

            stack.append((item["level"], node))

        self._fill_page_ends(root_nodes)
        return root_nodes

    def _fill_page_ends(self, nodes: list[OutlineNode]) -> None:
        all_chapters: list[OutlineNode] = []

        def _collect(ns: list[OutlineNode]) -> None:
            for n in ns:
                all_chapters.append(n)
                _collect(n.children)

        _collect(nodes)

        for i, chapter in enumerate(all_chapters):
            if i + 1 < len(all_chapters):
                chapter.page_end = all_chapters[i + 1].page_start - 1
            else:
                chapter.page_end = None


class StrategyB_IndexBlockParsing(BaseTOCStrategy):
    async def extract(self, result: PipelineResult) -> DocumentOutline:
        outline = DocumentOutline(document_id=result.document_id)

        index_items = [
            item for item in result.content_list
            if item.extra.get("block_type") == "index"
            or item.sub_type == "index"
        ]

        if index_items:
            entries = self._parse_index_items(index_items)
            if entries:
                outline.nodes = self._build_from_entries(entries)
                if outline.nodes:
                    return outline

        return await StrategyA_TitleAggregation().extract(result)

    def _parse_index_items(self, items: list[ContentItem]) -> list[dict]:
        entries = []
        for item in items:
            page_num = self._extract_page_number(item.text)
            level = item.text_level if item.text_level > 0 else 1
            entries.append({
                "title": item.text,
                "level": level,
                "page_num": page_num,
            })
        return entries

    @staticmethod
    def _extract_page_number(text: str) -> int:
        import re
        match = re.search(r'(\d+)\s*$', text.strip())
        if match:
            num = int(match.group(1))
            if 1 <= num <= 9999:
                return num
        return 0

    def _build_from_entries(self, entries: list[dict]) -> list[OutlineNode]:
        if not entries:
            return []
        root_nodes: list[OutlineNode] = []
        stack: list[tuple[int, OutlineNode]] = []
        counter = 0

        for entry in entries:
            node = OutlineNode(
                id=f"ch_{counter}",
                title=entry["title"],
                level=entry["level"],
                page_start=entry.get("page_num", 0),
            )
            counter += 1

            while stack and stack[-1][0] >= entry["level"]:
                stack.pop()

            if stack:
                parent = stack[-1][1]
                parent.children.append(node)
                node.parent_id = parent.id
            else:
                root_nodes.append(node)

            stack.append((entry["level"], node))

        StrategyA_TitleAggregation()._fill_page_ends(root_nodes)
        return root_nodes


class StrategyC_LLMEnhanced(BaseTOCStrategy):
    def __init__(self, llm_client: Any = None):
        self.llm = llm_client

    async def extract(self, result: PipelineResult) -> DocumentOutline:
        strategy_a = StrategyA_TitleAggregation()
        initial = await strategy_a.extract(result)

        if not initial.nodes or not self.llm:
            return initial

        titles = [
            {"text": ch.title, "page": ch.page_start}
            for ch in initial.get_all_chapters()
        ]

        if not titles:
            return initial

        try:
            optimized = await self._llm_optimize_hierarchy(titles)
            outline = DocumentOutline(document_id=result.document_id)
            outline.nodes = self._build_from_llm_result(optimized)
            if outline.nodes:
                return outline
        except Exception as exc:
            logger.warning("LLM optimization failed: %s", exc)

        return initial

    async def _llm_optimize_hierarchy(self, titles: list[dict]) -> list[dict]:
        if not self.llm:
            return titles

        import json
        prompt = (
            "请分析以下文档标题列表，为每个标题分配正确的层级编号。\n"
            "层级规则：1级=章，2级=节，3级=小节，层级必须连续\n\n"
            f"标题列表：\n{json.dumps(titles, ensure_ascii=False, indent=2)}\n\n"
            '请返回JSON格式：[{"title": "...", "level": 1, "page": 1}]'
        )
        response = await self.llm.chat(prompt)
        return json.loads(response)

    def _build_from_llm_result(self, items: list[dict]) -> list[OutlineNode]:
        if not items:
            return []
        root_nodes: list[OutlineNode] = []
        stack: list[tuple[int, OutlineNode]] = []
        counter = 0

        for item in items:
            node = OutlineNode(
                id=f"ch_{counter}",
                title=item.get("title", ""),
                level=item.get("level", 1),
                page_start=item.get("page", 0),
            )
            counter += 1

            while stack and stack[-1][0] >= node.level:
                stack.pop()

            if stack:
                parent = stack[-1][1]
                parent.children.append(node)
                node.parent_id = parent.id
            else:
                root_nodes.append(node)

            stack.append((node.level, node))

        StrategyA_TitleAggregation()._fill_page_ends(root_nodes)
        return root_nodes


class TOCExtractor:
    def __init__(self, llm_client: Any = None):
        self.strategies: list[BaseTOCStrategy] = [
            StrategyB_IndexBlockParsing(),
            StrategyA_TitleAggregation(),
        ]
        if llm_client:
            self.strategies.append(StrategyC_LLMEnhanced(llm_client))

    async def extract(self, result: PipelineResult) -> DocumentOutline:
        for strategy in self.strategies:
            outline = await strategy.extract(result)
            if outline.nodes:
                return outline

        return BaseTOCStrategy._make_default_outline(result.document_id)
