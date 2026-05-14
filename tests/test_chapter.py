from __future__ import annotations

import pytest

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.core.chapter.toc import (
    StrategyA_TitleAggregation,
    StrategyB_IndexBlockParsing,
    TOCExtractor,
)
from doc_parser.core.chapter.splitter import ChapterSplitter
from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult


def _make_result(
    doc_id: str = "test-doc",
    items: list[ContentItem] | None = None,
    markdown: str = "",
) -> PipelineResult:
    if items is None:
        items = []
    return PipelineResult(
        document_id=doc_id,
        engine="test-engine",
        content_list=items,
        markdown=markdown,
    )


def _make_heading(text: str, level: int, page: int = 0, order: int = 0) -> ContentItem:
    return ContentItem(
        type=ElementType.TEXT,
        text=text,
        text_level=level,
        page_idx=page,
        reading_order=order,
    )


def _make_text(text: str, page: int = 0, order: int = 0) -> ContentItem:
    return ContentItem(
        type=ElementType.TEXT,
        text=text,
        text_level=0,
        page_idx=page,
        reading_order=order,
    )


def _make_image(page: int = 0, order: int = 0) -> ContentItem:
    return ContentItem(
        type=ElementType.IMAGE,
        text="",
        img_path="img.png",
        page_idx=page,
        reading_order=order,
    )


def _make_table(page: int = 0, order: int = 0) -> ContentItem:
    return ContentItem(
        type=ElementType.TABLE,
        text="",
        table_body="<table><tr><td>data</td></tr></table>",
        page_idx=page,
        reading_order=order,
    )


def _make_equation(page: int = 0, order: int = 0) -> ContentItem:
    return ContentItem(
        type=ElementType.EQUATION,
        text="E=mc^2",
        page_idx=page,
        reading_order=order,
    )


class TestOutlineNode:
    def test_create_node(self):
        node = OutlineNode(id="ch_0", title="Chapter 1", level=1, page_start=0)
        assert node.id == "ch_0"
        assert node.title == "Chapter 1"
        assert node.children == []
        assert node.element_indices == []
        assert node.is_leaf()

    def test_nested_children(self):
        child = OutlineNode(id="ch_1", title="Section 1.1", level=2)
        parent = OutlineNode(id="ch_0", title="Chapter 1", level=1, children=[child])
        assert not parent.is_leaf()
        assert len(parent.children) == 1
        assert parent.children[0].title == "Section 1.1"

    def test_get_all_descendants(self):
        c1 = OutlineNode(id="1", title="S1", level=2)
        c2 = OutlineNode(id="2", title="S2", level=2)
        c1_1 = OutlineNode(id="3", title="S1.1", level=3)
        c1.children = [c1_1]
        root = OutlineNode(id="0", title="Ch1", level=1, children=[c1, c2])
        descs = root.get_all_descendants()
        assert len(descs) == 3
        assert [d.title for d in descs] == ["S1", "S1.1", "S2"]

    def test_serialization(self):
        node = OutlineNode(
            id="ch_0", title="Ch1", level=1,
            children=[OutlineNode(id="ch_1", title="S1.1", level=2)],
        )
        data = node.model_dump()
        assert data["title"] == "Ch1"
        assert len(data["children"]) == 1
        restored = OutlineNode.model_validate(data)
        assert restored.title == "Ch1"
        assert len(restored.children) == 1


