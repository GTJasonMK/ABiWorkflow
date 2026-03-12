import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App as AntdApp } from 'antd'
import type { Episode } from '../../types/episode'
import type { Panel } from '../../types/panel'
import { listEpisodes } from '../../api/episodes'
import {
  createPanel,
  deletePanel,
  generateEpisodePanels,
  listEpisodePanels,
  reorderPanels,
  updatePanel,
} from '../../api/panels'
import { getApiErrorMessage } from '../../utils/error'
import type { PanelEditDraft } from './types'

function toDraftText(value: string | null | undefined): string {
  return value ?? ''
}

function normalizeNullableText(value: string | null | undefined): string | null {
  const trimmed = (value ?? '').trim()
  return trimmed ? trimmed : null
}

function createPanelEditDraft(panel: Panel): PanelEditDraft {
  return {
    title: toDraftText(panel.title),
    script_text: toDraftText(panel.script_text),
    visual_prompt: toDraftText(panel.visual_prompt),
    negative_prompt: toDraftText(panel.negative_prompt),
    camera_hint: toDraftText(panel.camera_hint),
    duration_seconds: Number.isFinite(panel.duration_seconds) ? panel.duration_seconds : 5,
    style_preset: toDraftText(panel.style_preset),
    reference_image_url: toDraftText(panel.reference_image_url),
    tts_text: toDraftText(panel.tts_text),
  }
}

function buildPanelUpdatePayload(draft: PanelEditDraft) {
  const duration = Number(draft.duration_seconds)
  return {
    title: draft.title.trim(),
    script_text: normalizeNullableText(draft.script_text),
    visual_prompt: normalizeNullableText(draft.visual_prompt),
    negative_prompt: normalizeNullableText(draft.negative_prompt),
    camera_hint: normalizeNullableText(draft.camera_hint),
    duration_seconds: Math.max(0.1, duration),
    style_preset: normalizeNullableText(draft.style_preset),
    reference_image_url: normalizeNullableText(draft.reference_image_url),
    tts_text: normalizeNullableText(draft.tts_text),
  }
}

function applyOrderedPanels(panels: Panel[]): Panel[] {
  return panels.map((item, idx) => ({ ...item, panel_order: idx }))
}

export interface UseEpisodePanelsReturn {
  loading: boolean
  episodes: Episode[]
  panelsByEpisode: Record<string, Panel[]>
  activeEpisodeId: string | null
  activeEpisode: Episode | null
  activePanels: Panel[]
  newPanelTitle: string
  selectedPanelId: string | null
  selectedPanel: Panel | null
  panelEditDraft: PanelEditDraft | null
  panelEditDirty: boolean
  panelEditSaving: boolean
  panelGenerating: boolean
  setNewPanelTitle: (value: string) => void
  setPanelEditDraft: React.Dispatch<React.SetStateAction<PanelEditDraft | null>>
  setEpisodes: React.Dispatch<React.SetStateAction<Episode[]>>
  setPanelsByEpisode: React.Dispatch<React.SetStateAction<Record<string, Panel[]>>>
  handleSelectEpisode: (episodeId: string) => Promise<void>
  handleCreatePanel: () => Promise<void>
  selectPanel: (panelId: string | null) => void
  handleSavePanelDetail: () => Promise<void>
  handleDeletePanel: (panel: Panel) => Promise<void>
  handleReorderPanels: (panelIds: string[]) => Promise<void>
  handleGeneratePanels: () => Promise<void>
  replacePanel: (updated: Panel) => void
  reload: () => Promise<void>
  loadPanels: (episodeId: string) => Promise<void>
}

