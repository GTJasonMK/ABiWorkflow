import { useEffect } from 'react'
import { Steps } from 'antd'
import { LoadingOutlined } from '@ant-design/icons'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import { WORKFLOW_STEPS, getStepStatuses } from '../../utils/workflow'

/**
 * 工作流步骤导航条。
 *
 * 嵌入 PageHeader 的 navigation 插槽，与返回按钮同行展示。
 */
export default function WorkflowSteps() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { currentProject, fetchProject } = useProjectStore()

  // 若 store 中的项目 ID 与 URL 不匹配，触发加载
  useEffect(() => {
    if (projectId && currentProject?.id !== projectId) {
      fetchProject(projectId)
    }
  }, [projectId, currentProject?.id, fetchProject])

  const projectStatus = currentProject?.status ?? 'draft'
  const sceneCount = currentProject?.scene_count ?? 0

  // 从 URL 推断当前步骤索引
  const pathSegment = location.pathname.split('/').pop() ?? ''
  const currentIndex = WORKFLOW_STEPS.findIndex((step) => step.key === pathSegment)
  const activeIndex = currentIndex >= 0 ? currentIndex : 0

  // 根据项目状态计算每个步骤的显示状态
  const stepStatuses = getStepStatuses(projectStatus, sceneCount)

  const items = WORKFLOW_STEPS.map((step, index) => {
    const isActive = index === activeIndex
    const stepStatus = stepStatuses[index]

    // 正在执行的步骤（parsing/generating/composing）显示加载图标
    const showLoading = stepStatus === 'process' && isActive && (
      projectStatus === 'parsing' ||
      projectStatus === 'generating' ||
      projectStatus === 'composing'
    )

    return {
      title: step.title,
      status: isActive ? stepStatus : stepStatus as 'wait' | 'finish' | 'error' | 'process',
      icon: showLoading ? <LoadingOutlined /> : undefined,
    }
  })

  const handleStepClick = (index: number) => {
    if (!projectId) return
    const target = WORKFLOW_STEPS[index]
    if (target) {
      navigate(`/projects/${projectId}/${target.key}`)
    }
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
