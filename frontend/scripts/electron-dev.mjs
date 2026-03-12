import { spawn } from 'node:child_process'
import process from 'node:process'

const isWindows = process.platform === 'win32'

const rendererHost = '127.0.0.1'
const rendererPort = process.env.ELECTRON_RENDERER_PORT || '5173'
const rendererUrl = `http://${rendererHost}:${rendererPort}`
// 开发模式默认走 Vite 代理，减少跨域问题。
const apiBaseUrl = process.env.ELECTRON_API_BASE_URL || '/api'
const wsBaseUrl = process.env.ELECTRON_WS_BASE_URL || '/ws'

let viteProcess = null
let electronProcess = null
let shuttingDown = false

function shutdown(exitCode = 0) {
  if (shuttingDown) return
  shuttingDown = true

  if (electronProcess && !electronProcess.killed) {
    electronProcess.kill('SIGTERM')
  }
  if (viteProcess && !viteProcess.killed) {
    viteProcess.kill('SIGTERM')
  }

  setTimeout(() => process.exit(exitCode), 200)
}

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

function spawnCommand(command, env = process.env) {
  if (isWindows) {
    return spawn(
      'cmd.exe',
      ['/d', '/s', '/c', command],
      {
        stdio: 'inherit',
        env,
      },
    )
  }

  return spawn(
    'bash',
    ['-lc', command],
    {
      stdio: 'inherit',
      env,
    },
  )
}

async function waitForRendererReady(timeoutMs = 45000) {
  const start = Date.now()
  let lastProgressAt = 0
  while (Date.now() - start <= timeoutMs) {
    try {
      const response = await fetch(rendererUrl)
      if (response.ok || response.status === 404) {
        return true
      }
    } catch {
      // Ignore connection errors during startup.
    }
    const elapsed = Date.now() - start
    if (elapsed - lastProgressAt >= 5000) {
      lastProgressAt = elapsed
      console.log(`[electron-dev] 等待前端开发服务器就绪: ${rendererUrl} (${Math.floor(elapsed / 1000)}s)`)
    }
    await wait(500)
  }
  return false
}

function startVite() {
  console.log(`[electron-dev] 启动 Vite 渲染进程: ${rendererUrl}`)
  viteProcess = spawnCommand(`npm run dev -- --host ${rendererHost} --port ${rendererPort} --strictPort`)

  viteProcess.on('exit', (code) => {
    if (!shuttingDown) {
      console.error(`[electron-dev] Vite 已退出，退出码=${code ?? 0}`)
      shutdown(code ?? 1)
    }
  })
}

function startElectron() {
  electronProcess = spawnCommand(
    'npm exec electron .',
    {
      ...process.env,
      ELECTRON_RENDERER_URL: rendererUrl,
      ELECTRON_API_BASE_URL: apiBaseUrl,
      ELECTRON_WS_BASE_URL: wsBaseUrl,
    },
  )

  electronProcess.on('exit', (code) => {
    shutdown(code ?? 0)
  })
}

process.on('SIGINT', () => shutdown(0))
process.on('SIGTERM', () => shutdown(0))

startVite()
console.log(`[electron-dev] 等待前端开发服务器: ${rendererUrl}`)

const ready = await waitForRendererReady()
if (!ready) {
  console.error(`[electron-dev] 等待前端开发服务器超时: ${rendererUrl}`)
  shutdown(1)
} else {
  console.log(`[electron-dev] 渲染进程地址: ${rendererUrl}`)
  console.log(`[electron-dev] API 地址: ${apiBaseUrl}`)
  startElectron()
}
