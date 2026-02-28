import client from './client'
import type { ApiResponse } from '../types/api'
import type { AssetFolder, AssetHubOverview, GlobalCharacterAsset, GlobalLocationAsset, GlobalVoice } from '../types/assetHub'

export async function getAssetHubOverview(): Promise<AssetHubOverview> {
  const resp = await client.get<ApiResponse<AssetHubOverview>>('/asset-hub/overview')
  return resp.data.data ?? { folders: [], characters: [], locations: [], voices: [] }
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
  provider: string
  voice_code: string
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
  alias?: string
  description?: string
  prompt_template?: string
  reference_image_url?: string
  default_voice_id?: string
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
