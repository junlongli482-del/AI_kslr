// Restore smoke check for the v1 workbench. Read-only: it opens the list and one review page.
import fs from 'node:fs/promises'
import path from 'node:path'
import { projectRoot, browserOptions } from './browser-runtime.mjs'
import { chromium } from '../apps/web/node_modules/@playwright/test/index.mjs'

const web = `http://127.0.0.1:${process.env.WEB_PORT || 1001}`
const api = `http://127.0.0.1:${process.env.API_PORT || 1002}`
const out = path.join(projectRoot, 'data/logs')
await fs.mkdir(out, { recursive: true })

const tasks = await (await fetch(`${api}/api/quick-entry/tasks`)).json()
const candidate = tasks.find(t => t.status === 'committed') || tasks.find(t => t.status === 'ready')
if (!candidate) throw new Error('没有可打开的任务')

const browser = await chromium.launch(browserOptions(chromium))
const page = await browser.newPage({ viewport: { width: 1536, height: 1000 } })
const errors = []
page.on('pageerror', e => errors.push(`pageerror: ${e.message}`))
page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`) })
page.on('response', r => { if (r.status() >= 400) errors.push(`http ${r.status()} ${r.url()}`) })
page.on('requestfailed', r => errors.push(`requestfailed ${r.url()} ${r.failure()?.errorText}`))

await page.goto(web + '/', { waitUntil: 'networkidle' })
await page.screenshot({ path: path.join(out, 'restore-home.png'), fullPage: true })
const rows = await page.locator('tbody tr').count()
const title = await page.locator('tbody tr').first().innerText().catch(() => '')

await page.locator('tbody tr').filter({ hasText: candidate.title }).first()
  .getByRole('button', { name: '对照审核' }).click()
await page.waitForSelector('.rich-editor .tiptap', { timeout: 30000 })
await page.waitForTimeout(1500)
await page.screenshot({ path: path.join(out, 'restore-review.png'), fullPage: true })
const navCount = await page.locator('.question-nav-list>button').count()
const editorText = (await page.locator('.rich-editor .tiptap').first().innerText()).slice(0, 80)

await browser.close()
console.log(JSON.stringify({
  web, api, taskCount: tasks.length, rows, firstRow: title.slice(0, 60),
  opened: { id: candidate.id, title: candidate.title, status: candidate.status },
  questionNavCount: navCount, editorText, errors
}, null, 2))
