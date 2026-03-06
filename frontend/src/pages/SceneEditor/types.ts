import type { GlobalCharacterAsset, GlobalLocationAsset } from '../../types/assetHub'

export type AssetTabKey = 'character' | 'location' | 'voice'
export type PromptApplyMode = 'append' | 'replace'
export type AssetSourceScope = 'all' | 'project' | 'global'

export const DIRECT_BIND_PROMPT_MODE: PromptApplyMode = 'append'

export const DEFAULT_ASSET_FOLDER_FILTERS: Record<AssetTabKey, string> = {
  character: 'all',
  location: 'all',
  voice: 'all',
}
export const DEFAULT_ASSET_SEARCH_TEXTS: Record<AssetTabKey, string> = {
  character: '',
  location: '',
  voice: '',
}
export const DEFAULT_ONLY_BOUND_FILTERS: Record<AssetTabKey, boolean> = {
  character: false,
  location: false,
  voice: false,
}
export const DEFAULT_ASSET_SOURCE_SCOPES: Record<AssetTabKey, AssetSourceScope> = {
  character: 'all',
  location: 'all',
  voice: 'all',
}

export interface PanelAssetBinding {
  asset_character_ids?: string[]
  asset_character_id?: string
  asset_character_name?: string
  asset_location_ids?: string[]
  asset_location_id?: string
  asset_location_name?: string
  asset_voice_ids?: string[]
  asset_voice_id?: string
  asset_voice_name?: string
  asset_prompt_apply_mode?: string
}

export interface CharacterApplyPlan {
  nextPrompt: string | null
  nextReferenceImageUrl: string | null
  fallbackVoiceId: string | null
  fallbackVoiceName?: string
}

export interface LocationApplyPlan {
  nextPrompt: string | null
  nextReferenceImageUrl: string | null
}

export interface PanelEditDraft {
  title: string
  script_text: string
  visual_prompt: string
  negative_prompt: string
  camera_hint: string
  duration_seconds: number
  style_preset: string
  reference_image_url: string
  tts_text: string
}

export type BindPreviewState =
  | {
    type: 'character'
    panelId: string
    panelTitle: string
    originPrompt: string | null
    addedPromptLines: string[]
    plan: CharacterApplyPlan
    character: GlobalCharacterAsset
  }
  | {
    type: 'location'
    panelId: string
    panelTitle: string
    originPrompt: string | null
    addedPromptLines: string[]
    plan: LocationApplyPlan
    location: GlobalLocationAsset
  }

export interface AssetDrawerState {
  open: boolean
  panelId: string | null
  tab: AssetTabKey
}
