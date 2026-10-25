"""LLM 失败重试：每个渠道连续 3 次都失败才放弃。"""
import json
import shutil
from pathlib import Path

import core


def _folder() -> Path:
    folder = Path('.tmp') / 'llm-retry-case'
    shutil.rmtree(folder, ignore_errors=True)
    (folder / 'llm').mkdir(parents=True, exist_ok=True)
    return folder


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_retries_three_times_then_succeeds(monkeypatch):
    folder = _folder()
    attempts = {'count': 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            attempts['count'] += 1
            if attempts['count'] < 3:
                raise ValueError('模型返回的 JSON 无法解析：缺少最外层 }')
            return _Response({'choices': [{'message': {'content': '{"ok": true}'},
                                           'finish_reason': 'stop'}], 'usage': {}})

    monkeypatch.setattr(core, 'configured_channels',
                        lambda: [{'id': 'DEEPSEEK', 'key': 'k', 'model': 'm',
                                  'base': 'https://example.invalid', 'protocol': 'chat'}])
    monkeypatch.setattr(core.httpx, 'Client', FakeClient)

    llm = core.LLM(folder, 'deepseek', refresh=True, run='t1')
    result = llm.json('unit-retry', 'instruction', {'a': 1})
    assert result == {'ok': True}
    assert attempts['count'] == 3
    statuses = [call['status'] for call in llm.calls]
    assert statuses == ['failed', 'failed', 'success']


def test_gives_up_after_three_failures(monkeypatch):
    folder = _folder()
    attempts = {'count': 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            attempts['count'] += 1
            raise ValueError('总是失败')

    monkeypatch.setattr(core, 'configured_channels',
                        lambda: [{'id': 'DEEPSEEK', 'key': 'k', 'model': 'm',
                                  'base': 'https://example.invalid', 'protocol': 'chat'}])
    monkeypatch.setattr(core.httpx, 'Client', FakeClient)

    llm = core.LLM(folder, 'deepseek', refresh=True, run='t2')
    try:
        llm.json('unit-retry', 'instruction', {'a': 1})
        raise AssertionError('应当抛出异常')
    except core.PipelineError as exc:
        assert '均失败' in str(exc)
    assert attempts['count'] == 3
    assert len(llm.calls) == 3
