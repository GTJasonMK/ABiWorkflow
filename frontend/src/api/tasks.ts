import client from './client'
import type { ApiResponse } from '../types/api'
import type { TaskRecord } from '../types/taskRecord'

export interface TaskStatusPayload {
  task_id: string
  state: string
  ready: boolean
  successful: boolean
  task_type?: string
  target_type?: string | null
  target_id?: string | null
  project_id?: string | null
  episode_id?: string | null
  panel_id?: string | null
  progress_percent?: number
  message?: string | null
  result?: Record<string, unknown>
  error?: string
}

/** 查询后台任务状态 */
export async function getTaskStatus(taskId: string): Promise<TaskStatusPayload> {
  const resp = await client.get<ApiResponse<TaskStatusPayload>>(`/tasks/${taskId}`)
  return resp.data.data!
}

export async function listTaskRecords(params?: {
  project_id?: string
  episode_id?: string
  panel_id?: string
  status?: string
  include_dismissed?: boolean
  limit?: number
}): Promise<TaskRecord[]> {
  const resp = await client.get<ApiResponse<TaskRecord[]>>('/tasks', { params })
  return resp.data.data ?? []
}

export async function dismissTaskRecord(taskId: string): Promise<TaskRecord> {
  const resp = await client.post<ApiResponse<TaskRecord>>(`/tasks/${taskId}/dismiss`, {})
  return resp.data.data!
}

export async function cancelTaskRecord(taskId: string): Promise<TaskStatusPayload> {
  const resp = await client.post<ApiResponse<TaskStatusPayload>>(`/tasks/${taskId}/cancel`, {})
  return resp.data.data!
}

function toErrorMessage(error: unknown, fallback: string): string {
  const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
  return err?.response?.data?.detail ?? err?.response?.data?.message ?? err?.message ?? fallback
}

/** 轮询等待后台任务完成 */
export async function waitForTask(
  taskId: string,
  options?: { intervalMs?: number; timeoutMs?: number; maxConsecutiveErrors?: number },
): Promise<TaskStatusPayload> {
  const intervalMs = options?.intervalMs ?? 2000
  const timeoutMs = options?.timeoutMs ?? 10 * 60 * 1000
  const maxConsecutiveErrors = Math.max(1, options?.maxConsecutiveErrors ?? 3)
  const startedAt = Date.now()
  let consecutiveErrors = 0

  while (true) {
    let status: TaskStatusPayload
    try {
      status = await getTaskStatus(taskId)
      consecutiveErrors = 0
    } catch (error) {
      consecutiveErrors += 1
      const message = toErrorMessage(error, '任务状态查询失败')

      if (Date.now() - startedAt > timeoutMs) {
        throw new Error('任务等待超时，请稍后重试')
      }
      if (consecutiveErrors >= maxConsecutiveErrors) {
        throw new Error(`任务状态查询连续失败(${consecutiveErrors}次): ${message}`)
      }

      await new Promise((resolve) => setTimeout(resolve, intervalMs))
      continue
    }

    if (status.ready) {
      if (!status.successful) {
        throw new Error(status.error ?? `任务失败: ${status.state}`)
      }
      return status
    }

    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('任务等待超时，请稍后重试')
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}
