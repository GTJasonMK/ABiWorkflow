export const OPTIONAL_PROBE_ENABLED = import.meta.env.VITE_PROBE_OPTIONAL_ENDPOINTS === 'true'

export const CODE_INPUT_STYLE = { fontFamily: "'JetBrains Mono', 'Fira Code', monospace" } as const

export const HOME_LABEL: Record<string, string> = {
  '/dashboard': '总览看板',
  '/projects': '项目工作台',
  '/tasks': '任务中心',
  '/operations': '运营中心',
  '/settings': '系统设置',
  '/guide': '使用指南',
}
