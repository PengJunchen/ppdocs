from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from doc_parser.api.app import create_app, set_globals
from doc_parser.api.models import TaskStatus
from doc_parser.api.task_manager import TaskManager
from doc_parser.pipeline.base import (
    ContentItem,
    ElementType,
    ImageInfo,
    PipelineResult,
    TableInfo,
    EquationInfo,
    FormatNotSupported,
    ParseFailed,
)
from doc_parser.pipeline.registry import PipelineRegistry


def _make_result(
    doc_id: str = "test-doc",
    engine: str = "mineru-vlm",
    n_items: int = 3,
    n_images: int = 1,
    n_tables: int = 1,
    n_equations: int = 1,
) -> PipelineResult:
    items = [
        ContentItem(
            type=ElementType.TEXT,
            text=f"item {i}",
            text_level=0,
            reading_order=i,
        )
        for i in range(n_items)
    ]
    images = [
        ImageInfo(filename=f"img_{i}.png", source_path=f"/imgs/img_{i}.png")
        for i in range(n_images)
    ]
    tables = [
        TableInfo(html="<table><tr><td>data</td></tr></table>", page_idx=0)
        for _ in range(n_tables)
    ]
    equations = [
        EquationInfo(latex="E=mc^2", page_idx=0)
        for _ in range(n_equations)
    ]
    return PipelineResult(
        document_id=doc_id,
        engine=engine,
        content_list=items,
        markdown="# Test\nitem 0\nitem 1\nitem 2",
        images=images,
        tables=tables,
        equations=equations,
        metadata={"pages": 5},
    )


class _FakePipeline:
    engine_name = "fake-engine"
    supported_formats = ["pdf", "docx"]

    async def parse_bytes(self, data: bytes, filename: str, **kwargs):
        return _make_result(engine=self.engine_name)

    async def health_check(self):
        return True


class _OutlinePipeline:
    engine_name = "outline-engine"
    supported_formats = ["pdf"]

    async def parse_bytes(self, data: bytes, filename: str, **kwargs):
        items = [
            ContentItem(type=ElementType.TEXT, text="Chapter 1", text_level=1, page_idx=0, reading_order=0),
            ContentItem(type=ElementType.TEXT, text="intro text", text_level=0, page_idx=0, reading_order=1),
            ContentItem(type=ElementType.TEXT, text="Section 1.1", text_level=2, page_idx=1, reading_order=2),
            ContentItem(type=ElementType.TEXT, text="detail text", text_level=0, page_idx=1, reading_order=3),
            ContentItem(type=ElementType.IMAGE, text="", img_path="fig.png", page_idx=1, reading_order=4),
            ContentItem(type=ElementType.TABLE, text="", table_body="<table></table>", page_idx=2, reading_order=5),
            ContentItem(type=ElementType.EQUATION, text="E=mc^2", page_idx=2, reading_order=6),
            ContentItem(type=ElementType.TEXT, text="Chapter 2", text_level=1, page_idx=3, reading_order=7),
            ContentItem(type=ElementType.TEXT, text="ch2 text", text_level=0, page_idx=3, reading_order=8),
        ]
        return PipelineResult(
            document_id="outline-doc",
            engine=self.engine_name,
            content_list=items,
            markdown="# Chapter 1\nintro\n## Section 1.1\ndetail\n# Chapter 2\nch2",
        )

    async def health_check(self):
        return True


class _FailPipeline:
    engine_name = "fail-engine"
    supported_formats = ["txt"]

    async def parse_bytes(self, data: bytes, filename: str, **kwargs):
        raise ParseFailed("simulated failure")

    async def health_check(self):
        return False


def _make_test_registry() -> PipelineRegistry:
    registry = PipelineRegistry()
    registry.register(_FakePipeline())
    registry.register(_OutlinePipeline())
    registry.register(_FailPipeline())
    return registry


