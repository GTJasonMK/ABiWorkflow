import { Card, Descriptions, Switch, Typography } from 'antd'
import type { HealthPayload, RuntimeSummaryPayload } from '../../../api/system'
import StatusTag from './StatusTag'

const { Text } = Typography

interface RuntimeOverviewCardProps {
  health: HealthPayload | null
  runtime: RuntimeSummaryPayload | null
}

export default function RuntimeOverviewCard({ health, runtime }: RuntimeOverviewCardProps) {
  return (
    <Card title="运行状态总览" className="np-panel-card">
      <Descriptions column={1} size="small" styles={{ label: { width: 150 } }}>
        <Descriptions.Item label="后端健康">
          <StatusTag ok={health?.status === 'ok'} onLabel="正常" offLabel="异常" />
        </Descriptions.Item>
        <Descriptions.Item label="应用名称">
          <Text>{runtime?.app.name ?? '-'}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="调试模式">
          <Switch checked={Boolean(runtime?.app.debug)} disabled />
        </Descriptions.Item>
        <Descriptions.Item label="当前 LLM">
          <Text>{runtime?.llm.model ?? '-'}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="LLM Provider">
          <Text>{runtime?.llm.provider ?? '-'}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="视频提供者">
          <Text>{runtime?.video.provider ?? '-'}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="Celery Worker">
          <StatusTag ok={Boolean(runtime?.queue.celery_worker_online)} onLabel="在线" offLabel="离线" />
        </Descriptions.Item>
        <Descriptions.Item label="队列模式">
          <Text>Redis</Text>
        </Descriptions.Item>
        <Descriptions.Item label="Redis 连接">
          <StatusTag ok={Boolean(runtime?.queue.redis_available)} onLabel="正常" offLabel="不可用" />
        </Descriptions.Item>
      </Descriptions>
    </Card>
  )
}
