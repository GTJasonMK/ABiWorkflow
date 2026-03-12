import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Card, Empty, Space, Spin, Tag, Typography, App as AntdApp } from 'antd'
import {
  PlayCircleOutlined,
  ReloadOutlined,
  ScissorOutlined,
} from '@ant-design/icons'
import {
  listEpisodePanels,
  submitEpisodePanelsLipsyncBatch,
  submitEpisodePanelsVideoBatch,
  submitEpisodePanelsVoiceBatch,
} from '../../api/panels'
import { listEpisodes } from '../../api/episodes'
import type { Panel } from '../../types/panel'
import type { Episode } from '../../types/episode'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { getApiErrorMessage } from '../../utils/error'
import { buildWorkflowStepPath } from '../../utils/workflow'
import PanelGenerationCard from './PanelGenerationCard'

const { Paragraph, Text } = Typography

export default function VideoGeneration() {
  const { id: projectId, episodeId } = useParams<{ id: string; episodeId?: string }>()
  const navigate = useNavigate()
  const scopedEpisodeId = (episodeId || '').trim() || null
  const { message } = AntdApp.useApp()
  const [panels, setPanels] = useState<Panel[]>([])
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [loadingPanels, setLoadingPanels] = useState(false)
  const [submittingBatch, setSubmittingBatch] = useState<{ mode: 'video' | 'tts' | 'lipsync'; force: boolean } | null>(null)

  const selectedEpisode = useMemo(() => {
    if (!scopedEpisodeId) return null
    return episodes.find((episode) => episode.id === scopedEpisodeId) ?? null
  }, [episodes, scopedEpisodeId])

  const visiblePanels = panels

  const currentEpisodeTitle = selectedEpisode?.title ?? null

  const panelStats = useMemo(() => {
    const total = visiblePanels.length
    const completed = visiblePanels.filter((panel) => Boolean(panel.video_url || panel.lipsync_video_url)).length
    const processing = visiblePanels.filter((panel) => (
      [panel.video_status, panel.tts_status, panel.lipsync_status].some((item) => item === 'queued' || item === 'running')
    )).length
    const failed = visiblePanels.filter((panel) => (
      [panel.video_status, panel.tts_status, panel.lipsync_status].some((item) => item === 'failed')
    )).length
    return { total, completed, processing, failed }
  }, [visiblePanels])

  const canCompose = useMemo(
    () => visiblePanels.length > 0 && visiblePanels.every((panel) => panel.status === 'completed' && Boolean(panel.video_url || panel.lipsync_video_url)),
    [visiblePanels],
  )

  const canBatchVideo = useMemo(
    () => Boolean(selectedEpisode?.video_provider_key) && visiblePanels.some((panel) => Boolean(panel.visual_prompt || panel.script_text)),
    [selectedEpisode?.video_provider_key, visiblePanels],
  )
  const canBatchTts = useMemo(
    () => Boolean(selectedEpisode?.tts_provider_key) && visiblePanels.some((panel) => Boolean(panel.tts_text || panel.script_text)),
    [selectedEpisode?.tts_provider_key, visiblePanels],
  )
  const canBatchLipsync = useMemo(
    () => Boolean(selectedEpisode?.lipsync_provider_key) && visiblePanels.some((panel) => Boolean(panel.video_url && panel.tts_audio_url)),
    [selectedEpisode?.lipsync_provider_key, visiblePanels],
  )

  const fetchPanels = useCallback(async () => {
    if (!projectId || !scopedEpisodeId) return
    setLoadingPanels(true)
    try {
      const [rows, eps] = await Promise.all([
        listEpisodePanels(scopedEpisodeId),
        listEpisodes(projectId),
      ])
      setPanels(rows)
      setEpisodes(eps)
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载分镜失败'))
    } finally {
      setLoadingPanels(false)
    }
  }, [message, projectId, scopedEpisodeId])

  useEffect(() => {
    if (!projectId || !scopedEpisodeId) return
    void fetchPanels()
  }, [fetchPanels, projectId, scopedEpisodeId])

  const handleBatchSubmit = async (mode: 'video' | 'tts' | 'lipsync', force = false) => {
    if (!scopedEpisodeId) return
    setSubmittingBatch({ mode, force })
    try {
      const submitter = mode === 'video'
        ? submitEpisodePanelsVideoBatch
        : mode === 'tts'
          ? submitEpisodePanelsVoiceBatch
          : submitEpisodePanelsLipsyncBatch
      const result = await submitter(scopedEpisodeId, {
        payload: {},
        force,
      })
      const submitted = Number(result.submitted ?? 0)
      const skipped = Number(result.skipped ?? 0)
      const failed = Number(result.failed ?? 0)
      const total = Number(result.total ?? 0)
      const modeLabel = mode === 'video' ? '视频' : mode === 'tts' ? '语音' : '口型同步'
      message.success(`${modeLabel}批量提交完成：提交 ${submitted}/${total}，跳过 ${skipped}，失败 ${failed}`)
      await fetchPanels()
    } catch (error) {
      message.error(getApiErrorMessage(error, '批量提交失败'))
    } finally {
      setSubmittingBatch(null)
    }
  }

  if (loadingPanels) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  if (!projectId || !scopedEpisodeId) {
    return (
      <section className="np-page">
        <PageHeader
          kicker="生成流程"
          title="视频生成"
          subtitle="分集参数缺失，请返回分集列表重新进入。"
          onBack={() => {
            if (!projectId) return
            navigate(`/projects/${projectId}/script`)
          }}
          backLabel="返回剧本分集"
          navigation={<WorkflowSteps />}
        />
        <div className="np-page-scroll">
          <Card size="small" className="np-panel-card">
            <Empty description="分集参数缺失，请从分集列表重新进入视频生成。" />
          </Card>
        </div>
      </section>
    )
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="生成流程"
        title="视频生成"
        subtitle="以分镜为主线进行生成与逐镜复核（Provider 模式）。"
        onBack={() => {
          if (!projectId || !scopedEpisodeId) return
          navigate(buildWorkflowStepPath(projectId, 'storyboard', scopedEpisodeId))
        }}
        backLabel="返回上一步"
        navigation={<WorkflowSteps />}
        actions={(
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={submittingBatch?.mode === 'tts' && !submittingBatch.force}
              disabled={!canBatchTts}
              onClick={() => { void handleBatchSubmit('tts') }}
            >
              批量语音
            </Button>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={submittingBatch?.mode === 'video' && !submittingBatch.force}
              disabled={!canBatchVideo}
              onClick={() => { void handleBatchSubmit('video') }}
            >
              批量视频
            </Button>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={submittingBatch?.mode === 'lipsync' && !submittingBatch.force}
              disabled={!canBatchLipsync}
              onClick={() => { void handleBatchSubmit('lipsync') }}
            >
              批量口型
            </Button>
            <Button
              danger
              loading={submittingBatch?.mode === 'video' && submittingBatch.force}
              disabled={!canBatchVideo}
              onClick={() => { void handleBatchSubmit('video', true) }}
            >
              强制重提视频
            </Button>
            <Button
              icon={<ScissorOutlined />}
              disabled={!canCompose}
              onClick={() => {
                if (!projectId || !scopedEpisodeId) return
                navigate(buildWorkflowStepPath(projectId, 'preview', scopedEpisodeId))
              }}
            >
              去合成
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
        <Paragraph className="np-note" style={{ marginBottom: 12 }}>
          先完成“资产绑定与提示词复核”，再批量提交生成任务，可显著减少返工。
        </Paragraph>

        <Card size="small" className="np-panel-card" style={{ marginBottom: 12 }}>
          <Space size={12} wrap align="center">
            <Tag className="np-status-tag">单集模式</Tag>
            <Tag className="np-status-tag">{currentEpisodeTitle || '当前分集'}</Tag>
            <Tag className="np-status-tag">
              视频 Provider：{selectedEpisode?.video_provider_key || '未配置'}
            </Tag>
            <Tag className="np-status-tag">
              语音 Provider：{selectedEpisode?.tts_provider_key || '未配置'}
            </Tag>
            <Tag className="np-status-tag">
              口型 Provider：{selectedEpisode?.lipsync_provider_key || '未配置'}
            </Tag>
            <Tag className="np-status-tag">分镜总数：{panelStats.total}</Tag>
            <Tag className="np-status-tag np-status-generated">已完成：{panelStats.completed}</Tag>
            <Tag className="np-status-tag">处理中：{panelStats.processing}</Tag>
            <Tag className="np-status-tag np-status-failed">失败：{panelStats.failed}</Tag>
            <Text type="secondary">可在下方逐分镜复核并按需补提任务</Text>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => { void fetchPanels() }}
              loading={loadingPanels}
              aria-label="刷新分镜列表"
            >
              刷新
            </Button>
          </Space>
          <Paragraph style={{ marginTop: 8, marginBottom: 0 }} type="secondary">
            当前分集模式下，“批量提交 / 去合成”仅作用于该分集。
          </Paragraph>
          {selectedEpisode?.workflow_summary.blockers.length ? (
            <Paragraph style={{ marginTop: 8, marginBottom: 0 }} type="secondary">
              当前阻塞：{selectedEpisode.workflow_summary.blockers.join('、')}
            </Paragraph>
          ) : null}
        </Card>

        {visiblePanels.length > 0 ? (
          <PanelGenerationCard episode={selectedEpisode} panels={visiblePanels} onRefresh={fetchPanels} />
        ) : (
          <Text type="secondary">暂无分镜数据，可在"分镜编辑"中创建。</Text>
        )}
      </div>
    </section>
  )
}
