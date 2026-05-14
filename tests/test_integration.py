from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from doc_parser.pipeline.base import PipelineConfig, PipelineResult, ContentItem, ElementType
from doc_parser.pipeline.mineru import MinerUPipeline, MinerUVLMPipeline
from doc_parser.pipeline.docling_pipeline import DoclingPipeline
from doc_parser.pipeline.registry import PipelineRegistry, create_default_registry

FIXTURES_DIR = Path(__file__).parent.parent / "PDFTest"


def _load_mineru_pipeline_result() -> dict:
    path = FIXTURES_DIR / "DeepSeek_V4_pdf_mineru_3.json"
    if not path.exists():
        pytest.skip("MinerU pipeline result not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_mineru_vlm_result() -> dict:
    path = FIXTURES_DIR / "DeepSeek_V4_pdf_mineru_3_vlm.json"
    if not path.exists():
        pytest.skip("MinerU VLM result not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestMinerUOfflineTransform:
    def test_pipeline_full_transform(self):
        raw = _load_mineru_pipeline_result()
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(raw)

        assert result.engine == "mineru-pipeline"
        assert result.document_id != ""
        assert len(result.content_list) > 0
        assert result.markdown != ""
        assert len(result.images) > 0
        assert len(result.tables) > 0
        assert len(result.equations) > 0

    def test_vlm_full_transform(self):
        raw = _load_mineru_vlm_result()
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUVLMPipeline(config)
        result = pipeline._transform_result(raw)

        assert result.engine == "mineru-vlm"
        assert len(result.content_list) > 0
        assert result.markdown != ""
        assert len(result.images) > 0

    def test_pipeline_vs_vlm_both_valid(self):
        raw_pipeline = _load_mineru_pipeline_result()
        raw_vlm = _load_mineru_vlm_result()

        config = PipelineConfig(base_url="http://localhost:18089")
        p_result = MinerUPipeline(config)._transform_result(raw_pipeline)
        v_result = MinerUVLMPipeline(config)._transform_result(raw_vlm)

        assert p_result.engine != v_result.engine
        assert len(p_result.content_list) > 0
        assert len(v_result.content_list) > 0
        assert p_result.metadata["backend"] != v_result.metadata["backend"]

    def test_pipeline_content_types_coverage(self):
        raw = _load_mineru_pipeline_result()
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(raw)

        types = {item.type for item in result.content_list}
        assert ElementType.TEXT in types

        tables_in_cl = [i for i in result.content_list if i.type == ElementType.TABLE]
        assert len(tables_in_cl) > 0

        eqs_in_cl = [i for i in result.content_list if i.type == ElementType.EQUATION]
        assert len(eqs_in_cl) > 0

    def test_pipeline_page_idx_range(self):
        raw = _load_mineru_pipeline_result()
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(raw)

        pages = {item.page_idx for item in result.content_list}
        assert min(pages) == 0
        assert len(pages) > 1

    def test_pipeline_text_levels(self):
        raw = _load_mineru_pipeline_result()
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(raw)

        titles = [i for i in result.content_list if i.text_level > 0]
        assert len(titles) > 0
        levels = {t.text_level for t in titles}
        assert 1 in levels

    def test_images_have_data(self):
        raw = _load_mineru_pipeline_result()
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(raw)

        for img in result.images:
            assert img.filename != ""
            assert img.data != ""

    def test_tables_have_html_or_image(self):
        raw = _load_mineru_pipeline_result()
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(raw)

        for table in result.tables:
            assert table.html != "" or table.img_path != ""

    def test_vlm_content_has_image_descriptions(self):
        raw = _load_mineru_vlm_result()
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUVLMPipeline(config)
        result = pipeline._transform_result(raw)

        images = [i for i in result.content_list if i.type == ElementType.IMAGE]
        with_content = [i for i in images if i.content]
        assert len(with_content) > 0


class TestRegistryWithRealConfig:
    def test_create_production_registry(self):
        registry = create_default_registry(
            mineru_url="http://10.0.40.153:18089",
            docling_url="http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling",
            docling_api_key="Db3S72tVSn2YeSw",
        )

        assert len(registry.list_engines()) == 3
        engine = registry.get("mineru-vlm")
        assert engine.engine_name == "mineru-vlm"

        resolved = registry._resolve_engine("auto", "test.pdf")
        assert resolved.engine_name == "mineru-vlm"

    def test_pdf_goes_to_mineru_vlm(self):
        registry = create_default_registry(
            mineru_url="http://10.0.40.153:18089",
            docling_url="http://localhost:8080",
        )
        engine = registry._resolve_engine("auto", "document.pdf")
        assert engine.engine_name == "mineru-vlm"

    def test_docx_goes_to_docling(self):
        registry = create_default_registry(
            mineru_url="http://10.0.40.153:18089",
            docling_url="http://localhost:8080",
        )
        engine = registry._resolve_engine("auto", "document.docx")
        assert engine.engine_name == "docling"
