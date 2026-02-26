import client from './client'
import { buildAsyncTaskQuery, type StartTaskOptions } from './taskParams'
import type { ApiResponse } from '../types/api'
import type { Scene, Character } from '../types/scene'

/** 获取项目的所有场景 */
export async function listScenes(projectId: string): Promise<Scene[]> {
  const resp = await client.get<ApiResponse<Scene[]>>(`/scenes/project/${projectId}`)
  return resp.data.data!
}

/** 获取单个场景 */
export async function getScene(sceneId: string): Promise<Scene> {
  const resp = await client.get<ApiResponse<Scene>>(`/scenes/${sceneId}`)
  return resp.data.data!
}

/** 更新场景 */
export async function updateScene(sceneId: string, data: Partial<Scene>): Promise<Scene> {
  const resp = await client.put<ApiResponse<Scene>>(`/scenes/${sceneId}`, data)
  return resp.data.data!
}

/** 删除场景 */
export async function deleteScene(sceneId: string): Promise<void> {
  await client.delete(`/scenes/${sceneId}`)
}

/** 重新排序场景 */
export async function reorderScenes(projectId: string, sceneIds: string[]): Promise<void> {
  await client.put(`/scenes/project/${projectId}/reorder`, { scene_ids: sceneIds })
}

/** 获取项目角色列表 */
export async function listCharacters(projectId: string): Promise<Character[]> {
  const resp = await client.get<ApiResponse<Character[]>>(`/characters/project/${projectId}`)
  return resp.data.data!
}

/** 更新角色 */
export async function updateCharacter(characterId: string, data: Partial<Character>): Promise<Character> {
  const resp = await client.put<ApiResponse<Character>>(`/characters/${characterId}`, data)
  return resp.data.data!
}

/** 为角色生成立绘 */
export async function generatePortrait(characterId: string): Promise<Character> {
  const resp = await client.post<ApiResponse<Character>>(
    `/characters/${characterId}/portrait`,
    {},
    { timeout: 0 },
  )
  return resp.data.data!
}

export interface ParseQueuedResponse {
  task_id: string
  mode: 'async'
  status: string
}

export interface ParseResultResponse {
  character_count: number
  scene_count: number
}

/** 解析剧本 */
export async function parseScript(
  projectId: string,
  options: StartTaskOptions = {},
): Promise<ParseQueuedResponse | ParseResultResponse> {
  const query = buildAsyncTaskQuery(options)
  const resp = await client.post<ApiResponse<ParseQueuedResponse | ParseResultResponse>>(
    `/projects/${projectId}/parse?${query}`,
    {},
    { timeout: 0 },
  )
  return resp.data.data!
}
