import { create } from 'zustand'
import type { Project, ProjectListItem } from '../types/project'
import type { ListProjectsParams } from '../api/projects'
import * as projectApi from '../api/projects'

interface ProjectState {
  /** 项目列表 */
  projects: ProjectListItem[]
  /** 总数 */
  total: number
  /** 当前页 */
  page: number
  /** 加载状态 */
  loading: boolean
  /** 当前项目详情 */
  currentProject: Project | null
  /** 全局状态统计（各状态的项目数量） */
  stats: Record<string, number>
  /** 当前搜索/筛选/排序参数（不含分页） */
  listParams: Omit<ListProjectsParams, 'page' | 'pageSize'>

  /** 加载项目列表 */
  fetchProjects: (params?: ListProjectsParams) => Promise<void>
  /** 创建项目 */
  createProject: (name: string, description?: string) => Promise<Project>
  /** 加载项目详情 */
  fetchProject: (id: string) => Promise<void>
  /** 更新项目 */
  updateProject: (id: string, data: { name?: string; description?: string; script_text?: string }) => Promise<void>
  /** 删除项目 */
  deleteProject: (id: string) => Promise<void>
  /** 复制项目 */
  duplicateProject: (id: string) => Promise<Project>
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  total: 0,
  page: 1,
  loading: false,
  currentProject: null,
  stats: {},
  listParams: {},

  fetchProjects: async (params) => {
    // 合并传入参数与已保存的搜索/筛选/排序条件
    const prev = get().listParams
    const merged: ListProjectsParams = { ...prev, ...params }
    const rest = Object.fromEntries(
      Object.entries(merged).filter(([key]) => key !== 'page' && key !== 'pageSize'),
    ) as Omit<ListProjectsParams, 'page' | 'pageSize'>
    set({ loading: true, listParams: rest })
    try {
      const data = await projectApi.listProjects(merged)
      set({
        projects: data.items,
        total: data.total,
        page: data.page,
        stats: data.stats ?? {},
      })
    } finally {
      set({ loading: false })
    }
  },

  createProject: async (name, description) => {
    const project = await projectApi.createProject({ name, description })
    await get().fetchProjects({ page: get().page })
    return project
  },

  fetchProject: async (id) => {
    set({ loading: true })
    try {
      const project = await projectApi.getProject(id)
      set({ currentProject: project })
    } finally {
      set({ loading: false })
    }
  },

  updateProject: async (id, data) => {
    const project = await projectApi.updateProject(id, data)
    set({ currentProject: project })
  },

  deleteProject: async (id) => {
    await projectApi.deleteProject(id)
    await get().fetchProjects({ page: get().page })
  },

  duplicateProject: async (id) => {
    const project = await projectApi.duplicateProject(id)
    await get().fetchProjects({ page: get().page })
    return project
  },
}))
