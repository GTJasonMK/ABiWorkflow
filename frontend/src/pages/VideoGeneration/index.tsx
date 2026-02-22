import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Space, Spin, Card, Tag, List, Typography, message } from 'antd'
import {
  PlayCircleOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ScissorOutlined,
} from '@ant-design/icons'
import { useSceneStore } from '../../stores/sceneStore'
import { useWebSocket } from '../../hooks/useWebSocket'
import { startGeneration, retryScene } from '../../api/generation'
import ProgressBar from '../../components/ProgressBar'
import PageHeader from '../../components/PageHeader'

const { Text, Paragraph } = Typography

export default function VideoGeneration() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { scenes, loading, fetchScenes } = useSceneStore()
  const { lastMessage, connected } = useWebSocket(projectId)
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    if (projectId) {
      fetchScenes(projectId)
    }
  }, [projectId, fetchScenes])

  const handleGenerate = async () => {
    if (!projectId) return
    setGenerating(true)
    try {
      const result = await startGeneration(projectId)
      message.success(`生成完成：${result.completed} 成功，${result.failed} 失败`)
      await fetchScenes(projectId)
    } catch {
      message.error('视频生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const handleRetry = async (sceneId: string) => {
    try {
      await retryScene(sceneId)
      message.success('重试成功')
      if (projectId) await fetchScenes(projectId)
    } catch {
      message.error('重试失败')
    }
  }

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  const statusIcon: Record<string, React.ReactNode> = {
    pending: <Tag className="np-status-tag">待生成</Tag>,
    generating: <Tag className="np-status-tag np-status-generating" icon={<LoadingOutlined spin />}>生成中</Tag>,
    generated: <Tag className="np-status-tag np-status-generated" icon={<CheckCircleOutlined />}>已完成</Tag>,
    failed: <Tag className="np-status-tag np-status-failed" icon={<CloseCircleOutlined />}>失败</Tag>,
  }

  return (
    <div>
      <PageHeader
        kicker="Generation Pipeline"
        title="视频生成"
        subtitle="逐场景渲染视频片段，失败场景可单独重试。"
        onBack={() => navigate(`/projects/${projectId}/scenes`)}
        backLabel="返回场景"
        actions={(
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleGenerate}
              loading={generating}
            >
              {generating ? '生成中...' : '开始生成'}
            </Button>
            <Button
              icon={<ScissorOutlined />}
              disabled={!scenes.some((s) => s.status === 'generated')}
              onClick={() => navigate(`/projects/${projectId}/compose`)}
            >
              去合成
            </Button>
          </Space>
        )}
      />

      <Paragraph className="np-note" style={{ marginBottom: 12 }}>
        提示：优先修复失败场景再合成，可显著降低成片跳变与风格不一致。
      </Paragraph>

      {(generating || lastMessage) && (
        <Card size="small" className="np-panel-card">
          <ProgressBar lastMessage={lastMessage} connected={connected} />
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
            ].filter(Boolean)}
          >
            <List.Item.Meta
              title={
                <Space>
                  <Text>场景 {scene.sequence_order + 1}: {scene.title}</Text>
                  {statusIcon[scene.status] ?? <Tag className="np-status-tag">{scene.status}</Tag>}
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
  )
}
