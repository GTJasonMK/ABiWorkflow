import client from './client'
import type { ApiResponse } from '../types/api'
import type { AssetFolder, AssetHubOverview, GlobalCharacterAsset, GlobalLocationAsset, GlobalVoice } from '../types/assetHub'

export type AssetScope = 'all' | 'global' | 'project'
export type AssetDraftType = 'character' | 'location' | 'voice'

export interface AssetDraftFromPanelRequest {
  asset_type: AssetDraftType
  panel_title: string
  script_text?: string
  visual_prompt?: string
  tts_text?: string
  reference_image_url?: string
  source_voice_name?: string
  source_voice_provider?: string
  source_voice_code?: string
}

export interface AssetDraftFromPanelResponse {
  name: string
  description: string | null
  prompt_template: string | null
  style_prompt: string | null
  generator: 'llm'
}

export interface AssetHubOverviewQuery {
  projectId?: string | null
  scope?: AssetScope
}

function buildOverviewQuery(options?: AssetHubOverviewQuery): string {
  const params = new URLSearchParams()
  const scope = options?.scope ?? 'all'
  params.set('scope', scope)
  if (options?.projectId) {
    params.set('project_id', options.projectId)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

export async function getAssetHubOverview(options?: AssetHubOverviewQuery): Promise<AssetHubOverview> {
  const resp = await client.get<ApiResponse<AssetHubOverview>>(`/asset-hub/overview${buildOverviewQuery(options)}`)
  return resp.data.data ?? { folders: [], characters: [], locations: [], voices: [] }
}

export async function generateAssetDraftFromPanel(payload: AssetDraftFromPanelRequest): Promise<AssetDraftFromPanelResponse> {
  const resp = await client.post<ApiResponse<AssetDraftFromPanelResponse>>('/asset-hub/drafts/from-panel', payload)
  return resp.data.data!
}

export async function renderGlobalCharacterReference(characterId: string): Promise<GlobalCharacterAsset> {
  const resp = await client.post<ApiResponse<GlobalCharacterAsset>>(`/asset-hub/characters/${characterId}/render-reference`)
  return resp.data.data!
}

export async function renderGlobalLocationReference(locationId: string): Promise<GlobalLocationAsset> {
  const resp = await client.post<ApiResponse<GlobalLocationAsset>>(`/asset-hub/locations/${locationId}/render-reference`)
  return resp.data.data!
}

export async function renderGlobalVoiceSample(
  voiceId: string,
  payload?: { sample_text?: string },
): Promise<GlobalVoice> {
  const resp = await client.post<ApiResponse<GlobalVoice>>(`/asset-hub/voices/${voiceId}/render-sample`, payload ?? {})
  return resp.data.data!
}

export async function createAssetFolder(payload: {
  name: string
  folder_type?: string
  storage_path?: string
  description?: string
}): Promise<AssetFolder> {
  const resp = await client.post<ApiResponse<AssetFolder>>('/asset-hub/folders', payload)
  return resp.data.data!
}

export async function updateAssetFolder(
  folderId: string,
  payload: Partial<AssetFolder>,
): Promise<AssetFolder> {
  const resp = await client.put<ApiResponse<AssetFolder>>(`/asset-hub/folders/${folderId}`, payload)
  return resp.data.data!
}

export async function deleteAssetFolder(folderId: string): Promise<void> {
  await client.delete(`/asset-hub/folders/${folderId}`)
}

export async function createGlobalVoice(payload: {
  name: string
  project_id?: string | null
  provider: string
  voice_code: string
  folder_id?: string | null
  language?: string
  gender?: string
  sample_audio_url?: string
  style_prompt?: string
  meta?: Record<string, unknown>
}): Promise<GlobalVoice> {
  const resp = await client.post<ApiResponse<GlobalVoice>>('/asset-hub/voices', payload)
  return resp.data.data!
}

export async function updateGlobalVoice(voiceId: string, payload: Partial<GlobalVoice>): Promise<GlobalVoice> {
  const normalized = {
    ...payload,
    meta: payload.meta ?? {},
  }
  const resp = await client.put<ApiResponse<GlobalVoice>>(`/asset-hub/voices/${voiceId}`, normalized)
  return resp.data.data!
}

export async function deleteGlobalVoice(voiceId: string): Promise<void> {
  await client.delete(`/asset-hub/voices/${voiceId}`)
}

export async function createGlobalCharacter(payload: {
  name: string
  project_id?: string | null
  folder_id?: string | null
  alias?: string
  description?: string
  prompt_template?: string
  reference_image_url?: string
  default_voice_id?: string | null
  tags?: string[]
}): Promise<GlobalCharacterAsset> {
  const resp = await client.post<ApiResponse<GlobalCharacterAsset>>('/asset-hub/characters', payload)
  return resp.data.data!
}

export async function updateGlobalCharacter(
  characterId: string,
  payload: Partial<GlobalCharacterAsset>,
): Promise<GlobalCharacterAsset> {
  const normalized = {
    ...payload,
    tags: payload.tags ?? [],
  }
  const resp = await client.put<ApiResponse<GlobalCharacterAsset>>(`/asset-hub/characters/${characterId}`, normalized)
  return resp.data.data!
}

export async function deleteGlobalCharacter(characterId: string): Promise<void> {
  await client.delete(`/asset-hub/characters/${characterId}`)
}

export async function createGlobalLocation(payload: {
  name: string
  project_id?: string | null
  folder_id?: string | null
  description?: string
  prompt_template?: string
  reference_image_url?: string
  tags?: string[]
}): Promise<GlobalLocationAsset> {
  const resp = await client.post<ApiResponse<GlobalLocationAsset>>('/asset-hub/locations', payload)
  return resp.data.data!
}

export async function updateGlobalLocation(
  locationId: string,
  payload: Partial<GlobalLocationAsset>,
): Promise<GlobalLocationAsset> {
  const normalized = {
    ...payload,
    tags: payload.tags ?? [],
  }
  const resp = await client.put<ApiResponse<GlobalLocationAsset>>(`/asset-hub/locations/${locationId}`, normalized)
  return resp.data.data!
}

export async function deleteGlobalLocation(locationId: string): Promise<void> {
  await client.delete(`/asset-hub/locations/${locationId}`)
}
