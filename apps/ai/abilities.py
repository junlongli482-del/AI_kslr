"""学科能力维度 + 认知层级：值域唯一实现。

两轴设计：能力（本科核心素养，3~7 个含“其他”）× 认知层级（C1–C4 全学科通用）。
不做跨学段、跨学科比较，所以按 (学段, 学科) 各自一套值。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ABILITY_FILE = ROOT / 'apps' / 'ai' / 'tagging' / 'abilities.json'

_CACHE: dict = {'mtime': None, 'data': {'levels': [], 'level_notes': {}, 'subjects': {}}}


def _load() -> dict:
    try:
        mtime = ABILITY_FILE.stat().st_mtime
    except OSError:
        return _CACHE['data']
    if _CACHE['mtime'] != mtime:
        try:
            _CACHE['data'] = json.loads(ABILITY_FILE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        _CACHE['mtime'] = mtime
    return _CACHE['data']


def levels() -> list[dict]:
    return [{'code': code, 'name': name, 'definition': text}
            for code, name, text in _load().get('levels') or []]


def abilities(slug: str) -> list[dict]:
    items = (_load().get('subjects') or {}).get(slug) or []
    return [{'code': code, 'name': name, 'hint': hint} for code, name, hint in items]


def codes(slug: str) -> set[str]:
    return {item['code'] for item in abilities(slug)}


def level_codes() -> set[str]:
    return {item['code'] for item in levels()}


def payload(slug: str) -> dict:
    return {'slug': slug, 'abilities': abilities(slug), 'levels': levels(),
            'level_note': (_load().get('level_notes') or {}).get(slug, ''),
            'primary_required': True, 'secondary_max': 1}


def prompt_block(slug: str) -> str:
    """拼进打标前缀的能力段：只列本科取值，避免跨学科干扰。"""
    items = abilities(slug)
    if not items:
        return ''
    ability_lines = '\n'.join(f'- {item["code"]} {item["name"]}：{item["hint"]}' for item in items)
    level_lines = '\n'.join(f'- {item["code"]} {item["name"]}：{item["definition"]}' for item in levels())
    note = (_load().get('level_notes') or {}).get(slug, '')
    extra = f'\n本学科判层提示：{note}' if note else ''
    return (
        '\n【能力维度】只能从下列本科取值中选择，不得自造，也不得使用其他学科的词。\n'
        f'{ability_lines}\n'
        '规则：ability_primary 必填，1 个；ability_secondary 可空，最多 1 个；'
        '两者不能相同；判断依据是“这题要求学生做什么动作”，不是“这题涉及什么内容”；'
        '只有确实任何一项都不贴切时才用“其他”，能归入任何一项就不许用“其他”。\n'
        '\n【认知层级】从 C1–C4 中选 1 个，描述这道题要求的思维深度，与难度不是一回事。\n'
        f'{level_lines}{extra}\n'
        '输出示例："ability": {"primary": "MA-SEN-LOG", "secondary": "MA-SEN-ABS", "cognitive_level": "C4"}；'
        '没有次能力时 secondary 给 null。'
    )


def normalize_result(result: dict, slug: str) -> dict:
    """把模型输出收敛成 {primary, secondary, cognitive_level}，非法值置空。"""
    payload_data = result.get('ability') if isinstance(result.get('ability'), dict) else {}
    valid_codes = codes(slug)
    valid_levels = level_codes()
    primary = str(payload_data.get('primary') or '').strip().upper()
    secondary = str(payload_data.get('secondary') or '').strip().upper()
    level = str(payload_data.get('cognitive_level') or '').strip().upper()
    if primary not in valid_codes:
        primary = ''
    if secondary not in valid_codes or secondary == primary:
        secondary = ''
    if level not in valid_levels:
        level = ''
    return {'primary': primary or None, 'secondary': secondary or None,
            'cognitive_level': level or None}
