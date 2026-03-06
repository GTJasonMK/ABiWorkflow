import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Card, Empty, Space, Spin, Tag, Typography, App as AntdApp } from 'antd'
import {
  LoadingOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  ScissorOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { startGeneration } from '../../api/generation'
import { listEpisodePanels } from '../../api/panels'
import { listEpisodes } from '../../api/episodes'
import { resolveAsyncResult } from '../../api/tasks'
import { abortProjectTask, getProject } from '../../api/projects'
import { useWebSocket } from '../../hooks/useWebSocket'
import type { Panel } from '../../types/panel'
import type { Episode } from '../../types/episode'
import PageHeader from '../../components/PageHeader'
import ProgressBar from '../../components/ProgressBar'
import WorkflowSteps from '../../components/WorkflowSteps'
import { getApiErrorMessage } from '../../utils/error'
import { handleForceRecoverError } from '../../utils/forceRecover'
import { buildWorkflowStepPath } from '../../utils/workflow'
import PanelGenerationCard from './PanelGenerationCard'

const { Text } = Typography
const { Paragraph } = Typography

export default function VideoGeneration() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const episodeId = (searchParams.get('episodeId') || '').trim() || null
  const { messages, connected, clearMessages } = useWebSocket(projectId)
  const { message, modal } = AntdApp.useApp()
  const [generating, setGenerating] = useState(false)
  const [panels, setPanels] = useState<Panel[]>([])
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [loadingPanels, setLoadingPanels] = useState(false)

  const generateLastMessage = useMemo(
    () => [...messages].reverse().find((item) => item.type.startsWith('generate_')) ?? null,
    [messages],
  )

  const selectedEpisode = useMemo(() => {
    if (!episodeId) return null
    return episodes.find((episode) => episode.id === episodeId) ?? null
  }, [episodeId, episodes])
  const contextEpisodeId = selectedEpisode?.id ?? null

  const visiblePanels = panels

  const currentEpisodeTitle = selectedEpisode?.title ?? null

  const panelStats = useMemo(() => {
    const total = visiblePanels.length
    const completed = visiblePanels.filter((panel) => panel.status === 'completed' && Boolean(panel.video_url || panel.lipsync_video_url)).length
    const failed = visiblePanels.filter((panel) => panel.status === 'failed').length
    return { total, completed, failed }
  }, [visiblePanels])

  const canCompose = useMemo(
    () => visiblePanels.length > 0 && visiblePanels.every((panel) => panel.status === 'completed' && Boolean(panel.video_url || panel.lipsync_video_url)),
    [visiblePanels],
  )

  const fetchPanels = useCallback(async () => {
    if (!projectId || !episodeId) return
    setLoadingPanels(true)
    try {
      const [rows, eps] = await Promise.all([
        listEpisodePanels(episodeId),
        listEpisodes(projectId),
      ])
      setPanels(rows)
      setEpisodes(eps)
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载分镜失败'))
    } finally {
      setLoadingPanels(false)
    }
  }, [episodeId, message, projectId])

  useEffect(() => {
    if (!projectId || !episodeId) return
    void fetchPanels()
    getProject(projectId).then((project) => {
      setGenerating(project.status === 'generating')
    }).catch(() => {
      setGenerating(false)
    })
  }, [episodeId, fetchPanels, projectId])

  const runGenerate = async (forceRecover = false, forceRegenerate = false) => {
    if (!projectId || !contextEpisodeId) {
      message.warning('请先在剧本页选择分集后再执行生成')
      return
    }
    const scopeEpisodeId = contextEpisodeId
    setGenerating(true)
    clearMessages()
    try {
      const startResult = await startGeneration(projectId, { forceRecover, forceRegenerate }, scopeEpisodeId)
      const result = await resolveAsyncResult(
        startResult as unknown as Record<string, unknown>,
        { timeoutMs: 20 * 60 * 1000 },
      )
      const completed = Number(result.completed ?? 0)
      const failed = Number(result.failed ?? 0)
      const total = Number(result.total_panels ?? 0)
      message.success(`批量生成完成（当前分集）：${completed}/${total}，失败 ${failed}`)
    } catch (error) {
      handleForceRecoverError(error, forceRecover, modal, message, {
        retryFn: () => runGenerate(true, forceRegenerate),
        errorFallback: '分镜批量生成失败',
      })
    } finally {
      setGenerating(false)
      await fetchPanels()
    }
  }

  const handleAbort = () => {
    if (!projectId) return
    modal.confirm({
      title: '确认取消生成',
      content: '将强制中止当前批量生成任务，未完成分镜可稍后重试。',
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
          setGenerating(false)
          await fetchPanels()
        } catch (err) {
          message.error(getApiErrorMessage(err, '取消失败'))
        }
      },
    })
  }

  if (loadingPanels) {
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
          kicker="生成流程"
          title="视频生成"
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
          kicker="生成流程"
          title="视频生成"
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
            <Empty description="当前分集不存在或已删除，请从剧本页重新进入视频生成。" />
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
        subtitle="以分镜为主线进行批量生成与逐镜复核。"
        onBack={() => {
          if (!projectId) return
          navigate(buildWorkflowStepPath(projectId, 'scenes', contextEpisodeId))
        }}
        backLabel="返回上一步"
        navigation={<WorkflowSteps episodeIdOverride={contextEpisodeId} />}
        actions={(
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={() => { void runGenerate(false, false) }}
              disabled={generating || visiblePanels.length === 0}
              loading={generating}
            >
              {generating ? '生成中...' : '批量生成'}
            </Button>
            {generating && (
              <Button
                icon={<StopOutlined />}
                onClick={handleAbort}
                danger
              >
                取消生成
              </Button>
            )}
            <Button
              icon={<ScissorOutlined />}
              disabled={generating || !canCompose}
              onClick={() => {
                if (!projectId) return
                navigate(buildWorkflowStepPath(projectId, 'compose', contextEpisodeId))
              }}
            >
              去合成
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
        <Paragraph className="np-note" style={{ marginBottom: 12 }}>
          先完成“资产绑定与提示词复核”，再执行批量生成，可显著减少返工。
        </Paragraph>

        {(generating || generateLastMessage) && (
          <Card size="small" className="np-panel-card">
            <ProgressBar
              lastMessage={generateLastMessage}
              connected={connected}
              active={generating}
              activeText="正在批量生成分镜视频..."
            />
          </Card>
        )}

        <Card size="small" className="np-panel-card" style={{ marginBottom: 12 }}>
          <Space size={12} wrap align="center">
            <Tag className="np-status-tag">单集模式</Tag>
            <Tag className="np-status-tag">{currentEpisodeTitle || '当前分集'}</Tag>
            <Tag className="np-status-tag">分镜总数：{panelStats.total}</Tag>
            <Tag className="np-status-tag np-status-generated">已完成：{panelStats.completed}</Tag>
            <Tag className="np-status-tag np-status-failed">失败：{panelStats.failed}</Tag>
            {generating ? (
              <Tag className="np-status-tag np-status-generating" icon={<LoadingOutlined spin />}>生成中</Tag>
            ) : (
              <Text type="secondary">可在下方逐分镜复核并手动补提任务</Text>
            )}
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
            当前分集模式下，“批量生成 / 去合成”仅作用于该分集。
          </Paragraph>
        </Card>

        {visiblePanels.length > 0 ? (
          <PanelGenerationCard panels={visiblePanels} onRefresh={fetchPanels} />
        ) : (
          <Text type="secondary">暂无分镜数据，可在"分镜编辑"中创建。</Text>
        )}
      </div>
    </section>
  )
}
