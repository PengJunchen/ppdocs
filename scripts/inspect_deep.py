import json

def inspect_deep(filepath, label):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f'\n{"="*60}')
    print(f'  {label}')
    print(f'{"="*60}')

    for fname, fresult in data.get('results', {}).items():
        cl = fresult.get('content_list', [])
        print(f'\ncontent_list length: {len(cl)}')
        print(f'content_list[0] type: {type(cl[0])}')
        if isinstance(cl[0], str):
            print(f'content_list[0] value (first 200): {cl[0][:200]}')
            print(f'content_list[1] value (first 200): {cl[1][:200]}')
            print(f'content_list[2] value (first 200): {cl[2][:200]}')
            # find first non-empty string
            for i, item in enumerate(cl[:20]):
                print(f'  [{i}] len={len(item)} preview={item[:120]}')

        # Check images
        images = fresult.get('images', {})
        print(f'\nimages type: {type(images)}')
        if isinstance(images, dict):
            img_keys = list(images.keys())[:5]
            print(f'images keys (first 5): {img_keys}')
            for k in img_keys[:2]:
                v = images[k]
                print(f'  image key={k}: type={type(v)}, value={str(v)[:200]}')

        # Check model_output
        mo = fresult.get('model_output', [])
        print(f'\nmodel_output type: {type(mo)}')
        if isinstance(mo, list) and mo:
            print(f'model_output length: {len(mo)}')
            print(f'model_output[0] type: {type(mo[0])}')
            if isinstance(mo[0], list) and mo[0]:
                print(f'model_output[0][0] type: {type(mo[0][0])}')
                if isinstance(mo[0][0], dict):
                    print(f'model_output[0][0] keys: {list(mo[0][0].keys())}')
                    print(f'model_output[0][0] sample: {json.dumps(mo[0][0], ensure_ascii=False)[:500]}')
            elif isinstance(mo[0], dict):
                print(f'model_output[0] keys: {list(mo[0].keys())}')
                # layout_dets
                ld = mo[0].get('layout_dets', [])
                if ld:
                    print(f'  layout_dets[0] keys: {list(ld[0].keys())}')
                    print(f'  layout_dets[0]: {json.dumps(ld[0], ensure_ascii=False)[:500]}')

if __name__ == '__main__':
    base = r'e:\Work\PJC\Github\ppdocs\PDFTest'
    inspect_deep(f'{base}\\DeepSeek_V4_pdf_mineru_3.json', 'MinerU Pipeline - Deep')
    inspect_deep(f'{base}\\DeepSeek_V4_pdf_mineru_3_vlm.json', 'MinerU VLM - Deep')
