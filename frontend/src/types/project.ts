import type { Episode } from './episode'

/** 项目状态 */
export type ProjectStatus = 'draft' | 'parsing' | 'parsed' | 'generating' | 'composing' | 'completed' | 'failed'

export interface WorkflowDefaults {
  video_provider_key: string | null
  tts_provider_key: string | null
  lipsync_provider_key: string | null
  provider_payload_defaults: {
    video: Record<string, unknown>
    tts: Record<string, unknown>
    lipsync: Record<string, unknown>
  }
}

/** 项目 */
export interface Project {
  id: string
  name: string
  description: string | null
  script_text: string | null
  status: ProjectStatus
  episode_count: number
  panel_count: number
  generated_panel_count: number
  character_count: number
  workflow_defaults: WorkflowDefaults
  created_at: string
  updated_at: string
}

/** 项目列表项 */
export interface ProjectListItem {
  id: string
  name: string
  description: string | null
  status: ProjectStatus
  episode_count: number
  panel_count: number
  generated_panel_count: number
  character_count: number
  created_at: string
  updated_at: string
}

/** 创建项目请求 */
export interface ProjectCreate {
  name: string
  description?: string
  workflow_defaults?: Partial<WorkflowDefaults>
}

/** 更新项目请求 */
export interface ProjectUpdate {
  name?: string
  description?: string
  script_text?: string
  workflow_defaults?: Partial<WorkflowDefaults> | null
}

export interface ProjectWorkspaceResourceSummary {
  character_entity_count: number
  bound_character_entity_count: number
  location_entity_count: number
  bound_location_entity_count: number
  voice_asset_count: number
  panel_count: number
  clip_count: number
  ready_clip_count: number
  failed_clip_count: number
  composition_count: number
}

export interface ProjectWorkspacePreview {
  id: string
  status: string
  duration_seconds: number
  created_at: string | null
  updated_at: string | null
}

export interface ProjectWorkspace {
  project: Project
  episodes: Episode[]
  resource_summary: ProjectWorkspaceResourceSummary
  latest_preview: ProjectWorkspacePreview | null
  recommended_episode_id: string | null
  recommended_step: string
}

/** 状态标签颜色映射 */
export const STATUS_MAP: Record<ProjectStatus, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  parsing: { label: '解析中', color: 'processing' },
  parsed: { label: '已解析', color: 'cyan' },
  generating: { label: '生成中', color: 'processing' },
  composing: { label: '合成中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
}
