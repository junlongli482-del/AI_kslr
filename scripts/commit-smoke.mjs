import {projectRoot,browserOptions} from './browser-runtime.mjs'
import {chromium,expect} from '../apps/web/node_modules/@playwright/test/index.mjs'
import fs from 'node:fs/promises'
import path from 'node:path'
const root=projectRoot,base='http://127.0.0.1:8090/api'
const {id}=JSON.parse(await fs.readFile(path.join(root,'data/demo-task.json'),'utf8'))
async function api(url,method='GET',body){const res=await fetch(base+url,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(!res.ok)throw Error(await res.text());return res.json()}
const browser=await chromium.launch(browserOptions(chromium))
const page=await browser.newPage({viewport:{width:1536,height:1000}}),errors=[]
page.on('pageerror',e=>errors.push(e.message))
try{
 await page.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'})
 const task=await api('/quick-entry/tasks/'+id)
 await page.locator('tr').filter({hasText:task.title}).first().getByRole('button',{name:'对照审核'}).click()
 await page.getByRole('button',{name:'审核入库',exact:true}).click()
 await page.getByRole('button',{name:'保存到资源库',exact:true}).click()
 await expect.poll(async()=>(await api('/quick-entry/tasks/'+id)).status,{timeout:20000}).toBe('committed')
 const questions=(await api('/questionbank/questions')).filter(q=>q.task_id===id)
 const papers=(await api('/paperbank/papers')).filter(p=>p.task_id===id)
 if(questions.length!==46||papers.length!==2)throw Error('Unexpected bank counts')
 if(questions.some(q=>q.status!=='pending'))throw Error('Unreviewed samples must remain pending')
 for(const paper of papers){const detail=await api('/paperbank/papers/'+paper.id);if(detail.questions.length!==23||detail.templates.length!==1||detail.templates[0].scan_capability!=='not_integrated')throw Error('Paper/template relations incorrect')}
 const draft=await api('/quick-entry/tasks/'+id+'/review')
 const again=await api('/quick-entry/tasks/'+id+'/commit','POST',{revision:draft.revision})
 if((await api('/questionbank/questions')).filter(q=>q.task_id===id).length!==46)throw Error('Repeated commit duplicated resources')
 await page.locator('.app-sidebar nav button').nth(1).click()
 await expect(page.locator('.bank-item')).toHaveCount(46)
 await page.screenshot({path:path.join(root,'docs/handoff/quick-entry/screenshots/question-bank.png')})
 await page.locator('.bank-item').first().click()
 await expect(page.getByRole('dialog')).toBeVisible()
 await page.getByRole('button',{name:'关闭',exact:true}).last().click()
 await page.locator('.app-sidebar nav button').nth(2).click()
 await expect(page.locator('.bank-item')).toHaveCount(2)
 await page.locator('.bank-item').first().click()
 await expect(page.locator('.paper-detail-list article')).toHaveCount(23)
 await expect(page.locator('.preview-subquestion').first()).toBeVisible()
  await page.waitForTimeout(400)
 await page.screenshot({path:path.join(root,'docs/handoff/quick-entry/screenshots/paper-bank.png')})
 if(errors.length)throw Error(JSON.stringify(errors))
 const evidence={questions:46,papers:2,templates:2,review_status:'pending',scan_capability:'not_integrated',idempotent:true,errors}
 await fs.writeFile(path.join(root,'data/commit-smoke.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence))
}finally{await browser.close()}
