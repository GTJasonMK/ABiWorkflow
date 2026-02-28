import client from './client'
import type { ApiResponse } from '../types/api'
import type { Episode } from '../types/episode'

export async function listEpisodes(projectId: string): Promise<Episode[]> {
  const resp = await client.get<ApiResponse<Episode[]>>(`/projects/${projectId}/episodes`)
  return resp.data.data ?? []
}

export async function createEpisode(
  projectId: string,
  payload: { title: string; summary?: string; script_text?: string },
): Promise<Episode> {
  const resp = await client.post<ApiResponse<Episode>>(`/projects/${projectId}/episodes`, payload)
  return resp.data.data!
}

export async function updateEpisode(
  episodeId: string,
  payload: Partial<Pick<Episode, 'title' | 'summary' | 'script_text' | 'status'>>,
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
