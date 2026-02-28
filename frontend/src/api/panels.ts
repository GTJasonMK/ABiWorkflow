import client from './client'
import type { ApiResponse } from '../types/api'
import type { Panel } from '../types/panel'

export interface ProviderTaskSubmitPayload {
  provider_key: string
  payload?: Record<string, unknown>
  unit_price?: number
  model_name?: string
}

export async function listEpisodePanels(episodeId: string): Promise<Panel[]> {
  const resp = await client.get<ApiResponse<Panel[]>>(`/episodes/${episodeId}/panels`)
  return resp.data.data ?? []
}

export async function listProjectPanels(projectId: string): Promise<Panel[]> {
  const resp = await client.get<ApiResponse<Panel[]>>(`/projects/${projectId}/panels`)
  return resp.data.data ?? []
}

export async function createPanel(
  episodeId: string,
  payload: { title: string; script_text?: string; visual_prompt?: string; negative_prompt?: string; duration_seconds?: number },
): Promise<Panel> {
  const resp = await client.post<ApiResponse<Panel>>(`/episodes/${episodeId}/panels`, payload)
  return resp.data.data!
}

export async function updatePanel(
  panelId: string,
  payload: Partial<Panel>,
): Promise<Panel> {
  const resp = await client.put<ApiResponse<Panel>>(`/panels/${panelId}`, payload)
  return resp.data.data!
}

export async function deletePanel(panelId: string): Promise<void> {
  await client.delete(`/panels/${panelId}`)
}

export async function reorderPanels(episodeId: string, panelIds: string[]): Promise<void> {
  await client.put(`/episodes/${episodeId}/panels/reorder`, { panel_ids: panelIds })
}

export async function submitPanelVideo(panelId: string, payload: ProviderTaskSubmitPayload): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/video/submit`, payload)
  return resp.data.data ?? {}
}

export async function getPanelVideoStatus(panelId: string, providerKey: string): Promise<Record<string, unknown>> {
  const resp = await client.get<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/video/status`, {
    params: { provider_key: providerKey },
  })
  return resp.data.data ?? {}
}

export async function applyPanelVideo(panelId: string, resultUrl: string): Promise<Panel> {
  const resp = await client.post<ApiResponse<Panel>>(`/panels/${panelId}/video/apply`, { result_url: resultUrl })
  return resp.data.data!
}

export async function analyzePanelVoice(panelId: string): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/voice/analyze`, {})
  return resp.data.data ?? {}
}

export async function designPanelVoice(
  panelId: string,
  payload: { mood?: string; speed?: number; pitch?: number },
): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/voice/design`, payload)
  return resp.data.data ?? {}
}

export async function generatePanelVoiceLines(panelId: string, payload: ProviderTaskSubmitPayload): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/voice/generate-lines`, payload)
  return resp.data.data ?? {}
}

export async function bindPanelVoice(
  panelId: string,
  payload: { voice_id?: string | null; binding?: Record<string, unknown> },
): Promise<Panel> {
  const resp = await client.put<ApiResponse<Panel>>(`/panels/${panelId}/voice/binding`, payload)
  return resp.data.data!
}

export async function submitPanelLipsync(panelId: string, payload: ProviderTaskSubmitPayload): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/lipsync/submit`, payload)
  return resp.data.data ?? {}
}

export async function getPanelLipsyncStatus(panelId: string, providerKey: string): Promise<Record<string, unknown>> {
  const resp = await client.get<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/lipsync/status`, {
    params: { provider_key: providerKey },
  })
  return resp.data.data ?? {}
}

export async function applyPanelLipsync(panelId: string, resultUrl: string): Promise<Panel> {
  const resp = await client.post<ApiResponse<Panel>>(`/panels/${panelId}/lipsync/apply`, { result_url: resultUrl })
  return resp.data.data!
}
