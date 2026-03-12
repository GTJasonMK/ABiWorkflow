import { type Dispatch, type SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App as AntdApp } from 'antd'
import type { Panel } from '../../types/panel'
import type { AssetHubOverview, GlobalCharacterAsset, GlobalLocationAsset, GlobalVoice } from '../../types/assetHub'
import { updatePanel } from '../../api/panels'
import {
  createScriptEntity,
  getPanelEffectiveBindings,
  listScriptEntities,
  replacePanelAssetOverrides,
  updateScriptEntity,
} from '../../api/scriptAssets'
import { getApiErrorMessage } from '../../utils/error'
import { useAssetHubStore } from '../../stores/assetHubStore'
import type { PanelAssetBinding } from '../../types/panelBinding'
import type { ScriptEntity, ScriptEntityType, ScriptScopedOverride } from '../../types/scriptAssets'
import type {
  AssetApplyPlan,
  AssetDrawerState,
  AssetSourceScope,
  AssetTabKey,
  BindPreviewState,
} from './types'
import {
  DIRECT_BIND_PROMPT_MODE,
  DEFAULT_ASSET_FOLDER_FILTERS,
  DEFAULT_ASSET_SEARCH_TEXTS,
  DEFAULT_ASSET_SOURCE_SCOPES,
  DEFAULT_ONLY_BOUND_FILTERS,
} from './types'
import {
  buildResolvedPanelBindingState,
  getPanelBindingAssetIds,
  getPanelBindingPrimaryAssetId,
  parsePanelBinding,
} from '../../utils/panelBinding'
import {
  assetTabLabel,
  buildCharacterApplyPlan,
  buildLocationApplyPlan,
  collectAddedPromptLines,
  matchesFolderFilter,
  matchesSourceScope,
} from './utils'

const ASSET_TAB_TO_ENTITY_TYPE: Record<AssetTabKey, ScriptEntityType> = {
  character: 'character',
  location: 'location',
  voice: 'speaker',
}

const ASSET_TAB_TO_ASSET_TYPE: Record<AssetTabKey, 'character' | 'location' | 'voice'> = {
  character: 'character',
  location: 'location',
  voice: 'voice',
}

const STORYBOARD_EDITOR_SOURCE = 'storyboard_editor'
const STORYBOARD_EDITOR_AUTO_KEY = 'storyboard_editor_auto'
const STORYBOARD_EDITOR_ASSET_TYPE_KEY = 'storyboard_editor_asset_type'
const LEGACY_SCENE_EDITOR_AUTO_KEY = 'scene_editor_auto'
const LEGACY_SCENE_EDITOR_ASSET_TYPE_KEY = 'scene_editor_asset_type'

const CLEAR_BINDING_SUCCESS_MESSAGE: Record<AssetTabKey, string> = {
  character: '已清除角色覆盖',
  location: '已清除地点覆盖',
  voice: '已清除语音覆盖',
}

type PromptBindableTab = Extract<AssetTabKey, 'character' | 'location'>
type PromptBindableAsset = GlobalCharacterAsset | GlobalLocationAsset
type AssetBindActionOptions =
  | { tab: 'character'; asset: GlobalCharacterAsset; panelOverride?: Panel; planOverride?: AssetApplyPlan }
  | { tab: 'location'; asset: GlobalLocationAsset; panelOverride?: Panel; planOverride?: AssetApplyPlan }
  | { tab: 'voice'; asset: GlobalVoice; panelOverride?: Panel }

function buildStoryboardEditorStrategy(withPromptMode = false): Record<string, unknown> {
  return withPromptMode
    ? { apply_mode: DIRECT_BIND_PROMPT_MODE, source: STORYBOARD_EDITOR_SOURCE }
    : { source: STORYBOARD_EDITOR_SOURCE }
}

function buildPanelSearchText(panel: Panel): string {
  return [
    panel.title,
    panel.script_text ?? '',
    panel.visual_prompt ?? '',
    panel.tts_text ?? '',
  ].join(' ').toLowerCase()
}

function buildAutoEntityName(tab: AssetTabKey): string {
  if (tab === 'character') return '分镜编辑-自动角色实体'
  if (tab === 'location') return '分镜编辑-自动地点实体'
  return '分镜编辑-自动说话人实体'
}

