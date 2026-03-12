import client from './client'
import type { ApiResponse } from '../types/api'
import type { Panel } from '../types/panel'

export interface UpdatePanelPayload {
  title?: string
  script_text?: string | null
  visual_prompt?: string | null
  negative_prompt?: string | null
  camera_hint?: string | null
  duration_seconds?: number
  style_preset?: string | null
  reference_image_url?: string | null
  voice_id?: string | null
  tts_text?: string | null
  tts_audio_url?: string | null
  video_url?: string | null
  lipsync_video_url?: string | null
  status?: string | null
}

export interface ProviderTaskSubmitPayload {
  provider_key?: string | null
  payload?: Record<string, unknown>
  unit_price?: number
  model_name?: string
}

export async function listEpisodePanels(episodeId: string): Promise<Panel[]> {
  const resp = await client.get<ApiResponse<Panel[]>>(`/episodes/${episodeId}/panels`)
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
  payload: UpdatePanelPayload,
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

export async function generateEpisodePanels(
  episodeId: string,
  payload: { overwrite?: boolean } = {},
): Promise<Panel[]> {
  const resp = await client.post<ApiResponse<Panel[]>>(`/episodes/${episodeId}/panels/generate`, payload, { timeout: 0 })
  return resp.data.data ?? []
}

export async function submitPanelVideo(panelId: string, payload: ProviderTaskSubmitPayload): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/video/submit`, payload)
  return resp.data.data ?? {}
}

export async function submitEpisodePanelsVideoBatch(
  episodeId: string,
  payload: ProviderTaskSubmitPayload & { force?: boolean; panel_ids?: string[] },
): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/episodes/${episodeId}/panels/video/submit-batch`, payload)
  return resp.data.data ?? {}
}

export async function submitEpisodePanelsVoiceBatch(
  episodeId: string,
  payload: ProviderTaskSubmitPayload & { force?: boolean; panel_ids?: string[] },
): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/episodes/${episodeId}/panels/voice/submit-batch`, payload)
  return resp.data.data ?? {}
}

export async function submitEpisodePanelsLipsyncBatch(
  episodeId: string,
  payload: ProviderTaskSubmitPayload & { force?: boolean; panel_ids?: string[] },
): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/episodes/${episodeId}/panels/lipsync/submit-batch`, payload)
  return resp.data.data ?? {}
}

export async function getPanelVideoStatus(panelId: string, providerKey?: string | null): Promise<Record<string, unknown>> {
  const resp = await client.get<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/video/status`, {
    params: providerKey ? { provider_key: providerKey } : undefined,
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

export async function getPanelVoiceStatus(panelId: string, providerKey?: string | null): Promise<Record<string, unknown>> {
  const resp = await client.get<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/voice/status`, {
    params: providerKey ? { provider_key: providerKey } : undefined,
  })
  return resp.data.data ?? {}
}

export async function applyPanelVoice(panelId: string, resultUrl: string): Promise<Panel> {
  const resp = await client.post<ApiResponse<Panel>>(`/panels/${panelId}/voice/apply`, { result_url: resultUrl })
  return resp.data.data!
}

export async function submitPanelLipsync(panelId: string, payload: ProviderTaskSubmitPayload): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/lipsync/submit`, payload)
  return resp.data.data ?? {}
}

export async function getPanelLipsyncStatus(panelId: string, providerKey?: string | null): Promise<Record<string, unknown>> {
  const resp = await client.get<ApiResponse<Record<string, unknown>>>(`/panels/${panelId}/lipsync/status`, {
    params: providerKey ? { provider_key: providerKey } : undefined,
  })
  return resp.data.data ?? {}
}

export async function applyPanelLipsync(panelId: string, resultUrl: string): Promise<Panel> {
  const resp = await client.post<ApiResponse<Panel>>(`/panels/${panelId}/lipsync/apply`, { result_url: resultUrl })
  return resp.data.data!
}
