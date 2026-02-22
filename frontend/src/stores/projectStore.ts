import { create } from 'zustand'
import type { Project, ProjectListItem } from '../types/project'
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

  /** 加载项目列表 */
  fetchProjects: (page?: number) => Promise<void>
  /** 创建项目 */
  createProject: (name: string, description?: string) => Promise<Project>
  /** 加载项目详情 */
  fetchProject: (id: string) => Promise<void>
  /** 更新项目 */
  updateProject: (id: string, data: { name?: string; description?: string; script_text?: string }) => Promise<void>
  /** 删除项目 */
  deleteProject: (id: string) => Promise<void>
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  total: 0,
  page: 1,
  loading: false,
  currentProject: null,

  fetchProjects: async (page = 1) => {
    set({ loading: true })
    try {
      const data = await projectApi.listProjects(page)
      set({ projects: data.items, total: data.total, page: data.page })
    } finally {
      set({ loading: false })
    }
  },

  createProject: async (name, description) => {
    const project = await projectApi.createProject({ name, description })
    await get().fetchProjects(get().page)
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
    await get().fetchProjects(get().page)
  },
}))
