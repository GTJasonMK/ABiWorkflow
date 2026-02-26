/** 场景角色信息 */
export interface SceneCharacter {
  character_id: string
  character_name: string
  action: string | null
  emotion: string | null
}

/** 视频片段简要信息 */
export interface ClipBrief {
  id: string
  clip_order: number
  candidate_index: number
  is_selected: boolean
  status: string
  duration_seconds: number
  error_message: string | null
}

/** 候选片段详情（含媒体地址） */
export interface CandidateClip {
  id: string
  clip_order: number
  candidate_index: number
  is_selected: boolean
  status: string
  duration_seconds: number
  error_message: string | null
  media_url: string | null
}

/** 视频片段统计摘要 */
export interface ClipSummary {
  total: number
  completed: number
  failed: number
}

/** 场景 */
export interface Scene {
  id: string
  project_id: string
  sequence_order: number
  title: string
  description: string | null
  video_prompt: string | null
  negative_prompt: string | null
  camera_movement: string | null
  setting: string | null
  style_keywords: string | null
  dialogue: string | null
  duration_seconds: number
  transition_hint: string | null
  status: string
  characters: SceneCharacter[]
  clip_summary: ClipSummary
  clips: ClipBrief[]
  created_at: string
  updated_at: string
}

/** 角色档案 */
export interface Character {
  id: string
  project_id: string
  name: string
  appearance: string | null
  personality: string | null
  costume: string | null
  reference_image_url: string | null
  portrait_url: string | null
  created_at: string
  updated_at: string
}
