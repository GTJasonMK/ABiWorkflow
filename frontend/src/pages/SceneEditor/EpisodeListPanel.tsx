import { Card, Empty, Tag } from 'antd'
import type { Episode } from '../../types/episode'
import PanelStatusTag from '../../components/PanelStatusTag'

interface EpisodeListPanelProps {
  episodes: Episode[]
  activeEpisodeId: string | null
  lockedEpisodeId?: string | null
  onSelectEpisode: (episodeId: string) => void
}

export default function EpisodeListPanel({
  episodes,
  activeEpisodeId,
  lockedEpisodeId = null,
  onSelectEpisode,
}: EpisodeListPanelProps) {
  return (
    <section className="np-scene-column np-scene-column-side">
      <Card
        title={`分集 (${episodes.length})`}
        extra={<Tag className="np-status-tag">只读</Tag>}
        className="np-panel-card np-scene-episode-card"
        styles={{ body: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: 0 } }}
      >
        {episodes.length === 0 ? (
          <div style={{ padding: 16 }}>
            <Empty description="暂无分集，请先在剧本编辑页完成分集导入或切分" />
          </div>
        ) : (
          <div className="np-episode-list-scroll">
            {episodes.map((episode) => {
              const active = activeEpisodeId === episode.id
              const locked = Boolean(lockedEpisodeId && episode.id !== lockedEpisodeId)
              return (
                <button
                  key={episode.id}
                  type="button"
                  className={`np-episode-item${active ? ' is-active' : ''}${locked ? ' is-locked' : ''}`}
                  onClick={() => {
                    if (locked) return
                    onSelectEpisode(episode.id)
                  }}
                  disabled={locked}
                  role="option"
                  aria-selected={active}
                  aria-label={`${episode.title}，${episode.panel_count} 个分镜${locked ? '（当前步骤已锁定）' : ''}`}
                >
                  <span className="np-episode-item-indicator" />
                  <span className="np-episode-item-body">
                    <span className="np-episode-item-title">{episode.title}</span>
                    <span className="np-episode-item-meta">
                      <PanelStatusTag status={episode.status} />
                      <span>{episode.panel_count} 镜</span>
                      {locked ? <span>已锁定</span> : null}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </Card>
    </section>
  )
}
