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
  Checkbox,
  Popconfirm,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  HolderOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import type { Panel } from '../../types/panel'
import type { AssetTabKey } from './types'
import { parsePanelBinding } from './utils'
import PanelStatusTag from '../../components/PanelStatusTag'

const { Text } = Typography

interface DndPanelListProps {
  panels: Panel[]
  selectedIds?: Set<string>
  onSelectionChange?: (ids: Set<string>) => void
  onReorder: (panelIds: string[]) => void
  onEditPanel: (panel: Panel) => void
  onDeletePanel: (panel: Panel) => void
  onOpenAssetDrawer: (panel: Panel, tab?: AssetTabKey) => void
}

function SortablePanelItem({
  panel,
  index,
  selected,
  onToggleSelect,
  onEditPanel,
  onDeletePanel,
  onOpenAssetDrawer,
}: {
  panel: Panel
  index: number
  selected?: boolean
  onToggleSelect?: (id: string) => void
  onEditPanel: (panel: Panel) => void
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

  const itemBinding = parsePanelBinding(panel)
  const promptPreview = panel.visual_prompt
    ? panel.visual_prompt.length > 60
      ? `${panel.visual_prompt.slice(0, 60)}...`
      : panel.visual_prompt
    : null

  return (
    <div
      ref={setNodeRef}
      style={{
        ...style,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        padding: '8px 0',
        borderBottom: '1px solid var(--np-muted)',
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
      >
        <HolderOutlined />
      </div>

      {onToggleSelect != null ? (
        <Checkbox
          checked={selected}
          onChange={() => onToggleSelect(panel.id)}
          aria-label={`选择分镜 ${panel.title}`}
          style={{ flexShrink: 0, marginTop: 2 }}
        />
      ) : null}

      <div style={{ flex: 1, minWidth: 0 }}>
        <Text strong>{index + 1}. {panel.title}</Text>
        <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 4 }}>
          <Space size={8} wrap>
            <PanelStatusTag status={panel.status} />
            <Text type="secondary">{panel.duration_seconds.toFixed(1)} 秒</Text>
            {itemBinding.asset_character_name ? <Tag className="np-status-tag">角色</Tag> : null}
            {itemBinding.asset_location_name ? <Tag className="np-status-tag">地点</Tag> : null}
            {(itemBinding.asset_voice_id || (panel.effective_binding?.effective_voice as Record<string, unknown> | undefined)?.voice_id) ? (
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
        <Button
          size="small"
          icon={<EditOutlined />}
          onClick={() => onEditPanel(panel)}
          aria-label="编辑分镜"
        />
        <Tooltip title="分镜资产覆盖（角色/地点/语音）">
          <Button
            size="small"
            icon={<LinkOutlined />}
            onClick={() => onOpenAssetDrawer(panel)}
            aria-label="分镜资产覆盖"
          />
        </Tooltip>
        <Popconfirm
          title="确认删除该分镜？"
          onConfirm={() => onDeletePanel(panel)}
        >
          <Button size="small" danger icon={<DeleteOutlined />} aria-label="删除分镜" />
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
  selectedIds,
  onSelectionChange,
  onReorder,
  onEditPanel,
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

  const handleToggleSelect = onSelectionChange
    ? (id: string) => {
      const next = new Set(selectedIds ?? [])
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      onSelectionChange(next)
    }
    : undefined

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
            selected={selectedIds?.has(panel.id)}
            onToggleSelect={handleToggleSelect}
            onEditPanel={onEditPanel}
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
