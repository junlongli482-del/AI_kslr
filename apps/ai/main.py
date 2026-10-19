from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

import httpx
from PIL import Image
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from core import DATA, ROOT, Result, compile_result, crop_regions, normalize, read, safe_extract, save, question_span_regions
from diagnostics import describe_error, redact
from scheduler import TaskScheduler
from media import repair_result, key_of
from channels import channels as configured_channels, timeout as model_timeout

load_dotenv(ROOT / '.env')


@asynccontextmanager
async def lifespan(app):
    recover_pending_tasks()
    yield


app = FastAPI(title='Quick Entry processing service', version='0.1.0', lifespan=lifespan)
lock = threading.Lock()
settings_path = DATA / 'settings' / 'processing.json'
initial_limit = (read(settings_path).get('max_concurrency', 0) if settings_path.exists()
                 else int(os.getenv('QUICK_ENTRY_MAX_CONCURRENCY', '0')))
scheduler = TaskScheduler(max(0, initial_limit))


class RegionRecognizeRequest(BaseModel):
    task_id: str
    question_id: str
    region_index: int = Field(ge=0)
    channel: str = 'deepseek'
    target: str = 'subquestion'
    subquestion_index: int | None = Field(default=None, ge=0)


class ProcessRequest(BaseModel):
    task_id: str = Field(pattern=r'^[a-zA-Z0-9-]+$')
    files: list[dict]
    generate: bool = False
    channel_policy: str = 'deepseek'


def task_folder(task_id):
    if not task_id.replace('-', '').isalnum():
        raise HTTPException(400, 'Invalid task identifier')
    return DATA / 'tasks' / task_id


def process(request: ProcessRequest):
    folder = task_folder(request.task_id)
    folder.mkdir(parents=True, exist_ok=True)
    state_path = folder / 'state.json'
    current_stage = '等待资源'
    current_operation = ''

    def progress(stage, message):
        nonlocal current_stage, current_operation
        current_stage, current_operation = stage, message
        save(state_path, {'status': 'running', 'stage': stage, 'message': message, 'updated_at': time.time()})

    try:
        scheduler.acquire(request.task_id)
        progress('格式准备', '正在准备文件')
        documents = []
        for i, file in enumerate(request.files):
            source = (DATA / file['storage_key']).resolve()
            if not source.is_relative_to(DATA.resolve()) or not source.is_file():
                raise ValueError('Source file unavailable')
            doc_id = file.get('id', f'doc-{i}')
            docfolder = folder / doc_id
            docfolder.mkdir(parents=True, exist_ok=True)
            if source.suffix.lower() in ('.doc', '.docx'):
                progress('格式转换', file['name'])
                converted = docfolder / 'converted'
                converted.mkdir(exist_ok=True)
                target = converted / (source.stem + '.pdf')
                if not target.exists():
                    soffice = os.getenv('SOFFICE_PATH') or shutil.which('soffice') or 'C:/Program Files/LibreOffice/program/soffice.exe'
                    subprocess.run([soffice, '-env:UserInstallation=' + (docfolder / 'lo-profile').resolve().as_uri(),
                                    '--headless', '--convert-to', 'pdf', '--outdir', str(converted), str(source)],
                                   timeout=120, check=True, capture_output=True)
                if not target.exists():
                    raise ValueError('Word转换未产生PDF，请另存为PDF重传')
                source = target
            archive = docfolder / 'mineru.zip'
            if not archive.exists():
                progress('MinerU识别', f'正在识别 {file["name"]}')
                recognize(source, archive, docfolder, file['name'], progress)
            raw = docfolder / 'raw'
            if not (docfolder / 'extracted.ok').exists():
                safe_extract(archive, raw)
                (docfolder / 'extracted.ok').write_text('ok')
            progress('数据整理', f'提取内容、图片与坐标：{file["name"]}')
            documents.append(normalize(source, docfolder, doc_id, file['role'], file['name']))
        if request.channel_policy=='compare':
            from comparison import compare
            progress('模型对比','各渠道同时处理同一份资料，结果与成本分别保存')
            result=compare(request.task_id,documents,folder,request.generate,progress)
        else:
            result = compile_result(request.task_id, documents, folder, request.generate, request.channel_policy, progress)
        save(state_path, {'status': 'ready', 'stage': '待审核', 'message': f'识别完成，共 {len(result["questions"])} 道题', 'updated_at': time.time()})
    except Exception as exc:
        error = describe_error(exc, current_stage,
                               'MinerU' if current_stage == 'MinerU识别' else '处理服务', current_operation)
        error['attempts'] = getattr(exc, 'attempts', [])
        message = f'{current_stage}失败：{redact(exc)}'
        if isinstance(exc, httpx.HTTPError):
            message = f'{current_stage}失败：{error["detail"]}'
        save(state_path, {'status': 'failed', 'stage': '处理失败', 'message': message,
                          'error': error, 'updated_at': time.time()})
    finally:
        scheduler.release(request.task_id)


