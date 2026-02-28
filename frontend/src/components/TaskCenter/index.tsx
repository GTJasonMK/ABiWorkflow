import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { App as AntdApp, Badge, Button, Drawer, Empty, Space } from 'antd'
import { ArrowRightOutlined, BellOutlined, ReloadOutlined } from '@ant-design/icons'
import { useTaskStore } from '../../stores/taskStore'
import { getApiErrorMessage } from '../../utils/error'
import TaskRecordList from '../TaskRecordList'
import { sortTaskRecordsByUpdatedAt, summarizeTaskRecords } from '../../utils/taskRecords'
import useTaskRecords from '../../hooks/useTaskRecords'

export default function TaskCenter() {
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()
  const { panelOpen, setPanelOpen } = useTaskStore()
  const { tasks, loading, refresh } = useTaskRecords({
    enabled: panelOpen,
    limit: 200,
    includeDismissed: false,
    pollIntervalMs: 4000,
    onError: (error) => {
      message.error(getApiErrorMessage(error, '加载任务失败'))
    },
  })

  const sortedTasks = useMemo(() => sortTaskRecordsByUpdatedAt(tasks), [tasks])
  const counts = useMemo(() => summarizeTaskRecords(sortedTasks), [sortedTasks])
  const runningTasks = useMemo(
    () => sortedTasks.filter((task) => !task.ready).slice(0, 8),
    [sortedTasks],
  )

  return (
    <>
      <Badge count={counts.running} size="small">
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
            <Button
              size="small"
              onClick={() => void refresh({ showLoading: true })}
              loading={loading}
              icon={<ReloadOutlined />}
            >
              刷新
            </Button>
          </Space>
        )}
      >
        <div className="np-kpi-grid" style={{ marginBottom: 12 }}>
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

        {tasks.length === 0 ? (
          <Empty description="暂无任务记录" />
        ) : runningTasks.length === 0 ? (
          <Empty description="当前没有执行中的任务" />
        ) : (
          <TaskRecordList tasks={runningTasks} mode="compact" />
        )}

        <Space style={{ marginTop: 14 }}>
          <Button
            type="primary"
            icon={<ArrowRightOutlined />}
            onClick={() => {
              setPanelOpen(false)
              navigate('/tasks')
            }}
          >
            进入任务详情页
          </Button>
        </Space>
      </Drawer>
    </>
  )
}
