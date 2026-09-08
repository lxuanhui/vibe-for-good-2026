import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // maplibre-gl loads its tile/style processing code via `new Worker(new
  // URL(...))`. Vite's esbuild dep pre-bundler doesn't emit the resulting
  // worker chunk correctly (the request for maplibre-gl-worker.mjs hangs
  // forever), which silently blocks all map rendering with no console error.
  // Excluding it from pre-bundling lets the browser load it as native ESM,
  // where the worker URL resolves correctly.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
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
