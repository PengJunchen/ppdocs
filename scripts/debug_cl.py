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

        if isinstance(cl, list) and len(cl) > 0:
            first = cl[0]
            print(f'first element type: {type(first).__name__}')

            if isinstance(first, str):
                joined = ''.join(cl)
                print(f'joined length: {len(joined)}')
                print(f'joined first 300 chars: {joined[:300]}')

                try:
                    parsed = json.loads(joined)
                    print(f'Parsed as JSON: type={type(parsed).__name__}, length={len(parsed)}')
                    if isinstance(parsed, list) and parsed:
                        print(f'First item type: {type(parsed[0]).__name__}')
                        if isinstance(parsed[0], dict):
                            print(f'First item keys: {list(parsed[0].keys())}')
                            print(f'First 3 items (short):')
                            for i, item in enumerate(parsed[:3]):
                                tp = item.get('type', '?')
                                tl = item.get('text_level', '?')
                                txt = str(item.get('text', ''))[:80]
                                print(f'  [{i}] type={tp} text_level={tl} text={txt}')

                        types = set()
                        levels = set()
                        for item in parsed[:500]:
                            if isinstance(item, dict):
                                types.add(item.get('type', 'MISSING'))
                                levels.add(item.get('text_level', 'MISSING'))
                        print(f'Types (first 500): {sorted(types)}')
                        print(f'Levels (first 500): {sorted([str(l) for l in levels])}')
                except json.JSONDecodeError as e:
                    print(f'JSON parse error: {e}')
                    # Try finding the actual structure
                    print(f'Around pos {e.pos}: {joined[max(0,e.pos-100):e.pos+100]}')
            elif isinstance(first, dict):
                print(f'First item keys: {list(first.keys())}')
                for i, item in enumerate(cl[:3]):
                    print(f'  [{i}]: {json.dumps(item, ensure_ascii=False)[:200]}')
