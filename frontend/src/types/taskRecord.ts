export interface TaskRecord {
  id: string
  task_id: string
  source_task_id: string | null
  task_type: string
  target_type: string | null
  target_id: string | null
  project_id: string | null
  episode_id: string | null
  panel_id: string | null
  status: string
  state: string
  ready: boolean
  successful: boolean
  dismissed: boolean
  progress_percent: number
  message: string | null
  payload: Record<string, unknown>
  result: Record<string, unknown>
  error: string | null
  retry_count: number
  started_at: string | null
  finished_at: string | null
  created_at: string | null
  updated_at: string | null
}
