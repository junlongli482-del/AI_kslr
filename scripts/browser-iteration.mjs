import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import {chromium} from '../apps/web/node_modules/@playwright/test/index.mjs'
import {projectRoot,browserOptions} from './browser-runtime.mjs'

const fixtures={}
for(const name of ['physics','captions','civics'])fixtures[name]=JSON.parse(await fs.readFile(path.join(projectRoot,`data/iteration-fixtures/${name}.json`),'utf8'))
const browser=await chromium.launch(browserOptions(chromium))
const page=await browser.newPage({viewport:{width:1600,height:1050}})
const errors=[];page.on('pageerror',e=>errors.push(e.message))
let draft=structuredClone(fixtures.physics),rev=0
const task={id:'isolated-iteration',title:'隔离验收：物理图片选项与图注',status:'ready',stage:'待审核',mode:'textbook',created_at:'2026-10-15T17:00:00',message:''}
const out=path.join(projectRoot,'docs/handoff/quick-entry/screenshots/iteration-20261015')
await fs.mkdir(out,{recursive:true})
await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),p=url.pathname
  const json=data=>route.fulfill({json:data})
  if(p==='/api/assets')return route.continue()
  if(p==='/api/quick-entry/tasks')return json([task])
  if(p.endsWith('/settings/concurrency'))return json({max_concurrency:0,running:0,queued:0,unlimited:true})
  if(p.endsWith('/comparison'))return json({candidates:[]})
  if(p.endsWith('/validate'))return json({valid:true,issues:[],result:request.postDataJSON()})
  if(p.endsWith('/review')){
    if(request.method()==='PUT'){draft=request.postDataJSON().result;return json({revision:++rev,saved:true})}
    return json({result:draft,revision:rev})
  }
  if(p.endsWith('/commit'))return route.fulfill({status:422,json:{message:'存在需要修复的内容',code:'VALIDATION_FAILED',issues:[{question_id:draft.questions[0].id,severity:'error',message:'测试：失效图片',fields:['stem','editor_documents'],hint:'重新粘贴或删除此失效图片'}]}})
  if(p.endsWith('/isolated-iteration'))return json(task)
  return route.fulfill({status:404,json:{message:'隔离测试未定义的接口'}})
})
async function open(){await page.goto('http://127.0.0.1:5173/',{waitUntil:'networkidle'});await page.getByRole('button',{name:'对照审核',exact:true}).click();await page.locator('.review-workbench').waitFor()}
async function pick(n){await page.locator('.question-nav-list button').filter({has:page.locator('.q-number',{hasText:new RegExp('^'+n+'$')})}).click()}

try{
  await open()
  // Use source ids rather than assumptions about navigator text markup.
  const nav=await page.locator('.question-navigator').innerText();console.log('NAV',nav.slice(0,350))
  await pick(5)
  const stem=page.getByRole('textbox',{name:'题干编辑器',exact:true})
  await stem.locator('img[src]').first().waitFor()
  const image=await stem.locator('img[src]').first().evaluate(img=>({width:img.getBoundingClientRect().width,container:img.closest('.question-prose').getBoundingClientRect().width,natural:img.naturalWidth}))
  assert.ok(image.natural>0);assert.ok(image.width/image.container<.35,JSON.stringify(image))
  await page.screenshot({path:path.join(out,'physics-image.png')})
  await stem.locator('.image-figure').first().click()
  const slider=page.getByRole('slider',{name:'图片宽度百分比',exact:true})
  await slider.waitFor();await slider.evaluate(el=>{el.value='40';el.dispatchEvent(new Event('input',{bubbles:true}))});await page.waitForTimeout(200);console.log('SLIDER_AFTER',await slider.inputValue(),await stem.locator('.image-figure').first().getAttribute('style'))
  await page.getByRole('button',{name:'保存草稿',exact:true}).click()
  const q5=draft.questions.find(q=>q.number==='5');
  assert.ok(Object.values(q5.image_layout).some(m=>m.manual_width_pct===40),JSON.stringify(q5.image_layout))
  const persisted=JSON.stringify(q5.editor_documents.stem);assert.match(persisted,/"manualSize":true/)
  await page.reload({waitUntil:'networkidle'});await page.getByRole('button',{name:'对照审核',exact:true}).click();await pick(5)
  const reopened=await page.getByRole('textbox',{name:'题干编辑器',exact:true}).locator('.image-figure').first().evaluate(el=>el.style.width)
  assert.equal(reopened,'40%')
  await pick(3)
  const optionImages=await page.locator('.option-editor img[src]').evaluateAll(imgs=>imgs.map(img=>({width:img.getBoundingClientRect().width,container:img.closest('.option-editor').getBoundingClientRect().width})))
  assert.equal(optionImages.length,4);assert.ok(optionImages.every(i=>i.width/i.container>.22),JSON.stringify(optionImages))
  await page.screenshot({path:path.join(out,'option-images.png')})
  // Error text must open actionable issue list rather than dump JSON in a toast.
  await page.getByRole('button',{name:'审核入库',exact:true}).click();await page.getByRole('button',{name:'保存到资源库',exact:true}).click()
  await page.locator('.validation-item').waitFor();assert.match(await page.locator('.validation-item').innerText(),/阻止入库/);assert.match(await page.locator('.validation-item').innerText(),/题干/)
  await page.screenshot({path:path.join(out,'validation-errors.png')})
  draft=structuredClone(fixtures.captions);await open();await pick(15)
  const caps=page.getByRole('textbox',{name:'题干编辑器',exact:true}).locator('.image-caption')
  assert.deepEqual(await caps.allTextContents(),['甲','乙','丙'])
  const capImage=page.getByRole('textbox',{name:'题干编辑器',exact:true}).locator('img[src]')
  assert.equal(await capImage.count(),3)
  await page.screenshot({path:path.join(out,'captions.png')})
  await page.setViewportSize({width:390,height:844})
  await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true})
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
  assert.deepEqual(errors,[])
  console.log(JSON.stringify({passed:true,image,optionImages,reopened,errors,screenshots:out}))
}finally{await browser.close()}
