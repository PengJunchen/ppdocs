from __future__ import annotations

import pytest

from doc_parser.core.chapter.models import DocumentOutline, OutlineNode
from doc_parser.core.kg.lightrag_adapter import DummyKGBridge
from doc_parser.orchestrator import (
    DocumentOrchestrator,
    OrchestratorConfig,
    OrchestratorResult,
    PipelineStage,
    StageResult,
)
from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult
from doc_parser.storage.vector_store import InMemoryVectorStore


def _make_pipeline_result() -> PipelineResult:
    items = [
        ContentItem(type=ElementType.TEXT, text="Chapter 1", text_level=1, page_idx=0, reading_order=0),
        ContentItem(type=ElementType.TEXT, text="Introduction content here.", text_level=0, page_idx=0, reading_order=1),
        ContentItem(type=ElementType.TEXT, text="Chapter 2", text_level=1, page_idx=1, reading_order=2),
        ContentItem(type=ElementType.TEXT, text="Methods and approaches.", text_level=0, page_idx=1, reading_order=3),
    ]
    return PipelineResult(
        document_id="orch-test-doc",
        engine="test-engine",
        content_list=items,
        markdown="# Chapter 1\nIntroduction content here.\n# Chapter 2\nMethods and approaches.",
    )


class TestOrchestratorConfig:
    def test_defaults(self):
        config = OrchestratorConfig()
        assert config.enable_enhance is True
        assert config.enable_read is True
        assert config.enable_kg is False
        assert config.enable_vectorize is False

    def test_custom(self):
        config = OrchestratorConfig(
            enable_enhance=False,
            enable_read=False,
            enable_kg=True,
            enable_vectorize=True,
        )
        assert config.enable_enhance is False
        assert config.enable_kg is True
        assert config.enable_vectorize is True


class TestStageResult:
    def test_defaults(self):
        sr = StageResult()
        assert sr.stage == ""
        assert sr.success is False
        assert sr.duration == 0.0
        assert sr.error == ""


class TestOrchestratorResult:
    def test_defaults(self):
        r = OrchestratorResult()
        assert r.document_id == ""
        assert r.total_duration == 0.0
        assert r.stages == []
        assert r.errors == []


class TestPipelineStage:
    def test_values(self):
        assert PipelineStage.PARSE.value == "parse"
        assert PipelineStage.TOC.value == "toc"
        assert PipelineStage.SPLIT.value == "split"
        assert PipelineStage.ENHANCE.value == "enhance"
        assert PipelineStage.READ.value == "read"
        assert PipelineStage.KG.value == "kg"
        assert PipelineStage.VECTORIZE.value == "vectorize"


