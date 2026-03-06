import client from './client'
import { buildAsyncTaskQuery, type StartTaskOptions } from './tasks'
import type { ApiResponse } from '../types/api'
import { buildApiUrl } from '../runtime'
import { resolveBackendUrl } from '../utils/backendUrl'

interface CompositionOptions {
  transition_type?: 'none' | 'crossfade' | 'fade_black'
  transition_duration?: number
  include_subtitles?: boolean
  include_tts?: boolean
}

export interface ComposeQueuedResponse {
  task_id: string
  mode: 'async'
  status: string
}

export interface ComposeResultResponse {
  composition_id: string
  episode_id?: string | null
}

/** 合成记录详情 */
export interface CompositionRecord {
  id: string
  project_id: string
  episode_id?: string | null
  status: string
  output_path: string | null
  media_url: string | null
  transition_type: string
  include_subtitles: boolean
  include_tts: boolean
  duration_seconds: number
  created_at: string | null
}

function normalizeCompositionRecord(record: CompositionRecord): CompositionRecord {
  return {
    ...record,
    media_url: resolveBackendUrl(record.media_url),
  }
}

/** 获取项目最新的已完成合成记录 */
export async function getLatestComposition(projectId: string, episodeId?: string | null): Promise<CompositionRecord | null> {
  const params = new URLSearchParams()
  if (episodeId) {
    params.set('episode_id', episodeId)
  }
  const query = params.toString()
  const resp = await client.get<ApiResponse<CompositionRecord | null>>(
    `/projects/${projectId}/compositions/latest${query ? `?${query}` : ''}`,
  )
  const record = resp.data.data
  return record ? normalizeCompositionRecord(record) : null
}

/** 启动合成 */
export async function startComposition(
  projectId: string,
  options?: CompositionOptions,
  requestOptions: StartTaskOptions = {},
  episodeId?: string | null,
): Promise<ComposeQueuedResponse | ComposeResultResponse> {
  const query = new URLSearchParams(buildAsyncTaskQuery(requestOptions))
  if (episodeId) {
    query.set('episode_id', episodeId)
    query.set('async_mode', 'false')
  }
  const resp = await client.post<ApiResponse<ComposeQueuedResponse | ComposeResultResponse>>(
    `/projects/${projectId}/compose?${query.toString()}`,
    options ?? {},
    { timeout: 0 },
  )
  return resp.data.data!
}

/** 查询合成任务 */
export async function getComposition(compositionId: string): Promise<CompositionRecord> {
  const resp = await client.get<ApiResponse<CompositionRecord>>(`/compositions/${compositionId}`)
  return normalizeCompositionRecord(resp.data.data!)
}

/** 裁剪合成视频 */
export async function trimComposition(
  compositionId: string,
  startTime: number,
  endTime: number,
): Promise<{ composition_id: string; duration_seconds: number; media_url: string | null }> {
  const resp = await client.post<ApiResponse<{ composition_id: string; duration_seconds: number; media_url: string | null }>>(
    `/compositions/${compositionId}/trim`,
    { start_time: startTime, end_time: endTime },
    { timeout: 0 },
  )
  const payload = resp.data.data!
  return {
    ...payload,
    media_url: resolveBackendUrl(payload.media_url),
  }
}

/** 获取下载 URL（用于下载按钮，通过 API 端点返回 Content-Disposition） */
export function getDownloadUrl(compositionId: string): string {
  return buildApiUrl(`/compositions/${compositionId}/download`)
}
