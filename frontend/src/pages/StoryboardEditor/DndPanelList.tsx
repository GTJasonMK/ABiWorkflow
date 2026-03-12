import { useState } from 'react'
import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  Button,
  Popconfirm,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  DeleteOutlined,
  HolderOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import type { Panel } from '../../types/panel'
import type { AssetTabKey } from './types'
import { summarizePanelBinding } from '../../utils/panelBinding'
import PanelStatusTag from '../../components/PanelStatusTag'

const { Text } = Typography

interface DndPanelListProps {
  panels: Panel[]
  activePanelId: string | null
  onReorder: (panelIds: string[]) => void
  onSelectPanel: (panel: Panel) => void
  onDeletePanel: (panel: Panel) => void
  onOpenAssetDrawer: (panel: Panel, tab?: AssetTabKey) => void
}

function SortablePanelItem({
  panel,
  index,
  active,
  onSelectPanel,
  onDeletePanel,
  onOpenAssetDrawer,
}: {
  panel: Panel
  index: number
  active: boolean
  onSelectPanel: (panel: Panel) => void
  onDeletePanel: (panel: Panel) => void
  onOpenAssetDrawer: (panel: Panel, tab?: AssetTabKey) => void
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: panel.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  }

  const itemSummary = summarizePanelBinding(panel)
  const effectivePrompt = itemSummary.effectivePrompt ?? null
  const promptPreview = effectivePrompt
    ? effectivePrompt.length > 60
      ? `${effectivePrompt.slice(0, 60)}...`
      : effectivePrompt
    : null

  return (
    <div
      ref={setNodeRef}
      style={{
        ...style,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        padding: '8px 10px',
        borderBottom: '1px solid var(--np-muted)',
        background: active ? 'var(--np-panel)' : undefined,
        cursor: 'pointer',
      }}
      className={`np-panel-item${active ? ' is-active' : ''}`}
      role="button"
      aria-label={`选择分镜 ${panel.title}`}
      tabIndex={0}
      onClick={() => onSelectPanel(panel)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault()
          onSelectPanel(panel)
        }
      }}
    >
      <div
        {...attributes}
        {...listeners}
        style={{
          cursor: 'grab',
          padding: '4px 2px',
          color: 'var(--np-text-soft)',
          flexShrink: 0,
          marginTop: 2,
        }}
        aria-label="拖拽排序"
        onClick={(event) => event.stopPropagation()}
      >
        <HolderOutlined />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <Text strong>{index + 1}. {panel.title}</Text>
        <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 4 }}>
          <Space size={8} wrap>
            <PanelStatusTag status={panel.status} />
            <Text type="secondary">{panel.duration_seconds.toFixed(1)} 秒</Text>
            {itemSummary.characterNames.length > 0 ? <Tag className="np-status-tag">角色</Tag> : null}
            {itemSummary.locationNames.length > 0 ? <Tag className="np-status-tag">地点</Tag> : null}
            {itemSummary.voiceId || itemSummary.voiceName ? (
              <Tag className="np-status-tag">语音</Tag>
            ) : null}
          </Space>
          {promptPreview ? (
            <Text type="secondary" style={{ fontSize: 12 }}>{promptPreview}</Text>
          ) : null}
          {panel.video_url ? (
            <video
              src={panel.video_url}
              style={{ width: 120, height: 68, objectFit: 'cover', borderRadius: 0 }}
              muted
              preload="metadata"
            />
          ) : null}
        </Space>
      </div>

      <Space size={4} style={{ flexShrink: 0 }}>
        <Tooltip title="分镜资产覆盖（角色/地点/语音）">
          <Button
            size="small"
            icon={<LinkOutlined />}
            onClick={(event) => {
              event.stopPropagation()
              onOpenAssetDrawer(panel)
            }}
            aria-label="分镜资产覆盖"
          />
        </Tooltip>
        <Popconfirm
          title="确认删除该分镜？"
          onConfirm={() => onDeletePanel(panel)}
        >
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            aria-label="删除分镜"
            onClick={(event) => event.stopPropagation()}
          />
        </Popconfirm>
      </Space>
    </div>
  )
}

function DragOverlayItem({ panel, index }: { panel: Panel; index: number }) {
  return (
    <div
      style={{
        background: 'var(--np-bg)',
        border: '1px solid var(--np-accent)',
        borderRadius: 4,
        padding: '8px 12px',
        boxShadow: 'var(--np-surface-shadow)',
      }}
    >
      <Text strong>{index + 1}. {panel.title}</Text>
    </div>
  )
}

export default function DndPanelList({
  panels,
  activePanelId,
  onReorder,
  onSelectPanel,
  onDeletePanel,
  onOpenAssetDrawer,
}: DndPanelListProps) {
  const [activeId, setActiveId] = useState<string | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  const panelIds = panels.map((p) => p.id)

  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(String(event.active.id))
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setActiveId(null)

    if (!over || active.id === over.id) return

    const oldIndex = panelIds.indexOf(String(active.id))
    const newIndex = panelIds.indexOf(String(over.id))

    if (oldIndex === -1 || newIndex === -1) return

    const newIds = arrayMove(panelIds, oldIndex, newIndex)
    onReorder(newIds)
  }

  const activePanel = activeId ? panels.find((p) => p.id === activeId) : null
  const activePanelIndex = activeId ? panelIds.indexOf(activeId) : -1

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={panelIds} strategy={verticalListSortingStrategy}>
        {panels.map((panel, index) => (
          <SortablePanelItem
            key={panel.id}
            panel={panel}
            index={index}
            active={panel.id === activePanelId}
            onSelectPanel={onSelectPanel}
            onDeletePanel={onDeletePanel}
            onOpenAssetDrawer={onOpenAssetDrawer}
          />
        ))}
      </SortableContext>
      <DragOverlay>
        {activePanel ? (
          <DragOverlayItem panel={activePanel} index={activePanelIndex} />
        ) : null}
      </DragOverlay>
    </DndContext>
  )
}
