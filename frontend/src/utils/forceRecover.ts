import { getApiErrorMessage } from './error'

type ApiErrorWithDetail = {
  response?: {
    status?: number
    data?: {
      detail?: string
    }
  }
}

/**
 * 判断后端是否返回了"可使用 force_recover=true 重试"的提示。
 */
export function shouldSuggestForceRecover(error: unknown): boolean {
  const err = error as ApiErrorWithDetail
  const status = err?.response?.status
  const detail = err?.response?.data?.detail
  return status === 409 && typeof detail === 'string' && detail.includes('force_recover=true')
}

/**
 * 统一处理可能需要 forceRecover 的错误。
 * 如果错误符合 forceRecover 条件且未处于 forceRecover 模式，弹出确认框让用户选择重试；
 * 否则直接展示错误消息。
 */
export function handleForceRecoverError(
  error: unknown,
  forceRecover: boolean,
  modal: { confirm: (config: {
    title: string
    content: string
    okText: string
    cancelText: string
    onOk: () => Promise<void>
  }) => void },
  message: { error: (content: string) => void },
  options: {
    retryFn: () => Promise<void>
    errorFallback: string
  },
): void {
  if (!forceRecover && shouldSuggestForceRecover(error)) {
    modal.confirm({
      title: '检测到任务可能中断',
      content: '是否强制恢复项目状态并重试？若旧任务仍在执行，可能与新任务冲突。',
      okText: '强制恢复并重试',
      cancelText: '取消',
      onOk: options.retryFn,
    })
    return
  }
  message.error(getApiErrorMessage(error, options.errorFallback))
}
