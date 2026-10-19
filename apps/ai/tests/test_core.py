import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from PIL import Image

import core
from core import LLM, crop_regions, regions_from_blocks, safe_extract


def test_cross_column_question_retains_separate_regions():
    docs = [{'id':'d','blocks':[
        {'id':'a','page_index':0,'bbox':[.1,.8,.4,.85]},
        {'id':'b','page_index':0,'bbox':[.15,.86,.3,.95]},
        {'id':'c','page_index':0,'bbox':[.55,.05,.9,.12]},
        {'id':'d','page_index':1,'bbox':[.1,.05,.4,.15]},
    ]}]
    regions = regions_from_blocks(['a','b','c','d'],docs)
    assert len(regions)==3
    assert regions[0]['bbox']==[.1,.8,.4,.95]
    assert regions[1]['bbox'][0]>.5
    assert regions[2]['page_index']==1


def test_unknown_content_block_is_not_silently_accepted():
    with pytest.raises(ValueError,match='未知内容块'):
        regions_from_blocks(['invented'],[])


def test_zip_path_traversal_rejected(tmp_path):
    archive=tmp_path/'malicious.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../escaped.txt','bad')
    with pytest.raises(ValueError,match='Unsafe'):
        safe_extract(archive,tmp_path/'out')
    assert not (tmp_path/'escaped.txt').exists()


