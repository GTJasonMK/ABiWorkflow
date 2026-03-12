import { useMemo } from 'react'
import { Steps } from 'antd'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { WORKFLOW_STEPS, buildWorkflowStepPath, getStepStatusesByIndex, resolveWorkflowStepFromPath } from '../../utils/workflow'

/**
 * 工作流步骤导航条。
 *
 * 嵌入 PageHeader 的 navigation 插槽，与返回按钮同行展示。
 */
export default function WorkflowSteps() {
  const { id: projectId, episodeId } = useParams<{ id: string; episodeId?: string }>()
  const navigate = useNavigate()
  const location = useLocation()

  // 从 URL 推断当前步骤索引
  const currentKey = resolveWorkflowStepFromPath(location.pathname)
  const currentIndex = WORKFLOW_STEPS.findIndex((step) => step.key === currentKey)
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
