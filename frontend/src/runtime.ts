export interface AbiRuntimeConfig {
  apiBaseUrl?: string
  wsBaseUrl?: string
}

const API_BASE_OVERRIDE_KEY = 'abi_api_base_url_override'

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function normalizeWsBaseUrl(value: string): string {
  let normalized = value.trim()
  if (normalized.startsWith('http://')) {
    normalized = `ws://${normalized.slice('http://'.length)}`
  } else if (normalized.startsWith('https://')) {
    normalized = `wss://${normalized.slice('https://'.length)}`
  }
  normalized = trimTrailingSlash(normalized)
  if (!normalized.endsWith('/ws')) {
    normalized = `${normalized}/ws`
  }
  return normalized
}

function deriveWsBaseFromApiBase(rawApiBase: string): string | null {
  const apiBase = rawApiBase.trim()
  if (!apiBase) return null
  if (!apiBase.startsWith('http://') && !apiBase.startsWith('https://')) {
    return null
  }

  let wsBase = apiBase
  if (wsBase.endsWith('/api')) {
    wsBase = `${wsBase.slice(0, -'/api'.length)}/ws`
  } else {
    wsBase = `${trimTrailingSlash(wsBase)}/ws`
  }
  return normalizeWsBaseUrl(wsBase)
}

export function getRuntimeConfig(): AbiRuntimeConfig {
  if (typeof window === 'undefined') return {}
  return window.__ABI_RUNTIME__ ?? {}
}

function readStorageValue(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function getApiBaseUrlOverride(): string | null {
  const raw = readStorageValue(API_BASE_OVERRIDE_KEY)?.trim()
  return raw ? trimTrailingSlash(raw) : null
}

export function setApiBaseUrlOverride(value: string | null): void {
  if (typeof window === 'undefined') return
  try {
    const normalized = value?.trim()
    if (!normalized) {
      window.localStorage.removeItem(API_BASE_OVERRIDE_KEY)
      return
    }
    window.localStorage.setItem(API_BASE_OVERRIDE_KEY, trimTrailingSlash(normalized))
  } catch {
    // ignore localStorage errors
  }
}

export function getApiBaseUrl(): string {
  const runtimeBase = getRuntimeConfig().apiBaseUrl?.trim()
  const overrideBase = getApiBaseUrlOverride()
  const envBase = import.meta.env.VITE_API_BASE_URL?.trim()
  return trimTrailingSlash(runtimeBase || overrideBase || envBase || '/api')
}

export function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${getApiBaseUrl()}${normalizedPath}`
}

export function getWsBaseUrl(): string | null {
  const runtimeWs = getRuntimeConfig().wsBaseUrl?.trim()
  if (runtimeWs) return normalizeWsBaseUrl(runtimeWs)

  // 若用户动态覆盖了 API 地址（例如直连后端），优先从 API 基地址推导 WS 地址。
  const runtimeApi = getRuntimeConfig().apiBaseUrl?.trim()
  const overrideApi = getApiBaseUrlOverride()
  const envApi = import.meta.env.VITE_API_BASE_URL?.trim()
  return deriveWsBaseFromApiBase(runtimeApi || overrideApi || envApi || '')
}
