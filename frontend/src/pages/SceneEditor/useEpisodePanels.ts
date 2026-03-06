import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App as AntdApp } from 'antd'
import type { Episode } from '../../types/episode'
import type { Panel } from '../../types/panel'
import { listEpisodes } from '../../api/episodes'
import { createPanel, deletePanel, listEpisodePanels, reorderPanels, updatePanel } from '../../api/panels'
import { getApiErrorMessage } from '../../utils/error'
import type { PanelEditDraft } from './types'
import { moveItem } from './utils'

export interface UseEpisodePanelsReturn {
  loading: boolean
  episodes: Episode[]
  panelsByEpisode: Record<string, Panel[]>
  activeEpisodeId: string | null
  activePanels: Panel[]
  newPanelTitle: string
  editingPanel: Panel | null
  panelEditDraft: PanelEditDraft | null
  panelEditSaving: boolean
  setNewPanelTitle: (value: string) => void
  setPanelEditDraft: React.Dispatch<React.SetStateAction<PanelEditDraft | null>>
  setEpisodes: React.Dispatch<React.SetStateAction<Episode[]>>
  setPanelsByEpisode: React.Dispatch<React.SetStateAction<Record<string, Panel[]>>>
  handleSelectEpisode: (episodeId: string) => Promise<void>
  handleCreatePanel: () => Promise<void>
  openPanelEditor: (panel: Panel) => void
  closePanelEditor: () => void
  handleSavePanelDetail: () => Promise<void>
  handleDeletePanel: (panel: Panel) => Promise<void>
  handleBatchDeletePanels: (panels: Panel[]) => Promise<void>
  handleMovePanel: (from: number, to: number) => Promise<void>
  handleReorderPanels: (panelIds: string[]) => Promise<void>
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
  const [editingPanel, setEditingPanel] = useState<Panel | null>(null)
  const [panelEditDraft, setPanelEditDraft] = useState<PanelEditDraft | null>(null)
  const [panelEditSaving, setPanelEditSaving] = useState(false)
  const invalidLockNotifiedRef = useRef<string | null>(null)

