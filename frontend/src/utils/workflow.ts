/** 工作流步骤定义 */
export interface WorkflowStep {
  key: WorkflowStepKey
  title: string
  description: string
}

export type WorkflowStepKey = 'script' | 'assets' | 'storyboard' | 'video' | 'preview'

/** 5 个工作流步骤（顺序固定） */
export const WORKFLOW_STEPS: readonly WorkflowStep[] = [
  { key: 'script', title: '剧本分集', description: '选择分集并编辑剧本' },
  { key: 'assets', title: '资产绑定', description: '按分集绑定角色与地点资产' },
  { key: 'storyboard', title: '分镜编辑', description: '生成并调整分镜提示词，完成语音绑定' },
  { key: 'video', title: '视频生成', description: '批量生成视频片段' },
  { key: 'preview', title: '成片预览', description: '合成并导出成片' },
] as const

export function getWorkflowStepLabel(stepKey: string): string {
  return WORKFLOW_STEPS.find((item) => item.key === stepKey)?.title ?? stepKey
}

/**
 * 构建工作流步骤路由。
 *
 * 分集上下文下，除 script 外的步骤都要求 episodeId。
 */
export function buildWorkflowStepPath(
  projectId: string,
  stepKey: WorkflowStepKey,
  episodeId?: string | null,
): string {
  if (stepKey === 'script') {
    return `/projects/${projectId}/script`
  }
  if (!episodeId) {
    return `/projects/${projectId}/script`
  }
  return `/projects/${projectId}/${stepKey}/${encodeURIComponent(episodeId)}`
}

export function resolveWorkflowStepFromPath(pathname: string): WorkflowStepKey {
  const segments = pathname.split('/').filter(Boolean)
  const workflowSegment = segments[2] ?? 'script'
  if (workflowSegment === 'script') return 'script'
  if (workflowSegment === 'assets') return 'assets'
  if (workflowSegment === 'storyboard') return 'storyboard'
  if (workflowSegment === 'video') return 'video'
  if (workflowSegment === 'preview') return 'preview'
  return 'script'
}

/**
 * 根据当前步骤索引计算步骤状态。
 *
 * 返回长度为 5 的数组，依次对应 script / assets / storyboard / video / preview。
 */
export function getStepStatusesByIndex(
  activeIndex: number,
): Array<'wait' | 'process' | 'finish'> {
  return WORKFLOW_STEPS.map((_, index) => {
    if (index < activeIndex) return 'finish'
    if (index === activeIndex) return 'process'
    return 'wait'
  })
}
