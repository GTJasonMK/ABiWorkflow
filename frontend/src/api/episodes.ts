import client from './client'
import type { ApiResponse } from '../types/api'
import type { Episode, EpisodeProviderPayloadDefaults } from '../types/episode'

export interface EpisodeUpsertPayload {
  title?: string
  summary?: string | null
  script_text?: string | null
  video_provider_key?: string | null
  tts_provider_key?: string | null
  lipsync_provider_key?: string | null
  provider_payload_defaults?: EpisodeProviderPayloadDefaults | null
  skipped_checks?: string[]
  status?: string | null
}

export async function listEpisodes(projectId: string): Promise<Episode[]> {
  const resp = await client.get<ApiResponse<Episode[]>>(`/projects/${projectId}/episodes`)
  return resp.data.data ?? []
}

export async function createEpisode(
  projectId: string,
  payload: EpisodeUpsertPayload,
): Promise<Episode> {
  const resp = await client.post<ApiResponse<Episode>>(`/projects/${projectId}/episodes`, payload)
  return resp.data.data!
}

export async function updateEpisode(
  episodeId: string,
  payload: EpisodeUpsertPayload,
): Promise<Episode> {
  const resp = await client.put<ApiResponse<Episode>>(`/episodes/${episodeId}`, payload)
  return resp.data.data!
}

export async function deleteEpisode(episodeId: string): Promise<void> {
  await client.delete(`/episodes/${episodeId}`)
}

export async function reorderEpisodes(projectId: string, episodeIds: string[]): Promise<void> {
  await client.put(`/projects/${projectId}/episodes/reorder`, { episode_ids: episodeIds })
}
