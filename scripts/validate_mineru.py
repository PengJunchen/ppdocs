import asyncio
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from doc_parser.pipeline.base import PipelineConfig
from doc_parser.pipeline.mineru import MinerUPipeline, MinerUVLMPipeline

PDF_PATH = Path(__file__).parent / "PDFTest" / "DeepSeek_V4.pdf"
MINERU_URL = "http://10.0.40.153:18089"


async def test_mineru():
    print("=" * 60)
    print("  MinerU Pipeline Test")
    print("=" * 60)

    config = PipelineConfig(engine="mineru-pipeline", base_url=MINERU_URL, timeout=300)
    pipeline = MinerUPipeline(config)

    start = time.time()
    try:
        result = await pipeline.parse(str(PDF_PATH))
        elapsed = time.time() - start
        print(f"Parse completed in {elapsed:.1f}s")
        print(f"  engine: {result.engine}")
        print(f"  content_list: {len(result.content_list)} items")
        print(f"  markdown: {len(result.markdown)} chars")
        print(f"  images: {len(result.images)}")
        print(f"  tables: {len(result.tables)}")
        print(f"  equations: {len(result.equations)}")

        types = {}
        for item in result.content_list:
            t = item.type.value
            types[t] = types.get(t, 0) + 1
        print(f"  types: {types}")

        levels = {}
        for item in result.content_list:
            if item.text_level > 0:
                levels[item.text_level] = levels.get(item.text_level, 0) + 1
        print(f"  text_levels: {levels}")

        print("\n✅ PASSED")
    except Exception as e:
        print(f"❌ FAILED: {e}")


async def test_mineru_vlm():
    print("\n" + "=" * 60)
    print("  MinerU VLM Test")
    print("=" * 60)

    config = PipelineConfig(engine="mineru-vlm", base_url=MINERU_URL, timeout=300)
    pipeline = MinerUVLMPipeline(config)

    start = time.time()
    try:
        result = await pipeline.parse(str(PDF_PATH))
        elapsed = time.time() - start
        print(f"Parse completed in {elapsed:.1f}s")
        print(f"  engine: {result.engine}")
        print(f"  content_list: {len(result.content_list)} items")
        print(f"  markdown: {len(result.markdown)} chars")
        print(f"  images: {len(result.images)}")
        print(f"  tables: {len(result.tables)}")
        print(f"  equations: {len(result.equations)}")

        types = {}
        for item in result.content_list:
            t = item.type.value
            types[t] = types.get(t, 0) + 1
        print(f"  types: {types}")

        print("\n✅ PASSED")
    except Exception as e:
        print(f"❌ FAILED: {e}")


async def main():
    await test_mineru()
    await test_mineru_vlm()

if __name__ == "__main__":
    asyncio.run(main())
