import { useEffect, useMemo, useState } from 'react'
import { App as AntdApp, Spin } from 'antd'
import { useEpisodePanels } from './useEpisodePanels'
import { useAssetBinding } from './useAssetBinding'
import PanelListPanel from './PanelListPanel'
import PanelEditDrawer from './PanelEditDrawer'
import BindPreviewModal from './BindPreviewModal'
import AssetBindingDrawer from './AssetBindingDrawer'
import { listProviderConfigs } from '../../api/providers'
import type { ProviderConfig } from '../../types/provider'
import { resolveVideoProviderAllowedLengths } from '../../utils/providerConstraints'
import { getApiErrorMessage } from '../../utils/error'

interface EpisodePanelBoardProps {
  projectId: string
  initialEpisodeId?: string | null
  onEpisodeChange?: (episodeId: string | null) => void
  lockedEpisodeId?: string | null
}

export default function EpisodePanelBoard({
  projectId,
  initialEpisodeId = null,
  onEpisodeChange,
  lockedEpisodeId = null,
}: EpisodePanelBoardProps) {
  const { message } = AntdApp.useApp()
  const ep = useEpisodePanels(projectId, initialEpisodeId, onEpisodeChange, lockedEpisodeId)
  const asset = useAssetBinding(projectId, ep.panelsByEpisode, ep.replacePanel)
  const [providerConfigs, setProviderConfigs] = useState<ProviderConfig[]>([])

  useEffect(() => {
    listProviderConfigs()
      .then((rows) => setProviderConfigs(rows))
      .catch((error) => {
        message.error(getApiErrorMessage(error, '加载 Provider 配置失败'))
      })
  }, [message])

  const allowedDurations = useMemo(
    () => resolveVideoProviderAllowedLengths(providerConfigs, ep.activeEpisode?.video_provider_key),
    [ep.activeEpisode?.video_provider_key, providerConfigs],
  )

  if (ep.loading) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div className="np-storyboard-editor-layout">
      <PanelListPanel
        activeEpisodeId={ep.activeEpisodeId}
        activeEpisodeTitle={ep.activeEpisode?.title ?? '当前分集'}
        activePanels={ep.activePanels}
        selectedPanelId={ep.selectedPanelId}
        newPanelTitle={ep.newPanelTitle}
        generating={ep.panelGenerating}
        onNewPanelTitleChange={ep.setNewPanelTitle}
        onCreatePanel={() => { void ep.handleCreatePanel() }}
        onSelectPanel={(panel) => ep.selectPanel(panel.id)}
        onDeletePanel={(panel) => { void ep.handleDeletePanel(panel) }}
        onReorderPanels={(panelIds) => { void ep.handleReorderPanels(panelIds) }}
        onOpenAssetDrawer={(panel, tab) => { void asset.openAssetDrawer(panel, tab) }}
        onGeneratePanels={() => { void ep.handleGeneratePanels() }}
      />

      <PanelEditDrawer
        panel={ep.selectedPanel}
        draft={ep.panelEditDraft}
        dirty={ep.panelEditDirty}
        saving={ep.panelEditSaving}
        videoProviderKey={ep.activeEpisode?.video_provider_key ?? null}
        allowedDurations={allowedDurations}
        onDraftChange={ep.setPanelEditDraft}
        onSave={() => { void ep.handleSavePanelDetail() }}
        onDelete={(panel) => { void ep.handleDeletePanel(panel) }}
        onOpenAssetDrawer={(panel, tab) => { void asset.openAssetDrawer(panel, tab) }}
      />

      <BindPreviewModal
        bindPreview={asset.bindPreview}
        previewDiffOnly={asset.previewDiffOnly}
        saving={asset.assetSaving}
        onPreviewDiffOnlyChange={asset.setPreviewDiffOnly}
        onConfirm={() => { void asset.handleConfirmBindPreview() }}
        onCancel={() => {
          asset.setBindPreview(null)
          asset.setPreviewDiffOnly(true)
        }}
      />

      <AssetBindingDrawer
        projectId={projectId}
        asset={asset}
      />
    </div>
  )
}
