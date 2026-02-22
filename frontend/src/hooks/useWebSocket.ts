import { useEffect, useRef, useState, useCallback } from 'react'

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

  const connect = useCallback(() => {
    if (!projectId) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/progress/${projectId}`)

    ws.onopen = () => {
      setConnected(true)
    }

    ws.onmessage = (event) => {
      const msg: ProgressMessage = JSON.parse(event.data)
      setMessages((prev) => [...prev, msg])
      setLastMessage(msg)
    }

    ws.onclose = () => {
      setConnected(false)
    }

    ws.onerror = () => {
      setConnected(false)
    }

    wsRef.current = ws
  }, [projectId])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [connect])

  const clearMessages = useCallback(() => {
    setMessages([])
    setLastMessage(null)
  }, [])

  return { messages, lastMessage, connected, clearMessages }
}
