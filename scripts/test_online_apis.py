import asyncio
import sys
sys.path.insert(0, ".")

from doc_parser.pipeline.mineru import MinerUVLMPipeline, MinerUPipeline
from doc_parser.pipeline.docling_pipeline import DoclingPipeline
from doc_parser.pipeline.base import PipelineConfig, ParseFailed
from doc_parser.pipeline.registry import create_default_registry

MINERU_URL = "http://10.0.40.153:18089"
DOCLING_URL = "http://uatapi.shanghai-electric.com/apigatewaytest/SEDTAIGC/docling"
DOCLING_API_KEY = "Db3S72tVSn2YeSw"
PDF_PATH = "PDFTest/DeepSeek_V4.pdf"


async def test_mineru_vlm():
    print("=" * 60)
    print("Test: MinerU VLM parse with markdown-to-content_list")
    print("=" * 60)
    config = PipelineConfig(base_url=MINERU_URL, timeout=120)
    pipeline = MinerUVLMPipeline(config)
    try:
        result = await pipeline.parse(PDF_PATH)
        print(f"  Items: {len(result.content_list)}")
        print(f"  Markdown: {len(result.markdown)} chars")
        if result.content_list:
            headings = [i for i in result.content_list if i.text_level > 0]
            texts = [i for i in result.content_list if i.text_level == 0]
            print(f"  Headings: {len(headings)}")
            print(f"  Text lines: {len(texts)}")
            for h in headings[:5]:
                print(f"    H{h.text_level}: {h.text[:60]}")
    except ParseFailed as e:
        print(f"  ParseFailed: {e}")


async def test_mineru_pipeline():
    print("\n" + "=" * 60)
    print("Test: MinerU Pipeline parse (non-VLM)")
    print("=" * 60)
    config = PipelineConfig(base_url=MINERU_URL, timeout=120)
    pipeline = MinerUPipeline(config)
    try:
        result = await pipeline.parse(PDF_PATH)
        print(f"  Items: {len(result.content_list)}")
        print(f"  Markdown: {len(result.markdown)} chars")
        print(f"  Images: {len(result.images)}")
        print(f"  Tables: {len(result.tables)}")
        print(f"  Equations: {len(result.equations)}")
    except ParseFailed as e:
        print(f"  ParseFailed (expected - CUDA OOM): {str(e)[:200]}")


async def test_docling():
    print("\n" + "=" * 60)
    print("Test: Docling parse (API gateway)")
    print("=" * 60)
    config = PipelineConfig(
        base_url=DOCLING_URL,
        api_key=DOCLING_API_KEY,
        timeout=30,
    )
    pipeline = DoclingPipeline(config)
    print(f"  Default auth_header: {pipeline._auth_header}")
    print(f"  Default auth_prefix: '{pipeline._auth_prefix}'")
    print(f"  Built headers: {pipeline._build_auth_headers()}")

    health = await pipeline.health_check()
    print(f"  health_check: {health}")

    try:
        with open(PDF_PATH, "rb") as f:
            pdf_data = f.read()
        result = await pipeline.parse_bytes(pdf_data, "DeepSeek_V4.pdf")
        print(f"  Parse succeeded! Items: {len(result.content_list)}")
    except ParseFailed as e:
        print(f"  ParseFailed (expected - Kong gateway): {e}")


async def test_registry():
    print("\n" + "=" * 60)
    print("Test: Registry auto_select")
    print("=" * 60)
    registry = create_default_registry(
        mineru_url=MINERU_URL,
        docling_url=DOCLING_URL,
        docling_api_key=DOCLING_API_KEY,
    )
    for fname in ["test.pdf", "report.docx", "slides.pptx", "page.html", "readme.md", "data.xlsx"]:
        engine = registry._resolve_engine("auto", fname)
        print(f"  {fname:20s} -> {engine.engine_name}")


async def main():
    await test_mineru_vlm()
    await test_mineru_pipeline()
    await test_docling()
    await test_registry()
    print("\n" + "=" * 60)
    print("All online tests complete!")
    print("=" * 60)


asyncio.run(main())
