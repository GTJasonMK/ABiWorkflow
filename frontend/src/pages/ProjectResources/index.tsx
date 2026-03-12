import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { App as AntdApp, Button, Card, Empty, Image, Space, Spin, Tabs, Tag, Typography } from 'antd'
import { ArrowRightOutlined, ReloadOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import ProjectSectionNav from '../../components/ProjectSectionNav'
import { useProjectWorkspace } from '../../hooks/useProjectWorkspace'
import { getAssetHubOverview } from '../../api/assetHub'
import { getProjectAssets } from '../../api/assets'
import { listScriptEntities } from '../../api/scriptAssets'
import { getApiErrorMessage } from '../../utils/error'
import type { AssetHubOverview, GlobalCharacterAsset, GlobalLocationAsset, GlobalVoice } from '../../types/assetHub'
import type { ProjectWorkspace } from '../../types/project'
import type { Episode } from '../../types/episode'
import type { ScriptEntity } from '../../types/scriptAssets'

const { Paragraph, Text, Title } = Typography

function resolveRecommendedBindingPath(
  projectId: string,
  workspace: ProjectWorkspace | null,
): string {
  const targetEpisode = workspace?.episodes.find((item) => item.workflow_summary.current_step === 'assets')
    ?? workspace?.episodes[0]
    ?? null
  if (!targetEpisode) return `/projects/${projectId}/script`
  return `/projects/${projectId}/assets/${targetEpisode.id}`
}

function buildAssetBindingCountMap(entities: ScriptEntity[]) {
  const countMap = new Map<string, Set<string>>()
  entities.forEach((entity) => {
    entity.bindings.forEach((binding) => {
      const key = `${binding.asset_type}:${binding.asset_id}`
      const entityIds = countMap.get(key) ?? new Set<string>()
      entityIds.add(entity.id)
      countMap.set(key, entityIds)
    })
  })
  return countMap
}

function getEpisodeReference(episodes: Episode[], episodeId?: string | null): string {
  if (!episodeId) return '项目级'
  const hit = episodes.find((item) => item.id === episodeId)
  return hit?.title ?? '指定分集'
}

export default function ProjectResources() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()
  const { workspace, loading: workspaceLoading, refreshWorkspace } = useProjectWorkspace(projectId, '加载资源总览失败')
  const [loading, setLoading] = useState(false)
  const [overview, setOverview] = useState<AssetHubOverview | null>(null)
  const [entities, setEntities] = useState<ScriptEntity[]>([])
  const [projectAssets, setProjectAssets] = useState<Awaited<ReturnType<typeof getProjectAssets>> | null>(null)

  const loadData = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const [overviewRow, entityRows, assetRows] = await Promise.all([
        getAssetHubOverview({ projectId, scope: 'all' }),
        listScriptEntities(projectId),
        getProjectAssets(projectId),
      ])
      setOverview(overviewRow)
      setEntities(entityRows)
      setProjectAssets(assetRows)
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载资源总览失败'))
    } finally {
      setLoading(false)
    }
  }, [message, projectId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const bindingCountMap = useMemo(() => buildAssetBindingCountMap(entities), [entities])
  const pageLoading = loading || (workspaceLoading && !workspace)

  if (pageLoading) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  if (!projectId || !workspace) {
    return (
      <section className="np-page">
        <PageHeader
          kicker="资源总览"
          title="资源中心"
          subtitle="项目不存在或工作台数据加载失败。"
          onBack={() => navigate('/projects')}
          backLabel="返回项目列表"
        />
        <div className="np-page-scroll">
          <Card className="np-panel-card">
            <Empty description="未找到项目工作台数据" />
          </Card>
        </div>
      </section>
    )
  }

  const renderAssetCards = (
    rows: Array<GlobalCharacterAsset | GlobalLocationAsset>,
    assetType: 'character' | 'location',
  ) => {
    if (rows.length <= 0) {
      return <Empty description={`暂无${assetType === 'character' ? '角色' : '地点'}资产`} />
    }

    return (
      <div className="np-resource-card-grid">
        {rows.map((item) => {
          const boundCount = bindingCountMap.get(`${assetType}:${item.id}`)?.size ?? 0
          return (
            <article key={item.id} className="np-resource-card">
              {item.reference_image_url ? (
                <Image
                  src={item.reference_image_url}
                  alt={item.name}
                  className="np-resource-card-image"
                />
              ) : (
                <div className="np-resource-card-placeholder">暂无参考图</div>
              )}
              <div className="np-resource-card-body">
                <div className="np-resource-card-title-row">
                  <Title level={5} style={{ margin: 0 }}>{item.name}</Title>
                  <Tag className="np-status-tag">{item.project_id ? '项目专属' : '全局'}</Tag>
                </div>
                <Paragraph ellipsis={{ rows: 2 }} type="secondary">
                  {item.description || '暂无描述'}
                </Paragraph>
                <Space wrap size={8}>
                  <Tag className="np-status-tag">绑定实体 {boundCount}</Tag>
                  {item.prompt_template ? <Tag className="np-status-tag">含提示词模板</Tag> : null}
                </Space>
              </div>
            </article>
          )
        })}
      </div>
    )
  }

  const renderVoiceCards = (rows: GlobalVoice[]) => {
    if (rows.length <= 0) {
      return <Empty description="暂无声音资产" />
    }

    return (
      <div className="np-resource-card-grid">
        {rows.map((voice) => (
          <article key={voice.id} className="np-resource-card">
            <div className="np-resource-card-body">
              <div className="np-resource-card-title-row">
                <Title level={5} style={{ margin: 0 }}>{voice.name}</Title>
                <Tag className="np-status-tag">{voice.project_id ? '项目专属' : '全局'}</Tag>
              </div>
              <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                Provider：{voice.provider} · Voice Code：{voice.voice_code}
              </Paragraph>
              <Space wrap size={8}>
                {voice.language ? <Tag className="np-status-tag">{voice.language}</Tag> : null}
                {voice.gender ? <Tag className="np-status-tag">{voice.gender}</Tag> : null}
                {voice.style_prompt ? <Tag className="np-status-tag">含风格说明</Tag> : null}
              </Space>
              {voice.sample_audio_url ? (
                <audio style={{ width: '100%', marginTop: 12 }} controls src={voice.sample_audio_url}>
                  您的浏览器不支持试听。
                </audio>
              ) : (
                <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                  暂无试听样本
                </Paragraph>
              )}
            </div>
          </article>
        ))}
      </div>
    )
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="资源总览"
        title={`${workspace.project.name} · 资源中心`}
        subtitle="从项目级统一查看角色、地点、声音和媒体结果，再按需跳回具体分集处理。"
        onBack={() => {
          navigate(`/projects/${projectId}`)
        }}
        backLabel="返回项目总览"
        actions={(
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                void Promise.all([refreshWorkspace(), loadData()])
              }}
              loading={loading}
            >
              刷新
            </Button>
            <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => navigate(resolveRecommendedBindingPath(projectId, workspace))}>
              去绑定资源
            </Button>
          </Space>
        )}
      />

      {projectId ? <ProjectSectionNav projectId={projectId} /> : null}

      <div className="np-page-scroll">
        <Card className="np-panel-card" style={{ marginBottom: 12 }}>
          <Space wrap size={8}>
            <Tag className="np-status-tag">角色 {overview?.characters.length ?? 0}</Tag>
            <Tag className="np-status-tag">地点 {overview?.locations.length ?? 0}</Tag>
            <Tag className="np-status-tag">声音 {overview?.voices.length ?? 0}</Tag>
            <Tag className="np-status-tag np-status-generated">成片 {projectAssets?.summary.composition_count ?? 0}</Tag>
          </Space>
          <Paragraph type="secondary" style={{ marginTop: 10, marginBottom: 0 }}>
            当前可用资源范围包含全局资产与项目专属资产；绑定实体统计按当前项目内实体计算。
          </Paragraph>
        </Card>

        <Card className="np-panel-card">
          <Tabs
            items={[
              {
                key: 'character',
                label: `角色 (${overview?.characters.length ?? 0})`,
                children: renderAssetCards(overview?.characters ?? [], 'character'),
              },
              {
                key: 'location',
                label: `地点 (${overview?.locations.length ?? 0})`,
                children: renderAssetCards(overview?.locations ?? [], 'location'),
              },
              {
                key: 'voice',
                label: `声音 (${overview?.voices.length ?? 0})`,
                children: renderVoiceCards(overview?.voices ?? []),
              },
              {
                key: 'media',
                label: `媒体结果 (${projectAssets?.summary.composition_count ?? 0})`,
                children: projectAssets ? (
                  <div className="np-resource-media-panel">
                    <div className="np-workbench-stat-grid">
                      <article className="np-workbench-stat-card">
                        <span className="np-kpi-label">分镜片段</span>
                        <strong>{projectAssets.summary.panel_count}</strong>
                      </article>
                      <article className="np-workbench-stat-card">
                        <span className="np-kpi-label">视频候选</span>
                        <strong>{projectAssets.summary.ready_clip_count}/{projectAssets.summary.clip_count}</strong>
                      </article>
                      <article className="np-workbench-stat-card">
                        <span className="np-kpi-label">失败片段</span>
                        <strong>{projectAssets.summary.failed_clip_count}</strong>
                      </article>
                      <article className="np-workbench-stat-card">
                        <span className="np-kpi-label">已完成成片</span>
                        <strong>{projectAssets.summary.composition_count}</strong>
                      </article>
                    </div>
                    {projectAssets.compositions.length > 0 ? (
                      <div className="np-resource-card-grid" style={{ marginTop: 12 }}>
                        {projectAssets.compositions.map((item) => (
                          <article key={item.id} className="np-resource-card">
                            <div className="np-resource-card-body">
                              <div className="np-resource-card-title-row">
                                <Title level={5} style={{ margin: 0 }}>成片 {item.id.slice(0, 8)}</Title>
                                <Tag className={`np-status-tag${item.status === 'completed' ? ' np-status-generated' : ''}`}>
                                  {item.status}
                                </Tag>
                              </div>
                              <Paragraph type="secondary">
                                时长 {Number(item.duration_seconds || 0).toFixed(1)} 秒
                              </Paragraph>
                              <Paragraph type="secondary">
                                创建于 {new Date(item.created_at || '').toLocaleString('zh-CN')}
                              </Paragraph>
                              <Space wrap>
                                {item.media_url ? (
                                  <a href={item.media_url} target="_blank" rel="noreferrer">新窗口预览</a>
                                ) : null}
                                <a href={item.download_url} target="_blank" rel="noreferrer">下载文件</a>
                              </Space>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <Empty description="暂无成片结果" style={{ marginTop: 16 }} />
                    )}
                    {projectAssets.panels.length > 0 ? (
                      <Card size="small" className="np-panel-card" style={{ marginTop: 12 }}>
                        <Space direction="vertical" size={10} style={{ width: '100%' }}>
                          {projectAssets.panels.slice(0, 8).map((panel) => (
                            <div key={panel.panel_id} className="np-resource-media-row">
                              <div>
                                <Text strong>{panel.title}</Text>
                                <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                                  所属：{getEpisodeReference(workspace?.episodes ?? [], panel.episode_id)}
                                </Paragraph>
                              </div>
                              <Space wrap size={8}>
                                <Tag className="np-status-tag">候选 {panel.clips.length}</Tag>
                                <Tag className="np-status-tag">状态 {panel.status}</Tag>
                              </Space>
                            </div>
                          ))}
                        </Space>
                      </Card>
                    ) : null}
                  </div>
                ) : (
                  <Empty description="暂无媒体资产" />
                ),
              },
            ]}
          />
        </Card>
      </div>
    </section>
  )
}
