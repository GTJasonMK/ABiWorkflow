import { Tag } from 'antd'

const STATUS_LABEL_MAP: Record<string, string> = {
  draft: '草稿',
  idle: '未开始',
  pending: '待处理',
  queued: '已排队',
  running: '运行中',
  processing: '处理中',
  parsing: '解析中',
  parsed: '已解析',
  generating: '生成中',
  generated: '已生成',
  composing: '合成中',
  completed: '已完成',
  succeeded: '已完成',
  failed: '失败',
}

const STATUS_CLASS_MAP: Record<string, string> = {
  queued: 'np-status-parsing',
  running: 'np-status-generating',
  parsed: 'np-status-parsed',
  generated: 'np-status-generated',
  completed: 'np-status-completed',
  succeeded: 'np-status-completed',
  parsing: 'np-status-parsing',
  generating: 'np-status-generating',
  composing: 'np-status-composing',
  failed: 'np-status-failed',
}

interface PanelStatusTagProps {
  status: string
}

export default function PanelStatusTag({ status }: PanelStatusTagProps) {
  const label = STATUS_LABEL_MAP[status] ?? status
  const statusClass = STATUS_CLASS_MAP[status] ?? ''
  return (
    <Tag className={`np-status-tag ${statusClass}`.trim()}>
      {label}
    </Tag>
  )
}
