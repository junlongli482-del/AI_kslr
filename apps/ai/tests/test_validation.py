import copy
from pathlib import Path

import core
import main
from PIL import Image


def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DATA',tmp_path)
    monkeypatch.setattr(main,'DATA',tmp_path)
    Image.new('RGB',(100,100),'white').save(tmp_path/'page.png')
    return {'task_id':'t','papers':[{'id':'p','title':'Test'}],'documents':[{'id':'d','blocks':[{'id':'b'}],'pages':[{'image_key':'page.png'}]}],
            'questions':[{'id':'q','paper_id':'p','number':'1','stem':'Test','block_ids':['b'],'regions':[{'document_id':'d','page_index':0,'bbox':[.1,.1,.9,.9]}],'answer_entry_id':'a'}],
            'answer_entries':[{'id':'a'}]}


def test_valid_grounded_draft_passes(tmp_path,monkeypatch):
    result=main.validate('t',fixture(tmp_path,monkeypatch))
    assert result['valid']
    assert result['result']['questions'][0]['regions'][0]['crop_url']


def test_missing_image_is_blocking(tmp_path,monkeypatch):
    payload=fixture(tmp_path,monkeypatch)
    payload['questions'][0]['stem']='![](/api/assets?key=missing.png)'
    checked=main.validate('t',payload)
    assert not checked['valid']
    assert any('图片资产' in x['message'] for x in checked['issues'])


def test_answer_conflicts_and_foreign_blocks_are_blocking(tmp_path,monkeypatch):
    payload=fixture(tmp_path,monkeypatch)
    q=copy.deepcopy(payload['questions'][0]);q['id']='q2';q['number']='2';q['block_ids']=['unknown'];payload['questions'].append(q)
    checked=main.validate('t',payload)
    assert not checked['valid']
    assert any('重复关联' in x['message'] for x in checked['issues'])
    assert any('内容块' in x['message'] for x in checked['issues'])


def test_invalid_schema_returns_actionable_validation_not_server_error(tmp_path,monkeypatch):
    checked=main.validate('t',{'questions':'broken'})
    assert not checked['valid'] and checked['issues'][0]['severity']=='error'