function normalizeStoryboardEntityMeta(meta: Record<string, unknown> | null | undefined): {
  nextMeta: Record<string, unknown>
  isAuto: boolean
  assetType: string | null
  needsPersist: boolean
} {
  const source = meta && typeof meta === 'object' ? { ...meta } : {}
  const hasLegacyAuto = Object.prototype.hasOwnProperty.call(source, LEGACY_SCENE_EDITOR_AUTO_KEY)
  const hasLegacyAssetType = Object.prototype.hasOwnProperty.call(source, LEGACY_SCENE_EDITOR_ASSET_TYPE_KEY)
  const hasNextAuto = Object.prototype.hasOwnProperty.call(source, STORYBOARD_EDITOR_AUTO_KEY)
  const hasNextAssetType = Object.prototype.hasOwnProperty.call(source, STORYBOARD_EDITOR_ASSET_TYPE_KEY)

  const isAuto = Boolean(
    hasNextAuto ? source[STORYBOARD_EDITOR_AUTO_KEY] : source[LEGACY_SCENE_EDITOR_AUTO_KEY],
  )
  const assetTypeValue = hasNextAssetType
    ? source[STORYBOARD_EDITOR_ASSET_TYPE_KEY]
    : source[LEGACY_SCENE_EDITOR_ASSET_TYPE_KEY]
  const assetType = typeof assetTypeValue === 'string' && assetTypeValue.trim()
    ? assetTypeValue.trim()
    : null

  if (isAuto) {
    source[STORYBOARD_EDITOR_AUTO_KEY] = true
  } else {
    delete source[STORYBOARD_EDITOR_AUTO_KEY]
  }
  if (assetType) {
    source[STORYBOARD_EDITOR_ASSET_TYPE_KEY] = assetType
  } else {
    delete source[STORYBOARD_EDITOR_ASSET_TYPE_KEY]
  }

  delete source[LEGACY_SCENE_EDITOR_AUTO_KEY]
  delete source[LEGACY_SCENE_EDITOR_ASSET_TYPE_KEY]

  return {
    nextMeta: source,
    isAuto,
    assetType,
    needsPersist: hasLegacyAuto || hasLegacyAssetType,
  }
}

function normalizeStoryboardEntity(entity: ScriptEntity): ScriptEntity {
  const migration = normalizeStoryboardEntityMeta(entity.meta)
  return {
    ...entity,
    meta: migration.nextMeta,
  }
}

function buildPromptApplyPlan(tab: PromptBindableTab, panel: Panel, asset: PromptBindableAsset): AssetApplyPlan {
  if (tab === 'character') {
    return buildCharacterApplyPlan(panel, asset as GlobalCharacterAsset, DIRECT_BIND_PROMPT_MODE)
  }
  return buildLocationApplyPlan(panel, asset as GlobalLocationAsset, DIRECT_BIND_PROMPT_MODE)
}

function toOverrideKey(item: Pick<ScriptScopedOverride, 'entity_id' | 'asset_type' | 'asset_id' | 'role_tag'>): string {
  return `${item.entity_id}::${item.asset_type}::${item.asset_id}::${item.role_tag ?? ''}`
}

function normalizeOverridePrimary(overrides: ScriptScopedOverride[]): ScriptScopedOverride[] {
  const rows = overrides.map((item, index) => ({
    ...item,
    priority: Number.isFinite(item.priority) ? Number(item.priority) : index,
  }))
  const grouped = new Map<string, ScriptScopedOverride[]>()
  rows.forEach((item) => {
    const key = `${item.entity_id}::${item.asset_type}`
    const list = grouped.get(key) ?? []
    list.push(item)
    grouped.set(key, list)
  })
  grouped.forEach((items) => {
    if (items.length === 0) return
    const sorted = [...items].sort((a, b) => {
      const ap = a.is_primary ? 0 : 1
      const bp = b.is_primary ? 0 : 1
      if (ap !== bp) return ap - bp
      return Number(a.priority ?? 0) - Number(b.priority ?? 0)
    })
    const primary = sorted[0]
    items.forEach((item, idx) => {
      item.is_primary = item === primary
      item.priority = idx
    })
  })
  return rows
}


type FilterableAssetRow = {
  id: string
  is_active: boolean
  folder_id: string | null
  project_id: string | null
}

type AssetRowByTab = {
  character: GlobalCharacterAsset
  location: GlobalLocationAsset
  voice: GlobalVoice
}

type AssetRowsByTab = {
  [K in AssetTabKey]: AssetRowByTab[K][]
}

type AssetBoundIdsByTab = Record<AssetTabKey, Set<string>>

type AssetTabState = {
  label: string
  searchText: string
  folderFilter: string
  onlyBound: boolean
  sourceScope: AssetSourceScope
  visibleCount: number
  boundAssetId: string | null
}

function getAssetSearchTexts<K extends AssetTabKey>(tab: K, row: AssetRowByTab[K]): Array<string | null | undefined> {
  if (tab === 'character') {
    const item = row as GlobalCharacterAsset
    return [item.name, item.alias, item.description, item.prompt_template]
  }
  if (tab === 'location') {
    const item = row as GlobalLocationAsset
    return [item.name, item.description, item.prompt_template]
  }
  const item = row as GlobalVoice
  return [item.name, item.provider, item.voice_code, item.language]
}