def recognize(source, archive, folder, name, progress):
    headers = {'Authorization': 'Bearer ' + os.environ['MINERU_API_KEY']}
    base = os.getenv('MINERU_BASE_URL', 'https://mineru.net').rstrip('/')
    manifest = folder / 'mineru-task.json'
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        if manifest.exists():
            state = read(manifest)
        else:
            res = client.post(base + '/api/v4/file-urls/batch', headers=headers,
                              json={'files': [{'name': source.name, 'data_id': folder.name}], 'model_version': 'vlm',
                                    'enable_formula': True, 'enable_table': True})
            res.raise_for_status()
            payload = res.json()
            if payload.get('code') != 0:
                raise ValueError('MinerU: ' + str(payload.get('msg')))
            state = {'batch_id': payload['data']['batch_id'], 'uploaded': False, 'file_url': payload['data']['file_urls'][0]}
            save(manifest, state)
        if not state['uploaded']:
            with source.open('rb') as stream:
                res = client.put(state['file_url'], content=stream)
                res.raise_for_status()
            state['uploaded'] = True
            state.pop('file_url', None)
            save(manifest, state)
        for _ in range(240):
            res = client.get(base + '/api/v4/extract-results/batch/' + state['batch_id'], headers=headers)
            res.raise_for_status()
            payload = res.json()
            if payload.get('code') != 0:
                raise ValueError('MinerU: ' + str(payload.get('msg')))
            item = payload['data']['extract_result'][0]
            if item['state'] == 'done':
                response = client.get(item['full_zip_url'])
                response.raise_for_status()
                archive.write_bytes(response.content)
                return
            if item['state'] == 'failed':
                raise ValueError('MinerU识别失败：' + str(item.get('err_msg', '未知错误')))
            progress('MinerU识别', f'{name}：{item["state"]}')
            time.sleep(5)
    raise TimeoutError('MinerU尚未完成，可重试恢复查询')


@app.post('/region-recognize')
def region_recognize(request: RegionRecognizeRequest):
    folder = task_folder(request.task_id)
    result_path = folder / 'result.json'
    if not result_path.exists():
        raise HTTPException(404, '任务结果不存在')
    result = read(result_path)
    question = next((q for q in result.get('questions', []) if q.get('id') == request.question_id), None)
    if not question:
        raise HTTPException(404, '题目不存在')
    regions = question.get('regions', [])
    if request.region_index >= len(regions):
        raise HTTPException(400, '区域索引无效')
    region = regions[request.region_index]
    doc = next((d for d in result.get('documents', []) if d.get('id') == region.get('document_id')), None)
    if not doc:
        raise HTTPException(400, '区域文档不存在')
    page = doc.get('pages', [])[region.get('page_index', -1)]
    source = (DATA / page['image_key']).resolve()
    if not source.is_file():
        raise HTTPException(404, '原卷页面不存在')
    with Image.open(source) as image:
        w, h = image.size
        box = (int(region['bbox'][0] * w), int(region['bbox'][1] * h), int(region['bbox'][2] * w), int(region['bbox'][3] * h))
        crop = image.crop(box).convert('RGB')
        stream = io.BytesIO()
        crop.save(stream, format='PNG')
        encoded = base64.b64encode(stream.getvalue()).decode()
    providers = {p['id'].lower(): p for p in configured_channels()}
    provider = providers.get(request.channel.lower())
    if not provider:
        raise HTTPException(400, '未配置该模型渠道')
    prompt = '识别这块试卷区域，返回一个JSON对象：{"stem":"","options":[{"label":"A","content":""}],"subquestions":[],"answer":"","analysis":""}。保留原文、公式用LaTeX、表格用Markdown；不要猜测看不清的内容。'
    system = prompt + ' 只输出有效JSON，不要代码围栏。'
    protocol = provider.get('protocol', 'chat')
    if protocol != 'chat':
        raise HTTPException(400, '区域视觉识别当前优先支持 chat 视觉渠道')
    endpoint = provider['base'] + '/chat/completions'
    body = {'model': provider['model'], 'messages': [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': [
            {'type': 'text', 'text': '请识别这张试卷区域。'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}},
        ]},
    ]}
    with httpx.Client(timeout=model_timeout()) as client:
        response = client.post(endpoint, headers={'Authorization': 'Bearer ' + provider['key'], 'Content-Type': 'application/json'}, json=body)
        response.raise_for_status()
        payload = response.json()
    content = payload.get('choices', [{}])[0].get('message', {}).get('content', '')
    content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, '模型返回不是有效JSON') from exc
    return {'question_id': request.question_id, 'region_index': request.region_index,
            'target': request.target, 'subquestion_index': request.subquestion_index,
            'channel': request.channel, 'result': parsed}


