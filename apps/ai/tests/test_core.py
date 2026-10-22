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


def test_question_span_uses_next_start_and_column_width():
    docs=[{'id':'d','role':'question','pages':[{'width_px':1200,'height_px':800}],
           'blocks':[{'id':'a','page_index':0,'bbox':[.06,.2,.45,.3]},
                     {'id':'b','page_index':0,'bbox':[.06,.6,.45,.7]}]}]
    questions=[{'id':'q1','block_ids':['a'],'regions':[],'issues':[]},
               {'id':'q2','block_ids':['b'],'regions':[],'issues':[]}]
    core.question_span_regions(questions,docs)
    assert questions[0]['regions'][0]['bbox']==[.04,.196,.96,.604]
    assert questions[1]['regions'][0]['bbox'][1]==.596


def test_question_span_splits_across_pages():
    docs=[{'id':'d','role':'question','pages':[{'width_px':800,'height_px':1200},{'width_px':800,'height_px':1200}],
           'blocks':[{'id':'a','page_index':0,'bbox':[.1,.7,.9,.8]},
                     {'id':'b','page_index':1,'bbox':[.1,.05,.9,.2]},
                     {'id':'c','page_index':1,'bbox':[.1,.5,.9,.6]}]}]
    questions=[{'id':'q1','block_ids':['a','b'],'regions':[],'issues':[]},
               {'id':'q2','block_ids':['c'],'regions':[],'issues':[]}]
    core.question_span_regions(questions,docs)
    assert [(r['page_index'],round(r['bbox'][1],3),round(r['bbox'][3],3)) for r in questions[0]['regions']]==[(0,.696,.96),(1,.046,.504)]


def test_three_column_page_uses_per_column_frames():
    docs=[{'id':'d','role':'question','pages':[{'width_px':1400,'height_px':1000}],'columns':[3],
           'blocks':[{'id':'a','page_index':0,'bbox':[.04,.10,.30,.20]},
                     {'id':'b','page_index':0,'bbox':[.36,.10,.62,.20]},
                     {'id':'c','page_index':0,'bbox':[.68,.10,.95,.20]},
                     {'id':'d2','page_index':0,'bbox':[.04,.50,.30,.60]}]}]
    questions=[{'id':'q1','block_ids':['a'],'regions':[],'issues':[]},
               {'id':'q2','block_ids':['b'],'regions':[],'issues':[]},
               {'id':'q3','block_ids':['c'],'regions':[],'issues':[]},
               {'id':'q4','block_ids':['d2'],'regions':[],'issues':[]}]
    core.question_span_regions(questions,docs)
    assert [round(q['regions'][0]['bbox'][0],2) for q in questions]==[.04,.33,.65,.04]
    assert round(questions[0]['regions'][0]['bbox'][2],2)==.33
    assert round(questions[1]['regions'][0]['bbox'][2],2)==.65
    assert round(questions[2]['regions'][0]['bbox'][2],2)==.96
    assert questions[0]['regions'][0]['bbox'][3] <= .51


def test_section_heading_is_not_framed_into_previous_question():
    docs=[{'id':'d','role':'question','pages':[{'width_px':800,'height_px':1200}],
           'blocks':[{'id':'a','page_index':0,'bbox':[.06,.10,.45,.20]},
                     {'id':'h','page_index':0,'bbox':[.06,.24,.45,.27],'text':'二、多项选择题（本题共3小题）'},
                     {'id':'b','page_index':0,'bbox':[.06,.32,.45,.45]}]}]
    questions=[{'id':'q1','block_ids':['a'],'regions':[],'issues':[]},
               {'id':'q2','block_ids':['b'],'regions':[],'issues':[]}]
    core.question_span_regions(questions,docs)
    assert round(questions[0]['regions'][0]['bbox'][3],3)==.238


def test_subjective_question_frame_uses_whole_column():
    docs=[{'id':'d','role':'question','pages':[{'width_px':1200,'height_px':800}],'columns':[1],
           'blocks':[{'id':'a','page_index':0,'bbox':[.06,.10,.30,.20]}]}]
    questions=[{'id':'q1','block_ids':['a'],'regions':[],'issues':[],'attributes':{'question_type':'解答题'}}]
    core.question_span_regions(questions,docs)
    assert [round(v,2) for v in questions[0]['regions'][0]['bbox'][:3]]==[.04,.10,.96]


def test_question_issues_accept_model_objects():
    question=core.Question.model_validate({'id':'q1','paper_id':'p','number':'1','stem':'',
                                           'issues':[{'type':'subquestion_block_missing','message':'block_ids为空'},'需人工核对：图不清',None]})
    assert question.issues==['subquestion_block_missing: block_ids为空','需人工核对：图不清']


