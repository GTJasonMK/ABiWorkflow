import type { ReactNode } from 'react'
import {
  Button,
  Card,
  Collapse,
  Drawer,
  Empty,
  Image,
  Input,
  List,
  Select,
  Space,
  Switch,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import {
  AudioOutlined,
  EnvironmentOutlined,
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { GlobalCharacterAsset, GlobalLocationAsset, GlobalVoice } from '../../types/assetHub'
import type {
  AssetSourceScope,
  AssetTabKey,
} from './types'
import { getPanelBindingAssetIds, summarizePanelBinding } from '../../utils/panelBinding'
import { sourceScopeTag } from './utils'
import type { UseAssetBindingReturn } from './useAssetBinding'

const { Text } = Typography

type DrawerAssetRowByTab = {
  character: GlobalCharacterAsset
  location: GlobalLocationAsset
  voice: GlobalVoice
}

type DrawerSummaryItem = {
  key: AssetTabKey
  label: string
  value: string
  count: number
}

type DrawerTabConfig<K extends AssetTabKey = AssetTabKey> = {
  key: K
  icon: ReactNode
  title: string
  rows: DrawerAssetRowByTab[K][]
  boundIds: Set<string>
  renderTitle: (item: DrawerAssetRowByTab[K]) => ReactNode
  renderDescription: (item: DrawerAssetRowByTab[K]) => ReactNode
  handleAction: (item: DrawerAssetRowByTab[K]) => void | Promise<void>
}

interface AssetBindingDrawerProps {
  projectId: string
  asset: UseAssetBindingReturn
}

export default function AssetBindingDrawer({ projectId, asset }: AssetBindingDrawerProps) {
  const {
    assetLoading,
    assetSaving,
    assetDrawer,
    assetAdvancedOpen,
    selectedAssetPanel,
    panelBinding,
    filteredCharacters,
    filteredLocations,
    filteredVoices,
    folderMap,
    folderFilterOptions,
    currentAssetSearchText,
    currentFolderFilter,
    currentOnlyBoundFilter,
    currentSourceScope,
    currentVisibleCount,
    currentTabLabel,
    setAssetSearchTextByTab,
    setOnlyBoundFilterByTab,
    setAssetSourceScopeByTab,
    setAssetFolderFilterByTab,
    setAssetAdvancedOpen,
    setAssetDrawer,
    closeAssetDrawer,
    ensureAssetOverview,
    triggerClearBindingForCurrentTab,
    removeAssetFromPanel,
    openCharacterBindPreview,
    openLocationBindPreview,
    applyVoiceToPanel,
    getAssetEmptyText,
  } = asset

  const actionLoading = assetSaving

  const renderSourceLine = (item: { project_id?: string | null; folder_id?: string | null }) => (
    <Text type="secondary">
      来源：{sourceScopeTag(item.project_id, projectId)}
      {' · '}
      目录：{item.folder_id ? (folderMap.get(item.folder_id) ?? '已失效目录') : '未分组'}
    </Text>
  )

  const renderReferenceLink = (referenceImageUrl?: string | null) => (
    referenceImageUrl ? <a href={referenceImageUrl} target="_blank" rel="noreferrer">参考图</a> : null
  )

  const boundAssetIdsByTab: Record<AssetTabKey, Set<string>> = {
    character: new Set(getPanelBindingAssetIds(panelBinding, 'character')),
    location: new Set(getPanelBindingAssetIds(panelBinding, 'location')),
    voice: new Set(getPanelBindingAssetIds(panelBinding, 'voice')),
  }

  const panelSummary = selectedAssetPanel ? summarizePanelBinding(selectedAssetPanel) : null
  const summaryItems: DrawerSummaryItem[] = [
    {
      key: 'character',
      label: '角色',
      value: panelSummary?.characterNames[0] ?? '未绑定',
      count: boundAssetIdsByTab.character.size,
    },
    {
      key: 'location',
      label: '地点',
      value: panelSummary?.locationNames[0] ?? '未绑定',
      count: boundAssetIdsByTab.location.size,
    },
    {
      key: 'voice',
      label: '语音',
      value: panelSummary?.voiceName
        || (panelSummary?.voiceId ? `ID:${panelSummary.voiceId.slice(0, 8)}` : '未绑定'),
      count: boundAssetIdsByTab.voice.size,
    },
  ]

  const tabConfigs: { [K in AssetTabKey]: DrawerTabConfig<K> } = {
    character: {
      key: 'character',
      icon: <UserOutlined />,
      title: '角色',
      rows: filteredCharacters,
      boundIds: boundAssetIdsByTab.character,
      renderTitle: (item) => (
        <Space wrap>
          <Text strong>{item.name}</Text>
          {item.alias ? <Tag className="np-status-tag">别名：{item.alias}</Tag> : null}
        </Space>
      ),
      renderDescription: (item) => (
        <Space direction="vertical" size={2} style={{ width: '100%' }}>
          {renderSourceLine(item)}
          {item.description ? <Text type="secondary">{item.description}</Text> : null}
          <Space size={8} wrap>
            {item.default_voice_id ? <Tag className="np-status-tag">带默认语音</Tag> : null}
            {renderReferenceLink(item.reference_image_url)}
          </Space>
        </Space>
      ),
      handleAction: (item) => {
        if (boundAssetIdsByTab.character.has(item.id)) {
          return removeAssetFromPanel('character', item.id)
        }
        openCharacterBindPreview(item)
      },
    },
    location: {
      key: 'location',
      icon: <EnvironmentOutlined />,
      title: '地点',
      rows: filteredLocations,
      boundIds: boundAssetIdsByTab.location,
      renderTitle: (item) => <Text strong>{item.name}</Text>,
      renderDescription: (item) => (
        <Space direction="vertical" size={2} style={{ width: '100%' }}>
          {renderSourceLine(item)}
          {item.description ? <Text type="secondary">{item.description}</Text> : null}
          {renderReferenceLink(item.reference_image_url)}
        </Space>
      ),
      handleAction: (item) => {
        if (boundAssetIdsByTab.location.has(item.id)) {
          return removeAssetFromPanel('location', item.id)
        }
        openLocationBindPreview(item)
      },
    },
    voice: {
      key: 'voice',
      icon: <AudioOutlined />,
      title: '语音',
      rows: filteredVoices,
      boundIds: boundAssetIdsByTab.voice,
      renderTitle: (item) => <Text strong>{item.name}</Text>,
      renderDescription: (item) => (
        <Space direction="vertical" size={2} style={{ width: '100%' }}>
          {renderSourceLine(item)}
          <Text type="secondary">
            Provider：{item.provider} · 编码：{item.voice_code}
            {item.language ? ` · 语言：${item.language}` : ''}
          </Text>
          {item.style_prompt ? <Text type="secondary">风格：{item.style_prompt}</Text> : null}
        </Space>
      ),
      handleAction: (item) => {
        if (boundAssetIdsByTab.voice.has(item.id)) {
          return removeAssetFromPanel('voice', item.id)
        }
        return applyVoiceToPanel(item)
      },
    },
  }

  const buildTabItem = <K extends AssetTabKey>(config: DrawerTabConfig<K>) => ({
    key: config.key,
    label: <Space size={6}>{config.icon}{config.title}({config.rows.length})</Space>,
    children: (
      <List
        dataSource={config.rows}
        locale={{ emptyText: getAssetEmptyText(config.key) }}
        renderItem={(item) => {
          const isBound = config.boundIds.has(item.id)
          return (
            <List.Item
              actions={[
                <Button
                  key="bind"
                  type={isBound ? 'default' : 'primary'}
                  onClick={() => { void config.handleAction(item) }}
                  loading={actionLoading}
                >
                  {isBound ? '解绑' : '绑定'}
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={config.renderTitle(item)}
                description={config.renderDescription(item)}
              />
            </List.Item>
          )
        }}
      />
    ),
  })

  const tabItems = [
    buildTabItem(tabConfigs.character),
    buildTabItem(tabConfigs.location),
    buildTabItem(tabConfigs.voice),
  ]

  return (
    <Drawer
      title={`资产覆盖${selectedAssetPanel ? ` · ${selectedAssetPanel.title}` : ''}`}
      width={560}
      open={assetDrawer.open}
      onClose={closeAssetDrawer}
      extra={(
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={() => { void ensureAssetOverview(true) }}
          loading={assetLoading}
          aria-label="刷新资产"
        >
          刷新
        </Button>
      )}
    >
      {!selectedAssetPanel ? (
        <Empty description="未选择分镜" />
      ) : (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div className="np-asset-summary-row">
            <Text strong style={{ fontSize: 15 }}>{selectedAssetPanel.title}</Text>
            {panelSummary?.effectiveReferenceImageUrl ? (
              <Image
                src={panelSummary.effectiveReferenceImageUrl}
                width={48}
                height={48}
                style={{ border: '1px solid var(--np-frame-line)', objectFit: 'cover' }}
              />
            ) : (
              <Tag className="np-status-tag is-unbound">无参考图</Tag>
            )}
          </div>

          <div className="np-asset-binding-tags">
            {summaryItems.map((item) => (
              <Tag key={item.key} className={`np-status-tag${item.count > 0 ? '' : ' is-unbound'}`}>
                {item.label}：{item.value}{item.count > 1 ? `（+${item.count - 1}）` : ''}
              </Tag>
            ))}
          </div>

          <Card size="small" className="np-panel-card np-asset-action-card">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Text type="secondary">
                当前抽屉仅处理“分镜覆盖绑定”，用于临时替换或细节修正。剧本主绑定请在“资产绑定”页面维护。
              </Text>
              <Space wrap size={8}>
                <Button onClick={triggerClearBindingForCurrentTab} loading={actionLoading}>
                  清除当前{currentTabLabel}绑定
                </Button>
              </Space>
            </Space>
          </Card>

          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Input
              allowClear
              placeholder="搜索资产名称/描述"
              value={currentAssetSearchText}
              onChange={(event) => {
                const nextValue = event.target.value
                const tab = assetDrawer.tab
                setAssetSearchTextByTab((prev) => ({ ...prev, [tab]: nextValue }))
              }}
            />
            <Space wrap size={8}>
              <Switch
                size="small"
                checked={currentOnlyBoundFilter}
                onChange={(checked) => {
                  const tab = assetDrawer.tab
                  setOnlyBoundFilterByTab((prev) => ({ ...prev, [tab]: checked }))
                }}
                checkedChildren="仅看已绑定"
                unCheckedChildren="全部资产"
              />
              <Tag className="np-status-tag">当前可见：{currentVisibleCount}</Tag>
            </Space>
            <Collapse
              size="small"
              activeKey={assetAdvancedOpen ? ['advanced'] : []}
              onChange={(keys) => {
                const isOpen = Array.isArray(keys) ? keys.includes('advanced') : keys === 'advanced'
                setAssetAdvancedOpen(isOpen)
              }}
              items={[
                {
                  key: 'advanced',
                  label: '高级筛选',
                  children: (
                    <Space wrap size={8}>
                      <Text type="secondary">来源：</Text>
                      <Select
                        style={{ minWidth: 140 }}
                        value={currentSourceScope}
                        options={[
                          { label: '全局+当前项目', value: 'all' },
                          { label: '仅当前项目', value: 'project' },
                          { label: '仅全局', value: 'global' },
                        ]}
                        onChange={(value) => {
                          const tab = assetDrawer.tab
                          setAssetSourceScopeByTab((prev) => ({ ...prev, [tab]: value as AssetSourceScope }))
                        }}
                      />
                      <Text type="secondary">目录：</Text>
                      <Select
                        style={{ minWidth: 180 }}
                        value={currentFolderFilter}
                        options={folderFilterOptions}
                        onChange={(value) => {
                          const tab = assetDrawer.tab
                          setAssetFolderFilterByTab((prev) => ({ ...prev, [tab]: value }))
                        }}
                      />
                    </Space>
                  ),
                },
              ]}
            />
          </Space>

          <Tabs
            activeKey={assetDrawer.tab}
            onChange={(key) => setAssetDrawer((prev) => ({ ...prev, tab: key as AssetTabKey }))}
            items={tabItems}
          />
        </Space>
      )}
    </Drawer>
  )
}
