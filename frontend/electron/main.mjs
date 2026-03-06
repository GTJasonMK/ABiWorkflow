import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const devServerUrl = process.env.ELECTRON_RENDERER_URL
const isDev = Boolean(devServerUrl)
const electronApiBaseUrl = process.env.ELECTRON_API_BASE_URL || 'http://127.0.0.1:8000/api'

function sanitizeFileName(value) {
  const normalized = String(value || '')
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, '_')
    .trim()
  return normalized || 'video.mp4'
}

function guessDefaultFileNameFromUrl(url, fallback = 'video.mp4') {
  try {
    const parsed = new URL(url)
    const lastSegment = decodeURIComponent(parsed.pathname.split('/').filter(Boolean).pop() || '')
    if (!lastSegment) return fallback
    const normalized = sanitizeFileName(lastSegment)
    if (normalized.includes('.')) return normalized
    return `${normalized}.mp4`
  } catch {
    return fallback
  }
}

function resolveHttpUrl(rawUrl) {
  const input = String(rawUrl || '').trim()
  if (!input) return ''
  if (/^https?:\/\//i.test(input)) return input

  try {
    return new URL(input, electronApiBaseUrl).toString()
  } catch {
    return input
  }
}

ipcMain.handle('abi:pick-directory', async (event, options = {}) => {
  const senderWindow = BrowserWindow.fromWebContents(event.sender) ?? BrowserWindow.getFocusedWindow() ?? undefined
  const title = typeof options?.title === 'string' && options.title.trim()
    ? options.title.trim()
    : '选择目录'
  const defaultPath = typeof options?.defaultPath === 'string' && options.defaultPath.trim()
    ? options.defaultPath.trim()
    : undefined

  const result = await dialog.showOpenDialog(senderWindow, {
    title,
    defaultPath,
    properties: ['openDirectory', 'createDirectory', 'dontAddToRecent'],
  })

  if (result.canceled || result.filePaths.length === 0) {
    return null
  }
  return result.filePaths[0]
})

ipcMain.handle('abi:save-url-to-file', async (event, options = {}) => {
  const senderWindow = BrowserWindow.fromWebContents(event.sender) ?? BrowserWindow.getFocusedWindow() ?? undefined
  const targetUrl = resolveHttpUrl(options?.url)
  if (!targetUrl) {
    throw new Error('下载地址不能为空')
  }
  if (!/^https?:\/\//i.test(targetUrl)) {
    throw new Error('下载地址必须为 http(s) URL')
  }

  const title = typeof options?.title === 'string' && options.title.trim()
    ? options.title.trim()
    : '选择导出文件'
  const preferredName = typeof options?.defaultFileName === 'string' && options.defaultFileName.trim()
    ? options.defaultFileName.trim()
    : guessDefaultFileNameFromUrl(targetUrl)
  const defaultDirectory = typeof options?.defaultPath === 'string' && options.defaultPath.trim()
    ? options.defaultPath.trim()
    : app.getPath('downloads')
  const defaultPath = path.join(defaultDirectory, sanitizeFileName(preferredName))

  const saveDialogResult = await dialog.showSaveDialog(senderWindow, {
    title,
    defaultPath,
    buttonLabel: '导出',
    properties: ['createDirectory', 'showOverwriteConfirmation', 'dontAddToRecent'],
    filters: [
      { name: '视频文件', extensions: ['mp4', 'mov', 'mkv', 'webm'] },
      { name: '所有文件', extensions: ['*'] },
    ],
  })
  if (saveDialogResult.canceled || !saveDialogResult.filePath) {
    return { canceled: true, filePath: null }
  }

  const response = await fetch(targetUrl)
  if (!response.ok) {
    throw new Error(`下载失败：HTTP ${response.status}`)
  }
  const arrayBuffer = await response.arrayBuffer()
  await fs.writeFile(saveDialogResult.filePath, Buffer.from(arrayBuffer))
  return { canceled: false, filePath: saveDialogResult.filePath }
})

function readIntEnv(name, fallback) {
  const raw = process.env[name]
  const value = Number.parseInt(raw || '', 10)
  return Number.isFinite(value) && value > 0 ? value : fallback
}

function createMainWindow() {
  const windowWidth = readIntEnv('ELECTRON_WINDOW_WIDTH', 1180)
  const windowHeight = readIntEnv('ELECTRON_WINDOW_HEIGHT', 760)
  const minWindowWidth = readIntEnv('ELECTRON_MIN_WIDTH', 900)
  const minWindowHeight = readIntEnv('ELECTRON_MIN_HEIGHT', 620)

  const mainWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    minWidth: minWindowWidth,
    minHeight: minWindowHeight,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#f9f9f7',
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url)
    return { action: 'deny' }
  })

  if (isDev && devServerUrl) {
    void mainWindow.loadURL(devServerUrl)
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    void mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
}

app.whenReady().then(() => {
  createMainWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
