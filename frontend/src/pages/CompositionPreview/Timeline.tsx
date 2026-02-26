import { useCallback } from 'react'
import { Card, Tag, Typography, App as AntdApp } from 'antd'
import { VideoCameraOutlined } from '@ant-design/icons'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  horizontalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { Scene } from '../../types/scene'
import { getApiErrorMessage } from '../../utils/error'

const { Text } = Typography

interface Props {
  scenes: Scene[]
  projectId: string
  onReorder: (projectId: string, sceneIds: string[]) => Promise<void>
}

function SortableTimelineItem({ scene, idx }: { scene: Scene; idx: number }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: scene.id })

  const widthPercent = Math.max(60, scene.duration_seconds * 20)
  const ready = scene.status === 'generated' || scene.status === 'completed'
  const { clip_summary } = scene

  const style = {
    minWidth: widthPercent,
    flex: `0 0 ${widthPercent}px`,
    borderColor: ready ? '#1f7a1f' : '#111111',
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    cursor: 'grab',
    touchAction: 'none' as const,
  }

  return (
    <Card
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      className="np-timeline-item"
      size="small"
      style={style}
      styles={{ body: { padding: 8 } }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
        <VideoCameraOutlined style={{ fontSize: 12 }} />
        <Text ellipsis style={{ fontSize: 12, fontWeight: 500 }}>
          {idx + 1}. {scene.title}
        </Text>
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {scene.duration_seconds}s
        </Text>
        {clip_summary.total > 0 && (
          <Tag style={{ fontSize: 10, lineHeight: '16px', margin: 0, padding: '0 4px' }}
            className={clip_summary.failed > 0 ? 'np-status-tag np-status-failed' : 'np-status-tag'}>
            {clip_summary.completed}/{clip_summary.total}
          </Tag>
        )}
        {scene.characters.length > 0 && (
          <Text type="secondary" style={{ fontSize: 10 }}>
            {scene.characters.length}角色
          </Text>
        )}
      </div>
      {scene.transition_hint && (
        <Text type="secondary" style={{ fontSize: 10, display: 'block' }}>
          → {scene.transition_hint}
        </Text>
      )}
    </Card>
  )
}

export default function Timeline({ scenes, projectId, onReorder }: Props) {
  const { message } = AntdApp.useApp()
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  )

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id) return

      const oldIndex = scenes.findIndex((s) => s.id === active.id)
      const newIndex = scenes.findIndex((s) => s.id === over.id)
      if (oldIndex === -1 || newIndex === -1) return

      const newSceneIds = scenes.map((s) => s.id)
      const [moved] = newSceneIds.splice(oldIndex, 1)
      newSceneIds.splice(newIndex, 0, moved!)

      onReorder(projectId, newSceneIds).catch((error) => {
        message.error(getApiErrorMessage(error, '时间线排序失败'))
      })
    },
    [scenes, projectId, onReorder, message],
  )

  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
        <Text strong>时间线</Text>
        <Text type="secondary">({scenes.length} 个场景 · 拖拽调整顺序)</Text>
      </div>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={scenes.map((s) => s.id)}
          strategy={horizontalListSortingStrategy}
        >
          <div style={{ display: 'flex', gap: 4, overflowX: 'auto', paddingBottom: 8 }}>
            {scenes.map((scene, idx) => (
              <SortableTimelineItem key={scene.id} scene={scene} idx={idx} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
      <div style={{ borderTop: '2px solid #111111', marginTop: 4 }} />
    </div>
  )
}
