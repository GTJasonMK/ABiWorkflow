import { useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Empty, Space } from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { buildWorkflowStepPath } from '../../utils/workflow'
import EpisodePanelBoard from './EpisodePanelBoard'

export default function StoryboardEditor() {
  const { id: projectId, episodeId } = useParams<{ id: string; episodeId?: string }>()
  const navigate = useNavigate()
  const pageScrollRef = useRef<HTMLDivElement | null>(null)
  const scopedEpisodeId = (episodeId || '').trim() || null

  useEffect(() => {
    // 进入分镜页时总是从顶部开始，避免复用容器导致的滚动位置遗留
    pageScrollRef.current?.scrollTo({ top: 0, behavior: 'auto' })
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [projectId, scopedEpisodeId])

  return (
    <section className="np-page">
      <PageHeader
        kicker="分镜工坊"
        title="分集分镜编辑"
        subtitle="基于剧本与已绑定资产生成分镜提示词，并在此完成语音绑定与顺序调整。"
        onBack={() => {
          if (!projectId || !scopedEpisodeId) return
          navigate(buildWorkflowStepPath(projectId, 'assets', scopedEpisodeId))
        }}
        backLabel="返回上一步"
        navigation={<WorkflowSteps />}
        actions={(
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              disabled={!scopedEpisodeId}
              onClick={() => {
                if (!projectId || !scopedEpisodeId) return
                navigate(buildWorkflowStepPath(projectId, 'video', scopedEpisodeId))
              }}
            >
              开始生成视频
            </Button>
          </Space>
        )}
      />

      <div ref={pageScrollRef} className="np-page-scroll np-storyboard-editor-page-scroll">
        {projectId && scopedEpisodeId ? (
          <EpisodePanelBoard
            projectId={projectId}
            initialEpisodeId={scopedEpisodeId}
            lockedEpisodeId={scopedEpisodeId}
          />
        ) : <Empty description="分集参数缺失" />}
      </div>
    </section>
  )
}
