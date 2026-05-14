from __future__ import annotations

import json

import pytest

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.core.reader.llm_client import BaseLLMClient, DummyLLMClient
from doc_parser.core.reader.models import (
    ChapterAnalysis,
    CrossChapterRelation,
    DocumentMetadata,
    LLMReadingResult,
)
from doc_parser.core.reader.unified_reader import UnifiedReader, UnifiedReaderConfig
from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult


def _outline_with_chapters():
    c1 = OutlineNode(id="ch_0", title="Introduction", level=1, page_start=0, page_end=2)
    c1.markdown = "# Introduction\nThis is the introduction chapter."
    c2 = OutlineNode(id="ch_1", title="Methods", level=1, page_start=3, page_end=5)
    c2.markdown = "# Methods\nWe describe our methods here."
    c2.metadata = {
        "images": [{"path": "fig1.png", "vlm_description": {"description": "A chart showing results"}}]
    }
    c3 = OutlineNode(id="ch_2", title="Results", level=1, page_start=6, page_end=8)
    c3.markdown = "# Results\nThe results are promising."
    return DocumentOutline(document_id="test-doc", title="Test Paper", nodes=[c1, c2, c3])


class _FakeLLM(BaseLLMClient):
    def __init__(self, metadata_json=None, chapter_json=None, cross_json=None):
        self._metadata = metadata_json or {
            "title": "Test Paper",
            "subject": "AI",
            "summary": "A test paper summary.",
            "keywords": ["test", "AI"],
            "document_type": "学术论文",
            "language": "zh",
            "quality_assessment": "高",
        }
        self._chapter = chapter_json or {
            "summary": "Chapter summary.",
            "key_points": ["point1", "point2"],
            "entities": ["entity1"],
            "relations": [{"subject": "A", "predicate": "uses", "object": "B"}],
        }
        self._cross = cross_json or {
            "relations": [
                {"source": "Introduction", "target": "Methods", "relation_type": "依赖", "description": "Methods depends on intro"}
            ]
        }
        self.call_count = 0

    async def chat(self, messages, **kwargs):
        self.call_count += 1
        content = messages[0]["content"]
        if "文档级元数据" in content or "document_type" in content:
            return json.dumps(self._metadata, ensure_ascii=False)
        elif "跨章节" in content or "relation_type" in content:
            return json.dumps(self._cross, ensure_ascii=False)
        else:
            return json.dumps(self._chapter, ensure_ascii=False)

    async def health_check(self):
        return True


class _EmptyLLM(BaseLLMClient):
    async def chat(self, messages, **kwargs):
        return ""

    async def health_check(self):
        return False


class TestDocumentMetadata:
    def test_default(self):
        m = DocumentMetadata()
        assert m.title == ""
        assert m.keywords == []

    def test_with_values(self):
        m = DocumentMetadata(title="Test", keywords=["a", "b"], document_type="report")
        assert m.title == "Test"
        assert len(m.keywords) == 2


class TestChapterAnalysis:
    def test_default(self):
        ca = ChapterAnalysis(chapter_id="ch_0")
        assert ca.summary == ""
        assert ca.key_points == []

    def test_with_relations(self):
        ca = ChapterAnalysis(
            chapter_id="ch_0", summary="sum",
            relations=[{"subject": "A", "predicate": "uses", "object": "B"}],
        )
        assert len(ca.relations) == 1


class TestLLMReadingResult:
    def test_default(self):
        r = LLMReadingResult()
        assert r.metadata.title == ""
        assert r.chapters == []

    def test_full(self):
        r = LLMReadingResult(
            metadata=DocumentMetadata(title="T"),
            chapters=[ChapterAnalysis(chapter_id="c1")],
            cross_chapter_relations=[CrossChapterRelation(source="a", target="b")],
        )
        assert r.metadata.title == "T"
        assert len(r.chapters) == 1
        assert len(r.cross_chapter_relations) == 1


class TestDummyLLMClient:
    @pytest.mark.asyncio
    async def test_returns_empty(self):
        client = DummyLLMClient()
        r = await client.chat([{"role": "user", "content": "hi"}])
        assert r == ""

    @pytest.mark.asyncio
    async def test_health(self):
        client = DummyLLMClient()
        assert await client.health_check() is True


