import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue({ template: { compilerOptions: { isCustomElement: tag => tag === 'math-field' } } })], server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8090' } } })
