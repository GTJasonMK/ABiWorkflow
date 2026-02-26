import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendHost = process.env.VITE_BACKEND_HOST || '127.0.0.1'
const backendPort = process.env.VITE_BACKEND_PORT || '8000'
const backendHttpTarget = `http://${backendHost}:${backendPort}`
const backendWsTarget = `ws://${backendHost}:${backendPort}`

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backendHttpTarget, changeOrigin: true },
      '/ws': { target: backendWsTarget, ws: true },
      '/media': { target: backendHttpTarget, changeOrigin: true },
    },
  },
})
