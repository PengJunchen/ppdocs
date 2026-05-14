from __future__ import annotations

import json

import pytest

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.core.kg.builder import KGBuilder, KGBuilderConfig
from doc_parser.core.kg.lightrag_adapter import BaseKGBridge, DummyKGBridge, LLMKGBridge, LightRAGAdapter
from doc_parser.core.kg.models import (
    KGBuildResult,
    KGEntity,
    KGInsertResult,
    KGQueryMode,
    KGQueryResult,
    KGRelation,
)
from doc_parser.core.reader.models import CrossChapterRelation


def _outline_with_chapters():
    c1 = OutlineNode(id="ch_0", title="Introduction", level=1, page_start=0, page_end=2)
    c1.markdown = "# Introduction\nThis is the introduction chapter with key concepts."
    c2 = OutlineNode(id="ch_1", title="Methods", level=1, page_start=3, page_end=5)
    c2.markdown = "# Methods\nWe describe our methods here. The algorithm uses neural networks."
    c2.metadata = {
        "images": [{"path": "fig1.png", "vlm_description": {"description": "Architecture diagram"}}]
    }
    c3 = OutlineNode(id="ch_2", title="Results", level=1, page_start=6, page_end=8)
    c3.markdown = "# Results\nThe results are promising with 95% accuracy."
    return DocumentOutline(document_id="test-doc", title="Test Paper", nodes=[c1, c2, c3])


class TestKGModels:
    def test_kg_entity_defaults(self):
        e = KGEntity()
        assert e.name == ""
        assert e.entity_type == ""
        assert e.metadata == {}

    def test_kg_entity_with_values(self):
        e = KGEntity(name="Neural Network", entity_type="concept", description="A model", source_id="doc1")
        assert e.name == "Neural Network"
        assert e.entity_type == "concept"

    def test_kg_relation_defaults(self):
        r = KGRelation()
        assert r.source == ""
        assert r.weight == 1.0

    def test_kg_relation_with_values(self):
        r = KGRelation(source="A", target="B", relation_type="depends_on", weight=0.8)
        assert r.source == "A"
        assert r.weight == 0.8

    def test_kg_insert_result(self):
        r = KGInsertResult(document_id="doc1", total_chunks=3)
        assert r.document_id == "doc1"
        assert r.total_chunks == 3
        assert r.errors == []

    def test_kg_query_mode_enum(self):
        assert KGQueryMode.NAIVE.value == "naive"
        assert KGQueryMode.LOCAL.value == "local"
        assert KGQueryMode.GLOBAL.value == "global"
        assert KGQueryMode.HYBRID.value == "hybrid"

    def test_kg_query_result(self):
        r = KGQueryResult(query="test", mode=KGQueryMode.LOCAL, answer="result")
        assert r.query == "test"
        assert r.answer == "result"
        assert r.source_chunks == []

    def test_kg_build_result(self):
        r = KGBuildResult(document_id="doc1", total_chapters=3, total_chunks=5)
        assert r.total_chapters == 3
        assert r.build_time == 0.0
        assert r.insert_results == []


