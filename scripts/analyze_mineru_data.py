
import json
from pathlib import Path

def analyze_mineru_data():
    # Read MinerU raw data
    mineru_path = Path(r"e:\Work\PJC\Github\ppdocs\PDFTest\DeepSeek_V4_pdf_mineru_3.json")
    with open(mineru_path, encoding="utf-8") as f:
        data = json.load(f)
    
    # Get content_list
    results = data.get("results", {})
    file_name = list(results.keys())[0]
    file_data = results[file_name]
    
    # content_list might be JSON string
    content_list_str = file_data.get("content_list", "")
    if isinstance(content_list_str, str):
        content_list = json.loads(content_list_str)
    else:
        content_list = content_list_str
    
    print(f"Total elements: {len(content_list)}")
    print("\n" + "="*80)
    print("Top 100 elements (text_level):")
    print("="*80)
    
    for i, item in enumerate(content_list[:100]):
        item_type = item.get("type", "")
        text_level = item.get("text_level", 0)
        text = item.get("text", "")[:80]
        page_idx = item.get("page_idx", 0)
        print(f"[{i:3d}] type={item_type:15s} level={text_level} page={page_idx} text={text}")
    
    print("\n" + "="*80)
    print("All heading items (text_level > 0):")
    print("="*80)
    
    headings = []
    for i, item in enumerate(content_list):
        text_level = item.get("text_level", 0)
        if text_level > 0:
            headings.append({
                "index": i,
                "type": item.get("type", ""),
                "text_level": text_level,
                "text": item.get("text", ""),
                "page_idx": item.get("page_idx", 0),
            })
    
    print(f"Found {len(headings)} headings")
    for h in headings:
        print(f"[{h['index']:4d}] level={h['text_level']} page={h['page_idx']} text={h['text']}")

if __name__ == "__main__":
    analyze_mineru_data()
