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

export interface PanelBindingSummary {
  characterNames: string[]
  locationNames: string[]
  voiceName?: string
  voiceId?: string
  effectivePrompt?: string
  effectiveReferenceImageUrl?: string
  compiled: boolean
}
