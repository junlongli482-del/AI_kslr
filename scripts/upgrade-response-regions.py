"""Add inferred response areas to the existing draft, without re-running AI."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/ai'))
from core import *
task_id=read(DATA/'demo-task.json')['id'];folder=DATA/'tasks'/task_id
with httpx.Client(base_url='http://127.0.0.1:8090',timeout=120) as c:
    url='/api/quick-entry/tasks/'+task_id+'/review';draft=c.get(url).json();result=draft['result']
    for q in result['questions']:
        q['regions']=[r for r in q['regions'] if r.get('purpose')!='response']
    suggest_response_regions(result['questions'],result['documents'])
    for q in result['questions']:crop_regions(q,result['documents'],folder)
    save(folder/'result.json',result)
    response=c.put(url,json={'expected_revision':draft['revision'],'result':result});response.raise_for_status()
    print('Added',sum(r['purpose']=='response' for q in result['questions'] for r in q['regions']),'response proposals; draft remains pending review.')
