import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import {chromium} from '../apps/web/node_modules/@playwright/test/index.mjs'
import {projectRoot,browserOptions} from './browser-runtime.mjs'

// Real OCR evidence, isolated API writes: these checks never modify a human draft.
const original=await (await fetch('http://127.0.0.1:8090/api/quick-entry/tasks/61f9ab84-8226-4f2a-b5b9-3b834bf3058b/review')).json()
let draft=structuredClone(original.result)
draft.task_id='feedback-test'
draft.questions=[draft.questions.find(q=>q.number==='5')]
const q=draft.questions[0]
q.answer=String.raw`设答对的概率为 \(p=\frac34\)。\n\n\[p^2=\left(\frac34\right)^2=\frac9{16}.\]`.replaceAll('\\n','\n')
q.analysis=String.raw`（1）\(\overrightarrow{AF}=\frac23a+\frac29b\)。`
delete q.editor_documents.answer;delete q.editor_documents.analysis
let revision=0,uploadCount=0,limit=3
const task={id:'feedback-test',title:'反馈验证：公式和漏图',status:'ready',stage:'待审核',mode:'textbook',created_at:'2026-10-15T15:00:00',message:'done'}
const failure={id:'failure-test',title:'反馈验证：失败详情',status:'failed',mode:'textbook',stage:'处理失败',created_at:'2026-10-15T15:00:00',message:'AI编排失败：供应商超时',files:[],events:[],error:{stage:'AI编排',detail:'两个模型渠道均失败',hint:'已完成阶段可以复用',attempts:[{channel:'low',operation:'structure-d1',detail:'ReadTimeout：外部服务未在设定时间内响应',hint:'检查渠道状态后重试'},{channel:'stable',operation:'structure-d1',detail:'HTTP 524：upstream timeout',hint:'供应商网关等待上游响应超时'}]}}
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6C2kAAAAASUVORK5CYII=','base64')
const browser=await chromium.launch(browserOptions(chromium))
const page=await browser.newPage({viewport:{width:1536,height:1000}})
const errors=[]
page.on('pageerror',e=>errors.push(e.message))
const out=path.join(projectRoot,'docs/handoff/quick-entry/screenshots/feedback-fixes')
await fs.mkdir(out,{recursive:true})
await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),p=url.pathname
  const json=value=>route.fulfill({json:value})
  if(p==='/api/assets'){
    if(url.searchParams.get('key')==='test/clipboard.png')return route.fulfill({body:png,contentType:'image/png'})
    return route.continue()
  }
  if(p==='/api/quick-entry/tasks')return json([task,failure])
  if(p==='/api/quick-entry/settings/concurrency'){
    if(req.method()==='PUT')limit=req.postDataJSON().max_concurrency
    return json({max_concurrency:limit,unlimited:limit===0,running:2,queued:limit===0?0:1})
  }
  if(p.endsWith('/images')){assert.match(req.headers()['content-type'],/multipart\/form-data/);uploadCount++;return json({url:'/api/assets?key=test%2Fclipboard.png',name:'粘贴截图',width_px:1,height_px:1})}
  if(p.endsWith('/review')){
    if(req.method()==='PUT'){draft=req.postDataJSON().result;return json({revision:++revision,saved:true})}
    return json({result:draft,revision})
  }
  if(p.endsWith('/failure-test'))return json(failure)
  if(p.endsWith('/feedback-test'))return json(task)
  return route.fulfill({status:404,json:{message:'Unknown isolated test endpoint'}})
})
try{
  await page.goto('http://127.0.0.1:5173/',{waitUntil:'networkidle'})
  const math=await page.evaluate(async()=>{
    const m=await import('/src/render.ts')
    const source=String.raw`行内 \(\frac34\)，显示 \[\begin{matrix}1&2\\3&4\end{matrix}\]，$x^2$ 和 $$y=1$$`
    const box=document.createElement('div');box.innerHTML=m.renderMarkdown(source)
    const doc=m.prepareEditorDocument({type:'doc',content:[{type:'paragraph',content:[{type:'text',text:String.raw`旧公式 (\frac34)`}]}]},'')
    const display=m.prepareEditorDocument({type:'doc',content:['[',String.raw`p^2=\frac9{16}`,']'].map(text=>({type:'paragraph',content:[{type:'text',text}]}))},'')
    return {count:box.querySelectorAll('.katex').length,errors:box.querySelectorAll('.katex-error').length,
      oldType:doc.content[0].content[1]?.type,displayType:display.content[0].content[0].type,displayBlockCount:display.content.length,normal:m.normalizeMathSource(source)}
  })
  assert.equal(math.count,4);assert.equal(math.errors,0);assert.equal(math.oldType,'mathInline')
  assert.equal(math.displayType,'mathInline');assert.equal(math.displayBlockCount,1)
  await page.locator('.concurrency-edit .el-checkbox').click()
  await page.getByRole('button',{name:'应用设置',exact:true}).click()
  await page.waitForFunction(()=>document.querySelector('.concurrency-current').textContent.includes('无本地上限'))
  assert.equal(limit,0)
  await page.screenshot({path:path.join(out,'tasks.png')})
  await page.getByRole('button',{name:'新建录入',exact:true}).first().click()
  await page.locator('.answer-file-drop').evaluate(el=>{
    const dt=new DataTransfer();dt.items.add(new File(['%PDF test'],'独立答案.pdf',{type:'application/pdf'}))
    el.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:dt}))
  })
  assert.equal(await page.locator('.selected-files').filter({hasText:'独立答案.pdf'}).count(),1)
  assert.equal(await page.locator('.selected-files').count(),1)
  await page.screenshot({path:path.join(out,'answer-upload.png')})
  await page.getByRole('button',{name:'取消',exact:true}).click()
  await page.locator('tr').filter({hasText:failure.title}).getByRole('button',{name:'查看进度'}).click()
  await page.waitForSelector('.failure-details')
  assert.match(await page.locator('.failure-details').innerText(),/低价渠道/)
  assert.match(await page.locator('.failure-details').innerText(),/HTTP 524/)
  await page.screenshot({path:path.join(out,'failure.png')})
  await page.getByRole('button',{name:'全部任务',exact:true}).click()
  await page.locator('tr').filter({hasText:task.title}).getByRole('button',{name:'对照审核'}).click()
  const stem=page.getByRole('textbox',{name:'题干编辑器',exact:true})
  await stem.locator('img[src]').first().waitFor()
  assert.equal(await stem.locator('img[src]').count(),1)
  assert.ok(await stem.locator('img[src]').first().evaluate(img=>img.complete&&img.naturalWidth>0))
  await page.screenshot({path:path.join(out,'recovered-image.png')})
  await stem.click()
  await stem.evaluate(el=>{
    const bytes=Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6C2kAAAAASUVORK5CYII='),c=>c.charCodeAt(0))
    const dt=new DataTransfer();dt.items.add(new File([bytes],'截图.png',{type:'image/png'}))
    el.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:dt}))
  })
  await page.waitForFunction(()=>document.querySelectorAll('[aria-label="题干编辑器"] img[src]').length===2)
  assert.equal(uploadCount,1)
  await page.getByRole('button',{name:'保存草稿',exact:true}).click()
  assert.ok(draft.questions[0].stem.includes('clipboard.png'))
  assert.ok(JSON.stringify(draft.questions[0].editor_documents.stem).includes('clipboard.png'))
  await page.getByRole('button',{name:'答案与解析',exact:true}).click()
  await page.getByRole('textbox',{name:'答案编辑器',exact:true}).locator('.katex').first().waitFor()
  assert.equal(await page.getByRole('textbox',{name:'答案编辑器',exact:true}).locator('.katex').count(),2)
  assert.equal(await page.getByRole('textbox',{name:'解析编辑器',exact:true}).locator('.katex').count(),1)
  assert.equal(await page.locator('.katex-error').count(),0)
  await page.screenshot({path:path.join(out,'answer-math.png')})
  await page.setViewportSize({width:390,height:844})
  await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true})
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
  assert.deepEqual(errors,[])
  console.log(JSON.stringify({passed:true,mathCount:math.count,uploadCount,revision,errors,screenshots:out}))
}finally{await browser.close()}