def test_row_break_before_letter_survives_escape_repair():
    stem=r'$a_1=3,a_{n+1}=\begin{cases}a_n+1,&n\text{为奇数},\\a_n+2,&n\text{为偶数}.\end{cases}$'
    question={'stem':stem,'answer':'','analysis':'','options':[],'subquestions':[]}
    core.normalize_question_content(question,[])
    assert r'\\a_n+2' in question['stem']
    doubled={'stem':r'$x=\\frac{1}{2}$','answer':'','analysis':'','options':[],'subquestions':[]}
    core.normalize_question_content(doubled,[])
    assert r'\frac{1}{2}' in doubled['stem']


def test_page_vision_image_names_and_resizes(tmp_path,monkeypatch):
    from PIL import Image
    monkeypatch.setattr(core,'DATA',tmp_path)
    (tmp_path/'pages').mkdir()
    Image.new('RGB',(2000,1000),'white').save(tmp_path/'pages'/'p0.png')
    doc={'id':'doc1','name':'历史 试卷.pdf','pages':[{'image_key':'pages/p0.png'}]}
    images=core.document_vision_images(doc,tmp_path/'task')
    assert len(images)==1
    assert images[0]['name']=='历史 试卷-第01页.png'
    assert images[0]['data_url'].startswith('data:image/jpeg;base64,')
    import base64,io
    raw=base64.b64decode(images[0]['data_url'].split(',',1)[1])
    assert max(Image.open(io.BytesIO(raw)).size)==1400


def test_gutter_detection_reads_two_columns():
    doc={'id':'d','pages':[{}],'blocks':[
        {'id':'h','page_index':0,'bbox':[.04,.03,.96,.06]},
        {'id':'a','page_index':0,'bbox':[.05,.10,.45,.30]},
        {'id':'b','page_index':0,'bbox':[.54,.10,.95,.30]}]}
    assert core.detected_columns(doc,0)==2


def test_attach_columns_applies_paper_count_to_every_page():
    doc={'id':'d','pages':[{'width_px':1400,'height_px':1000},{'width_px':1400,'height_px':1000}],
         'blocks':[{'id':'a','page_index':0,'bbox':[.05,.1,.45,.3]},{'id':'b','page_index':1,'bbox':[.05,.1,.45,.3]}]}
    paper={'id':'p','source':{'columns':3},'source_document_ids':['d']}
    core.attach_page_columns([doc],[paper])
    assert doc['columns']==[3,3]
    assert paper['issues'] and '请核对' in paper['issues'][0]


def test_restore_blanks_from_source_blocks():
    blocks={'b1':{'id':'b1','text':'only one \\_42\\_ stands out'}}
    question={'stem':'only one 42 stands out','block_ids':['b1'],'issues':[]}
    assert core.restore_blanks(question,blocks)==1
    assert '{{blank:42}}' in question['stem']


def test_restore_blanks_ignores_years_and_math():
    blocks={'b1':{'id':'b1','text':'\\_24\\_ and \\_25\\_'}}
    question={'stem':'In 2024 we use $x=24$ then 25 here','block_ids':['b1'],'issues':[]}
    core.restore_blanks(question,blocks)
    assert '2024' in question['stem']
    assert '$x=24$' in question['stem']
    assert '{{blank:25}}' in question['stem']


def test_excluded_block_is_dropped_from_frame():
    docs=[{'id':'d','role':'question','pages':[{'width_px':800,'height_px':1200}],
           'blocks':[{'id':'a','page_index':0,'bbox':[.06,.10,.45,.20]},
                     {'id':'h','page_index':0,'bbox':[.06,.20,.45,.44],'text':'第三部分 语言运用（共两节）'},
                     {'id':'b','page_index':0,'bbox':[.06,.50,.45,.60]}]}]
    questions=[{'id':'q1','block_ids':['a'],'regions':[],'issues':[]},
               {'id':'q2','block_ids':['h','b'],'regions':[],'issues':[]}]
    core.question_span_regions(questions,docs,excluded=['h'])
    assert questions[1]['regions'][0]['bbox'][1] >= .49
    assert questions[0]['regions'][0]['bbox'][3] <= .51


def test_allocate_sub_scores_keeps_integer_total():
    subs=[{'weight_pct':33.3},{'weight_pct':33.3},{'weight_pct':33.4}]
    core.allocate_sub_scores(10,subs)
    assert [s['score'] for s in subs]==[3,3,4]
    assert sum(s['score'] for s in subs)==10


