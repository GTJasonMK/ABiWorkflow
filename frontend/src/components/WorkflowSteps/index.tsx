import { useMemo } from 'react'
import { Steps } from 'antd'
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom'
import { WORKFLOW_STEPS, buildWorkflowStepPath, getStepStatusesByIndex } from '../../utils/workflow'

/**
 * 工作流步骤导航条。
 *
 * 嵌入 PageHeader 的 navigation 插槽，与返回按钮同行展示。
 */
interface WorkflowStepsProps {
  /**
   * 可选：页面可注入“已校验的分集上下文”。
   * 传 null 表示强制按无分集上下文处理，禁用非 script 步骤。
   * 传 undefined 表示沿用 URL 中的 episodeId。
   */
  episodeIdOverride?: string | null
}

export default function WorkflowSteps({ episodeIdOverride }: WorkflowStepsProps) {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const urlEpisodeId = (searchParams.get('episodeId') || '').trim() || null
  const episodeId = episodeIdOverride === undefined ? urlEpisodeId : episodeIdOverride

  // 从 URL 推断当前步骤索引
  const pathSegment = location.pathname.split('/').pop() ?? ''
  const currentIndex = WORKFLOW_STEPS.findIndex((step) => step.key === pathSegment)
  const activeIndex = currentIndex >= 0 ? currentIndex : 0

  const stepStatuses = getStepStatusesByIndex(activeIndex)

  const items = useMemo(() => WORKFLOW_STEPS.map((step, index) => {
    const requiresEpisode = step.key !== 'script'
    const disabled = requiresEpisode && !episodeId
    return {
      title: step.title,
      status: disabled ? 'wait' : stepStatuses[index],
      disabled,
    }
  }), [episodeId, stepStatuses])

  const handleStepClick = (index: number) => {
    if (!projectId) return
    const target = WORKFLOW_STEPS[index]
    if (!target) return
    if (target.key !== 'script' && !episodeId) {
      return
    }
    navigate(buildWorkflowStepPath(projectId, target.key, episodeId))
  }

  return (
    <Steps
      className="np-workflow-steps"
      size="small"
      current={activeIndex}
      items={items}
      onChange={handleStepClick}
    />
  )
}
