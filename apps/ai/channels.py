"""Provider registry, long response waits and transparent usage-based pricing."""
import os
from datetime import datetime, timezone, timedelta

import httpx


def channels():
    result=[]
    # LOW remains supported for explicit test/legacy configuration, but is not
    # enabled in the project's .env after the provider became unavailable.
    for name in ['LOW','STABLE','DEEPSEEK','CLAUDE','GEMINI','MINIMAX','GLM']:
        prefix='LLM_'+name
        key=os.getenv(prefix+'_API_KEY') or (os.getenv('DEEPSEEK_API_KEY') if name=='DEEPSEEK' else None)
        if not key:continue
        base=os.getenv(prefix+'_BASE_URL','https://api.deepseek.com' if name=='DEEPSEEK' else '').rstrip('/')
        protocol=os.getenv(prefix+'_PROTOCOL', 'chat' if name=='DEEPSEEK' or 'gpt.huaiapi.xyz' not in base else 'responses')
        result.append({'id':name,'key':key,'base':base,'model':os.getenv(prefix+'_MODEL','deepseek-flash' if name=='DEEPSEEK' else ''),'protocol':protocol})
    return result


def timeout():
    return httpx.Timeout(float(os.getenv('LLM_READ_TIMEOUT_SECONDS','1800')),
                         connect=float(os.getenv('LLM_CONNECT_TIMEOUT_SECONDS','25')))


def cost(channel, usage, now=None):
    prompt=int(usage.get('prompt_tokens',usage.get('input_tokens',0)) or 0)
    output=int(usage.get('completion_tokens',usage.get('output_tokens',0)) or 0)
    details=usage.get('prompt_tokens_details') or {}
    cached=int(usage.get('prompt_cache_hit_tokens',details.get('cached_tokens',0)) or 0)
    written=int(details.get('cache_write_tokens',0) or 0)
    uncached=max(0,prompt-cached-written)
    tier='base_gt_272k' if prompt>272000 else 'base_lt_272k'
    status='calculated' if usage else 'unknown'
    if channel=='DEEPSEEK':
        # Legal-holiday calendar was not supplied. Preserve the possible price range.
        now=now or datetime.now(timezone(timedelta(hours=8)))
        peak=now.weekday()<5 and (9<=now.hour<12 or 14<=now.hour<18)
        prices=(2,8,.04,0) if peak else (1,4,.02,0)
        plan='deepseek-flash-user-2026-10-15';tier='weekday_peak_calendar_unverified' if peak else 'off_peak'
        status='estimated' if usage else 'unknown'
    else:
        plan='a-enterprise' if channel=='STABLE' else ('full-plus' if channel=='LOW' else f'{channel.lower()}-provider')
        known={'a-enterprise':{'base_lt_272k':(1.4,7,.07,1.75),'base_gt_272k':(2.8,10.5,.14,3.5)},
               'full-plus':{'base_lt_272k':(.24,1.2,.012,.3),'base_gt_272k':(.48,1.8,.024,.6)}}
        priced=plan in known
        prices=known.get(plan,{}).get(tier,(0,0,0,0)); status='unknown' if not priced else status
    amount=((uncached*prices[0]+output*prices[1]+cached*prices[2]+written*prices[3])/1_000_000 if usage and (channel=='DEEPSEEK' or priced) else None)
    result={'provider':'llm','pricing_plan_id':plan,'tier':tier,'currency':'CNY','input_tokens':prompt,
            'output_tokens':output,'cached_read_tokens':cached,'cached_write_tokens':written,
            'amount':round(amount,8) if amount is not None else None,'amount_status':status,
            'unit_price_cny_per_million':dict(zip(['input','output','cache_read','cache_write'],prices)),
            'pricing_basis':'用户提供单价×供应商usage；非账单核销'}
    if channel=='DEEPSEEK' and usage:
        result['amount_range']=[round((uncached+output*4+cached*.02)/1_000_000,8),round((uncached*2+output*8+cached*.04)/1_000_000,8)]
        result['pricing_note']='节假日时段未接入官方日历，按北京时间工作日估算；最终以供应商账单为准'
    return result