def test_scoring_points_are_normalized_to_100():
    doc={'type':'doc','content':[]}
    scoring=core.normalize_scoring({'points':[{'pct':20,'criterion':'公式正确','editor_document':doc},{'pct':30,'criterion':'结果正确'}]})
    assert round(sum(point['pct'] for point in scoring['points']))==100
    assert scoring['points'][0]['editor_document']==doc


def test_apply_rubrics_merges_points_and_allocates_integer_scores():
    class Fake:
        def json(self,*args):return {'items':[{'question_id':'q1','grading_method':'manual','difficulty':4,'difficulty_reason':'多步推理','subquestions':[
            {'subquestion_id':'s1','weight_pct':40,'scoring':{'type':'step','points':[{'pct':100,'criterion':'正确'}]}},
            {'subquestion_id':'s2','weight_pct':60,'scoring':{'type':'step','points':[{'pct':100,'criterion':'正确'}]}}]}]}
    q={'id':'q1','paper_id':'p1','number':'15','stem':'','options':[],'answer':'','analysis':'','attributes':{'score':10},
       'subquestions':[{'subquestion_id':'s1','number':'(1)','stem':'','options':[],'answer':{'value':'','analysis':''}},
                       {'subquestion_id':'s2','number':'(2)','stem':'','options':[],'answer':{'value':'','analysis':''}}],
       'grading_method':None,'issues':[]}
    core.apply_rubrics([q],[{'id':'p1','title':'t'}],Fake())
    assert [sub['score'] for sub in q['subquestions']]==[4,6]
    assert q['attributes']['difficulty']==4
    assert q['subquestions'][0]['scoring']['points'][0]['pct']==100


def test_fill_rubric_marks_objective_target_as_auto():
    class Fake:
        def json(self,*args):return {'items':[{'question_id':'q1','grading_method':'auto','subquestions':[{'subquestion_id':'s2','weight_pct':100}]}]}
    q={'id':'q1','number':'11','stem':'','options':[],'answer':'','analysis':'','attributes':{'score':4},
       'subquestions':[{'subquestion_id':'s1','number':'(1)','stem':'','options':[],'answer':{'value':'','analysis':''},'scoring':{'method':'auto'}},
                       {'subquestion_id':'s2','number':'(2)','stem':'','options':[],'answer':{'value':'变小','analysis':''}}]}
    assert core.fill_question_rubric(q,Fake(),'s2')==1
    assert q['subquestions'][1]['scoring']=={'method':'auto'}
    assert core.missing_rubric_targets(q,'s2')==[]
    assert core.fill_question_rubric(q,Fake(),'s2')==0


def test_sync_sub_scores_sets_question_total_from_subquestions():
    qs=[{'id':'q1','attributes':{'score':6,'score_source':'ai_assigned'},'subquestions':[{'score':4},{'score':2},{'score':2}]},
        {'id':'q2','attributes':{'score':5,'score_source':'paper_declared'},'subquestions':[{'score':None},{'score':2}]},
        {'id':'q3','attributes':{'score':5}}]
    core.sync_sub_scores(qs)
    assert qs[0]['attributes']['score']==8
    assert qs[0]['attributes']['score_source']=='manual'
    assert qs[1]['attributes']['score']==5
    assert qs[2]['attributes']['score']==5


def test_allocate_paper_scores_fills_only_missing_to_declared_total():
    paper=core.normalize_paper({'id':'p','declared_total_score':100})
    paper['exam']['declared_total_score']=100
    qs=[{'id':'1','paper_id':'p','attributes':{'score':60}},{'id':'2','paper_id':'p','attributes':{}},{'id':'3','paper_id':'p','attributes':{}}]
    core.allocate_paper_scores(paper,qs)
    assert [q['attributes']['score'] for q in qs]==[60,20,20]
    assert paper['computed_total_score']==100
    assert qs[1]['attributes']['score_source']=='ai_assigned'


def test_paper_inheritance_respects_manual_fields():
    paper=core.normalize_paper({'id':'p','attributes':{'subject':'地理','year':'2025'}})
    qs=[{'id':'1','paper_id':'p','attributes':{'subject':'数学','year':'2024'},'attribute_sources':{'subject':'manual'}}]
    core.apply_paper_inheritance(paper,qs)
    assert qs[0]['attributes']['subject']=='数学'
    assert qs[0]['attributes']['year']=='2025'
    assert qs[0]['attribute_sources']['year']=='paper'


def test_paper_source_shapes_are_normalized():
    paper=core.normalize_paper({'id':'p','source':{'printed_page_numbers':'1、2、3','columns':2}})
    assert paper['source']['printed_page_numbers']==['1','2','3']
    # A bare number is a whole-paper column count, not "page 1 only".
    assert paper['source']['columns']==2


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
