import client from './client'
import { resolveAsyncResult } from './tasks'
import type { ApiResponse } from '../types/api'
import { getApiErrorMessage } from '../utils/error'

export interface ImportEpisodeDraft {
  title: string
  summary: string | null
  script_text: string
  order: number
}

export interface ImportSplitResponse {
  method: string
  has_markers?: boolean
  marker_type?: string | null
  confidence: number
  episodes: ImportEpisodeDraft[]
}

export async function splitByMarkers(projectId: string, content: string): Promise<ImportSplitResponse> {
  const resp = await client.post<ApiResponse<ImportSplitResponse>>(`/projects/${projectId}/import/marker-split`, { content })
  if (!resp.data.data) {
    throw new Error('标识符切分失败：响应为空')
  }
  return resp.data.data
}

export async function splitByLlm(projectId: string, content: string): Promise<ImportSplitResponse> {
  let startResult: Record<string, unknown>
  try {
    const resp = await client.post<ApiResponse<Record<string, unknown>>>(
      `/projects/${projectId}/import/llm-split?async_mode=true`,
      { content },
      { timeout: 0, suppressErrorLog: true },
    )
    startResult = resp.data.data ?? {}
  } catch (error) {
    const message = getApiErrorMessage(error, '')
    if (message.includes('当前没有可用的 Celery worker')) {
      const fallbackResp = await client.post<ApiResponse<Record<string, unknown>>>(
        `/projects/${projectId}/import/llm-split?async_mode=false`,
        { content },
        { timeout: 0 },
      )
      startResult = fallbackResp.data.data ?? {}
    } else {
      throw error
    }
  }

  const result = await resolveAsyncResult(startResult, { timeoutMs: 20 * 60 * 1000 })
  const episodes = Array.isArray(result.episodes) ? (result.episodes as ImportEpisodeDraft[]) : null
  if (!episodes) {
    throw new Error('AI 切分失败：响应格式非法')
  }
  return {
    method: typeof result.method === 'string' ? result.method : 'llm',
    confidence: Number(result.confidence ?? 0),
    marker_type: typeof result.marker_type === 'string' ? result.marker_type : null,
    has_markers: Boolean(result.has_markers),
    episodes,
  }
}
