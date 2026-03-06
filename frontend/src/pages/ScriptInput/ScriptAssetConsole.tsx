import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  App as AntdApp,
  Button,
  Card,
  Empty,
  Input,
  List,
  Modal,
  Select,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { DeleteOutlined, DownOutlined, PlusOutlined, SaveOutlined, UpOutlined } from '@ant-design/icons'
import { getApiErrorMessage } from '../../utils/error'
import { getAssetHubOverview } from '../../api/assetHub'
import {
  createScriptEntity,
  deleteScriptEntity,
  listScriptEntities,
  replaceScriptEntityBindings,
  updateScriptEntity,
} from '../../api/scriptAssets'
import type { ScriptAssetBinding, ScriptEntity, ScriptEntityType } from '../../types/scriptAssets'
import type { AssetHubOverview } from '../../types/assetHub'
import { bindingBelongsToEpisodeScope, normalizeBindingForEpisodeScope } from '../../utils/scriptAssetScope'

const { Text } = Typography

interface ScriptAssetConsoleProps {
  projectId: string
  enabledTypes?: ScriptEntityType[]
  initialType?: ScriptEntityType
  refreshSignal?: number
  focusSignal?: number
  scopeEpisodeId?: string | null
  enforceEpisodeScope?: boolean
  embedded?: boolean
  onEntitiesChange?: (entities: ScriptEntity[]) => void
}

function entityTypeLabel(type: ScriptEntityType): string {
  if (type === 'character') return '角色'
  if (type === 'location') return '地点'
  return '说话人'
}

function defaultEntityName(type: ScriptEntityType): string {
  if (type === 'character') return '新角色实体'
  if (type === 'location') return '新地点实体'
  return '新说话人实体'
}

