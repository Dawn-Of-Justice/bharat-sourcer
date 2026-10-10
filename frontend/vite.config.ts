import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // Vite reads this only on the development server; the browser never receives the team key.
  const env = loadEnv(mode, process.cwd(), '')
  const backend = env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
  const integrationKey = env.INTEGRATION_KEY
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: backend,
          changeOrigin: true,
          rewrite: path =>
            path === '/api/healthz'
              ? backend.startsWith('https:')
                ? '/health'
                : '/healthz'
              : path.replace(/^\/api/, ''),
          configure: proxy =>
            proxy.on('proxyReq', request => {
              if (integrationKey) request.setHeader('X-Integration-Key', integrationKey)
            }),
        },
      },
    },
  }
})
