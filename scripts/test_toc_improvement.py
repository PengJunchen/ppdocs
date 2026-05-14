
import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from doc_parser.core.chapter.toc import StrategyA_TitleAggregation
from doc_parser.pipeline.base import PipelineResult, ContentItem, ElementType


def test_with_mineru_data():
    """Test TOC extraction with real MinerU data from DeepSeek-V4 paper"""
    print("=" * 80)
    print("Testing TOC Extraction Improvement with DeepSeek-V4 Paper")
    print("=" * 80)

    # Load MinerU raw data
    mineru_path = Path(r"e:\Work\PJC\Github\ppdocs\PDFTest\DeepSeek_V4_pdf_mineru_3.json")
    with open(mineru_path, encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", {})
    file_name = list(results.keys())[0]
    file_data = results[file_name]

    # Parse content_list
    content_list_str = file_data.get("content_list", "")
    if isinstance(content_list_str, str):
        content_list_raw = json.loads(content_list_str)
    else:
        content_list_raw = content_list_str

    # Create PipelineResult
    content_items = []
    for item in content_list_raw:
        content_items.append(ContentItem(
            type=ElementType(item.get("type", "text")),
            text=item.get("text", ""),
            text_level=item.get("text_level", 0),
            page_idx=item.get("page_idx", 0),
            reading_order=item.get("reading_order", 0),
        ))

    result = PipelineResult(
        document_id="test_doc",
        content_list=content_items,
    )

    # Test StrategyA
    strategy = StrategyA_TitleAggregation()
    import asyncio

    outline = asyncio.run(strategy.extract(result))

    print(f"\nTotal nodes: {len(outline.nodes)}")
    print("\n" + "=" * 80)
    print("TOC Tree Structure:")
    print("=" * 80)

    def print_tree(nodes: list, indent=0):
        for node in nodes:
            prefix = "  " * indent
            print(f"{prefix}[Level {node.level}] {node.title} (page {node.page_start}-{node.page_end})")
            if node.children:
                print_tree(node.children, indent + 1)

    print_tree(outline.nodes)

    print("\n" + "=" * 80)
    print("All chapters with levels:")
    print("=" * 80)

    all_chapters = outline.get_all_chapters()
    for i, ch in enumerate(all_chapters):
        print(f"[{i:3d}] Level {ch.level} - {ch.title}")

    print(f"\n✅ Successfully extracted {len(all_chapters)} chapters with proper hierarchy!")


if __name__ == "__main__":
    test_with_mineru_data()
