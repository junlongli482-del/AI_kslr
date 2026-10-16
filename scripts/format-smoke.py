"""Live MinerU + LLM checks with clearly labelled synthetic documents."""
import json,time,sys
from pathlib import Path
import httpx
from PIL import Image
import pypdfium2 as pdfium
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'data/format-smoke.json'
records=json.loads(out.read_text(encoding='utf8')) if out.exists() else []
pdf=pdfium.PdfDocument(ROOT/'data/fixtures/inline-answers.pdf')
page=pdf[0];bitmap=page.render(scale=1.7);bitmap.to_pil().save(ROOT/'data/fixtures/inline-answers.png');bitmap.close();page.close();pdf.close()
with httpx.Client(base_url='http://127.0.0.1:8090',timeout=120) as client:
    for filename,mode in [('inline-answers.docx','questions'),('inline-answers.png','paper')]:
        record=next((r for r in records if r['filename']==filename),None)
        if record is None:
            response=client.post('/api/quick-entry/tasks',json={'title':'[衍生验证] '+filename,'mode':mode,'channel_policy':'stable_first'})
            response.raise_for_status();task=response.json()
            path=ROOT/'data/fixtures'/filename
            with path.open('rb') as stream:
                response=client.post('/api/quick-entry/tasks/'+task['id']+'/files',data={'role':'mixed'},files={'files':(filename,stream)})
                response.raise_for_status()
            record={'filename':filename,'mode':mode,'id':task['id']};records.append(record);out.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
            response=client.post('/api/quick-entry/tasks/'+task['id']+'/start');response.raise_for_status()
        for attempt in range(210):
            task=client.get('/api/quick-entry/tasks/'+record['id']).json()
            if task['status'] in ('ready','committed','failed','interrupted'):break
            time.sleep(4)
        record['status']=task['status']
        if task['status'] not in ('ready','committed'):
            record['message']=task.get('message');out.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8');raise RuntimeError(record)
        draft=client.get('/api/quick-entry/tasks/'+record['id']+'/review').json()
        qs=draft['result']['questions'];record.update(questions=len(qs),answers=sum(bool(q['answer']) for q in qs))
        out.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
        assert len(qs)==2 and all(q['answer'] for q in qs),record
        print(json.dumps(record,ensure_ascii=False),flush=True)
