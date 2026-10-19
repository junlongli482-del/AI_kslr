"""Create a real API task; reuse the already paid, original MinerU archives."""
import json
import shutil
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
state = json.loads((ROOT / 'data/sample-recognition/manifest.json').read_text(encoding='utf-8'))
with httpx.Client(base_url='http://127.0.0.1:8090', timeout=120) as c:
    response = c.post('/api/quick-entry/tasks', json={'title': '金版数学九上 · 期中与期末', 'mode': 'textbook', 'channel_policy': 'low_first'})
    response.raise_for_status()
    task = response.json()
    for i, source in enumerate(state['sources']):
        p = Path(source)
        with p.open('rb') as f:
            response = c.post(f'/api/quick-entry/tasks/{task["id"]}/files', data={'role': 'answer' if i == 2 else 'question'}, files={'files': (p.name, f, 'application/pdf')})
        response.raise_for_status()
        fid = response.json()[-1]['id']
        dest = ROOT / 'data/tasks' / task['id'] / fid
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f'data/sample-recognition/sample-{i}.zip', dest / 'mineru.zip')
    (ROOT / 'data/demo-task.json').write_text(json.dumps({'id': task['id']}, indent=2))
    response = c.post(f'/api/quick-entry/tasks/{task["id"]}/start')
    response.raise_for_status()
    print(json.dumps({'task_id': task['id'], 'status': response.json()['status']}))
