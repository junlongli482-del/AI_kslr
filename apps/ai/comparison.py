"""Compare full pipelines independently after sharing the same OCR documents."""
import copy
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from channels import channels
from core import compile_result, save, read
from diagnostics import describe_error, PipelineError


def compare(task_id, documents, folder, generate, progress):
    providers=channels()
    if not providers:raise PipelineError('未配置可用模型渠道',[])
    report={'policy':'compare','selection':'质量检查项较少者优先，最终需人工审核','candidates':[],'selected':None}
    for p in providers:
        report['candidates'].append({'channel':p['id'].lower(),'model':p['model'],'status':'running','started_at':time.time()})
    save(folder/'comparison.json',report)
    def run(provider):
        ch=provider['id'].lower();out=folder/'candidates'/ch
        def update(stage,message):
            # Stage per candidate is kept separately; the public task remains in compare mode.
            save(out/'state.json',{'stage':stage,'message':message,'updated_at':time.time()})
        return compile_result(task_id,copy.deepcopy(documents),out,generate,ch,update)
    errors=[];valid={}
    with ThreadPoolExecutor(max_workers=len(providers),thread_name_prefix='model-compare') as executor:
        futures={executor.submit(run,p):p for p in providers}
        for future in as_completed(futures):
            p=futures[future];ch=p['id'].lower();item=next(c for c in report['candidates'] if c['channel']==ch)
            item['seconds']=round(time.time()-item['started_at'],2)
            calls=folder/'candidates'/ch/'llm/calls.json'
            records=read(calls) if calls.exists() else []
            item['calls']=records
            item['cost_cny']=round(sum((c.get('cost') or {}).get('amount') or 0 for c in records),8)
            item['cost_status']='estimated_or_unknown' if any((c.get('cost') or {}).get('amount_status') not in ('actual','calculated') for c in records) else 'calculated'
            try:
                result=future.result();valid[ch]=result
                qs=result['questions'];item['status']='success'
                item['quality']={'questions':len(qs),'missing_answers':sum(not q.get('answer') for q in qs),
                                 'missing_regions':sum(not q.get('regions') for q in qs),'review_flags':sum(len(q.get('issues',[])) for q in qs)}
                # No cross-candidate mixing; these are mechanical indicators, not an accuracy claim.
                item['quality_note']='题量和缺项等机械检查；内容准确性需要原卷核对'
                first=len(valid)==1
                if first:
                    report['selected']=ch;save(folder/'result.json',result)
                    progress('模型对比',f'{ch}已完成，可预览；其他模型继续处理')
            except Exception as exc:
                diagnostic=describe_error(exc,'模型对比','LLM',ch);diagnostic['attempts']=getattr(exc,'attempts',[])
                item.update(status='failed',error=diagnostic);errors.append(diagnostic)
            save(folder/'comparison.json',report)
            # Aggregate every request, including unsuccessful and cached requests, for task cost.
            merged=[]
            for c in report['candidates']:
                cp=folder/'candidates'/c['channel']/'llm/calls.json'
                if cp.exists():merged.extend(read(cp))
            save(folder/'llm/calls.json',merged)
    if not valid:raise PipelineError('所有模型对比候选均失败',errors)
    candidates=[c for c in report['candidates'] if c['status']=='success' and c['quality']['questions']>0]
    if not candidates:raise PipelineError('所有模型返回空题目，不能作为可用结果',errors)
    chosen=min(candidates,key=lambda c:(c['quality']['missing_regions'],c['quality']['review_flags'],c['quality']['missing_answers']))
    report['selected']=chosen['channel'];save(folder/'comparison.json',report)
    result=valid[chosen['channel']]
    result['processing_metadata']['comparison']=report
    save(folder/'result.json',result)
    return result
