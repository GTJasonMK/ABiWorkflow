export function renderTaskStateLabel(state: string): string {
  switch (state) {
    case 'pending':
    case 'queued':
      return '排队中'
    case 'started':
    case 'processing':
    case 'running':
      return '执行中'
    case 'success':
    case 'completed':
      return '已完成'
    case 'failure':
    case 'failed':
      return '失败'
    case 'timeout':
      return '超时'
    case 'cancelled':
    case 'canceled':
      return '已取消'
    default:
      return state
  }
}

export function renderExtendedTaskType(taskType: string): string {
  if (taskType === 'parse') return '剧本解析'
  if (taskType === 'generate') return '视频生成'
  if (taskType === 'compose') return '视频合成'
  if (taskType === 'video') return '分镜视频'
  if (taskType === 'tts') return '语音生成'
  if (taskType === 'lipsync') return '口型同步'
  return taskType
}
