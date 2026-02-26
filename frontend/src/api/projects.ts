import client from './client'
import type { ApiResponse, PaginatedResponse } from '../types/api'
import type { Project, ProjectCreate, ProjectListItem, ProjectUpdate } from '../types/project'

/** 项目列表查询参数 */
export interface ListProjectsParams {
  page?: number
  pageSize?: number
  keyword?: string
  status?: string
  sort_by?: string
  sort_order?: string
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

/** 获取项目详情 */
export async function getProject(id: string): Promise<Project> {
  const resp = await client.get<ApiResponse<Project>>(`/projects/${id}`)
  return resp.data.data!
}

/** 更新项目 */
export async function updateProject(id: string, data: ProjectUpdate): Promise<Project> {
  const resp = await client.put<ApiResponse<Project>>(`/projects/${id}`, data)
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
