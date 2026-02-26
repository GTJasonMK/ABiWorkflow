import type { ProjectStatus } from '../types/project'

/** 工作流步骤定义 */
export interface WorkflowStep {
  key: string
  title: string
  description: string
}

/** 4 个工作流步骤（顺序固定） */
export const WORKFLOW_STEPS: readonly WorkflowStep[] = [
  { key: 'script', title: '剧本编辑', description: '输入或修改剧本' },
  { key: 'scenes', title: '场景编辑', description: '调整场景与角色' },
  { key: 'generate', title: '视频生成', description: '批量生成视频片段' },
  { key: 'compose', title: '合成预览', description: '合成并导出成片' },
] as const

/** 正在执行异步任务的项目状态集合 */
export const BUSY_STATUSES: ReadonlySet<ProjectStatus> = new Set([
  'parsing',
  'generating',
  'composing',
])

/**
 * 根据项目状态返回最合适的步骤路由 key。
 *
 * 用于 ProjectList 的导航按钮、以及其他需要"跳转到当前进度"的场景。
 */
export function getTargetStepKey(status: ProjectStatus): string {
  switch (status) {
    case 'draft':
    case 'parsing':
      return 'script'
    case 'parsed':
      return 'scenes'
    case 'generating':
      return 'generate'
    case 'composing':
    case 'completed':
      return 'compose'
    case 'failed':
      return 'script'
    default:
      return 'script'
  }
}

/**
 * 根据项目状态返回每个步骤应展示的 Ant Design Steps status。
 *
 * 返回长度为 4 的数组，依次对应 script / scenes / generate / compose。
 */
export function getStepStatuses(
  projectStatus: ProjectStatus,
  sceneCount: number,
): Array<'wait' | 'process' | 'finish' | 'error'> {
  switch (projectStatus) {
    case 'draft':
      return ['process', 'wait', 'wait', 'wait']
    case 'parsing':
      return ['process', 'wait', 'wait', 'wait']
    case 'parsed':
      return ['finish', 'process', 'wait', 'wait']
    case 'generating':
      return ['finish', 'finish', 'process', 'wait']
    case 'composing':
      return ['finish', 'finish', 'finish', 'process']
    case 'completed':
      return ['finish', 'finish', 'finish', 'finish']
    case 'failed': {
      // 推断失败发生在哪个步骤
      if (sceneCount === 0) {
        return ['error', 'wait', 'wait', 'wait']
      }
      // 有场景但可能未全部生成 — 标记生成步骤失败
      return ['finish', 'finish', 'error', 'wait']
    }
    default:
      return ['process', 'wait', 'wait', 'wait']
  }
}
