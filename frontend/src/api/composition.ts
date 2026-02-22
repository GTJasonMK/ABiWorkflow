import client from './client'
import type { ApiResponse } from '../types/api'

interface CompositionOptions {
  transition_type?: 'none' | 'crossfade' | 'fade_black'
  transition_duration?: number
  include_subtitles?: boolean
  include_tts?: boolean
}

/** 启动合成 */
export async function startComposition(
  projectId: string,
  options?: CompositionOptions,
): Promise<{ composition_id: string }> {
  const resp = await client.post<ApiResponse<{ composition_id: string }>>(
    `/projects/${projectId}/compose`,
    options ?? {},
  )
  return resp.data.data!
}

/** 查询合成任务 */
export async function getComposition(compositionId: string): Promise<Record<string, unknown>> {
  const resp = await client.get<ApiResponse<Record<string, unknown>>>(`/compositions/${compositionId}`)
  return resp.data.data!
}

/** 获取下载 URL */
export function getDownloadUrl(compositionId: string): string {
  return `/api/compositions/${compositionId}/download`
}
