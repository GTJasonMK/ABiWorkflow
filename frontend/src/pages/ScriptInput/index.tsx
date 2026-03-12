import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Button, Drawer, Empty, Input, Modal, Select, Space, Spin, Tag, Typography, Card, App as AntdApp } from 'antd'
import {
  SaveOutlined,
  RobotOutlined,
  ScissorOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import ProjectSectionNav from '../../components/ProjectSectionNav'
import WorkflowSteps from '../../components/WorkflowSteps'
import { getApiErrorMessage } from '../../utils/error'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { useProjectWorkspace } from '../../hooks/useProjectWorkspace'
import { splitByLlm, splitByMarkers } from '../../api/imports'
import { updateProjectScriptWorkspace } from '../../api/projects'
import { listProviderConfigs } from '../../api/providers'
import { buildWorkflowStepPath, getWorkflowStepLabel } from '../../utils/workflow'
import type { Episode, EpisodeProviderPayloadDefaults, EpisodeWorkflowSummary } from '../../types/episode'
import type { WorkflowDefaults } from '../../types/project'
import type { ProviderConfig } from '../../types/provider'
import { extractAllowedVideoLengths } from '../../utils/providerConstraints'

const { TextArea } = Input
const { Paragraph } = Typography

interface EpisodeDraft {
  id?: string
  title: string
  summary: string | null
  script_text: string
  video_provider_key: string | null
  tts_provider_key: string | null
  lipsync_provider_key: string | null
  video_payload_defaults_text: string
  tts_payload_defaults_text: string
  lipsync_payload_defaults_text: string
  skipped_checks: string[]
  order: number
  panel_count?: number
  workflow_summary: EpisodeWorkflowSummary | null
}

function normalizeProviderKey(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function normalizeSkippedChecks(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<string>()
  const result: string[] = []
  value.forEach((item) => {
    if (typeof item !== 'string') return
    const normalized = item.trim()
    if (!normalized || seen.has(normalized)) return
    seen.add(normalized)
    result.push(normalized)
  })
  return result
}

function formatProviderPayloadDefaultsText(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length <= 0) return ''
  return JSON.stringify(value, null, 2)
}

function parseProviderPayloadDefaultsText(
  text: string,
  label: string,
): Record<string, unknown> {
  const normalized = text.trim()
  if (!normalized) return {}
  let parsed: unknown
  try {
    parsed = JSON.parse(normalized)
  } catch {
    throw new Error(`${label}默认参数不是合法 JSON`)
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label}默认参数必须是 JSON 对象`)
  }
  return parsed as Record<string, unknown>
}

function buildEpisodeProviderPayloadDefaults(
  item: EpisodeDraft,
  index: number,
): EpisodeProviderPayloadDefaults {
  return {
    video: parseProviderPayloadDefaultsText(item.video_payload_defaults_text, `第${index + 1}集视频`),
    tts: parseProviderPayloadDefaultsText(item.tts_payload_defaults_text, `第${index + 1}集语音`),
    lipsync: parseProviderPayloadDefaultsText(item.lipsync_payload_defaults_text, `第${index + 1}集口型同步`),
  }
}

function normalizeEpisodes(items: Array<Partial<EpisodeDraft>>): EpisodeDraft[] {
  const normalized = items
    .map((item, index) => ({
      id: typeof item.id === 'string' ? item.id : undefined,
      title: (item.title || `第${index + 1}集`).trim(),
      summary: (item.summary || '').trim() || null,
      script_text: (item.script_text || '').trim(),
      video_provider_key: normalizeProviderKey(item.video_provider_key),
      tts_provider_key: normalizeProviderKey(item.tts_provider_key),
      lipsync_provider_key: normalizeProviderKey(item.lipsync_provider_key),
      video_payload_defaults_text: typeof item.video_payload_defaults_text === 'string' ? item.video_payload_defaults_text : '',
      tts_payload_defaults_text: typeof item.tts_payload_defaults_text === 'string' ? item.tts_payload_defaults_text : '',
      lipsync_payload_defaults_text: typeof item.lipsync_payload_defaults_text === 'string' ? item.lipsync_payload_defaults_text : '',
      skipped_checks: normalizeSkippedChecks(item.skipped_checks),
      order: index,
      panel_count: Number.isFinite(item.panel_count) ? item.panel_count : 0,
      workflow_summary: item.workflow_summary ?? null,
    }))
    .filter((item) => Boolean(item.title) || Boolean(item.script_text))
  return normalized.map((item, index) => ({
    ...item,
    title: item.title || `第${index + 1}集`,
    order: index,
  }))
}

function toEpisodeDraft(item: Episode, fallbackOrder: number): EpisodeDraft {
  return {
    id: item.id,
    title: (item.title || `第${fallbackOrder + 1}集`).trim(),
    summary: (item.summary || '').trim() || null,
    script_text: (item.script_text || '').trim(),
    video_provider_key: item.video_provider_key ?? null,
    tts_provider_key: item.tts_provider_key ?? null,
    lipsync_provider_key: item.lipsync_provider_key ?? null,
    video_payload_defaults_text: formatProviderPayloadDefaultsText(item.provider_payload_defaults.video),
    tts_payload_defaults_text: formatProviderPayloadDefaultsText(item.provider_payload_defaults.tts),
    lipsync_payload_defaults_text: formatProviderPayloadDefaultsText(item.provider_payload_defaults.lipsync),
    skipped_checks: normalizeSkippedChecks(item.skipped_checks),
    order: Number.isFinite(item.episode_order) ? item.episode_order : fallbackOrder,
    panel_count: Number.isFinite(item.panel_count) ? item.panel_count : 0,
    workflow_summary: item.workflow_summary ?? null,
  }
}

function buildSingleEpisode(raw: string): EpisodeDraft[] {
  const text = (raw || '').trim()
  return [{
    title: '第1集',
    summary: text ? text.slice(0, 80) : null,
    script_text: text,
    video_provider_key: null,
    tts_provider_key: null,
    lipsync_provider_key: null,
    video_payload_defaults_text: '',
    tts_payload_defaults_text: '',
    lipsync_payload_defaults_text: '',
    skipped_checks: [],
    order: 0,
    panel_count: 0,
    workflow_summary: null,
  }]
}

function mergeEpisodesToScript(episodes: EpisodeDraft[]): string {
  const blocks = episodes
    .map((item, index) => {
      const title = (item.title || '').trim() || `第${index + 1}集`
      const body = (item.script_text || '').trim()
      if (!body) return ''
      const heading = title.startsWith('第') ? title : `第${index + 1}集 ${title}`
      return `${heading}\n${body}`
    })
    .filter(Boolean)
  return blocks.join('\n\n').trim()
}

function emptyWorkflowDefaults(): WorkflowDefaults {
  return {
    video_provider_key: null,
    tts_provider_key: null,
    lipsync_provider_key: null,
    provider_payload_defaults: {
      video: {},
      tts: {},
      lipsync: {},
    },
  }
}

function buildWorkflowDefaultsFromTexts(
  defaults: {
    video_provider_key: string | null
    tts_provider_key: string | null
    lipsync_provider_key: string | null
    video_payload_defaults_text: string
    tts_payload_defaults_text: string
    lipsync_payload_defaults_text: string
  },
): WorkflowDefaults {
  return {
    video_provider_key: defaults.video_provider_key,
    tts_provider_key: defaults.tts_provider_key,
    lipsync_provider_key: defaults.lipsync_provider_key,
    provider_payload_defaults: {
      video: parseProviderPayloadDefaultsText(defaults.video_payload_defaults_text, '项目默认视频'),
      tts: parseProviderPayloadDefaultsText(defaults.tts_payload_defaults_text, '项目默认语音'),
      lipsync: parseProviderPayloadDefaultsText(defaults.lipsync_payload_defaults_text, '项目默认口型同步'),
    },
  }
}

function buildWorkspaceEpisodesFromProjectEpisodes(projectEpisodes: Episode[]): EpisodeDraft[] {
  return normalizeEpisodes(
    projectEpisodes
      .slice()
      .sort((a, b) => a.episode_order - b.episode_order)
      .map((item, index) => toEpisodeDraft(item, index)),
  )
}

export default function ScriptInput() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const {
    workspace,
    loading: workspaceLoading,
    replaceWorkspace,
  } = useProjectWorkspace(id, '加载项目失败')
  const [saving, setSaving] = useState(false)
  const [episodes, setEpisodes] = useState<EpisodeDraft[]>(buildSingleEpisode(''))
  const [activeEpisodeIndex, setActiveEpisodeIndex] = useState(0)
  const [episodeEditorOpen, setEpisodeEditorOpen] = useState(false)
  const [hydratingEpisodes, setHydratingEpisodes] = useState(false)
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [importRawContent, setImportRawContent] = useState('')
  const [splitting, setSplitting] = useState(false)
  const [scriptDirty, setScriptDirty] = useState(false)
  const [providerLoading, setProviderLoading] = useState(false)
  const [providerConfigs, setProviderConfigs] = useState<ProviderConfig[]>([])
  const [defaultVideoProviderKey, setDefaultVideoProviderKey] = useState<string | null>(null)
  const [defaultTtsProviderKey, setDefaultTtsProviderKey] = useState<string | null>(null)
  const [defaultLipsyncProviderKey, setDefaultLipsyncProviderKey] = useState<string | null>(null)
  const [defaultVideoPayloadDefaultsText, setDefaultVideoPayloadDefaultsText] = useState('')
  const [defaultTtsPayloadDefaultsText, setDefaultTtsPayloadDefaultsText] = useState('')
  const [defaultLipsyncPayloadDefaultsText, setDefaultLipsyncPayloadDefaultsText] = useState('')
  const { message } = AntdApp.useApp()
  const currentProject = workspace?.project ?? null

  useUnsavedChanges(scriptDirty)

  useEffect(() => {
    setProviderLoading(true)
    listProviderConfigs()
      .then((rows) => setProviderConfigs(rows))
      .catch((error) => {
        message.error(getApiErrorMessage(error, '加载 Provider 配置失败'))
      })
      .finally(() => setProviderLoading(false))
  }, [message])

  useEffect(() => {
    if (!currentProject || scriptDirty) return
    const defaults = currentProject.workflow_defaults ?? emptyWorkflowDefaults()
    setDefaultVideoProviderKey(defaults.video_provider_key ?? null)
    setDefaultTtsProviderKey(defaults.tts_provider_key ?? null)
    setDefaultLipsyncProviderKey(defaults.lipsync_provider_key ?? null)
    setDefaultVideoPayloadDefaultsText(formatProviderPayloadDefaultsText(defaults.provider_payload_defaults.video))
    setDefaultTtsPayloadDefaultsText(formatProviderPayloadDefaultsText(defaults.provider_payload_defaults.tts))
    setDefaultLipsyncPayloadDefaultsText(formatProviderPayloadDefaultsText(defaults.provider_payload_defaults.lipsync))
  }, [currentProject, scriptDirty])

  const applyDefaultsToEpisodeDraft = useCallback((draft: EpisodeDraft): EpisodeDraft => ({
    ...draft,
    video_provider_key: draft.video_provider_key ?? defaultVideoProviderKey,
    tts_provider_key: draft.tts_provider_key ?? defaultTtsProviderKey,
    lipsync_provider_key: draft.lipsync_provider_key ?? defaultLipsyncProviderKey,
    video_payload_defaults_text: draft.video_payload_defaults_text || defaultVideoPayloadDefaultsText,
    tts_payload_defaults_text: draft.tts_payload_defaults_text || defaultTtsPayloadDefaultsText,
    lipsync_payload_defaults_text: draft.lipsync_payload_defaults_text || defaultLipsyncPayloadDefaultsText,
  }), [
    defaultLipsyncPayloadDefaultsText,
    defaultLipsyncProviderKey,
    defaultTtsPayloadDefaultsText,
    defaultTtsProviderKey,
    defaultVideoPayloadDefaultsText,
    defaultVideoProviderKey,
  ])

  const setEpisodesWithActive = useCallback((
    nextEpisodes: EpisodeDraft[],
    nextActiveIndex = 0,
    options: { markDirty?: boolean } = {},
  ) => {
    const { markDirty = true } = options
    const normalized = normalizeEpisodes(nextEpisodes).map(applyDefaultsToEpisodeDraft)
    const ensured = normalized.length > 0 ? normalized : buildSingleEpisode('')
    setEpisodes(ensured)
    setActiveEpisodeIndex(Math.max(0, Math.min(nextActiveIndex, ensured.length - 1)))
    if (markDirty) {
      setScriptDirty(true)
    }
  }, [applyDefaultsToEpisodeDraft])

  const updateActiveEpisode = useCallback((updater: (episode: EpisodeDraft) => EpisodeDraft) => {
    setEpisodes((prev) => prev.map((episode, index) => (
      index === activeEpisodeIndex ? updater(episode) : episode
    )))
    setScriptDirty(true)
  }, [activeEpisodeIndex])

  useEffect(() => {
    if (!id || !currentProject) return
    // 用户正在编辑时，不用远端数据覆盖本地草稿。
    if (scriptDirty) return

    const rawScript = (currentProject.script_text || '').trim()
    const fallback = buildSingleEpisode(rawScript)
    const persistedEpisodes = workspace?.episodes ?? []

    if (!rawScript) {
      setEpisodesWithActive(buildSingleEpisode(''), 0, { markDirty: false })
      return
    }

    if (persistedEpisodes.length > 0) {
      setEpisodesWithActive(buildWorkspaceEpisodesFromProjectEpisodes(persistedEpisodes), 0, { markDirty: false })
      return
    }

    let cancelled = false
    const hydrate = async () => {
      if (rawScript.length < 100) {
        if (!cancelled) {
          setEpisodesWithActive(fallback, 0, { markDirty: false })
        }
        return
      }

      setHydratingEpisodes(true)
      try {
        const result = await splitByMarkers(id, rawScript)
        if (cancelled) return
        const nextEpisodes = normalizeEpisodes(result.episodes || [])
        if (nextEpisodes.length > 0) {
          setEpisodesWithActive(nextEpisodes, 0, { markDirty: false })
        } else {
          setEpisodesWithActive(fallback, 0, { markDirty: false })
        }
      } catch {
        if (!cancelled) {
          setEpisodesWithActive(fallback, 0, { markDirty: false })
        }
      } finally {
        if (!cancelled) {
          setHydratingEpisodes(false)
        }
      }
    }

    void hydrate()
    return () => {
      cancelled = true
    }
  }, [currentProject, id, scriptDirty, setEpisodesWithActive, workspace?.episodes])

  const activeEpisode = useMemo(
    () => episodes[activeEpisodeIndex] ?? episodes[0],
    [episodes, activeEpisodeIndex],
  )

  useEffect(() => {
    const targetEpisodeId = (searchParams.get('episode') || '').trim()
    const shouldOpenEditor = searchParams.get('mode') === 'edit'
    if (!targetEpisodeId) return
    const index = episodes.findIndex((item) => item.id === targetEpisodeId)
    if (index < 0) return
    setActiveEpisodeIndex(index)
    if (shouldOpenEditor) {
      setEpisodeEditorOpen(true)
    }
  }, [episodes, searchParams])

  const videoProviders = useMemo(
    () => providerConfigs.filter((item) => item.provider_type === 'video' && item.enabled),
    [providerConfigs],
  )
  const ttsProviders = useMemo(
    () => providerConfigs.filter((item) => item.provider_type === 'tts' && item.enabled),
    [providerConfigs],
  )
  const lipsyncProviders = useMemo(
    () => providerConfigs.filter((item) => item.provider_type === 'lipsync' && item.enabled),
    [providerConfigs],
  )

  const activeVideoProvider = useMemo(
    () => (activeEpisode?.video_provider_key
      ? videoProviders.find((item) => item.provider_key === activeEpisode.video_provider_key) ?? null
      : null),
    [activeEpisode?.video_provider_key, videoProviders],
  )

  const activeAllowedLengths = useMemo(
    () => extractAllowedVideoLengths(activeVideoProvider?.request_template),
    [activeVideoProvider],
  )

  const applyDefaultsToIncompleteEpisodes = useCallback(() => {
    setEpisodesWithActive(episodes.map((item) => applyDefaultsToEpisodeDraft(item)), activeEpisodeIndex)
  }, [activeEpisodeIndex, applyDefaultsToEpisodeDraft, episodes, setEpisodesWithActive])

  const applyWorkspaceSnapshot = useCallback((nextWorkspace: NonNullable<typeof workspace>, nextActiveIndex = 0) => {
    replaceWorkspace(nextWorkspace)
    const defaults = nextWorkspace.project.workflow_defaults ?? emptyWorkflowDefaults()
    setDefaultVideoProviderKey(defaults.video_provider_key ?? null)
    setDefaultTtsProviderKey(defaults.tts_provider_key ?? null)
    setDefaultLipsyncProviderKey(defaults.lipsync_provider_key ?? null)
    setDefaultVideoPayloadDefaultsText(formatProviderPayloadDefaultsText(defaults.provider_payload_defaults.video))
    setDefaultTtsPayloadDefaultsText(formatProviderPayloadDefaultsText(defaults.provider_payload_defaults.tts))
    setDefaultLipsyncPayloadDefaultsText(formatProviderPayloadDefaultsText(defaults.provider_payload_defaults.lipsync))
    const nextEpisodes = nextWorkspace.episodes.length > 0
      ? buildWorkspaceEpisodesFromProjectEpisodes(nextWorkspace.episodes)
      : buildSingleEpisode(nextWorkspace.project.script_text || '')
    setEpisodesWithActive(nextEpisodes, nextActiveIndex, { markDirty: false })
    setScriptDirty(false)
  }, [replaceWorkspace, setEpisodesWithActive])

  const persistProjectEpisodes = useCallback(async (options: {
    nextActiveIndex?: number
  } = {}): Promise<{ episodes: EpisodeDraft[] } | null> => {
    if (!id || !currentProject) return null
    const mergedScript = mergeEpisodesToScript(episodes)
    if (!mergedScript) {
      message.warning('至少需要一个包含正文的分集')
      return null
    }

    const workflowDefaults = buildWorkflowDefaultsFromTexts({
      video_provider_key: defaultVideoProviderKey,
      tts_provider_key: defaultTtsProviderKey,
      lipsync_provider_key: defaultLipsyncProviderKey,
      video_payload_defaults_text: defaultVideoPayloadDefaultsText,
      tts_payload_defaults_text: defaultTtsPayloadDefaultsText,
      lipsync_payload_defaults_text: defaultLipsyncPayloadDefaultsText,
    })
    const normalizedEpisodes = normalizeEpisodes(episodes)
    const nextWorkspace = await updateProjectScriptWorkspace(id, {
      script_text: mergedScript,
      workflow_defaults: workflowDefaults,
      episodes: normalizedEpisodes.map((item, index) => ({
        id: item.id,
        title: (item.title || '').trim() || `第${index + 1}集`,
        summary: item.summary,
        script_text: item.script_text,
        video_provider_key: item.video_provider_key,
        tts_provider_key: item.tts_provider_key,
        lipsync_provider_key: item.lipsync_provider_key,
        provider_payload_defaults: buildEpisodeProviderPayloadDefaults(item, index),
        skipped_checks: item.skipped_checks,
      })),
    })
    applyWorkspaceSnapshot(nextWorkspace, options.nextActiveIndex ?? activeEpisodeIndex)
    return {
      episodes: nextWorkspace.episodes.length > 0
        ? buildWorkspaceEpisodesFromProjectEpisodes(nextWorkspace.episodes)
        : buildSingleEpisode(nextWorkspace.project.script_text || ''),
    }
  }, [
    activeEpisodeIndex,
    applyWorkspaceSnapshot,
    defaultLipsyncPayloadDefaultsText,
    defaultLipsyncProviderKey,
    defaultTtsPayloadDefaultsText,
    defaultTtsProviderKey,
    defaultVideoPayloadDefaultsText,
    defaultVideoProviderKey,
    episodes,
    currentProject,
    id,
    message,
  ])

  const handleSplitAndFill = async (mode: 'marker' | 'llm' | 'single') => {
    if (!id) return
    const raw = importRawContent.trim()
    if (!raw) {
      message.warning('请先输入原始文案')
      return
    }

    if (mode === 'single') {
      setEpisodesWithActive(buildSingleEpisode(raw))
      setImportRawContent('')
      message.success('已按单集导入到编辑区')
      setImportModalOpen(false)
      return
    }

    if (raw.length < 100) {
      message.warning('切分模式要求文案至少 100 字；不切分请使用“直接导入为单集”')
      return
    }

    setSplitting(true)
    try {
      const result = mode === 'llm'
        ? await splitByLlm(id, raw)
        : await splitByMarkers(id, raw)
      const importedEpisodes = normalizeEpisodes(result.episodes || [])
      const nextEpisodes = importedEpisodes.length > 0 ? importedEpisodes : buildSingleEpisode(raw)
      setEpisodesWithActive(nextEpisodes)
      setImportRawContent('')
      message.success(`已导入到分集管理台，共 ${nextEpisodes.length} 集`)
      setImportModalOpen(false)
    } catch (error) {
      message.error(getApiErrorMessage(error, mode === 'llm' ? 'AI 切分失败' : '标识符切分失败'))
    } finally {
      setSplitting(false)
    }
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      const result = await persistProjectEpisodes()
      if (!result) return
      message.success('剧本与分集已保存')
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const handleGoToAssetBinding = async (targetIndex: number) => {
    if (!id) return

    try {
      setSaving(true)
      const result = await persistProjectEpisodes({ nextActiveIndex: targetIndex })
      if (!result) return
      const safeIndex = Math.max(0, Math.min(targetIndex, result.episodes.length - 1))
      const targetEpisode = result.episodes[safeIndex]
      navigate(buildWorkflowStepPath(id, 'assets', targetEpisode?.id))
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存分集并进入资产绑定失败'))
    } finally {
      setSaving(false)
    }
  }

  const getEpisodeCompletion = (episode: EpisodeDraft): { label: string; className: string; detail: string } => {
    if (episode.workflow_summary) {
      const summary = episode.workflow_summary
      const hasBlockers = summary.blockers.length > 0
      const skippedAssetCheck = summary.skipped_checks.includes('asset_binding_ready')
      const stepLabel = getWorkflowStepLabel(summary.current_step)
      const detail = skippedAssetCheck
        ? '已跳过资产绑定检查'
        : summary.blockers[0] || `下一步：${stepLabel}`
      if (summary.completion_percent >= 85 && !hasBlockers) {
        return {
          label: `${stepLabel} ${summary.completion_percent}%`,
          className: 'np-status-tag np-status-completed',
          detail,
        }
      }
      return {
        label: `${stepLabel} ${summary.completion_percent}%`,
        className: hasBlockers ? 'np-status-tag np-status-failed' : 'np-status-tag',
        detail,
      }
    }

    const charCount = (episode.script_text || '').trim().length
    if (charCount <= 0) {
      return { label: '待填充', className: 'np-status-tag is-unbound', detail: '请先补充分集正文' }
    }
    if (Number(episode.panel_count || 0) > 0) {
      return { label: '分镜已生成', className: 'np-status-tag np-status-completed', detail: '可进入资产绑定继续推进' }
    }
    if (charCount < 80) {
      return { label: '编写中', className: 'np-status-tag', detail: '正文较短，建议继续完善' }
    }
    return { label: '已完成', className: 'np-status-tag np-status-completed', detail: '可进入资产绑定继续推进' }
  }

  if (workspaceLoading && !currentProject) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  if (!id || !currentProject) {
    return (
      <section className="np-page np-script-page">
        <PageHeader
          kicker="剧本工作台"
          title="剧本分集工作台"
          subtitle="项目不存在或工作台数据加载失败。"
          onBack={() => navigate('/projects')}
          backLabel="返回项目列表"
          navigation={<WorkflowSteps />}
        />
        <div className="np-page-scroll np-script-workspace">
          <Card className="np-panel-card">
            <Empty description="未找到项目工作台数据" />
          </Card>
        </div>
      </section>
    )
  }

  return (
    <section className="np-page np-script-page">
      <PageHeader
        kicker="剧本工作台"
        title={`${currentProject.name} · 剧本分集工作台`}
        subtitle="先配置项目默认 Provider，再管理分集卡片并决定每一集的下一步。"
        onBack={() => navigate(`/projects/${id}`)}
        backLabel="返回项目总览"
        navigation={<WorkflowSteps />}
        actions={(
          <Space>
            <Button icon={<RobotOutlined />} onClick={() => setImportModalOpen(true)}>
              导入并切分
            </Button>
            <Button icon={<SaveOutlined />} onClick={handleSave} loading={saving}>
              {saving ? '保存中...' : '保存全部'}
            </Button>
          </Space>
        )}
      />

      {id ? <ProjectSectionNav projectId={id} /> : null}

      <div className="np-page-scroll np-script-workspace">
        <Card
          size="small"
          className="np-panel-card"
          title="项目默认配置"
          extra={(
            <Button size="small" onClick={applyDefaultsToIncompleteEpisodes}>
              应用到未单独配置分集
            </Button>
          )}
        >
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Alert
              type="info"
              showIcon
              message="项目默认配置只会作为新分集和未单独配置分集的初始值"
              description="后续生成仍以分集自身配置为准。保存后会写回项目级工作台。"
            />
            <div className="np-workbench-default-grid">
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Paragraph style={{ margin: 0 }} type="secondary">默认视频 Provider</Paragraph>
                <Select
                  showSearch
                  allowClear
                  placeholder="选择项目默认视频 Provider"
                  loading={providerLoading}
                  optionFilterProp="label"
                  value={defaultVideoProviderKey ?? undefined}
                  options={videoProviders.map((item) => ({
                    label: `${item.name} (${item.provider_key})`,
                    value: item.provider_key,
                  }))}
                  onChange={(value) => {
                    setDefaultVideoProviderKey(value ?? null)
                    setScriptDirty(true)
                  }}
                />
              </Space>
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Paragraph style={{ margin: 0 }} type="secondary">默认语音 Provider</Paragraph>
                <Select
                  showSearch
                  allowClear
                  placeholder="选择项目默认语音 Provider"
                  loading={providerLoading}
                  optionFilterProp="label"
                  value={defaultTtsProviderKey ?? undefined}
                  options={ttsProviders.map((item) => ({
                    label: `${item.name} (${item.provider_key})`,
                    value: item.provider_key,
                  }))}
                  onChange={(value) => {
                    setDefaultTtsProviderKey(value ?? null)
                    setScriptDirty(true)
                  }}
                />
              </Space>
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Paragraph style={{ margin: 0 }} type="secondary">默认口型 Provider</Paragraph>
                <Select
                  showSearch
                  allowClear
                  placeholder="选择项目默认口型 Provider"
                  loading={providerLoading}
                  optionFilterProp="label"
                  value={defaultLipsyncProviderKey ?? undefined}
                  options={lipsyncProviders.map((item) => ({
                    label: `${item.name} (${item.provider_key})`,
                    value: item.provider_key,
                  }))}
                  onChange={(value) => {
                    setDefaultLipsyncProviderKey(value ?? null)
                    setScriptDirty(true)
                  }}
                />
              </Space>
            </div>
            <div className="np-workbench-default-grid">
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Paragraph style={{ margin: 0 }} type="secondary">视频默认参数（JSON）</Paragraph>
                <TextArea
                  rows={4}
                  value={defaultVideoPayloadDefaultsText}
                  onChange={(event) => {
                    setDefaultVideoPayloadDefaultsText(event.target.value)
                    setScriptDirty(true)
                  }}
                  placeholder='例如：{"seed": 42}'
                />
              </Space>
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Paragraph style={{ margin: 0 }} type="secondary">语音默认参数（JSON）</Paragraph>
                <TextArea
                  rows={4}
                  value={defaultTtsPayloadDefaultsText}
                  onChange={(event) => {
                    setDefaultTtsPayloadDefaultsText(event.target.value)
                    setScriptDirty(true)
                  }}
                  placeholder='例如：{"format": "mp3"}'
                />
              </Space>
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Paragraph style={{ margin: 0 }} type="secondary">口型默认参数（JSON）</Paragraph>
                <TextArea
                  rows={4}
                  value={defaultLipsyncPayloadDefaultsText}
                  onChange={(event) => {
                    setDefaultLipsyncPayloadDefaultsText(event.target.value)
                    setScriptDirty(true)
                  }}
                  placeholder='例如：{"fps": 25}'
                />
              </Space>
            </div>
          </Space>
        </Card>

        <Card
          size="small"
          className="np-panel-card np-script-episode-grid-card"
          title={`分集卡片（${episodes.length}）`}
          extra={(
            <Button
              size="small"
              icon={<PlusOutlined />}
              onClick={() => {
                const nextEpisodes = [
                  ...episodes,
                  {
                    title: `第${episodes.length + 1}集`,
                    summary: null,
                    script_text: '',
                    video_provider_key: null,
                    tts_provider_key: null,
                    lipsync_provider_key: null,
                    video_payload_defaults_text: '',
                    tts_payload_defaults_text: '',
                    lipsync_payload_defaults_text: '',
                    skipped_checks: [],
                    order: episodes.length,
                    panel_count: 0,
                    workflow_summary: null,
                  },
                ]
                setEpisodesWithActive(nextEpisodes, nextEpisodes.length - 1)
                setEpisodeEditorOpen(true)
              }}
            >
              新增分集
            </Button>
          )}
        >
          {episodes.length <= 0 ? (
            <Empty description="暂无分集，请先导入并切分剧本" />
          ) : (
            <div className="np-script-episode-grid">
              {episodes.map((item, index) => {
                const completion = getEpisodeCompletion(item)
                return (
                  <Card
                    key={`${item.id ?? 'draft'}-${index}`}
                    size="small"
                    className="np-panel-card np-script-episode-status-card np-script-episode-entry-card"
                    title={item.title || `第${index + 1}集`}
                    hoverable
                  >
                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                      <Space size={8} wrap>
                        <Tag className={completion.className}>{completion.label}</Tag>
                        {item.panel_count && item.panel_count > 0 ? (
                          <Tag className="np-status-tag">已生成 {item.panel_count} 个分镜</Tag>
                        ) : null}
                        {item.video_provider_key ? <Tag className="np-status-tag">视频 Provider 已配置</Tag> : null}
                        {item.tts_provider_key ? <Tag className="np-status-tag">语音 Provider 已配置</Tag> : null}
                        {item.lipsync_provider_key ? <Tag className="np-status-tag">口型 Provider 已配置</Tag> : null}
                      </Space>
                      <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
                        <Paragraph style={{ margin: 0 }} type="secondary">
                          {completion.detail}
                        </Paragraph>
                        <Space size={4}>
                          <Button
                            size="small"
                            type="default"
                            icon={<ArrowRightOutlined />}
                            onClick={(event) => {
                              event.stopPropagation()
                              if (saving) return
                              void handleGoToAssetBinding(index)
                            }}
                          >
                            继续流程
                          </Button>
                          <Button
                            size="small"
                            type="text"
                            icon={<EditOutlined />}
                            onClick={(event) => {
                              event.stopPropagation()
                              setActiveEpisodeIndex(index)
                              setEpisodeEditorOpen(true)
                            }}
                          >
                            编辑本集
                          </Button>
                        </Space>
                      </Space>
                    </Space>
                  </Card>
                )
              })}
            </div>
          )}
        </Card>
      </div>

      <Drawer
        title={activeEpisode ? `编辑分集 · ${activeEpisode.title || `第${activeEpisodeIndex + 1}集`}` : '编辑分集'}
        open={episodeEditorOpen}
        onClose={() => setEpisodeEditorOpen(false)}
        placement="right"
        width={680}
        closable
        maskClosable
        destroyOnHidden
        extra={(
          <Button type="primary" onClick={() => setEpisodeEditorOpen(false)}>
            完成
          </Button>
        )}
        footer={(
          <Space>
            <Button
              danger
              icon={<DeleteOutlined />}
              disabled={episodes.length <= 1 || !activeEpisode}
              onClick={() => {
                if (!activeEpisode || episodes.length <= 1) return
                const nextEpisodes = episodes
                  .filter((_, idx) => idx !== activeEpisodeIndex)
                  .map((ep, idx) => ({ ...ep, order: idx, title: ep.title || `第${idx + 1}集` }))
                setEpisodesWithActive(nextEpisodes, Math.max(0, activeEpisodeIndex - 1))
                if (nextEpisodes.length <= 0) {
                  setEpisodeEditorOpen(false)
                }
              }}
            >
              删除本集
            </Button>
          </Space>
        )}
      >
        {activeEpisode ? (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            {activeEpisode.workflow_summary ? (
              <Card size="small" className="np-panel-card">
                <Space size={8} wrap>
                    <Tag className="np-status-tag">
                    当前步骤：{getWorkflowStepLabel(activeEpisode.workflow_summary.current_step)}
                  </Tag>
                  <Tag className="np-status-tag">
                    完成度：{activeEpisode.workflow_summary.completion_percent}%
                  </Tag>
                  {activeEpisode.workflow_summary.skipped_checks.length > 0 ? (
                    <Tag className="np-status-tag">
                      已跳过：{activeEpisode.workflow_summary.skipped_checks.join(' / ')}
                    </Tag>
                  ) : null}
                </Space>
                <Paragraph style={{ marginTop: 8, marginBottom: 0 }} type="secondary">
                  {activeEpisode.workflow_summary.blockers[0] || '当前分集已具备下一步所需的基础信息。'}
                </Paragraph>
              </Card>
            ) : null}
            <Input
              value={activeEpisode.title}
              placeholder="分集标题"
              aria-label="分集标题"
              onChange={(event) => {
                updateActiveEpisode((episode) => ({ ...episode, title: event.target.value }))
              }}
            />
            <Input
              value={activeEpisode.summary ?? ''}
              placeholder="分集摘要（可选）"
              aria-label="分集摘要"
              onChange={(event) => {
                updateActiveEpisode((episode) => ({ ...episode, summary: event.target.value || null }))
              }}
            />
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Paragraph style={{ margin: 0 }} type="secondary">
                视频 Provider（决定分镜时长离散可选值）
              </Paragraph>
              <Select
                showSearch
                allowClear
                placeholder="请选择视频 Provider"
                loading={providerLoading}
                optionFilterProp="label"
                value={activeEpisode.video_provider_key ?? undefined}
                options={videoProviders.map((item) => ({
                  label: `${item.name} (${item.provider_key})`,
                  value: item.provider_key,
                }))}
                onChange={(value) => {
                  updateActiveEpisode((episode) => ({ ...episode, video_provider_key: value ?? null }))
                }}
              />
              {activeEpisode.video_provider_key ? (
                activeAllowedLengths.length > 0 ? (
                  <Paragraph style={{ margin: 0 }} type="secondary">
                    可用时长：{activeAllowedLengths.join(' / ')} 秒
                  </Paragraph>
                ) : (
                  <Paragraph style={{ margin: 0 }} type="warning">
                    当前 Provider 未配置 _allowed_video_lengths，分镜生成会失败
                  </Paragraph>
                )
              ) : (
                <Paragraph style={{ margin: 0 }} type="secondary">
                  未设置：分镜生成将无法确定合法时长
                </Paragraph>
              )}
            </Space>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Paragraph style={{ margin: 0 }} type="secondary">
                语音 Provider
              </Paragraph>
              <Select
                showSearch
                allowClear
                placeholder="请选择语音 Provider"
                loading={providerLoading}
                optionFilterProp="label"
                value={activeEpisode.tts_provider_key ?? undefined}
                options={ttsProviders.map((item) => ({
                  label: `${item.name} (${item.provider_key})`,
                  value: item.provider_key,
                }))}
                onChange={(value) => {
                  updateActiveEpisode((episode) => ({ ...episode, tts_provider_key: value ?? null }))
                }}
              />
            </Space>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Paragraph style={{ margin: 0 }} type="secondary">
                口型同步 Provider
              </Paragraph>
              <Select
                showSearch
                allowClear
                placeholder="请选择口型同步 Provider"
                loading={providerLoading}
                optionFilterProp="label"
                value={activeEpisode.lipsync_provider_key ?? undefined}
                options={lipsyncProviders.map((item) => ({
                  label: `${item.name} (${item.provider_key})`,
                  value: item.provider_key,
                }))}
                onChange={(value) => {
                  updateActiveEpisode((episode) => ({ ...episode, lipsync_provider_key: value ?? null }))
                }}
              />
            </Space>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Paragraph style={{ margin: 0 }} type="secondary">
                视频默认参数（JSON，可留空）
              </Paragraph>
              <TextArea
                rows={4}
                value={activeEpisode.video_payload_defaults_text}
                onChange={(event) => {
                  updateActiveEpisode((episode) => ({ ...episode, video_payload_defaults_text: event.target.value }))
                }}
                placeholder='例如：{"seed": 42, "cfg": 7}'
              />
            </Space>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Paragraph style={{ margin: 0 }} type="secondary">
                语音默认参数（JSON，可留空）
              </Paragraph>
              <TextArea
                rows={4}
                value={activeEpisode.tts_payload_defaults_text}
                onChange={(event) => {
                  updateActiveEpisode((episode) => ({ ...episode, tts_payload_defaults_text: event.target.value }))
                }}
                placeholder='例如：{"format": "mp3"}'
              />
            </Space>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Paragraph style={{ margin: 0 }} type="secondary">
                口型同步默认参数（JSON，可留空）
              </Paragraph>
              <TextArea
                rows={4}
                value={activeEpisode.lipsync_payload_defaults_text}
                onChange={(event) => {
                  updateActiveEpisode((episode) => ({ ...episode, lipsync_payload_defaults_text: event.target.value }))
                }}
                placeholder='例如：{"fps": 25}'
              />
            </Space>
            <TextArea
              rows={14}
              className="np-script-episode-input"
              value={activeEpisode.script_text}
              onChange={(event) => {
                updateActiveEpisode((episode) => ({ ...episode, script_text: event.target.value }))
              }}
              placeholder="请输入当前分集正文..."
            />
          </Space>
        ) : (
          <Paragraph style={{ margin: 0 }}>暂无可编辑分集</Paragraph>
        )}
      </Drawer>

      <Modal
        title="导入并切分剧本"
        open={importModalOpen}
        onCancel={() => setImportModalOpen(false)}
        footer={(
          <Space>
            <Button onClick={() => setImportModalOpen(false)}>取消</Button>
            <Button onClick={() => void handleSplitAndFill('single')} loading={splitting}>
              直接导入为单集
            </Button>
            <Button icon={<ScissorOutlined />} onClick={() => void handleSplitAndFill('marker')} loading={splitting}>
              标识符切分
            </Button>
            <Button type="primary" icon={<RobotOutlined />} onClick={() => void handleSplitAndFill('llm')} loading={splitting}>
              AI 切分
            </Button>
          </Space>
        )}
      >
        <TextArea
          rows={12}
          value={importRawContent}
          onChange={(event) => setImportRawContent(event.target.value)}
          placeholder="粘贴原始文案：可选择标识符切分、AI切分，或不切分直接按1集导入。"
        />
        {hydratingEpisodes && <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>正在根据已有剧本恢复分集结构...</Paragraph>}
      </Modal>
    </section>
  )
}
