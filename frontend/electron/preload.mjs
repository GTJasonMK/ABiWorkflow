import { contextBridge, ipcRenderer } from 'electron'

function trimTrailingSlash(value) {
  return value.replace(/\/+$/, '')
}

const apiBaseUrl = trimTrailingSlash(
  process.env.ELECTRON_API_BASE_URL || 'http://127.0.0.1:8000/api',
)
const wsBaseUrl = trimTrailingSlash(
  process.env.ELECTRON_WS_BASE_URL || 'ws://127.0.0.1:8000/ws',
)

contextBridge.exposeInMainWorld('__ABI_RUNTIME__', {
  apiBaseUrl,
  wsBaseUrl,
})

contextBridge.exposeInMainWorld('__ABI_DESKTOP__', {
  async pickDirectory(options = {}) {
    return ipcRenderer.invoke('abi:pick-directory', options)
  },
  async saveUrlToFile(options = {}) {
    return ipcRenderer.invoke('abi:save-url-to-file', options)
  },
})
