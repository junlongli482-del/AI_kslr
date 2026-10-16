"""Run the supplied, authorized source PDFs through official MinerU; resumable."""
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
SOURCES = [
    Path('D:/RuanJan/xwechat_files/wxid_71tw5b36mncp22_e7c4/msg/file/2026-10/26秋金版 数学 九年级上册（人教版）试卷_1-4.pdf'),
    Path('D:/RuanJan/xwechat_files/wxid_71tw5b36mncp22_e7c4/msg/file/2026-10/26秋金版 数学 九年级上册（人教版）试卷_5-8.pdf'),
    Path('E:/金版学案教辅/初中（21本）/6_26秋金版 数学 九年级上册（人教版）/单元卷录入和上传/提取自26秋金版 数学 九年级上册（人教版）答案(1).pdf'),
]


def main():
    dest = ROOT / 'data/sample-recognition'
    dest.mkdir(parents=True, exist_ok=True)
    manifest = dest / 'manifest.json'
    headers = {'Authorization': 'Bearer ' + os.environ['MINERU_API_KEY']}
    base = os.environ.get('MINERU_BASE_URL', 'https://mineru.net')
    with httpx.Client(timeout=90, follow_redirects=True) as client:
        if manifest.exists():
            state = json.loads(manifest.read_text(encoding='utf-8'))
        else:
            res = client.post(base + '/api/v4/file-urls/batch', headers=headers, json={
                'files': [{'name': p.name, 'data_id': f'sample-{i}'} for i, p in enumerate(SOURCES)],
                'model_version': 'vlm', 'enable_formula': True, 'enable_table': True,
            })
            res.raise_for_status()
            payload = res.json()
            if payload.get('code') != 0:
                raise RuntimeError(str(payload.get('msg')))
            state = {'batch_id': payload['data']['batch_id'], 'sources': [str(p) for p in SOURCES], 'uploaded': False}
            manifest.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
            for p, url in zip(SOURCES, payload['data']['file_urls'], strict=True):
                with p.open('rb') as stream:
                    upload = client.put(url, content=stream)
                upload.raise_for_status()
            state['uploaded'] = True
            manifest.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        if not state['uploaded']:
            raise RuntimeError('Previous upload interrupted; inspect manifest before resubmitting.')
        for _ in range(180):
            res = client.get(base + '/api/v4/extract-results/batch/' + state['batch_id'], headers=headers)
            res.raise_for_status()
            payload = res.json()
            if payload.get('code') != 0:
                raise RuntimeError(str(payload.get('msg')))
            results = payload['data']['extract_result']
            print(json.dumps({'states': [r['state'] for r in results]}, ensure_ascii=True), flush=True)
            for i, result in enumerate(results):
                target = dest / f'sample-{i}.zip'
                if result['state'] == 'done' and not target.exists():
                    z = client.get(result['full_zip_url'])
                    z.raise_for_status()
                    target.write_bytes(z.content)
            if all(r['state'] in ('done', 'failed') for r in results):
                state['results'] = [{k: v for k, v in r.items() if k != 'full_zip_url'} for r in results]
                manifest.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
                print('Recognition finished.', flush=True)
                return
            time.sleep(5)
        raise TimeoutError('Recognition not complete; rerun to resume polling.')


if __name__ == '__main__':
    main()