class TestDocumentOutline:
    def test_empty_outline(self):
        outline = DocumentOutline(document_id="doc1")
        assert outline.nodes == []
        assert outline.total_chapters == 0

    def test_get_all_chapters(self):
        c1 = OutlineNode(id="1", title="Ch1", level=1)
        c1_1 = OutlineNode(id="2", title="S1.1", level=2)
        c2 = OutlineNode(id="3", title="Ch2", level=1)
        c1.children = [c1_1]
        outline = DocumentOutline(document_id="doc1", nodes=[c1, c2])
        chapters = outline.get_all_chapters()
        assert len(chapters) == 3
        assert outline.total_chapters == 3

    def test_total_chapters_updates_after_node_assignment(self):
        outline = DocumentOutline(document_id="doc1")
        assert outline.total_chapters == 0
        outline.nodes = [OutlineNode(id="1", title="Ch1", level=1)]
        assert outline.total_chapters == 1

    def test_get_chapter_by_page(self):
        c1 = OutlineNode(id="1", title="Ch1", level=1, page_start=0, page_end=4)
        c2 = OutlineNode(id="2", title="Ch2", level=1, page_start=5, page_end=9)
        outline = DocumentOutline(nodes=[c1, c2])
        assert outline.get_chapter_by_page(2) is c1
        assert outline.get_chapter_by_page(7) is c2
        assert outline.get_chapter_by_page(15) is None

    def test_get_leaf_chapters(self):
        c1 = OutlineNode(id="1", title="Ch1", level=1)
        c1_1 = OutlineNode(id="2", title="S1.1", level=2)
        c2 = OutlineNode(id="3", title="Ch2", level=1)
        c1.children = [c1_1]
        outline = DocumentOutline(nodes=[c1, c2])
        leaves = outline.get_leaf_chapters()
        assert len(leaves) == 2
        titles = [l.title for l in leaves]
        assert "S1.1" in titles
        assert "Ch2" in titles

    def test_to_tree_dict(self):
        c1 = OutlineNode(id="1", title="Ch1", level=1)
        outline = DocumentOutline(document_id="d1", nodes=[c1])
        d = outline.to_tree_dict()
        assert d["document_id"] == "d1"
        assert len(d["nodes"]) == 1


class TestStrategyA:
    @pytest.mark.asyncio
    async def test_no_headings_returns_default(self):
        items = [_make_text("hello"), _make_text("world")]
        result = _make_result(items=items)
        strategy = StrategyA_TitleAggregation()
        outline = await strategy.extract(result)
        assert len(outline.nodes) == 1
        assert outline.nodes[0].title == "全文"

    @pytest.mark.asyncio
    async def test_flat_headings(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_text("content 1", 0, 1),
            _make_heading("Chapter 2", 1, 2, 2),
            _make_text("content 2", 2, 3),
        ]
        result = _make_result(items=items)
        strategy = StrategyA_TitleAggregation()
        outline = await strategy.extract(result)
        assert len(outline.nodes) == 2
        assert outline.nodes[0].title == "Chapter 1"
        assert outline.nodes[1].title == "Chapter 2"

    @pytest.mark.asyncio
    async def test_nested_headings(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_heading("Section 1.1", 2, 1, 1),
            _make_text("content", 1, 2),
            _make_heading("Section 1.2", 2, 3, 3),
            _make_heading("Chapter 2", 1, 4, 4),
        ]
        result = _make_result(items=items)
        strategy = StrategyA_TitleAggregation()
        outline = await strategy.extract(result)
        assert len(outline.nodes) == 2
        assert outline.nodes[0].title == "Chapter 1"
        assert len(outline.nodes[0].children) == 2
        assert outline.nodes[0].children[0].title == "Section 1.1"
        assert outline.nodes[0].children[1].title == "Section 1.2"
        assert outline.nodes[1].title == "Chapter 2"

    @pytest.mark.asyncio
    async def test_deep_nesting(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_heading("Section 1.1", 2, 1, 1),
            _make_heading("Sub 1.1.1", 3, 2, 2),
            _make_heading("Sub 1.1.2", 3, 3, 3),
            _make_heading("Section 1.2", 2, 4, 4),
        ]
        result = _make_result(items=items)
        strategy = StrategyA_TitleAggregation()
        outline = await strategy.extract(result)
        ch1 = outline.nodes[0]
        assert ch1.title == "Chapter 1"
        s11 = ch1.children[0]
        assert s11.title == "Section 1.1"
        assert len(s11.children) == 2
        assert s11.children[0].title == "Sub 1.1.1"

    @pytest.mark.asyncio
    async def test_page_ends_filled(self):
        items = [
            _make_heading("Ch1", 1, 0, 0),
            _make_heading("Ch2", 1, 5, 1),
            _make_heading("Ch3", 1, 10, 2),
        ]
        result = _make_result(items=items)
        strategy = StrategyA_TitleAggregation()
        outline = await strategy.extract(result)
        assert outline.nodes[0].page_end == 4
        assert outline.nodes[1].page_end == 9
        assert outline.nodes[2].page_end is None


