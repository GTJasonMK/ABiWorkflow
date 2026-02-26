import { useCallback, useEffect, useMemo, useState } from 'react'
import { App as AntdApp, Button, Card, Collapse, Empty, Select, Space, Spin, Tag, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useProjectStore } from '../../stores/projectStore'
import { getProjectAssets, type ProjectAssetsPayload } from '../../api/assets'
import PageHeader from '../../components/PageHeader'
import { getApiErrorMessage } from '../../utils/error'

const { Text } = Typography

export default function AssetsLibrary() {
  const { projects, fetchProjects } = useProjectStore()
  const { message } = AntdApp.useApp()
  const [projectId, setProjectId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [payload, setPayload] = useState<ProjectAssetsPayload | null>(null)

  useEffect(() => {
    fetchProjects({ page: 1 }).catch((error) => {
      message.error(getApiErrorMessage(error, '加载项目失败'))
    })
  }, [fetchProjects, message])

  useEffect(() => {
    if (!projectId && projects.length > 0) {
      const firstProject = projects[0]
      if (firstProject) {
        setProjectId(firstProject.id)
      }
    }
  }, [projects, projectId])

  const loadAssets = useCallback(async (id: string) => {
    setLoading(true)
    try {
      const data = await getProjectAssets(id)
      const projectName = projects.find((item) => item.id === id)?.name
      if (projectName && data.project_name === id) {
        data.project_name = projectName
      }
      setPayload(data)
      setError(null)
    } catch (err) {
      setError(getApiErrorMessage(err, '获取媒体资产失败'))
      setPayload(null)
    } finally {
      setLoading(false)
    }
  }, [projects])

  useEffect(() => {
    if (projectId) {
      void loadAssets(projectId)
    }
  }, [projectId, loadAssets])

  const projectOptions = useMemo(
    () => projects.map((item) => ({ label: item.name, value: item.id })),
    [projects],
  )

  if (!projectId && projects.length === 0) {
    return (
      <section className="np-page">
        <PageHeader
          kicker="媒体资源"
          title="媒体资产库"
          subtitle="集中查看生成片段和成片输出。"
        />
        <div className="np-page-scroll">
          <Card className="np-panel-card">
            <Empty description="暂无项目，请先创建并生成视频。" />
          </Card>
        </div>
      </section>
    )
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="媒体资源"
        title="媒体资产库"
        subtitle="按项目查看场景片段和合成结果，支持直接预览与下载。"
        actions={(
          <Space>
            <Select
              style={{ minWidth: 220 }}
              placeholder="选择项目"
              value={projectId ?? undefined}
              options={projectOptions}
              onChange={setProjectId}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                if (projectId) void loadAssets(projectId)
              }}
            >
              刷新资产
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
        {loading ? (
          <div className="np-page-loading">
            <Spin size="large" />
          </div>
        ) : error ? (
          <Card className="np-panel-card">
            <Text className="np-task-error">{error}</Text>
          </Card>
        ) : payload ? (
          <>
            <div className="np-kpi-grid">
              <article className="np-kpi-card">
                <p className="np-kpi-label">场景数</p>
                <p className="np-kpi-value">{payload.summary.scene_count}</p>
              </article>
              <article className="np-kpi-card">
                <p className="np-kpi-label">片段总数</p>
                <p className="np-kpi-value">{payload.summary.clip_count}</p>
              </article>
              <article className="np-kpi-card">
                <p className="np-kpi-label">可用成片</p>
                <p className="np-kpi-value">{payload.summary.composition_count}</p>
              </article>
            </div>

            <Card title="合成成片" className="np-panel-card">
              {payload.compositions.length === 0 ? (
                <Empty description="暂无合成成片" />
              ) : (
                <div className="np-asset-grid">
                  {payload.compositions.map((item) => {
                    const src = item.media_url || item.download_url
                    return (
                      <Card
                        key={item.id}
                        size="small"
                        title={`成片 ${item.id.slice(0, 8)}`}
                        extra={<Tag className={`np-status-tag np-status-${item.status}`}>{item.status}</Tag>}
                      >
                        {src ? (
                          <video
                            controls
                            preload="metadata"
                            className="np-asset-video"
                            src={src}
                          />
                        ) : (
                          <Text type="secondary">文件暂不可用</Text>
                        )}
                        <Space wrap style={{ marginTop: 10 }}>
                          <Tag className="np-status-tag">转场 {item.transition_type}</Tag>
                          {item.include_subtitles && <Tag className="np-status-tag">字幕</Tag>}
                          {item.include_tts && <Tag className="np-status-tag">配音</Tag>}
                        </Space>
                        <div style={{ marginTop: 8 }}>
                          <a href={item.download_url} target="_blank" rel="noreferrer">下载成片</a>
                        </div>
                      </Card>
                    )
                  })}
                </div>
              )}
            </Card>

            <Card title="场景片段" className="np-panel-card">
              <Collapse
                items={payload.scenes.map((scene) => ({
                  key: scene.scene_id,
                  label: (
                    <Space>
                      <Text>场景 {scene.sequence_order + 1} · {scene.title}</Text>
                      <Tag className={`np-status-tag np-status-${scene.status}`}>{scene.status}</Tag>
                      <Text type="secondary">片段 {scene.clips.length}</Text>
                    </Space>
                  ),
                  children: scene.clips.length === 0 ? (
                    <Empty description="该场景暂无生成片段" />
                  ) : (
                    <div className="np-asset-grid">
                      {scene.clips.map((clip) => (
                        <Card
                          key={clip.id}
                          size="small"
                          title={`片段 ${clip.clip_order + 1}`}
                          extra={<Tag className={`np-status-tag np-status-${clip.status}`}>{clip.status}</Tag>}
                        >
                          {clip.media_url ? (
                            <video
                              controls
                              preload="metadata"
                              className="np-asset-video"
                              src={clip.media_url}
                            />
                          ) : (
                            <Text type="secondary">片段文件不可用</Text>
                          )}
                          <div style={{ marginTop: 8 }}>
                            <Text type="secondary">时长：{clip.duration_seconds.toFixed(1)} 秒</Text>
                          </div>
                          {clip.error_message && (
                            <div style={{ marginTop: 8 }}>
                              <Text className="np-task-error">{clip.error_message}</Text>
                            </div>
                          )}
                        </Card>
                      ))}
                    </div>
                  ),
                }))}
              />
            </Card>
          </>
        ) : (
          <Card className="np-panel-card">
            <Empty description="暂无资产数据" />
          </Card>
        )}
      </div>
    </section>
  )
}
