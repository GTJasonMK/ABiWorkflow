import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getProjectAssets, type ProjectAssetsPayload } from '../../api/assets'
import { getAssetHubOverview } from '../../api/assetHub'
import { getProjectCosts } from '../../api/costs'
import { useProjectStore } from '../../stores/projectStore'
import type { AssetHubOverview } from '../../types/assetHub'
import type { CostListPayload } from '../../types/cost'
import { getApiErrorMessage } from '../../utils/error'

export type OperationsTab = 'costs' | 'assets'
export type AssetsTab = 'project' | 'global'

export function normalizeOperationsTab(raw: string | null): OperationsTab {
  return raw === 'assets' ? 'assets' : 'costs'
}

interface UseOperationsDataOptions {
  activeTab: OperationsTab
  notifyError: (message: string) => void
}

export default function useOperationsData({ activeTab, notifyError }: UseOperationsDataOptions) {
  const { projects, fetchProjects, loading: projectLoading } = useProjectStore()
  const notifyErrorRef = useRef(notifyError)

  const [projectId, setProjectId] = useState<string | null>(null)
  const [assetsTab, setAssetsTab] = useState<AssetsTab>('project')

  const [costLoading, setCostLoading] = useState(false)
  const [costPayload, setCostPayload] = useState<CostListPayload | null>(null)
  const [costError, setCostError] = useState<string | null>(null)

  const [assetsLoading, setAssetsLoading] = useState(false)
  const [assetsPayload, setAssetsPayload] = useState<ProjectAssetsPayload | null>(null)
  const [assetsError, setAssetsError] = useState<string | null>(null)

  const [globalAssetsLoading, setGlobalAssetsLoading] = useState(false)
  const [globalAssetsPayload, setGlobalAssetsPayload] = useState<AssetHubOverview | null>(null)
  const [globalAssetsError, setGlobalAssetsError] = useState<string | null>(null)

  useEffect(() => {
    notifyErrorRef.current = notifyError
  }, [notifyError])

  useEffect(() => {
    fetchProjects({ page: 1, pageSize: 50 }).catch((error) => {
      notifyErrorRef.current(getApiErrorMessage(error, '加载项目失败'))
    })
  }, [fetchProjects])

  useEffect(() => {
    if (!projectId && projects.length > 0) {
      setProjectId(projects[0]?.id ?? null)
    }
  }, [projectId, projects])

  const projectOptions = useMemo(
    () => projects.map((item) => ({ label: item.name, value: item.id })),
    [projects],
  )

  const loadCosts = useCallback(async (id: string) => {
    setCostLoading(true)
    try {
      const data = await getProjectCosts(id, 300)
      setCostPayload(data)
      setCostError(null)
    } catch (error) {
      setCostPayload(null)
      setCostError(getApiErrorMessage(error, '加载成本统计失败'))
    } finally {
      setCostLoading(false)
    }
  }, [])

  const loadProjectAssets = useCallback(async (id: string) => {
    setAssetsLoading(true)
    try {
      const data = await getProjectAssets(id)
      const projectName = projects.find((item) => item.id === id)?.name
      if (projectName && data.project_name === id) {
        data.project_name = projectName
      }
      setAssetsPayload(data)
      setAssetsError(null)
    } catch (error) {
      setAssetsPayload(null)
      setAssetsError(getApiErrorMessage(error, '获取媒体资产失败'))
    } finally {
      setAssetsLoading(false)
    }
  }, [projects])

  const loadGlobalAssets = useCallback(async () => {
    setGlobalAssetsLoading(true)
    try {
      const data = await getAssetHubOverview()
      setGlobalAssetsPayload(data)
      setGlobalAssetsError(null)
    } catch (error) {
      setGlobalAssetsPayload(null)
      setGlobalAssetsError(getApiErrorMessage(error, '获取全局资产失败'))
    } finally {
      setGlobalAssetsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!projectId) return
    void loadCosts(projectId)
    void loadProjectAssets(projectId)
  }, [projectId, loadCosts, loadProjectAssets])

  useEffect(() => {
    void loadGlobalAssets()
  }, [loadGlobalAssets])

  const refreshCurrent = useCallback(() => {
    if (activeTab === 'costs') {
      if (projectId) {
        void loadCosts(projectId)
      }
      return
    }

    if (assetsTab === 'project') {
      if (projectId) {
        void loadProjectAssets(projectId)
      }
      return
    }

    void loadGlobalAssets()
  }, [activeTab, assetsTab, loadCosts, loadGlobalAssets, loadProjectAssets, projectId])

  return {
    projectLoading,
    projectId,
    setProjectId,
    projectOptions,
    assetsTab,
    setAssetsTab,
    costLoading,
    costPayload,
    costError,
    assetsLoading,
    assetsPayload,
    assetsError,
    globalAssetsLoading,
    globalAssetsPayload,
    globalAssetsError,
    refreshCurrent,
  }
}