@app.get('/health')
def health():
    return {'status': 'ok', 'mineru_configured': bool(os.getenv('MINERU_API_KEY')),
            'llm_configured': bool(os.getenv('LLM_LOW_API_KEY') or os.getenv('LLM_STABLE_API_KEY') or os.getenv('LLM_DEEPSEEK_API_KEY')),
            'read_timeout_seconds':float(os.getenv('LLM_READ_TIMEOUT_SECONDS','1800'))}


@app.post('/process')
def start(request: ProcessRequest):
    with lock:
        if scheduler.contains(request.task_id):
            return {'status': 'running' if request.task_id in scheduler.running else 'queued'}
        folder = task_folder(request.task_id)
        save(folder / 'request.json', request.model_dump())
        scheduler.register(request.task_id)
        try:
            save(folder / 'state.json', {'status': 'queued', 'stage': '等待资源',
                 'message': '正在启动' if scheduler.limit == 0 else '等待配置的并发处理名额', 'updated_at': time.time()})
            threading.Thread(target=process, args=(request,), daemon=True).start()
        except Exception:
            scheduler.release(request.task_id)
            raise
    return {'status': 'queued'}


def recover_pending_tasks():
    for state_path in sorted((DATA / 'tasks').glob('*/state.json')):
        try:
            previous = read(state_path)
            if previous.get('status') not in ('running', 'queued', 'pending'):
                continue
            folder = state_path.parent
            if (folder / 'result.json').exists():
                result = read(folder / 'result.json')
                save(state_path, {'status': 'ready', 'stage': '待审核',
                     'message': f'识别完成，共 {len(result["questions"])} 道题', 'updated_at': time.time()})
            elif (folder / 'request.json').exists():
                start(ProcessRequest.model_validate(read(folder / 'request.json')))
            else:
                save(state_path, {**previous, 'status': 'interrupted', 'message': '缺少恢复请求，请点击恢复处理'})
        except Exception as exc:
            save(state_path, {'status': 'interrupted', 'stage': '恢复失败', 'message': redact(exc), 'updated_at': time.time()})


class ConcurrencySettings(BaseModel):
    max_concurrency: int = Field(ge=0, strict=True)


@app.get('/settings/concurrency')
def concurrency():
    return scheduler.snapshot()


@app.put('/settings/concurrency')
def configure_concurrency(settings: ConcurrencySettings):
    with lock:
        save(settings_path, settings.model_dump())
        return scheduler.configure(settings.max_concurrency)


@app.get('/tasks/{task_id}')
def state(task_id: str):
    p = task_folder(task_id) / 'state.json'
    if not p.exists():
        return {'status': 'pending', 'stage': '等待处理', 'message': ''}
    result = read(p)
    if result['status'] in ('running', 'queued', 'pending') and not scheduler.contains(task_id):
        result.update(status='interrupted', message='服务曾重启，点击重试可恢复已完成阶段')
    return result


@app.get('/tasks/{task_id}/result')
def result(task_id: str):
    p = task_folder(task_id) / 'result.json'
    if not p.exists():
        raise HTTPException(404, '结果尚未生成')
    return read(p)


