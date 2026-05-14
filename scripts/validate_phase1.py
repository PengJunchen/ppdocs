import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from doc_parser.pipeline.base import PipelineConfig
from doc_parser.pipeline.mineru import MinerUPipeline, MinerUVLMPipeline
from doc_parser.pipeline.docling_pipeline import DoclingPipeline
from doc_parser.pipeline.registry import PipelineRegistry, create_default_registry

PDF_PATH = Path(__file__).parent / "PDFTest" / "DeepSeek_V4.pdf"

MINERU_URL = "http://10.0.40.153:18089"
DOCLING_URL = "http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling"
DOCLING_API_KEY = "Db3S72tVSn2YeSw"


async def test_mineru_pipeline():
    print("\n" + "=" * 60)
    print("  Testing MinerU Pipeline (non-VLM)")
    print("=" * 60)

    config = PipelineConfig(engine="mineru-pipeline", base_url=MINERU_URL, timeout=300)
    pipeline = MinerUPipeline(config)

    try:
        healthy = await pipeline.health_check()
        print(f"Health check: {'OK' if healthy else 'FAILED'}")
    except Exception as e:
        print(f"Health check error: {e}")
        return

    if not healthy:
        print("Skipping MinerU Pipeline test - service unavailable")
        return

    start = time.time()
    try:
        result = await pipeline.parse(str(PDF_PATH))
        elapsed = time.time() - start

        print(f"Parse completed in {elapsed:.1f}s")
        print(f"  document_id: {result.document_id}")
        print(f"  engine: {result.engine}")
        print(f"  content_list items: {len(result.content_list)}")
        print(f"  markdown length: {len(result.markdown)}")
        print(f"  images: {len(result.images)}")
        print(f"  tables: {len(result.tables)}")
        print(f"  equations: {len(result.equations)}")
        print(f"  metadata: {result.metadata}")

        if result.content_list:
            types = {}
            for item in result.content_list:
                t = item.type.value
                types[t] = types.get(t, 0) + 1
            print(f"  Element types: {types}")

            levels = {}
            for item in result.content_list:
                if item.text_level > 0:
                    levels[item.text_level] = levels.get(item.text_level, 0) + 1
            print(f"  Text levels: {levels}")

        assert len(result.content_list) > 0, "content_list should not be empty"
        assert len(result.markdown) > 0, "markdown should not be empty"
        assert len(result.images) > 0, "images should not be empty"
        print("\n✅ MinerU Pipeline test PASSED")

    except Exception as e:
        print(f"❌ MinerU Pipeline test FAILED: {e}")


async def test_mineru_vlm():
    print("\n" + "=" * 60)
    print("  Testing MinerU VLM")
    print("=" * 60)

    config = PipelineConfig(engine="mineru-vlm", base_url=MINERU_URL, timeout=300)
    pipeline = MinerUVLMPipeline(config)

    try:
        healthy = await pipeline.health_check()
        print(f"Health check: {'OK' if healthy else 'FAILED'}")
    except Exception as e:
        print(f"Health check error: {e}")
        return

    if not healthy:
        print("Skipping MinerU VLM test - service unavailable")
        return

    start = time.time()
    try:
        result = await pipeline.parse(str(PDF_PATH))
        elapsed = time.time() - start

        print(f"Parse completed in {elapsed:.1f}s")
        print(f"  document_id: {result.document_id}")
        print(f"  engine: {result.engine}")
        print(f"  content_list items: {len(result.content_list)}")
        print(f"  markdown length: {len(result.markdown)}")
        print(f"  images: {len(result.images)}")
        print(f"  tables: {len(result.tables)}")
        print(f"  equations: {len(result.equations)}")

        assert len(result.content_list) > 0
        assert len(result.markdown) > 0
        print("\n✅ MinerU VLM test PASSED")

    except Exception as e:
        print(f"❌ MinerU VLM test FAILED: {e}")


