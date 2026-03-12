import client from './client'
import type { ApiResponse, PaginatedResponse } from '../types/api'
import type { EpisodeProviderPayloadDefaults } from '../types/episode'
import type { Project, ProjectCreate, ProjectListItem, ProjectUpdate, ProjectWorkspace } from '../types/project'

/** 项目列表查询参数 */
export interface ListProjectsParams {
  page?: number
  pageSize?: number
  keyword?: string
  status?: string
  sort_by?: string
  sort_order?: string
}

export interface ProjectScriptWorkspaceEpisodePayload {
  id?: string
  title?: string | null
  summary?: string | null
  script_text?: string | null
  video_provider_key?: string | null
  tts_provider_key?: string | null
  lipsync_provider_key?: string | null
  provider_payload_defaults?: EpisodeProviderPayloadDefaults
  skipped_checks?: string[]
}

export interface ProjectScriptWorkspacePayload {
  script_text: string
  workflow_defaults: NonNullable<ProjectCreate['workflow_defaults']>
  episodes: ProjectScriptWorkspaceEpisodePayload[]
}

/** 创建项目 */
export async function createProject(data: ProjectCreate): Promise<Project> {
  const resp = await client.post<ApiResponse<Project>>('/projects', data)
  return resp.data.data!
}

/** 获取项目列表 */
export async function listProjects(params: ListProjectsParams = {}): Promise<PaginatedResponse<ProjectListItem>> {
  const { page = 1, pageSize = 20, keyword, status, sort_by, sort_order } = params
  const resp = await client.get<ApiResponse<PaginatedResponse<ProjectListItem>>>('/projects', {
    params: {
      page,
      page_size: pageSize,
      ...(keyword ? { keyword } : {}),
      ...(status ? { status } : {}),
      ...(sort_by ? { sort_by } : {}),
      ...(sort_order ? { sort_order } : {}),
    },
  })
  return resp.data.data!
}

/** 获取项目工作台聚合信息 */
export async function getProjectWorkspace(id: string): Promise<ProjectWorkspace> {
  const resp = await client.get<ApiResponse<ProjectWorkspace>>(`/projects/${id}/workspace`)
  return resp.data.data!
}

/** 更新项目 */
export async function updateProject(id: string, data: ProjectUpdate): Promise<Project> {
  const resp = await client.put<ApiResponse<Project>>(`/projects/${id}`, data)
  return resp.data.data!
}

/** 保存剧本分集工作台 */
export async function updateProjectScriptWorkspace(
  id: string,
  data: ProjectScriptWorkspacePayload,
): Promise<ProjectWorkspace> {
  const resp = await client.put<ApiResponse<ProjectWorkspace>>(`/projects/${id}/script-workspace`, data)
  return resp.data.data!
}

/** 删除项目 */
export async function deleteProject(id: string): Promise<void> {
  await client.delete(`/projects/${id}`)
}

/** 复制项目 */
export async function duplicateProject(id: string): Promise<Project> {
  const resp = await client.post<ApiResponse<Project>>(`/projects/${id}/duplicate`)
  return resp.data.data!
}

/** 中止项目当前任务（解析/生成/合成），恢复为可操作状态 */
export async function abortProjectTask(id: string): Promise<{ aborted: boolean; status: string; message: string }> {
  const resp = await client.post<ApiResponse<{ aborted: boolean; status: string; message: string }>>(`/projects/${id}/abort`)
  return resp.data.data!
}
