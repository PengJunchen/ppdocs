import asyncio
import json
import sys
sys.path.insert(0, ".")

from doc_parser.pipeline.mineru import MinerUVLMPipeline
from doc_parser.pipeline.base import PipelineConfig, ParseFailed, ParseTimeout

MINERU_URL = "http://10.0.40.153:18089"
PDF_PATH = "PDFTest/DeepSeek_V4.pdf"


async def test_mineru_raw():
    config = PipelineConfig(base_url=MINERU_URL, timeout=120)
    pipeline = MinerUVLMPipeline(config)

    try:
        result = await pipeline.parse(PDF_PATH)
        print(f"Items: {len(result.content_list)}")
        print(f"Markdown length: {len(result.markdown)}")
        print(f"Images: {len(result.images)}")
        print(f"Tables: {len(result.tables)}")
        print(f"Equations: {len(result.equations)}")
        print(f"Metadata: {result.metadata}")

        if result.raw_result:
            raw = result.raw_result
            print(f"\nRaw result keys: {list(raw.keys())}")
            results = raw.get("results", {})
            for fname, fdata in results.items():
                print(f"\nFile: {fname}")
                if isinstance(fdata, dict):
                    print(f"  Keys: {list(fdata.keys())}")
                    cl = fdata.get("content_list")
                    if cl is not None:
                        print(f"  content_list type: {type(cl).__name__}")
                        if isinstance(cl, str):
                            print(f"  content_list string length: {len(cl)}")
                            try:
                                parsed = json.loads(cl)
                                print(f"  Parsed content_list length: {len(parsed)}")
                                if parsed:
                                    print(f"  First item keys: {list(parsed[0].keys()) if isinstance(parsed[0], dict) else type(parsed[0])}")
                            except:
                                print(f"  content_list first 200 chars: {cl[:200]}")
                        elif isinstance(cl, list):
                            print(f"  content_list list length: {len(cl)}")
                            if cl:
                                print(f"  First item type: {type(cl[0]).__name__}")
                                if isinstance(cl[0], str):
                                    print(f"  First item: {cl[0][:200]}")
                    md = fdata.get("md_content", "")
                    print(f"  md_content length: {len(md)}")
        else:
            print("No raw_result")

    except ParseFailed as e:
        print(f"ParseFailed: {e}")
    except ParseTimeout as e:
        print(f"ParseTimeout: {e}")


asyncio.run(test_mineru_raw())
