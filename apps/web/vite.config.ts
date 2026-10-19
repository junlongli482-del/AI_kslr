import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const port = Number(process.env.WEB_PORT || 5173)
const api = process.env.API_TARGET || `http://127.0.0.1:${process.env.API_PORT || 8090}`

export default defineConfig({
  plugins: [vue({ template: { compilerOptions: { isCustomElement: tag => tag === 'math-field' } } })],
  server: { port, strictPort: true, proxy: { '/api': api } }
})