@pytest.fixture
def app():
    application = create_app(mineru_url="http://localhost:9999", docling_url="")
    registry = _make_test_registry()
    tm = TaskManager(max_tasks=10, ttl_seconds=60)
    set_globals(registry, tm)
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "engines" in data

    @pytest.mark.asyncio
    async def test_health_lists_engines(self, client):
        resp = await client.get("/v1/health")
        data = resp.json()
        engine_names = [e["name"] for e in data["engines"]]
        assert "fake-engine" in engine_names
        assert "fail-engine" in engine_names

    @pytest.mark.asyncio
    async def test_health_shows_healthy_status(self, client):
        resp = await client.get("/v1/health")
        data = resp.json()
        for eng in data["engines"]:
            if eng["name"] == "fake-engine":
                assert eng["healthy"] is True
            if eng["name"] == "fail-engine":
                assert eng["healthy"] is False


class TestEnginesEndpoint:
    @pytest.mark.asyncio
    async def test_list_engines(self, client):
        resp = await client.get("/v1/engines")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        names = [e["name"] for e in data]
        assert "fake-engine" in names

    @pytest.mark.asyncio
    async def test_engine_format_info(self, client):
        resp = await client.get("/v1/engines")
        data = resp.json()
        for eng in data:
            if eng["name"] == "fake-engine":
                assert "pdf" in eng["supported_formats"]
                assert "docx" in eng["supported_formats"]


