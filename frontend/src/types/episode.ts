export interface Episode {
  id: string
  project_id: string
  episode_order: number
  title: string
  summary: string | null
  script_text: string | null
  status: string
  panel_count: number
  created_at: string
  updated_at: string
}