export default function ScriptAssetConsole({
  projectId,
  enabledTypes,
  initialType,
  refreshSignal,
  focusSignal,
  scopeEpisodeId,
  enforceEpisodeScope = false,
  embedded = false,
  onEntitiesChange,
}: ScriptAssetConsoleProps) {
  const { message } = AntdApp.useApp()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [entities, setEntities] = useState<ScriptEntity[]>([])
  const [assetOverview, setAssetOverview] = useState<AssetHubOverview | null>(null)
  const [activeType, setActiveType] = useState<ScriptEntityType>(initialType ?? 'character')
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [pendingDeleteEntity, setPendingDeleteEntity] = useState<ScriptEntity | null>(null)
  const [entityKeyword, setEntityKeyword] = useState('')
  const [focusPulse, setFocusPulse] = useState(false)
  const [showEntityMeta, setShowEntityMeta] = useState(false)
  const [entityDraft, setEntityDraft] = useState({
    name: '',
    alias: '',
    description: '',
  })
  const refreshInitializedRef = useRef(false)
  const focusInitializedRef = useRef(false)
  const focusPulseTimerRef = useRef<number | null>(null)
  const consoleRootRef = useRef<HTMLDivElement | null>(null)
  const availableTypes = useMemo<ScriptEntityType[]>(() => {
    const defaults: ScriptEntityType[] = ['character', 'location', 'speaker']
    const source = enabledTypes && enabledTypes.length > 0 ? enabledTypes : defaults
    const valid = source.filter((item): item is ScriptEntityType => defaults.includes(item))
    const deduped = Array.from(new Set(valid))
    return deduped.length > 0 ? deduped : defaults
  }, [enabledTypes])
  const availableTypeSet = useMemo(() => new Set<ScriptEntityType>(availableTypes), [availableTypes])
  const scopedMode = enforceEpisodeScope && Boolean(scopeEpisodeId)

  const bindingBelongsToCurrentScope = (binding: ScriptAssetBinding): boolean => {
    if (!scopedMode) return true
    return bindingBelongsToEpisodeScope(binding, scopeEpisodeId)
  }

  const normalizeBindingForScope = (binding: ScriptAssetBinding): ScriptAssetBinding => {
    if (!scopedMode) return binding
    return normalizeBindingForEpisodeScope(binding, scopeEpisodeId, 'asset_binding_page')
  }

  const reloadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [entityRows, overview] = await Promise.all([
        listScriptEntities(projectId),
        getAssetHubOverview({ projectId, scope: 'all' }),
      ])
      setEntities(entityRows)
      onEntitiesChange?.(entityRows)
      setAssetOverview(overview)
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载剧本资产规划失败'))
    } finally {
      setLoading(false)
    }
  }, [message, onEntitiesChange, projectId])

  useEffect(() => {
    void reloadAll()
  }, [reloadAll])

  const entitiesByType = useMemo(() => ({
    character: entities.filter((item) => item.entity_type === 'character'),
    location: entities.filter((item) => item.entity_type === 'location'),
    speaker: entities.filter((item) => item.entity_type === 'speaker'),
  }), [entities])

  const selectedEntity = useMemo(
    () => entities.find((item) => item.id === selectedEntityId) ?? null,
    [entities, selectedEntityId],
  )

  useEffect(() => {
    if (availableTypeSet.has(activeType)) return
    const fallback = availableTypes[0] ?? 'character'
    if (fallback !== activeType) {
      setActiveType(fallback)
    }
  }, [activeType, availableTypeSet, availableTypes])

  useEffect(() => {
    if (loading) return
    if (!selectedEntity) {
      setEntityDraft({
        name: '',
        alias: '',
        description: '',
      })
      return
    }
    setEntityDraft({
      name: selectedEntity.name,
      alias: selectedEntity.alias ?? '',
      description: selectedEntity.description ?? '',
    })
  }, [loading, selectedEntity])

  useEffect(() => {
    if (selectedEntity && selectedEntity.entity_type === activeType) return
    const first = entitiesByType[activeType][0]
    const nextId = first?.id ?? null
    if (nextId !== selectedEntityId) {
      setSelectedEntityId(nextId)
    }
  }, [activeType, entitiesByType, selectedEntity, selectedEntityId])

  useEffect(() => {
    if (!initialType || !availableTypeSet.has(initialType)) return
    if (initialType !== activeType) {
      setActiveType(initialType)
    }
  }, [activeType, availableTypeSet, initialType])

  useEffect(() => {
    setEntityKeyword('')
  }, [activeType])

  useEffect(() => {
    setShowEntityMeta(false)
  }, [activeType, selectedEntityId])

  useEffect(() => {
    if (refreshSignal === undefined) return
    if (!refreshInitializedRef.current) {
      refreshInitializedRef.current = true
      return
    }
    void reloadAll()
  }, [refreshSignal, reloadAll])

  useEffect(() => {
    if (focusSignal === undefined) return
    if (!focusInitializedRef.current) {
      focusInitializedRef.current = true
      return
    }

    if (initialType && availableTypeSet.has(initialType)) {
      setActiveType((prev) => (prev === initialType ? prev : initialType))
    }
    setEntityKeyword('')
    const host = consoleRootRef.current
    const scopedScrollContainer = host?.closest('.np-asset-binding-main') as HTMLElement | null
    if (host && scopedScrollContainer) {
      const targetTop = Math.max(0, host.offsetTop - 8)
      scopedScrollContainer.scrollTo({ top: targetTop, behavior: 'smooth' })
    }

    if (focusPulseTimerRef.current) {
      window.clearTimeout(focusPulseTimerRef.current)
    }
    setFocusPulse(true)
    focusPulseTimerRef.current = window.setTimeout(() => {
      setFocusPulse(false)
      focusPulseTimerRef.current = null
    }, 900)
  }, [availableTypeSet, focusSignal, initialType])

  useEffect(() => () => {
    if (focusPulseTimerRef.current) {
      window.clearTimeout(focusPulseTimerRef.current)
    }
  }, [])

  const currentTypeEntities = entitiesByType[activeType]
  const filteredCurrentTypeEntities = useMemo(() => {
    const keyword = entityKeyword.trim().toLowerCase()
    if (!keyword) return currentTypeEntities
    return currentTypeEntities.filter((item) => (
      `${item.name} ${item.alias ?? ''} ${item.description ?? ''}`.toLowerCase().includes(keyword)
    ))
  }, [currentTypeEntities, entityKeyword])

  const mergeEntityIntoList = (rows: ScriptEntity[], entity: ScriptEntity): ScriptEntity[] => {
    const idx = rows.findIndex((item) => item.id === entity.id)
    if (idx < 0) return [...rows, entity]
    const next = [...rows]
    next[idx] = entity
    return next
  }

  const upsertEntityInList = (entity: ScriptEntity) => {
    setEntities((prev) => mergeEntityIntoList(prev, entity))
  }

  const handleCreateEntity = async () => {
    setSaving(true)
    try {
      const created = await createScriptEntity(projectId, {
        entity_type: activeType,
        name: defaultEntityName(activeType),
        bindings: [],
      })
      upsertEntityInList(created)
      setSelectedEntityId(created.id)
      message.success(`已创建${entityTypeLabel(activeType)}实体`)
    } catch (error) {
      message.error(getApiErrorMessage(error, `创建${entityTypeLabel(activeType)}实体失败`))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveEntityMeta = async () => {
    if (!selectedEntity) return
    const name = entityDraft.name.trim()
    if (!name) {
      message.warning('请输入名称')
      return
    }
    setSaving(true)
    try {
      const updated = await updateScriptEntity(selectedEntity.id, {
        name,
        alias: entityDraft.alias.trim() || null,
        description: entityDraft.description.trim() || null,
      })
      upsertEntityInList(updated)
      message.success('实体信息已保存')
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存实体信息失败'))
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteEntity = async () => {
    if (!pendingDeleteEntity) return
    setSaving(true)
    try {
      await deleteScriptEntity(pendingDeleteEntity.id)
      const nextEntities = entities.filter((item) => item.id !== pendingDeleteEntity.id)
      setEntities(nextEntities)
      onEntitiesChange?.(nextEntities)
      if (selectedEntityId === pendingDeleteEntity.id) {
        const fallback = entitiesByType[activeType].find((item) => item.id !== pendingDeleteEntity.id)
        setSelectedEntityId(fallback?.id ?? null)
      }
      setDeleteModalOpen(false)
      setPendingDeleteEntity(null)
      message.success('实体已删除')
    } catch (error) {
      message.error(getApiErrorMessage(error, '删除实体失败'))
    } finally {
      setSaving(false)
    }
  }

  const candidateOptions = useMemo(() => {
    if (!assetOverview) return []
    if (activeType === 'character') {
      return assetOverview.characters.map((item) => ({ label: item.name, value: item.id, asset_name: item.name }))
    }
    if (activeType === 'location') {
      return assetOverview.locations.map((item) => ({ label: item.name, value: item.id, asset_name: item.name }))
    }
    return assetOverview.voices.map((item) => ({ label: item.name, value: item.id, asset_name: item.name }))
  }, [activeType, assetOverview])

  const handleAppendBinding = (assetId: string) => {
    if (!selectedEntity) return
    const exists = selectedEntity.bindings.some((item) => item.asset_id === assetId && bindingBelongsToCurrentScope(item))
    if (exists) return
    const option = candidateOptions.find((item) => item.value === assetId)
    const scopeBindings = selectedEntity.bindings.filter((item) => bindingBelongsToCurrentScope(item))
    const next: ScriptAssetBinding[] = [
      ...selectedEntity.bindings,
      normalizeBindingForScope({
        asset_type: activeType === 'speaker' ? 'voice' : activeType,
        asset_id: assetId,
        asset_name: option?.asset_name ?? '',
        role_tag: null,
        priority: scopeBindings.length,
        is_primary: scopeBindings.length === 0,
        strategy: {},
      }),
    ]
    upsertEntityInList({ ...selectedEntity, bindings: next })
  }

  const handleDeleteBinding = (assetId: string) => {
    if (!selectedEntity) return
    const remainedScoped = selectedEntity.bindings.filter((item) => (
      !bindingBelongsToCurrentScope(item) || item.asset_id !== assetId
    ))
    const scopeBindings = remainedScoped.filter((item) => bindingBelongsToCurrentScope(item))
    const normalizedScoped = scopeBindings.map((item, index) => ({ ...item, priority: index }))
    if (normalizedScoped.length > 0 && !normalizedScoped.some((item) => item.is_primary)) {
      const first = normalizedScoped[0]
      if (first) {
        first.is_primary = true
      }
    }
    const nonScoped = remainedScoped.filter((item) => !bindingBelongsToCurrentScope(item))
    upsertEntityInList({ ...selectedEntity, bindings: [...nonScoped, ...normalizedScoped] })
  }

  const handlePrimaryChange = (assetId: string) => {
    if (!selectedEntity) return
    const normalized = selectedEntity.bindings.map((item) => {
      if (!bindingBelongsToCurrentScope(item)) return item
      return { ...item, is_primary: item.asset_id === assetId }
    })
    upsertEntityInList({ ...selectedEntity, bindings: normalized })
  }

  const handleSaveBindings = async () => {
    if (!selectedEntity) return
    setSaving(true)
    try {
      const scopedSource = selectedEntity.bindings.filter((item) => bindingBelongsToCurrentScope(item))
      const nonScoped = selectedEntity.bindings.filter((item) => !bindingBelongsToCurrentScope(item))
      const scopedNormalized = scopedSource.map((item, index) => normalizeBindingForScope({
        asset_type: item.asset_type,
        asset_id: item.asset_id,
        asset_name: item.asset_name ?? undefined,
        role_tag: item.role_tag ?? undefined,
        priority: index,
        is_primary: Boolean(item.is_primary),
        strategy: item.strategy ?? {},
      }))
      const nextBindings = [...nonScoped, ...scopedNormalized].map((item, index) => ({
        asset_type: item.asset_type,
        asset_id: item.asset_id,
        asset_name: item.asset_name ?? undefined,
        role_tag: item.role_tag ?? undefined,
        priority: index,
        is_primary: Boolean(item.is_primary),
        strategy: item.strategy ?? {},
      }))
      const saved = await replaceScriptEntityBindings(selectedEntity.id, nextBindings)
      const nextEntity = { ...selectedEntity, bindings: saved }
      const nextEntities = mergeEntityIntoList(entities, nextEntity)
      setEntities(nextEntities)
      onEntitiesChange?.(nextEntities)
      message.success(scopedMode ? '当前分集绑定已保存' : '默认绑定已保存')
    } catch (error) {
      message.error(getApiErrorMessage(error, scopedMode ? '保存当前分集绑定失败' : '保存默认绑定失败'))
    } finally {
      setSaving(false)
    }
  }

  const visibleBindings = selectedEntity
    ? selectedEntity.bindings.filter((item) => bindingBelongsToCurrentScope(item))
    : []

  const headerActions = (
    <Space>
      <Button onClick={() => { void reloadAll() }} loading={loading}>刷新资产池</Button>
      <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateEntity} loading={saving}>
        新增{entityTypeLabel(activeType)}
      </Button>
    </Space>
  )

  const consoleBody = loading ? (
    <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>
  ) : (
    <Tabs
      activeKey={activeType}
      onChange={(key) => setActiveType(key as ScriptEntityType)}
      items={availableTypes.map((type) => ({
        key: type,
        label: `${entityTypeLabel(type)}（${entitiesByType[type].length}）`,
      })).map((item) => ({
        ...item,
        children: (
          <div className="np-script-asset-console-grid">
            <section className="np-script-asset-pane np-script-asset-pane-left">
              <div className="np-script-asset-pane-head">
                <Text strong>{entityTypeLabel(activeType)}实体</Text>
              </div>
              <div className="np-script-asset-pane-body">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Input.Search
                    allowClear
                    value={entityKeyword}
                    onChange={(event) => setEntityKeyword(event.target.value)}
                    placeholder={`搜索${entityTypeLabel(activeType)}实体`}
                  />
                  {filteredCurrentTypeEntities.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={currentTypeEntities.length === 0
                        ? `暂无${entityTypeLabel(activeType)}实体`
                        : '未匹配到搜索结果'}
                    />
                  ) : (
                    <List
                      size="small"
                      dataSource={filteredCurrentTypeEntities}
                      renderItem={(row) => (
                        <List.Item
                          className={`np-script-entity-item${selectedEntityId === row.id ? ' is-active' : ''}`}
                          onClick={() => setSelectedEntityId(row.id)}
                        >
                          <Space direction="vertical" size={2} style={{ width: '100%', minWidth: 0 }}>
                            <Text strong>{row.name}</Text>
                            <Text type="secondary" className="np-script-entity-meta">
                              {row.alias || row.description || '未补充说明'}
                            </Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  )}
                </Space>
              </div>
            </section>

            <section className="np-script-asset-pane np-script-asset-pane-right">
              <div className="np-script-asset-pane-head">
                <Text strong>{selectedEntity ? `编辑：${selectedEntity.name}` : '实体详情'}</Text>
              </div>
              <div className="np-script-asset-pane-body">
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <div className="np-script-asset-binding-block">
                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                      <Text strong>{scopedMode ? '当前分集绑定' : '默认绑定'}（{entityTypeLabel(activeType)}）</Text>
                      {!selectedEntity ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`请选择左侧实体后配置${scopedMode ? '当前分集绑定' : '默认绑定'}`} />
                      ) : (
                        <>
                          <Text type="secondary">
                            {activeType === 'speaker'
                              ? '说话人绑定语音资产，分镜层只做情绪/语速微调。'
                              : activeType === 'character'
                                ? '角色绑定用于外观一致性，分镜层只做临时造型覆盖。'
                                : '地点绑定用于场景一致性，分镜层建议优先使用地点变体覆盖。'}
                          </Text>
                          {scopedMode ? (
                            <Text type="secondary">
                              当前仅显示并保存本分集的绑定，不会覆盖其他分集或全局默认绑定。
                            </Text>
                          ) : null}
                          <Select
                            showSearch
                            placeholder={`添加${entityTypeLabel(activeType)}资产`}
                            options={candidateOptions}
                            optionFilterProp="label"
                            onSelect={(value) => handleAppendBinding(String(value))}
                          />
                          {visibleBindings.length === 0 ? (
                            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={scopedMode ? '当前分集未绑定资产' : '未绑定资产'} />
                          ) : (
                            <List
                              size="small"
                              dataSource={visibleBindings}
                              renderItem={(row) => (
                                <List.Item className={`np-script-binding-item${row.is_primary ? ' is-primary' : ''}`}>
                                  <div className="np-script-binding-row">
                                    <Space size={6} wrap style={{ minWidth: 0 }}>
                                      <Tag className="np-status-tag">{row.asset_name || row.asset_id}</Tag>
                                      {row.role_tag ? <Tag className="np-status-tag">角色位：{row.role_tag}</Tag> : null}
                                      {row.is_primary ? <Tag className="np-status-tag np-status-completed">主绑定</Tag> : null}
                                    </Space>
                                    <Space size={4} className="np-script-binding-actions">
                                      {!row.is_primary ? (
                                        <Button
                                          type="text"
                                          size="small"
                                          onClick={() => handlePrimaryChange(row.asset_id)}
                                        >
                                          设为主
                                        </Button>
                                      ) : null}
                                      <Button
                                        type="text"
                                        size="small"
                                        danger
                                        onClick={() => handleDeleteBinding(row.asset_id)}
                                      >
                                        删除
                                      </Button>
                                    </Space>
                                  </div>
                                </List.Item>
                              )}
                            />
                          )}
                          <Button type="primary" onClick={() => { void handleSaveBindings() }} loading={saving}>
                            {scopedMode ? '保存当前分集绑定' : '保存默认绑定'}
                          </Button>
                        </>
                      )}
                    </Space>
                  </div>

                  {selectedEntity ? (
                    <>
                      <div className="np-script-asset-meta-toggle">
                        <Button
                          type="text"
                          size="small"
                          icon={showEntityMeta ? <UpOutlined /> : <DownOutlined />}
                          onClick={() => setShowEntityMeta((prev) => !prev)}
                        >
                          {showEntityMeta ? '收起实体信息（高级）' : '展开实体信息（高级）'}
                        </Button>
                      </div>

                      {showEntityMeta ? (
                        <div className="np-script-asset-meta-block">
                          <Space direction="vertical" size={10} style={{ width: '100%' }}>
                            <Text strong>实体信息（高级）</Text>
                            <Input
                              value={entityDraft.name}
                              onChange={(event) => setEntityDraft((prev) => ({ ...prev, name: event.target.value }))}
                              placeholder="名称"
                            />
                            <Input
                              value={entityDraft.alias}
                              onChange={(event) => setEntityDraft((prev) => ({ ...prev, alias: event.target.value }))}
                              placeholder="别名（可选）"
                            />
                            <Input.TextArea
                              value={entityDraft.description}
                              onChange={(event) => setEntityDraft((prev) => ({ ...prev, description: event.target.value }))}
                              autoSize={{ minRows: 2, maxRows: 4 }}
                              placeholder="描述（可选）"
                            />
                            <Space wrap>
                              <Button
                                type="primary"
                                icon={<SaveOutlined />}
                                onClick={() => { void handleSaveEntityMeta() }}
                                loading={saving}
                              >
                                保存实体信息
                              </Button>
                              <Button
                                danger
                                icon={<DeleteOutlined />}
                                onClick={() => {
                                  if (!selectedEntity) return
                                  setPendingDeleteEntity(selectedEntity)
                                  setDeleteModalOpen(true)
                                }}
                              >
                                删除实体
                              </Button>
                            </Space>
                          </Space>
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </Space>
              </div>
            </section>
          </div>
        ),
      }))}
    />
  )

  return (
    <div ref={consoleRootRef} className={`np-script-asset-console-host${embedded ? ' is-embedded' : ''}`}>
      {embedded ? (
        <section className={`np-script-asset-console np-script-asset-console-embedded${focusPulse ? ' is-focus-pulse' : ''}`}>
          <div className="np-script-asset-console-toolbar">
            <Text strong>资产规划台（剧本主绑定）</Text>
            {headerActions}
          </div>
          {consoleBody}
        </section>
      ) : (
        <Card
          className={`np-panel-card np-script-asset-console${focusPulse ? ' is-focus-pulse' : ''}`}
          title="资产规划台（剧本主绑定）"
          extra={headerActions}
        >
          {consoleBody}
        </Card>
      )}

      <Modal
        title="确认删除实体"
        open={deleteModalOpen}
        onCancel={() => {
          setDeleteModalOpen(false)
          setPendingDeleteEntity(null)
        }}
        onOk={() => { void handleDeleteEntity() }}
        okButtonProps={{ danger: true, loading: saving }}
        okText="删除"
        cancelText="取消"
        destroyOnHidden
      >
        <Text>{scopedMode ? '删除后将移除该实体及其分集绑定规则，且不可恢复。' : '删除后将移除该实体的默认绑定与覆盖规则，且不可恢复。'}</Text>
      </Modal>
    </div>
  )
}
