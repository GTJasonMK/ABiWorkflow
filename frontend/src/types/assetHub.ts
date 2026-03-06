export interface AssetFolder {
  id: string
  name: string
  folder_type: string
  storage_path: string | null
  description: string | null
  sort_order: number
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface GlobalVoice {
  id: string
  name: string
  project_id: string | null
  provider: string
  voice_code: string
  folder_id: string | null
  language: string | null
  gender: string | null
  sample_audio_url: string | null
  style_prompt: string | null
  meta: Record<string, unknown>
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface GlobalCharacterAsset {
  id: string
  name: string
  project_id: string | null
  folder_id: string | null
  alias: string | null
  description: string | null
  prompt_template: string | null
  reference_image_url: string | null
  default_voice_id: string | null
  tags: string[]
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface GlobalLocationAsset {
  id: string
  name: string
  project_id: string | null
  folder_id: string | null
  description: string | null
  prompt_template: string | null
  reference_image_url: string | null
  tags: string[]
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface AssetHubOverview {
  folders: AssetFolder[]
  characters: GlobalCharacterAsset[]
  locations: GlobalLocationAsset[]
  voices: GlobalVoice[]
}