def test_crop_uses_normalized_physical_page_coordinates(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DATA',tmp_path)
    img=Image.new('RGB',(200,100),'white');img.save(tmp_path/'page.png')
    q={'id':'q','regions':[{'document_id':'d','page_index':0,'bbox':[.5,.1,.9,.6]}]}
    crop_regions(q,[{'id':'d','pages':[{'image_key':'page.png'}]}],tmp_path/'task')
    with Image.open(next((tmp_path/'task/crops').glob('q-0-*.png'))) as crop:assert crop.size==(80,50)
    assert q['regions'][0]['crop_url'].startswith('/api/assets?key=')
    original_url=q['regions'][0]['crop_url']
    q['regions'][0]['bbox']=[.6,.1,.9,.6]
    crop_regions(q,[{'id':'d','pages':[{'image_key':'page.png'}]}],tmp_path/'task')
    assert q['regions'][0]['crop_url']!=original_url
    assert len(list((tmp_path/'task/crops').glob('*.png')))==2


def test_invalid_regions_fail_before_cropping(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DATA',tmp_path)
    q={'id':'q','regions':[{'document_id':'d','page_index':0,'bbox':[.2,.1,1.2,.6]}]}
    with pytest.raises(ValueError,match='坐标'):
        crop_regions(q,[{'id':'d','pages':[{'image_key':'page.png'}]}],tmp_path)


def test_low_channel_failure_falls_back_and_preserves_input(tmp_path,monkeypatch):
    for ch in ['LOW','STABLE']:
        monkeypatch.setenv(f'LLM_{ch}_API_KEY',ch)
        monkeypatch.setenv(f'LLM_{ch}_BASE_URL','https://example.test/v1')
        monkeypatch.setenv(f'LLM_{ch}_MODEL','test-model')
    requests=[]
    def handle(req):
        requests.append(json.loads(req.content))
        if req.headers['Authorization']=='Bearer LOW':return httpx.Response(503)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'}}]})
    original=httpx.Client
    with patch('core.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)):
        llm=LLM(tmp_path)
        assert llm.json('phase','Return JSON',{'source':'same'})=={'ok':True}
    assert requests[0]==requests[1]
    assert [r['status'] for r in llm.calls]==['failed','success']
    assert llm.calls[1]['channel']=='stable'


def test_json_cache_reuses_success_without_repeating_paid_call(tmp_path):
    llm=LLM(tmp_path)
    import hashlib
    payload={'p':1};instruction='instruction'
    digest=hashlib.sha256((instruction+json.dumps(payload,ensure_ascii=False)).encode()).hexdigest()[:16]
    core.save(tmp_path/'llm'/f'test-{digest}.json',{'done':True})
    with patch('core.httpx.Client',side_effect=AssertionError('Network should not run')):
        assert llm.json('test',instruction,payload)=={'done':True}


def test_overlapping_text_and_nested_graphics_share_one_crop():
    docs=[{'id':'d','blocks':[
        {'id':'a','page_index':0,'bbox':[.06,.54,.48,.79]},
        {'id':'b','page_index':0,'bbox':[.08,.69,.27,.83]},
        {'id':'c','page_index':0,'bbox':[.06,.71,.48,.93]},
        {'id':'d','page_index':0,'bbox':[.53,.07,.91,.11]},
    ]}]
    regions=regions_from_blocks(['a','b','c','d'],docs)
    assert len(regions)==2
    assert regions[0]['bbox']==[.06,.54,.48,.93]


def test_sparse_original_diagram_is_preserved_when_ocr_omits_it(tmp_path,monkeypatch):
    from PIL import ImageDraw
    monkeypatch.setattr(core,'DATA',tmp_path)
    img=Image.new('RGB',(1000,1000),'white')
    ImageDraw.Draw(img).rectangle((200,340,280,395),outline='black')
    img.save(tmp_path/'page.png')
    docs=[{'id':'d','pages':[{'image_key':'page.png'}],'blocks':[
        {'id':'a','page_index':0,'bbox':[.1,.2,.45,.3]},
        {'id':'b','page_index':0,'bbox':[.1,.42,.45,.5]},
    ]}]
    q={'id':'q','stem':'题干','block_ids':['a','b'],'regions':[]}
    core.recover_visual_gaps(q,docs,tmp_path/'task')
    assert len(q['regions'])==1
    assert 'original_gap_crop' in str(q['image_layout'])
    assert len(list((tmp_path/'task/recovered').glob('*.png')))==1


def test_double_escaped_latex_is_repaired_without_destroying_matrix_row_breaks():
    q={'stem':r'$\\frac{1}{2}$ and $\begin{matrix}1\\ 2\end{matrix}$','subquestions':[{'stem':r'$\\triangle ABC$'}]}
    core.normalize_question_content(q,[])
    assert q['stem']==r'$\frac{1}{2}$ and $\begin{matrix}1\\ 2\end{matrix}$'
    assert q['subquestions'][0]['stem']==r'$\triangle ABC$'


def test_expanded_answers_must_cover_every_original_number():
    class Fake:
        def json(self,*args):return {'entries':[{'parent_id':'a','number':'1','answer':'A'}]}
    with pytest.raises(ValueError,match='完整覆盖'):
        core.expand_answer_ranges([{'id':'a','number':'1–3'}],Fake())


def test_response_proposal_stops_before_next_question_without_crossing_columns():
    def q(id,box,kind):
        return {'id':id,'attributes':{'question_type':kind},'issues':[],'regions':[{'document_id':'d','page_index':0,'bbox':box,'purpose':'content'}]}
    questions=[q('q1',[.06,.2,.45,.3],'解答题'),q('q2',[.06,.6,.45,.7],'选择题'),q('q3',[.54,.1,.94,.2],'选择题')]
    core.suggest_response_regions(questions,[{'id':'d','role':'question','pages':[{'width_px':1200,'height_px':800}]}])
    response=questions[0]['regions'][1]
    assert response['purpose']=='response'
    assert response['bbox']==[.06,.3,.45,.592]
    assert len(questions[1]['regions'])==1


def _deepseek_env(monkeypatch):
    monkeypatch.setenv('LLM_DEEPSEEK_API_KEY','sk-test')
    monkeypatch.setenv('LLM_DEEPSEEK_BASE_URL','https://example.test')
    monkeypatch.setenv('LLM_DEEPSEEK_MODEL','test-model')


def test_no_input_or_output_token_cap_is_sent(tmp_path,monkeypatch):
    _deepseek_env(monkeypatch)
    captured={}
    def handle(req):
        captured.update(json.loads(req.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}],'usage':{'total_tokens':3}})
    original=httpx.Client
    with patch('core.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)):
        result=LLM(tmp_path,'deepseek').json('phase','Return JSON',{'text':'x'*700000})
    assert result=={'ok':True}
    assert 'max_tokens' not in captured
    assert 'max_output_tokens' not in captured


def test_empty_answer_reports_finish_reason_and_usage(tmp_path,monkeypatch):
    _deepseek_env(monkeypatch)
    def handle(req):
        return httpx.Response(200,json={'choices':[{'message':{'content':''},'finish_reason':'length'}],
                                        'usage':{'prompt_tokens':100,'completion_tokens':16000,'total_tokens':16100}})
    original=httpx.Client
    with patch('core.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)):
        llm=LLM(tmp_path,'deepseek')
        with pytest.raises(core.PipelineError,match='finish_reason=length'):
            llm.json('answers-doc','Return JSON',{'source':'same'})
    assert llm.calls[-1]['finish_reason']=='length'
    assert llm.calls[-1]['usage']['completion_tokens']==16000


def test_flat_subanswer_is_upgraded_and_parent_answer_is_rejected():
    q={'id':'q','stem':'s','answer':None,'image_layout':{},'subquestions':[{'number':'(1)','stem':'x','answer':'A','analysis':'为什么'}]}
    core.normalize_model_question(q)
    assert q['subquestions'][0]['answer']=={'value':'A','analysis':'为什么','scoring_criteria':None,'source':''}
    q['answer']='A'
    with pytest.raises(ValueError,match='答案必须挂到小问'):
        core.normalize_model_question(q)


def test_null_answer_fields_do_not_crash_source_image_scan():
    q={'stem':'s','answer':None,'analysis':None,'options':[],'subquestions':[{'stem':'x','answer':None}]}
    assert core.restore_source_images(q,[]) is None


def test_option_image_without_source_metadata_does_not_crash_layout():
    q={'stem':'','answer':'','analysis':'','options':[{'label':'A','content':'![](/api/assets?key=k.png)'}],
       'image_layout':{'/api/assets?key=k.png':{}},'subquestions':[],'regions':[],'editor_documents':{}}
    core.apply_layout(q,[{'id':'d','asset_metadata':{},'pages':[],'blocks':[]}])
    assert q['image_layout']['/api/assets?key=k.png']=={}
