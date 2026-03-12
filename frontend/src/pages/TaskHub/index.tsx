import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { App as AntdApp, Button, Card, Empty, Space, Tag } from 'antd'
import { ReloadOutlined, RocketOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import { cancelTaskRecord, dismissFailedTaskRecords, dismissTaskRecord, retryTaskRecord } from '../../api/tasks'
import { getApiErrorMessage } from '../../utils/error'
import TaskRecordList from '../../components/TaskRecordList'
import { sortTaskRecordsByUpdatedAt, summarizeTaskRecords } from '../../utils/taskRecords'
import useTaskRecords from '../../hooks/useTaskRecords'

export default function TaskHub() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { message } = AntdApp.useApp()
  const projectId = (searchParams.get('project_id') || '').trim() || undefined
  const episodeId = (searchParams.get('episode_id') || '').trim() || undefined
  const panelId = (searchParams.get('panel_id') || '').trim() || undefined
  const status = (searchParams.get('status') || '').trim() || undefined
  const hasScopedFilter = Boolean(projectId || episodeId || panelId || status)
  const { tasks, loading, refresh } = useTaskRecords({
    enabled: true,
    limit: 200,
    includeDismissed: false,
    projectId,
    episodeId,
    panelId,
    status,
    onError: (error) => {
      message.error(getApiErrorMessage(error, '加载后端任务记录失败'))
    },
  })
  const sortedTasks = useMemo(() => sortTaskRecordsByUpdatedAt(tasks), [tasks])
  const counts = useMemo(() => summarizeTaskRecords(sortedTasks), [sortedTasks])
  const failedTaskIds = useMemo(
    () => sortedTasks.filter((task) => task.ready && !task.successful).map((task) => task.id),
    [sortedTasks],
  )

  return (
    <section className="np-page">
      <PageHeader
        kicker="任务编排"
        title="全局任务中心"
        subtitle="以全局视角统一查看解析、生成、合成与 Provider 任务状态；外部 Provider 任务支持查看与失败后重试，不在任务中心内取消。"
        actions={(
          <Space>
            {hasScopedFilter ? (
              <Button onClick={() => navigate('/tasks')}>
                清空筛选
              </Button>
            ) : null}
            <Button
              disabled={failedTaskIds.length === 0}
              onClick={() => {
                void (async () => {
                  try {
                    const result = await dismissFailedTaskRecords({ project_id: projectId, task_ids: failedTaskIds })
                    await refresh({ showLoading: false })
                    message.success(`已忽略失败任务 ${result.dismissed} 条`)
                  } catch (error) {
                    message.error(getApiErrorMessage(error, '批量忽略失败任务失败'))
                  }
                })()
              }}
            >
              忽略失败任务（{failedTaskIds.length}）
            </Button>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void refresh({ showLoading: true })}>
              刷新任务
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
        <Card size="small" className="np-panel-card" style={{ marginBottom: 12 }}>
          <Space size={12} wrap align="center">
            <Tag className="np-status-tag">当前视角：{hasScopedFilter ? '筛选结果' : '全局'}</Tag>
            {projectId ? <Tag className="np-status-tag">项目：{projectId.slice(0, 8)}</Tag> : null}
            {episodeId ? <Tag className="np-status-tag">分集：{episodeId.slice(0, 8)}</Tag> : null}
            {panelId ? <Tag className="np-status-tag">分镜：{panelId.slice(0, 8)}</Tag> : null}
            {status ? <Tag className="np-status-tag">状态：{status}</Tag> : null}
            <Tag className="np-status-tag">任务数：{sortedTasks.length}</Tag>
          </Space>
        </Card>

        <div className="np-kpi-grid">
          <article className="np-kpi-card">
            <p className="np-kpi-label">执行中</p>
            <p className="np-kpi-value">{counts.running}</p>
          </article>
          <article className="np-kpi-card">
            <p className="np-kpi-label">已完成</p>
            <p className="np-kpi-value">{counts.success}</p>
          </article>
          <article className="np-kpi-card">
            <p className="np-kpi-label">失败/超时</p>
            <p className="np-kpi-value">{counts.failed}</p>
          </article>
        </div>

        {sortedTasks.length === 0 ? (
          <Card className="np-panel-card">
            <Empty description="暂无任务记录。执行“解析剧本 / 开始生成 / 开始合成”后会自动记录。">
              <Button type="primary" icon={<RocketOutlined />} onClick={() => navigate('/projects')}>
                去项目工作台
              </Button>
            </Empty>
          </Card>
        ) : (
          <TaskRecordList
            tasks={sortedTasks}
            mode="full"
            onCancelTask={async (task) => {
              try {
                await cancelTaskRecord(task.id)
                await refresh({ showLoading: false })
              } catch (error) {
                message.error(getApiErrorMessage(error, '取消任务失败'))
              }
            }}
            onDismissTask={async (task) => {
              try {
                await dismissTaskRecord(task.id)
                await refresh({ showLoading: false })
              } catch (error) {
                message.error(getApiErrorMessage(error, '忽略任务失败'))
              }
            }}
            onRetryTask={async (task) => {
              try {
                await retryTaskRecord(task.id)
                await refresh({ showLoading: false })
                message.success('重试任务已提交')
              } catch (error) {
                message.error(getApiErrorMessage(error, '重试任务失败'))
              }
            }}
          />
        )}
      </div>
    </section>
  )
}
