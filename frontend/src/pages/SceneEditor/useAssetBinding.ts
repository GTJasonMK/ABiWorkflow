import { type Dispatch, type SetStateAction, useCallback, useEffect, useMemo, useState } from 'react'
import { App as AntdApp } from 'antd'
import type { Panel } from '../../types/panel'
import type { AssetHubOverview, GlobalCharacterAsset, GlobalLocationAsset, GlobalVoice } from '../../types/assetHub'
import { updatePanel } from '../../api/panels'
import {
  createScriptEntity,
  getPanelEffectiveBindings,
  listScriptEntities,
  replacePanelAssetOverrides,
} from '../../api/scriptAssets'
import { getApiErrorMessage } from '../../utils/error'
import { useAssetHubStore } from '../../stores/assetHubStore'
import type { ScriptEntity, ScriptEntityType, ScriptScopedOverride } from '../../types/scriptAssets'
import type {
  AssetDrawerState,
  AssetSourceScope,
  AssetTabKey,
  BindPreviewState,
  PanelAssetBinding,
} from './types'
import {
  DIRECT_BIND_PROMPT_MODE,
  DEFAULT_ASSET_FOLDER_FILTERS,
  DEFAULT_ASSET_SEARCH_TEXTS,
  DEFAULT_ASSET_SOURCE_SCOPES,
  DEFAULT_ONLY_BOUND_FILTERS,
} from './types'
import {
  assetTabLabel,
  buildCharacterApplyPlan,
  buildLocationApplyPlan,
  collectAddedPromptLines,
  matchesFolderFilter,
  matchesSourceScope,
  parsePanelBinding,
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

function getPrimaryFromEffective(
  effective: Panel['effective_binding'] | null,
  type: AssetTabKey,
): { assetId: string | null; assetName: string | null } {
  if (!effective || typeof effective !== 'object') {
    return { assetId: null, assetName: null }
  }
  if (type === 'voice') {
    const voice = effective.effective_voice
    const assetId = voice && typeof voice.voice_id === 'string' ? voice.voice_id : null
    const assetName = voice && typeof voice.voice_name === 'string' ? voice.voice_name : null
    return { assetId, assetName }
  }
  const list = type === 'character' ? effective.characters : effective.locations
  const firstPrimary = list.find((item) => Boolean(item?.is_primary)) ?? list[0]
  if (!firstPrimary || typeof firstPrimary !== 'object') {
    return { assetId: null, assetName: null }
  }
  return {
    assetId: typeof firstPrimary.asset_id === 'string' ? firstPrimary.asset_id : null,
    assetName: typeof firstPrimary.asset_name === 'string' ? firstPrimary.asset_name : null,
  }
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

  const selectedAssetPanel = useMemo(() => {
    if (!assetDrawer.panelId) return null
    const allPanels = Object.values(panelsByEpisode).flat()
    return allPanels.find((panel) => panel.id === assetDrawer.panelId) ?? null
  }, [assetDrawer.panelId, panelsByEpisode])

  const panelBinding = useMemo(
    () => parsePanelBinding(selectedAssetPanel),
    [selectedAssetPanel],
  )

  const selectedCharacterLinkIds = useMemo(
    () => new Set(panelBinding.asset_character_ids ?? []),
    [panelBinding.asset_character_ids],
  )
  const selectedLocationLinkIds = useMemo(
    () => new Set(panelBinding.asset_location_ids ?? []),
    [panelBinding.asset_location_ids],
  )
  const selectedVoiceLinkIds = useMemo(
    () => new Set(panelBinding.asset_voice_ids ?? []),
    [panelBinding.asset_voice_ids],
  )

  const resolvePanel = useCallback((panelId: string): Panel | null => {
    const allPanels = Object.values(panelsByEpisode).flat()
    return allPanels.find((item) => item.id === panelId) ?? null
  }, [panelsByEpisode])

  const ensureScriptEntities = useCallback(async (force = false): Promise<ScriptEntity[]> => {
    if (!force && scriptEntities.length > 0) return scriptEntities
    const rows = await listScriptEntities(projectId)
    setScriptEntities(rows)
    return rows
  }, [projectId, scriptEntities])

  const upsertScriptEntity = useCallback((entity: ScriptEntity) => {
    setScriptEntities((prev) => {
      const idx = prev.findIndex((item) => item.id === entity.id)
      if (idx < 0) return [...prev, entity]
      const next = [...prev]
      next[idx] = entity
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

    const panelText = [
      panel.title,
      panel.script_text ?? '',
      panel.visual_prompt ?? '',
      panel.tts_text ?? '',
    ].join(' ').toLowerCase()
    const hitByName = typed.find((item) => {
      const name = item.name.trim().toLowerCase()
      const alias = (item.alias ?? '').trim().toLowerCase()
      return Boolean((name && panelText.includes(name)) || (alias && panelText.includes(alias)))
    })
    if (hitByName) return hitByName

    const autoEntity = typed.find((item) => {
      const meta = (item.meta && typeof item.meta === 'object' ? item.meta : {}) as Record<string, unknown>
      return meta.scene_editor_auto === true && meta.scene_editor_asset_type === assetType
    })
    if (autoEntity) return autoEntity

    const autoName = tab === 'character'
      ? '场景编辑-自动角色实体'
      : tab === 'location'
        ? '场景编辑-自动地点实体'
        : '场景编辑-自动说话人实体'
    const created = await createScriptEntity(projectId, {
      entity_type: entityType,
      name: autoName,
      description: '由分镜资产覆盖自动创建',
      meta: {
        scene_editor_auto: true,
        scene_editor_asset_type: assetType,
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
    const effectiveVoice = getPrimaryFromEffective(effective, 'voice')
    const updated: Panel = {
      ...panel,
      asset_overrides: savedOverrides,
      effective_binding: effective,
      voice_id: effectiveVoice.assetId ?? null,
    }
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

  const filteredCharacters = useMemo(() => {
    const rows = assetOverview?.characters ?? []
    const keyword = assetSearchTextByTab.character.trim().toLowerCase()
    const folderFilter = assetFolderFilterByTab.character
    const sourceScope = assetSourceScopeByTab.character
    const onlyBound = onlyBoundFilterByTab.character
    return rows.filter((item) => {
      if (!item.is_active) return false
      if (!matchesFolderFilter(item.folder_id, folderFilter)) return false
      if (!matchesSourceScope(item.project_id, projectId, sourceScope)) return false
      if (onlyBound && !selectedCharacterLinkIds.has(item.id)) return false
      if (keyword) {
        return [item.name, item.alias, item.description, item.prompt_template]
          .filter(Boolean)
          .some((text) => String(text).toLowerCase().includes(keyword))
      }
      return true
    })
  }, [
    assetFolderFilterByTab.character,
    assetOverview,
    assetSearchTextByTab.character,
    assetSourceScopeByTab.character,
    onlyBoundFilterByTab.character,
    projectId,
    selectedCharacterLinkIds,
  ])

  const filteredLocations = useMemo(() => {
    const rows = assetOverview?.locations ?? []
    const keyword = assetSearchTextByTab.location.trim().toLowerCase()
    const folderFilter = assetFolderFilterByTab.location
    const sourceScope = assetSourceScopeByTab.location
    const onlyBound = onlyBoundFilterByTab.location
    return rows.filter((item) => {
      if (!item.is_active) return false
      if (!matchesFolderFilter(item.folder_id, folderFilter)) return false
      if (!matchesSourceScope(item.project_id, projectId, sourceScope)) return false
      if (onlyBound && !selectedLocationLinkIds.has(item.id)) return false
      if (keyword) {
        return [item.name, item.description, item.prompt_template]
          .filter(Boolean)
          .some((text) => String(text).toLowerCase().includes(keyword))
      }
      return true
    })
  }, [
    assetFolderFilterByTab.location,
    assetOverview,
    assetSearchTextByTab.location,
    assetSourceScopeByTab.location,
    onlyBoundFilterByTab.location,
    projectId,
    selectedLocationLinkIds,
  ])

  const filteredVoices = useMemo(() => {
    const rows = assetOverview?.voices ?? []
    const keyword = assetSearchTextByTab.voice.trim().toLowerCase()
    const folderFilter = assetFolderFilterByTab.voice
    const sourceScope = assetSourceScopeByTab.voice
    const onlyBound = onlyBoundFilterByTab.voice
    return rows.filter((item) => {
      if (!item.is_active) return false
      if (!matchesFolderFilter(item.folder_id, folderFilter)) return false
      if (!matchesSourceScope(item.project_id, projectId, sourceScope)) return false
      if (onlyBound && !selectedVoiceLinkIds.has(item.id)) return false
      if (keyword) {
        return [item.name, item.provider, item.voice_code, item.language]
          .filter(Boolean)
          .some((text) => String(text).toLowerCase().includes(keyword))
      }
      return true
    })
  }, [
    assetFolderFilterByTab.voice,
    assetOverview,
    assetSearchTextByTab.voice,
    assetSourceScopeByTab.voice,
    onlyBoundFilterByTab.voice,
    projectId,
    selectedVoiceLinkIds,
  ])

  const currentAssetSearchText = assetSearchTextByTab[assetDrawer.tab]
  const currentFolderFilter = assetFolderFilterByTab[assetDrawer.tab]
  const currentOnlyBoundFilter = onlyBoundFilterByTab[assetDrawer.tab]
  const currentSourceScope = assetSourceScopeByTab[assetDrawer.tab]

  const currentVisibleCount = useMemo(() => {
    if (assetDrawer.tab === 'character') return filteredCharacters.length
    if (assetDrawer.tab === 'location') return filteredLocations.length
    return filteredVoices.length
  }, [assetDrawer.tab, filteredCharacters.length, filteredLocations.length, filteredVoices.length])

  const boundAssetIdByTab = useMemo<Record<AssetTabKey, string | null>>(() => ({
    character: panelBinding.asset_character_id ?? (selectedCharacterLinkIds.values().next().value ?? null),
    location: panelBinding.asset_location_id ?? (selectedLocationLinkIds.values().next().value ?? null),
    voice: panelBinding.asset_voice_id ?? (selectedVoiceLinkIds.values().next().value ?? null),
  }), [
    panelBinding.asset_character_id,
    panelBinding.asset_location_id,
    panelBinding.asset_voice_id,
    selectedCharacterLinkIds,
    selectedLocationLinkIds,
    selectedVoiceLinkIds,
  ])

  const currentTabLabel = assetTabLabel(assetDrawer.tab)

  const getAssetEmptyText = useCallback((tab: AssetTabKey): string => {
    const label = assetTabLabel(tab)
    const onlyBound = onlyBoundFilterByTab[tab]
    const hasBound = Boolean(boundAssetIdByTab[tab])
    const hasSearch = assetSearchTextByTab[tab].trim().length > 0
    const hasFolderFilter = assetFolderFilterByTab[tab] !== 'all'
    const hasSourceFilter = assetSourceScopeByTab[tab] !== 'all'

    if (onlyBound && !hasBound) {
      return `当前分镜尚未绑定${label}，可先关闭"仅看已绑定"或执行绑定。`
    }

    if (hasSearch || hasFolderFilter || hasSourceFilter || onlyBound) {
      return `未命中${label}筛选结果，请调整筛选条件后重试。`
    }

    return `暂无可用${label}资产`
  }, [assetFolderFilterByTab, assetSearchTextByTab, assetSourceScopeByTab, boundAssetIdByTab, onlyBoundFilterByTab])

  const ensureAssetOverview = useCallback(async (force = false) => {
    await loadAssetOverview({ force, projectId, scope: 'all' })
  }, [loadAssetOverview, projectId])

  const openAssetDrawer = async (panel: Panel, tab?: AssetTabKey) => {
    setBindPreview(null)
    setAssetAdvancedOpen(false)
    setAssetDrawer((prev) => ({ open: true, panelId: panel.id, tab: tab ?? prev.tab }))
    try {
      await Promise.all([ensureAssetOverview(), ensureScriptEntities()])
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载资产上下文失败'))
    }
  }

  const closeAssetDrawer = () => {
    setBindPreview(null)
    setAssetAdvancedOpen(false)
    setAssetDrawer((prev) => ({ ...prev, open: false, panelId: null }))
  }

  const applyCharacterToPanel = async (
    character: GlobalCharacterAsset,
    panelOverride?: Panel,
    planOverride?: ReturnType<typeof buildCharacterApplyPlan>,
  ) => {
    const panel = panelOverride ?? selectedAssetPanel
    if (!panel) return
    setAssetSaving(true)
    try {
      const currentPanel = resolvePanel(panel.id) ?? panel
      const plan = planOverride ?? buildCharacterApplyPlan(
        currentPanel,
        character,
        DIRECT_BIND_PROMPT_MODE,
        assetOverview?.voices ?? [],
      )
      const panelAfterPrompt = await updatePanel(currentPanel.id, {
        visual_prompt: plan.nextPrompt,
        reference_image_url: plan.nextReferenceImageUrl,
      })
      replacePanel(panelAfterPrompt)

      const characterEntity = await ensureEntityForTab('character', character.id, panelAfterPrompt)
      const currentOverrides = panelAfterPrompt.asset_overrides ?? []
      const hasCharacterOverride = currentOverrides.some((item) => item.asset_type === 'character')
      const additions: ScriptScopedOverride[] = [{
        entity_id: characterEntity.id,
        asset_type: 'character',
        asset_id: character.id,
        asset_name: character.name,
        priority: 0,
        is_primary: !hasCharacterOverride,
        strategy: {
          apply_mode: DIRECT_BIND_PROMPT_MODE,
          source: 'scene_editor',
        },
      }]
      if (plan.fallbackVoiceId) {
        const voiceEntity = await ensureEntityForTab('voice', plan.fallbackVoiceId, panelAfterPrompt)
        const hasVoiceOverride = currentOverrides.some((item) => item.asset_type === 'voice')
        const effectiveVoice = getPrimaryFromEffective(panelAfterPrompt.effective_binding, 'voice')
        additions.push({
          entity_id: voiceEntity.id,
          asset_type: 'voice',
          asset_id: plan.fallbackVoiceId,
          asset_name: plan.fallbackVoiceName || effectiveVoice.assetName || null,
          priority: 0,
          is_primary: !hasVoiceOverride && !effectiveVoice.assetId,
          strategy: {
            source: 'scene_editor_character_fallback',
          },
        })
      }
      const mergedOverrides = upsertOverrides(currentOverrides, additions)
      await applyPanelOverrides(panelAfterPrompt, mergedOverrides)
      message.success(`已绑定角色资产：${character.name}`)
    } catch (error) {
      message.error(getApiErrorMessage(error, '绑定角色资产失败'))
    } finally {
      setAssetSaving(false)
    }
  }

  const applyLocationToPanel = async (
    location: GlobalLocationAsset,
    panelOverride?: Panel,
    planOverride?: ReturnType<typeof buildLocationApplyPlan>,
  ) => {
    const panel = panelOverride ?? selectedAssetPanel
    if (!panel) return
    setAssetSaving(true)
    try {
      const currentPanel = resolvePanel(panel.id) ?? panel
      const plan = planOverride ?? buildLocationApplyPlan(currentPanel, location, DIRECT_BIND_PROMPT_MODE)
      const panelAfterPrompt = await updatePanel(currentPanel.id, {
        visual_prompt: plan.nextPrompt,
        reference_image_url: plan.nextReferenceImageUrl,
      })
      replacePanel(panelAfterPrompt)

      const locationEntity = await ensureEntityForTab('location', location.id, panelAfterPrompt)
      const currentOverrides = panelAfterPrompt.asset_overrides ?? []
      const hasLocationOverride = currentOverrides.some((item) => item.asset_type === 'location')
      const mergedOverrides = upsertOverrides(currentOverrides, [{
        entity_id: locationEntity.id,
        asset_type: 'location',
        asset_id: location.id,
        asset_name: location.name,
        priority: 0,
        is_primary: !hasLocationOverride,
        strategy: {
          apply_mode: DIRECT_BIND_PROMPT_MODE,
          source: 'scene_editor',
        },
      }])
      await applyPanelOverrides(panelAfterPrompt, mergedOverrides)
      message.success(`已绑定地点资产：${location.name}`)
    } catch (error) {
      message.error(getApiErrorMessage(error, '绑定地点资产失败'))
    } finally {
      setAssetSaving(false)
    }
  }

  const applyVoiceToPanel = async (voice: GlobalVoice, panelOverride?: Panel) => {
    const targetPanel = panelOverride ?? selectedAssetPanel
    if (!targetPanel) return
    setAssetSaving(true)
    try {
      const currentPanel = resolvePanel(targetPanel.id) ?? targetPanel
      const voiceEntity = await ensureEntityForTab('voice', voice.id, currentPanel)
      const currentOverrides = currentPanel.asset_overrides ?? []
      const mergedOverrides = upsertOverrides(currentOverrides, [{
        entity_id: voiceEntity.id,
        asset_type: 'voice',
        asset_id: voice.id,
        asset_name: voice.name,
        priority: 0,
        is_primary: true,
        strategy: {
          source: 'scene_editor',
        },
      }], { clearType: 'voice' })
      await applyPanelOverrides(currentPanel, mergedOverrides)
      message.success(`已绑定语音资产：${voice.name}`)
    } catch (error) {
      message.error(getApiErrorMessage(error, '绑定语音资产失败'))
    } finally {
      setAssetSaving(false)
    }
  }

  const clearAssetBinding = async (type: AssetTabKey) => {
    if (!selectedAssetPanel) return
    setAssetSaving(true)
    try {
      const panel = resolvePanel(selectedAssetPanel.id) ?? selectedAssetPanel
      const mergedOverrides = upsertOverrides(panel.asset_overrides ?? [], [], { clearType: type })
      await applyPanelOverrides(panel, mergedOverrides)
      if (type === 'voice') {
        message.success('已清除语音覆盖')
      } else if (type === 'character') {
        message.success('已清除角色覆盖')
      } else {
        message.success('已清除地点覆盖')
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, '清除绑定失败'))
    } finally {
      setAssetSaving(false)
    }
  }

  const removeAssetFromPanel = async (type: AssetTabKey, assetId: string) => {
    if (!selectedAssetPanel) return
    setAssetSaving(true)
    try {
      const panel = resolvePanel(selectedAssetPanel.id) ?? selectedAssetPanel
      const mergedOverrides = upsertOverrides(panel.asset_overrides ?? [], [], { removeType: type, removeAssetIds: [assetId] })
      await applyPanelOverrides(panel, mergedOverrides)
      message.success(`已解绑${assetTabLabel(type)}资产`)
    } catch (error) {
      message.error(getApiErrorMessage(error, '解绑资产失败'))
    } finally {
      setAssetSaving(false)
    }
  }

  const openCharacterBindPreview = (character: GlobalCharacterAsset) => {
    if (!selectedAssetPanel) return
    const plan = buildCharacterApplyPlan(selectedAssetPanel, character, DIRECT_BIND_PROMPT_MODE, assetOverview?.voices ?? [])
    setBindPreview({
      type: 'character',
      panelId: selectedAssetPanel.id,
      panelTitle: selectedAssetPanel.title,
      originPrompt: selectedAssetPanel.visual_prompt,
      addedPromptLines: collectAddedPromptLines(selectedAssetPanel.visual_prompt, plan.nextPrompt),
      plan,
      character,
    })
    setPreviewDiffOnly(true)
  }

  const openLocationBindPreview = (location: GlobalLocationAsset) => {
    if (!selectedAssetPanel) return
    const plan = buildLocationApplyPlan(selectedAssetPanel, location, DIRECT_BIND_PROMPT_MODE)
    setBindPreview({
      type: 'location',
      panelId: selectedAssetPanel.id,
      panelTitle: selectedAssetPanel.title,
      originPrompt: selectedAssetPanel.visual_prompt,
      addedPromptLines: collectAddedPromptLines(selectedAssetPanel.visual_prompt, plan.nextPrompt),
      plan,
      location,
    })
    setPreviewDiffOnly(true)
  }

  const handleConfirmBindPreview = async () => {
    if (!bindPreview) return
    const targetPanel = Object.values(panelsByEpisode).flat().find((item) => item.id === bindPreview.panelId)
    if (!targetPanel) {
      message.warning('分镜已更新，请重新打开绑定抽屉后再试')
      setBindPreview(null)
      return
    }
    if (bindPreview.type === 'character') {
      await applyCharacterToPanel(bindPreview.character, targetPanel, bindPreview.plan)
    } else {
      await applyLocationToPanel(bindPreview.location, targetPanel, bindPreview.plan)
    }
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
