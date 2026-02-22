import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Card, Col, Row, Space, Spin, Typography, message } from 'antd'
import { DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { useSceneStore } from '../../stores/sceneStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { startComposition, getDownloadUrl } from '../../api/composition'
import VideoPlayer from '../../components/VideoPlayer'
import ProgressBar from '../../components/ProgressBar'
import Timeline from './Timeline'
import OptionsPanel from './OptionsPanel'
import PageHeader from '../../components/PageHeader'

const { Paragraph } = Typography

export default function CompositionPreview() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { scenes, loading, fetchScenes } = useSceneStore()
  const { lastMessage, connected } = useWebSocket(projectId)
  const [composing, setComposing] = useState(false)
  const [compositionId, setCompositionId] = useState<string | null>(null)
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
      fetchScenes(projectId)
    }
  }, [projectId, fetchScenes])

  const handleCompose = async () => {
    if (!projectId) return
    setComposing(true)
    try {
      const result = await startComposition(projectId, options)
      setCompositionId(result.composition_id)
      message.success('视频合成完成')
    } catch {
      message.error('合成失败')
    } finally {
      setComposing(false)
    }
  }

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  return (
    <div>
      <PageHeader
        kicker="Final Composition"
        title="合成预览"
        subtitle="设置转场与字幕策略，生成最终成片并下载导出。"
        onBack={() => navigate(`/projects/${projectId}/generate`)}
        backLabel="返回生成"
        actions={(
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleCompose}
              loading={composing}
            >
              {composing ? '合成中...' : '开始合成'}
            </Button>
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

      <Paragraph className="np-note" style={{ marginBottom: 12 }}>
        推荐先使用默认转场完成首版，再针对节奏问题进行二次细调。
      </Paragraph>

      <Row gutter={16}>
        <Col xs={24} lg={18}>
          {/* 视频预览 */}
          <Card className="np-panel-card">
            <VideoPlayer
              src={compositionId ? getDownloadUrl(compositionId) : null}
            />
          </Card>

          {/* 进度条 */}
          {(composing || lastMessage) && (
            <Card size="small" className="np-panel-card">
              <ProgressBar lastMessage={lastMessage} connected={connected} />
            </Card>
          )}

          {/* 时间线 */}
          <Card size="small" className="np-panel-card">
            <Timeline scenes={scenes} />
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
  )
}