class TestStrategyB:
    @pytest.mark.asyncio
    async def test_fallback_to_strategy_a(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_text("content", 0, 1),
        ]
        result = _make_result(items=items)
        strategy = StrategyB_IndexBlockParsing()
        outline = await strategy.extract(result)
        assert len(outline.nodes) == 1
        assert outline.nodes[0].title == "Chapter 1"

    @pytest.mark.asyncio
    async def test_page_number_extraction(self):
        strategy = StrategyB_IndexBlockParsing()
        assert strategy._extract_page_number("Introduction ........... 5") == 5
        assert strategy._extract_page_number("Chapter 1   12") == 12
        assert strategy._extract_page_number("No number here") == 0
        assert strategy._extract_page_number("Page 99999") == 0

    @pytest.mark.asyncio
    async def test_index_block_parsing(self):
        idx_item = ContentItem(
            type=ElementType.TEXT,
            text="Introduction ........... 5",
            text_level=1,
            page_idx=0,
            reading_order=0,
            extra={"block_type": "index"},
        )
        result = _make_result(items=[idx_item])
        strategy = StrategyB_IndexBlockParsing()
        outline = await strategy.extract(result)
        assert len(outline.nodes) == 1
        assert outline.nodes[0].title == "Introduction ........... 5"
        assert outline.nodes[0].page_start == 5


class TestTOCExtractor:
    @pytest.mark.asyncio
    async def test_extractor_uses_strategies_in_order(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_text("content", 0, 1),
            _make_heading("Chapter 2", 1, 2, 2),
        ]
        result = _make_result(items=items)
        extractor = TOCExtractor()
        outline = await extractor.extract(result)
        assert len(outline.nodes) == 2
        assert outline.nodes[0].title == "Chapter 1"

    @pytest.mark.asyncio
    async def test_extractor_empty_returns_default(self):
        result = _make_result(items=[])
        extractor = TOCExtractor()
        outline = await extractor.extract(result)
        assert len(outline.nodes) == 1
        assert outline.nodes[0].title == "全文"

    @pytest.mark.asyncio
    async def test_extractor_with_llm(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
        ]
        result = _make_result(items=items)
        extractor = TOCExtractor(llm_client=None)
        outline = await extractor.extract(result)
        assert len(outline.nodes) == 1


