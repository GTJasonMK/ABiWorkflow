import { create } from 'zustand'
import { getAssetHubOverview, type AssetScope } from '../api/assetHub'
import type { AssetHubOverview } from '../types/assetHub'
import { getApiErrorMessage } from '../utils/error'

interface LoadOptions {
  force?: boolean
  projectId?: string | null
  scope?: AssetScope
}

interface AssetHubState {
  overview: AssetHubOverview | null
  loading: boolean
  error: string | null
  loadedAt: number | null
  loadOverview: (options?: LoadOptions) => Promise<AssetHubOverview>
  invalidate: () => void
}

const EMPTY_OVERVIEW: AssetHubOverview = {
  folders: [],
  characters: [],
  locations: [],
  voices: [],
}

let inflight: Promise<AssetHubOverview> | null = null
let inflightKey: string | null = null
const cacheByKey = new Map<string, AssetHubOverview>()

function toCacheKey(options?: LoadOptions): string {
  const scope = options?.scope ?? 'all'
  const projectId = options?.projectId ?? ''
  return `${scope}::${projectId}`
}

export const useAssetHubStore = create<AssetHubState>((set) => ({
  overview: null,
  loading: false,
  error: null,
  loadedAt: null,
  loadOverview: async (options?: LoadOptions) => {
    const force = Boolean(options?.force)
    const cacheKey = toCacheKey(options)
    const cached = cacheByKey.get(cacheKey)
    if (!force && cached) {
      set({ overview: cached, error: null })
      return cached
    }
    if (inflight && inflightKey === cacheKey) {
      return inflight
    }

    set({ loading: true, error: null })
    inflightKey = cacheKey
    inflight = (async () => {
      try {
        const payload = await getAssetHubOverview({
          projectId: options?.projectId,
          scope: options?.scope ?? 'all',
        })
        const normalized = payload ?? EMPTY_OVERVIEW
        cacheByKey.set(cacheKey, normalized)
        set({
          overview: normalized,
          loading: false,
          error: null,
          loadedAt: Date.now(),
        })
        return normalized
      } catch (error) {
        const errorMessage = getApiErrorMessage(error, '获取全局资产失败')
        set({
          loading: false,
          error: errorMessage,
        })
        throw error
      } finally {
        inflight = null
        inflightKey = null
      }
    })()

    return inflight
  },
  invalidate: () => {
    cacheByKey.clear()
    inflightKey = null
    set({
      overview: null,
      loadedAt: null,
    })
  },
}))
