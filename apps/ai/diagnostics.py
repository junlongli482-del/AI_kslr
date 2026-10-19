"""Actionable provider diagnostics with credential and signed URL redaction."""
import json
import os
import re

import httpx


def redact(value):
    text = str(value)
    for name, secret in os.environ.items():
        if secret and ('API_KEY' in name or name.endswith('TOKEN')):
            text = text.replace(secret, '[已隐藏密钥]')
    text = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[已隐藏密钥]', text)
    text = re.sub(r'Bearer\s+[^\s"<>]+', 'Bearer [已隐藏]', text, flags=re.I)
    text = re.sub(r'https?://[^\s"<>]+', lambda m: m.group().split('?')[0], text)
    text = re.sub(r'(?i)((?:api[_-]?key|authorization|token|signature)\s*[=:]\s*)[^\s,;]+', r'\1[已隐藏]', text)
    return text[:2000]


def describe_error(exc, stage='', service='', operation=''):
    status = None
    detail = str(exc)
    retryable = False
    hint = '检查资料或详细原因后重试，已完成的识别阶段会复用。'
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        try:
            body = exc.response.json()
            error = body.get('error', body) if isinstance(body, dict) else body
            detail = error.get('message', json.dumps(error, ensure_ascii=False)) if isinstance(error, dict) else str(error)
        except (ValueError, TypeError):
            detail = re.sub(r'<[^>]+>', ' ', exc.response.text)
            detail = re.sub(r'\s+', ' ', detail).strip() or str(exc)
        detail = f'HTTP {status}：{detail}'
        retryable = status in (408, 429) or status >= 500
        hint = {401: '供应商拒绝认证，请检查该渠道密钥。',
                403: '供应商拒绝访问，请检查账户权限或模型权限。',
                429: '供应商限制了请求速率或并发，请降低并发数或稍后重试。',
                524: '供应商网关等待上游响应超时，可切换渠道或稍后重试。'}.get(status, hint)
    elif isinstance(exc, httpx.TimeoutException):
        detail = f'{type(exc).__name__}：外部服务未在设定时间内响应'
        retryable = True
        hint = '检查渠道服务状态或稍后重试；本地无上限不代表供应商无并发限制。'
    elif isinstance(exc, httpx.NetworkError):
        detail = f'{type(exc).__name__}：{exc}'
        retryable = True
        hint = '检查网络连接和供应商服务状态后重试。'
    elif isinstance(exc, json.JSONDecodeError):
        detail = f'模型返回的 JSON 无法解析：第 {exc.lineno} 行，第 {exc.colno} 列，{exc.msg}'
        hint = '该渠道返回了不完整或格式错误的内容，重试会重新调用失败阶段。'
    elif isinstance(exc, KeyError):
        detail = f'缺少必需字段：{exc.args[0]}'
    return {'stage': stage, 'service': service, 'operation': operation,
            'type': type(exc).__name__, 'status_code': status, 'detail': redact(detail),
            'retryable': retryable, 'hint': hint}


class PipelineError(RuntimeError):
    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts = attempts
