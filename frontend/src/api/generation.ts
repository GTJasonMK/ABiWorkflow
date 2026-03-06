import client from './client'
import { buildAsyncTaskQuery, type StartTaskOptions } from './tasks'
import type { ApiResponse } from '../types/api'

export interface GenerateQueuedResponse {
  task_id: string
  mode: 'async'
  status: string
}

export interface GenerateResultResponse {
  total_panels: number
  completed: number
  failed: number
}

/** 启动视频生成 */
export async function startGeneration(
  projectId: string,
  options: StartTaskOptions = {},
  episodeId?: string | null,
): Promise<GenerateQueuedResponse | GenerateResultResponse> {
  const query = new URLSearchParams(buildAsyncTaskQuery(options))
  if (episodeId) {
    query.set('episode_id', episodeId)
    query.set('async_mode', 'false')
  }
  const resp = await client.post<ApiResponse<GenerateQueuedResponse | GenerateResultResponse>>(
    `/projects/${projectId}/generate?${query.toString()}`,
    {},
    { timeout: 0 },
  )
  return resp.data.data!
}
