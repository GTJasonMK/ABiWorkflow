import client from './client'
import type { ApiResponse } from '../types/api'
import type { CostListPayload } from '../types/cost'

export async function listCosts(params?: {
  project_id?: string
  episode_id?: string
  panel_id?: string
  limit?: number
}): Promise<CostListPayload> {
  const resp = await client.get<ApiResponse<CostListPayload>>('/costs', { params })
  return resp.data.data ?? {
    summary: { count: 0, total_cost: 0, total_quantity: 0, currency: 'USD', by_provider: [] },
    items: [],
  }
}

export async function getProjectCosts(projectId: string, limit = 200): Promise<CostListPayload> {
  const resp = await client.get<ApiResponse<CostListPayload>>(`/projects/${projectId}/costs`, {
    params: { limit },
  })
  return resp.data.data ?? {
    summary: { count: 0, total_cost: 0, total_quantity: 0, currency: 'USD', by_provider: [] },
    items: [],
  }
}
