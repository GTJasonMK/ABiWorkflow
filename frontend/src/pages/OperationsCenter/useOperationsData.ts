import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getProjectAssets, type ProjectAssetsPayload } from '../../api/assets'
import { getProjectCosts } from '../../api/costs'
import { useProjectStore } from '../../stores/projectStore'
import { useAssetHubStore } from '../../stores/assetHubStore'
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

  const [costProjectId, setCostProjectId] = useState<string | null>(null)
  const [assetsProjectId, setAssetsProjectId] = useState<string | null>(null)
  const [assetsTab, setAssetsTab] = useState<AssetsTab>('project')

  const [costLoading, setCostLoading] = useState(false)
  const [costPayload, setCostPayload] = useState<CostListPayload | null>(null)
  const [costError, setCostError] = useState<string | null>(null)

  const [assetsLoading, setAssetsLoading] = useState(false)
  const [assetsPayload, setAssetsPayload] = useState<ProjectAssetsPayload | null>(null)
  const [assetsError, setAssetsError] = useState<string | null>(null)
  const globalAssetsLoading = useAssetHubStore((state) => state.loading)
  const globalAssetsPayload = useAssetHubStore((state) => state.overview)
  const globalAssetsError = useAssetHubStore((state) => state.error)
  const loadGlobalAssets = useAssetHubStore((state) => state.loadOverview)

  useEffect(() => {
    notifyErrorRef.current = notifyError
  }, [notifyError])

  useEffect(() => {
    fetchProjects({ page: 1, pageSize: 50 }).catch((error) => {
      notifyErrorRef.current(getApiErrorMessage(error, '加载项目失败'))
    })
  }, [fetchProjects])

  useEffect(() => {
    if (projects.length === 0) {
      setCostProjectId(null)
      setAssetsProjectId(null)
      return
    }

    const firstProjectId = projects[0]?.id ?? null
    setCostProjectId((prev) => (prev && projects.some((item) => item.id === prev) ? prev : firstProjectId))
    setAssetsProjectId((prev) => (prev && projects.some((item) => item.id === prev) ? prev : firstProjectId))
  }, [projects])

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

  useEffect(() => {
    if (!costProjectId) return
    void loadCosts(costProjectId)
  }, [costProjectId, loadCosts])

  useEffect(() => {
    if (!assetsProjectId) return
    void loadProjectAssets(assetsProjectId)
  }, [assetsProjectId, loadProjectAssets])

  useEffect(() => {
    loadGlobalAssets().catch((error) => {
      notifyErrorRef.current(getApiErrorMessage(error, '获取全局资产失败'))
    })
  }, [loadGlobalAssets])

  const refreshCurrent = useCallback(() => {
    if (activeTab === 'costs') {
      if (costProjectId) {
        void loadCosts(costProjectId)
      }
      return
    }

    if (assetsTab === 'project') {
      if (assetsProjectId) {
        void loadProjectAssets(assetsProjectId)
      }
      return
    }

    loadGlobalAssets({ force: true }).catch((error) => {
      notifyErrorRef.current(getApiErrorMessage(error, '获取全局资产失败'))
    })
  }, [activeTab, assetsProjectId, assetsTab, costProjectId, loadCosts, loadGlobalAssets, loadProjectAssets])

  return {
    projectLoading,
    costProjectId,
    setCostProjectId,
    assetsProjectId,
    setAssetsProjectId,
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
