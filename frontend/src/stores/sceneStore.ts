import { create } from 'zustand'
import type { Scene, Character } from '../types/scene'
import * as sceneApi from '../api/scenes'

interface SceneState {
  scenes: Scene[]
  characters: Character[]
  loading: boolean
  parsing: boolean

  fetchScenes: (projectId: string) => Promise<void>
  fetchCharacters: (projectId: string) => Promise<void>
  updateCharacter: (characterId: string, data: Partial<Character>) => Promise<void>
  updateScene: (sceneId: string, data: Partial<Scene>) => Promise<void>
  deleteScene: (sceneId: string, projectId: string) => Promise<void>
  reorderScenes: (projectId: string, sceneIds: string[]) => Promise<void>
  parseScript: (projectId: string) => Promise<{ character_count: number; scene_count: number }>
}

export const useSceneStore = create<SceneState>((set, get) => ({
  scenes: [],
  characters: [],
  loading: false,
  parsing: false,

  fetchScenes: async (projectId) => {
    set({ loading: true })
    try {
      const scenes = await sceneApi.listScenes(projectId)
      set({ scenes })
    } finally {
      set({ loading: false })
    }
  },

  fetchCharacters: async (projectId) => {
    const characters = await sceneApi.listCharacters(projectId)
    set({ characters })
  },

  updateCharacter: async (characterId, data) => {
    const updated = await sceneApi.updateCharacter(characterId, data)
    set((state) => ({
      characters: state.characters.map((c) => (c.id === characterId ? updated : c)),
    }))
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

  parseScript: async (projectId) => {
    set({ parsing: true })
    try {
      const result = await sceneApi.parseScript(projectId)
      await get().fetchScenes(projectId)
      await get().fetchCharacters(projectId)
      return result
    } finally {
      set({ parsing: false })
    }
  },
}))