function filterAssetRows<Row extends FilterableAssetRow>(options: {
  rows: Row[]
  keyword: string
  folderFilter: string
  sourceScope: AssetSourceScope
  projectId: string
  onlyBound: boolean
  boundIds: Set<string>
  searchTexts: (row: Row) => Array<string | null | undefined>
}): Row[] {
  const {
    rows,
    keyword,
    folderFilter,
    sourceScope,
    projectId,
    onlyBound,
    boundIds,
    searchTexts,
  } = options
  const normalizedKeyword = keyword.trim().toLowerCase()

  return rows.filter((item) => {
    if (!item.is_active) return false
    if (!matchesFolderFilter(item.folder_id, folderFilter)) return false
    if (!matchesSourceScope(item.project_id, projectId, sourceScope)) return false
    if (onlyBound && !boundIds.has(item.id)) return false
    if (!normalizedKeyword) return true

    return searchTexts(item)
      .filter(Boolean)
      .some((text) => String(text).toLowerCase().includes(normalizedKeyword))
  })
}

export interface UseAssetBindingReturn {
  assetOverview: AssetHubOverview | null
  assetLoading: boolean
  assetSaving: boolean
  bindPreview: BindPreviewState | null
  previewDiffOnly: boolean
  assetDrawer: AssetDrawerState
  assetAdvancedOpen: boolean
  selectedAssetPanel: Panel | null
  panelBinding: PanelAssetBinding
  filteredCharacters: GlobalCharacterAsset[]
  filteredLocations: GlobalLocationAsset[]
  filteredVoices: GlobalVoice[]
  folderMap: Map<string, string>
  folderFilterOptions: Array<{ label: string; value: string }>
  assetSearchTextByTab: Record<AssetTabKey, string>
  assetFolderFilterByTab: Record<AssetTabKey, string>
  onlyBoundFilterByTab: Record<AssetTabKey, boolean>
  assetSourceScopeByTab: Record<AssetTabKey, AssetSourceScope>
  currentAssetSearchText: string
  currentFolderFilter: string
  currentOnlyBoundFilter: boolean
  currentSourceScope: AssetSourceScope
  currentVisibleCount: number
  currentTabLabel: string
  setPreviewDiffOnly: (value: boolean) => void
  setBindPreview: (value: BindPreviewState | null) => void
  setAssetSearchTextByTab: Dispatch<SetStateAction<Record<AssetTabKey, string>>>
  setAssetFolderFilterByTab: Dispatch<SetStateAction<Record<AssetTabKey, string>>>
  setOnlyBoundFilterByTab: Dispatch<SetStateAction<Record<AssetTabKey, boolean>>>
  setAssetSourceScopeByTab: Dispatch<SetStateAction<Record<AssetTabKey, AssetSourceScope>>>
  setAssetAdvancedOpen: Dispatch<SetStateAction<boolean>>
  setAssetDrawer: Dispatch<SetStateAction<AssetDrawerState>>
  openAssetDrawer: (panel: Panel, tab?: AssetTabKey) => Promise<void>
  closeAssetDrawer: () => void
  applyVoiceToPanel: (voice: GlobalVoice, panelOverride?: Panel) => Promise<void>
  clearAssetBinding: (type: AssetTabKey) => Promise<void>
  removeAssetFromPanel: (type: AssetTabKey, assetId: string) => Promise<void>
  openCharacterBindPreview: (character: GlobalCharacterAsset) => void
  openLocationBindPreview: (location: GlobalLocationAsset) => void
  handleConfirmBindPreview: () => Promise<void>
  triggerClearBindingForCurrentTab: () => void
  getAssetEmptyText: (tab: AssetTabKey) => string
  ensureAssetOverview: (force?: boolean) => Promise<void>
}