class TestDummyKGBridge:
    @pytest.mark.asyncio
    async def test_insert(self):
        bridge = DummyKGBridge()
        result = await bridge.insert("test content", doc_id="doc1")
        assert result.document_id == "doc1"
        assert result.total_chunks == 1

    @pytest.mark.asyncio
    async def test_insert_tracks_items(self):
        bridge = DummyKGBridge()
        await bridge.insert("content1", doc_id="doc1", metadata={"key": "val"})
        await bridge.insert("content2", doc_id="doc2")
        assert len(bridge.inserted_items) == 2
        assert bridge.inserted_items[0]["doc_id"] == "doc1"
        assert bridge.inserted_items[0]["metadata"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_query(self):
        bridge = DummyKGBridge()
        result = await bridge.query("test query", mode=KGQueryMode.HYBRID)
        assert result.query == "test query"
        assert result.answer == ""

    @pytest.mark.asyncio
    async def test_health_check(self):
        bridge = DummyKGBridge()
        assert await bridge.health_check() is True


class TestLightRAGAdapter:
    def test_init_defaults(self):
        adapter = LightRAGAdapter()
        assert adapter._working_dir == ""
        assert adapter._rag is None

    def test_init_with_params(self):
        adapter = LightRAGAdapter(
            working_dir="/tmp/rag",
            llm_model="qwen-max",
            embedding_model="bge-large",
        )
        assert adapter._working_dir == "/tmp/rag"
        assert adapter._llm_model == "qwen-max"

    @pytest.mark.asyncio
    async def test_health_check_no_rag(self):
        adapter = LightRAGAdapter()
        assert await adapter.health_check() is False


class TestKGBuilder:
    @pytest.mark.asyncio
    async def test_build_basic(self):
        bridge = DummyKGBridge()
        builder = KGBuilder(kg_bridge=bridge)
        outline = _outline_with_chapters()

        result = await builder.build(outline)
        assert result.document_id == "test-doc"
        assert result.total_chapters == 3
        assert result.total_chunks == 3
        assert len(result.insert_results) == 3
        assert result.build_time > 0

    @pytest.mark.asyncio
    async def test_build_with_cross_relations(self):
        bridge = DummyKGBridge()
        builder = KGBuilder(kg_bridge=bridge)
        outline = _outline_with_chapters()

        relations = [
            CrossChapterRelation(
                source="Introduction", target="Methods",
                relation_type="依赖", description="Methods depends on intro"
            ),
        ]
        result = await builder.build(outline, cross_relations=relations)
        assert len(result.cross_chapter_relations) == 1
        assert result.cross_chapter_relations[0].source == "Introduction"
        assert result.cross_chapter_relations[0].relation_type == "依赖"
        assert result.total_chunks == 4

    @pytest.mark.asyncio
    async def test_build_empty_outline(self):
        bridge = DummyKGBridge()
        builder = KGBuilder(kg_bridge=bridge)
        outline = DocumentOutline(document_id="empty-doc")

        result = await builder.build(outline)
        assert result.document_id == "empty-doc"
        assert result.total_chapters == 0
        assert result.total_chunks == 0

    @pytest.mark.asyncio
    async def test_build_chapter_with_no_content(self):
        bridge = DummyKGBridge()
        builder = KGBuilder(kg_bridge=bridge)
        c1 = OutlineNode(id="ch_0", title="Empty Chapter", level=1, page_start=0)
        outline = DocumentOutline(document_id="doc1", nodes=[c1])

        result = await builder.build(outline)
        assert result.total_chunks == 1
        assert "Empty Chapter" in bridge.inserted_items[0]["content"]

    @pytest.mark.asyncio
    async def test_query(self):
        bridge = DummyKGBridge()
        builder = KGBuilder(kg_bridge=bridge)

        result = await builder.query("what is neural network?", mode=KGQueryMode.LOCAL)
        assert result.query == "what is neural network?"
        assert result.mode == KGQueryMode.LOCAL

    @pytest.mark.asyncio
    async def test_build_config_metadata(self):
        bridge = DummyKGBridge()
        config = KGBuilderConfig(include_metadata=True, include_entities=True)
        builder = KGBuilder(kg_bridge=bridge, config=config)
        outline = _outline_with_chapters()

        result = await builder.build(outline)
        assert result.total_chunks == 3
        inserted = bridge.inserted_items
        assert any("pages" in item["content"] for item in inserted)

    @pytest.mark.asyncio
    async def test_build_config_no_metadata(self):
        bridge = DummyKGBridge()
        config = KGBuilderConfig(include_metadata=False)
        builder = KGBuilder(kg_bridge=bridge, config=config)
        outline = _outline_with_chapters()

        result = await builder.build(outline)
        inserted = bridge.inserted_items
        assert all("pages" not in item["content"] for item in inserted)

    @pytest.mark.asyncio
    async def test_build_with_images_in_content(self):
        bridge = DummyKGBridge()
        builder = KGBuilder(kg_bridge=bridge)
        outline = _outline_with_chapters()

        result = await builder.build(outline)
        methods_insert = bridge.inserted_items[1]
        assert "[Image:" in methods_insert["content"]
        assert "Architecture diagram" in methods_insert["content"]

    @pytest.mark.asyncio
    async def test_build_chapter_metadata_entities(self):
        bridge = DummyKGBridge()
        builder = KGBuilder(kg_bridge=bridge)
        c1 = OutlineNode(id="ch_0", title="Neural Networks", level=1, page_start=0, page_end=3)
        c1.markdown = "# Neural Networks\nDeep learning concepts."
        c1.metadata = {"analysis": {"entities": ["CNN", "RNN", "Transformer"]}}
        outline = DocumentOutline(document_id="doc1", nodes=[c1])

        result = await builder.build(outline)
        inserted = bridge.inserted_items[0]
        assert "entities" in inserted["metadata"]
        assert "CNN" in inserted["metadata"]["entities"]

    @pytest.mark.asyncio
    async def test_build_cross_chapter_relation_content(self):
        bridge = DummyKGBridge()
        builder = KGBuilder(kg_bridge=bridge)
        outline = _outline_with_chapters()

        relations = [
            CrossChapterRelation(source="A", target="B", relation_type="引用", description="A cites B"),
            CrossChapterRelation(source="C", target="D", relation_type="对比", description="C compares D"),
        ]
        result = await builder.build(outline, cross_relations=relations)

        last_insert = bridge.inserted_items[-1]
        assert "Cross-Chapter Relations" in last_insert["content"]
        assert "引用" in last_insert["content"]
        assert "对比" in last_insert["content"]


class TestLLMKGBridge:
    @pytest.fixture
    def mock_llm(self):
        class MockLLM:
            async def chat(self, messages, **kwargs):
                return json.dumps({
                    "entities": [
                        {"name": "张三", "type": "人物", "description": "项目经理"},
                        {"name": "AI系统", "type": "技术", "description": "智能文档处理系统"},
                    ],
                    "relations": [
                        {"source": "张三", "target": "AI系统", "relation_type": "开发了", "description": "张三开发了AI系统"},
                    ],
                })

            async def health_check(self):
                return True

        return MockLLM()

    @pytest.mark.asyncio
    async def test_insert_without_llm(self):
        bridge = LLMKGBridge()
        result = await bridge.insert("测试内容", doc_id="doc1")
        assert result.document_id == "doc1"
        assert result.total_entities == 0
        assert result.total_relations == 0

    @pytest.mark.asyncio
    async def test_insert_with_llm(self, mock_llm):
        bridge = LLMKGBridge(llm_client=mock_llm)
        result = await bridge.insert("张三开发了AI系统", doc_id="doc1")
        assert result.document_id == "doc1"
        assert result.total_entities == 2
        assert result.total_relations == 1

    @pytest.mark.asyncio
    async def test_entities_stored(self, mock_llm):
        bridge = LLMKGBridge(llm_client=mock_llm)
        await bridge.insert("张三开发了AI系统", doc_id="doc1")
        assert len(bridge.entities) == 2
        assert bridge.entities[0]["name"] == "张三"
        assert bridge.entities[1]["name"] == "AI系统"

    @pytest.mark.asyncio
    async def test_relations_stored(self, mock_llm):
        bridge = LLMKGBridge(llm_client=mock_llm)
        await bridge.insert("张三开发了AI系统", doc_id="doc1")
        assert len(bridge.relations) == 1
        assert bridge.relations[0]["source"] == "张三"
        assert bridge.relations[0]["target"] == "AI系统"

    @pytest.mark.asyncio
    async def test_query_without_llm(self):
        bridge = LLMKGBridge()
        result = await bridge.query("谁开发了AI系统?")
        assert result.answer == ""

    @pytest.mark.asyncio
    async def test_query_with_llm(self, mock_llm):
        bridge = LLMKGBridge(llm_client=mock_llm)
        await bridge.insert("张三开发了AI系统", doc_id="doc1")
        result = await bridge.query("谁开发了AI系统?")
        assert result.query == "谁开发了AI系统?"
        assert len(result.source_entities) > 0

    @pytest.mark.asyncio
    async def test_extract_json(self):
        text = '一些文字 ```json\n{"entities": [], "relations": []}\n```'
        result = LLMKGBridge._extract_json(text)
        assert result is not None
        assert result["entities"] == []

    @pytest.mark.asyncio
    async def test_health_check_no_llm(self):
        bridge = LLMKGBridge()
        assert await bridge.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_with_llm(self, mock_llm):
        bridge = LLMKGBridge(llm_client=mock_llm)
        assert await bridge.health_check() is True
