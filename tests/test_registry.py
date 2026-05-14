from __future__ import annotations

import pytest

from doc_parser.pipeline.base import (
    EngineNotFound,
    FormatNotSupported,
    PipelineConfig,
)
from doc_parser.pipeline.mineru import MinerUPipeline, MinerUVLMPipeline
from doc_parser.pipeline.docling_pipeline import DoclingPipeline
from doc_parser.pipeline.registry import PipelineRegistry, create_default_registry


class TestPipelineRegistry:
    @pytest.fixture()
    def registry(self):
        reg = PipelineRegistry()
        mineru_cfg = PipelineConfig(engine="mineru-pipeline", base_url="http://localhost:18089")
        vlm_cfg = PipelineConfig(engine="mineru-vlm", base_url="http://localhost:18089")
        docling_cfg = PipelineConfig(engine="docling", base_url="http://localhost:8080", api_key="test")
        reg.register(MinerUPipeline(mineru_cfg))
        reg.register(MinerUVLMPipeline(vlm_cfg))
        reg.register(DoclingPipeline(docling_cfg))
        return reg

    def test_register_and_list(self, registry):
        engines = registry.list_engines()
        assert "mineru-pipeline" in engines
        assert "mineru-vlm" in engines
        assert "docling" in engines

    def test_get_existing_engine(self, registry):
        engine = registry.get("mineru-pipeline")
        assert engine.engine_name == "mineru-pipeline"

    def test_get_missing_engine(self, registry):
        with pytest.raises(EngineNotFound):
            registry.get("nonexistent")

    def test_resolve_auto_pdf(self, registry):
        engine = registry._resolve_engine("auto", "test.pdf")
        assert engine.engine_name == "mineru-vlm"

    def test_resolve_auto_docx(self, registry):
        engine = registry._resolve_engine("auto", "test.docx")
        assert engine.engine_name == "docling"

    def test_resolve_auto_pptx(self, registry):
        engine = registry._resolve_engine("auto", "report.pptx")
        assert engine.engine_name == "docling"

    def test_resolve_specific_engine(self, registry):
        engine = registry._resolve_engine("docling", "test.pdf")
        assert engine.engine_name == "docling"

    def test_resolve_unsupported_format(self, registry):
        with pytest.raises(FormatNotSupported):
            registry._resolve_engine("auto", "test.exe")


class TestCreateDefaultRegistry:
    def test_with_all_engines(self):
        registry = create_default_registry(
            mineru_url="http://10.0.40.153:18089",
            docling_url="http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling",
            docling_api_key="Db3S72tVSn2YeSw",
        )
        engines = registry.list_engines()
        assert "mineru-pipeline" in engines
        assert "mineru-vlm" in engines
        assert "docling" in engines

    def test_with_mineru_only(self):
        registry = create_default_registry(
            mineru_url="http://10.0.40.153:18089",
        )
        engines = registry.list_engines()
        assert "mineru-pipeline" in engines
        assert "mineru-vlm" in engines
        assert "docling" not in engines

    def test_with_docling_only(self):
        registry = create_default_registry(
            docling_url="http://localhost:8080",
            docling_api_key="key123",
        )
        engines = registry.list_engines()
        assert "docling" in engines
        assert "mineru-pipeline" not in engines

    def test_empty_registry(self):
        registry = create_default_registry()
        engines = registry.list_engines()
        assert len(engines) == 0


class TestDoclingTransform:
    def test_build_content_list_empty(self):
        config = PipelineConfig(base_url="http://localhost:8080")
        pipeline = DoclingPipeline(config)
        result = pipeline._build_content_list({})
        assert result == []

    def test_build_content_list_with_items(self):
        config = PipelineConfig(base_url="http://localhost:8080")
        pipeline = DoclingPipeline(config)
        raw = {
            "content_list": [
                {
                    "type": "section_header",
                    "text": "Chapter 1",
                    "level": 1,
                    "page_idx": 0,
                },
                {
                    "type": "paragraph",
                    "text": "Some text here",
                    "page_idx": 0,
                },
                {
                    "type": "table",
                    "html": "<table><tr><td>A</td></tr></table>",
                    "page_idx": 1,
                },
            ]
        }
        result = pipeline._build_content_list(raw)
        assert len(result) == 3
        assert result[0].text_level == 1
        assert result[0].type.value == "text"
        assert result[2].table_body != ""

    def test_grid_to_html(self):
        data = [["A", "B"], ["C", "D"]]
        html = DoclingPipeline._grid_to_html(data)
        assert "<table>" in html
        assert "<td>A</td>" in html
        assert "<td>D</td>" in html

    def test_build_content_list_string_content(self):
        import json
        config = PipelineConfig(base_url="http://localhost:8080")
        pipeline = DoclingPipeline(config)
        items = [{"type": "text", "text": "Hello", "page_idx": 0}]
        raw = {"content_list": json.dumps(items)}
        result = pipeline._build_content_list(raw)
        assert len(result) == 1
        assert result[0].text == "Hello"
