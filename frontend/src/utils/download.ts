import { resolveBackendUrl } from './backendUrl'

interface SaveUrlWithPickerOptions {
  url: string
  title?: string
  defaultPath?: string
  defaultFileName?: string
}

interface SaveUrlWithPickerResult {
  mode: 'desktop' | 'browser'
  canceled: boolean
  filePath: string | null
}

function resolveToAbsoluteHttpUrl(rawUrl: string): string {
  const url = rawUrl.trim()
  if (!url) return url
  return resolveBackendUrl(url) ?? url
}

function triggerBrowserDownload(url: string, defaultFileName?: string): void {
  const link = document.createElement('a')
  link.href = url
  link.rel = 'noreferrer'
  link.target = '_blank'
  if (defaultFileName?.trim()) {
    link.download = defaultFileName.trim()
  }
  document.body.appendChild(link)
  link.click()
  link.remove()
}

export async function saveUrlWithPicker(options: SaveUrlWithPickerOptions): Promise<SaveUrlWithPickerResult> {
  const resolvedUrl = resolveToAbsoluteHttpUrl(options.url)
  const desktopBridge = window.__ABI_DESKTOP__?.saveUrlToFile
  if (!desktopBridge) {
    triggerBrowserDownload(resolvedUrl, options.defaultFileName)
    return { mode: 'browser', canceled: false, filePath: null }
  }

  const result = await desktopBridge({
    url: resolvedUrl,
    title: options.title,
    defaultPath: options.defaultPath,
    defaultFileName: options.defaultFileName,
  })
  return {
    mode: 'desktop',
    canceled: result.canceled,
    filePath: result.filePath,
  }
}
