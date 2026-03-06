import { getApiBaseUrl, getRuntimeConfig } from '../runtime'

function parseHttpOrigin(raw: string | null | undefined): string | null {
  const value = (raw ?? '').trim()
  if (!/^https?:\/\//i.test(value)) return null
  try {
    return new URL(value).origin
  } catch {
    return null
  }
}

function getEnvBackendOrigin(): string | null {
  const host = (import.meta.env.VITE_BACKEND_HOST ?? '').trim()
  const port = (import.meta.env.VITE_BACKEND_PORT ?? '').trim()
  if (!host || !port) return null
  return `http://${host}:${port}`
}

export function getBackendOrigin(): string | null {
  // 桌面模式优先使用 preload 注入的运行时 API 基地址（通常是绝对地址）。
  const runtimeOrigin = parseHttpOrigin(getRuntimeConfig().apiBaseUrl)
  if (runtimeOrigin) return runtimeOrigin

  // 用户覆盖或环境变量可能将 API 基地址设置为绝对 URL。
  const apiOrigin = parseHttpOrigin(getApiBaseUrl())
  if (apiOrigin) return apiOrigin

  // 开发模式（Vite）通过环境变量拿后端地址，避免依赖 5173 代理层。
  const envOrigin = getEnvBackendOrigin()
  if (envOrigin) return envOrigin

  if (typeof window !== 'undefined' && /^https?:$/i.test(window.location.protocol)) {
    return window.location.origin
  }
  return null
}

export function resolveBackendUrl(rawUrl: string | null | undefined): string | null {
  const value = (rawUrl ?? '').trim()
  if (!value) return null
  if (/^https?:\/\//i.test(value)) return value
  if (value.startsWith('//')) {
    if (typeof window !== 'undefined' && window.location.protocol) {
      return `${window.location.protocol}${value}`
    }
    return `https:${value}`
  }

  const origin = getBackendOrigin()
  if (!origin) return value
  if (value.startsWith('/')) return `${origin}${value}`
  return `${origin}/${value.replace(/^\/+/, '')}`
}
