import type { TaskRecord } from '../types/taskRecord'

export type TaskScope = 'project' | 'episode' | 'panel'
export type TaskScopeFilter = 'all' | TaskScope

export function shortTaskId(value: string | null | undefined, length = 8): string {
  if (!value) return '-'
  return value.slice(0, length)
}

export function resolveTaskEpisodeId(task: TaskRecord): string | null {
  if (task.episode_id) return task.episode_id
  const payloadEpisodeIdRaw = task.payload?.['episode_id']
  if (typeof payloadEpisodeIdRaw !== 'string') return null
  const trimmed = payloadEpisodeIdRaw.trim()
  return trimmed || null
}

export function resolveTaskScope(task: TaskRecord): TaskScope {
  if (task.panel_id) return 'panel'
  if (resolveTaskEpisodeId(task)) return 'episode'
  return 'project'
}

export function resolveTaskScopeLabel(task: TaskRecord): string {
  const scope = resolveTaskScope(task)
  if (scope === 'panel') return `分镜 ${shortTaskId(task.panel_id)}`
  if (scope === 'episode') return `分集 ${shortTaskId(resolveTaskEpisodeId(task))}`
  return '全项目'
}
