import {projectRoot,browserOptions} from './browser-runtime.mjs'
import { chromium } from '../apps/web/node_modules/@playwright/test/index.mjs'
import fs from 'node:fs/promises'
import path from 'node:path'
const root=projectRoot
const browser=await chromium.launch(browserOptions(chromium))
const page=await browser.newPage({viewport:{width:1536,height:1000}})
const errors=[]
page.on('pageerror',e=>errors.push(e.message))
const out=path.join(root,'docs/handoff/quick-entry/screenshots')
await fs.mkdir(out,{recursive:true})
await page.goto('http://127.0.0.1:5173/',{waitUntil:'networkidle'})
await page.screenshot({path:path.join(out,'tasks-desktop.png'),fullPage:true})
await page.getByRole('button',{name:'新建录入',exact:true}).first().click()
await page.waitForTimeout(400)
await page.screenshot({path:path.join(out,'upload-desktop.png')})
await page.getByRole('button',{name:'取消',exact:true}).click()
const demo=JSON.parse(await fs.readFile(path.join(root,'data/demo-task.json'),'utf8'))
const task=await (await fetch('http://127.0.0.1:8090/api/quick-entry/tasks/'+demo.id)).json()
if(['ready','committed'].includes(task.status)){
  const row=page.locator('tr').filter({hasText:task.title}).first()
  await row.getByRole('button',{name:'对照审核'}).click()
  await page.waitForSelector('.rich-editor .tiptap')
  await page.waitForTimeout(1000)
  await page.screenshot({path:path.join(out,'review-desktop.png')})
  await page.getByRole('button',{name:'属性标签',exact:true}).click()
  await page.screenshot({path:path.join(out,'attributes-desktop.png')})
  await page.locator('.question-nav-list>button').nth(4).click()
  await page.screenshot({path:path.join(out,'recovered-diagram.png')})
  await page.locator('.question-nav-list>button').nth(23).click()
  await page.screenshot({path:path.join(out,'graphic-options.png')})
  await page.locator('.question-nav-list>button').nth(29).click()
  await page.screenshot({path:path.join(out,'inline-diagrams.png')})
}
await page.setViewportSize({width:390,height:844})
await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true})
console.log(JSON.stringify({errors,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),taskStatus:task.status}))
await browser.close()
