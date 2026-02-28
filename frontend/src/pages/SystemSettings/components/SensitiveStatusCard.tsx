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

  return (
    <Card title="敏感项当前状态" className="np-panel-card">
      <Descriptions column={1} size="small" styles={{ label: { width: 180 } }}>
        <Descriptions.Item label="OpenAI Key">
          <Space size={6} wrap>
            <StatusTag ok={Boolean(llm?.openai.api_key_configured)} onLabel="已配置" offLabel="未配置" />
            {llm?.openai.api_key_preview ? <Text code>{llm.openai.api_key_preview}</Text> : null}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="Anthropic Key">
          <Space size={6} wrap>
            <StatusTag ok={Boolean(llm?.anthropic.api_key_configured)} onLabel="已配置" offLabel="未配置" />
            {llm?.anthropic.api_key_preview ? <Text code>{llm.anthropic.api_key_preview}</Text> : null}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="DeepSeek Key">
          <Space size={6} wrap>
            <StatusTag ok={Boolean(llm?.deepseek.api_key_configured)} onLabel="已配置" offLabel="未配置" />
            {llm?.deepseek.api_key_preview ? <Text code>{llm.deepseek.api_key_preview}</Text> : null}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="GGK Key">
          <Space size={6} wrap>
            <StatusTag ok={Boolean(llm?.ggk.api_key_configured)} onLabel="已配置" offLabel="未配置" />
            {llm?.ggk.api_key_preview ? <Text code>{llm.ggk.api_key_preview}</Text> : null}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="HTTP Provider Key">
          <Space size={6} wrap>
            <StatusTag ok={Boolean(httpProvider?.api_key_configured)} onLabel="已配置" offLabel="未配置" />
            {httpProvider?.api_key_preview ? <Text code>{httpProvider.api_key_preview}</Text> : null}
          </Space>
        </Descriptions.Item>
      </Descriptions>
    </Card>
  )
}
