from __future__ import annotations

import logging
from typing import Any, Optional

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult

logger = logging.getLogger(__name__)


class ChapterSplitter:
    async def split(
        self, result: PipelineResult, outline: DocumentOutline
    ) -> DocumentOutline:
        all_chapters = outline.get_all_chapters()

        if not all_chapters:
            if not outline.nodes:
                outline.nodes = [
                    OutlineNode(id="ch_0", title="全文", level=1, page_start=0)
                ]
            outline.nodes[0].element_indices = list(range(len(result.content_list)))
            outline.nodes[0].markdown = result.markdown
            self._count_types(outline.nodes[0], result)
            return outline

        for chapter in all_chapters:
            chapter.element_indices = []

        for idx, item in enumerate(result.content_list):
            chapter = self._find_chapter_for_item(item, outline, all_chapters, idx)
            if chapter:
                chapter.element_indices.append(idx)

        for chapter in all_chapters:
            self._assign_unowned(chapter, result, outline)

        for chapter in all_chapters:
            self._count_types(chapter, result)

        for chapter in all_chapters:
            chapter.markdown = self._build_chapter_markdown(chapter, result)

        return outline

    def _find_chapter_for_item(
        self,
        item: ContentItem,
        outline: DocumentOutline,
        all_chapters: list[OutlineNode],
        item_idx: int,
    ) -> Optional[OutlineNode]:
        page = item.page_idx

        if item.text_level > 0:
            for chapter in all_chapters:
                if (
                    chapter.page_start == page
                    and chapter.title.strip().lower() == item.text.strip().lower()
                ):
                    return self._find_deepest_leaf(chapter)

        exact = outline.get_chapter_by_page(page)
        if exact:
            return self._find_deepest_leaf(exact)

        closest = None
        closest_start = -1
        for chapter in all_chapters:
            if chapter.page_start <= page and chapter.page_start > closest_start:
                closest = chapter
                closest_start = chapter.page_start

        if closest:
            return self._find_deepest_leaf(closest)

        if all_chapters:
            return all_chapters[-1]

        return None

    @staticmethod
    def _find_deepest_leaf(node: OutlineNode) -> OutlineNode:
        current = node
        while current.children:
            current = current.children[-1]
        return current

    def _assign_unowned(
        self, chapter: OutlineNode, result: PipelineResult, outline: DocumentOutline
    ) -> None:
        if not chapter.element_indices:
            owned = set()
            for ch in outline.get_all_chapters():
                owned.update(ch.element_indices)
            for idx, item in enumerate(result.content_list):
                if idx in owned:
                    continue
                if item.page_idx >= chapter.page_start and (
                    chapter.page_end is None or item.page_idx <= chapter.page_end
                ):
                    chapter.element_indices.append(idx)

    def _count_types(
        self, chapter: OutlineNode, result: PipelineResult
    ) -> None:
        img = tbl = eq = 0
        for idx in chapter.element_indices:
            if idx < len(result.content_list):
                item = result.content_list[idx]
                if item.type == ElementType.IMAGE:
                    img += 1
                elif item.type == ElementType.TABLE:
                    tbl += 1
                elif item.type == ElementType.EQUATION:
                    eq += 1
        chapter.image_count = img
        chapter.table_count = tbl
        chapter.equation_count = eq

    def _build_chapter_markdown(
        self, chapter: OutlineNode, result: PipelineResult
    ) -> str:
        parts: list[str] = [f"{'#' * chapter.level} {chapter.title}\n"]

        for idx in chapter.element_indices:
            if idx >= len(result.content_list):
                continue
            item = result.content_list[idx]

            if item.type == ElementType.TEXT:
                if item.text_level > 0 and item.text.strip().lower() != chapter.title.strip().lower():
                    parts.append(f"{'#' * item.text_level} {item.text}\n")
                elif item.text_level == 0:
                    parts.append(item.text)
            elif item.type == ElementType.TABLE:
                if item.table_body:
                    parts.append(item.table_body)
                elif item.text:
                    parts.append(item.text)
            elif item.type == ElementType.EQUATION:
                latex = item.text or item.extra.get("latex", "")
                if latex:
                    parts.append(f"$$\n{latex}\n$$")
            elif item.type == ElementType.IMAGE:
                path = item.img_path or item.extra.get("path", "")
                caption = ""
                if item.image_caption:
                    caption = item.image_caption[0]
                alt = caption or "图片"
                parts.append(f"![{alt}]({path})")
            elif item.type == ElementType.CODE:
                body = item.code_body or item.text
                parts.append(f"```\n{body}\n```")
            elif item.type == ElementType.HEADER:
                parts.append(item.text)
            elif item.type == ElementType.LIST:
                for li in item.list_items:
                    parts.append(f"- {li}")
            else:
                if item.text:
                    parts.append(item.text)

        return "\n\n".join(parts)
