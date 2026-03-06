import { Spin } from 'antd'
import { useEpisodePanels } from './useEpisodePanels'
import { useAssetBinding } from './useAssetBinding'
import EpisodeListPanel from './EpisodeListPanel'
import PanelListPanel from './PanelListPanel'
import PanelEditDrawer from './PanelEditDrawer'
import BindPreviewModal from './BindPreviewModal'
import AssetBindingDrawer from './AssetBindingDrawer'

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
  const ep = useEpisodePanels(projectId, initialEpisodeId, onEpisodeChange, lockedEpisodeId)
  const asset = useAssetBinding(projectId, ep.panelsByEpisode, ep.replacePanel)
  const visibleEpisodes = lockedEpisodeId
    ? ep.episodes.filter((episode) => episode.id === lockedEpisodeId)
    : ep.episodes

  if (ep.loading) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div className="np-scene-editor-layout">
      <EpisodeListPanel
        episodes={visibleEpisodes}
        activeEpisodeId={ep.activeEpisodeId}
        lockedEpisodeId={lockedEpisodeId}
        onSelectEpisode={(id) => { void ep.handleSelectEpisode(id) }}
      />

      <PanelListPanel
        episodes={visibleEpisodes}
        activeEpisodeId={ep.activeEpisodeId}
        activePanels={ep.activePanels}
        newPanelTitle={ep.newPanelTitle}
        onNewPanelTitleChange={ep.setNewPanelTitle}
        onCreatePanel={() => { void ep.handleCreatePanel() }}
        onEditPanel={ep.openPanelEditor}
        onDeletePanel={(panel) => { void ep.handleDeletePanel(panel) }}
        onBatchDeletePanels={(panels) => { void ep.handleBatchDeletePanels(panels) }}
        onReorderPanels={(panelIds) => { void ep.handleReorderPanels(panelIds) }}
        onOpenAssetDrawer={(panel, tab) => { void asset.openAssetDrawer(panel, tab) }}
      />

      <PanelEditDrawer
        open={Boolean(ep.editingPanel && ep.panelEditDraft)}
        title={ep.editingPanel ? `编辑分镜详情 · ${ep.editingPanel.title}` : '编辑分镜详情'}
        draft={ep.panelEditDraft}
        saving={ep.panelEditSaving}
        onDraftChange={ep.setPanelEditDraft}
        onSave={() => { void ep.handleSavePanelDetail() }}
        onClose={ep.closePanelEditor}
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
