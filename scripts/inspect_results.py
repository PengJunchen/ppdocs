import json
import sys

def inspect_mineru_result(filepath, label):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f'\n{"="*60}')
    print(f'  {label}')
    print(f'{"="*60}')

    print(f'Top-level keys: {list(data.keys())}')
    for k in ['task_id', 'status', 'backend', 'version']:
        print(f'  {k}: {data.get(k)}')

    results = data.get('results', {})
    print(f'\nResults keys: {list(results.keys())}')
    for fname, fresult in results.items():
        print(f'\nFile: {fname}')
        print(f'  Keys: {list(fresult.keys())}')

        cl = fresult.get('content_list', [])
        print(f'  content_list length: {len(cl)}')
        if cl:
            first = cl[0]
            print(f'  First item keys: {list(first.keys()) if isinstance(first, dict) else type(first)}')
            print(f'  First 3 items:')
            for i, item in enumerate(cl[:3]):
                if isinstance(item, dict):
                    tp = item.get('type', '?')
                    tl = item.get('text_level', '?')
                    pi = item.get('page_idx', '?')
                    ro = item.get('reading_order', '?')
                    txt = str(item.get('text', ''))[:80]
                    print(f'    [{i}] type={tp}, text_level={tl}, page_idx={pi}, reading_order={ro}')
                    print(f'        text={txt}')

        md = fresult.get('md_content', '')
        print(f'  md_content length: {len(md)}')

        for k2 in fresult.keys():
            if k2 not in ['content_list', 'md_content']:
                val = fresult[k2]
                if isinstance(val, (list, dict)):
                    print(f'  {k2}: {type(val).__name__} len={len(val)}')
                else:
                    print(f'  {k2}: {str(val)[:100]}')

    # Collect all unique types and text_levels
    for fname, fresult in results.items():
        cl = fresult.get('content_list', [])
        types = set()
        levels = set()
        for item in cl:
            if isinstance(item, dict):
                types.add(item.get('type', 'MISSING'))
                levels.add(item.get('text_level', 'MISSING'))
        print(f'\n  Unique types: {sorted(types)}')
        print(f'  Unique text_levels: {sorted([str(l) for l in levels])}')

        # Sample items of each type
        for t in sorted(types):
            items_of_type = [item for item in cl if isinstance(item, dict) and item.get('type') == t]
            if items_of_type:
                sample = items_of_type[0]
                print(f'\n  Sample type={t}:')
                for k3, v3 in sample.items():
                    val_str = str(v3)[:100]
                    print(f'    {k3}: {val_str}')

if __name__ == '__main__':
    base = r'e:\Work\PJC\Github\ppdocs\PDFTest'
    inspect_mineru_result(f'{base}\\DeepSeek_V4_pdf_mineru_3.json', 'MinerU Pipeline')
    inspect_mineru_result(f'{base}\\DeepSeek_V4_pdf_mineru_3_vlm.json', 'MinerU VLM')
