import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mineru_local


def test_adapt_converts_structured_content_to_content_list(tmp_path):
    raw = tmp_path / 'raw'
    raw.mkdir()
    structured = {
        'pages': [
            {'page_idx': 0, 'blocks': [
                {'type': 'text', 'bbox': [0.1, 0.2, 0.3, 0.25], 'content': '第一段'},
                {'type': 'image', 'bbox': [100, 200, 300, 400], 'content': '',
                 'image_path': 'images/page_0_image_1.jpg'},
            ]},
            {'page_idx': 1, 'blocks': [
                {'type': 'text', 'bbox': [0.05, 0.1, 0.95, 0.2], 'content': '第二页'},
            ]},
        ]
    }
    (raw / 'structured_content.json').write_text(json.dumps(structured, ensure_ascii=False), encoding='utf-8')
    mineru_local.adapt(raw)
    items = json.loads((raw / f'{raw.name}_content_list.json').read_text(encoding='utf-8'))
    assert [item['text'] for item in items] == ['第一段', '', '第二页']
    assert items[0]['bbox'] == [100.0, 200.0, 300.0, 250.0]
    assert items[0]['page_idx'] == 0
    # Pixel boxes from older bundles must pass through untouched.
    assert items[1]['bbox'] == [100, 200, 300, 400]
    assert items[1]['img_path'] == 'images/page_0_image_1.jpg'
    assert items[2]['page_idx'] == 1


def test_adapt_is_idempotent_and_skips_cloud_bundles(tmp_path):
    raw = tmp_path / 'raw'
    raw.mkdir()
    (raw / 'doc_content_list.json').write_text('[]', encoding='utf-8')
    (raw / 'structured_content.json').write_text('{"pages": []}', encoding='utf-8')
    mineru_local.adapt(raw)
    assert (raw / 'doc_content_list.json').read_text(encoding='utf-8') == '[]'


def test_local_provider_respects_cloud_only(monkeypatch):
    monkeypatch.setenv('MINERU_PROVIDER', 'cloud')
    assert mineru_local.enabled() is False
    assert mineru_local.available(0.1) is False
    monkeypatch.setenv('MINERU_PROVIDER', 'auto')
    assert mineru_local.enabled() is True
