import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  App as AntdApp,
  Alert,
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
import {
  bindingBelongsToEpisodeScope,
  bindingIsSharedDefault,
  normalizeBindingForEpisodeScope,
} from '../../utils/scriptAssetScope'

const { Text } = Typography

interface ScriptAssetConsoleProps {
  projectId: string
  enabledTypes?: ScriptEntityType[]
  initialType?: ScriptEntityType
  hideTypeTabs?: boolean
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

interface CandidateOption {
  label: string
  value: string
  asset_name: string
}

interface ScopedBindingsState {
  scoped: ScriptAssetBinding[]
  unscoped: ScriptAssetBinding[]
}

function mergeEntityIntoList(rows: ScriptEntity[], entity: ScriptEntity): ScriptEntity[] {
  const idx = rows.findIndex((item) => item.id === entity.id)
  if (idx < 0) return [...rows, entity]
  const next = [...rows]
  next[idx] = entity
  return next
}

function getBindingAssetType(entityType: ScriptEntityType): ScriptAssetBinding['asset_type'] {
  return entityType === 'speaker' ? 'voice' : entityType
}

function normalizeBindingRecord(binding: ScriptAssetBinding, priority: number): ScriptAssetBinding {
  return {
    asset_type: binding.asset_type,
    asset_id: binding.asset_id,
    asset_name: binding.asset_name ?? undefined,
    role_tag: binding.role_tag ?? undefined,
    priority,
    is_primary: Boolean(binding.is_primary),
    strategy: binding.strategy ?? {},
  }
}

function normalizeBindingList(
  bindings: ScriptAssetBinding[],
  transform?: (binding: ScriptAssetBinding) => ScriptAssetBinding,
): ScriptAssetBinding[] {
  const normalized = bindings.map((binding, index) => normalizeBindingRecord(binding, index))
  if (normalized.length > 0 && !normalized.some((item) => item.is_primary)) {
    const firstBinding = normalized[0]
    if (firstBinding) {
      normalized[0] = { ...firstBinding, is_primary: true }
    }
  }
  return normalized.map((binding, index) => {
    const nextBinding = { ...binding, priority: index }
    return transform ? transform(nextBinding) : nextBinding
  })
}

function splitBindingsByScope(
  bindings: ScriptAssetBinding[],
  inScope: (binding: ScriptAssetBinding) => boolean,
): ScopedBindingsState {
  return bindings.reduce<ScopedBindingsState>((acc, binding) => {
    if (inScope(binding)) {
      acc.scoped.push(binding)
    } else {
      acc.unscoped.push(binding)
    }
    return acc
  }, { scoped: [], unscoped: [] })
}

function buildCandidateOptions(overview: AssetHubOverview | null, entityType: ScriptEntityType): CandidateOption[] {
  if (!overview) return []
  if (entityType === 'character') {
    return overview.characters.map((item) => ({ label: item.name, value: item.id, asset_name: item.name }))
  }
  if (entityType === 'location') {
    return overview.locations.map((item) => ({ label: item.name, value: item.id, asset_name: item.name }))
  }
  return overview.voices.map((item) => ({ label: item.name, value: item.id, asset_name: item.name }))
}

export default function ScriptAssetConsole({
  projectId,
  enabledTypes,
  initialType,
  hideTypeTabs = false,
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

  const bindingBelongsToCurrentScope = useCallback((binding: ScriptAssetBinding): boolean => {
    if (!scopedMode) return true
    return bindingBelongsToEpisodeScope(binding, scopeEpisodeId)
  }, [scopedMode, scopeEpisodeId])

  const normalizeBindingForScope = useCallback((binding: ScriptAssetBinding): ScriptAssetBinding => {
    if (!scopedMode) return binding
    return normalizeBindingForEpisodeScope(binding, scopeEpisodeId, 'asset_binding_page')
  }, [scopedMode, scopeEpisodeId])

  const commitEntityRows = useCallback((rows: ScriptEntity[]) => {
    setEntities(rows)
    onEntitiesChange?.(rows)
  }, [onEntitiesChange])

  const reloadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [entityRows, overview] = await Promise.all([
        listScriptEntities(projectId),
        getAssetHubOverview({ projectId, scope: 'all' }),
      ])
      commitEntityRows(entityRows)
      setAssetOverview(overview)
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载剧本资产规划失败'))
    } finally {
      setLoading(false)
    }
  }, [commitEntityRows, message, projectId])

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
  const currentTypeLabel = entityTypeLabel(activeType)
  const shouldHideTypeTabs = hideTypeTabs || availableTypes.length <= 1
  const filteredCurrentTypeEntities = useMemo(() => {
    const keyword = entityKeyword.trim().toLowerCase()
    if (!keyword) return currentTypeEntities
    return currentTypeEntities.filter((item) => (
      `${item.name} ${item.alias ?? ''} ${item.description ?? ''}`.toLowerCase().includes(keyword)
    ))
  }, [currentTypeEntities, entityKeyword])

  const upsertEntityInList = useCallback((entity: ScriptEntity) => {
    setEntities((prev) => mergeEntityIntoList(prev, entity))
  }, [])

  const commitUpsertEntity = useCallback((entity: ScriptEntity) => {
    commitEntityRows(mergeEntityIntoList(entities, entity))
  }, [commitEntityRows, entities])

  const updateSelectedEntityBindings = useCallback((
    updater: (bindings: ScriptAssetBinding[], state: ScopedBindingsState) => ScriptAssetBinding[],
  ) => {
    if (!selectedEntity) return
    const scopeState = splitBindingsByScope(selectedEntity.bindings, bindingBelongsToCurrentScope)
    upsertEntityInList({
      ...selectedEntity,
      bindings: updater(selectedEntity.bindings, scopeState),
    })
  }, [bindingBelongsToCurrentScope, selectedEntity, upsertEntityInList])

  const handleCreateEntity = async () => {
    setSaving(true)
    try {
      const created = await createScriptEntity(projectId, {
        entity_type: activeType,
        name: defaultEntityName(activeType),
        bindings: [],
      })
      commitUpsertEntity(created)
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
      commitUpsertEntity(updated)
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
      commitEntityRows(nextEntities)
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

  const candidateOptions = useMemo(() => buildCandidateOptions(assetOverview, activeType), [activeType, assetOverview])
  const currentBindingAssetType = getBindingAssetType(activeType)

  const selectedBindingState = useMemo(() => splitBindingsByScope(
    selectedEntity?.bindings ?? [],
    bindingBelongsToCurrentScope,
  ), [bindingBelongsToCurrentScope, selectedEntity?.bindings])

  const visibleBindings = useMemo(() => selectedBindingState.scoped.filter((item) => (
    item.asset_type === currentBindingAssetType
  )), [currentBindingAssetType, selectedBindingState.scoped])

  const inheritedBindings = useMemo(() => {
    if (!scopedMode) return []
    return selectedBindingState.unscoped.filter((item) => (
      item.asset_type === currentBindingAssetType && bindingIsSharedDefault(item)
    ))
  }, [currentBindingAssetType, scopedMode, selectedBindingState.unscoped])

  const handleAppendBinding = (assetId: string) => {
    const option = candidateOptions.find((item) => item.value === assetId)
    if (!option) return
    if (scopedMode && inheritedBindings.some((item) => item.asset_id === assetId)) {
      message.info('该资产已作为旧默认绑定生效；如需保持现状，无需重复添加')
      return
    }
    updateSelectedEntityBindings((bindings, state) => {
      if (state.scoped.some((item) => item.asset_id === assetId)) return bindings
      const nextScoped = normalizeBindingList([
        ...state.scoped,
        normalizeBindingForScope({
          asset_type: getBindingAssetType(activeType),
          asset_id: assetId,
          asset_name: option.asset_name,
          role_tag: null,
          priority: state.scoped.length,
          is_primary: state.scoped.length === 0,
          strategy: {},
        }),
      ])
      return [...state.unscoped, ...nextScoped]
    })
  }

  const handleDeleteBinding = (assetId: string) => {
    updateSelectedEntityBindings((_bindings, state) => {
      const nextScoped = normalizeBindingList(state.scoped.filter((item) => item.asset_id !== assetId))
      return [...state.unscoped, ...nextScoped]
    })
  }

  const handlePrimaryChange = (assetId: string) => {
    updateSelectedEntityBindings((_bindings, state) => {
      const nextScoped = normalizeBindingList(state.scoped.map((item) => ({
        ...item,
        is_primary: item.asset_id === assetId,
      })))
      return [...state.unscoped, ...nextScoped]
    })
  }

  const handleSaveBindings = async () => {
    if (!selectedEntity) return
    setSaving(true)
    try {
      const scopedNormalized = normalizeBindingList(selectedBindingState.scoped, normalizeBindingForScope)
      const nextBindings = normalizeBindingList([...selectedBindingState.unscoped, ...scopedNormalized])
      const saved = await replaceScriptEntityBindings(selectedEntity.id, nextBindings)
      commitUpsertEntity({ ...selectedEntity, bindings: saved })
      message.success(scopedMode ? '当前分集绑定已保存' : '默认绑定已保存')
    } catch (error) {
      message.error(getApiErrorMessage(error, scopedMode ? '保存当前分集绑定失败' : '保存默认绑定失败'))
    } finally {
      setSaving(false)
    }
  }

  const headerActions = (
    <Space>
      <Button onClick={() => { void reloadAll() }} loading={loading}>刷新资产池</Button>
      <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateEntity} loading={saving}>
        新增{currentTypeLabel}
      </Button>
    </Space>
  )

  const typePane = (
    <div className="np-script-asset-console-grid">
      <section className="np-script-asset-pane np-script-asset-pane-left">
        <div className="np-script-asset-pane-head">
          <Text strong>{currentTypeLabel}实体</Text>
        </div>
        <div className="np-script-asset-pane-body">
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Input.Search
              allowClear
              value={entityKeyword}
              onChange={(event) => setEntityKeyword(event.target.value)}
              placeholder={`搜索${currentTypeLabel}实体`}
            />
            {filteredCurrentTypeEntities.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={currentTypeEntities.length === 0
                  ? `暂无${currentTypeLabel}实体`
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
                <Text strong>{scopedMode ? '当前分集绑定' : '默认绑定'}（{currentTypeLabel}）</Text>
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
                        当前仅编辑本分集专属绑定；旧默认绑定会在下方单独展示，不会被本次保存覆盖。
                      </Text>
                    ) : null}
                    <Select
                      showSearch
                      placeholder={`添加${currentTypeLabel}资产`}
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
                    {scopedMode && inheritedBindings.length > 0 ? (
                      <>
                        <Alert
                          type="info"
                          showIcon
                          message={`检测到 ${inheritedBindings.length} 个历史默认绑定`}
                          description="这些绑定是旧版本留下的共享默认绑定，数据没有丢失，当前分集仍会继承使用。若你想改成当前分集专属，请重新添加当前分集绑定后保存。"
                        />
                        <List
                          size="small"
                          dataSource={inheritedBindings}
                          renderItem={(row) => (
                            <List.Item className={`np-script-binding-item${row.is_primary ? ' is-primary' : ''}`}>
                              <div className="np-script-binding-row">
                                <Space size={6} wrap style={{ minWidth: 0 }}>
                                  <Tag className="np-status-tag">{row.asset_name || row.asset_id}</Tag>
                                  <Tag className="np-status-tag">旧默认绑定</Tag>
                                  {row.role_tag ? <Tag className="np-status-tag">角色位：{row.role_tag}</Tag> : null}
                                  {row.is_primary ? <Tag className="np-status-tag np-status-completed">主绑定</Tag> : null}
                                </Space>
                              </div>
                            </List.Item>
                          )}
                        />
                      </>
                    ) : null}
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
  )

  const consoleBody = loading ? (
    <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>
  ) : shouldHideTypeTabs ? (
    typePane
  ) : (
    <Tabs
      activeKey={activeType}
      onChange={(key) => setActiveType(key as ScriptEntityType)}
      items={availableTypes.map((type) => ({
        key: type,
        label: `${entityTypeLabel(type)}（${entitiesByType[type].length}）`,
        children: type === activeType ? typePane : null,
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
