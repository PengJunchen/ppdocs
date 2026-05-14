import json
from pathlib import Path

base = Path(r'e:\Work\PJC\Github\ppdocs\PDFTest')

for name in ['DeepSeek_V4_pdf_mineru_3.json', 'DeepSeek_V4_pdf_mineru_3_vlm.json']:
    print(f'\n{"="*60}')
    print(f'  {name}')
    print(f'{"="*60}')

    with open(base / name, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for fname, fresult in data.get('results', {}).items():
        cl = fresult.get('content_list', [])
        print(f'content_list type: {type(cl).__name__}, length: {len(cl)}')
        print(f'content_list first 300 chars: {str(cl)[:300]}')

        if isinstance(cl, str):
            try:
                parsed = json.loads(cl)
                print(f'Parsed: type={type(parsed).__name__}, length={len(parsed)}')
                if isinstance(parsed, list) and parsed:
                    item = parsed[0]
                    print(f'First item keys: {list(item.keys())}')
                    for i, item in enumerate(parsed[:5]):
                        tp = item.get('type', '?')
                        tl = item.get('text_level', '?')
                        pi = item.get('page_idx', '?')
                        txt = str(item.get('text', ''))[:80]
                        print(f'  [{i}] type={tp} text_level={tl} page_idx={pi} text={txt}')

                    types = set()
                    levels = set()
                    for item in parsed[:2000]:
                        if isinstance(item, dict):
                            types.add(item.get('type', 'MISSING'))
                            levels.add(item.get('text_level', 'MISSING'))
                    print(f'\nTypes (first 2000): {sorted(types)}')
                    print(f'Levels (first 2000): {sorted([str(l) for l in levels])}')

                    for t in sorted(types):
                        count = sum(1 for item in parsed if isinstance(item, dict) and item.get('type') == t)
                        print(f'  type={t}: count={count}')
            except json.JSONDecodeError as e:
                print(f'JSON parse error: {e}')

        md = fresult.get('md_content', '')
        print(f'\nmd_content length: {len(md)}')

        images = fresult.get('images', {})
        print(f'images type: {type(images).__name__}')
        if isinstance(images, dict):
            print(f'images count: {len(images)}')
            for k in list(images.keys())[:2]:
                v = images[k]
                print(f'  key={k}: type={type(v).__name__}, len={len(str(v))}')
