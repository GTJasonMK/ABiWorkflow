import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Empty, Space, Spin, Tag, Typography } from 'antd'
import { ArrowRightOutlined, EditOutlined, ReloadOutlined, UnorderedListOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import ProjectSectionNav from '../../components/ProjectSectionNav'
import { useProjectWorkspace } from '../../hooks/useProjectWorkspace'
import type { ProjectWorkspace } from '../../types/project'
import type { Episode } from '../../types/episode'
import { buildWorkflowStepPath, getWorkflowStepLabel, type WorkflowStepKey } from '../../utils/workflow'
import { STATUS_MAP } from '../../types/project'

const { Paragraph, Text, Title } = Typography

function buildEpisodeContinuePath(projectId: string, episode: Episode): string {
  const stepKey = (episode.workflow_summary.current_step || 'script') as WorkflowStepKey
  if (stepKey === 'script') {
    return `/projects/${projectId}/script?episode=${episode.id}&mode=edit`
  }
  return buildWorkflowStepPath(projectId, stepKey, episode.id)
}

function resolveProjectNextPath(projectId: string, workspace: ProjectWorkspace): string {
  const stepKey = (workspace.recommended_step || 'script') as WorkflowStepKey
  if (stepKey === 'script') return `/projects/${projectId}/script`
  if (!workspace.recommended_episode_id) return `/projects/${projectId}/script`
  return buildWorkflowStepPath(projectId, stepKey, workspace.recommended_episode_id)
}

export default function ProjectWorkbench() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { workspace, loading, refreshWorkspace: loadWorkspace } = useProjectWorkspace(projectId)

  const defaults = workspace?.project.workflow_defaults
  const providerTags = useMemo(() => {
    if (!defaults) return []
    return [
      defaults.video_provider_key ? `视频：${defaults.video_provider_key}` : null,
      defaults.tts_provider_key ? `语音：${defaults.tts_provider_key}` : null,
      defaults.lipsync_provider_key ? `口型：${defaults.lipsync_provider_key}` : null,
    ].filter(Boolean) as string[]
  }, [defaults])

  if (loading && !workspace) {
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
          kicker="项目工作台"
          title="项目总览"
          subtitle="项目不存在或加载失败。"
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

  const nextPath = resolveProjectNextPath(projectId, workspace)
  const resourceSummary = workspace.resource_summary

  return (
    <section className="np-page">
      <PageHeader
        kicker="项目工作台"
        title={workspace.project.name}
        subtitle={workspace.project.description || '以项目视角集中查看分集推进、资源准备和成片状态。'}
        onBack={() => navigate('/projects')}
        backLabel="返回项目列表"
        actions={(
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => { void loadWorkspace() }} loading={loading}>
              刷新
            </Button>
            <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => navigate(nextPath)}>
              继续创作
            </Button>
          </Space>
        )}
      />

      <ProjectSectionNav projectId={projectId} />

      <div className="np-page-scroll np-project-workbench-scroll">
        <div className="np-workbench-grid">
          <Card className="np-panel-card" title="项目摘要">
            <Space size={8} wrap style={{ marginBottom: 12 }}>
              <Tag className={`np-status-tag np-status-${workspace.project.status}`}>
                {STATUS_MAP[workspace.project.status]?.label ?? workspace.project.status}
              </Tag>
              <Tag className="np-status-tag">分集 {workspace.project.episode_count}</Tag>
              <Tag className="np-status-tag">分镜 {workspace.project.panel_count}</Tag>
              <Tag className="np-status-tag np-status-generated">成片 {resourceSummary.composition_count}</Tag>
            </Space>
            <Paragraph type="secondary" style={{ marginBottom: 12 }}>
              最近更新：{new Date(workspace.project.updated_at).toLocaleString('zh-CN')}
            </Paragraph>
            <Space wrap size={8}>
              {providerTags.length > 0 ? providerTags.map((item) => (
                <Tag key={item} className="np-status-tag">{item}</Tag>
              )) : <Tag className="np-status-tag">未配置项目默认 Provider</Tag>}
            </Space>
          </Card>

          <Card className="np-panel-card" title="继续创作">
            <Title level={5} style={{ marginTop: 0 }}>
              推荐下一步：{getWorkflowStepLabel(workspace.recommended_step)}
            </Title>
            <Paragraph type="secondary">
              {workspace.recommended_episode_id
                ? `建议先推进指定分集，再回到项目视角统一复核。`
                : '建议先完善项目默认配置和分集内容，再推进后续步骤。'}
            </Paragraph>
            <Space wrap>
              <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => navigate(nextPath)}>
                进入推荐步骤
              </Button>
              <Button icon={<UnorderedListOutlined />} onClick={() => navigate(`/projects/${projectId}/script`)}>
                管理分集
              </Button>
            </Space>
          </Card>

          <Card className="np-panel-card" title="资源与结果摘要">
            <div className="np-workbench-stat-grid">
              <article className="np-workbench-stat-card">
                <span className="np-kpi-label">角色实体</span>
                <strong>{resourceSummary.bound_character_entity_count}/{resourceSummary.character_entity_count}</strong>
              </article>
              <article className="np-workbench-stat-card">
                <span className="np-kpi-label">地点实体</span>
                <strong>{resourceSummary.bound_location_entity_count}/{resourceSummary.location_entity_count}</strong>
              </article>
              <article className="np-workbench-stat-card">
                <span className="np-kpi-label">声音资产</span>
                <strong>{resourceSummary.voice_asset_count}</strong>
              </article>
              <article className="np-workbench-stat-card">
                <span className="np-kpi-label">已完成片段</span>
                <strong>{resourceSummary.ready_clip_count}/{resourceSummary.clip_count}</strong>
              </article>
            </div>
            <Space wrap style={{ marginTop: 12 }}>
              <Button onClick={() => navigate(`/projects/${projectId}/resources`)}>查看资源总览</Button>
              <Button onClick={() => navigate(`/tasks?project_id=${projectId}`)}>查看项目任务</Button>
            </Space>
            {workspace.latest_preview ? (
              <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                最新成片：{new Date(workspace.latest_preview.updated_at || workspace.latest_preview.created_at || '').toLocaleString('zh-CN')}
              </Paragraph>
            ) : (
              <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                暂无已完成成片。
              </Paragraph>
            )}
          </Card>
        </div>

        <Card className="np-panel-card" title={`分集进度板（${workspace.episodes.length}）`} style={{ marginTop: 12 }}>
          {workspace.episodes.length <= 0 ? (
            <Empty description="还没有分集，先进入剧本分集页导入或创建。" />
          ) : (
            <div className="np-workbench-episode-list">
              {workspace.episodes.map((episode) => (
                <article key={episode.id} className="np-workbench-episode-card">
                  <div className="np-workbench-episode-header">
                    <div>
                      <Title level={5} style={{ margin: 0 }}>{episode.title}</Title>
                      <Text type="secondary">当前步骤：{getWorkflowStepLabel(episode.workflow_summary.current_step)}</Text>
                    </div>
                    <Tag className={`np-status-tag${episode.workflow_summary.blockers.length > 0 ? ' np-status-failed' : ' np-status-completed'}`}>
                      {episode.workflow_summary.completion_percent}%
                    </Tag>
                  </div>
                  <Paragraph className="np-workbench-episode-summary">
                    {episode.summary || episode.workflow_summary.blockers[0] || '当前分集已具备继续推进的基础信息。'}
                  </Paragraph>
                  <Space wrap size={8}>
                    <Tag className="np-status-tag">分镜 {episode.panel_count}</Tag>
                    {episode.video_provider_key ? <Tag className="np-status-tag">视频已配置</Tag> : null}
                    {episode.tts_provider_key ? <Tag className="np-status-tag">语音已配置</Tag> : null}
                    {episode.lipsync_provider_key ? <Tag className="np-status-tag">口型已配置</Tag> : null}
                  </Space>
                  <div className="np-workbench-episode-actions">
                    <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => navigate(buildEpisodeContinuePath(projectId, episode))}>
                      继续流程
                    </Button>
                    <Button
                      icon={<EditOutlined />}
                      onClick={() => navigate(`/projects/${projectId}/script?episode=${episode.id}&mode=edit`)}
                    >
                      编辑本集
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Card>
      </div>
    </section>
  )
}
