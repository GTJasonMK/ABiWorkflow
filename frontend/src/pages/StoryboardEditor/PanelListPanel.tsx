import {
  Button,
  Card,
  Empty,
  Input,
  Popconfirm,
  Space,
  Typography,
} from 'antd'
import { PlusOutlined, RobotOutlined } from '@ant-design/icons'
import type { Panel } from '../../types/panel'
import type { AssetTabKey } from './types'
import DndPanelList from './DndPanelList'

const { Text } = Typography

interface PanelListPanelProps {
  activeEpisodeId: string | null
  activeEpisodeTitle: string
  activePanels: Panel[]
  selectedPanelId: string | null
  newPanelTitle: string
  generating: boolean
  onNewPanelTitleChange: (value: string) => void
  onCreatePanel: () => void
  onSelectPanel: (panel: Panel) => void
  onDeletePanel: (panel: Panel) => void
  onReorderPanels: (panelIds: string[]) => void
  onOpenAssetDrawer: (panel: Panel, tab?: AssetTabKey) => void
  onGeneratePanels: () => void
}

export default function PanelListPanel({
  activeEpisodeId,
  activeEpisodeTitle,
  activePanels,
  selectedPanelId,
  newPanelTitle,
  generating,
  onNewPanelTitleChange,
  onCreatePanel,
  onSelectPanel,
  onDeletePanel,
  onReorderPanels,
  onOpenAssetDrawer,
  onGeneratePanels,
}: PanelListPanelProps) {
  return (
    <aside className="np-storyboard-column np-storyboard-column-main">
      <Card
        title={activeEpisodeId ? `分镜列表 · ${activeEpisodeTitle}（${activePanels.length}）` : '分镜列表'}
        className="np-panel-card np-storyboard-panel-card"
        styles={{ body: { display: 'flex', flexDirection: 'column', gap: 12, flex: 1, minHeight: 0 } }}
        extra={activeEpisodeId ? (
          <Popconfirm
            title="确认生成分镜？"
            description={activePanels.length > 0
              ? '将覆盖当前分集的全部分镜内容（不可恢复）。'
              : '将根据当前分集的剧本内容自动生成分镜。'}
            okText="确认生成"
            cancelText="取消"
            onConfirm={onGeneratePanels}
            okButtonProps={activePanels.length > 0 ? { danger: true } : undefined}
          >
            <Button icon={<RobotOutlined />} loading={generating}>
              AI 生成分镜
            </Button>
          </Popconfirm>
        ) : null}
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
              <Empty description="暂无分镜：可手动新增，或点击「AI 生成分镜」" />
            ) : (
              <div className="np-panel-list-scroll">
                <Text type="secondary" style={{ fontSize: 11 }}>
                  点击分镜查看详情；拖拽手柄调整顺序
                </Text>
                <DndPanelList
                  panels={activePanels}
                  activePanelId={selectedPanelId}
                  onReorder={onReorderPanels}
                  onSelectPanel={onSelectPanel}
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
