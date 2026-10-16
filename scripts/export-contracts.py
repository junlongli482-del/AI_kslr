"""Export the implemented AI schema and the public HTTP surface, without secrets."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/ai'))
from core import Result

out=ROOT/'docs/contracts/quick-entry'
out.mkdir(parents=True,exist_ok=True)
(out/'result-v1.schema.json').write_text(json.dumps(Result.model_json_schema(),ensure_ascii=False,indent=2),encoding='utf-8')
paths={}
definitions=[
 ('/api/health','get','服务状态'),
 ('/api/quick-entry/tasks','get','查询任务'),('/api/quick-entry/tasks','post','新建任务'),
 ('/api/quick-entry/tasks/{id}','get','任务阶段、文件与事件'),
 ('/api/quick-entry/tasks/{id}/files','post','上传题目或答案文件'),
 ('/api/quick-entry/tasks/{id}/images','post','粘贴或上传审核补充图片'),
 ('/api/quick-entry/settings/concurrency','get','读取实际并发设置与任务数量'),
 ('/api/quick-entry/settings/concurrency','put','调整并发，0表示无本地上限'),
 ('/api/quick-entry/tasks/{id}/start','post','启动处理'),('/api/quick-entry/tasks/{id}/retry','post','恢复处理'),
 ('/api/quick-entry/tasks/{id}/review','get','读取审核稿'),('/api/quick-entry/tasks/{id}/review','put','乐观锁保存审核稿'),
 ('/api/quick-entry/tasks/{id}/validate','post','校验结构与裁图'),('/api/quick-entry/tasks/{id}/commit','post','幂等事务入库'),
 ('/api/assets','get','读取原始PDF或图片资产'),('/api/catalogs','get','目录配置状态'),
 ('/api/questionbank/questions','get','查询题库'),('/api/questionbank/questions/{id}','get','题目版本详情'),
 ('/api/paperbank/papers','get','查询试卷库'),('/api/paperbank/papers/{id}','get','试卷、题目版本与原卷模板'),
]
for path,method,summary in definitions:
 entry={'summary':summary,'responses':{'200':{'description':'成功'},'400':{'description':'输入错误'},'409':{'description':'版本冲突或阶段不可执行'},'500':{'description':'服务错误'}}}
 params=[]
 if '{id}' in path:params.append({'name':'id','in':'path','required':True,'schema':{'type':'string'}})
 if path=='/api/assets':params.append({'name':'key','in':'query','required':True,'schema':{'type':'string'},'description':'data目录内的相对资产键，禁止目录穿越'})
 if path=='/api/questionbank/questions':params.append({'name':'query','in':'query','schema':{'type':'string'}})
 if params:entry['parameters']=params
 if method in ('post','put') and not path.endswith(('/start','/retry')):
  if path.endswith('/images'):
   entry['requestBody']={'required':True,'content':{'multipart/form-data':{'schema':{'type':'object','required':['file'],'properties':{'file':{'type':'string','format':'binary'}}}}}}
  elif path.endswith('/files'):
   entry['requestBody']={'required':True,'content':{'multipart/form-data':{'schema':{'type':'object','required':['files'],'properties':{'files':{'type':'array','items':{'type':'string','format':'binary'}},'role':{'type':'string','enum':['question','answer','mixed']}}}}}}
  else:
   schema={'type':'object'}
   if path.endswith('/commit'):schema={'type':'object','required':['revision'],'properties':{'revision':{'type':'integer','minimum':0}}}
   elif path.endswith('/concurrency'):schema={'type':'object','required':['max_concurrency'],'properties':{'max_concurrency':{'type':'integer','minimum':0,'description':'0为无本地上限，正整数为同时处理的任务数'}}}
   elif path.endswith('/review'):schema={'type':'object','required':['expected_revision','result'],'properties':{'expected_revision':{'type':'integer'},'result':{'$ref':'./result-v1.schema.json'}}}
   elif path.endswith('/validate'):schema={'$ref':'./result-v1.schema.json'}
   elif path=='/api/quick-entry/tasks':schema={'type':'object','required':['mode'],'properties':{'title':{'type':'string'},'mode':{'type':'string','enum':['textbook','paper','questions']},'generate_answers':{'type':'boolean','default':False},'channel_policy':{'type':'string','enum':['low_first','stable_first']}}}
   entry['requestBody']={'required':not path.endswith('/validate'),'content':{'application/json':{'schema':schema}}}
 paths.setdefault(path,{})[method]=entry
spec={'openapi':'3.1.0','info':{'title':'快速录入本地工作台API','version':'0.1.0'},'servers':[{'url':'http://127.0.0.1:8090'}],'paths':paths}
(out/'openapi.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Exported AI schema and {len(paths)} HTTP paths.')