class TestUnifiedReader:
    @pytest.mark.asyncio
    async def test_read_document_full(self):
        llm = _FakeLLM()
        reader = UnifiedReader(llm_client=llm)
        outline = _outline_with_chapters()

        result = await reader.read_document(outline)

        assert result.metadata.title == "Test Paper"
        assert result.metadata.keywords == ["test", "AI"]
        assert len(result.chapters) == 3
        assert result.chapters[0].chapter_id == "ch_0"
        assert result.chapters[0].key_points == ["point1", "point2"]
        assert len(result.cross_chapter_relations) == 1

    @pytest.mark.asyncio
    async def test_read_document_metadata_only(self):
        llm = _FakeLLM()
        config = UnifiedReaderConfig(enable_metadata=True, enable_chapter_analysis=False, enable_cross_chapter=False)
        reader = UnifiedReader(llm_client=llm, config=config)
        outline = _outline_with_chapters()

        result = await reader.read_document(outline)

        assert result.metadata.title == "Test Paper"
        assert len(result.chapters) == 0
        assert len(result.cross_chapter_relations) == 0

    @pytest.mark.asyncio
    async def test_read_document_empty_llm(self):
        reader = UnifiedReader(llm_client=_EmptyLLM())
        outline = _outline_with_chapters()

        result = await reader.read_document(outline)

        assert result.metadata.title == ""
        assert all(ca.summary == "" for ca in result.chapters)
        assert result.cross_chapter_relations == []

    @pytest.mark.asyncio
    async def test_read_document_empty_outline(self):
        reader = UnifiedReader(llm_client=_FakeLLM(metadata_json={
            "title": "", "subject": "", "summary": "", "keywords": [],
            "document_type": "", "language": "", "quality_assessment": "",
        }))
        outline = DocumentOutline(document_id="empty")

        result = await reader.read_document(outline)

        assert result.metadata.title == ""

    @pytest.mark.asyncio
    async def test_chapter_with_images_metadata(self):
        llm = _FakeLLM()
        reader = UnifiedReader(llm_client=llm)
        outline = _outline_with_chapters()

        result = await reader.read_document(outline)

        ch1_analysis = next((c for c in result.chapters if c.chapter_id == "ch_1"), None)
        assert ch1_analysis is not None

    @pytest.mark.asyncio
    async def test_config_preview_length(self):
        config = UnifiedReaderConfig(content_preview_length=100)
        reader = UnifiedReader(config=config)
        assert reader._config.content_preview_length == 100


class TestUnifiedReaderParsing:
    def test_parse_metadata_valid_json(self):
        reader = UnifiedReader()
        text = '{"title": "Hello", "subject": "World", "summary": "A summary", "keywords": ["a"], "document_type": "report", "language": "en", "quality_assessment": "高"}'
        m = reader._parse_metadata(text)
        assert m.title == "Hello"
        assert m.keywords == ["a"]

    def test_parse_metadata_json_in_text(self):
        reader = UnifiedReader()
        text = 'Here is the result:\n{"title": "Embedded", "subject": "", "summary": "", "keywords": [], "document_type": "", "language": "", "quality_assessment": ""}\nDone.'
        m = reader._parse_metadata(text)
        assert m.title == "Embedded"

    def test_parse_metadata_invalid(self):
        reader = UnifiedReader()
        m = reader._parse_metadata("not json at all")
        assert m.title == ""

    def test_parse_chapter_analysis_valid(self):
        reader = UnifiedReader()
        text = '{"summary": "test sum", "key_points": ["p1"], "entities": ["e1"], "relations": []}'
        ca = reader._parse_chapter_analysis(text, "ch_0")
        assert ca.chapter_id == "ch_0"
        assert ca.summary == "test sum"

    def test_parse_chapter_analysis_empty_response(self):
        reader = UnifiedReader()
        ca = reader._parse_chapter_analysis("", "ch_0")
        assert ca.chapter_id == "ch_0"
        assert ca.summary == ""

    def test_parse_cross_chapter_valid(self):
        reader = UnifiedReader()
        text = '{"relations": [{"source": "A", "target": "B", "relation_type": "ref", "description": "A refs B"}]}'
        rels = reader._parse_cross_chapter(text)
        assert len(rels) == 1
        assert rels[0].source == "A"

    def test_parse_cross_chapter_invalid(self):
        reader = UnifiedReader()
        rels = reader._parse_cross_chapter("invalid")
        assert rels == []

    def test_extract_json_from_markdown(self):
        reader = UnifiedReader()
        text = "```json\n{\"key\": \"value\"}\n```"
        result = reader._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_empty(self):
        reader = UnifiedReader()
        assert reader._extract_json("") is None
        assert reader._extract_json("no braces") is None
