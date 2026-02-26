import { create } from 'zustand'
import type { Scene, Character } from '../types/scene'
import * as sceneApi from '../api/scenes'
import { useTaskStore } from './taskStore'

interface SceneState {
  scenes: Scene[]
  characters: Character[]
  activeProjectId: string | null
  loading: boolean
  parsing: boolean

  fetchScenes: (projectId: string) => Promise<void>
  fetchCharacters: (projectId: string) => Promise<void>
  updateCharacter: (characterId: string, data: Partial<Character>) => Promise<void>
  updateScene: (sceneId: string, data: Partial<Scene>) => Promise<void>
  deleteScene: (sceneId: string, projectId: string) => Promise<void>
  reorderScenes: (projectId: string, sceneIds: string[]) => Promise<void>
  parseScript: (projectId: string, options?: { forceRecover?: boolean }) => Promise<{ character_count: number; scene_count: number }>
}

export const useSceneStore = create<SceneState>((set, get) => ({
  scenes: [],
  characters: [],
  activeProjectId: null,
  loading: false,
  parsing: false,

  fetchScenes: async (projectId) => {
    set((state) => ({
      loading: true,
      activeProjectId: projectId,
      scenes: state.activeProjectId === projectId ? state.scenes : [],
    }))
    try {
      const scenes = await sceneApi.listScenes(projectId)
      set((state) => {
        if (state.activeProjectId !== projectId) return state
        return { scenes }
      })
    } finally {
      set((state) => {
        if (state.activeProjectId !== projectId) return state
        return { loading: false }
      })
    }
  },

  fetchCharacters: async (projectId) => {
    set((state) => ({
      activeProjectId: projectId,
      characters: state.activeProjectId === projectId ? state.characters : [],
    }))
    const characters = await sceneApi.listCharacters(projectId)
    set((state) => {
      if (state.activeProjectId !== projectId) return state
      return { characters }
    })
  },

  updateCharacter: async (characterId, data) => {
    const updated = await sceneApi.updateCharacter(characterId, data)
    set((state) => ({
      characters: state.characters.map((c) => (c.id === characterId ? updated : c)),
      scenes: state.scenes.map((scene) => ({
        ...scene,
        characters: scene.characters.map((item) => (
          item.character_id === characterId
            ? { ...item, character_name: updated.name }
            : item
        )),
      })),
    }))

    // 后端可能因角色参考图变更将关联场景回退为 pending，这里主动回拉场景避免前端状态滞后。
    try {
      const scenes = await sceneApi.listScenes(updated.project_id)
      if (get().activeProjectId === updated.project_id) {
        set({ scenes })
      }
    } catch {
      // 角色编辑已成功，本地保留已更新数据，场景刷新失败不阻塞交互。
    }
  },

  updateScene: async (sceneId, data) => {
    const updated = await sceneApi.updateScene(sceneId, data)
    set((state) => ({
      scenes: state.scenes.map((s) => (s.id === sceneId ? updated : s)),
    }))
  },

  deleteScene: async (sceneId, projectId) => {
    await sceneApi.deleteScene(sceneId)
    await get().fetchScenes(projectId)
  },

  reorderScenes: async (projectId, sceneIds) => {
    await sceneApi.reorderScenes(projectId, sceneIds)
    await get().fetchScenes(projectId)
  },

  parseScript: async (projectId, options = {}) => {
    set({ parsing: true })
    try {
      const startResult = await sceneApi.parseScript(projectId, options)
      let character_count = 0
      let scene_count = 0

      if ('task_id' in startResult) {
        const finalStatus = await useTaskStore.getState().trackTask(
          startResult.task_id,
          { taskType: 'parse', projectId },
          { timeoutMs: 20 * 60 * 1000 },
        )
        const resultData = finalStatus.result ?? {}
        character_count = Number(resultData.character_count ?? 0)
        scene_count = Number(resultData.scene_count ?? 0)
      } else {
        character_count = startResult.character_count
        scene_count = startResult.scene_count
      }

      await get().fetchScenes(projectId)
      await get().fetchCharacters(projectId)
      return { character_count, scene_count }
    } finally {
      set({ parsing: false })
    }
  },
}))