class TestParseEndpoint:
    @pytest.mark.asyncio
    async def test_parse_pdf(self, client):
        resp = await client.post(
            "/v1/parse",
            files={"file": ("test.pdf", b"fake pdf data", "application/pdf")},
            data={"engine": "fake-engine"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"] == "fake-engine"
        assert len(data["content_list"]) == 3
        assert data["markdown"] == "# Test\nitem 0\nitem 1\nitem 2"
        assert len(data["images"]) == 1
        assert len(data["tables"]) == 1
        assert len(data["equations"]) == 1
        assert data["metadata"]["pages"] == 5

    @pytest.mark.asyncio
    async def test_parse_returns_content_items(self, client):
        resp = await client.post(
            "/v1/parse",
            files={"file": ("doc.docx", b"fake docx", "application/octet-stream")},
            data={"engine": "fake-engine"},
        )
        data = resp.json()
        for item in data["content_list"]:
            assert "type" in item
            assert "text" in item
            assert "reading_order" in item

    @pytest.mark.asyncio
    async def test_parse_failure_returns_500(self, client):
        resp = await client.post(
            "/v1/parse",
            files={"file": ("fail.txt", b"fail data", "text/plain")},
            data={"engine": "fail-engine"},
        )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_parse_with_default_engine(self, client):
        resp = await client.post(
            "/v1/parse",
            files={"file": ("test.pdf", b"pdf data", "application/pdf")},
            data={"engine": "fake-engine"},
        )
        assert resp.status_code == 200


class TestParseAsyncEndpoint:
    @pytest.mark.asyncio
    async def test_async_parse_returns_task(self, client):
        resp = await client.post(
            "/v1/parse/async",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "fake-engine"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] in ("pending", "processing")
        assert data["filename"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_async_task_completes(self, client):
        resp = await client.post(
            "/v1/parse/async",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "fake-engine"},
        )
        task_id = resp.json()["task_id"]
        await asyncio.sleep(0.5)

        resp2 = await client.get(f"/v1/task/{task_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["status"] == "success"
        assert data["result"] is not None
        assert len(data["result"]["content_list"]) == 3

    @pytest.mark.asyncio
    async def test_async_task_failure(self, client):
        resp = await client.post(
            "/v1/parse/async",
            files={"file": ("fail.txt", b"fail data", "text/plain")},
            data={"engine": "fail-engine"},
        )
        task_id = resp.json()["task_id"]
        await asyncio.sleep(0.5)

        resp2 = await client.get(f"/v1/task/{task_id}")
        data = resp2.json()
        assert data["status"] == "failed"
        assert "simulated failure" in data["error"]


class TestTaskEndpoint:
    @pytest.mark.asyncio
    async def test_task_not_found(self, client):
        resp = await client.get("/v1/task/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_tasks(self, client):
        await client.post(
            "/v1/parse/async",
            files={"file": ("a.pdf", b"aa", "application/pdf")},
            data={"engine": "fake-engine"},
        )
        await client.post(
            "/v1/parse/async",
            files={"file": ("b.pdf", b"bb", "application/pdf")},
            data={"engine": "fake-engine"},
        )
        resp = await client.get("/v1/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    @pytest.mark.asyncio
    async def test_task_result_contains_images_tables_equations(self, client):
        resp = await client.post(
            "/v1/parse/async",
            files={"file": ("test.pdf", b"pdf", "application/pdf")},
            data={"engine": "fake-engine"},
        )
        task_id = resp.json()["task_id"]
        await asyncio.sleep(0.5)

        resp2 = await client.get(f"/v1/task/{task_id}")
        data = resp2.json()
        assert data["result"]["images"][0]["filename"] == "img_0.png"
        assert data["result"]["tables"][0]["html"] == "<table><tr><td>data</td></tr></table>"
        assert data["result"]["equations"][0]["latex"] == "E=mc^2"


class TestOutlineEndpoint:
    @pytest.mark.asyncio
    async def test_outline_returns_structure(self, client):
        resp = await client.post(
            "/v1/outline",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == "outline-doc"
        assert len(data["nodes"]) >= 1
        assert data["total_chapters"] >= 2

    @pytest.mark.asyncio
    async def test_outline_has_nested_structure(self, client):
        resp = await client.post(
            "/v1/outline",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine"},
        )
        data = resp.json()
        ch1 = data["nodes"][0]
        assert ch1["title"] == "Chapter 1"
        assert len(ch1["children"]) >= 1
        assert ch1["children"][0]["title"] == "Section 1.1"

    @pytest.mark.asyncio
    async def test_outline_failure_returns_500(self, client):
        resp = await client.post(
            "/v1/outline",
            files={"file": ("fail.txt", b"fail", "text/plain")},
            data={"engine": "fail-engine"},
        )
        assert resp.status_code == 500


class TestSplitEndpoint:
    @pytest.mark.asyncio
    async def test_split_returns_outline_with_elements(self, client):
        resp = await client.post(
            "/v1/split",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "outline" in data
        assert "element_conservation" in data

    @pytest.mark.asyncio
    async def test_split_conservation_rate(self, client):
        resp = await client.post(
            "/v1/split",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine"},
        )
        data = resp.json()
        cons = data["element_conservation"]
        assert cons["total_elements"] == 9
        assert cons["total_assigned"] == 9
        assert cons["conservation_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_split_chapter_type_counts(self, client):
        resp = await client.post(
            "/v1/split",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine"},
        )
        data = resp.json()
        nodes = data["outline"]["nodes"]
        ch1 = nodes[0]
        s1 = ch1["children"][0]
        assert s1["image_count"] >= 1
        assert s1["table_count"] >= 1
        assert s1["equation_count"] >= 1

    @pytest.mark.asyncio
    async def test_split_chapter_has_markdown(self, client):
        resp = await client.post(
            "/v1/split",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine"},
        )
        data = resp.json()
        ch1 = data["outline"]["nodes"][0]
        assert len(ch1["markdown"]) > 0
        assert "Chapter 1" in ch1["markdown"]

    @pytest.mark.asyncio
    async def test_split_failure_returns_500(self, client):
        resp = await client.post(
            "/v1/split",
            files={"file": ("fail.txt", b"fail", "text/plain")},
            data={"engine": "fail-engine"},
        )
        assert resp.status_code == 500


class TestEnhanceEndpoint:
    @pytest.mark.asyncio
    async def test_enhance_returns_images(self, client):
        resp = await client.post(
            "/v1/enhance",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine", "enable_ocr": "false", "enable_vlm": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == "outline-doc"
        assert data["total_images"] == 1
        assert len(data["enhanced_images"]) == 1
        assert data["enhanced_images"][0]["path"] == "fig.png"
        assert data["ocr_enabled"] is False
        assert data["vlm_enabled"] is False

    @pytest.mark.asyncio
    async def test_enhance_with_ocr_flag(self, client):
        resp = await client.post(
            "/v1/enhance",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine", "enable_ocr": "true", "enable_vlm": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ocr_enabled"] is True

    @pytest.mark.asyncio
    async def test_enhance_failure_returns_500(self, client):
        resp = await client.post(
            "/v1/enhance",
            files={"file": ("fail.txt", b"fail", "text/plain")},
            data={"engine": "fail-engine"},
        )
        assert resp.status_code == 500


class TestReadEndpoint:
    @pytest.mark.asyncio
    async def test_read_returns_structure(self, client):
        resp = await client.post(
            "/v1/read",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine", "enable_llm": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == "outline-doc"
        assert "metadata" in data
        assert "chapters" in data
        assert "cross_chapter_relations" in data

    @pytest.mark.asyncio
    async def test_read_without_llm(self, client):
        resp = await client.post(
            "/v1/read",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={"engine": "outline-engine", "enable_llm": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == "outline-doc"
        assert data["metadata"]["title"] == ""
        assert len(data["chapters"]) == 0

    @pytest.mark.asyncio
    async def test_read_failure_returns_500(self, client):
        resp = await client.post(
            "/v1/read",
            files={"file": ("fail.txt", b"fail", "text/plain")},
            data={"engine": "fail-engine"},
        )
        assert resp.status_code == 500


class TestProcessEndpoint:
    @pytest.mark.asyncio
    async def test_process_basic(self, client):
        resp = await client.post(
            "/v1/process",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={
                "engine": "outline-engine",
                "enable_enhance": "false",
                "enable_read": "false",
                "enable_kg": "false",
                "enable_vectorize": "false",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == "outline-doc"
        assert data["total_duration"] > 0
        stage_names = [s["stage"] for s in data["stages"]]
        assert "toc" in stage_names
        assert "split" in stage_names
        assert data["outline"] is not None

    @pytest.mark.asyncio
    async def test_process_with_all_stages(self, client):
        resp = await client.post(
            "/v1/process",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={
                "engine": "outline-engine",
                "enable_enhance": "true",
                "enable_read": "true",
                "enable_kg": "true",
                "enable_vectorize": "true",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        stage_names = [s["stage"] for s in data["stages"]]
        assert "toc" in stage_names
        assert "split" in stage_names
        assert "enhance" in stage_names
        assert "read" in stage_names
        assert "kg" in stage_names
        assert "vectorize" in stage_names
        all_success = all(s["success"] for s in data["stages"])
        assert all_success is True

    @pytest.mark.asyncio
    async def test_process_failure_returns_500(self, client):
        resp = await client.post(
            "/v1/process",
            files={"file": ("fail.txt", b"fail", "text/plain")},
            data={"engine": "fail-engine"},
        )
        assert resp.status_code == 500


class TestProcessAsyncEndpoint:
    @pytest.mark.asyncio
    async def test_process_async_returns_task(self, client):
        resp = await client.post(
            "/v1/process/async",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={
                "engine": "outline-engine",
                "enable_enhance": "false",
                "enable_read": "false",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] in ("pending", "processing")

    @pytest.mark.asyncio
    async def test_process_async_completes(self, client):
        resp = await client.post(
            "/v1/process/async",
            files={"file": ("test.pdf", b"fake pdf", "application/pdf")},
            data={
                "engine": "outline-engine",
                "enable_enhance": "false",
                "enable_read": "false",
            },
        )
        task_id = resp.json()["task_id"]
        await asyncio.sleep(1.0)

        resp2 = await client.get(f"/v1/task/{task_id}")
        data = resp2.json()
        assert data["status"] == "success"


class TestKGQueryEndpoint:
    @pytest.mark.asyncio
    async def test_kg_query_basic(self, client):
        resp = await client.post(
            "/v1/documents/test-doc/graph/query",
            json={"query": "what is neural network?", "mode": "hybrid"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "what is neural network?"
        assert data["mode"] == "hybrid"

    @pytest.mark.asyncio
    async def test_kg_query_invalid_mode(self, client):
        resp = await client.post(
            "/v1/documents/test-doc/graph/query",
            json={"query": "test", "mode": "invalid_mode"},
        )
        assert resp.status_code == 400


class TestSearchEndpoint:
    @pytest.mark.asyncio
    async def test_search_basic(self, client):
        resp = await client.post(
            "/v1/documents/test-doc/search",
            json={"query": "test", "top_k": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == "test-doc"
        assert data["total_results"] == 0

    @pytest.mark.asyncio
    async def test_search_with_filters(self, client):
        resp = await client.post(
            "/v1/documents/test-doc/search",
            json={"query": "test", "top_k": 3, "chapter_id": "ch1", "score_threshold": 0.5},
        )
        assert resp.status_code == 200
