"""Rebuild whole-question regions for the current draft, without re-running AI."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/ai'))
from core import *
task_id=read(DATA/'demo-task.json')['id'];folder=DATA/'tasks'/task_id
with httpx.Client(base_url='http://127.0.0.1:1002',timeout=120) as c:
    url='/api/quick-entry/tasks/'+task_id+'/review';draft=c.get(url).json();result=draft['result']
    question_span_regions(result['questions'],result['documents'])
    for q in result['questions']:crop_regions(q,result['documents'],folder)
    save(folder/'result.json',result)
    response=c.put(url,json={'expected_revision':draft['revision'],'result':result});response.raise_for_status()
    print('Rebuilt',sum(len(q['regions']) for q in result['questions']),'whole-question regions; draft remains pending review.')
