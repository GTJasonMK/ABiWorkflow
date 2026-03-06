import client from './client'
import type { ApiResponse } from '../types/api'
import { resolveBackendUrl } from '../utils/backendUrl'

export interface AssetClip {
  id: string
  clip_order: number
  candidate_index: number
  is_selected: boolean
  status: string
  duration_seconds: number
  provider_task_id: string | null
  file_path: string | null
  media_url: string | null
  error_message: string | null
  updated_at: string | null
}

export interface AssetPanel {
  panel_id: string
  episode_id: string
  panel_order: number
  title: string
  status: string
  duration_seconds: number
  clips: AssetClip[]
}

export interface AssetComposition {
  id: string
  status: string
  duration_seconds: number
  transition_type: string
  include_subtitles: boolean
  include_tts: boolean
  file_path: string | null
  media_url: string | null
  download_url: string
  error_message: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ProjectAssetsPayload {
  project_id: string
  project_name: string
  summary: {
    panel_count: number
    clip_count: number
    ready_clip_count: number
    failed_clip_count: number
    composition_count: number
  }
  panels: AssetPanel[]
  compositions: AssetComposition[]
}

const inflightRequests = new Map<string, Promise<ProjectAssetsPayload>>()

function normalizeProjectAssetsPayload(payload: ProjectAssetsPayload): ProjectAssetsPayload {
  return {
    ...payload,
    panels: payload.panels.map((panel) => ({
      ...panel,
      clips: panel.clips.map((clip) => ({
        ...clip,
        media_url: resolveBackendUrl(clip.media_url),
      })),
    })),
    compositions: payload.compositions.map((item) => ({
      ...item,
      media_url: resolveBackendUrl(item.media_url),
      download_url: resolveBackendUrl(item.download_url) ?? item.download_url,
    })),
  }
}

/** 获取项目媒体资产 */
export async function getProjectAssets(projectId: string): Promise<ProjectAssetsPayload> {
  const cachedRequest = inflightRequests.get(projectId)
  if (cachedRequest) return cachedRequest

  const request = (async () => {
    const resp = await client.get<ApiResponse<ProjectAssetsPayload>>(`/projects/${projectId}/assets`)
    if (!resp.data?.data) {
      throw new Error('获取媒体资产失败：响应格式非法')
    }
    return normalizeProjectAssetsPayload(resp.data.data)
  })()

  inflightRequests.set(projectId, request)
  try {
    return await request
  } finally {
    inflightRequests.delete(projectId)
  }
}
