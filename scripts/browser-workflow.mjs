import {projectRoot,browserOptions} from './browser-runtime.mjs'
import {chromium,expect} from '../apps/web/node_modules/@playwright/test/index.mjs'
import fs from 'node:fs/promises'
import path from 'node:path'
const root=projectRoot,base='http://127.0.0.1:8090/api'
const {id}=JSON.parse(await fs.readFile(path.join(root,'data/demo-task.json'),'utf8'))
async function api(url,method='GET',body){const res=await fetch(base+url,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(!res.ok)throw Error(`${method} ${url}: ${res.status} ${await res.text()}`);return res.json()}
const endpoint=`/quick-entry/tasks/${id}`
const baseline=await api(endpoint+'/review')
await fs.writeFile(path.join(root,'data/browser-baseline.json'),JSON.stringify(baseline))
const browser=await chromium.launch(browserOptions(chromium))
const page=await browser.newPage({viewport:{width:1536,height:1000}})
const errors=[],checks=[]
page.on('pageerror',e=>errors.push(e.message))
async function open(){await page.goto('http://127.0.0.1:5173',{waitUntil:'networkidle'});const task=await api(endpoint);await page.locator('tr').filter({hasText:task.title}).first().getByRole('button',{name:'对照审核'}).click();await page.locator('[aria-label="题干编辑器"]').waitFor()}
async function saved(predicate){await expect.poll(async()=>{const d=await api(endpoint+'/review');return predicate(d.result)},{timeout:18000}).toBe(true)}
try{
  await open()
  const first=baseline.result.questions[0]
  await page.locator('.editable-formula').first().click()
  const dialog=page.getByRole('dialog',{name:'编辑公式',exact:true})
  await expect(dialog.locator('math-field')).toBeVisible()
  await dialog.locator('math-field').evaluate(el=>{el.value='x^2+1';el.dispatchEvent(new InputEvent('input',{bubbles:true}))})
  await dialog.getByRole('button',{name:'保存公式',exact:true}).click()
  await saved(r=>r.questions[0].stem.includes('$x^2+1$'))
  checks.push('MathLive visual edit persists LaTeX')
  await page.locator('.editable-formula').first().click()
  await dialog.getByRole('button',{name:'LaTeX 源码',exact:true}).click()
  await dialog.locator('textarea').fill('x^2+2')
  await dialog.getByRole('button',{name:'保存公式',exact:true}).click()
  await saved(r=>r.questions[0].stem.includes('$x^2+2$'))
  checks.push('LaTeX source edit persists')
  const editor=page.locator('[aria-label="题干编辑器"]')
  await editor.click();await page.keyboard.press('Control+End');await page.keyboard.insertText('【交互测试标记】')
  await saved(r=>r.questions[0].stem.includes('【交互测试标记】'))
  await page.reload({waitUntil:'networkidle'});await open()
  await expect(page.locator('[aria-label="题干编辑器"]')).toContainText('【交互测试标记】')
  checks.push('Rich edit autosaves and survives reload')
  const rect=page.locator('.source-viewer svg g.selected>rect').first()
  const box=await rect.boundingBox();if(!box)throw Error('Region missing')
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+5,box.y+box.height/2+5,{steps:5});await page.mouse.up()
  await saved(r=>Math.abs(r.questions[0].regions[0].bbox[0]-first.regions[0].bbox[0])>.0001)
  await saved(r=>r.questions[0].regions[0].crop_url.includes('&v='))
  checks.push('Source region drag persists and refreshes crop')
  await page.getByRole('button',{name:'确认并继续',exact:true}).click()
  await saved(r=>r.questions[0].review_status==='reviewed')
  checks.push('Confirm advances and saves review state')
  await page.getByRole('button',{name:'规则检查',exact:true}).click()
  await expect(page.getByRole('dialog',{name:'规则检查',exact:true})).toBeVisible()
  checks.push('Validation dialog opens')
}finally{
  await browser.close()
  const current=await api(endpoint+'/review')
  await api(endpoint+'/review','PUT',{expected_revision:current.revision,result:baseline.result})
}
if(errors.length)throw Error(JSON.stringify(errors))
await fs.writeFile(path.join(root,'data/browser-workflow.json'),JSON.stringify({checks,errors,restored:true},null,2))
console.log(JSON.stringify({checks,errors,restored:true}))
