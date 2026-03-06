import client from './client'
import type { ApiResponse } from '../types/api'
import type {
  PanelEffectiveBinding,
  ScriptAssetBinding,
  ScriptEntity,
  ScriptEntityType,
  ScriptScopedOverride,
} from '../types/scriptAssets'

export async function listScriptEntities(projectId: string): Promise<ScriptEntity[]> {
  const resp = await client.get<ApiResponse<{ items: ScriptEntity[] }>>(`/projects/${projectId}/script-assets/entities`)
  return resp.data.data?.items ?? []
}

export async function createScriptEntity(
  projectId: string,
  payload: {
    entity_type: ScriptEntityType
    name: string
    alias?: string | null
    description?: string | null
    meta?: Record<string, unknown> | null
    bindings?: ScriptAssetBinding[]
  },
): Promise<ScriptEntity> {
  const resp = await client.post<ApiResponse<ScriptEntity>>(`/projects/${projectId}/script-assets/entities`, payload)
  return resp.data.data!
}

export async function updateScriptEntity(
  entityId: string,
  payload: {
    name?: string
    alias?: string | null
    description?: string | null
    meta?: Record<string, unknown> | null
  },
): Promise<ScriptEntity> {
  const resp = await client.put<ApiResponse<ScriptEntity>>(`/script-assets/entities/${entityId}`, payload)
  return resp.data.data!
}

export async function deleteScriptEntity(entityId: string): Promise<void> {
  await client.delete(`/script-assets/entities/${entityId}`)
}

export async function replaceScriptEntityBindings(entityId: string, bindings: ScriptAssetBinding[]): Promise<ScriptAssetBinding[]> {
  const resp = await client.put<ApiResponse<{ entity_id: string; bindings: ScriptAssetBinding[] }>>(
    `/script-assets/entities/${entityId}/bindings`,
    { bindings },
  )
  return resp.data.data?.bindings ?? []
}

export async function getPanelAssetOverrides(panelId: string): Promise<ScriptScopedOverride[]> {
  const resp = await client.get<ApiResponse<{ panel_id: string; overrides: ScriptScopedOverride[] }>>(`/panels/${panelId}/asset-overrides`)
  return resp.data.data?.overrides ?? []
}

export async function replacePanelAssetOverrides(panelId: string, overrides: ScriptScopedOverride[]): Promise<ScriptScopedOverride[]> {
  const resp = await client.put<ApiResponse<{ panel_id: string; overrides: ScriptScopedOverride[] }>>(
    `/panels/${panelId}/asset-overrides`,
    { overrides },
  )
  return resp.data.data?.overrides ?? []
}

export async function getEpisodeAssetOverrides(episodeId: string): Promise<ScriptScopedOverride[]> {
  const resp = await client.get<ApiResponse<{ episode_id: string; overrides: ScriptScopedOverride[] }>>(`/episodes/${episodeId}/asset-overrides`)
  return resp.data.data?.overrides ?? []
}

export async function replaceEpisodeAssetOverrides(episodeId: string, overrides: ScriptScopedOverride[]): Promise<ScriptScopedOverride[]> {
  const resp = await client.put<ApiResponse<{ episode_id: string; overrides: ScriptScopedOverride[] }>>(
    `/episodes/${episodeId}/asset-overrides`,
    { overrides },
  )
  return resp.data.data?.overrides ?? []
}

export async function compilePanelBindings(panelId: string): Promise<PanelEffectiveBinding> {
  const resp = await client.post<ApiResponse<PanelEffectiveBinding>>(`/panels/${panelId}/compile-bindings`)
  return resp.data.data!
}

export async function getPanelEffectiveBindings(panelId: string): Promise<PanelEffectiveBinding> {
  const resp = await client.get<ApiResponse<PanelEffectiveBinding>>(`/panels/${panelId}/effective-bindings`)
  return resp.data.data!
}

export async function compileProjectBindings(projectId: string): Promise<{ panel_count: number; compiled_count: number }> {
  const resp = await client.post<ApiResponse<{ panel_count: number; compiled_count: number }>>(
    `/projects/${projectId}/compile-bindings`,
  )
  return resp.data.data ?? { panel_count: 0, compiled_count: 0 }
}
