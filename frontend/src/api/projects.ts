import client from './client'
import type { ApiResponse, PaginatedResponse } from '../types/api'
import type { Project, ProjectCreate, ProjectListItem, ProjectUpdate } from '../types/project'

/** 创建项目 */
export async function createProject(data: ProjectCreate): Promise<Project> {
  const resp = await client.post<ApiResponse<Project>>('/projects', data)
  return resp.data.data!
}

/** 获取项目列表 */
export async function listProjects(page = 1, pageSize = 20): Promise<PaginatedResponse<ProjectListItem>> {
  const resp = await client.get<ApiResponse<PaginatedResponse<ProjectListItem>>>('/projects', {
    params: { page, page_size: pageSize },
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
