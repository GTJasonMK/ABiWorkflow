import { create } from 'zustand'
import { waitForTask, type TaskStatusPayload } from '../api/tasks'

export type TaskKind = 'parse' | 'generate' | 'compose'

interface TaskTrackOptions {
  intervalMs?: number
  timeoutMs?: number
  maxConsecutiveErrors?: number
}

interface TaskState {
  panelOpen: boolean
  setPanelOpen: (open: boolean) => void
  trackTask: (
    taskId: string,
    meta: { taskType: TaskKind; projectId: string },
    options?: TaskTrackOptions,
  ) => Promise<TaskStatusPayload>
}

export const useTaskStore = create<TaskState>((set) => ({
  panelOpen: false,

  setPanelOpen: (open) => set({ panelOpen: open }),

  trackTask: async (taskId, _meta, options) => waitForTask(taskId, options),
}))
