import { create } from 'zustand'
import { getTaskStatus, type TaskStatusPayload } from '../api/tasks'

export type TaskKind = 'parse' | 'generate' | 'compose'

export interface TaskItem {
  taskId: string
  taskType: TaskKind
  projectId: string
  state: string
  ready: boolean
  successful: boolean
  startedAt: number
  updatedAt: number
  result?: Record<string, unknown>
  error?: string
}

interface TaskTrackOptions {
  intervalMs?: number
  timeoutMs?: number
  maxConsecutiveErrors?: number
}

interface TaskState {
  tasks: TaskItem[]
  panelOpen: boolean

  setPanelOpen: (open: boolean) => void
  removeTask: (taskId: string) => void
  clearFinished: () => void
  clearAll: () => void
  refreshTask: (taskId: string) => Promise<TaskStatusPayload>
  trackTask: (
    taskId: string,
    meta: { taskType: TaskKind; projectId: string },
    options?: TaskTrackOptions,
  ) => Promise<TaskStatusPayload>
}

const MAX_HISTORY = 50

function toErrorMessage(error: unknown, fallback: string): string {
  const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
  return err?.response?.data?.detail ?? err?.response?.data?.message ?? err?.message ?? fallback
}

function upsertTask(
  tasks: TaskItem[],
  taskId: string,
  updater: (prev: TaskItem | null) => TaskItem,
): TaskItem[] {
  const idx = tasks.findIndex((t) => t.taskId === taskId)
  if (idx >= 0) {
    const next = [...tasks]
    next[idx] = updater(next[idx] ?? null)
    return next
  }

  const created = updater(null)
  const next = [created, ...tasks]
  return next.slice(0, MAX_HISTORY)
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: [],
  panelOpen: false,

  setPanelOpen: (open) => set({ panelOpen: open }),

  removeTask: (taskId) => {
    set((state) => ({ tasks: state.tasks.filter((t) => t.taskId !== taskId) }))
  },

  clearFinished: () => {
    set((state) => ({ tasks: state.tasks.filter((t) => !t.ready) }))
  },

  clearAll: () => {
    set({ tasks: [] })
  },

  refreshTask: async (taskId) => {
    try {
      const status = await getTaskStatus(taskId)
      const now = Date.now()
      set((state) => ({
        tasks: upsertTask(state.tasks, taskId, (prev) => ({
          taskId,
          taskType: prev?.taskType ?? 'generate',
          projectId: prev?.projectId ?? '',
          startedAt: prev?.startedAt ?? now,
          updatedAt: now,
          state: status.state,
          ready: status.ready,
          successful: status.successful,
          result: status.result,
          error: status.error,
        })),
      }))
      return status
    } catch (error) {
      const now = Date.now()
      const message = toErrorMessage(error, '任务状态刷新失败')
      set((state) => ({
        tasks: upsertTask(state.tasks, taskId, (prev) => ({
          taskId,
          taskType: prev?.taskType ?? 'generate',
          projectId: prev?.projectId ?? '',
          startedAt: prev?.startedAt ?? now,
          updatedAt: now,
          state: 'error',
          ready: true,
          successful: false,
          result: prev?.result,
          error: message,
        })),
      }))
      throw new Error(message)
    }
  },

  trackTask: async (taskId, meta, options) => {
    const intervalMs = options?.intervalMs ?? 2000
    const timeoutMs = options?.timeoutMs ?? 10 * 60 * 1000
    const maxConsecutiveErrors = Math.max(1, options?.maxConsecutiveErrors ?? 3)
    const startedAt = Date.now()
    let consecutiveErrors = 0

    set((state) => ({
      tasks: upsertTask(state.tasks, taskId, (prev) => ({
        taskId,
        taskType: meta.taskType,
        projectId: meta.projectId,
        startedAt: prev?.startedAt ?? startedAt,
        updatedAt: startedAt,
        state: prev?.state ?? 'queued',
        ready: prev?.ready ?? false,
        successful: prev?.successful ?? false,
        result: prev?.result,
        error: prev?.error,
      })),
    }))

    while (true) {
      let status: TaskStatusPayload
      try {
        status = await getTaskStatus(taskId)
        consecutiveErrors = 0
      } catch (error) {
        const now = Date.now()
        const message = toErrorMessage(error, '任务状态查询失败')
        consecutiveErrors += 1
        const reachErrorLimit = consecutiveErrors >= maxConsecutiveErrors

        set((state) => ({
          tasks: upsertTask(state.tasks, taskId, (prev) => ({
            taskId,
            taskType: prev?.taskType ?? meta.taskType,
            projectId: prev?.projectId ?? meta.projectId,
            startedAt: prev?.startedAt ?? startedAt,
            updatedAt: now,
            state: reachErrorLimit ? 'error' : 'processing',
            ready: reachErrorLimit,
            successful: false,
            result: prev?.result,
            error: message,
          })),
        }))

        if (Date.now() - startedAt > timeoutMs) {
          set((state) => ({
            tasks: upsertTask(state.tasks, taskId, (prev) => ({
              taskId,
              taskType: prev?.taskType ?? meta.taskType,
              projectId: prev?.projectId ?? meta.projectId,
              startedAt: prev?.startedAt ?? startedAt,
              updatedAt: Date.now(),
              state: 'timeout',
              ready: true,
              successful: false,
              result: prev?.result,
              error: '任务等待超时，请稍后重试',
            })),
          }))
          throw new Error('任务等待超时，请稍后重试')
        }

        if (reachErrorLimit) {
          throw new Error(`任务状态查询连续失败(${consecutiveErrors}次): ${message}`)
        }

        await new Promise((resolve) => setTimeout(resolve, intervalMs))
        continue
      }

      const now = Date.now()
      set((state) => ({
        tasks: upsertTask(state.tasks, taskId, (prev) => ({
          taskId,
          taskType: prev?.taskType ?? meta.taskType,
          projectId: prev?.projectId ?? meta.projectId,
          startedAt: prev?.startedAt ?? startedAt,
          updatedAt: now,
          state: status.state,
          ready: status.ready,
          successful: status.successful,
          result: status.result,
          error: status.error,
        })),
      }))

      if (status.ready) {
        if (!status.successful) {
          throw new Error(status.error ?? `任务失败: ${status.state}`)
        }
        return status
      }

      if (Date.now() - startedAt > timeoutMs) {
        set((state) => ({
          tasks: upsertTask(state.tasks, taskId, (prev) => ({
            taskId,
            taskType: prev?.taskType ?? meta.taskType,
            projectId: prev?.projectId ?? meta.projectId,
            startedAt: prev?.startedAt ?? startedAt,
            updatedAt: Date.now(),
            state: 'timeout',
            ready: true,
            successful: false,
            result: prev?.result,
            error: '任务等待超时，请稍后重试',
          })),
        }))
        throw new Error('任务等待超时，请稍后重试')
      }

      await new Promise((resolve) => setTimeout(resolve, intervalMs))
    }
  },
}))
