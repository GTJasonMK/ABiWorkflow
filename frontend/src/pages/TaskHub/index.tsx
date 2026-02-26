import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Card, Empty, Space, Tag, Typography, App as AntdApp } from 'antd'
import { DeleteOutlined, ReloadOutlined, RocketOutlined } from '@ant-design/icons'
import { useTaskStore, type TaskItem } from '../../stores/taskStore'
import PageHeader from '../../components/PageHeader'

const { Text } = Typography

function renderTaskType(taskType: TaskItem['taskType']): string {
  if (taskType === 'parse') return '剧本解析'
  if (taskType === 'generate') return '视频生成'
  return '视频合成'
}

function renderStateLabel(state: string): string {
  switch (state) {
    case 'pending':
    case 'queued':
      return '排队中'
    case 'started':
    case 'processing':
      return '执行中'
    case 'success':
    case 'completed':
      return '已完成'
    case 'failure':
    case 'failed':
      return '失败'
    case 'timeout':
      return '超时'
    default:
      return state
  }
}

function renderStateClass(task: TaskItem): string {
  if (!task.ready) return 'np-status-tag np-status-generating'
  if (task.successful) return 'np-status-tag np-status-generated'
  return 'np-status-tag np-status-failed'
}

function renderSummary(task: TaskItem): string | null {
  if (!task.result || !task.successful) return null
  if (task.taskType === 'parse') {
    const scenes = Number(task.result.scene_count ?? 0)
    const characters = Number(task.result.character_count ?? 0)
    return `${characters} 角色 / ${scenes} 场景`
  }
  if (task.taskType === 'generate') {
    const completed = Number(task.result.completed ?? 0)
    const failed = Number(task.result.failed ?? 0)
    return `${completed} 成功 / ${failed} 失败`
  }
  if (task.taskType === 'compose') {
    const compositionId = String(task.result.composition_id ?? '')
    return compositionId ? `合成编号 ${compositionId.slice(0, 12)}` : null
  }
  return null
}

export default function TaskHub() {
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()
  const { tasks, refreshTask, removeTask, clearFinished, clearAll, setPanelOpen } = useTaskStore()

  const sortedTasks = useMemo(
    () => [...tasks].sort((a, b) => b.updatedAt - a.updatedAt),
    [tasks],
  )

  const counts = useMemo(() => {
    const running = sortedTasks.filter((item) => !item.ready).length
    const failed = sortedTasks.filter((item) => item.ready && !item.successful).length
    const success = sortedTasks.filter((item) => item.ready && item.successful).length
    return { running, failed, success }
  }, [sortedTasks])

  return (
    <section className="np-page">
      <PageHeader
        kicker="任务编排"
        title="任务中心"
        subtitle="统一查看解析、生成、合成任务状态，并支持手动刷新和清理。"
        actions={(
          <Space>
            <Button onClick={() => setPanelOpen(true)}>打开右侧抽屉</Button>
            <Button danger onClick={clearFinished}>清理已完成</Button>
            <Button danger onClick={clearAll}>清空全部</Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
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
            <Empty
              description="暂无任务记录。执行“解析剧本 / 开始生成 / 开始合成”后会自动记录。"
            >
              <Button type="primary" icon={<RocketOutlined />} onClick={() => navigate('/projects')}>
                去项目工作台
              </Button>
            </Empty>
          </Card>
        ) : (
          <div className="np-task-list">
            {sortedTasks.map((task) => {
              const summary = renderSummary(task)
              return (
                <article key={task.taskId} className="np-task-item">
                  <header className="np-task-item-head">
                    <Space size={6}>
                      <Tag className="np-status-tag">{renderTaskType(task.taskType)}</Tag>
                      <Tag className={renderStateClass(task)}>{renderStateLabel(task.state)}</Tag>
                      {!task.ready && <Badge status="processing" />}
                    </Space>
                    <Space size={6}>
                      <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        onClick={async () => {
                          try {
                            await refreshTask(task.taskId)
                          } catch (error) {
                            message.error((error as Error).message || '刷新任务失败')
                          }
                        }}
                      />
                      <Button
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => removeTask(task.taskId)}
                      />
                    </Space>
                  </header>

                  <div className="np-task-item-body">
                    <Text type="secondary">项目：{task.projectId ? task.projectId.slice(0, 8) : '-'}</Text>
                    <Text type="secondary">任务编号：{task.taskId.slice(0, 16)}</Text>
                    <Text type="secondary">更新时间：{new Date(task.updatedAt).toLocaleString('zh-CN')}</Text>
                    {summary && <Text type="secondary">结果：{summary}</Text>}
                    {task.error && <Text className="np-task-error">{task.error}</Text>}
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
}
