import {projectRoot,browserOptions} from './browser-runtime.mjs'
import {chromium,expect} from '../apps/web/node_modules/@playwright/test/index.mjs'
import fs from 'node:fs/promises'
import path from 'node:path'
const root=projectRoot,base='http://127.0.0.1:8090/api'
const records=JSON.parse(await fs.readFile(path.join(root,'data/format-smoke.json'),'utf8'))
const {id}=records.find(r=>r.filename.endsWith('.docx'))
async function api(url,method='GET',body){const res=await fetch(base+url,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(!res.ok)throw Error(await res.text());return res.json()}
const endpoint='/quick-entry/tasks/'+id,baseline=await api(endpoint+'/review')
const browser=await chromium.launch(browserOptions(chromium))
const page=await browser.newPage({viewport:{width:1536,height:1000}}),errors=[],checks=[]
page.on('pageerror',e=>errors.push(e.message))
async function saved(fn){await expect.poll(async()=>fn((await api(endpoint+'/review')).result),{timeout:18000}).toBe(true)}
try{
 await page.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'})
 const task=await api(endpoint);await page.locator('tr').filter({hasText:task.title}).getByRole('button',{name:'对照审核'}).click()
 await page.getByRole('button',{name:'答案与解析',exact:true}).click()
 const select=page.locator('.question-detail .el-select').first()
 await select.hover();await select.locator('.el-select__clear').click({force:true})
 await saved(r=>!r.questions[0].answer_entry_id&&!r.questions[0].answer)
 await select.click()
 const entry=baseline.result.answer_entries.find(e=>e.id===baseline.result.questions[0].answer_entry_id)
 await page.locator('.el-select-dropdown__item').filter({hasText:entry.group+' · 第'+entry.number+'题'}).click()
 await saved(r=>r.questions[0].answer_entry_id===entry.id&&r.questions[0].answer===entry.answer)
 checks.push('Answer unlink/relink keeps one-to-one metadata and content')
 await page.getByRole('button',{name:'题目内容',exact:true}).click()
 await page.getByRole('button',{name:'补框',exact:true}).click()
 const svg=await page.locator('.paper-image>svg').boundingBox()
 await page.mouse.move(svg.x+svg.width*.75,svg.y+svg.height*.75);await page.mouse.down();await page.mouse.move(svg.x+svg.width*.9,svg.y+svg.height*.85,{steps:4});await page.mouse.up()
 await saved(r=>r.questions[0].regions.length===baseline.result.questions[0].regions.length+1)
 await page.getByRole('button',{name:'题目操作',exact:true}).click();await page.getByText('拆出最后区域',{exact:true}).click()
 await saved(r=>r.questions.length===3&&!r.questions[1].answer_entry_id&&r.questions[1].regions.length===1)
 checks.push('Split preserves separate region and resets inherited answer match')
 await page.getByRole('button',{name:'题目操作',exact:true}).click();await page.getByText('合并下一题',{exact:true}).click()
 await saved(r=>r.questions.length===2&&r.questions[0].regions.length===baseline.result.questions[0].regions.length+1)
 checks.push('Merge keeps content and multiple regions')
 await page.getByRole('button',{name:'新增漏题',exact:true}).click()
 const editor=page.locator('[aria-label="题干编辑器"]');await editor.fill('人工新增测试题')
 await saved(r=>r.questions.length===3&&r.questions[2].stem==='人工新增测试题')
 await page.getByRole('button',{name:'题目操作',exact:true}).click();await page.getByText('删除误识别题目',{exact:true}).click()
 await page.getByRole('button',{name:'确定',exact:true}).click()
 await saved(r=>r.questions.length===2)
 checks.push('Add and delete question persists')
 await page.getByRole('button',{name:'上移题目',exact:true}).click()
 await saved(r=>r.questions[0].id===baseline.result.questions[1].id)
 checks.push('Reordering persists')
 if(errors.length)throw Error(JSON.stringify(errors))
}finally{
 await browser.close();const current=await api(endpoint+'/review');await api(endpoint+'/review','PUT',{expected_revision:current.revision,result:baseline.result})
}
await fs.writeFile(path.join(root,'data/browser-structure.json'),JSON.stringify({checks,errors,restored:true},null,2));console.log(JSON.stringify({checks,errors,restored:true}))

