import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { App as AntdApp, Button, Card, Empty, Space } from 'antd'
import { ReloadOutlined, RocketOutlined } from '@ant-design/icons'
import { useTaskStore } from '../../stores/taskStore'
import PageHeader from '../../components/PageHeader'
import { cancelTaskRecord, dismissTaskRecord } from '../../api/tasks'
import { getApiErrorMessage } from '../../utils/error'
import TaskRecordList from '../../components/TaskRecordList'
import { sortTaskRecordsByUpdatedAt, summarizeTaskRecords } from '../../utils/taskRecords'
import useTaskRecords from '../../hooks/useTaskRecords'

export default function TaskHub() {
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()
  const { setPanelOpen } = useTaskStore()
  const { tasks, loading, refresh } = useTaskRecords({
    enabled: true,
    limit: 200,
    includeDismissed: false,
    onError: (error) => {
      message.error(getApiErrorMessage(error, '加载后端任务记录失败'))
    },
  })
  const sortedTasks = useMemo(() => sortTaskRecordsByUpdatedAt(tasks), [tasks])
  const counts = useMemo(() => summarizeTaskRecords(sortedTasks), [sortedTasks])

  return (
    <section className="np-page">
      <PageHeader
        kicker="任务编排"
        title="任务中心"
        subtitle="统一查看解析、生成、合成任务状态，并支持手动刷新和清理。"
        actions={(
          <Space>
            <Button onClick={() => setPanelOpen(true)}>打开右侧抽屉</Button>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void refresh({ showLoading: true })}>
              刷新任务
            </Button>
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
          />
        )}
      </div>
    </section>
  )
}