  const activePanels = useMemo(
    () => (activeEpisodeId ? (panelsByEpisode[activeEpisodeId] ?? []) : []),
    [activeEpisodeId, panelsByEpisode],
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
      setEpisodes((prev) => prev.map((item) => (
        item.id === activeEpisodeId ? { ...item, panel_count: item.panel_count + 1 } : item
      )))
      setNewPanelTitle('')
      message.success('已创建分镜')
    } catch (error) {
      message.error(getApiErrorMessage(error, '创建分镜失败'))
    }
  }

  const openPanelEditor = (panel: Panel) => {
    setEditingPanel(panel)
    setPanelEditDraft({
      title: panel.title || '',
      script_text: panel.script_text || '',
      visual_prompt: panel.visual_prompt || '',
      negative_prompt: panel.negative_prompt || '',
      camera_hint: panel.camera_hint || '',
      duration_seconds: Number.isFinite(panel.duration_seconds) ? panel.duration_seconds : 5,
      style_preset: panel.style_preset || '',
      reference_image_url: panel.reference_image_url || '',
      tts_text: panel.tts_text || '',
    })
  }

  const closePanelEditor = () => {
    if (panelEditSaving) return
    setEditingPanel(null)
    setPanelEditDraft(null)
  }

  const normalizeNullableText = (value: string): string | null => {
    const trimmed = value.trim()
    return trimmed ? trimmed : null
  }

  const handleSavePanelDetail = async () => {
    if (!editingPanel || !panelEditDraft) return
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
      const updated = await updatePanel(editingPanel.id, {
        title,
        script_text: normalizeNullableText(panelEditDraft.script_text),
        visual_prompt: normalizeNullableText(panelEditDraft.visual_prompt),
        negative_prompt: normalizeNullableText(panelEditDraft.negative_prompt),
        camera_hint: normalizeNullableText(panelEditDraft.camera_hint),
        duration_seconds: Math.max(0.1, duration),
        style_preset: normalizeNullableText(panelEditDraft.style_preset),
        reference_image_url: normalizeNullableText(panelEditDraft.reference_image_url),
        tts_text: normalizeNullableText(panelEditDraft.tts_text),
      })
      setPanelsByEpisode((prev) => ({
        ...prev,
        [editingPanel.episode_id]: (prev[editingPanel.episode_id] ?? []).map((item) => (item.id === editingPanel.id ? updated : item)),
      }))
      message.success('分镜详情已更新')
      setEditingPanel(null)
      setPanelEditDraft(null)
    } catch (error) {
      message.error(getApiErrorMessage(error, '更新分镜详情失败'))
    } finally {
      setPanelEditSaving(false)
    }
  }

  const handleDeletePanel = async (panel: Panel) => {
    try {
      await deletePanel(panel.id)
      setPanelsByEpisode((prev) => ({
        ...prev,
        [panel.episode_id]: (prev[panel.episode_id] ?? []).filter((item) => item.id !== panel.id),
      }))
      setEpisodes((prev) => prev.map((item) => (
        item.id === panel.episode_id ? { ...item, panel_count: Math.max(0, item.panel_count - 1) } : item
      )))
      message.success('已删除分镜')
    } catch (error) {
      message.error(getApiErrorMessage(error, '删除分镜失败'))
    }
  }

  const handleBatchDeletePanels = async (panels: Panel[]) => {
    if (panels.length === 0) return
    const deleteIds = new Set(panels.map((p) => p.id))
    try {
      await Promise.all(panels.map((p) => deletePanel(p.id)))
      setPanelsByEpisode((prev) => {
        const next = { ...prev }
        for (const key of Object.keys(next)) {
          next[key] = (next[key] ?? []).filter((item) => !deleteIds.has(item.id))
        }
        return next
      })
      const episodeCounts = new Map<string, number>()
      for (const panel of panels) {
        episodeCounts.set(panel.episode_id, (episodeCounts.get(panel.episode_id) ?? 0) + 1)
      }
      setEpisodes((prev) => prev.map((ep) => {
        const count = episodeCounts.get(ep.id) ?? 0
        return count > 0 ? { ...ep, panel_count: Math.max(0, ep.panel_count - count) } : ep
      }))
      message.success(`已批量删除 ${panels.length} 个分镜`)
    } catch (error) {
      message.error(getApiErrorMessage(error, '批量删除分镜失败'))
      if (activeEpisodeId) await loadPanels(activeEpisodeId)
    }
  }

  const handleMovePanel = async (from: number, to: number) => {
    if (!activeEpisodeId) return
    const current = activePanels
    const reordered = moveItem(current, from, to)
    setPanelsByEpisode((prev) => ({
      ...prev,
      [activeEpisodeId]: reordered.map((item, idx) => ({ ...item, panel_order: idx })),
    }))
    try {
      await reorderPanels(activeEpisodeId, reordered.map((item) => item.id))
    } catch (error) {
      message.error(getApiErrorMessage(error, '分镜排序失败'))
      await loadPanels(activeEpisodeId)
    }
  }

  const handleReorderPanels = async (panelIds: string[]) => {
    if (!activeEpisodeId) return
    const current = activePanels
    const idToPanel = new Map(current.map((p) => [p.id, p]))
    const reordered = panelIds
      .map((id) => idToPanel.get(id))
      .filter((p): p is Panel => p != null)

    setPanelsByEpisode((prev) => ({
      ...prev,
      [activeEpisodeId]: reordered.map((item, idx) => ({ ...item, panel_order: idx })),
    }))
    try {
      await reorderPanels(activeEpisodeId, panelIds)
    } catch (error) {
      message.error(getApiErrorMessage(error, '分镜排序失败'))
      await loadPanels(activeEpisodeId)
    }
  }

  return {
    loading,
    episodes,
    panelsByEpisode,
    activeEpisodeId,
    activePanels,
    newPanelTitle,
    editingPanel,
    panelEditDraft,
    panelEditSaving,
    setNewPanelTitle,
    setPanelEditDraft,
    setEpisodes,
    setPanelsByEpisode,
    handleSelectEpisode,
    handleCreatePanel,
    openPanelEditor,
    closePanelEditor,
    handleSavePanelDetail,
    handleDeletePanel,
    handleBatchDeletePanels,
    handleMovePanel,
    handleReorderPanels,
    replacePanel,
    reload,
    loadPanels,
  }
}
