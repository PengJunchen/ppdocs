from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_parser.pipeline.base import (
    ContentItem,
    ElementType,
    EngineNotFound,
    FormatNotSupported,
    ImageInfo,
    ParseFailed,
    ParseTimeout,
    PipelineConfig,
    PipelineError,
    PipelineResult,
    TableInfo,
    EquationInfo,
)
from doc_parser.pipeline.mineru import MinerUPipeline, MinerUVLMPipeline
from doc_parser.pipeline.docling_pipeline import DoclingPipeline


FIXTURES_DIR = Path(__file__).parent.parent / "PDFTest"


class TestPipelineResult:
    def test_default_values(self):
        result = PipelineResult()
        assert result.document_id == ""
        assert result.engine == ""
        assert result.content_list == []
        assert result.markdown == ""
        assert result.images == []
        assert result.tables == []
        assert result.equations == []

    def test_serialization(self):
        item = ContentItem(type=ElementType.TEXT, text="Hello", text_level=1, page_idx=0)
        result = PipelineResult(
            document_id="test-123",
            engine="mineru-pipeline",
            content_list=[item],
            markdown="# Hello",
        )
        d = result.model_dump()
        assert d["document_id"] == "test-123"
        assert d["engine"] == "mineru-pipeline"
        assert len(d["content_list"]) == 1
        assert d["content_list"][0]["text"] == "Hello"

    def test_deserialization(self):
        data = {
            "document_id": "doc-1",
            "engine": "docling",
            "content_list": [{"type": "text", "text": "World", "text_level": 2}],
            "markdown": "## World",
        }
        result = PipelineResult.model_validate(data)
        assert result.document_id == "doc-1"
        assert result.content_list[0].text == "World"
        assert result.content_list[0].text_level == 2


class TestContentItem:
    def test_default_values(self):
        item = ContentItem()
        assert item.type == ElementType.UNKNOWN
        assert item.text == ""
        assert item.text_level == 0
        assert item.page_idx == 0

    def test_with_values(self):
        item = ContentItem(
            type=ElementType.TABLE,
            text="Table 1",
            text_level=0,
            page_idx=5,
            table_body="<table><tr><td>A</td></tr></table>",
            table_caption=["Table 1: Results"],
        )
        assert item.type == ElementType.TABLE
        assert item.table_body != ""
        assert len(item.table_caption) == 1


class TestPipelineConfig:
    def test_default_values(self):
        config = PipelineConfig()
        assert config.engine == "auto"
        assert config.timeout == 300

    def test_custom_values(self):
        config = PipelineConfig(
            engine="mineru-vlm",
            base_url="http://localhost:8080",
            api_key="test-key",
            timeout=600,
        )
        assert config.engine == "mineru-vlm"
        assert config.base_url == "http://localhost:8080"


class TestPipelineError:
    def test_base_error(self):
        err = PipelineError("test error", code="TEST")
        assert err.code == "TEST"
        assert "test error" in str(err)

    def test_engine_not_found(self):
        err = EngineNotFound("bad-engine")
        assert err.code == "ENGINE_NOT_FOUND"
        assert "bad-engine" in str(err)

    def test_parse_failed(self):
        err = ParseFailed("parse crash")
        assert err.code == "PARSE_FAILED"

    def test_parse_timeout(self):
        err = ParseTimeout(300)
        assert err.code == "PARSE_TIMEOUT"
        assert "300" in str(err)

    def test_format_not_supported(self):
        err = FormatNotSupported("exe")
        assert err.code == "FORMAT_NOT_SUPPORTED"
        assert "exe" in str(err)


