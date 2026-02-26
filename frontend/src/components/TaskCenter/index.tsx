import { Badge, Button, Drawer, Empty, Space, Tag, Typography, App as AntdApp } from 'antd'
import { BellOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import { useMemo } from 'react'
import { useTaskStore, type TaskItem } from '../../stores/taskStore'

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

function renderResultSummary(task: TaskItem): string | null {
  if (!task.result || !task.successful) return null

  if (task.taskType === 'parse') {
    const scenes = Number(task.result.scene_count ?? 0)
    const characters = Number(task.result.character_count ?? 0)
    return `结果：${characters} 角色 / ${scenes} 场景`
  }
  if (task.taskType === 'generate') {
    const completed = Number(task.result.completed ?? 0)
    const failed = Number(task.result.failed ?? 0)
    return `结果：${completed} 成功 / ${failed} 失败`
  }
  if (task.taskType === 'compose') {
    const compositionId = String(task.result.composition_id ?? '')
    return compositionId ? `结果：合成编号 ${compositionId.slice(0, 12)}` : null
  }
  return null
}

export default function TaskCenter() {
  const { message } = AntdApp.useApp()
  const {
    tasks,
    panelOpen,
    setPanelOpen,
    removeTask,
    clearFinished,
    clearAll,
    refreshTask,
  } = useTaskStore()

  const runningCount = useMemo(
    () => tasks.filter((task) => !task.ready).length,
    [tasks],
  )

  return (
    <>
      <Badge count={runningCount} size="small">
        <Button
          icon={<BellOutlined />}
          onClick={() => setPanelOpen(true)}
        >
          任务中心
        </Button>
      </Badge>

      <Drawer
        title="任务中心"
        width={420}
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        extra={(
          <Space>
            <Button size="small" danger onClick={clearAll}>
              清空全部
            </Button>
            <Button size="small" onClick={clearFinished}>
              清理已完成
            </Button>
          </Space>
        )}
      >
        {tasks.length === 0 ? (
          <Empty description="暂无任务记录" />
        ) : (
          <div className="np-task-list">
            {tasks.map((task) => {
              const summary = renderResultSummary(task)
              return (
                <article key={task.taskId} className="np-task-item">
                  <header className="np-task-item-head">
                    <Space size={6}>
                      <Tag className="np-status-tag">{renderTaskType(task.taskType)}</Tag>
                      <Tag className={renderStateClass(task)}>{renderStateLabel(task.state)}</Tag>
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
                    <Text type="secondary">项目：{task.projectId.slice(0, 8) || '-'}</Text>
                    <Text type="secondary">任务编号：{task.taskId.slice(0, 12)}</Text>
                    <Text type="secondary">
                      更新时间：{new Date(task.updatedAt).toLocaleString('zh-CN')}
                    </Text>
                    {summary && (
                      <Text type="secondary">{summary}</Text>
                    )}
                    {task.error && (
                      <Text className="np-task-error">{task.error}</Text>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </Drawer>
    </>
  )
}
