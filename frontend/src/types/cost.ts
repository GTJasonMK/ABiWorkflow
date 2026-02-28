export interface CostSummary {
  count: number
  total_cost: number
  total_quantity: number
  currency: string
  by_provider: Array<{
    provider_type: string
    count: number
    total_cost: number
  }>
}

export interface CostItem {
  id: string
  project_id: string | null
  episode_id: string | null
  panel_id: string | null
  task_id: string | null
  provider_type: string
  provider_name: string | null
  model_name: string | null
  usage_type: string
  quantity: number
  unit: string
  unit_price: number
  total_cost: number
  currency: string
  metadata: Record<string, unknown>
  created_at: string | null
}

export interface CostListPayload {
  summary: CostSummary
  items: CostItem[]
}
