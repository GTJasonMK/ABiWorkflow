export interface EpisodeProviderPayloadDefaults {
  video: Record<string, unknown>
  tts: Record<string, unknown>
  lipsync: Record<string, unknown>
}

export interface EpisodeWorkflowChecks {
  script_ready: boolean
  providers_ready: boolean
  asset_binding_ready: boolean
  panels_ready: boolean
  voice_ready: boolean
  video_ready: boolean
  compose_ready: boolean
  composed: boolean
}

export interface EpisodeWorkflowCounts {
  required_characters: number
  bound_characters: number
  required_locations: number
  bound_locations: number
  panel_total: number
  panel_video_done: number
  panel_tts_done: number
  panel_lipsync_done: number
}

export interface EpisodeWorkflowSummary {
  current_step: string
  completion_percent: number
  checks: EpisodeWorkflowChecks
  counts: EpisodeWorkflowCounts
  blockers: string[]
  skipped_checks: string[]
}

export interface Episode {
  id: string
  project_id: string
  episode_order: number
  title: string
  summary: string | null
  script_text: string | null
  video_provider_key: string | null
  tts_provider_key: string | null
  lipsync_provider_key: string | null
  provider_payload_defaults: EpisodeProviderPayloadDefaults
  skipped_checks: string[]
  status: string
  panel_count: number
  workflow_summary: EpisodeWorkflowSummary
  created_at: string
  updated_at: string
}