export function useAssetBinding(
  projectId: string,
  panelsByEpisode: Record<string, Panel[]>,
  replacePanel: (updated: Panel) => void,
): UseAssetBindingReturn {
  const { message } = AntdApp.useApp()
  const assetOverview = useAssetHubStore((state) => state.overview)
  const assetLoading = useAssetHubStore((state) => state.loading)
  const loadAssetOverview = useAssetHubStore((state) => state.loadOverview)
  const latestProjectIdRef = useRef(projectId)
  const [assetSaving, setAssetSaving] = useState(false)
  const [bindPreview, setBindPreview] = useState<BindPreviewState | null>(null)
  const [previewDiffOnly, setPreviewDiffOnly] = useState(true)
  const [assetSearchTextByTab, setAssetSearchTextByTab] = useState<Record<AssetTabKey, string>>(DEFAULT_ASSET_SEARCH_TEXTS)
  const [assetFolderFilterByTab, setAssetFolderFilterByTab] = useState<Record<AssetTabKey, string>>(DEFAULT_ASSET_FOLDER_FILTERS)
  const [onlyBoundFilterByTab, setOnlyBoundFilterByTab] = useState<Record<AssetTabKey, boolean>>(DEFAULT_ONLY_BOUND_FILTERS)
  const [assetSourceScopeByTab, setAssetSourceScopeByTab] = useState<Record<AssetTabKey, AssetSourceScope>>(DEFAULT_ASSET_SOURCE_SCOPES)
  const [assetAdvancedOpen, setAssetAdvancedOpen] = useState(false)
  const [assetDrawer, setAssetDrawer] = useState<AssetDrawerState>({ open: false, panelId: null, tab: 'character' })
  const [scriptEntities, setScriptEntities] = useState<ScriptEntity[]>([])

  useEffect(() => {
    latestProjectIdRef.current = projectId
    setScriptEntities([])
  }, [projectId])

  const folderMap = useMemo(() => {
    return new Map((assetOverview?.folders ?? []).map((item) => [item.id, item.name]))
  }, [assetOverview?.folders])

  const folderFilterOptions = useMemo(() => ([
    { label: '全部目录', value: 'all' },
    { label: '未分组', value: '__none__' },
    ...(assetOverview?.folders ?? []).map((item) => ({ label: item.name, value: item.id })),
  ]), [assetOverview?.folders])

  const allPanels = useMemo(() => Object.values(panelsByEpisode).flat(), [panelsByEpisode])

  const selectedAssetPanel = useMemo(() => {
    if (!assetDrawer.panelId) return null
    return allPanels.find((panel) => panel.id === assetDrawer.panelId) ?? null
  }, [allPanels, assetDrawer.panelId])

  const panelBinding = useMemo(
    () => parsePanelBinding(selectedAssetPanel),
    [selectedAssetPanel],
  )

  const assetRowsByTab = useMemo<AssetRowsByTab>(() => ({
    character: assetOverview?.characters ?? [],
    location: assetOverview?.locations ?? [],
    voice: assetOverview?.voices ?? [],
  }), [assetOverview?.characters, assetOverview?.locations, assetOverview?.voices])

  const boundAssetIdsByTab = useMemo<AssetBoundIdsByTab>(() => ({
    character: new Set(getPanelBindingAssetIds(panelBinding, 'character')),
    location: new Set(getPanelBindingAssetIds(panelBinding, 'location')),
    voice: new Set(getPanelBindingAssetIds(panelBinding, 'voice')),
  }), [panelBinding])

  const resolvePanel = useCallback((panelId: string): Panel | null => {
    return allPanels.find((item) => item.id === panelId) ?? null
  }, [allPanels])

  const resolveCurrentPanel = useCallback((panelOverride?: Panel | null): Panel | null => {
    const targetPanel = panelOverride ?? selectedAssetPanel
    if (!targetPanel) return null
    return resolvePanel(targetPanel.id) ?? targetPanel
  }, [resolvePanel, selectedAssetPanel])

  const persistLegacyStoryboardEntityMeta = useCallback(async (rows: ScriptEntity[]) => {
    const requestProjectId = latestProjectIdRef.current
    const updates = rows.flatMap((entity) => {
      const migration = normalizeStoryboardEntityMeta(entity.meta)
      if (!migration.needsPersist) return []
      return [{ entityId: entity.id, meta: migration.nextMeta }]
    })
    if (updates.length <= 0) return

    const settled = await Promise.allSettled(
      updates.map((item) => updateScriptEntity(item.entityId, { meta: item.meta })),
    )
    const migrated = settled
      .filter((item): item is PromiseFulfilledResult<ScriptEntity> => item.status === 'fulfilled')
      .map((item) => normalizeStoryboardEntity(item.value))
    if (migrated.length <= 0) return
    if (latestProjectIdRef.current !== requestProjectId) return

    setScriptEntities((prev) => {
      const nextMap = new Map(prev.map((item) => [item.id, item]))
      migrated.forEach((item) => nextMap.set(item.id, item))
      return Array.from(nextMap.values())
    })
  }, [latestProjectIdRef])

  const ensureScriptEntities = useCallback(async (force = false): Promise<ScriptEntity[]> => {
    if (!force && scriptEntities.length > 0) return scriptEntities
    const requestProjectId = projectId
    const rows = await listScriptEntities(projectId)
    if (latestProjectIdRef.current !== requestProjectId) return []
    const normalizedRows = rows.map((item) => normalizeStoryboardEntity(item))
    setScriptEntities(normalizedRows)
    void persistLegacyStoryboardEntityMeta(rows)
    return normalizedRows
  }, [latestProjectIdRef, persistLegacyStoryboardEntityMeta, projectId, scriptEntities])

  const upsertScriptEntity = useCallback((entity: ScriptEntity) => {
    const normalizedEntity = normalizeStoryboardEntity(entity)
    setScriptEntities((prev) => {
      const idx = prev.findIndex((item) => item.id === normalizedEntity.id)
      if (idx < 0) return [...prev, normalizedEntity]
      const next = [...prev]
      next[idx] = normalizedEntity
      return next
    })
  }, [])

  const ensureEntityForTab = useCallback(async (
    tab: AssetTabKey,
    assetId: string,
    panel: Panel,
  ): Promise<ScriptEntity> => {
    const entityType = ASSET_TAB_TO_ENTITY_TYPE[tab]
    const assetType = ASSET_TAB_TO_ASSET_TYPE[tab]
    const entities = await ensureScriptEntities()
    const typed = entities.filter((item) => item.entity_type === entityType)
    const hitByBinding = typed.find((item) => item.bindings.some((binding) => (
      binding.asset_type === assetType && binding.asset_id === assetId
    )))
    if (hitByBinding) return hitByBinding

    const panelText = buildPanelSearchText(panel)
    const hitByName = typed.find((item) => {
      const name = item.name.trim().toLowerCase()
      const alias = (item.alias ?? '').trim().toLowerCase()
      return Boolean((name && panelText.includes(name)) || (alias && panelText.includes(alias)))
    })
    if (hitByName) return hitByName

    const autoEntity = typed.find((item) => {
      const migration = normalizeStoryboardEntityMeta(item.meta)
      return migration.isAuto && migration.assetType === assetType
    })
    if (autoEntity) return autoEntity

    const created = await createScriptEntity(projectId, {
      entity_type: entityType,
      name: buildAutoEntityName(tab),
      description: '由分镜资产覆盖自动创建',
      meta: {
        [STORYBOARD_EDITOR_AUTO_KEY]: true,
        [STORYBOARD_EDITOR_ASSET_TYPE_KEY]: assetType,
      },
      bindings: [],
    })
    upsertScriptEntity(created)
    return created
  }, [ensureScriptEntities, projectId, upsertScriptEntity])

  const applyPanelOverrides = useCallback(async (
    panel: Panel,
    overrides: ScriptScopedOverride[],
  ): Promise<Panel> => {
    const normalized = normalizeOverridePrimary(overrides)
    const savedOverrides = await replacePanelAssetOverrides(panel.id, normalized)
    let effective = panel.effective_binding
    try {
      effective = await getPanelEffectiveBindings(panel.id)
    } catch {
      // 编译读取失败时保留旧值，避免阻断本地状态刷新
    }
    const updated = buildResolvedPanelBindingState(panel, {
      assetOverrides: savedOverrides,
      effectiveBinding: effective,
    })
    replacePanel(updated)
    return updated
  }, [replacePanel])

  const upsertOverrides = useCallback((
    base: ScriptScopedOverride[],
    additions: ScriptScopedOverride[],
    options?: {
      clearType?: AssetTabKey
      removeType?: AssetTabKey
      removeAssetIds?: string[]
    },
  ): ScriptScopedOverride[] => {
    const removeSet = new Set(options?.removeAssetIds ?? [])
    const removeAssetType = options?.removeType ? ASSET_TAB_TO_ASSET_TYPE[options.removeType] : null
    const clearAssetType = options?.clearType ? ASSET_TAB_TO_ASSET_TYPE[options.clearType] : null
    const kept = base.filter((item) => {
      if (clearAssetType && item.asset_type === clearAssetType) return false
      if (removeAssetType && item.asset_type === removeAssetType && removeSet.has(item.asset_id)) return false
      return true
    })
    const nextMap = new Map<string, ScriptScopedOverride>()
    kept.forEach((item) => nextMap.set(toOverrideKey(item), { ...item }))
    additions.forEach((item) => nextMap.set(toOverrideKey(item), { ...item }))
    return normalizeOverridePrimary(Array.from(nextMap.values()))
  }, [])

  const bindPanelAsset = useCallback(async (options: {
    panel: Panel
    tab: AssetTabKey
    assetId: string
    assetName: string
    strategy?: Record<string, unknown>
    clearType?: AssetTabKey
    promptUpdate?: {
      nextPrompt: string | null
      nextReferenceImageUrl: string | null
    }
  }): Promise<Panel> => {
    let nextPanel = options.panel
    if (options.promptUpdate) {
      nextPanel = await updatePanel(nextPanel.id, {
        visual_prompt: options.promptUpdate.nextPrompt,
        reference_image_url: options.promptUpdate.nextReferenceImageUrl,
      })
      replacePanel(nextPanel)
    }

    const entity = await ensureEntityForTab(options.tab, options.assetId, nextPanel)
    const currentOverrides = nextPanel.asset_overrides ?? []
    const assetType = ASSET_TAB_TO_ASSET_TYPE[options.tab]
    const hasOverride = currentOverrides.some((item) => item.asset_type === assetType)
    const mergedOverrides = upsertOverrides(currentOverrides, [{
      entity_id: entity.id,
      asset_type: assetType,
      asset_id: options.assetId,
      asset_name: options.assetName,
      priority: 0,
      is_primary: options.clearType ? true : !hasOverride,
      strategy: options.strategy,
    }], options.clearType ? { clearType: options.clearType } : undefined)
    return applyPanelOverrides(nextPanel, mergedOverrides)
  }, [applyPanelOverrides, ensureEntityForTab, replacePanel, upsertOverrides])

  const runAssetSavingAction = useCallback(async (options: {
    panel?: Panel | null
    errorMessage: string
    successMessage?: string
    action: (panel: Panel) => Promise<void>
  }): Promise<boolean> => {
    const targetPanel = resolveCurrentPanel(options.panel)
    if (!targetPanel) return false

    setAssetSaving(true)
    try {
      await options.action(targetPanel)
      if (options.successMessage) {
        message.success(options.successMessage)
      }
      return true
    } catch (error) {
      message.error(getApiErrorMessage(error, options.errorMessage))
      return false
    } finally {
      setAssetSaving(false)
    }
  }, [message, resolveCurrentPanel])

  const filteredAssetsByTab = useMemo<AssetRowsByTab>(() => ({
    character: filterAssetRows({
      rows: assetRowsByTab.character,
      keyword: assetSearchTextByTab.character,
      folderFilter: assetFolderFilterByTab.character,
      sourceScope: assetSourceScopeByTab.character,
      projectId,
      onlyBound: onlyBoundFilterByTab.character,
      boundIds: boundAssetIdsByTab.character,
      searchTexts: (row) => getAssetSearchTexts('character', row),
    }),
    location: filterAssetRows({
      rows: assetRowsByTab.location,
      keyword: assetSearchTextByTab.location,
      folderFilter: assetFolderFilterByTab.location,
      sourceScope: assetSourceScopeByTab.location,
      projectId,
      onlyBound: onlyBoundFilterByTab.location,
      boundIds: boundAssetIdsByTab.location,
      searchTexts: (row) => getAssetSearchTexts('location', row),
    }),
    voice: filterAssetRows({
      rows: assetRowsByTab.voice,
      keyword: assetSearchTextByTab.voice,
      folderFilter: assetFolderFilterByTab.voice,
      sourceScope: assetSourceScopeByTab.voice,
      projectId,
      onlyBound: onlyBoundFilterByTab.voice,
      boundIds: boundAssetIdsByTab.voice,
      searchTexts: (row) => getAssetSearchTexts('voice', row),
    }),
  }), [
    assetFolderFilterByTab,
    assetRowsByTab,
    assetSearchTextByTab,
    assetSourceScopeByTab,
    boundAssetIdsByTab,
    onlyBoundFilterByTab,
    projectId,
  ])

  const filteredCharacters = filteredAssetsByTab.character
  const filteredLocations = filteredAssetsByTab.location
  const filteredVoices = filteredAssetsByTab.voice

  const assetTabStateByTab = useMemo<Record<AssetTabKey, AssetTabState>>(() => ({
    character: {
      label: assetTabLabel('character'),
      searchText: assetSearchTextByTab.character,
      folderFilter: assetFolderFilterByTab.character,
      onlyBound: onlyBoundFilterByTab.character,
      sourceScope: assetSourceScopeByTab.character,
      visibleCount: filteredAssetsByTab.character.length,
      boundAssetId: getPanelBindingPrimaryAssetId(panelBinding, 'character'),
    },
    location: {
      label: assetTabLabel('location'),
      searchText: assetSearchTextByTab.location,
      folderFilter: assetFolderFilterByTab.location,
      onlyBound: onlyBoundFilterByTab.location,
      sourceScope: assetSourceScopeByTab.location,
      visibleCount: filteredAssetsByTab.location.length,
      boundAssetId: getPanelBindingPrimaryAssetId(panelBinding, 'location'),
    },
    voice: {
      label: assetTabLabel('voice'),
      searchText: assetSearchTextByTab.voice,
      folderFilter: assetFolderFilterByTab.voice,
      onlyBound: onlyBoundFilterByTab.voice,
      sourceScope: assetSourceScopeByTab.voice,
      visibleCount: filteredAssetsByTab.voice.length,
      boundAssetId: getPanelBindingPrimaryAssetId(panelBinding, 'voice'),
    },
  }), [
    assetFolderFilterByTab,
    assetSearchTextByTab,
    assetSourceScopeByTab,
    filteredAssetsByTab,
    onlyBoundFilterByTab,
    panelBinding,
  ])

  const currentTabState = assetTabStateByTab[assetDrawer.tab]
  const currentAssetSearchText = currentTabState.searchText
  const currentFolderFilter = currentTabState.folderFilter
  const currentOnlyBoundFilter = currentTabState.onlyBound
  const currentSourceScope = currentTabState.sourceScope
  const currentVisibleCount = currentTabState.visibleCount
  const currentTabLabel = currentTabState.label

  const getAssetEmptyText = useCallback((tab: AssetTabKey): string => {
    const tabState = assetTabStateByTab[tab]
    const hasSearch = tabState.searchText.trim().length > 0
    const hasFolderFilter = tabState.folderFilter !== 'all'
    const hasSourceFilter = tabState.sourceScope !== 'all'

    if (tabState.onlyBound && !tabState.boundAssetId) {
      return `当前分镜尚未绑定${tabState.label}，可先关闭"仅看已绑定"或执行绑定。`
    }

    if (hasSearch || hasFolderFilter || hasSourceFilter || tabState.onlyBound) {
      return `未命中${tabState.label}筛选结果，请调整筛选条件后重试。`
    }

    return `暂无可用${tabState.label}资产`
  }, [assetTabStateByTab])

  const ensureAssetOverview = useCallback(async (force = false) => {
    await loadAssetOverview({ force, projectId, scope: 'all' })
  }, [loadAssetOverview, projectId])

  const resetAssetDrawerContext = useCallback(() => {
    setBindPreview(null)
    setPreviewDiffOnly(true)
    setAssetAdvancedOpen(false)
  }, [])

  const openAssetDrawer = async (panel: Panel, tab?: AssetTabKey) => {
    resetAssetDrawerContext()
    setAssetDrawer((prev) => ({ open: true, panelId: panel.id, tab: tab ?? prev.tab }))
    try {
      await Promise.all([ensureAssetOverview(), ensureScriptEntities()])
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载资产上下文失败'))
    }
  }

  const closeAssetDrawer = () => {
    resetAssetDrawerContext()
    setAssetDrawer((prev) => ({ ...prev, open: false, panelId: null }))
  }

  const runOverrideUpdateAction = async (options: {
    type: AssetTabKey
    successMessage: string
    errorMessage: string
    removeAssetIds?: string[]
    clear?: boolean
  }) => {
    await runAssetSavingAction({
      errorMessage: options.errorMessage,
      successMessage: options.successMessage,
      action: async (panel) => {
        const mergedOverrides = upsertOverrides(panel.asset_overrides ?? [], [], options.clear
          ? { clearType: options.type }
          : { removeType: options.type, removeAssetIds: options.removeAssetIds })
        await applyPanelOverrides(panel, mergedOverrides)
      },
    })
  }

  const applyAssetToPanel = async (options: AssetBindActionOptions): Promise<boolean> => {
    const label = assetTabLabel(options.tab)
    return runAssetSavingAction({
      panel: options.panelOverride,
      errorMessage: `绑定${label}资产失败`,
      successMessage: `已绑定${label}资产：${options.asset.name}`,
      action: async (currentPanel) => {
        const promptUpdate = options.tab === 'voice'
          ? undefined
          : (() => {
            const plan = options.planOverride ?? buildPromptApplyPlan(
              options.tab,
              currentPanel,
              options.asset as PromptBindableAsset,
            )
            return {
              nextPrompt: plan.nextPrompt,
              nextReferenceImageUrl: plan.nextReferenceImageUrl,
            }
          })()

        await bindPanelAsset({
          panel: currentPanel,
          tab: options.tab,
          assetId: options.asset.id,
          assetName: options.asset.name,
          clearType: options.tab === 'voice' ? 'voice' : undefined,
          strategy: buildStoryboardEditorStrategy(options.tab !== 'voice'),
          promptUpdate,
        })
      },
    })
  }

  const applyCharacterToPanel = async (
    character: GlobalCharacterAsset,
    panelOverride?: Panel,
    planOverride?: ReturnType<typeof buildCharacterApplyPlan>,
  ): Promise<boolean> => applyAssetToPanel({
    tab: 'character',
    asset: character,
    panelOverride,
    planOverride,
  })

  const applyLocationToPanel = async (
    location: GlobalLocationAsset,
    panelOverride?: Panel,
    planOverride?: ReturnType<typeof buildLocationApplyPlan>,
  ): Promise<boolean> => applyAssetToPanel({
    tab: 'location',
    asset: location,
    panelOverride,
    planOverride,
  })

  const applyVoiceToPanel = async (voice: GlobalVoice, panelOverride?: Panel) => {
    await applyAssetToPanel({
      tab: 'voice',
      asset: voice,
      panelOverride,
    })
  }

  const clearAssetBinding = async (type: AssetTabKey) => {
    await runOverrideUpdateAction({
      type,
      clear: true,
      errorMessage: '清除绑定失败',
      successMessage: CLEAR_BINDING_SUCCESS_MESSAGE[type],
    })
  }

  const removeAssetFromPanel = async (type: AssetTabKey, assetId: string) => {
    await runOverrideUpdateAction({
      type,
      errorMessage: '解绑资产失败',
      successMessage: `已解绑${assetTabLabel(type)}资产`,
      removeAssetIds: [assetId],
    })
  }

  const openBindPreview = useCallback((preview: BindPreviewState) => {
    setBindPreview(preview)
    setPreviewDiffOnly(true)
  }, [])

  const createBindPreviewBase = useCallback((panel: Panel, nextPrompt: string | null) => ({
    panelId: panel.id,
    panelTitle: panel.title,
    originPrompt: panel.visual_prompt,
    addedPromptLines: collectAddedPromptLines(panel.visual_prompt, nextPrompt),
  }), [])

  const openPromptBindPreview = useCallback((tab: PromptBindableTab, asset: PromptBindableAsset) => {
    if (!selectedAssetPanel) return
    const plan = buildPromptApplyPlan(tab, selectedAssetPanel, asset)
    const previewBase = createBindPreviewBase(selectedAssetPanel, plan.nextPrompt)
    openBindPreview(tab === 'character'
      ? {
        type: 'character',
        ...previewBase,
        plan,
        character: asset as GlobalCharacterAsset,
      }
      : {
        type: 'location',
        ...previewBase,
        plan,
        location: asset as GlobalLocationAsset,
      })
  }, [createBindPreviewBase, openBindPreview, selectedAssetPanel])

  const openCharacterBindPreview = (character: GlobalCharacterAsset) => {
    openPromptBindPreview('character', character)
  }

  const openLocationBindPreview = (location: GlobalLocationAsset) => {
    openPromptBindPreview('location', location)
  }

  const handleConfirmBindPreview = async () => {
    if (!bindPreview) return
    const targetPanel = resolvePanel(bindPreview.panelId)
    if (!targetPanel) {
      message.warning('分镜已更新，请重新打开绑定抽屉后再试')
      setBindPreview(null)
      return
    }
    const success = bindPreview.type === 'character'
      ? await applyCharacterToPanel(bindPreview.character, targetPanel, bindPreview.plan)
      : await applyLocationToPanel(bindPreview.location, targetPanel, bindPreview.plan)
    if (!success) return
    setBindPreview(null)
    setPreviewDiffOnly(true)
  }

  const triggerClearBindingForCurrentTab = () => {
    void clearAssetBinding(assetDrawer.tab)
  }

  return {
    assetOverview,
    assetLoading,
    assetSaving,
    bindPreview,
    previewDiffOnly,
    assetDrawer,
    assetAdvancedOpen,
    selectedAssetPanel,
    panelBinding,
    filteredCharacters,
    filteredLocations,
    filteredVoices,
    folderMap,
    folderFilterOptions,
    assetSearchTextByTab,
    assetFolderFilterByTab,
    onlyBoundFilterByTab,
    assetSourceScopeByTab,
    currentAssetSearchText,
    currentFolderFilter,
    currentOnlyBoundFilter,
    currentSourceScope,
    currentVisibleCount,
    currentTabLabel,
    setPreviewDiffOnly,
    setBindPreview,
    setAssetSearchTextByTab,
    setAssetFolderFilterByTab,
    setOnlyBoundFilterByTab,
    setAssetSourceScopeByTab,
    setAssetAdvancedOpen,
    setAssetDrawer,
    openAssetDrawer,
    closeAssetDrawer,
    applyVoiceToPanel,
    clearAssetBinding,
    removeAssetFromPanel,
    openCharacterBindPreview,
    openLocationBindPreview,
    handleConfirmBindPreview,
    triggerClearBindingForCurrentTab,
    getAssetEmptyText,
    ensureAssetOverview,
  }
}