class TestMinerUTransformResult:
    @pytest.fixture()
    def pipeline_result_json(self):
        path = FIXTURES_DIR / "DeepSeek_V4_pdf_mineru_3.json"
        if not path.exists():
            pytest.skip("MinerU pipeline result JSON not found")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture()
    def vlm_result_json(self):
        path = FIXTURES_DIR / "DeepSeek_V4_pdf_mineru_3_vlm.json"
        if not path.exists():
            pytest.skip("MinerU VLM result JSON not found")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_transform_pipeline_result(self, pipeline_result_json):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(pipeline_result_json)

        assert result.engine == "mineru-pipeline"
        assert result.document_id != ""
        assert len(result.content_list) > 0
        assert result.markdown != ""
        assert len(result.images) > 0

        first_item = result.content_list[0]
        assert first_item.type == ElementType.TEXT
        assert first_item.text != ""
        assert first_item.page_idx == 0

    def test_transform_pipeline_result_has_text_levels(self, pipeline_result_json):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(pipeline_result_json)

        levels = {item.text_level for item in result.content_list}
        assert 1 in levels or 2 in levels

    def test_transform_pipeline_result_has_element_types(self, pipeline_result_json):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(pipeline_result_json)

        types = {item.type for item in result.content_list}
        assert ElementType.TEXT in types

    def test_transform_vlm_result(self, vlm_result_json):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUVLMPipeline(config)
        result = pipeline._transform_result(vlm_result_json)

        assert result.engine == "mineru-vlm"
        assert len(result.content_list) > 0
        assert result.markdown != ""
        assert len(result.images) > 0

    def test_pipeline_result_tables_extracted(self, pipeline_result_json):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(pipeline_result_json)

        assert len(result.tables) > 0
        for table in result.tables:
            assert table.html != "" or table.img_path != ""

    def test_pipeline_result_equations_extracted(self, pipeline_result_json):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(pipeline_result_json)

        assert len(result.equations) > 0
        for eq in result.equations:
            assert eq.latex != ""

    def test_pipeline_result_metadata(self, pipeline_result_json):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(pipeline_result_json)

        assert "task_id" in result.metadata
        assert "backend" in result.metadata
        assert "version" in result.metadata

    def test_content_list_element_coverage(self, pipeline_result_json):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        result = pipeline._transform_result(pipeline_result_json)

        types = {item.type.value for item in result.content_list}
        expected_types = {"text", "table", "image", "equation", "chart", "code", "header", "list", "page_footnote", "page_number"}
        overlap = types & expected_types
        assert len(overlap) >= 5


class TestMinerUFormatValidation:
    def test_supports_pdf(self):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        assert pipeline.supports_format("test.pdf")
        assert not pipeline.supports_format("test.docx")

    def test_rejects_non_pdf(self):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUPipeline(config)
        with pytest.raises(FormatNotSupported):
            pipeline._validate_format("test.docx")

    def test_vlm_supports_pdf(self):
        config = PipelineConfig(base_url="http://localhost:18089")
        pipeline = MinerUVLMPipeline(config)
        assert pipeline.supports_format("test.pdf")


class TestDoclingFormatValidation:
    def test_supports_multiple_formats(self):
        config = PipelineConfig(
            base_url="http://localhost:8080",
            api_key="test",
        )
        pipeline = DoclingPipeline(config)
        for ext in ["pdf", "docx", "pptx", "html", "md", "xlsx"]:
            assert pipeline.supports_format(f"test.{ext}"), f"Should support .{ext}"

    def test_rejects_unsupported(self):
        config = PipelineConfig(base_url="http://localhost:8080")
        pipeline = DoclingPipeline(config)
        assert not pipeline.supports_format("test.exe")


class TestMinerUParseContentList:
    def test_empty_content_list(self):
        result = MinerUPipeline._parse_content_list({})
        assert result == []

    def test_string_content_list(self):
        raw_cl = json.dumps([
            {"type": "text", "text": "Hello", "text_level": 1, "bbox": [0, 0, 100, 20], "page_idx": 0}
        ])
        char_list = list(raw_cl)
        file_result = {"content_list": char_list}
        result = MinerUPipeline._parse_content_list(file_result)
        assert len(result) == 1
        assert result[0].text == "Hello"
        assert result[0].text_level == 1

    def test_dict_content_list(self):
        file_result = {
            "content_list": [
                {"type": "text", "text": "Title", "text_level": 1, "page_idx": 0},
                {"type": "table", "table_body": "<table></table>", "page_idx": 1},
                {"type": "equation", "text": "$$E=mc^2$$", "text_format": "latex", "page_idx": 1},
            ]
        }
        result = MinerUPipeline._parse_content_list(file_result)
        assert len(result) == 3
        assert result[0].type == ElementType.TEXT
        assert result[1].type == ElementType.TABLE
        assert result[2].type == ElementType.EQUATION

    def test_missing_text_level_defaults_zero(self):
        file_result = {
            "content_list": [
                {"type": "text", "text": "No level", "page_idx": 0}
            ]
        }
        result = MinerUPipeline._parse_content_list(file_result)
        assert result[0].text_level == 0

    def test_reading_order_is_index(self):
        file_result = {
            "content_list": [
                {"type": "text", "text": "A", "page_idx": 0},
                {"type": "text", "text": "B", "page_idx": 0},
                {"type": "text", "text": "C", "page_idx": 1},
            ]
        }
        result = MinerUPipeline._parse_content_list(file_result)
        assert result[0].reading_order == 0
        assert result[1].reading_order == 1
        assert result[2].reading_order == 2


class TestMinerUParseImages:
    def test_dict_images(self):
        file_result = {
            "images": {
                "abc.jpg": "data:image/jpeg;base64,/9j/...",
                "def.png": "data:image/png;base64,iVBOR...",
            }
        }
        result = MinerUPipeline._parse_images(file_result)
        assert len(result) == 2
        assert result[0].filename == "abc.jpg"

    def test_empty_images(self):
        result = MinerUPipeline._parse_images({})
        assert result == []
