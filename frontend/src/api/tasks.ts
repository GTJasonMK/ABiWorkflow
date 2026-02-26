import client from './client'
import type { ApiResponse } from '../types/api'

export interface TaskStatusPayload {
  task_id: string
  state: string
  ready: boolean
  successful: boolean
  result?: Record<string, unknown>
  error?: string
}

/** 查询后台任务状态 */
export async function getTaskStatus(taskId: string): Promise<TaskStatusPayload> {
  const resp = await client.get<ApiResponse<TaskStatusPayload>>(`/tasks/${taskId}`)
  return resp.data.data!
}

/** 轮询等待后台任务完成 */
export async function waitForTask(
  taskId: string,
  options?: { intervalMs?: number; timeoutMs?: number },
): Promise<TaskStatusPayload> {
  const intervalMs = options?.intervalMs ?? 2000
  const timeoutMs = options?.timeoutMs ?? 10 * 60 * 1000
  const startedAt = Date.now()

  while (true) {
    const status = await getTaskStatus(taskId)
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

