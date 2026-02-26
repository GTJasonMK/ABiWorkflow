import client from './client'
import { buildAsyncTaskQuery, type StartTaskOptions } from './taskParams'
import type { ApiResponse } from '../types/api'
import type { Scene, CandidateClip } from '../types/scene'

export interface GenerateQueuedResponse {
  task_id: string
  mode: 'async'
  status: string
}

export interface GenerateResultResponse {
  total_scenes: number
  completed: number
  failed: number
}

/** 启动视频生成 */
export async function startGeneration(
  projectId: string,
  options: StartTaskOptions = {},
): Promise<GenerateQueuedResponse | GenerateResultResponse> {
  const query = buildAsyncTaskQuery(options)
  const resp = await client.post<ApiResponse<GenerateQueuedResponse | GenerateResultResponse>>(
    `/projects/${projectId}/generate?${query}`,
    {},
    { timeout: 0 },
  )
  return resp.data.data!
}

/** 重试单个场景 */
export async function retryScene(sceneId: string): Promise<{ scene_id: string; status: string; clips: number }> {
  const resp = await client.post<ApiResponse<{ scene_id: string; status: string; clips: number }>>(
    `/scenes/${sceneId}/retry`,
    {},
    { timeout: 0 },
  )
  return resp.data.data!
}

/** 为场景生成多候选 */
export async function generateCandidates(
  sceneId: string,
  candidateCount: number = 3,
): Promise<{ scene_id: string; generated: number; failed: number }> {
  const resp = await client.post<ApiResponse<{ scene_id: string; generated: number; failed: number }>>(
    `/scenes/${sceneId}/generate-candidates?candidate_count=${candidateCount}`,
    {},
    { timeout: 0 },
  )
  return resp.data.data!
}

/** 获取场景候选列表 */
export async function getSceneCandidates(sceneId: string): Promise<CandidateClip[]> {
  const resp = await client.get<ApiResponse<CandidateClip[]>>(`/scenes/${sceneId}/candidates`)
  return resp.data.data!
}

/** 选择候选片段 */
export async function selectCandidate(sceneId: string, clipId: string): Promise<Scene> {
  const resp = await client.put<ApiResponse<Scene>>(`/scenes/${sceneId}/clips/${clipId}/select`)
  return resp.data.data!
}
