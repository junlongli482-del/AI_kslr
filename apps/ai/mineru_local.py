"""Local MinerU (self-hosted 4.x) provider.

The local API server exposes MinerU's V1 HTTP API on 127.0.0.1; a parse request
returns the same zip bundle as the cloud service, but with different member
names.  This module keeps that difference in one place so ``normalize`` stays
provider agnostic.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx


def base_url() -> str:
    return os.getenv('MINERU_LOCAL_URL', 'http://127.0.0.1:8020').rstrip('/')


def enabled() -> bool:
    return os.getenv('MINERU_PROVIDER', 'auto').lower() in ('local', 'auto')


def available(timeout: float = 3.0) -> bool:
    if not enabled():
        return False
    try:
        response = httpx.get(base_url() + '/v1/health', timeout=timeout)
        return response.status_code == 200 and response.json().get('status') == 'ok'
    except Exception:
        return False


def fetch_zip(source: Path, timeout: float | None = None) -> bytes:
    """Ask the resident local server for a parse bundle (zip bytes)."""
    limit = timeout or float(os.getenv('MINERU_LOCAL_TIMEOUT', '600'))
    with httpx.Client(timeout=limit) as client:
        with source.open('rb') as stream:
            response = client.post(
                base_url() + '/v1/file_parse',
                params={'tier': os.getenv('MINERU_LOCAL_TIER', 'standard'),
                        'response_format': 'zip',
                        'wait_timeout': int(limit)},
                files={'files': (source.name, stream, 'application/pdf')},
            )
        response.raise_for_status()
        if response.headers.get('content-type', '').startswith('application/json'):
            payload = response.json()
            raise ValueError('MinerU本地解析未完成：' + str(payload.get('status') or payload)[:120])
        return response.content


def adapt(raw: Path) -> None:
    """Convert MinerU 4.x structured content into the content_list shape we read."""
    if next(raw.rglob('*content_list.json'), None):
        return
    structured = next(raw.rglob('structured_content.json'), None)
    if not structured:
        return
    try:
        data = json.loads(structured.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    items = []
    for page in data.get('pages') or []:
        page_index = int(page.get('page_idx') or 0)
        for block in page.get('blocks') or []:
            bbox = block.get('bbox') or []
            if len(bbox) != 4:
                continue
            scale = 1000.0 if max(abs(float(v)) for v in bbox) <= 1.5 else 1.0
            text = block.get('content') or block.get('text') or ''
            if not isinstance(text, str):
                text = json.dumps(text, ensure_ascii=False)
            item = {'type': block.get('type', 'text'), 'page_idx': page_index,
                    'bbox': [float(v) * scale for v in bbox], 'text': text}
            image = (block.get('image_source') or block.get('image_path')
                     or block.get('img_path'))
            if image:
                item['img_path'] = image
            caption = block.get('captions') or block.get('image_caption') or block.get('table_caption')
            if caption:
                item['image_caption' if block.get('type') == 'image' else 'table_caption'] = caption
            items.append(item)
    if items:
        (raw / f'{raw.name}_content_list.json').write_text(
            json.dumps(items, ensure_ascii=False), encoding='utf-8')
