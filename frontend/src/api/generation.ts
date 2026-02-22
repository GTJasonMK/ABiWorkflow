import client from './client'
import type { ApiResponse } from '../types/api'

/** 启动视频生成 */
export async function startGeneration(projectId: string): Promise<{
  total_scenes: number
  completed: number
  failed: number
}> {
  const resp = await client.post<ApiResponse<{ total_scenes: number; completed: number; failed: number }>>(
    `/projects/${projectId}/generate`
  )
  return resp.data.data!
}

/** 重试单个场景 */
export async function retryScene(sceneId: string): Promise<{ scene_id: string; status: string; clips: number }> {
  const resp = await client.post<ApiResponse<{ scene_id: string; status: string; clips: number }>>(
    `/scenes/${sceneId}/retry`
  )
  return resp.data.data!
}
