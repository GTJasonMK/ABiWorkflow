import type { TaskRecord } from '../types/taskRecord'

export interface TaskRecordSummary {
  running: number
  failed: number
  success: number
}

export function sortTaskRecordsByUpdatedAt(tasks: TaskRecord[]): TaskRecord[] {
  return [...tasks].sort((a, b) => {
    const at = a.updated_at ? new Date(a.updated_at).getTime() : 0
    const bt = b.updated_at ? new Date(b.updated_at).getTime() : 0
    return bt - at
  })
}

export function summarizeTaskRecords(tasks: TaskRecord[]): TaskRecordSummary {
  const running = tasks.filter((item) => !item.ready).length
  const failed = tasks.filter((item) => item.ready && !item.successful).length
  const success = tasks.filter((item) => item.ready && item.successful).length
  return { running, failed, success }
}

