import { useState } from 'react'
import {
  Button,
  Card,
  Checkbox,
  Empty,
  Input,
  Popconfirm,
  Space,
  Typography,
} from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { Episode } from '../../types/episode'
import type { Panel } from '../../types/panel'
import type { AssetTabKey } from './types'
import DndPanelList from './DndPanelList'

const { Text } = Typography

interface PanelListPanelProps {
  episodes: Episode[]
  activeEpisodeId: string | null
  activePanels: Panel[]
  newPanelTitle: string
  onNewPanelTitleChange: (value: string) => void
  onCreatePanel: () => void
  onEditPanel: (panel: Panel) => void
  onDeletePanel: (panel: Panel) => void
  onBatchDeletePanels?: (panels: Panel[]) => void
  onReorderPanels: (panelIds: string[]) => void
  onOpenAssetDrawer: (panel: Panel, tab?: AssetTabKey) => void
}

export default function PanelListPanel({
  episodes,
  activeEpisodeId,
  activePanels,
  newPanelTitle,
  onNewPanelTitleChange,
  onCreatePanel,
  onEditPanel,
  onDeletePanel,
  onBatchDeletePanels,
  onReorderPanels,
  onOpenAssetDrawer,
}: PanelListPanelProps) {
  const activeEpisodeTitle = episodes.find((item) => item.id === activeEpisodeId)?.title ?? ''
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const selectedPanels = activePanels.filter((p) => selectedIds.has(p.id))
  const allSelected = activePanels.length > 0 && selectedIds.size === activePanels.length

  const handleSelectAll = (checked: boolean) => {
    setSelectedIds(checked ? new Set(activePanels.map((p) => p.id)) : new Set())
  }

  const handleBatchDelete = () => {
    if (onBatchDeletePanels && selectedPanels.length > 0) {
      onBatchDeletePanels(selectedPanels)
      setSelectedIds(new Set())
    }
  }

  return (
    <aside className="np-scene-column np-scene-column-main">
      <Card
        title={activeEpisodeId ? `分镜列表（${activeEpisodeTitle}）` : '分镜列表'}
        className="np-panel-card np-scene-panel-card"
        styles={{ body: { display: 'flex', flexDirection: 'column', gap: 12, flex: 1, minHeight: 0 } }}
      >
        {!activeEpisodeId ? (
          <Empty description="请先选择分集" />
        ) : (
          <>
            <Space.Compact>
              <Input
                value={newPanelTitle}
                onChange={(event) => onNewPanelTitleChange(event.target.value)}
                placeholder="新分镜标题"
                aria-label="新分镜标题"
                onPressEnter={onCreatePanel}
              />
              <Button type="primary" icon={<PlusOutlined />} onClick={onCreatePanel}>
                新增分镜
              </Button>
            </Space.Compact>

            {activePanels.length === 0 ? (
              <Empty description="暂无分镜，请新增" />
            ) : (
              <div className="np-panel-list-scroll">
                <Space size={8} style={{ marginBottom: 8 }} wrap>
                  <Checkbox
                    checked={allSelected}
                    indeterminate={selectedIds.size > 0 && !allSelected}
                    onChange={(e) => handleSelectAll(e.target.checked)}
                    aria-label="全选分镜"
                  >
                    全选
                  </Checkbox>
                  {selectedIds.size > 0 ? (
                    <>
                      <Text type="secondary">已选 {selectedIds.size} 项</Text>
                      <Popconfirm
                        title={`确认批量删除 ${selectedIds.size} 个分镜？`}
                        onConfirm={handleBatchDelete}
                      >
                        <Button size="small" danger icon={<DeleteOutlined />} aria-label="批量删除">
                          批量删除
                        </Button>
                      </Popconfirm>
                    </>
                  ) : (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      拖拽左侧手柄可调整顺序
                    </Text>
                  )}
                </Space>
                <DndPanelList
                  panels={activePanels}
                  selectedIds={selectedIds}
                  onSelectionChange={setSelectedIds}
                  onReorder={onReorderPanels}
                  onEditPanel={onEditPanel}
                  onDeletePanel={onDeletePanel}
                  onOpenAssetDrawer={onOpenAssetDrawer}
                />
              </div>
            )}
          </>
        )}
      </Card>
    </aside>
  )
}
