import json

def inspect_parsed(filepath, label):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f'\n{"="*60}')
    print(f'  {label}')
    print(f'{"="*60}')

    for fname, fresult in data.get('results', {}).items():
        cl_raw = fresult.get('content_list', [])
        content_str = ''.join(cl_raw)
        print(f'content_list joined length: {len(content_str)}')
        print(f'content_list first 500 chars: {content_str[:500]}')

        try:
            cl = json.loads(content_str)
            print(f'\nParsed content_list length: {len(cl)}')
            if cl:
                print(f'First item type: {type(cl[0])}')
                if isinstance(cl[0], dict):
                    print(f'First item keys: {list(cl[0].keys())}')
                    for i, item in enumerate(cl[:5]):
                        print(f'  [{i}]: {json.dumps(item, ensure_ascii=False)[:300]}')

                types = set()
                levels = set()
                for item in cl[:1000]:
                    if isinstance(item, dict):
                        types.add(item.get('type', 'MISSING'))
                        levels.add(item.get('text_level', 'MISSING'))
                print(f'\nUnique types (first 1000): {sorted(types)}')
                print(f'Unique text_levels (first 1000): {sorted([str(l) for l in levels])}')

                for t in sorted(types):
                    items_of_type = [item for item in cl[:2000] if isinstance(item, dict) and item.get('type') == t]
                    if items_of_type:
                        sample = items_of_type[0]
                        print(f'\n  Sample type={t}:')
                        for k3, v3 in sample.items():
                            val_str = str(v3)[:150]
                            print(f'    {k3}: {val_str}')
        except json.JSONDecodeError as e:
            print(f'JSON parse error: {e}')
            print(f'Around position: {content_str[max(0,e.pos-50):e.pos+50]}')

        images = fresult.get('images', {})
        print(f'\nimages count: {len(images)}')
        for k in list(images.keys())[:1]:
            v = images[k]
            print(f'  image key={k}: type={type(v)}, len={len(v)}, prefix={str(v)[:80]}')

        mo_raw = fresult.get('model_output', '')
        if isinstance(mo_raw, str):
            print(f'\nmodel_output is string, length: {len(mo_raw)}')
            print(f'model_output first 500 chars: {mo_raw[:500]}')
        elif isinstance(mo_raw, list):
            print(f'\nmodel_output is list, length: {len(mo_raw)}')

if __name__ == '__main__':
    base = r'e:\Work\PJC\Github\ppdocs\PDFTest'
    inspect_parsed(f'{base}\\DeepSeek_V4_pdf_mineru_3.json', 'MinerU Pipeline - Parsed')
    inspect_parsed(f'{base}\\DeepSeek_V4_pdf_mineru_3_vlm.json', 'MinerU VLM - Parsed')
