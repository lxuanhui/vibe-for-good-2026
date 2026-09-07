import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Proxies /api/* to the local Flask app so the console can call
    // fetch('/api/...') with no CORS setup in development. In deployed
    // environments the same paths are served by the Lambda behind API
    // Gateway -- see infra/.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: true,
      },
    },
  },
})
