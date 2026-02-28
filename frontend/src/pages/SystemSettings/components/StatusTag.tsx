import { Tag } from 'antd'

interface StatusTagProps {
  ok: boolean
  onLabel: string
  offLabel: string
}

export default function StatusTag({ ok, onLabel, offLabel }: StatusTagProps) {
  return (
    <Tag className={ok ? 'np-status-tag np-status-generated' : 'np-status-tag np-status-failed'}>
      {ok ? onLabel : offLabel}
    </Tag>
  )
}