@app.post('/tasks/{task_id}/validate')
def validate(task_id: str, payload: dict):
    try:
        result = Result.model_validate(payload).model_dump()
    except ValidationError:
        return {'issues':[{'severity':'error','message':'题目结构不符合协议，请检查必填内容与字段类型'}],'valid':False,'result':payload}
    if result['task_id'] == task_id:
        repair_result(result, DATA, task_id)
        rebuild=payload.get('rebuild_region_question_ids',[])
        if rebuild:
            question_span_regions(result['questions'],result['documents'],question_ids=rebuild)
    issues = []
    if result['task_id'] != task_id:
        issues.append({'severity':'error','message':'结果不属于当前任务'})
    ids = set()
    papers = {p['id'] for p in result['papers']}
    if len(papers) != len(result['papers']):
        issues.append({'severity':'error','message':'试卷ID重复'})
    documents = {d['id']:d for d in result['documents']}
    blocks = {b['id'] for d in result['documents'] for b in d.get('blocks',[])}
    entries = {e['id'] for e in result['answer_entries']}
    answer_uses = set()
    seen_subquestion_ids = set()
    seen_numbers = set()
    for q in result['questions']:
        def issue(message,severity='error'):
            issues.append({'question_id':q['id'],'severity':severity,'message':message})
        if q['id'] in ids:
            issues.append({'question_id': q['id'], 'severity': 'error', 'message': '题目ID重复'})
        ids.add(q['id'])
        number=(q['paper_id'],q['number'])
        if number in seen_numbers: issue('同一试卷题号重复，请核对节选或重号','warning')
        seen_numbers.add(number)
        if q['paper_id'] not in papers:
            issues.append({'question_id': q['id'], 'severity': 'error', 'message': '题目所属试卷不存在'})
        if not q['stem'].strip() and not q['editor_documents'].get('stem'):
            issues.append({'question_id': q['id'], 'severity': 'error', 'message': '题干为空'})
        if any(b not in blocks for b in q['block_ids']): issue('引用的原文内容块不存在')
        if q['answer_entry_id']:
            if q['answer_entry_id'] not in entries: issue('关联答案条目不存在')
            if q['answer_entry_id'] in answer_uses: issue('同一答案被重复关联至多道题目')
            answer_uses.add(q['answer_entry_id'])
        if not q['regions']: issue('缺少原卷区域，原卷模板仍待补框','warning')
        score=q['attributes'].get('score')
        if score is not None and (not isinstance(score,(int,float)) or isinstance(score,bool) or score<0): issue('分值必须为非负数')
        for r in q['regions']:
            d=documents.get(r['document_id'])
            if not d or not 0<=r['page_index']<len(d['pages']): continue
            page_path=(DATA/d['pages'][r['page_index']]['image_key']).resolve()
            if not page_path.is_relative_to(DATA.resolve()) or not page_path.is_file(): issue('原卷页面资产不存在')
        bad={}
        for field in ('stem','options','subquestions','answer','analysis','editor_documents'):
            content=json.dumps(q[field],ensure_ascii=False)
            for url in re.findall(r'/api/assets\?key=[^\s)"<>]+',content):
                key=key_of(url);asset=(DATA/key).resolve()
                if not key or not asset.is_relative_to(DATA.resolve()) or not asset.is_file():
                    bad.setdefault(key,{'url':url,'fields':[]})['fields'].append(field)
        for key,ref in bad.items():
            fields=list(dict.fromkeys(ref['fields']))
            issues.append({'question_id':q['id'],'number':q['number'],'paper_id':q['paper_id'],
                           'severity':'error','code':'missing_asset','fields':fields,'asset_url':ref['url'],
                           'message':f'第{q["number"]}题引用的图片资产不存在：{Path(key).name}',
                           'hint':'请定位到对应内容删除失效图片或重新粘贴；系统无法唯一匹配到本任务现存图片。'})
        try:
            crop_regions(q, result['documents'], task_folder(task_id))
        except (ValueError,KeyError,IndexError,OSError) as exc:
            issue('题框或页面资产无效，请修正坐标和页面引用')
        for index, sub in enumerate(q.get('subquestions') or []):
            sub_id=sub.get('subquestion_id') or f"{q['id']}-sub-{index+1}"
            sub['subquestion_id']=sub_id
            raw_answer=sub.get('answer')
            if not isinstance(raw_answer,dict):
                sub['answer']={'value':raw_answer or '','analysis':sub.pop('analysis','') or '','scoring_criteria':sub.pop('scoring_criteria',None),'source':sub.pop('answer_source','') or ''}
            if sub_id in seen_subquestion_ids: issue('小问ID重复')
            seen_subquestion_ids.add(sub_id)
            if sub.get('answer_entry_id'):
                if sub['answer_entry_id'] not in entries: issue(f'小问{sub.get("number", index+1)}关联答案条目不存在')
                if sub['answer_entry_id'] in answer_uses: issue('同一答案被重复关联至多个题目或小问')
                answer_uses.add(sub['answer_entry_id'])
            if not sub.get('stem','').strip(): issue(f'小问{sub.get("number", index+1)}题干为空','warning')
            if not str((sub.get('answer') or {}).get('value','')).strip():
                issues.append({'question_id':q['id'],'severity':'warning','message':f'小问{sub.get("number", index+1)}缺少答案，可作为待完善资源保存'})
        if q.get('subquestions') and str(q.get('answer') or '').strip():
            issue('答案必须挂到小问；有子问题的父题 answer 必须为空')
        if not q['answer'] and not q.get('subquestions'):
            issues.append({'question_id': q['id'], 'severity': 'warning', 'message': '缺少答案，可作为待完善资源保存'})
    if not result['questions']:
        issues.append({'severity': 'error', 'message': '没有可入库题目'})
    return {'issues': issues, 'valid': not any(x['severity'] == 'error' for x in issues), 'result': result}


@app.get('/schema')
def schema():
    return Result.model_json_schema()
