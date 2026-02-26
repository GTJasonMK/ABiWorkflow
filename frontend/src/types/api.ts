/** 统一 API 响应 */
export interface ApiResponse<T> {
  success: boolean
  data: T | null
  error: string | null
}

/** 分页响应 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  stats?: Record<string, number>
}
