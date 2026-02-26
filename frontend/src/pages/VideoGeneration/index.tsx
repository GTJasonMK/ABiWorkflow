import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Space, Spin, Card, Tag, List, Tooltip, Typography, App as AntdApp } from 'antd'
import {
  PlayCircleOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  ScissorOutlined,
  StopOutlined,
  PictureOutlined,
  CopyOutlined,
} from '@ant-design/icons'
import { useSceneStore } from '../../stores/sceneStore'
import { useTaskStore } from '../../stores/taskStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { startGeneration, retryScene, generateCandidates } from '../../api/generation'
import { abortProjectTask, getProject } from '../../api/projects'
import ProgressBar from '../../components/ProgressBar'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import CandidatePickerModal from '../../components/CandidatePickerModal'
import { getApiErrorMessage } from '../../utils/error'
import { shouldSuggestForceRecover } from '../../utils/forceRecover'

const { Text, Paragraph } = Typography

export default function VideoGeneration() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { scenes, loading, fetchScenes } = useSceneStore()
  const { messages, connected, clearMessages } = useWebSocket(projectId)
  const [generating, setGenerating] = useState(false)
  const [pickerScene, setPickerScene] = useState<{ id: string; title: string } | null>(null)
  const [generatingCandidateId, setGeneratingCandidateId] = useState<string | null>(null)
  const { message, modal } = AntdApp.useApp()
  const generateLastMessage = useMemo(
    () => [...messages].reverse().find((item) => item.type.startsWith('generate_')) ?? null,
    [messages],
  )
  const readySceneStatuses = useMemo(() => new Set(['generated', 'completed']), [])
  const failedScenes = useMemo(() => scenes.filter((s) => s.status === 'failed'), [scenes])

  useEffect(() => {
    if (projectId) {
      fetchScenes(projectId).catch((error) => {
        message.error(getApiErrorMessage(error, '加载场景失败'))
      })
      // 检测项目是否仍在生成（页面刷新/导航后恢复状态）
      getProject(projectId).then((project) => {
        if (project.status === 'generating') {
          setGenerating(true)
        }
      }).catch(() => {})
    }
  }, [projectId, fetchScenes, message])

  const runGenerate = async (forceRecover = false, forceRegenerate = false) => {
    if (!projectId) return
    setGenerating(true)
    clearMessages()
    try {
      const startResult = await startGeneration(projectId, { forceRecover, forceRegenerate })
      let completed = 0
      let failed = 0

      if ('task_id' in startResult) {
        const finalStatus = await useTaskStore.getState().trackTask(
          startResult.task_id,
          { taskType: 'generate', projectId },
          { timeoutMs: 20 * 60 * 1000 },
        )
        const resultData = finalStatus.result ?? {}
        completed = Number(resultData.completed ?? 0)
        failed = Number(resultData.failed ?? 0)
      } else {
        completed = startResult.completed
        failed = startResult.failed
      }

      message.success(`生成完成：${completed} 成功，${failed} 失败`)
    } catch (error) {
      if (!forceRecover && shouldSuggestForceRecover(error)) {
        modal.confirm({
          title: '检测到生成任务可能中断',
          content: '是否强制恢复项目状态并重试生成？若旧任务仍在执行，可能与新任务冲突。',
          okText: '强制恢复并重试',
          cancelText: '取消',
          onOk: async () => {
            await runGenerate(true, forceRegenerate)
          },
        })
        return
      }
      message.error(getApiErrorMessage(error, '视频生成失败'))
    } finally {
      setGenerating(false)
      // 无论成功或失败，都刷新场景列表以同步后端最新状态
      fetchScenes(projectId).catch(() => {})
    }
  }

  const handleGenerate = () => {
    void runGenerate(false, false)
  }

  const handleRegenerate = () => {
    modal.confirm({
      title: '确认重新生成',
      content: '将重新生成所有场景的视频片段，已有的视频将被替换。确定继续吗？',
      okText: '重新生成全部',
      cancelText: '取消',
      onOk: async () => {
        await runGenerate(false, true)
      },
    })
  }

  const handleRetryAllFailed = () => {
    modal.confirm({
      title: '重试全部失败场景',
      content: `当前有 ${failedScenes.length} 个失败场景，将重新生成这些场景的视频。确定继续吗？`,
      okText: '重试失败场景',
      cancelText: '取消',
      onOk: async () => {
        await runGenerate(false, false)
      },
    })
  }

  const handleAbort = () => {
    if (!projectId) return
    modal.confirm({
      title: '确认取消生成',
      content: '将强制中止当前生成任务，项目状态恢复为可操作。已完成的场景不受影响，未完成的场景可稍后重试。',
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
          await fetchScenes(projectId)
        } catch (err) {
          message.error(getApiErrorMessage(err, '取消失败'))
        }
      },
    })
  }

  const handleRetry = async (sceneId: string) => {
    try {
      await retryScene(sceneId)
      message.success('重试成功')
      if (projectId) await fetchScenes(projectId)
    } catch (error) {
      message.error(getApiErrorMessage(error, '重试失败'))
    }
  }

  const handleGenerateCandidates = async (sceneId: string) => {
    setGeneratingCandidateId(sceneId)
    try {
      const result = await generateCandidates(sceneId, 3)
      message.success(`候选生成完成：${result.generated} 成功，${result.failed} 失败`)
      if (projectId) await fetchScenes(projectId)
    } catch (error) {
      message.error(getApiErrorMessage(error, '候选生成失败'))
    } finally {
      setGeneratingCandidateId(null)
    }
  }

  if (loading) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  const statusIcon: Record<string, React.ReactNode> = {
    pending: <Tag className="np-status-tag">待生成</Tag>,
    generating: <Tag className="np-status-tag np-status-generating" icon={<LoadingOutlined spin />}>生成中</Tag>,
    generated: <Tag className="np-status-tag np-status-generated" icon={<CheckCircleOutlined />}>已完成</Tag>,
    completed: <Tag className="np-status-tag np-status-generated" icon={<CheckCircleOutlined />}>已完成</Tag>,
    failed: <Tag className="np-status-tag np-status-failed" icon={<CloseCircleOutlined />}>失败</Tag>,
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="生成流程"
        title="视频生成"
        subtitle="逐场景渲染视频片段，失败场景可单独重试。"
        onBack={() => navigate(`/projects/${projectId}/scenes`)}
        backLabel="返回场景"
        navigation={<WorkflowSteps />}
        actions={(
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleGenerate}
              disabled={generating}
              loading={generating}
            >
              {generating ? '生成中...' : '开始生成'}
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
            {failedScenes.length > 0 && (
              <Button
                icon={<ExclamationCircleOutlined />}
                onClick={handleRetryAllFailed}
                disabled={generating}
                danger
              >
                重试全部失败（{failedScenes.length}）
              </Button>
            )}
            {scenes.some((s) => readySceneStatuses.has(s.status)) && (
              <Button
                icon={<ReloadOutlined />}
                onClick={handleRegenerate}
                disabled={generating}
              >
                重新生成全部
              </Button>
            )}
            <Button
              icon={<ScissorOutlined />}
              disabled={generating || scenes.length === 0 || !scenes.every((s) => readySceneStatuses.has(s.status))}
              onClick={() => navigate(`/projects/${projectId}/compose`)}
            >
              去合成
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
        <Paragraph className="np-note" style={{ marginBottom: 12 }}>
          提示：优先修复失败场景再合成，可显著降低成片跳变与风格不一致。
        </Paragraph>

        {(generating || generateLastMessage) && (
          <Card size="small" className="np-panel-card">
            <ProgressBar
              lastMessage={generateLastMessage}
              connected={connected}
              active={generating}
              activeText="正在生成视频片段..."
            />
          </Card>
        )}

        <List
          bordered
          dataSource={scenes}
          renderItem={(scene) => (
            <List.Item
              actions={[
                scene.status === 'failed' && (
                  <Button
                    key="retry"
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={() => handleRetry(scene.id)}
                  >
                    重试
                  </Button>
                ),
                readySceneStatuses.has(scene.status) && (
                  <Button
                    key="regenerate"
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={() => handleRetry(scene.id)}
                  >
                    重新生成
                  </Button>
                ),
                readySceneStatuses.has(scene.status) && (
                  <Tooltip key="pick" title="选片：比较候选视频并选择最佳版本">
                    <Button
                      size="small"
                      icon={<PictureOutlined />}
                      onClick={() => setPickerScene({ id: scene.id, title: scene.title })}
                    >
                      选片
                    </Button>
                  </Tooltip>
                ),
                scene.video_prompt && !generating && (
                  <Tooltip key="candidates" title="生成 3 个候选版本供对比选择">
                    <Button
                      size="small"
                      icon={<CopyOutlined />}
                      loading={generatingCandidateId === scene.id}
                      disabled={!!generatingCandidateId}
                      onClick={() => handleGenerateCandidates(scene.id)}
                    >
                      生成候选
                    </Button>
                  </Tooltip>
                ),
              ].filter(Boolean)}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Text>场景 {scene.sequence_order + 1}: {scene.title}</Text>
                    {statusIcon[scene.status] ?? <Tag className="np-status-tag">{scene.status}</Tag>}
                    {scene.clip_summary.total > 1 && (
                      <Tag className="np-status-tag" style={{ fontSize: 10 }}>
                        {scene.clip_summary.completed}/{scene.clip_summary.total} 片段
                      </Tag>
                    )}
                  </Space>
                }
                description={
                  <Text type="secondary" ellipsis>
                    {scene.video_prompt?.slice(0, 120)}...
                  </Text>
                }
              />
              <Text type="secondary">{scene.duration_seconds}秒</Text>
            </List.Item>
          )}
        />
      </div>

      {pickerScene && (
        <CandidatePickerModal
          open={!!pickerScene}
          sceneId={pickerScene.id}
          sceneTitle={pickerScene.title}
          onClose={() => setPickerScene(null)}
          onSelected={() => {
            if (projectId) fetchScenes(projectId).catch(() => {})
          }}
        />
      )}
    </section>
  )
}