class TestDocumentOrchestrator:
    @pytest.mark.asyncio
    async def test_process_basic(self):
        orchestrator = DocumentOrchestrator(
            config=OrchestratorConfig(enable_enhance=False, enable_read=False),
        )
        result = await orchestrator.process(_make_pipeline_result())

        assert result.document_id == "orch-test-doc"
        assert result.total_duration > 0
        stage_names = [s.stage for s in result.stages]
        assert "toc" in stage_names
        assert "split" in stage_names
        assert "enhance" not in stage_names
        assert "read" not in stage_names

    @pytest.mark.asyncio
    async def test_process_with_enhance(self):
        orchestrator = DocumentOrchestrator(
            config=OrchestratorConfig(enable_enhance=True, enable_read=False),
        )
        result = await orchestrator.process(_make_pipeline_result())

        stage_names = [s.stage for s in result.stages]
        assert "enhance" in stage_names
        enhance_stage = next(s for s in result.stages if s.stage == "enhance")
        assert enhance_stage.success is True

    @pytest.mark.asyncio
    async def test_process_with_read(self):
        orchestrator = DocumentOrchestrator(
            config=OrchestratorConfig(enable_enhance=False, enable_read=True),
        )
        result = await orchestrator.process(_make_pipeline_result())

        stage_names = [s.stage for s in result.stages]
        assert "read" in stage_names
        assert result.reading_result is not None

    @pytest.mark.asyncio
    async def test_process_with_kg(self):
        orchestrator = DocumentOrchestrator(
            kg_bridge=DummyKGBridge(),
            config=OrchestratorConfig(enable_enhance=False, enable_read=False, enable_kg=True),
        )
        result = await orchestrator.process(_make_pipeline_result())

        stage_names = [s.stage for s in result.stages]
        assert "kg" in stage_names
        assert result.kg_result is not None

    @pytest.mark.asyncio
    async def test_process_with_vectorize(self):
        orchestrator = DocumentOrchestrator(
            vector_store=InMemoryVectorStore(),
            config=OrchestratorConfig(enable_enhance=False, enable_read=False, enable_vectorize=True),
        )
        result = await orchestrator.process(_make_pipeline_result())

        stage_names = [s.stage for s in result.stages]
        assert "vectorize" in stage_names
        assert result.vector_result is not None

    @pytest.mark.asyncio
    async def test_process_full_pipeline(self):
        orchestrator = DocumentOrchestrator(
            kg_bridge=DummyKGBridge(),
            vector_store=InMemoryVectorStore(),
            config=OrchestratorConfig(
                enable_enhance=True,
                enable_read=True,
                enable_kg=True,
                enable_vectorize=True,
            ),
        )
        result = await orchestrator.process(_make_pipeline_result())

        assert result.document_id == "orch-test-doc"
        assert len(result.stages) == 6
        stage_names = [s.stage for s in result.stages]
        assert stage_names == ["toc", "split", "enhance", "read", "kg", "vectorize"]
        all_success = all(s.success for s in result.stages)
        assert all_success is True
        assert result.outline is not None
        assert result.reading_result is not None
        assert result.kg_result is not None
        assert result.vector_result is not None
        assert result.total_duration > 0

    @pytest.mark.asyncio
    async def test_process_outline_populated(self):
        orchestrator = DocumentOrchestrator(
            config=OrchestratorConfig(enable_enhance=False, enable_read=False),
        )
        result = await orchestrator.process(_make_pipeline_result())

        assert result.outline is not None
        assert result.outline["document_id"] == "orch-test-doc"
        assert result.outline["total_chapters"] >= 2

    @pytest.mark.asyncio
    async def test_process_all_stages_have_duration(self):
        orchestrator = DocumentOrchestrator(
            config=OrchestratorConfig(enable_enhance=False, enable_read=False),
        )
        result = await orchestrator.process(_make_pipeline_result())

        for stage in result.stages:
            assert stage.duration >= 0
            assert stage.stage != ""

    @pytest.mark.asyncio
    async def test_process_toc_failure_stops_pipeline(self):
        class _FailTocOrchestrator(DocumentOrchestrator):
            async def _stage_toc(self, pipeline_result):
                raise RuntimeError("TOC extraction failed")

        orchestrator = _FailTocOrchestrator(
            config=OrchestratorConfig(enable_enhance=False, enable_read=False),
        )
        result = await orchestrator.process(_make_pipeline_result())

        assert len(result.errors) > 0
        toc_stage = next(s for s in result.stages if s.stage == "toc")
        assert toc_stage.success is False
        assert "TOC extraction failed" in toc_stage.error

    @pytest.mark.asyncio
    async def test_process_kg_with_reading_cross_relations(self):
        orchestrator = DocumentOrchestrator(
            kg_bridge=DummyKGBridge(),
            config=OrchestratorConfig(
                enable_enhance=False, enable_read=True, enable_kg=True,
            ),
        )
        result = await orchestrator.process(_make_pipeline_result())

        kg_stage = next(s for s in result.stages if s.stage == "kg")
        assert kg_stage.success is True

    @pytest.mark.asyncio
    async def test_process_empty_content(self):
        items = [
            ContentItem(type=ElementType.TEXT, text="single text", text_level=0, page_idx=0, reading_order=0),
        ]
        pipeline_result = PipelineResult(
            document_id="empty-doc",
            engine="test",
            content_list=items,
            markdown="single text",
        )
        orchestrator = DocumentOrchestrator(
            config=OrchestratorConfig(enable_enhance=False, enable_read=False),
        )
        result = await orchestrator.process(pipeline_result)
        assert result.document_id == "empty-doc"
        assert len(result.stages) >= 1
