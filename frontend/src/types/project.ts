/** 项目状态 */
export type ProjectStatus = 'draft' | 'parsing' | 'parsed' | 'generating' | 'composing' | 'completed' | 'failed'

/** 项目 */
export interface Project {
  id: string
  name: string
  description: string | null
  script_text: string | null
  status: ProjectStatus
  scene_count: number
  character_count: number
  created_at: string
  updated_at: string
}

/** 项目列表项 */
export interface ProjectListItem {
  id: string
  name: string
  description: string | null
  status: ProjectStatus
  scene_count: number
  character_count: number
  created_at: string
  updated_at: string
}

/** 创建项目请求 */
export interface ProjectCreate {
  name: string
  description?: string
}

/** 更新项目请求 */
export interface ProjectUpdate {
  name?: string
  description?: string
  script_text?: string
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
