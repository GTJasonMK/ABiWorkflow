import client from './client'
import { resolveAsyncResult } from './tasks'
import type { ApiResponse } from '../types/api'

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
  return resp.data.data ?? { method: 'heuristic', confidence: 0, episodes: [] }
}

export async function splitByLlm(projectId: string, content: string): Promise<ImportSplitResponse> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(
    `/projects/${projectId}/import/llm-split?async_mode=true`,
    { content },
    { timeout: 0 },
  )
  const result = await resolveAsyncResult(resp.data.data ?? {}, { timeoutMs: 20 * 60 * 1000 })
  return {
    method: typeof result.method === 'string' ? result.method : 'llm_fallback',
    confidence: Number(result.confidence ?? 0),
    marker_type: typeof result.marker_type === 'string' ? result.marker_type : null,
    has_markers: Boolean(result.has_markers),
    episodes: Array.isArray(result.episodes) ? result.episodes as ImportEpisodeDraft[] : [],
  }
}
