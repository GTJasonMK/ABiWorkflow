/// <reference types="vite/client" />

interface Window {
  __ABI_RUNTIME__?: {
    apiBaseUrl?: string
    wsBaseUrl?: string
  }
  __ABI_DESKTOP__?: {
    pickDirectory?: (options?: {
      title?: string
      defaultPath?: string
    }) => Promise<string | null>
  }
}

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_PROBE_OPTIONAL_ENDPOINTS?: string
}
