import json
import threading
import time

import httpx
import pytest

import core
import main
from diagnostics import describe_error
from scheduler import TaskScheduler


def test_increasing_limit_releases_waiters_without_waiting_for_a_completion():
    scheduler = TaskScheduler(1)
    for task in ['a', 'b', 'c', 'd']: scheduler.register(task)
    scheduler.acquire('a')
    started = []
    def run(task):
        scheduler.acquire(task)
        started.append(task)
    threads = [threading.Thread(target=run,args=(task,),daemon=True) for task in ['b','c','d']]
    for thread in threads: thread.start()
    assert scheduler.snapshot() == {'max_concurrency':1,'unlimited':False,'running':1,'queued':3}
    scheduler.configure(0)
    for thread in threads: thread.join(2)
    assert set(started) == {'b','c','d'}
    assert scheduler.snapshot()['running'] == 4
    assert scheduler.snapshot()['queued'] == 0


def test_slot_release_starts_the_next_waiter_and_duplicate_is_rejected():
    scheduler = TaskScheduler(1)
    assert scheduler.register('a')
    assert not scheduler.register('a')
    scheduler.acquire('a')
    scheduler.register('b')
    entered=threading.Event()
    thread=threading.Thread(target=lambda:(scheduler.acquire('b'),entered.set()),daemon=True)
    thread.start()
    assert not entered.wait(.05)
    scheduler.release('a')
    assert entered.wait(2)
    assert scheduler.snapshot()['running']==1
    scheduler.release('b')
    assert not scheduler.contains('b')


def test_decreasing_limit_does_not_interrupt_running_work():
    scheduler=TaskScheduler(0)
    for task in ['a','b','c']: scheduler.register(task);scheduler.acquire(task)
    scheduler.configure(1)
    assert scheduler.snapshot()['running']==3
    scheduler.register('d')
    entered=threading.Event()
    thread=threading.Thread(target=lambda:(scheduler.acquire('d'),entered.set()),daemon=True)
    thread.start()
    scheduler.release('a');scheduler.release('b')
    assert not entered.wait(.05)
    scheduler.release('c')
    assert entered.wait(2)


def test_timeout_and_provider_error_include_detail_and_hide_credentials(monkeypatch):
    monkeypatch.setenv('LLM_LOW_API_KEY','sk-test-secret')
    request=httpx.Request('POST','https://provider.test/chat')
    response=httpx.Response(429,request=request,json={'error':{'message':'limit exceeded Bearer sk-test-secret'}})
    exc=httpx.HTTPStatusError('failed',request=request,response=response)
    result=describe_error(exc,'AI编排','LLM','structure-d1')
    assert result['status_code']==429
    assert 'limit exceeded' in result['detail']
    assert 'sk-test-secret' not in json.dumps(result)
    assert '降低并发' in result['hint']
    timeout=describe_error(httpx.ReadTimeout(''),service='LLM')
    assert '未在设定时间' in timeout['detail']


def test_alternative_latex_delimiters_keep_commands_and_matrix_rows():
    q={'stem':r'题目 \(\frac34\)', 'answer':r'\[\begin{matrix}1\\2\end{matrix}\]', 'analysis':'', 'options':[], 'subquestions':[]}
    core.normalize_question_content(q,[])
    assert q['stem']==r'题目 $\frac34$'
    assert q['answer']==r'$$\begin{matrix}1\\2\end{matrix}$$'


def test_owned_images_restored_once_and_options_not_duplicated():
    url='/api/assets?key=figure.png'
    docs=[{'id':'d','blocks':[{'id':'b','text':f'![]({url})','page_index':0,'bbox':[.4,.3,.48,.4]}]}]
    q={'stem':'如图','options':[],'block_ids':['b']}
    core.restore_source_images(q,docs)
    core.restore_source_images(q,docs)
    assert q['stem'].count(url)==1
    assert q['image_layout'][url]['bbox']==[.4,.3,.48,.4]
    q2={'stem':'选择','options':[{'content':f'![]({url})'}],'block_ids':['b']}
    core.restore_source_images(q2,docs)
    assert url not in q2['stem']


def test_restart_recovers_queued_and_running_but_does_not_retry_failed(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DATA',tmp_path)
    captured=[]
    monkeypatch.setattr(main,'start',lambda request:captured.append(request.task_id))
    for task,status in [('a','queued'),('b','running'),('c','failed')]:
        core.save(tmp_path/'tasks'/task/'state.json',{'status':status})
        core.save(tmp_path/'tasks'/task/'request.json',{'task_id':task,'files':[]})
    main.recover_pending_tasks()
    assert captured==['a','b']


def test_restart_uses_completed_result_without_new_api_calls(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DATA',tmp_path)
    monkeypatch.setattr(main,'start',lambda request:pytest.fail('must not rerun completed result'))
    folder=tmp_path/'tasks'/'a'
    core.save(folder/'state.json',{'status':'running'})
    core.save(folder/'result.json',{'questions':[{'id':'q'}]})
    main.recover_pending_tasks()
    assert core.read(folder/'state.json')['status']=='ready'


def test_settings_api_validates_and_persists_dynamic_limit(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main,'DATA',tmp_path)
    monkeypatch.setattr(main,'settings_path',tmp_path/'settings.json')
    monkeypatch.setattr(main,'scheduler',TaskScheduler(0))
    with TestClient(main.app) as client:
        assert client.get('/settings/concurrency').json()['unlimited']
        assert client.put('/settings/concurrency',json={'max_concurrency':7}).json()['max_concurrency']==7
        assert core.read(tmp_path/'settings.json')['max_concurrency']==7
        assert client.put('/settings/concurrency',json={'max_concurrency':0}).json()['unlimited']
        for invalid in [-1,1.5,True,'3']:
            assert client.put('/settings/concurrency',json={'max_concurrency':invalid}).status_code==422


def test_metadata_extension_reuses_old_completed_structure_checkpoint(tmp_path):
    import hashlib
    old={'name':'paper.pdf','markdown':'source','blocks':[]}
    digest=hashlib.sha256(('instruction'+json.dumps(old,ensure_ascii=False)).encode()).hexdigest()[:16]
    core.save(tmp_path/'llm'/f'structure-d1-{digest}.json',{'questions':[]})
    llm=core.LLM(tmp_path)
    assert llm.json('structure-d1','instruction',{**old,'images':[]})=={'questions':[]}
    assert llm.calls[-1]['status']=='cache_hit'


def test_failed_processing_persists_stage_detail_and_releases_admission(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DATA',tmp_path)
    scheduler=TaskScheduler(1)
    monkeypatch.setattr(main,'scheduler',scheduler)
    scheduler.register('failure')
    main.process(main.ProcessRequest(task_id='failure',files=[{'storage_key':'missing.pdf'}]))
    result=core.read(tmp_path/'tasks/failure/state.json')
    assert result['status']=='failed'
    assert result['error']['stage']=='格式准备'
    assert 'Source file unavailable' in result['error']['detail']
    assert scheduler.snapshot()['running']==0
    assert not scheduler.contains('failure')
