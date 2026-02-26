import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Card, Col, Row, Space, Spin, Typography, App as AntdApp } from 'antd'
import { DownloadOutlined, PlayCircleOutlined, StopOutlined } from '@ant-design/icons'
import { useSceneStore } from '../../stores/sceneStore'
import { useTaskStore } from '../../stores/taskStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { startComposition, getDownloadUrl, getLatestComposition, getComposition } from '../../api/composition'
import { abortProjectTask, getProject } from '../../api/projects'
import VideoTrimEditor from '../../components/VideoTrimEditor'
import ProgressBar from '../../components/ProgressBar'
import Timeline from './Timeline'
import OptionsPanel from './OptionsPanel'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { getApiErrorMessage } from '../../utils/error'
import { shouldSuggestForceRecover } from '../../utils/forceRecover'

const { Paragraph } = Typography

export default function CompositionPreview() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { scenes, loading, fetchScenes, reorderScenes } = useSceneStore()
  const { messages, connected, clearMessages } = useWebSocket(projectId)
  const [composing, setComposing] = useState(false)
  const [compositionId, setCompositionId] = useState<string | null>(null)
  const [compositionDuration, setCompositionDuration] = useState(0)
  const [mediaUrl, setMediaUrl] = useState<string | null>(null)
  const { message, modal } = AntdApp.useApp()
  const composeLastMessage = useMemo(
    () => [...messages].reverse().find((item) => item.type.startsWith('compose_')) ?? null,
    [messages],
  )
  const readySceneStatuses = useMemo(() => new Set(['generated', 'completed']), [])
  const canCompose = useMemo(
    () => scenes.length > 0 && scenes.every((scene) => readySceneStatuses.has(scene.status)),
    [readySceneStatuses, scenes],
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

  useEffect(() => {
    if (projectId) {
      fetchScenes(projectId).catch((error) => {
        message.error(getApiErrorMessage(error, '加载场景失败'))
      })
      // 加载最新的已完成合成记录
      getLatestComposition(projectId).then((record) => {
        if (record) {
          setCompositionId(record.id)
          setCompositionDuration(Number(record.duration_seconds ?? 0))
          setMediaUrl(record.media_url ?? null)
        }
      }).catch(() => {
        // 查询失败不阻塞页面
      })
      // 检测项目是否仍在合成（页面刷新/导航后恢复状态）
      getProject(projectId).then((project) => {
        if (project.status === 'composing') {
          setComposing(true)
        }
      }).catch(() => {})
    }
  }, [projectId, fetchScenes, message])

  const runCompose = async (forceRecover = false) => {
    if (!projectId) return
    if (!canCompose) {
      message.warning('请先完成全部场景生成，再进行合成')
      return
    }
    setComposing(true)
    clearMessages()
    try {
      const startResult = await startComposition(projectId, options, { forceRecover })
      let compositionId = ''

      if ('task_id' in startResult) {
        const finalStatus = await useTaskStore.getState().trackTask(
          startResult.task_id,
          { taskType: 'compose', projectId },
          { timeoutMs: 20 * 60 * 1000 },
        )
        const resultData = finalStatus.result ?? {}
        compositionId = String(resultData.composition_id ?? '')
      } else {
        compositionId = startResult.composition_id
      }

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
    } catch (error) {
      if (!forceRecover && shouldSuggestForceRecover(error)) {
        modal.confirm({
          title: '检测到合成任务可能中断',
          content: '是否强制恢复项目状态并重试合成？若旧任务仍在执行，可能与新任务冲突。',
          okText: '强制恢复并重试',
          cancelText: '取消',
          onOk: async () => {
            await runCompose(true)
          },
        })
        return
      }
      message.error(getApiErrorMessage(error, '合成失败'))
    } finally {
      setComposing(false)
      // 无论成功或失败，都刷新场景列表以同步后端最新状态
      fetchScenes(projectId).catch(() => {})
    }
  }

  const handleCompose = () => {
    void runCompose(false)
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

  return (
    <section className="np-page">
      <PageHeader
        kicker="成片合成"
        title="合成预览"
        subtitle="设置转场与字幕策略，生成最终成片并下载导出。"
        onBack={() => navigate(`/projects/${projectId}/generate`)}
        backLabel="返回生成"
        navigation={<WorkflowSteps />}
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
                href={getDownloadUrl(compositionId)}
                target="_blank"
              >
                下载视频
              </Button>
            )}
          </Space>
        )}
      />

      <div className="np-page-scroll">
        <Paragraph className="np-note" style={{ marginBottom: 12 }}>
          推荐先使用默认转场完成首版，再针对节奏问题进行二次细调。
        </Paragraph>

        <Row gutter={16}>
          <Col xs={24} lg={18}>
            {/* 视频预览 + 裁剪编辑器 */}
            <Card className="np-panel-card" styles={{ body: { padding: 0 } }}>
              <VideoTrimEditor
                src={mediaUrl}
                compositionId={compositionId}
                duration={compositionDuration}
                scenes={scenes}
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
              <Timeline scenes={scenes} projectId={projectId!} onReorder={reorderScenes} />
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
