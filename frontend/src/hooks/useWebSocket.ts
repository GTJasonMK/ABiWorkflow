import { useEffect, useRef, useState, useCallback } from 'react'
import { getWsBaseUrl } from '../runtime'

export interface ProgressMessage {
  type: string
  data: Record<string, unknown>
}

/**
 * WebSocket 进度连接 Hook
 * 自动连接到后端 /ws/progress/{projectId}，接收实时进度消息
 */
export function useWebSocket(projectId: string | undefined) {
  const [messages, setMessages] = useState<ProgressMessage[]>([])
  const [connected, setConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<ProgressMessage | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const shouldReconnectRef = useRef(true)

  const connect = useCallback(() => {
    if (!projectId) return
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (wsRef.current) {
      const state = wsRef.current.readyState
      if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const fallbackBase = `${protocol}//${window.location.host}/ws`
    const wsBase = getWsBaseUrl() ?? fallbackBase
    const ws = new WebSocket(`${wsBase}/progress/${projectId}`)

    ws.onopen = () => {
      setConnected(true)
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }

    ws.onmessage = (event) => {
      try {
        const msg: ProgressMessage = JSON.parse(event.data)
        setMessages((prev) => [...prev, msg])
        setLastMessage(msg)
      } catch {
        // ignore malformed progress payloads
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      if (shouldReconnectRef.current && projectId) {
        reconnectTimerRef.current = window.setTimeout(() => {
          connect()
        }, 2000)
      }
    }

    ws.onerror = () => {
      setConnected(false)
      ws.close()
    }

    wsRef.current = ws
  }, [projectId])

  useEffect(() => {
    shouldReconnectRef.current = true
    connect()
    return () => {
      shouldReconnectRef.current = false
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  const clearMessages = useCallback(() => {
    setMessages([])
    setLastMessage(null)
  }, [])

  return { messages, lastMessage, connected, clearMessages }
}
