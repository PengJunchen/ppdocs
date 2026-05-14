import asyncio
import json
import sys
sys.path.insert(0, ".")

from doc_parser.pipeline.mineru import MinerUPipeline
from doc_parser.pipeline.base import PipelineConfig
from doc_parser.core.chapter import TOCExtractor, ChapterSplitter


PIPELINE_JSON = "PDFTest/DeepSeek_V4_pdf_mineru_3.json"
VLM_JSON = "PDFTest/DeepSeek_V4_pdf_mineru_3_vlm.json"


async def validate_with_fixture(json_path: str, label: str):
    print(f"\n{'='*60}")
    print(f"Validating Phase 2 with {label}: {json_path}")
    print(f"{'='*60}")

    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    pipeline = MinerUPipeline(PipelineConfig(base_url="http://localhost"))
    result = pipeline._transform_result(raw)

    print(f"\nPipelineResult:")
    print(f"  document_id: {result.document_id}")
    print(f"  content_list: {len(result.content_list)} items")
    print(f"  images: {len(result.images)}")
    print(f"  tables: {len(result.tables)}")
    print(f"  equations: {len(result.equations)}")

    headings = [i for i in result.content_list if i.text_level > 0]
    print(f"  headings: {len(headings)}")
    for h in headings[:10]:
        print(f"    H{h.text_level}: {h.text[:80]} (page {h.page_idx})")

    extractor = TOCExtractor()
    outline = await extractor.extract(result)

    print(f"\nDocumentOutline:")
    print(f"  total_chapters: {outline.total_chapters}")
    for node in outline.nodes:
        _print_node(node, "  ")

    splitter = ChapterSplitter()
    outline = await splitter.split(result, outline)

    print(f"\nAfter ChapterSplitter:")
    all_ch = outline.get_all_chapters()
    total_assigned = sum(len(ch.element_indices) for ch in all_ch)
    print(f"  chapters: {len(all_ch)}")
    print(f"  total elements: {len(result.content_list)}")
    print(f"  total assigned: {total_assigned}")
    rate = total_assigned / len(result.content_list) if result.content_list else 1.0
    print(f"  conservation rate: {rate:.1%}")

    for ch in all_ch[:10]:
        print(f"    [{ch.id}] H{ch.level} {ch.title[:50]} | elems={len(ch.element_indices)} | imgs={ch.image_count} tbls={ch.table_count} eqs={ch.equation_count} | md={len(ch.markdown)} chars")

    passed = rate >= 0.95
    status = "PASS" if passed else "FAIL"
    print(f"\n  Conservation VG: {status} (rate={rate:.1%}, threshold=95%)")
    return passed


def _print_node(node, prefix: str):
    print(f"{prefix}[{node.id}] H{node.level} {node.title[:60]} (p{node.page_start}-{node.page_end})")
    for child in node.children:
        _print_node(child, prefix + "  ")


async def main():
    results = []

    try:
        r1 = await validate_with_fixture(PIPELINE_JSON, "Pipeline")
        results.append(("Pipeline", r1))
    except Exception as e:
        print(f"Pipeline fixture failed: {e}")
        results.append(("Pipeline", False))

    try:
        r2 = await validate_with_fixture(VLM_JSON, "VLM")
        results.append(("VLM", r2))
    except Exception as e:
        print(f"VLM fixture failed: {e}")
        results.append(("VLM", False))

    print(f"\n{'='*60}")
    print("Phase 2 Validation Summary")
    print(f"{'='*60}")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")


asyncio.run(main())
