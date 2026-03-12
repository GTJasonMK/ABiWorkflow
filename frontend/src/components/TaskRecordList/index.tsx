import { Button, List, Space, Tag, Typography } from 'antd'
import { CloseCircleOutlined, EyeInvisibleOutlined, RedoOutlined } from '@ant-design/icons'
import type { TaskRecord } from '../../types/taskRecord'
import { renderExtendedTaskType, renderTaskStateLabel } from '../../utils/taskPresentation'
import { resolveTaskScopeLabel, shortTaskId } from '../../utils/taskScope'

const { Text } = Typography

const PROVIDER_TASK_TYPES = new Set(['video', 'tts', 'lipsync'])

type TaskRecordListMode = 'full' | 'compact'

interface TaskRecordListProps {
  tasks: TaskRecord[]
  mode?: TaskRecordListMode
  onCancelTask?: (task: TaskRecord) => Promise<void> | void
  onDismissTask?: (task: TaskRecord) => Promise<void> | void
  onRetryTask?: (task: TaskRecord) => Promise<void> | void
}

function resolveStateClass(task: TaskRecord): string {
  if (!task.ready) return 'np-status-tag np-status-generating'
  return task.successful ? 'np-status-tag np-status-generated' : 'np-status-tag np-status-failed'
}

function isProviderTask(task: TaskRecord): boolean {
  return PROVIDER_TASK_TYPES.has(task.task_type)
}

function sourceTaskLabel(task: TaskRecord): string {
  return isProviderTask(task) ? 'Provider 任务' : 'Celery ID'
}

export default function TaskRecordList({
  tasks,
  mode = 'full',
  onCancelTask,
  onDismissTask,
  onRetryTask,
}: TaskRecordListProps) {
  if (mode === 'compact') {
    return (
      <List
        size="small"
        dataSource={tasks}
        renderItem={(task) => (
          <List.Item>
            <Space size={6} wrap>
              <Tag className="np-status-tag">{renderExtendedTaskType(task.task_type)}</Tag>
              <Tag className={resolveStateClass(task)}>{renderTaskStateLabel(task.status)}</Tag>
              <Tag className="np-status-tag">{resolveTaskScopeLabel(task)}</Tag>
              {isProviderTask(task) && <Tag className="np-status-tag">外部 Provider</Tag>}
              <Text type="secondary">进度 {task.progress_percent.toFixed(0)}%</Text>
              <Text type="secondary">{task.id.slice(0, 12)}</Text>
            </Space>
          </List.Item>
        )}
      />
    )
  }

  return (
    <div className="np-task-list">
      {tasks.map((task) => {
        const externalProvider = isProviderTask(task)
        return (
          <article key={task.id} className="np-task-item">
            <header className="np-task-item-head">
              <Space size={6}>
                <Tag className="np-status-tag">{renderExtendedTaskType(task.task_type)}</Tag>
                <Tag className={resolveStateClass(task)}>{renderTaskStateLabel(task.status)}</Tag>
                <Tag className="np-status-tag">{resolveTaskScopeLabel(task)}</Tag>
                {task.target_type && <Tag className="np-status-tag">{task.target_type}</Tag>}
                {externalProvider && <Tag className="np-status-tag">外部 Provider</Tag>}
              </Space>
              <Space size={6}>
                {!task.ready && onCancelTask && !externalProvider && (
                  <Button
                    size="small"
                    icon={<CloseCircleOutlined />}
                    onClick={() => {
                      void onCancelTask(task)
                    }}
                  />
                )}
                {task.ready && onRetryTask && (
                  <Button
                    size="small"
                    icon={<RedoOutlined />}
                    onClick={() => {
                      void onRetryTask(task)
                    }}
                  />
                )}
                {onDismissTask && (
                  <Button
                    size="small"
                    icon={<EyeInvisibleOutlined />}
                    onClick={() => {
                      void onDismissTask(task)
                    }}
                  />
                )}
              </Space>
            </header>

            <div className="np-task-item-body">
              <Text type="secondary">项目：{shortTaskId(task.project_id)}</Text>
              <Text type="secondary">任务编号：{task.id.slice(0, 16)}</Text>
              {task.source_task_id && <Text type="secondary">{sourceTaskLabel(task)}：{task.source_task_id.slice(0, 16)}</Text>}
              {task.target_id && <Text type="secondary">目标：{shortTaskId(task.target_id)}</Text>}
              <Text type="secondary">进度：{task.progress_percent.toFixed(0)}%</Text>
              <Text type="secondary">
                更新时间：{task.updated_at ? new Date(task.updated_at).toLocaleString('zh-CN') : '-'}
              </Text>
              {externalProvider && !task.ready && (
                <Text type="secondary">外部 Provider 任务请在 Provider 侧取消，任务中心仅保留状态查看。</Text>
              )}
              {task.message && <Text type="secondary">{task.message}</Text>}
              {task.error && <Text className="np-task-error">{task.error}</Text>}
            </div>
          </article>
        )
      })}
    </div>
  )
}