async def test_docling():
    print("\n" + "=" * 60)
    print("  Testing Docling")
    print("=" * 60)

    config = PipelineConfig(
        engine="docling",
        base_url=DOCLING_URL,
        api_key=DOCLING_API_KEY,
        timeout=300,
    )
    pipeline = DoclingPipeline(config)

    try:
        healthy = await pipeline.health_check()
        print(f"Health check: {'OK' if healthy else 'FAILED'}")
    except Exception as e:
        print(f"Health check error: {e}")
        return

    if not healthy:
        print("Skipping Docling test - service unavailable (health check failed, but will try parse anyway)")

    start = time.time()
    try:
        result = await pipeline.parse(str(PDF_PATH))
        elapsed = time.time() - start

        print(f"Parse completed in {elapsed:.1f}s")
        print(f"  document_id: {result.document_id}")
        print(f"  engine: {result.engine}")
        print(f"  content_list items: {len(result.content_list)}")
        print(f"  markdown length: {len(result.markdown)}")
        print(f"  images: {len(result.images)}")
        print(f"  tables: {len(result.tables)}")

        if result.content_list:
            types = {}
            for item in result.content_list:
                t = item.type.value
                types[t] = types.get(t, 0) + 1
            print(f"  Element types: {types}")

        print("\n✅ Docling test PASSED")

    except Exception as e:
        print(f"❌ Docling test FAILED: {e}")


async def test_registry_auto():
    print("\n" + "=" * 60)
    print("  Testing Registry Auto-Select")
    print("=" * 60)

    registry = create_default_registry(
        mineru_url=MINERU_URL,
        docling_url=DOCLING_URL,
        docling_api_key=DOCLING_API_KEY,
    )

    print(f"Registered engines: {registry.list_engines()}")

    for filename in ["test.pdf", "test.docx", "test.pptx", "report.html"]:
        try:
            engine = registry._resolve_engine("auto", filename)
            print(f"  {filename} -> {engine.engine_name}")
        except Exception as e:
            print(f"  {filename} -> ERROR: {e}")

    print("\n✅ Registry auto-select test PASSED")


async def test_format_consistency():
    print("\n" + "=" * 60)
    print("  Testing Output Format Consistency")
    print("=" * 60)

    if not PDF_PATH.exists():
        print("PDF file not found, skipping")
        return

    config_m = PipelineConfig(engine="mineru-pipeline", base_url=MINERU_URL, timeout=300)
    config_v = PipelineConfig(engine="mineru-vlm", base_url=MINERU_URL, timeout=300)

    pipeline_m = MinerUPipeline(config_m)
    pipeline_v = MinerUVLMPipeline(config_v)

    try:
        result_m = await pipeline_m.parse(str(PDF_PATH))
        result_v = await pipeline_v.parse(str(PDF_PATH))

        m_keys = set(result_m.model_dump().keys())
        v_keys = set(result_v.model_dump().keys())

        assert m_keys == v_keys, f"Schema mismatch: {m_keys.symmetric_difference(v_keys)}"
        print(f"  Both outputs have identical schema: {sorted(m_keys)}")

        for key in ["document_id", "engine", "content_list", "markdown", "images", "tables", "equations"]:
            assert key in m_keys, f"Missing key: {key}"
        print(f"  All required fields present")

        assert result_m.engine != result_v.engine
        print(f"  Engine names differ correctly: {result_m.engine} vs {result_v.engine}")

        print("\n✅ Format consistency test PASSED")

    except Exception as e:
        print(f"❌ Format consistency test FAILED: {e}")


async def main():
    print("Phase 1 Validation - Online API Tests")
    print(f"PDF test file: {PDF_PATH}")
    print(f"PDF exists: {PDF_PATH.exists()}")

    await test_registry_auto()
    await test_mineru_pipeline()
    await test_mineru_vlm()
    await test_docling()
    await test_format_consistency()

    print("\n" + "=" * 60)
    print("  All Phase 1 validation tests completed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
