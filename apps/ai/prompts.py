"""Prompt overrides: defaults live in code, edits live in data/settings/prompts.json."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'
PATH = DATA / 'settings' / 'prompts.json'
LOCK = threading.Lock()
_cache: dict = {'mtime': None, 'data': {}}


def _load() -> dict:
    try:
        mtime = PATH.stat().st_mtime
    except OSError:
        return {}
    if _cache['mtime'] == mtime:
        return _cache['data']
    try:
        data = json.loads(PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    _cache.update(mtime=mtime, data=data)
    return data


def _write(data: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix('.json.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(PATH)
    _cache.update(mtime=None, data={})


def get_prompt(key: str, default: str) -> str:
    entry = (_load().get(key) or {}).get('current')
    return entry.get('content') if isinstance(entry, dict) and entry.get('content') else default


def describe(key: str, default: str) -> dict:
    entry = _load().get(key) or {}
    current = entry.get('current') or {'content': default, 'revision': 0, 'sha1': _sha1(default), 'updated_at': None}
    return {'key': key, 'content': current.get('content', default), 'revision': current.get('revision', 0),
            'sha1': current.get('sha1', _sha1(default)), 'updated_at': current.get('updated_at'),
            'default_chars': len(default), 'is_default': not entry.get('current'),
            'history': [{'revision': item.get('revision'), 'sha1': item.get('sha1'), 'updated_at': item.get('updated_at'),
                         'chars': len(item.get('content') or '')} for item in (entry.get('history') or [])[-20:]]}


def list_prompts(defaults: dict) -> list[dict]:
    data = _load()
    rows = []
    for key, default in defaults.items():
        entry = data.get(key) or {}
        current = entry.get('current') or {}
        rows.append({'key': key, 'revision': current.get('revision', 0),
                     'updated_at': current.get('updated_at'), 'chars': len(current.get('content') or default),
                     'default_chars': len(default), 'is_default': not current})
    return rows


def save(key: str, content: str, defaults: dict) -> dict:
    if not content or not content.strip():
        raise ValueError('提示词不能为空')
    with LOCK:
        data = _load()
        entry = data.setdefault(key, {'current': None, 'history': []})
        previous = entry.get('current')
        if previous:
            entry['history'].append(previous)
        revision = (previous or {}).get('revision', 0) + 1
        entry['current'] = {'content': content, 'revision': revision, 'sha1': _sha1(content),
                            'updated_at': datetime.now().isoformat(timespec='seconds')}
        _write(data)
    return describe(key, defaults.get(key, ''))


def rollback(key: str, revision: int, defaults: dict) -> dict:
    with LOCK:
        data = _load()
        entry = data.get(key) or {}
        target = next((item for item in entry.get('history') or [] if item.get('revision') == revision), None)
        if not target:
            raise ValueError('找不到该历史版本')
        content = target.get('content') or ''
        data.setdefault(key, {'current': None, 'history': []})
        current = data[key].get('current')
        if current:
            data[key]['history'].append(current)
        data[key]['current'] = {'content': content, 'revision': (current or {}).get('revision', 0) + 1,
                                'sha1': _sha1(content), 'updated_at': datetime.now().isoformat(timespec='seconds')}
        _write(data)
    return describe(key, defaults.get(key, ''))


def reset(key: str, defaults: dict) -> dict:
    with LOCK:
        data = _load()
        entry = data.get(key)
        if entry:
            data.pop(key, None)
            _write(data)
    return describe(key, defaults.get(key, ''))


def _sha1(text: str) -> str:
    return hashlib.sha1((text or '').encode('utf-8')).hexdigest()[:12]
