import { Progress, Typography } from 'antd'
import { LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import type { ProgressMessage } from '../../hooks/useWebSocket'

const { Text } = Typography

interface Props {
  lastMessage: ProgressMessage | null
  connected: boolean
  active?: boolean
  activeText?: string
  idleText?: string
}

/** 从消息类型推断状态 */
function getStepStatus(type: string): 'process' | 'finish' | 'error' | 'wait' {
  if (type.endsWith('_complete')) return 'finish'
  if (type.endsWith('_failed')) return 'error'
  if (type.endsWith('_start') || type.endsWith('_progress')) return 'process'
  return 'wait'
}

export default function ProgressBar({
  lastMessage,
  connected,
  active = false,
  activeText = '任务执行中...',
  idleText = '等待中...',
}: Props) {
  const latestData = lastMessage?.data ?? {}
  const percent = (latestData.percent as number) ?? 0
  const message = (latestData.message as string) ?? ''
  const status = lastMessage ? getStepStatus(lastMessage.type) : active ? 'process' : 'wait'
  const displayText = message || (active ? activeText : idleText)
  const showIndeterminate = active && percent <= 0

  return (
    <div className="np-progress-shell">
      <div className="np-progress-title">
        {status === 'process' && <LoadingOutlined spin />}
        {status === 'finish' && <CheckCircleOutlined style={{ color: '#52c41a' }} />}
        {status === 'error' && <CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
        <Text strong>{displayText}</Text>
        {!connected && <Text type="secondary">{active ? '（实时进度不可用，显示加载动画）' : '（未连接）'}</Text>}
      </div>

      {percent > 0 && (
        <Progress
          percent={percent}
          status={status === 'error' ? 'exception' : status === 'finish' ? 'success' : 'active'}
          size="small"
        />
      )}

      {showIndeterminate && <div className="np-progress-indeterminate" />}
    </div>
  )
}
