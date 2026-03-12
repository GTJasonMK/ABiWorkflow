import { useCallback, useEffect, useRef, useState } from 'react'
import { listTaskRecords } from '../api/tasks'
import type { TaskRecord } from '../types/taskRecord'

interface RefreshTaskRecordsOptions {
  silent?: boolean
  showLoading?: boolean
}

interface UseTaskRecordsOptions {
  enabled?: boolean
  limit?: number
  includeDismissed?: boolean
  pollIntervalMs?: number | null
  projectId?: string
  episodeId?: string
  panelId?: string
  status?: string
  onError?: (error: unknown) => void
}

export default function useTaskRecords({
  enabled = true,
  limit = 200,
  includeDismissed = false,
  pollIntervalMs = null,
  projectId,
  episodeId,
  panelId,
  status,
  onError,
}: UseTaskRecordsOptions = {}) {
  const [tasks, setTasks] = useState<TaskRecord[]>([])
  const [loading, setLoading] = useState(false)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onErrorRef.current = onError
  }, [onError])

  const refresh = useCallback(async (options?: RefreshTaskRecordsOptions) => {
    const showLoading = options?.showLoading ?? true
    if (showLoading) setLoading(true)
    try {
      const rows = await listTaskRecords({
        project_id: projectId,
        episode_id: episodeId,
        panel_id: panelId,
        status,
        limit,
        include_dismissed: includeDismissed,
      })
      setTasks(rows)
    } catch (error) {
      if (!options?.silent) {
        onErrorRef.current?.(error)
      }
    } finally {
      if (showLoading) setLoading(false)
    }
  }, [episodeId, includeDismissed, limit, panelId, projectId, status])

  useEffect(() => {
    if (!enabled) return

    void refresh({ showLoading: true })

    if (!pollIntervalMs || pollIntervalMs <= 0) return

    const timer = window.setInterval(() => {
      void refresh({ silent: true, showLoading: false })
    }, pollIntervalMs)

    return () => window.clearInterval(timer)
  }, [enabled, pollIntervalMs, refresh])

  return { tasks, loading, refresh, setTasks }
}
