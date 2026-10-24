import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const port = Number(process.env.WEB_PORT || 5173)
const api = process.env.API_TARGET || `http://127.0.0.1:${process.env.API_PORT || 8090}`
const ai = process.env.AI_TARGET || `http://127.0.0.1:${process.env.AI_PORT || 1003}`

export default defineConfig({
  plugins: [vue({ template: { compilerOptions: { isCustomElement: tag => tag === 'math-field' } } })],
  server: {
    port,
    strictPort: true,
    // 允许通过 cpolar 等隧道域名访问（免费版域名会变，用通配）。
    allowedHosts: ['.cpolar.cn', '.cpolar.top'],
    // Editors that save atomically create short-lived tmpdirs; watching them can crash Vite with EBUSY.
    watch: { ignored: ['**/*.tmpdir/**', '**/*.tmp'] },
    proxy: { '/api': api, '/prompt-api': { target: ai, rewrite: (path:string)=>path.replace(/^\/prompt-api/, '') } }
  }
})