class TestChapterSplitter:
    @pytest.mark.asyncio
    async def test_empty_result(self):
        result = _make_result(items=[])
        outline = DocumentOutline(document_id="d1", nodes=[])
        splitter = ChapterSplitter()
        result_outline = await splitter.split(result, outline)
        assert len(result_outline.nodes) == 1
        assert result_outline.nodes[0].title == "全文"

    @pytest.mark.asyncio
    async def test_single_chapter(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_text("content", 0, 1),
            _make_text("more content", 0, 2),
        ]
        result = _make_result(items=items)
        outline = DocumentOutline(
            document_id="d1",
            nodes=[OutlineNode(id="ch_0", title="Chapter 1", level=1, page_start=0)],
        )
        splitter = ChapterSplitter()
        result_outline = await splitter.split(result, outline)
        ch = result_outline.get_all_chapters()[0]
        assert len(ch.element_indices) == 3

    @pytest.mark.asyncio
    async def test_multiple_chapters_page_assignment(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_text("ch1 content", 0, 1),
            _make_heading("Chapter 2", 1, 5, 2),
            _make_text("ch2 content", 5, 3),
        ]
        result = _make_result(items=items)
        outline = DocumentOutline(
            document_id="d1",
            nodes=[
                OutlineNode(id="ch_0", title="Chapter 1", level=1, page_start=0, page_end=4),
                OutlineNode(id="ch_1", title="Chapter 2", level=1, page_start=5),
            ],
        )
        splitter = ChapterSplitter()
        result_outline = await splitter.split(result, outline)
        ch1 = result_outline.nodes[0]
        ch2 = result_outline.nodes[1]
        assert len(ch1.element_indices) >= 2
        assert len(ch2.element_indices) >= 2

    @pytest.mark.asyncio
    async def test_type_counts(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_image(page=0, order=1),
            _make_table(page=0, order=2),
            _make_equation(page=0, order=3),
            _make_text("text", 0, 4),
        ]
        result = _make_result(items=items)
        outline = DocumentOutline(
            document_id="d1",
            nodes=[OutlineNode(id="ch_0", title="Chapter 1", level=1, page_start=0)],
        )
        splitter = ChapterSplitter()
        result_outline = await splitter.split(result, outline)
        ch = result_outline.get_all_chapters()[0]
        assert ch.image_count == 1
        assert ch.table_count == 1
        assert ch.equation_count == 1

    @pytest.mark.asyncio
    async def test_chapter_markdown_generated(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_text("Hello world", 0, 1),
        ]
        result = _make_result(items=items)
        outline = DocumentOutline(
            document_id="d1",
            nodes=[OutlineNode(id="ch_0", title="Chapter 1", level=1, page_start=0)],
        )
        splitter = ChapterSplitter()
        result_outline = await splitter.split(result, outline)
        ch = result_outline.get_all_chapters()[0]
        assert "Chapter 1" in ch.markdown
        assert "Hello world" in ch.markdown

    @pytest.mark.asyncio
    async def test_nested_chapters_element_assignment(self):
        items = [
            _make_heading("Chapter 1", 1, 0, 0),
            _make_text("ch1 intro", 0, 1),
            _make_heading("Section 1.1", 2, 2, 2),
            _make_text("s1.1 content", 2, 3),
            _make_heading("Chapter 2", 1, 5, 4),
            _make_text("ch2 content", 5, 5),
        ]
        result = _make_result(items=items)
        c1 = OutlineNode(id="ch_0", title="Chapter 1", level=1, page_start=0, page_end=4)
        s1 = OutlineNode(id="ch_1", title="Section 1.1", level=2, page_start=2, page_end=4)
        c1.children = [s1]
        c2 = OutlineNode(id="ch_2", title="Chapter 2", level=1, page_start=5)
        outline = DocumentOutline(document_id="d1", nodes=[c1, c2])

        splitter = ChapterSplitter()
        result_outline = await splitter.split(result, outline)
        chapters = result_outline.get_all_chapters()
        assert len(chapters) == 3
        total = sum(len(ch.element_indices) for ch in chapters)
        assert total == 6

    @pytest.mark.asyncio
    async def test_conservation_all_elements_assigned(self):
        items = [
            _make_heading("Ch1", 1, 0, 0),
            _make_text("a", 0, 1),
            _make_text("b", 1, 2),
            _make_image(page=2, order=3),
            _make_heading("Ch2", 1, 3, 4),
            _make_text("c", 3, 5),
            _make_table(page=4, order=6),
            _make_equation(page=5, order=7),
        ]
        result = _make_result(items=items)
        outline = DocumentOutline(
            document_id="d1",
            nodes=[
                OutlineNode(id="ch_0", title="Ch1", level=1, page_start=0, page_end=2),
                OutlineNode(id="ch_1", title="Ch2", level=1, page_start=3),
            ],
        )
        splitter = ChapterSplitter()
        result_outline = await splitter.split(result, outline)
        total = sum(len(ch.element_indices) for ch in result_outline.get_all_chapters())
        assert total == len(items)
