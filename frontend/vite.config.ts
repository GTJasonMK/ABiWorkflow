import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendHost = process.env.VITE_BACKEND_HOST || '127.0.0.1'
const backendPort = process.env.VITE_BACKEND_PORT || '8000'
const backendHttpTarget = `http://${backendHost}:${backendPort}`

const VENDOR_GROUPS: Record<string, string[]> = {
  'vendor-react': ['react', 'react-dom', 'scheduler'],
  'vendor-router': ['react-router', 'react-router-dom'],
  'vendor-dnd': ['@dnd-kit/core', '@dnd-kit/sortable', '@dnd-kit/utilities'],
}

const INLINE_VENDOR_PACKAGES = new Set([
  'cookie',
  'dayjs',
  'json2mq',
  'set-cookie-parser',
  'string-convert',
])

function readPackageName(id: string): string | null {
  const normalized = id.replace(/\\/g, '/')
  const packagePath = normalized.split('/node_modules/')[1]
  if (!packagePath) return null

  const segments = packagePath.split('/')
  if (segments[0]?.startsWith('@')) {
    return segments[1] ? `${segments[0]}/${segments[1]}` : null
  }

  return segments[0] ?? null
}

function resolveGroupedChunk(packageName: string): string | null {
  for (const [chunkName, packages] of Object.entries(VENDOR_GROUPS)) {
    if (packages.includes(packageName)) {
      return chunkName
    }
  }
  return null
}

function manualChunks(id: string): string | undefined {
  if (!id.includes('node_modules')) return undefined

  const packageName = readPackageName(id)
  if (!packageName) return 'vendor-misc'
  if (INLINE_VENDOR_PACKAGES.has(packageName)) return undefined

  const groupedChunk = resolveGroupedChunk(packageName)
  if (groupedChunk) {
    return groupedChunk
  }

  if (packageName === 'antd') {
    return 'vendor-antd'
  }

  return `vendor-${packageName.replace(/^@/, '').replace(/\//g, '-')}`
}

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backendHttpTarget, changeOrigin: true },
      '/ws': { target: backendHttpTarget, ws: true },
      '/media': { target: backendHttpTarget, changeOrigin: true },
    },
  },
})
