import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Empty, Input, Space, App as AntdApp, Spin, Typography, Card, Modal, Tag, Drawer } from 'antd'
import {
  SaveOutlined,
  RobotOutlined,
  ScissorOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
} from '@ant-design/icons'
import { useProjectStore } from '../../stores/projectStore'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { getApiErrorMessage } from '../../utils/error'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { splitByLlm, splitByMarkers } from '../../api/imports'
import { createEpisode, deleteEpisode, listEpisodes, reorderEpisodes, updateEpisode } from '../../api/episodes'
import { buildWorkflowStepPath } from '../../utils/workflow'
import type { Episode } from '../../types/episode'

const { TextArea } = Input
const { Paragraph } = Typography

interface EpisodeDraft {
  id?: string
  title: string
  summary: string | null
  script_text: string
  order: number
  panel_count?: number
}

function normalizeEpisodes(items: Array<Partial<EpisodeDraft>>): EpisodeDraft[] {
  const normalized = items
    .map((item, index) => ({
      id: typeof item.id === 'string' ? item.id : undefined,
      title: (item.title || `第${index + 1}集`).trim(),
      summary: (item.summary || '').trim() || null,
      script_text: (item.script_text || '').trim(),
      order: index,
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
    order: Number.isFinite(item.episode_order) ? item.episode_order : fallbackOrder,
    panel_count: Number.isFinite(item.panel_count) ? item.panel_count : 0,
  }
}

function buildSingleEpisode(raw: string): EpisodeDraft[] {
  const text = (raw || '').trim()
  return [{
    title: '第1集',
    summary: text ? text.slice(0, 80) : null,
    script_text: text,
    order: 0,
    panel_count: 0,
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

export default function ScriptInput() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { currentProject, loading, fetchProject, updateProject } = useProjectStore()
  const [saving, setSaving] = useState(false)
  const [episodes, setEpisodes] = useState<EpisodeDraft[]>(buildSingleEpisode(''))
  const [activeEpisodeIndex, setActiveEpisodeIndex] = useState(0)
  const [episodeEditorOpen, setEpisodeEditorOpen] = useState(false)
  const [hydratingEpisodes, setHydratingEpisodes] = useState(false)
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [importRawContent, setImportRawContent] = useState('')
  const [splitting, setSplitting] = useState(false)
  const [scriptDirty, setScriptDirty] = useState(false)
  const { message } = AntdApp.useApp()

  useUnsavedChanges(scriptDirty)

  useEffect(() => {
    if (id) {
      fetchProject(id).catch((error) => {
        message.error(getApiErrorMessage(error, '加载项目失败'))
      })
    }
  }, [id, fetchProject, message])

  const setEpisodesWithActive = (
    nextEpisodes: EpisodeDraft[],
    nextActiveIndex = 0,
    options: { markDirty?: boolean } = {},
  ) => {
    const { markDirty = true } = options
    const normalized = normalizeEpisodes(nextEpisodes)
    const ensured = normalized.length > 0 ? normalized : buildSingleEpisode('')
    setEpisodes(ensured)
    setActiveEpisodeIndex(Math.max(0, Math.min(nextActiveIndex, ensured.length - 1)))
    if (markDirty) {
      setScriptDirty(true)
    }
  }

  useEffect(() => {
    if (!id || !currentProject) return
    // 用户正在编辑时，不用远端数据覆盖本地草稿。
    if (scriptDirty) return

    const rawScript = (currentProject.script_text || '').trim()
    const fallback = buildSingleEpisode(rawScript)

    if (!rawScript) {
      setEpisodesWithActive(buildSingleEpisode(''), 0, { markDirty: false })
      return
    }

    let cancelled = false
    const hydrate = async () => {
      try {
        const persisted = await listEpisodes(id)
        if (cancelled) return
        if (persisted.length > 0) {
          const nextEpisodes = normalizeEpisodes(
            persisted
              .sort((a, b) => a.episode_order - b.episode_order)
              .map((item, index) => toEpisodeDraft(item, index)),
          )
          setEpisodesWithActive(nextEpisodes, 0, { markDirty: false })
          return
        }
      } catch {
        // 分集读取失败时回退到剧本文本切分，不中断页面加载。
      }

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
  }, [id, currentProject, scriptDirty])

  const activeEpisode = useMemo(
    () => episodes[activeEpisodeIndex] ?? episodes[0],
    [episodes, activeEpisodeIndex],
  )

  const syncEpisodesWhenSafe = async (
    projectId: string,
    drafts: EpisodeDraft[],
    options: { force?: boolean } = {},
  ): Promise<EpisodeDraft[] | null> => {
    const force = Boolean(options.force)
    if (!force && (!currentProject || Number(currentProject.panel_count || 0) > 0)) {
      return null
    }
    const normalized = normalizeEpisodes(drafts)
    const existing = await listEpisodes(projectId)
    const existingMap = new Map(existing.map((item) => [item.id, item]))
    const keepIds: string[] = []

    for (const item of normalized) {
      const payload = {
        title: (item.title || '').trim() || `第${keepIds.length + 1}集`,
        summary: item.summary || undefined,
        script_text: item.script_text || undefined,
      }
      if (item.id && existingMap.has(item.id)) {
        const updated = await updateEpisode(item.id, payload)
        keepIds.push(updated.id)
      } else {
        const created = await createEpisode(projectId, payload)
        keepIds.push(created.id)
      }
    }

    const staleIds = existing
      .map((item) => item.id)
      .filter((episodeId) => !keepIds.includes(episodeId))
    for (const episodeId of staleIds) {
      await deleteEpisode(episodeId)
    }

    if (keepIds.length > 0) {
      await reorderEpisodes(projectId, keepIds)
    }

    const refreshed = await listEpisodes(projectId)
    return normalizeEpisodes(
      refreshed
        .sort((a, b) => a.episode_order - b.episode_order)
        .map((item, index) => toEpisodeDraft(item, index)),
    )
  }

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
    if (!id) return
    const mergedScript = mergeEpisodesToScript(episodes)
    if (!mergedScript) {
      message.warning('至少需要一个包含正文的分集')
      return
    }
    try {
      setSaving(true)
      await updateProject(id, { script_text: mergedScript })
      const persisted = await syncEpisodesWhenSafe(id, episodes)
      if (persisted && persisted.length > 0) {
        setEpisodesWithActive(persisted, activeEpisodeIndex, { markDirty: false })
        message.success('剧本与分集已保存')
      } else {
        message.success('剧本已保存')
      }
      setScriptDirty(false)
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const handleGoToAssetBinding = async (targetIndex: number) => {
    if (!id) return
    const mergedScript = mergeEpisodesToScript(episodes)
    if (!mergedScript) {
      message.warning('至少需要一个包含正文的分集')
      return
    }

    try {
      setSaving(true)
      await updateProject(id, { script_text: mergedScript })
      const persisted = await syncEpisodesWhenSafe(id, episodes, { force: true })
      const resolvedEpisodes = persisted && persisted.length > 0 ? persisted : normalizeEpisodes(episodes)
      if (persisted && persisted.length > 0) {
        setEpisodesWithActive(persisted, targetIndex, { markDirty: false })
      }
      setScriptDirty(false)
      const safeIndex = Math.max(0, Math.min(targetIndex, resolvedEpisodes.length - 1))
      const targetEpisode = resolvedEpisodes[safeIndex]
      navigate(buildWorkflowStepPath(id, 'assets', targetEpisode?.id))
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存分集并进入资产绑定失败'))
    } finally {
      setSaving(false)
    }
  }

  const getEpisodeCompletion = (episode: EpisodeDraft): { label: string; className: string } => {
    const charCount = (episode.script_text || '').trim().length
    if (charCount <= 0) {
      return { label: '待填充', className: 'np-status-tag is-unbound' }
    }
    if (Number(episode.panel_count || 0) > 0) {
      return { label: '分镜已生成', className: 'np-status-tag np-status-completed' }
    }
    if (charCount < 80) {
      return { label: '编写中', className: 'np-status-tag' }
    }
    return { label: '已完成', className: 'np-status-tag np-status-completed' }
  }

  if (loading || !currentProject) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <section className="np-page np-script-page">
      <PageHeader
        kicker="剧本工作台"
        title={`${currentProject.name} · 剧本编辑`}
        onBack={() => navigate('/projects')}
        backLabel="返回项目列表"
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

      <div className="np-page-scroll np-script-workspace">
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
                  { title: `第${episodes.length + 1}集`, summary: null, script_text: '', order: episodes.length, panel_count: 0 },
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
                    onClick={() => {
                      if (saving) return
                      void handleGoToAssetBinding(index)
                    }}
                  >
                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                      <Space size={8} wrap>
                        <Tag className={completion.className}>{completion.label}</Tag>
                        {item.panel_count && item.panel_count > 0 ? (
                          <Tag className="np-status-tag">已生成 {item.panel_count} 个分镜</Tag>
                        ) : null}
                      </Space>
                      <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
                        <Paragraph style={{ margin: 0 }} type="secondary">
                          点击卡片进入资产绑定
                        </Paragraph>
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
            <Input
              value={activeEpisode.title}
              placeholder="分集标题"
              aria-label="分集标题"
              onChange={(event) => {
                const next = episodes.map((ep, idx) => (
                  idx === activeEpisodeIndex ? { ...ep, title: event.target.value } : ep
                ))
                setEpisodes(next)
                setScriptDirty(true)
              }}
            />
            <Input
              value={activeEpisode.summary ?? ''}
              placeholder="分集摘要（可选）"
              aria-label="分集摘要"
              onChange={(event) => {
                const next = episodes.map((ep, idx) => (
                  idx === activeEpisodeIndex ? { ...ep, summary: event.target.value || null } : ep
                ))
                setEpisodes(next)
                setScriptDirty(true)
              }}
            />
            <TextArea
              rows={14}
              className="np-script-episode-input"
              value={activeEpisode.script_text}
              onChange={(event) => {
                const next = episodes.map((ep, idx) => (
                  idx === activeEpisodeIndex ? { ...ep, script_text: event.target.value } : ep
                ))
                setEpisodes(next)
                setScriptDirty(true)
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
