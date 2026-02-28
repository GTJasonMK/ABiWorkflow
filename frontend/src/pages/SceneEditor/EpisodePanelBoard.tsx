import { useCallback, useEffect, useMemo, useState } from 'react'
import { App as AntdApp, Button, Card, Empty, Input, List, Modal, Popconfirm, Space, Spin, Tag, Typography } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import type { Episode } from '../../types/episode'
import type { Panel } from '../../types/panel'
import { createEpisode, deleteEpisode, listEpisodes, reorderEpisodes, updateEpisode } from '../../api/episodes'
import { createPanel, deletePanel, listEpisodePanels, reorderPanels, updatePanel } from '../../api/panels'
import { getApiErrorMessage } from '../../utils/error'

const { Text } = Typography

interface EpisodePanelBoardProps {
  projectId: string
}

function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items]
  const [picked] = next.splice(from, 1)
  next.splice(to, 0, picked!)
  return next
}

export default function EpisodePanelBoard({ projectId }: EpisodePanelBoardProps) {
  const { message } = AntdApp.useApp()
  const [loading, setLoading] = useState(false)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [panelsByEpisode, setPanelsByEpisode] = useState<Record<string, Panel[]>>({})
  const [activeEpisodeId, setActiveEpisodeId] = useState<string | null>(null)
  const [newEpisodeTitle, setNewEpisodeTitle] = useState('')
  const [newPanelTitle, setNewPanelTitle] = useState('')
  const [renameTarget, setRenameTarget] = useState<
    { type: 'episode'; payload: Episode } | { type: 'panel'; payload: Panel } | null
  >(null)
  const [renameValue, setRenameValue] = useState('')

  const activePanels = useMemo(
    () => (activeEpisodeId ? (panelsByEpisode[activeEpisodeId] ?? []) : []),
    [activeEpisodeId, panelsByEpisode],
  )

  const loadPanels = useCallback(async (episodeId: string) => {
    const rows = await listEpisodePanels(episodeId)
    setPanelsByEpisode((prev) => ({ ...prev, [episodeId]: rows }))
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const rows = await listEpisodes(projectId)
      setEpisodes(rows)
      const firstId = rows[0]?.id ?? null
      setActiveEpisodeId((prev) => {
        if (prev && rows.some((item) => item.id === prev)) return prev
        return firstId
      })
      if (firstId) {
        await loadPanels(firstId)
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载分集失败'))
    } finally {
      setLoading(false)
    }
  }, [loadPanels, message, projectId])

  useEffect(() => {
    void reload()
  }, [reload])

  const handleSelectEpisode = async (episodeId: string) => {
    setActiveEpisodeId(episodeId)
    if (!panelsByEpisode[episodeId]) {
      try {
        await loadPanels(episodeId)
      } catch (error) {
        message.error(getApiErrorMessage(error, '加载分镜失败'))
      }
    }
  }

  const handleCreateEpisode = async () => {
    const title = newEpisodeTitle.trim()
    if (!title) {
      message.warning('请输入分集标题')
      return
    }
    try {
      const created = await createEpisode(projectId, { title })
      setEpisodes((prev) => [...prev, created].sort((a, b) => a.episode_order - b.episode_order))
      setActiveEpisodeId(created.id)
      setPanelsByEpisode((prev) => ({ ...prev, [created.id]: [] }))
      setNewEpisodeTitle('')
      message.success('已创建分集')
    } catch (error) {
      message.error(getApiErrorMessage(error, '创建分集失败'))
    }
  }

  const openRenameEpisode = (episode: Episode) => {
    setRenameTarget({ type: 'episode', payload: episode })
    setRenameValue(episode.title)
  }

  const handleDeleteEpisode = async (episodeId: string) => {
    try {
      await deleteEpisode(episodeId)
      setEpisodes((prev) => prev.filter((item) => item.id !== episodeId))
      setPanelsByEpisode((prev) => {
        const next = { ...prev }
        delete next[episodeId]
        return next
      })
      if (activeEpisodeId === episodeId) {
        const remain = episodes.filter((item) => item.id !== episodeId)
        setActiveEpisodeId(remain[0]?.id ?? null)
      }
      message.success('已删除分集')
    } catch (error) {
      message.error(getApiErrorMessage(error, '删除分集失败'))
    }
  }

  const handleMoveEpisode = async (from: number, to: number) => {
    const reordered = moveItem(episodes, from, to)
    setEpisodes(reordered.map((item, index) => ({ ...item, episode_order: index })))
    try {
      await reorderEpisodes(projectId, reordered.map((item) => item.id))
    } catch (error) {
      message.error(getApiErrorMessage(error, '分集排序失败'))
      void reload()
    }
  }

  const handleCreatePanel = async () => {
    if (!activeEpisodeId) return
    const title = newPanelTitle.trim()
    if (!title) {
      message.warning('请输入分镜标题')
      return
    }
    try {
      const created = await createPanel(activeEpisodeId, { title })
      setPanelsByEpisode((prev) => ({
        ...prev,
        [activeEpisodeId]: [...(prev[activeEpisodeId] ?? []), created].sort((a, b) => a.panel_order - b.panel_order),
      }))
      setEpisodes((prev) => prev.map((item) => (
        item.id === activeEpisodeId ? { ...item, panel_count: item.panel_count + 1 } : item
      )))
      setNewPanelTitle('')
      message.success('已创建分镜')
    } catch (error) {
      message.error(getApiErrorMessage(error, '创建分镜失败'))
    }
  }

  const openRenamePanel = (panel: Panel) => {
    setRenameTarget({ type: 'panel', payload: panel })
    setRenameValue(panel.title)
  }

  const handleConfirmRename = async () => {
    const target = renameTarget
    if (!target) return
    const nextTitle = renameValue.trim()
    if (!nextTitle) {
      message.warning('名称不能为空')
      return
    }

    if (target.type === 'episode') {
      const episode = target.payload
      if (nextTitle === episode.title) {
        setRenameTarget(null)
        return
      }
      try {
        const updated = await updateEpisode(episode.id, { title: nextTitle })
        setEpisodes((prev) => prev.map((item) => (item.id === episode.id ? updated : item)))
        setRenameTarget(null)
      } catch (error) {
        message.error(getApiErrorMessage(error, '重命名分集失败'))
      }
      return
    }

    const panel = target.payload
    if (nextTitle === panel.title) {
      setRenameTarget(null)
      return
    }
    try {
      const updated = await updatePanel(panel.id, { title: nextTitle })
      setPanelsByEpisode((prev) => ({
        ...prev,
        [panel.episode_id]: (prev[panel.episode_id] ?? []).map((item) => (item.id === panel.id ? updated : item)),
      }))
      setRenameTarget(null)
    } catch (error) {
      message.error(getApiErrorMessage(error, '重命名分镜失败'))
    }
  }

  const handleDeletePanel = async (panel: Panel) => {
    try {
      await deletePanel(panel.id)
      setPanelsByEpisode((prev) => ({
        ...prev,
        [panel.episode_id]: (prev[panel.episode_id] ?? []).filter((item) => item.id !== panel.id),
      }))
      setEpisodes((prev) => prev.map((item) => (
        item.id === panel.episode_id ? { ...item, panel_count: Math.max(0, item.panel_count - 1) } : item
      )))
      message.success('已删除分镜')
    } catch (error) {
      message.error(getApiErrorMessage(error, '删除分镜失败'))
    }
  }

  const handleMovePanel = async (from: number, to: number) => {
    if (!activeEpisodeId) return
    const current = activePanels
    const reordered = moveItem(current, from, to)
    setPanelsByEpisode((prev) => ({
      ...prev,
      [activeEpisodeId]: reordered.map((item, idx) => ({ ...item, panel_order: idx })),
    }))
    try {
      await reorderPanels(activeEpisodeId, reordered.map((item) => item.id))
    } catch (error) {
      message.error(getApiErrorMessage(error, '分镜排序失败'))
      await loadPanels(activeEpisodeId)
    }
  }

  if (loading) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div className="np-scene-editor-layout">
      <section className="np-scene-column np-scene-column-main">
        <Card
          title="分集列表"
          className="np-panel-card"
          styles={{ body: { display: 'flex', flexDirection: 'column', gap: 12 } }}
        >
          <Space.Compact>
            <Input
              value={newEpisodeTitle}
              onChange={(event) => setNewEpisodeTitle(event.target.value)}
              placeholder="新分集标题，例如：第1集 开场"
              onPressEnter={() => void handleCreateEpisode()}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => void handleCreateEpisode()}>
              新增分集
            </Button>
          </Space.Compact>

          {episodes.length === 0 ? (
            <Empty description="暂无分集，请先创建" />
          ) : (
            <List
              dataSource={episodes}
              renderItem={(episode, index) => (
                <List.Item
                  style={{
                    cursor: 'pointer',
                    border: activeEpisodeId === episode.id ? '1px solid #111' : undefined,
                    padding: 12,
                  }}
                  onClick={() => void handleSelectEpisode(episode.id)}
                  actions={[
                    <Button
                      key="up"
                      size="small"
                      icon={<ArrowUpOutlined />}
                      disabled={index === 0}
                      onClick={(event) => {
                        event.stopPropagation()
                        void handleMoveEpisode(index, index - 1)
                      }}
                    />,
                    <Button
                      key="down"
                      size="small"
                      icon={<ArrowDownOutlined />}
                      disabled={index === episodes.length - 1}
                      onClick={(event) => {
                        event.stopPropagation()
                        void handleMoveEpisode(index, index + 1)
                      }}
                    />,
                    <Button
                      key="edit"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(event) => {
                        event.stopPropagation()
                        openRenameEpisode(episode)
                      }}
                    />,
                    <Popconfirm
                      key="delete"
                      title="确认删除该分集？"
                      onConfirm={() => void handleDeleteEpisode(episode.id)}
                    >
                      <Button
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(event) => event.stopPropagation()}
                      />
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={episode.title}
                    description={(
                      <Space size={8}>
                        <Text type="secondary">顺序 #{episode.episode_order + 1}</Text>
                        <Tag className="np-status-tag">{episode.status}</Tag>
                        <Text type="secondary">分镜 {episode.panel_count}</Text>
                      </Space>
                    )}
                  />
                </List.Item>
              )}
            />
          )}
        </Card>
      </section>

      <aside className="np-scene-column np-scene-column-side">
        <Card
          title={activeEpisodeId ? `分镜列表（${episodes.find((item) => item.id === activeEpisodeId)?.title ?? ''}）` : '分镜列表'}
          className="np-panel-card"
          styles={{ body: { display: 'flex', flexDirection: 'column', gap: 12 } }}
        >
          {!activeEpisodeId ? (
            <Empty description="请先选择分集" />
          ) : (
            <>
              <Space.Compact>
                <Input
                  value={newPanelTitle}
                  onChange={(event) => setNewPanelTitle(event.target.value)}
                  placeholder="新分镜标题"
                  onPressEnter={() => void handleCreatePanel()}
                />
                <Button type="primary" icon={<PlusOutlined />} onClick={() => void handleCreatePanel()}>
                  新增分镜
                </Button>
              </Space.Compact>

              {activePanels.length === 0 ? (
                <Empty description="暂无分镜，请新增" />
              ) : (
                <List
                  dataSource={activePanels}
                  renderItem={(panel, index) => (
                    <List.Item
                      actions={[
                        <Button
                          key="up"
                          size="small"
                          icon={<ArrowUpOutlined />}
                          disabled={index === 0}
                          onClick={() => void handleMovePanel(index, index - 1)}
                        />,
                        <Button
                          key="down"
                          size="small"
                          icon={<ArrowDownOutlined />}
                          disabled={index === activePanels.length - 1}
                          onClick={() => void handleMovePanel(index, index + 1)}
                        />,
                        <Button
                          key="edit"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => openRenamePanel(panel)}
                        />,
                        <Popconfirm
                          key="delete"
                          title="确认删除该分镜？"
                          onConfirm={() => void handleDeletePanel(panel)}
                        >
                          <Button size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>,
                      ]}
                    >
                      <List.Item.Meta
                        title={`${panel.panel_order + 1}. ${panel.title}`}
                        description={(
                          <Space size={8}>
                            <Tag className="np-status-tag">{panel.status}</Tag>
                            <Text type="secondary">{panel.duration_seconds.toFixed(1)} 秒</Text>
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              )}
            </>
          )}
        </Card>
      </aside>

      <Modal
        title={renameTarget?.type === 'episode' ? '重命名分集' : '重命名分镜'}
        open={!!renameTarget}
        onOk={() => void handleConfirmRename()}
        onCancel={() => setRenameTarget(null)}
        okText="确认"
        cancelText="取消"
      >
        <Input
          value={renameValue}
          onChange={(event) => setRenameValue(event.target.value)}
          onPressEnter={() => void handleConfirmRename()}
          placeholder="请输入名称"
          autoFocus
        />
      </Modal>
    </div>
  )
}
