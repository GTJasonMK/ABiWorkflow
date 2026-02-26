interface SupportCachePayload {
  supported: boolean
  updatedAt: number
}

function readSupportFromStorage(storageKey: string, ttlMs: number): boolean | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<SupportCachePayload>
    if (typeof parsed.supported !== 'boolean' || typeof parsed.updatedAt !== 'number') {
      return null
    }
    if ((Date.now() - parsed.updatedAt) > ttlMs) {
      return null
    }
    return parsed.supported
  } catch {
    return null
  }
}

function writeSupportToStorage(storageKey: string, supported: boolean): void {
  if (typeof window === 'undefined') return
  try {
    const payload: SupportCachePayload = {
      supported,
      updatedAt: Date.now(),
    }
    window.localStorage.setItem(storageKey, JSON.stringify(payload))
  } catch {
    // ignore localStorage errors
  }
}

export interface EndpointSupportStore {
  get: () => boolean | null
  set: (supported: boolean) => void
}

export function createEndpointSupportStore(storageKey: string, ttlMs: number): EndpointSupportStore {
  let support = readSupportFromStorage(storageKey, ttlMs)
  return {
    get: () => support,
    set: (supported: boolean) => {
      support = supported
      writeSupportToStorage(storageKey, supported)
    },
  }
}

export function isRouteMissingResponse(payload: unknown): boolean {
  if (typeof payload === 'string') {
    const normalized = payload.trim().toLowerCase()
    return normalized.includes('not found') || normalized.includes('<!doctype html') || normalized.includes('<html')
  }
  if (!payload || typeof payload !== 'object') return false
  if (!('detail' in payload)) return false
  const detail = (payload as { detail?: unknown }).detail
  return typeof detail === 'string' && detail.trim().toLowerCase() === 'not found'
}
