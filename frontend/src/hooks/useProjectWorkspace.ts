import { useCallback, useEffect, useState } from 'react'
import { App as AntdApp } from 'antd'
import { getProjectWorkspace } from '../api/projects'
import type { ProjectWorkspace } from '../types/project'
import { getApiErrorMessage } from '../utils/error'

export function useProjectWorkspace(
  projectId: string | undefined,
  errorMessage = '加载项目工作台失败',
) {
  const { message } = AntdApp.useApp()
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null)
  const [loading, setLoading] = useState(false)

  const refreshWorkspace = useCallback(async () => {
    if (!projectId) {
      setWorkspace(null)
      return null
    }
    setLoading(true)
    try {
      const nextWorkspace = await getProjectWorkspace(projectId)
      setWorkspace(nextWorkspace)
      return nextWorkspace
    } catch (error) {
      message.error(getApiErrorMessage(error, errorMessage))
      return null
    } finally {
      setLoading(false)
    }
  }, [errorMessage, message, projectId])

  const replaceWorkspace = useCallback((nextWorkspace: ProjectWorkspace | null) => {
    setWorkspace(nextWorkspace)
  }, [])

  useEffect(() => {
    void refreshWorkspace()
  }, [refreshWorkspace])

  return {
    workspace,
    loading,
    refreshWorkspace,
    replaceWorkspace,
  }
}
