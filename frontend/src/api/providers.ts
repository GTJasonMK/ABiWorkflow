import client from './client'
import type { ApiResponse } from '../types/api'
import type { ProviderConfig, ProviderUpsertPayload } from '../types/provider'

export async function listProviderConfigs(): Promise<ProviderConfig[]> {
  const resp = await client.get<ApiResponse<ProviderConfig[]>>('/system/providers')
  return resp.data.data ?? []
}

export async function upsertProviderConfig(providerKey: string, payload: ProviderUpsertPayload): Promise<ProviderConfig> {
  const resp = await client.put<ApiResponse<ProviderConfig>>(`/system/providers/${providerKey}`, payload)
  return resp.data.data!
}

export async function testProviderConfig(providerKey: string): Promise<Record<string, unknown>> {
  const resp = await client.post<ApiResponse<Record<string, unknown>>>(`/system/providers/${providerKey}/test`, {})
  return resp.data.data ?? {}
}
