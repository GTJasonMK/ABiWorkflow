export interface TaskEventMessage {
  event_no: number
  id: string
  task_id: string
  project_id: string | null
  episode_id: string | null
  panel_id: string | null
  event_type: string
  status: string | null
  progress_percent: number | null
  message: string | null
  payload: Record<string, unknown>
  created_at: string | null
}

export interface TaskSseOptions {
  projectId?: string
  episodeId?: string
  panelId?: string
  lastEventId?: number
}

function buildSseUrl(options: TaskSseOptions = {}): string {
  const query = new URLSearchParams()
  if (options.projectId) query.set('project_id', options.projectId)
  if (options.episodeId) query.set('episode_id', options.episodeId)
  if (options.panelId) query.set('panel_id', options.panelId)
  if (options.lastEventId && options.lastEventId > 0) query.set('last_event_id', String(options.lastEventId))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return `/api/sse${suffix}`
}

export function createTaskEventSource(options: TaskSseOptions = {}): EventSource {
  return new EventSource(buildSseUrl(options))
}
