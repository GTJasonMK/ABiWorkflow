import { Card, Descriptions, Space, Typography } from 'antd'
import type { RuntimeSummaryPayload } from '../../../api/system'
import StatusTag from './StatusTag'

const { Text } = Typography

interface SensitiveStatusCardProps {
  runtime: RuntimeSummaryPayload | null
}

export default function SensitiveStatusCard({ runtime }: SensitiveStatusCardProps) {
  const llm = runtime?.llm
  const httpProvider = runtime?.video.http_provider
  const ggkProvider = runtime?.video.ggk_provider
  const portrait = runtime?.video.portrait

  return (
    <Card title="敏感项当前状态" className="np-panel-card">
      <Descriptions column={1} size="small" styles={{ label: { width: 180 } }}>
        <Descriptions.Item label="LLM Key">
          <Space size={6} wrap>
            <StatusTag ok={Boolean(llm?.api_key_configured)} onLabel="已配置" offLabel="未配置" />
            {llm?.api_key_preview ? <Text code>{llm.api_key_preview}</Text> : null}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="GGK Video Key">
          <Space size={6} wrap>
            <StatusTag ok={Boolean(ggkProvider?.api_key_configured)} onLabel="已配置" offLabel="未配置" />
            {ggkProvider?.api_key_preview ? <Text code>{ggkProvider.api_key_preview}</Text> : null}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="HTTP Provider Key">
          <Space size={6} wrap>
            <StatusTag ok={Boolean(httpProvider?.api_key_configured)} onLabel="已配置" offLabel="未配置" />
            {httpProvider?.api_key_preview ? <Text code>{httpProvider.api_key_preview}</Text> : null}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="Portrait API Key">
          <Space size={6} wrap>
            <StatusTag ok={Boolean(portrait?.api_key_configured)} onLabel="已配置" offLabel="未配置" />
            {portrait?.api_key_preview ? <Text code>{portrait.api_key_preview}</Text> : null}
          </Space>
        </Descriptions.Item>
      </Descriptions>
    </Card>
  )
}
