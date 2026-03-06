/** 工作流步骤定义 */
export interface WorkflowStep {
  key: WorkflowStepKey
  title: string
  description: string
}

export type WorkflowStepKey = 'script' | 'assets' | 'scenes' | 'generate' | 'compose'

/** 5 个工作流步骤（顺序固定） */
export const WORKFLOW_STEPS: readonly WorkflowStep[] = [
  { key: 'script', title: '剧本编辑', description: '输入或修改剧本' },
  { key: 'assets', title: '资产绑定', description: '按分集绑定角色与地点资产' },
  { key: 'scenes', title: '分镜编辑', description: '生成并调整分镜提示词，完成语音绑定' },
  { key: 'generate', title: '视频生成', description: '批量生成视频片段' },
  { key: 'compose', title: '合成预览', description: '合成并导出成片' },
] as const

/**
 * 构建工作流步骤路由。
 *
 * 单集上下文下，除 script 外的步骤都透传 episodeId。
 */
export function buildWorkflowStepPath(
  projectId: string,
  stepKey: WorkflowStepKey,
  episodeId?: string | null,
): string {
  if (stepKey === 'script' || !episodeId) {
    return `/projects/${projectId}/${stepKey}`
  }
  return `/projects/${projectId}/${stepKey}?episodeId=${encodeURIComponent(episodeId)}`
}

/**
 * 根据当前步骤索引计算步骤状态。
 *
 * 返回长度为 5 的数组，依次对应 script / assets / scenes / generate / compose。
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
