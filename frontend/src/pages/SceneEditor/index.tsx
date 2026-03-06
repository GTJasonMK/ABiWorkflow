import { useCallback, useEffect, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Button, Empty, Space } from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { buildWorkflowStepPath } from '../../utils/workflow'
import EpisodePanelBoard from './EpisodePanelBoard'

export default function SceneEditor() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const pageScrollRef = useRef<HTMLDivElement | null>(null)
  const episodeId = (searchParams.get('episodeId') || '').trim() || null
  const handleEpisodeChange = useCallback((nextEpisodeId: string | null) => {
    if (nextEpisodeId === episodeId) return
    if (!nextEpisodeId) {
      setSearchParams({}, { replace: true })
      return
    }
    setSearchParams({ episodeId: nextEpisodeId }, { replace: true })
  }, [episodeId, setSearchParams])

  useEffect(() => {
    // 进入分镜页时总是从顶部开始，避免复用容器导致的滚动位置遗留
    pageScrollRef.current?.scrollTo({ top: 0, behavior: 'auto' })
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [projectId, episodeId])

  return (
    <section className="np-page">
      <PageHeader
        kicker="分镜工坊"
        title="分集分镜编辑"
        subtitle="基于剧本与已绑定资产生成分镜提示词，并在此完成语音绑定与顺序调整。"
        onBack={() => {
          if (!projectId) return
          if (episodeId) {
            navigate(buildWorkflowStepPath(projectId, 'assets', episodeId))
            return
          }
          navigate(buildWorkflowStepPath(projectId, 'script'))
        }}
        backLabel={episodeId ? '返回上一步' : '返回剧本编辑'}
        navigation={<WorkflowSteps episodeIdOverride={episodeId} />}
        actions={(
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              disabled={!episodeId}
              onClick={() => {
                if (!projectId) return
                navigate(buildWorkflowStepPath(projectId, 'generate', episodeId))
              }}
            >
              开始生成视频
            </Button>
          </Space>
        )}
      />

      <div ref={pageScrollRef} className="np-page-scroll np-scene-editor-page-scroll">
        {!episodeId ? (
          <div className="np-scene-empty">
            <Space direction="vertical" size={12} style={{ width: 460, maxWidth: '100%' }}>
              <Alert
                type="warning"
                showIcon
                message="缺少分集上下文，无法进入分镜编辑"
                description="请先在剧本编辑页选择目标分集，再进入资产绑定和分镜编辑。"
              />
              <Button
                type="primary"
                onClick={() => {
                  if (!projectId) return
                  navigate(buildWorkflowStepPath(projectId, 'script'))
                }}
              >
                返回剧本编辑选择分集
              </Button>
            </Space>
          </div>
        ) : projectId ? (
          <EpisodePanelBoard
            projectId={projectId}
            initialEpisodeId={episodeId}
            onEpisodeChange={handleEpisodeChange}
            lockedEpisodeId={episodeId}
          />
        ) : <Empty description="项目参数缺失" />}
      </div>
    </section>
  )
}
