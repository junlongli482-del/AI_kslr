import fs from 'node:fs'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
export const projectRoot=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
export function browserOptions(chromium){
  if(process.env.PLAYWRIGHT_CHROMIUM_PATH)return {headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_PATH}
  if(fs.existsSync(chromium.executablePath()))return {headless:true}
  const cache=path.join(process.env.LOCALAPPDATA||'', 'ms-playwright')
  if(fs.existsSync(cache))for(const entry of fs.readdirSync(cache).filter(x=>x.startsWith('chromium-')).sort().reverse()){
    for(const folder of ['chrome-win64','chrome-win']){
      const executablePath=path.join(cache,entry,folder,'chrome.exe')
      if(fs.existsSync(executablePath))return {headless:true,executablePath}
    }
  }
  throw Error('未找到Chromium，请在apps/web执行 pnpm exec playwright install chromium，或设置PLAYWRIGHT_CHROMIUM_PATH。')
}
