export interface Panel {
  id: string
  project_id: string
  episode_id: string
  panel_order: number
  title: string
  script_text: string | null
  visual_prompt: string | null
  negative_prompt: string | null
  camera_hint: string | null
  duration_seconds: number
  style_preset: string | null
  reference_image_url: string | null
  voice_id: string | null
  voice_binding_json: Record<string, unknown> | null
  tts_text: string | null
  tts_audio_url: string | null
  video_url: string | null
  lipsync_video_url: string | null
  provider_task_id: string | null
  status: string
  error_message: string | null
  created_at: string
  updated_at: string
}
