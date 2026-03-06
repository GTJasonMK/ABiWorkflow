import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Button, Card, Col, Empty, Row, Space, Spin, Tag, Typography, App as AntdApp } from 'antd'
import { DownloadOutlined, PlayCircleOutlined, StopOutlined } from '@ant-design/icons'
import { useWebSocket } from '../../hooks/useWebSocket'
import { startComposition, getDownloadUrl, getComposition, getLatestComposition } from '../../api/composition'
import { resolveAsyncResult } from '../../api/tasks'
import { abortProjectTask, getProject } from '../../api/projects'
import { listEpisodePanels } from '../../api/panels'
import { listEpisodes } from '../../api/episodes'
import VideoTrimEditor, { type TimelineSegment } from '../../components/VideoTrimEditor'
import ProgressBar from '../../components/ProgressBar'
import Timeline from './Timeline'
import OptionsPanel from './OptionsPanel'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { getApiErrorMessage } from '../../utils/error'
import { handleForceRecoverError } from '../../utils/forceRecover'
import { saveUrlWithPicker } from '../../utils/download'
import { buildWorkflowStepPath } from '../../utils/workflow'
import type { Panel } from '../../types/panel'
import type { Episode } from '../../types/episode'

const { Paragraph } = Typography

export default function CompositionPreview() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const episodeId = (searchParams.get('episodeId') || '').trim() || null
  const { messages, connected, clearMessages } = useWebSocket(projectId)
  const [loading, setLoading] = useState(false)
  const [panels, setPanels] = useState<Panel[]>([])
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [composing, setComposing] = useState(false)
  const [compositionId, setCompositionId] = useState<string | null>(null)
  const [compositionDuration, setCompositionDuration] = useState(0)
  const [mediaUrl, setMediaUrl] = useState<string | null>(null)
  const [staleWarning, setStaleWarning] = useState(false)
  const [projectUpdatedAt, setProjectUpdatedAt] = useState<string | null>(null)
  const { message, modal } = AntdApp.useApp()
  const composeLastMessage = useMemo(
    () => [...messages].reverse().find((item) => item.type.startsWith('compose_')) ?? null,
    [messages],
  )
  const selectedEpisode = useMemo(() => {
    if (!episodeId) return null
    return episodes.find((episode) => episode.id === episodeId) ?? null
  }, [episodeId, episodes])
  const contextEpisodeId = selectedEpisode?.id ?? null
  const visiblePanels = panels
  const canCompose = useMemo(
    () => visiblePanels.length > 0 && visiblePanels.every((panel) => panel.status === 'completed' && Boolean(panel.lipsync_video_url || panel.video_url)),
    [visiblePanels],
  )
  const currentEpisodeTitle = selectedEpisode?.title ?? null
  const timelineSegments = useMemo<TimelineSegment[]>(
    () => visiblePanels.map((panel) => ({
      id: panel.id,
      title: panel.title,
      duration_seconds: panel.duration_seconds,
    })),
    [visiblePanels],
  )
  const [options, setOptions] = useState<{
    transition_type: 'none' | 'crossfade' | 'fade_black'
    transition_duration: number
    include_subtitles: boolean
    include_tts: boolean
  }>({
    transition_type: 'crossfade',
    transition_duration: 0.5,
    include_subtitles: true,
    include_tts: true,
  })

  const fetchPanels = useCallback(async () => {
    if (!projectId || !episodeId) return
    setLoading(true)
    try {
      const [rows, episodeRows] = await Promise.all([
        listEpisodePanels(episodeId),
        listEpisodes(projectId),
      ])
      setPanels(rows)
      setEpisodes(episodeRows)
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载分镜失败'))
    } finally {
      setLoading(false)
    }
  }, [episodeId, message, projectId])

  const loadLatestEpisodeComposition = useCallback(async (
    targetProjectId: string,
    targetEpisodeId: string,
    projectUpdatedAtValue: string | null,
  ) => {
    try {
      const record = await getLatestComposition(targetProjectId, targetEpisodeId)
      if (!record) {
        setCompositionId(null)
        setCompositionDuration(0)
        setMediaUrl(null)
        setStaleWarning(false)
        return
      }
      setCompositionId(record.id)
      setCompositionDuration(Number(record.duration_seconds ?? 0))
      setMediaUrl(record.media_url ?? null)
      if (projectUpdatedAtValue && record.created_at && new Date(projectUpdatedAtValue) > new Date(record.created_at)) {
        setStaleWarning(true)
      } else {
        setStaleWarning(false)
      }
    } catch {
      setCompositionId(null)
      setCompositionDuration(0)
      setMediaUrl(null)
      setStaleWarning(false)
    }
  }, [])

  useEffect(() => {
    if (!projectId) return
    void fetchPanels()
    getProject(projectId).then((project) => {
      setProjectUpdatedAt(project.updated_at ?? null)
      setComposing(project.status === 'composing')
    }).catch(() => {
      setComposing(false)
    })
  }, [fetchPanels, projectId])

  useEffect(() => {
    if (!projectId || !contextEpisodeId) {
      setCompositionId(null)
      setCompositionDuration(0)
      setMediaUrl(null)
      setStaleWarning(false)
      return
    }
    void loadLatestEpisodeComposition(projectId, contextEpisodeId, projectUpdatedAt)
  }, [contextEpisodeId, loadLatestEpisodeComposition, projectId, projectUpdatedAt])

  const runCompose = async (forceRecover = false) => {
    if (!projectId || !contextEpisodeId) {
      message.warning('请先在剧本页选择分集后再执行合成')
      return
    }
    if (!canCompose) {
      message.warning('请先完成当前分集分镜生成，再进行合成')
      return
    }
    setComposing(true)
    clearMessages()
    try {
      const startResult = await startComposition(projectId, options, { forceRecover }, contextEpisodeId)
      const result = await resolveAsyncResult(
        startResult as unknown as Record<string, unknown>,
        { timeoutMs: 20 * 60 * 1000 },
      )
      const compositionId = String(result.composition_id ?? '')

      if (!compositionId) {
        throw new Error('未获取到合成结果ID')
      }

      setCompositionId(compositionId)
      // 加载合成记录的时长和媒体URL
      getComposition(compositionId).then((record) => {
        setCompositionDuration(Number(record.duration_seconds ?? 0))
        setMediaUrl(record.media_url ?? null)
      }).catch(() => {})
      message.success('视频合成完成')
      setStaleWarning(false)
    } catch (error) {
      handleForceRecoverError(error, forceRecover, modal, message, {
        retryFn: () => runCompose(true),
        errorFallback: '合成失败',
      })
    } finally {
      setComposing(false)
      // 无论成功或失败，都刷新分镜列表以同步后端最新状态
      await fetchPanels()
    }
  }

  const handleCompose = () => {
    void runCompose(false)
  }

  const handleDownloadComposition = async () => {
    if (!compositionId) return
    try {
      const result = await saveUrlWithPicker({
        url: getDownloadUrl(compositionId),
        title: '导出合成视频',
        defaultFileName: `composition-${compositionId.slice(0, 8)}.mp4`,
      })
      if (result.mode === 'desktop' && !result.canceled && result.filePath) {
        message.success(`已导出到：${result.filePath}`)
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, '导出视频失败'))
    }
  }

  const handleAbort = () => {
    if (!projectId) return
    modal.confirm({
      title: '确认取消合成',
      content: '将强制中止当前合成任务，项目状态恢复为可操作。正在进行的编码将被放弃。',
      okText: '确认取消',
      okButtonProps: { danger: true },
      cancelText: '继续等待',
      onOk: async () => {
        try {
          const result = await abortProjectTask(projectId)
          if (result.aborted) {
            message.success(result.message)
          } else {
            message.info(result.message)
          }
          setComposing(false)
        } catch (err) {
          message.error(getApiErrorMessage(err, '取消失败'))
        }
      },
    })
  }

  if (loading) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  if (!episodeId) {
    return (
      <section className="np-page">
        <PageHeader
          kicker="成片合成"
          title="合成预览"
          subtitle="当前流程仅支持单集操作，请先选择分集。"
          onBack={() => {
            if (!projectId) return
            navigate(`/projects/${projectId}/script`)
          }}
          backLabel="返回剧本分集"
          navigation={<WorkflowSteps episodeIdOverride={null} />}
        />
        <div className="np-page-scroll">
          <Card size="small" className="np-panel-card">
            <Empty description="缺少分集上下文，请从剧本页选择分集后进入本页面。" />
          </Card>
        </div>
      </section>
    )
  }

  if (!selectedEpisode) {
    return (
      <section className="np-page">
        <PageHeader
          kicker="成片合成"
          title="合成预览"
          subtitle="分集上下文无效，请返回剧本页重新选择分集。"
          onBack={() => {
            if (!projectId) return
            navigate(`/projects/${projectId}/script`)
          }}
          backLabel="返回剧本分集"
          navigation={<WorkflowSteps episodeIdOverride={null} />}
        />
        <div className="np-page-scroll">
          <Card size="small" className="np-panel-card">
            <Empty description="当前分集不存在或已删除，请从剧本页重新进入合成预览。" />
          </Card>
        </div>
      </section>
    )
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="成片合成"
        title="合成预览"
        subtitle="设置转场与字幕策略，生成最终成片并下载导出。"
        onBack={() => {
          if (!projectId) return
          navigate(buildWorkflowStepPath(projectId, 'generate', contextEpisodeId))
        }}
        backLabel="返回上一步"
        navigation={<WorkflowSteps episodeIdOverride={contextEpisodeId} />}
        actions={(
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleCompose}
              disabled={!canCompose || composing}
              loading={composing}
            >
              {composing ? '合成中...' : '开始合成'}
            </Button>
            {composing && (
              <Button
                icon={<StopOutlined />}
                onClick={handleAbort}
                danger
              >
                取消合成
              </Button>
            )}
            {compositionId && (
              <Button
                icon={<DownloadOutlined />}
                onClick={() => {
                  void handleDownloadComposition()
                }}
              >
                下载视频
              </Button>
            )}
          </Space>
        )}
      />

      <div className="np-page-scroll">
        {staleWarning && !composing && (
          <Alert
            type="warning"
            showIcon
            message="分镜或配置在上次合成后有变更，当前成片可能不是最新版本。"
            closable
            onClose={() => setStaleWarning(false)}
            style={{ marginBottom: 12 }}
          />
        )}

        <Paragraph className="np-note" style={{ marginBottom: 12 }}>
          推荐先使用默认转场完成首版，再针对节奏问题进行二次细调。
        </Paragraph>

        <Card size="small" className="np-panel-card" style={{ marginBottom: 12 }}>
          <Space size={12} wrap align="center">
            <Tag className="np-status-tag">单集模式</Tag>
            <Tag className="np-status-tag">{currentEpisodeTitle || '当前分集'}</Tag>
            <Tag className="np-status-tag">当前分集：{visiblePanels.length} 镜</Tag>
            <Tag className={`np-status-tag${canCompose ? ' np-status-generated' : ''}`}>
              当前分集可合成：{canCompose ? '是' : '否'}
            </Tag>
          </Space>
          <Paragraph style={{ marginTop: 8, marginBottom: 0 }} type="secondary">
            “开始合成”仅合成当前分集片段。
          </Paragraph>
        </Card>

        <Row gutter={16}>
          <Col xs={24} lg={18}>
            {/* 视频预览 + 裁剪编辑器 */}
            <Card className="np-panel-card" styles={{ body: { padding: 0 } }}>
              <VideoTrimEditor
                src={mediaUrl}
                compositionId={compositionId}
                duration={compositionDuration}
                segments={timelineSegments}
                onTrimApplied={(newId, newDur, newMediaUrl) => {
                  setCompositionId(newId)
                  setCompositionDuration(newDur)
                  setMediaUrl(newMediaUrl ?? null)
                }}
              />
            </Card>

            {/* 进度条 */}
            {(composing || composeLastMessage) && (
              <Card size="small" className="np-panel-card">
                <ProgressBar
                  lastMessage={composeLastMessage}
                  connected={connected}
                  active={composing}
                  activeText="正在合成视频..."
                />
              </Card>
            )}

            {/* 时间线 */}
            <Card size="small" className="np-panel-card">
              <Timeline panels={visiblePanels} />
            </Card>
          </Col>

          <Col xs={24} lg={6}>
            {/* 合成选项 */}
            <Card title="合成选项" size="small" className="np-panel-card">
              <OptionsPanel options={options} onChange={setOptions} />
            </Card>
          </Col>
        </Row>
      </div>
    </section>
  )
}
