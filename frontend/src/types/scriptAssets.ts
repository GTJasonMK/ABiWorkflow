export type ScriptEntityType = 'character' | 'location' | 'speaker'
export type ScriptAssetType = 'character' | 'location' | 'voice'

export interface ScriptAssetBinding {
  id?: string
  entity_id?: string
  asset_type: ScriptAssetType
  asset_id: string
  asset_name?: string | null
  role_tag?: string | null
  priority?: number
  is_primary?: boolean
  strategy?: Record<string, unknown> | null
  created_at?: string
  updated_at?: string
}

export interface ScriptEntity {
  id: string
  project_id: string
  entity_type: ScriptEntityType
  name: string
  alias: string | null
  description: string | null
  meta: Record<string, unknown>
  bindings: ScriptAssetBinding[]
  created_at: string
  updated_at: string
}

export interface ScriptScopedOverride {
  id?: string
  entity_id: string
  asset_type: ScriptAssetType
  asset_id: string
  asset_name?: string | null
  role_tag?: string | null
  priority?: number
  is_primary?: boolean
  strategy?: Record<string, unknown> | null
  created_at?: string
  updated_at?: string
}

export interface PanelEffectiveBinding {
  panel_id: string
  project_id: string
  episode_id: string
  characters: Array<Record<string, unknown>>
  locations: Array<Record<string, unknown>>
  voices: Array<Record<string, unknown>>
  effective_voice: Record<string, unknown> | null
  effective_reference_image_url: string | null
  effective_visual_prompt: string | null
  effective_negative_prompt: string | null
  effective_tts_text: string | null
  trace: {
    warnings: string[]
    compiled_at: string
    compiler_version: string
  }
}
