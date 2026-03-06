import { Card, Tag, Typography } from 'antd'
import { VideoCameraOutlined } from '@ant-design/icons'
import type { Panel } from '../../types/panel'
import PanelStatusTag from '../../components/PanelStatusTag'

const { Text } = Typography

interface Props {
  panels: Panel[]
}

function TimelineItem({ panel, idx }: { panel: Panel; idx: number }) {
  const widthPercent = Math.max(80, panel.duration_seconds * 24)
  const ready = Boolean(panel.lipsync_video_url || panel.video_url)

  const style = {
    minWidth: widthPercent,
    flex: `0 0 ${widthPercent}px`,
    borderColor: ready ? 'var(--np-success)' : 'var(--np-ink)',
  }

  return (
    <Card
      className="np-timeline-item"
      size="small"
      style={style}
      styles={{ body: { padding: 8 } }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
        <VideoCameraOutlined style={{ fontSize: 12 }} />
        <Text ellipsis style={{ fontSize: 12, fontWeight: 500 }}>
          {idx + 1}. {panel.title}
        </Text>
      </div>
      {panel.video_url ? (
        <video
          src={panel.video_url}
          style={{ width: '100%', height: 48, objectFit: 'cover', borderRadius: 0, marginBottom: 4 }}
          muted
          preload="metadata"
        />
      ) : null}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {panel.duration_seconds.toFixed(1)}s
        </Text>
        <PanelStatusTag status={panel.status} />
        {ready ? <Tag className="np-status-tag">可合成</Tag> : null}
      </div>
    </Card>
  )
}

export default function Timeline({ panels }: Props) {
  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
        <Text strong>时间线</Text>
        <Text type="secondary">({panels.length} 个分镜 · 顺序请在分镜编辑页调整)</Text>
      </div>
      <div style={{ display: 'flex', gap: 4, overflowX: 'auto', paddingBottom: 8 }}>
        {panels.map((panel, idx) => (
          <TimelineItem key={panel.id} panel={panel} idx={idx} />
        ))}
      </div>
      <div style={{ borderTop: '2px solid var(--np-ink)', marginTop: 4 }} />
    </div>
  )
}
