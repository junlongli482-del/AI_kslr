import copy
import json
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import pytest
from PIL import Image

import core
import main
import media
from channels import cost, timeout


def source(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DATA',tmp_path);monkeypatch.setattr(main,'DATA',tmp_path)
    folder=tmp_path/'tasks'/'t';folder.mkdir(parents=True)
    name='a'*40+'.png';asset=folder/'d'/'raw'/'images'/name;asset.parent.mkdir(parents=True)
    Image.new('RGB',(100,100)).save(asset)
    url=core.asset_url(asset)
    docs=[{'id':'d','role':'question','pages':[{'page_index':0,'width_px':2000,'height_px':1400,'image_key':'page.png'}],
           'blocks':[{'id':'b','kind':'text','text':f'![]({url})','page_index':0,'bbox':[.05,.2,.47,.4]}],
           'asset_metadata':{url:{'bbox':[.39,.2,.47,.3],'page_index':0,'width_px':100,'height_px':100,'caption':['甲']}}}]
    q={'id':'q','paper_id':'p','number':'1','stem':f'![]({url})','options':[],'subquestions':[],'answer':'','analysis':'',
       'regions':[{'document_id':'d','page_index':0,'bbox':[.39,.2,.47,.3],'purpose':'content'}],
       'block_ids':['b'],'attributes':{},'issues':[],'editor_documents':{}}
    return docs,q,url,folder


def test_picture_region_is_not_the_display_width_reference(tmp_path,monkeypatch):
    docs,q,url,_=source(tmp_path,monkeypatch)
    media.apply_layout(q,docs)
    assert q['image_layout'][url]['render_width_pct']==pytest.approx(19.048,abs=.001)
    changed=copy.deepcopy(q);changed['regions'][0]['bbox']=[.05,.2,.47,.4]
    media.apply_layout(changed,docs)
    assert changed['image_layout'][url]['render_width_pct']==q['image_layout'][url]['render_width_pct']
    assert q['stem'].startswith('![甲]')


def test_option_width_converts_to_the_actual_option_cell_once(tmp_path,monkeypatch):
    docs,q,url,_=source(tmp_path,monkeypatch)
    q['stem']='选择题';q['options']=[{'label':c,'content':f'![]({url})'} for c in 'ABCD']
    media.apply_layout(q,docs)
    # Shared asset is still converted once, not four successive multiplications.
    assert q['image_layout'][url]['render_width_pct']==pytest.approx(76.192,abs=.01)
    before=copy.deepcopy(q);media.apply_layout(q,docs);assert q==before


def test_model_image_layout_variants_are_normalized_to_mapping():
    q={'image_layout':[]}
    assert core.normalize_model_question(q)['image_layout']=={}
    q={'image_layout':[{'url':'/api/assets?key=x','caption':['甲'],'row':1}]}
    assert core.normalize_model_question(q)['image_layout']['/api/assets?key=x']['caption']==['甲']


def test_source_two_by_two_options_are_not_forced_to_four_columns(tmp_path,monkeypatch):
    docs,q,url,_=source(tmp_path,monkeypatch);q['stem']='选择'
    for i,(x,y) in enumerate([(.08,.3),(.28,.3),(.08,.5),(.28,.5)]):
        u=f'/api/assets?key={i}.png';docs[0]['asset_metadata'][u]={'bbox':[x,y,x+.1,y+.1],'page_index':0}
        q['options'].append({'label':str(i),'content':f'![]({u})'})
    media.apply_layout(q,docs)
    assert q['options_layout']['columns']==2


def test_missing_directory_is_repaired_in_place_and_duplicate_editor_removed(tmp_path,monkeypatch):
    docs,q,url,_=source(tmp_path,monkeypatch)
    bad='/api/assets?key=tasks%2Ft%2F'+('a'*40)+'.png'
    q['stem']=f'![]({bad})\n甲\n![]({url})'
    q['editor_documents']={'stem':{'type':'doc','content':[{'type':'paragraph','content':[{'type':'image','attrs':{'src':bad}},{'type':'image','attrs':{'src':url}}]}]}}
    audit=media.repair_assets(q,docs,tmp_path,'t');media.apply_layout(q,docs)
    assert len(audit)==1 and bad not in q['stem'] and q['stem'].count(url)==1
    assert len(q['editor_documents']['stem']['content'][0]['content'])==1
    before=copy.deepcopy(q);assert media.repair_assets(q,docs,tmp_path,'t')==[];media.apply_layout(q,docs);assert before==q


def test_one_character_filename_error_only_repairs_unique_known_asset(tmp_path,monkeypatch):
    docs,q,url,_=source(tmp_path,monkeypatch)
    bad=url.replace('a'*40,'a'*39);q['stem']=f'![]({bad})'
    assert media.repair_assets(q,docs,tmp_path,'t')
    assert url in q['stem']


def test_removed_original_is_not_resurrected_by_alias_repair(tmp_path,monkeypatch):
    docs,q,url,_=source(tmp_path,monkeypatch)
    bad=url.replace('a'*40,'a'*39);q['stem']=f'![]({bad})';q['excluded_image_urls']=[url]
    media.repair_assets(q,docs,tmp_path,'t');assert '![' not in q['stem']


def test_same_column_side_graphic_merges_but_spread_does_not():
    docs=[{'id':'d','blocks':[{'id':'a','page_index':0,'bbox':[.52,.59,.86,.75]},
                             {'id':'b','page_index':0,'bbox':[.867,.595,.938,.632]},
                             {'id':'c','page_index':0,'bbox':[.05,.59,.47,.75]}]}]
    boxes=core.regions_from_blocks(['a','b','c'],docs)
    assert len(boxes)==2 and boxes[0]['bbox']==[.52,.59,.938,.75]


def test_question_span_covers_blank_until_next_question(tmp_path,monkeypatch):
    docs,q,url,_=source(tmp_path,monkeypatch)
    docs[0]['blocks']=[{'id':'a','page_index':0,'bbox':[.53,.07,.93,.09]},
                       {'id':'b2','page_index':0,'bbox':[.53,.28,.93,.30]},
                       {'id':'c','page_index':0,'bbox':[.53,.49,.93,.8]}]
    q['block_ids']=['a','b2'];q['regions']=[]
    nextq=copy.deepcopy(q);nextq['id']='q2';nextq['block_ids']=['c'];nextq['regions']=[]
    core.question_span_regions([q,nextq],docs)
    assert q['regions'][0]['bbox']==pytest.approx([.53,.066,.93,.49])
    assert nextq['regions'][0]['bbox'][3]==.96


def test_structured_table_removes_source_image_even_without_asset_key(tmp_path,monkeypatch):
    docs,q,url,_=source(tmp_path,monkeypatch)
    docs[0]['blocks'].append({'id':'tbl','kind':'table','text':'','page_index':0,'bbox':[.39,.2,.47,.3]})
    q['tables']=[{'structure_status':'structured','source_block_id':'tbl','markdown':'|a|b|'}]
    q['stem']=f'![]({url})\n|a|b|'
    media.apply_layout(q,docs)
    assert '![' not in q['stem'] and '|a|b|' in q['stem']


def test_long_model_wait_and_price_unknown_are_not_zero(monkeypatch):
    monkeypatch.delenv('LLM_READ_TIMEOUT_SECONDS',raising=False)
    assert timeout().read==1800 and timeout().connect==25
    assert cost('DEEPSEEK',{})['amount'] is None
    price=cost('DEEPSEEK',{'prompt_tokens':1000000,'prompt_cache_hit_tokens':500000,'completion_tokens':1000000},datetime(2026,10,15,10,tzinfo=timezone(timedelta(hours=8))))
    assert price['amount']==9.02 and price['amount_status']=='estimated'


def test_comparison_runs_full_candidates_concurrently_and_preserves_results(tmp_path,monkeypatch):
    import comparison
    barrier=threading.Barrier(3)
    monkeypatch.setattr(comparison,'channels',lambda:[{'id':x,'model':x} for x in ['LOW','STABLE','DEEPSEEK']])
    def fake(task,documents,folder,generate,channel,progress):
        barrier.wait(timeout=3)
        result={'task_id':task,'questions':[{'id':channel,'answer':'A','regions':[{}],'issues':[]}],'processing_metadata':{}}
        core.save(folder/'result.json',result);core.save(folder/'llm/calls.json',[{'channel':channel,'cost':{'amount':1,'amount_status':'calculated'}}]);return result
    monkeypatch.setattr(comparison,'compile_result',fake)
    result=comparison.compare('t',[],tmp_path,False,lambda *args:None)
    report=core.read(tmp_path/'comparison.json')
    assert all(c['status']=='success' for c in report['candidates'])
    assert len(core.read(tmp_path/'llm/calls.json'))==3
    assert result['questions'][0]['id'] in ['low','stable','deepseek']
