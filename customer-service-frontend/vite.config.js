import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      // 教育业务数据服务（edu-data）
      '/api/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // 智能客服后端
      '/api': {
        target: 'http://127.0.0.1:18082',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:18082',
        changeOrigin: true,
        ws: true,
      },
      '/health': {
        target: 'http://127.0.0.1:18082',
        changeOrigin: true,
      },
    },
  },
})
