type ApiErrorWithDetail = {
  response?: {
    status?: number
    data?: {
      detail?: string
    }
  }
}

/**
 * 判断后端是否返回了“可使用 force_recover=true 重试”的提示。
 */
export function shouldSuggestForceRecover(error: unknown): boolean {
  const err = error as ApiErrorWithDetail
  const status = err?.response?.status
  const detail = err?.response?.data?.detail
  return status === 409 && typeof detail === 'string' && detail.includes('force_recover=true')
}
