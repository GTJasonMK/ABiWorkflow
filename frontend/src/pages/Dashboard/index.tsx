import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, List, Space, Spin, Tag, Typography, App as AntdApp } from 'antd'
import { PlusOutlined, ReloadOutlined, RightOutlined } from '@ant-design/icons'
import { useProjectStore } from '../../stores/projectStore'
import type { ProjectListItem } from '../../types/project'
import { STATUS_MAP } from '../../types/project'
import { getHealthStatus, type HealthPayload } from '../../api/system'
import PageHeader from '../../components/PageHeader'
import { getApiErrorMessage } from '../../utils/error'
import { getApiBaseUrl } from '../../runtime'

const { Text, Paragraph } = Typography

function getProjectEntry(project: ProjectListItem): { path: string; label: string } {
  return { path: `/projects/${project.id}`, label: '进入项目' }
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { projects, loading, stats, fetchProjects } = useProjectStore()
  const { message } = AntdApp.useApp()
  const [health, setHealth] = useState<HealthPayload | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)
  const [healthError, setHealthError] = useState<string | null>(null)
  const apiBaseUrl = getApiBaseUrl()

  const refreshHealth = async () => {
    setHealthLoading(true)
    try {
      const result = await getHealthStatus()
      setHealth(result)
      setHealthError(null)
    } catch (error) {
      setHealthError(getApiErrorMessage(error, '后端连接失败'))
      setHealth(null)
    } finally {
      setHealthLoading(false)
    }
  }

  useEffect(() => {
    fetchProjects({ page: 1 }).catch((error) => {
      message.error(getApiErrorMessage(error, '加载项目失败'))
    })
    void refreshHealth()
  }, [fetchProjects, message])

  // 使用后端返回的全局统计，不受分页影响
  const totalAll = Object.values(stats).reduce((sum, n) => sum + n, 0)
  const activeCount = (stats.parsing ?? 0) + (stats.generating ?? 0) + (stats.composing ?? 0)
  const completedCount = stats.completed ?? 0

  if (loading && projects.length === 0) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="总览看板"
        title="工作区总览"
        subtitle="快速查看项目进度、系统状态和最近活动。"
        actions={(
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                fetchProjects({ page: 1 }).catch((error) => {
                  message.error(getApiErrorMessage(error, '刷新项目失败'))
                })
              }}
            >
              刷新项目
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/projects')}>
              新建/管理项目
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
        <div className="np-kpi-grid">
          <article className="np-kpi-card">
            <p className="np-kpi-label">项目总数</p>
            <p className="np-kpi-value">{totalAll}</p>
          </article>
          <article className="np-kpi-card">
            <p className="np-kpi-label">执行中</p>
            <p className="np-kpi-value">{activeCount}</p>
          </article>
          <article className="np-kpi-card">
            <p className="np-kpi-label">已完成</p>
            <p className="np-kpi-value">{completedCount}</p>
          </article>
        </div>

        <div className="np-dashboard-grid">
          <Card
            title="系统状态"
            extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => void refreshHealth()}>刷新</Button>}
            className="np-panel-card"
          >
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <div>
                <Text type="secondary">后端健康：</Text>{' '}
                {healthLoading ? (
                  <Tag className="np-status-tag np-status-generating">检查中</Tag>
                ) : health?.status === 'ok' ? (
                  <Tag className="np-status-tag np-status-generated">正常</Tag>
                ) : (
                  <Tag className="np-status-tag np-status-failed">异常</Tag>
                )}
              </div>
              <div>
                <Text type="secondary">服务名：</Text>
                <Text>{health?.app ?? '-'}</Text>
              </div>
              <div>
                <Text type="secondary">API 基地址：</Text>
                <Text code>{apiBaseUrl}</Text>
              </div>
              {healthError && (
                <Paragraph className="np-task-error" style={{ marginBottom: 0 }}>
                  {healthError}
                </Paragraph>
              )}
            </Space>
          </Card>

          <Card title="状态分布" className="np-panel-card">
            <Space wrap>
              {Object.entries(STATUS_MAP).map(([status, info]) => {
                const count = stats[status] ?? 0
                return (
                  <Tag key={status} className={`np-status-tag np-status-${status}`}>
                    {info.label} · {count}
                  </Tag>
                )
              })}
            </Space>
          </Card>
        </div>

        <Card
          title="最近活跃"
          className="np-panel-card"
          extra={<Button size="small" type="link" onClick={() => navigate('/projects')}>全部项目 →</Button>}
        >
          <List
            dataSource={projects.slice(0, 4)}
            locale={{ emptyText: '暂无项目，先创建一个项目开始创作。' }}
            renderItem={(item) => {
              const entry = getProjectEntry(item)
              return (
                <List.Item
                  actions={[
                    <Button
                      key="open"
                      size="small"
                      type="default"
                      icon={<RightOutlined />}
                      onClick={() => navigate(entry.path)}
                    >
                      {entry.label}
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={item.name}
                    description={item.description || '暂无描述'}
                  />
                  <Space size={8}>
                    <Tag className={`np-status-tag np-status-${item.status}`}>{STATUS_MAP[item.status].label}</Tag>
                    <Text type="secondary">{new Date(item.updated_at).toLocaleString('zh-CN')}</Text>
                  </Space>
                </List.Item>
              )
            }}
          />
        </Card>
      </div>
    </section>
  )
}