export function useEpisodePanels(
  projectId: string,
  initialEpisodeId: string | null = null,
  onEpisodeChange?: (episodeId: string | null) => void,
  lockedEpisodeId: string | null = null,
): UseEpisodePanelsReturn {
  const { message } = AntdApp.useApp()
  const [loading, setLoading] = useState(false)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [panelsByEpisode, setPanelsByEpisode] = useState<Record<string, Panel[]>>({})
  const [activeEpisodeId, setActiveEpisodeId] = useState<string | null>(null)
  const [newPanelTitle, setNewPanelTitle] = useState('')
  const [selectedPanelId, setSelectedPanelId] = useState<string | null>(null)
  const [panelEditDraft, setPanelEditDraft] = useState<PanelEditDraft | null>(null)
  const [panelEditDirty, setPanelEditDirty] = useState(false)
  const [panelEditSaving, setPanelEditSaving] = useState(false)
  const [panelGenerating, setPanelGenerating] = useState(false)
  const invalidLockNotifiedRef = useRef<string | null>(null)

  const activePanels = useMemo(
    () => (activeEpisodeId ? (panelsByEpisode[activeEpisodeId] ?? []) : []),
    [activeEpisodeId, panelsByEpisode],
  )

  const activeEpisode = useMemo(
    () => (activeEpisodeId ? episodes.find((item) => item.id === activeEpisodeId) ?? null : null),
    [activeEpisodeId, episodes],
  )

  const selectedPanel = useMemo(
    () => (selectedPanelId ? activePanels.find((item) => item.id === selectedPanelId) ?? null : null),
    [activePanels, selectedPanelId],
  )

  const replacePanel = useCallback((updated: Panel) => {
    setPanelsByEpisode((prev) => {
      const list = prev[updated.episode_id]
      if (!list) return prev
      return {
        ...prev,
        [updated.episode_id]: list.map((panel) => (panel.id === updated.id ? updated : panel)),
      }
    })
  }, [])

  const hydratePanelEditor = useCallback((panel: Panel | null) => {
    setSelectedPanelId(panel?.id ?? null)
    setPanelEditDraft(panel ? createPanelEditDraft(panel) : null)
    setPanelEditDirty(false)
  }, [])

  const updateEpisodePanelCount = useCallback((episodeId: string, delta: number) => {
    setEpisodes((prev) => prev.map((item) => (
      item.id === episodeId ? { ...item, panel_count: Math.max(0, item.panel_count + delta) } : item
    )))
  }, [])

  const loadPanels = useCallback(async (episodeId: string) => {
    const rows = await listEpisodePanels(episodeId)
    setPanelsByEpisode((prev) => ({ ...prev, [episodeId]: rows }))
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const rows = await listEpisodes(projectId)
      setEpisodes(rows)
      const firstId = rows[0]?.id ?? null
      const lockRequested = Boolean(lockedEpisodeId)
      const lockedExists = Boolean(lockedEpisodeId && rows.some((item) => item.id === lockedEpisodeId))
      if (lockRequested && !lockedExists) {
        setActiveEpisodeId(null)
        if (lockedEpisodeId && invalidLockNotifiedRef.current !== lockedEpisodeId) {
          message.warning('当前分集上下文无效，请返回剧本编辑重新选择分集')
          invalidLockNotifiedRef.current = lockedEpisodeId
        }
        return
      }
      invalidLockNotifiedRef.current = null
      const lockedId = lockedEpisodeId ?? null
      const targetEpisodeId = lockRequested && lockedId
        ? lockedId
        : (activeEpisodeId && rows.some((item) => item.id === activeEpisodeId) ? activeEpisodeId : firstId)
      setActiveEpisodeId(targetEpisodeId)
      if (targetEpisodeId) {
        await loadPanels(targetEpisodeId)
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载分集失败'))
    } finally {
      setLoading(false)
    }
  }, [activeEpisodeId, loadPanels, lockedEpisodeId, message, projectId])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    if (!onEpisodeChange) return
    onEpisodeChange(activeEpisodeId)
  }, [activeEpisodeId, onEpisodeChange])

  useEffect(() => {
    if (!initialEpisodeId) return
    if (lockedEpisodeId) return
    if (!episodes.some((item) => item.id === initialEpisodeId)) return
    setActiveEpisodeId((prev) => (prev === initialEpisodeId ? prev : initialEpisodeId))
    if (!panelsByEpisode[initialEpisodeId]) {
      void loadPanels(initialEpisodeId).catch((error) => {
        message.error(getApiErrorMessage(error, '加载分镜失败'))
      })
    }
  }, [episodes, initialEpisodeId, loadPanels, lockedEpisodeId, message, panelsByEpisode])

  useEffect(() => {
    if (!lockedEpisodeId) return
    if (!episodes.some((item) => item.id === lockedEpisodeId)) return
    if (activeEpisodeId !== lockedEpisodeId) {
      setActiveEpisodeId(lockedEpisodeId)
    }
    if (!panelsByEpisode[lockedEpisodeId]) {
      void loadPanels(lockedEpisodeId).catch((error) => {
        message.error(getApiErrorMessage(error, '加载分镜失败'))
      })
    }
  }, [activeEpisodeId, episodes, loadPanels, lockedEpisodeId, message, panelsByEpisode])

  const handleSelectEpisode = async (episodeId: string) => {
    if (lockedEpisodeId && episodeId !== lockedEpisodeId) return
    setActiveEpisodeId(episodeId)
    if (!panelsByEpisode[episodeId]) {
      try {
        await loadPanels(episodeId)
      } catch (error) {
        message.error(getApiErrorMessage(error, '加载分镜失败'))
      }
    }
  }

  useEffect(() => {
    if (!activeEpisodeId) {
      hydratePanelEditor(null)
      return
    }
    if (activePanels.length === 0) {
      hydratePanelEditor(null)
      return
    }

    if (selectedPanelId && activePanels.some((panel) => panel.id === selectedPanelId)) {
      // 用户编辑中不自动覆写草稿，只在草稿未初始化时补齐。
      if (!panelEditDraft && !panelEditDirty) {
        hydratePanelEditor(activePanels.find((panel) => panel.id === selectedPanelId) ?? activePanels[0] ?? null)
      }
      return
    }

    // 当前选择失效（首次加载/删除后/重新生成后）→ 默认选中第一条。
    if (!panelEditDirty) {
      hydratePanelEditor(activePanels[0] ?? null)
    }
  }, [activeEpisodeId, activePanels, hydratePanelEditor, panelEditDirty, panelEditDraft, selectedPanelId])

  const handleCreatePanel = async () => {
    if (!activeEpisodeId) return
    const title = newPanelTitle.trim()
    if (!title) {
      message.warning('请输入分镜标题')
      return
    }
    try {
      const created = await createPanel(activeEpisodeId, { title })
      setPanelsByEpisode((prev) => ({
        ...prev,
        [activeEpisodeId]: [...(prev[activeEpisodeId] ?? []), created].sort((a, b) => a.panel_order - b.panel_order),
      }))
      updateEpisodePanelCount(activeEpisodeId, 1)
      setNewPanelTitle('')
      hydratePanelEditor(created)
      message.success('已创建分镜')
    } catch (error) {
      message.error(getApiErrorMessage(error, '创建分镜失败'))
    }
  }

  const selectPanel = (panelId: string | null) => {
    if (!panelId) {
      hydratePanelEditor(null)
      return
    }
    const panel = activePanels.find((item) => item.id === panelId) ?? null
    hydratePanelEditor(panel)
  }

  const setPanelEditDraftWithDirty: React.Dispatch<React.SetStateAction<PanelEditDraft | null>> = (updater) => {
    setPanelEditDraft((prev) => {
      const next = typeof updater === 'function'
        ? (updater as (draft: PanelEditDraft | null) => PanelEditDraft | null)(prev)
        : updater
      setPanelEditDirty(next != null)
      return next
    })
  }

  const handleSavePanelDetail = async () => {
    if (!selectedPanel || !panelEditDraft) return
    const title = panelEditDraft.title.trim()
    if (!title) {
      message.warning('分镜标题不能为空')
      return
    }
    const duration = Number(panelEditDraft.duration_seconds)
    if (!Number.isFinite(duration) || duration <= 0) {
      message.warning('分镜时长必须大于 0 秒')
      return
    }

    setPanelEditSaving(true)
    try {
      const updated = await updatePanel(selectedPanel.id, buildPanelUpdatePayload(panelEditDraft))
      replacePanel(updated)
      message.success('分镜详情已更新')
      hydratePanelEditor(updated)
    } catch (error) {
      message.error(getApiErrorMessage(error, '更新分镜详情失败'))
    } finally {
      setPanelEditSaving(false)
    }
  }

  const handleDeletePanel = async (panel: Panel) => {
    const currentList = panelsByEpisode[panel.episode_id] ?? []
    const deletingIndex = currentList.findIndex((item) => item.id === panel.id)
    const nextSelection = panel.id === selectedPanelId
      ? (currentList.filter((item) => item.id !== panel.id)[deletingIndex]
        ?? currentList.filter((item) => item.id !== panel.id)[deletingIndex - 1]
        ?? null)
      : null

    try {
      await deletePanel(panel.id)
      setPanelsByEpisode((prev) => ({
        ...prev,
        [panel.episode_id]: (prev[panel.episode_id] ?? []).filter((item) => item.id !== panel.id),
      }))
      updateEpisodePanelCount(panel.episode_id, -1)
      if (panel.id === selectedPanelId) {
        hydratePanelEditor(nextSelection)
      }
      message.success('已删除分镜')
    } catch (error) {
      message.error(getApiErrorMessage(error, '删除分镜失败'))
    }
  }

  const applyActiveEpisodePanelOrder = useCallback((panels: Panel[]): Panel[] => {
    if (!activeEpisodeId) return panels
    const ordered = applyOrderedPanels(panels)
    setPanelsByEpisode((prev) => ({
      ...prev,
      [activeEpisodeId]: ordered,
    }))
    return ordered
  }, [activeEpisodeId])

  const handleReorderPanels = async (panelIds: string[]) => {
    if (!activeEpisodeId) return
    const idToPanel = new Map(activePanels.map((panel) => [panel.id, panel]))
    const reordered = panelIds
      .map((id) => idToPanel.get(id))
      .filter((panel): panel is Panel => panel != null)

    applyActiveEpisodePanelOrder(reordered)
    try {
      await reorderPanels(activeEpisodeId, panelIds)
    } catch (error) {
      message.error(getApiErrorMessage(error, '分镜排序失败'))
      await loadPanels(activeEpisodeId)
    }
  }

  const handleGeneratePanels = async () => {
    if (!activeEpisodeId) return
    if (!activeEpisode?.video_provider_key) {
      message.warning('当前分集未配置视频 Provider，请返回剧本编辑页设置')
      return
    }
    setPanelGenerating(true)
    try {
      const panels = await generateEpisodePanels(activeEpisodeId, {
        overwrite: true,
      })
      setPanelsByEpisode((prev) => ({ ...prev, [activeEpisodeId]: panels }))
      setEpisodes((prev) => prev.map((episode) => (
        episode.id === activeEpisodeId ? { ...episode, panel_count: panels.length } : episode
      )))
      hydratePanelEditor(panels[0] ?? null)
      message.success('分镜已生成')
    } catch (error) {
      message.error(getApiErrorMessage(error, '生成分镜失败'))
    } finally {
      setPanelGenerating(false)
    }
  }

  return {
    loading,
    episodes,
    panelsByEpisode,
    activeEpisodeId,
    activeEpisode,
    activePanels,
    newPanelTitle,
    selectedPanelId,
    selectedPanel,
    panelEditDraft,
    panelEditDirty,
    panelEditSaving,
    panelGenerating,
    setNewPanelTitle,
    setPanelEditDraft: setPanelEditDraftWithDirty,
    setEpisodes,
    setPanelsByEpisode,
    handleSelectEpisode,
    handleCreatePanel,
    selectPanel,
    handleSavePanelDetail,
    handleDeletePanel,
    handleReorderPanels,
    handleGeneratePanels,
    replacePanel,
    reload,
    loadPanels,
  }
}
