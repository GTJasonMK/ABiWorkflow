import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const devServerUrl = process.env.ELECTRON_RENDERER_URL
const isDev = Boolean(devServerUrl)

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
