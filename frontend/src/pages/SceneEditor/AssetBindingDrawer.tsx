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
import { sourceScopeTag } from './utils'
import type { UseAssetBindingReturn } from './useAssetBinding'

const { Text } = Typography

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

  const characterBoundIds = new Set(panelBinding.asset_character_ids ?? [])
  const locationBoundIds = new Set(panelBinding.asset_location_ids ?? [])
  const voiceBoundIds = new Set(panelBinding.asset_voice_ids ?? [])
  if (panelBinding.asset_character_id) characterBoundIds.add(panelBinding.asset_character_id)
  if (panelBinding.asset_location_id) locationBoundIds.add(panelBinding.asset_location_id)
  if (panelBinding.asset_voice_id) voiceBoundIds.add(panelBinding.asset_voice_id)
  const characterBoundCount = characterBoundIds.size
  const locationBoundCount = locationBoundIds.size
  const voiceBoundCount = voiceBoundIds.size

  const voiceLabel = panelBinding.asset_voice_name
    || (panelBinding.asset_voice_id ? '未命名语音' : '未绑定')
  const voiceBound = voiceBoundCount > 0 || Boolean(panelBinding.asset_voice_id)

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
          {/* 分镜信息行 */}
          <div className="np-asset-summary-row">
            <Text strong style={{ fontSize: 15 }}>{selectedAssetPanel.title}</Text>
            {selectedAssetPanel.reference_image_url ? (
              <Image
                src={selectedAssetPanel.reference_image_url}
                width={48}
                height={48}
                style={{ border: '1px solid var(--np-frame-line)', objectFit: 'cover' }}
              />
            ) : (
              <Tag className="np-status-tag is-unbound">无参考图</Tag>
            )}
          </div>

          {/* 绑定状态行 */}
          <div className="np-asset-binding-tags">
            <Tag className={`np-status-tag${characterBoundCount > 0 ? '' : ' is-unbound'}`}>
              角色：{panelBinding.asset_character_name || '未绑定'}{characterBoundCount > 1 ? `（+${characterBoundCount - 1}）` : ''}
            </Tag>
            <Tag className={`np-status-tag${locationBoundCount > 0 ? '' : ' is-unbound'}`}>
              地点：{panelBinding.asset_location_name || '未绑定'}{locationBoundCount > 1 ? `（+${locationBoundCount - 1}）` : ''}
            </Tag>
            <Tag className={`np-status-tag${voiceBound ? '' : ' is-unbound'}`}>
              语音：{voiceLabel}{voiceBoundCount > 1 ? `（+${voiceBoundCount - 1}）` : ''}
            </Tag>
          </div>

          {/* 操作区：工作模式 + 流程提示 + 操作按钮 */}
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

          {/* 搜索与筛选 */}
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

          {/* 资产列表 */}
          <Tabs
            activeKey={assetDrawer.tab}
            onChange={(key) => setAssetDrawer((prev) => ({ ...prev, tab: key as AssetTabKey }))}
            items={[
              {
                key: 'character',
                label: <Space size={6}><UserOutlined />角色({filteredCharacters.length})</Space>,
                children: (
                  <List
                    dataSource={filteredCharacters}
                    locale={{ emptyText: getAssetEmptyText('character') }}
                    renderItem={(item: GlobalCharacterAsset) => (
                      <List.Item
                        actions={[
                          <Button
                            key="bind"
                            type={characterBoundIds.has(item.id) ? 'default' : 'primary'}
                            onClick={() => {
                              if (characterBoundIds.has(item.id)) {
                                void removeAssetFromPanel('character', item.id)
                              } else {
                                openCharacterBindPreview(item)
                              }
                            }}
                            loading={actionLoading}
                          >
                            {characterBoundIds.has(item.id) ? '解绑' : '绑定'}
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={(
                            <Space wrap>
                              <Text strong>{item.name}</Text>
                              {item.alias ? <Tag className="np-status-tag">别名：{item.alias}</Tag> : null}
                            </Space>
                          )}
                          description={(
                            <Space direction="vertical" size={2} style={{ width: '100%' }}>
                              {renderSourceLine(item)}
                              {item.description ? <Text type="secondary">{item.description}</Text> : null}
                              <Space size={8} wrap>
                                {item.default_voice_id ? <Tag className="np-status-tag">语音已关联</Tag> : null}
                                {item.reference_image_url ? (
                                  <a href={item.reference_image_url} target="_blank" rel="noreferrer">参考图</a>
                                ) : null}
                              </Space>
                            </Space>
                          )}
                        />
                      </List.Item>
                    )}
                  />
                ),
              },
              {
                key: 'location',
                label: <Space size={6}><EnvironmentOutlined />地点({filteredLocations.length})</Space>,
                children: (
                  <List
                    dataSource={filteredLocations}
                    locale={{ emptyText: getAssetEmptyText('location') }}
                    renderItem={(item: GlobalLocationAsset) => (
                      <List.Item
                        actions={[
                          <Button
                            key="bind"
                            type={locationBoundIds.has(item.id) ? 'default' : 'primary'}
                            onClick={() => {
                              if (locationBoundIds.has(item.id)) {
                                void removeAssetFromPanel('location', item.id)
                              } else {
                                openLocationBindPreview(item)
                              }
                            }}
                            loading={actionLoading}
                          >
                            {locationBoundIds.has(item.id) ? '解绑' : '绑定'}
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={<Text strong>{item.name}</Text>}
                          description={(
                            <Space direction="vertical" size={2} style={{ width: '100%' }}>
                              {renderSourceLine(item)}
                              {item.description ? <Text type="secondary">{item.description}</Text> : null}
                              {item.reference_image_url ? (
                                <a href={item.reference_image_url} target="_blank" rel="noreferrer">参考图</a>
                              ) : null}
                            </Space>
                          )}
                        />
                      </List.Item>
                    )}
                  />
                ),
              },
              {
                key: 'voice',
                label: <Space size={6}><AudioOutlined />语音({filteredVoices.length})</Space>,
                children: (
                  <List
                    dataSource={filteredVoices}
                    locale={{ emptyText: getAssetEmptyText('voice') }}
                    renderItem={(item: GlobalVoice) => (
                      <List.Item
                        actions={[
                          <Button
                            key="bind"
                            type={voiceBoundIds.has(item.id) ? 'default' : 'primary'}
                            onClick={() => {
                              if (voiceBoundIds.has(item.id)) {
                                void removeAssetFromPanel('voice', item.id)
                              } else {
                                void applyVoiceToPanel(item)
                              }
                            }}
                            loading={actionLoading}
                          >
                            {voiceBoundIds.has(item.id) ? '解绑' : '绑定'}
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={<Text strong>{item.name}</Text>}
                          description={(
                            <Space direction="vertical" size={2} style={{ width: '100%' }}>
                              {renderSourceLine(item)}
                              <Text type="secondary">
                                Provider：{item.provider} · 编码：{item.voice_code}
                                {item.language ? ` · 语言：${item.language}` : ''}
                              </Text>
                              {item.style_prompt ? <Text type="secondary">风格：{item.style_prompt}</Text> : null}
                            </Space>
                          )}
                        />
                      </List.Item>
                    )}
                  />
                ),
              },
            ]}
          />
        </Space>
      )}
    </Drawer>
  )
}
