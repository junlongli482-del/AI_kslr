"""Reprocess cached source geometry and answers; never repeats paid OCR/structure."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/ai'))
from dotenv import load_dotenv
from core import *
load_dotenv(ROOT / '.env')
folder = DATA / 'tasks' / read(DATA/'demo-task.json')['id']
result = read(folder/'result.json')
backup = folder/'result-before-repair.json'
if not backup.exists():
    save(backup, result)
original = read(backup)
result = original
request = read(folder/'request.json')
docs = []
for file in request['files']:
    cache = folder/file['id']/'normalized.json'
    if cache.exists(): cache.unlink()
    docs.append(normalize(DATA/file['storage_key'], folder/file['id'], file['id'], file['role'], file['name']))
result['documents'] = docs
llm = LLM(folder)
entries = expand_answer_ranges(original['answer_entries'], llm)
for e in entries:
    e.pop('matched_question_id',None)
    e.pop('match_reason',None)
match = llm.json('match', MATCH_PROMPT, {'papers':result['papers'], 'questions':[{k:q.get(k) for k in ('id','paper_id','number','stem','options','subquestions')} for q in result['questions']], 'entries':entries}, 12000)
questions = {q['id']:q for q in result['questions']}
byentry = {e['id']:e for e in entries}
used = set()
for q in questions.values():
    normalize_question_content(q, docs)
    q.update(answer='',analysis='',answer_source='missing',analysis_source='missing',answer_entry_id=None)
    q['issues'] = [i for i in q.get('issues',[]) if i not in ('缺少答案','原答案含略／图略，详细内容待完善')]
for m in match['matches']:
    q,e=questions.get(m['question_id']),byentry.get(m['answer_entry_id'])
    if not q or not e or e['id'] in used or q['answer_entry_id']: continue
    q.update(answer=e.get('answer',''),analysis=e.get('analysis',''),answer_source='answer_file',analysis_source='answer_file' if e.get('analysis') else 'missing',answer_entry_id=e['id'])
    e.update(matched_question_id=q['id'],match_reason=m.get('reason',''))
    if e.get('incomplete'): q['issues'].append('原答案含略／图略，详细内容待完善')
    used.add(e['id'])
metadata = {url:m for d in docs for url,m in d['asset_metadata'].items()}
for q in questions.values():
    for field in ('stem','answer','analysis'): q[field]=q[field].replace(r'\n\n','\n\n')
    q['regions'] = regions_from_blocks(q['block_ids'], docs)
    urls = re.findall(r'!\[[^\]]*\]\((/api/assets\?key=[^)]+)\)',q['stem']+'\n'+'\n'.join(o.get('content','') for o in q['options']))
    q['image_layout']={u:metadata[u] for u in urls if u in metadata}
    if len(q['options'])>=2 and all('![' in o.get('content','') for o in q['options']): q['options_layout']={'columns':min(4,len(q['options'])),'source':'original_image_geometry'}
    recover_visual_gaps(q,docs,folder)
    crop_regions(q,docs,folder)
    if not q['answer']: q['issues'].append('缺少答案')
result['answer_entries']=entries
result['unmatched_answer_entry_ids']=[e['id'] for e in entries if e['id'] not in used]
result['processing_metadata']['calls']=llm.calls
result=Result.model_validate(result).model_dump()
save(folder/'result.json', result)
with httpx.Client(base_url='http://127.0.0.1:8090',timeout=60) as client:
    endpoint='/api/quick-entry/tasks/'+result['task_id']+'/review'
    draft=client.get(endpoint).json()
    response=client.put(endpoint,json={'expected_revision':draft['revision'],'result':result})
    response.raise_for_status()
print(json.dumps({'questions':len(questions),'matched':len(used),'unused_entries':len(result['unmatched_answer_entry_ids']),'recovered_visuals':sum('recovered_visual'==r['purpose'] for q in questions.values() for r in q['regions'])}))
