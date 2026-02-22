import { Card, Typography } from 'antd'
import { VideoCameraOutlined, DragOutlined } from '@ant-design/icons'
import type { Scene } from '../../types/scene'

const { Text } = Typography

interface Props {
  scenes: Scene[]
}

export default function Timeline({ scenes }: Props) {
  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
        <DragOutlined />
        <Text strong>时间线</Text>
        <Text type="secondary">({scenes.length} 个场景)</Text>
      </div>
      <div style={{ display: 'flex', gap: 4, overflowX: 'auto', paddingBottom: 8 }}>
        {scenes.map((scene, idx) => {
          const widthPercent = Math.max(60, scene.duration_seconds * 20)
          return (
            <Card
              key={scene.id}
              className="np-timeline-item"
              size="small"
              style={{
                minWidth: widthPercent,
                flex: `0 0 ${widthPercent}px`,
                borderColor: scene.status === 'generated' ? '#1f7a1f' : '#111111',
              }}
              bodyStyle={{ padding: 8 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                <VideoCameraOutlined style={{ fontSize: 12 }} />
                <Text ellipsis style={{ fontSize: 12, fontWeight: 500 }}>
                  {idx + 1}. {scene.title}
                </Text>
              </div>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {scene.duration_seconds}秒
              </Text>
              {scene.transition_hint && (
                <Text type="secondary" style={{ fontSize: 10, display: 'block' }}>
                  → {scene.transition_hint}
                </Text>
              )}
            </Card>
          )
        })}
      </div>
      <div style={{ borderTop: '2px solid #111111', marginTop: 4 }} />
    </div>
  )
}
