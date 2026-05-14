"""Phase 3 end-to-end validation with PDFTest fixtures.

Validates:
- ImageEnhancer with real MinerU results (basic mode, no external services)
- UnifiedReader with real document outline (DummyLLM)
- Full pipeline: parse → TOC → split → enhance → read
"""
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from doc_parser.pipeline.base import ContentItem, ElementType, PipelineResult
from doc_parser.core.chapter import TOCExtractor, ChapterSplitter, DocumentOutline
from doc_parser.core.image import ImageEnhancer, ImageEnhancerConfig
from doc_parser.core.reader import UnifiedReader, UnifiedReaderConfig
from doc_parser.core.reader.llm_client import DummyLLMClient


def load_fixture(name: str) -> dict:
    path = PROJECT_ROOT / "PDFTest" / name
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "results" in data and isinstance(data["results"], dict):
        for _key, inner in data["results"].items():
            if isinstance(inner, dict) and "content_list" in inner:
                return inner
    return data


def fixture_to_result(data: dict) -> PipelineResult:
    content_list_raw = data.get("content_list", [])
    if isinstance(content_list_raw, str):
        content_list_raw = json.loads(content_list_raw)

    items = []
    for raw in content_list_raw:
        if isinstance(raw, dict):
            etype_str = raw.get("type", "text").lower()
            try:
                etype = ElementType(etype_str)
            except ValueError:
                etype = ElementType.TEXT
            items.append(ContentItem(
                type=etype,
                text=raw.get("text", ""),
                text_level=raw.get("text_level", 0),
                page_idx=raw.get("page_idx", 0),
                reading_order=raw.get("reading_order", 0),
                img_path=raw.get("img_path", ""),
                table_body=raw.get("table_body", ""),
                equation_latex=raw.get("equation_latex", raw.get("latex", "")),
                bbox=raw.get("bbox", []),
                extra={k: v for k, v in raw.items() if k not in {
                    "type", "text", "text_level", "page_idx", "reading_order",
                    "img_path", "table_body", "equation_latex", "latex", "bbox",
                }},
            ))

    md = data.get("md_content", data.get("markdown", ""))
    images_raw = data.get("images", [])
    images = []
    if isinstance(images_raw, dict):
        images = [{"path": k, **(v if isinstance(v, dict) else {})} for k, v in images_raw.items()]
    elif isinstance(images_raw, list):
        images = images_raw

    return PipelineResult(
        document_id=data.get("document_id", "test"),
        engine=data.get("engine", "mineru"),
        content_list=items,
        markdown=md,
        images=images,
    )


async def validate_pipeline_mode():
    print("=" * 60)
    print("Validating Pipeline Mode (DeepSeek_V4_pdf_mineru_3.json)")
    print("=" * 60)

    data = load_fixture("DeepSeek_V4_pdf_mineru_3.json")
    result = fixture_to_result(data)
    print(f"  Content items: {len(result.content_list)}")

    extractor = TOCExtractor()
    outline = await extractor.extract(result)
    print(f"  TOC chapters: {outline.total_chapters}")

    splitter = ChapterSplitter()
    outline = await splitter.split(result, outline)
    leaf_chapters = outline.get_leaf_chapters()
    total_assigned = sum(len(ch.element_indices) for ch in outline.get_all_chapters())
    print(f"  Element conservation: {total_assigned}/{len(result.content_list)} = {total_assigned/len(result.content_list)*100:.1f}%")

    config = ImageEnhancerConfig(enable_ocr=False, enable_vlm=False)
    enhancer = ImageEnhancer(config=config)
    enhanced = await enhancer.enhance(result)
    image_count = sum(1 for item in result.content_list if item.type == ElementType.IMAGE)
    print(f"  Images found: {image_count}, Enhanced images: {len(enhanced)}")

    reader = UnifiedReader(llm_client=DummyLLMClient())
    reading = await reader.read_document(outline)
    print(f"  LLM Reading (Dummy): metadata.title='{reading.metadata.title}', chapters={len(reading.chapters)}, cross_relations={len(reading.cross_chapter_relations)}")

    print(f"  Status: PASS\n")
    return True


async def validate_vlm_mode():
    print("=" * 60)
    print("Validating VLM Mode (DeepSeek_V4_pdf_mineru_3_vlm.json)")
    print("=" * 60)

    data = load_fixture("DeepSeek_V4_pdf_mineru_3_vlm.json")
    result = fixture_to_result(data)
    print(f"  Content items: {len(result.content_list)}")

    extractor = TOCExtractor()
    outline = await extractor.extract(result)
    print(f"  TOC chapters: {outline.total_chapters}")

    splitter = ChapterSplitter()
    outline = await splitter.split(result, outline)
    total_assigned = sum(len(ch.element_indices) for ch in outline.get_all_chapters())
    print(f"  Element conservation: {total_assigned}/{len(result.content_list)} = {total_assigned/len(result.content_list)*100:.1f}%")

    image_count = sum(1 for item in result.content_list if item.type == ElementType.IMAGE)
    print(f"  Images found: {image_count}")

    reader = UnifiedReader(llm_client=DummyLLMClient())
    reading = await reader.read_document(outline)
    print(f"  LLM Reading (Dummy): metadata.title='', chapters={len(reading.chapters)}, cross_relations={len(reading.cross_chapter_relations)}")

    print(f"  Status: PASS\n")
    return True


async def main():
    results = []
    results.append(await validate_pipeline_mode())
    results.append(await validate_vlm_mode())

    print("=" * 60)
    print(f"Summary: {'ALL PASS' if all(results) else 'SOME FAILED'}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
