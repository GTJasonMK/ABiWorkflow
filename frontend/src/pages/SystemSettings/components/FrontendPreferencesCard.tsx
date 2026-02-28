import { Form, Card, Select, Input, Typography } from 'antd'
import { LinkOutlined } from '@ant-design/icons'
import StatusTag from './StatusTag'
import { CODE_INPUT_STYLE } from '../constants'

const { Text, Paragraph } = Typography

interface HomeOption {
  value: string
  label: string
}

interface FrontendPreferencesCardProps {
  homePath: string
  homeOptions: HomeOption[]
  onHomePathChange: (path: string) => void
  apiOverride: string
  onApiOverrideChange: (value: string) => void
  currentApiBase: string
  optionalProbeEnabled: boolean
}

export default function FrontendPreferencesCard({
  homePath,
  homeOptions,
  onHomePathChange,
  apiOverride,
  onApiOverrideChange,
  currentApiBase,
  optionalProbeEnabled,
}: FrontendPreferencesCardProps) {
  return (
    <Card title="前端偏好设置" className="np-panel-card">
      <Form layout="vertical">
        <Form.Item label="默认首页">
          <Select
            value={homePath}
            options={homeOptions}
            onChange={onHomePathChange}
          />
        </Form.Item>

        <Form.Item label="API 地址覆盖（可选）">
          <Input
            prefix={<LinkOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder="例如 /api 或 http://127.0.0.1:8000/api"
            value={apiOverride}
            onChange={(event) => onApiOverrideChange(event.target.value)}
            allowClear
          />
        </Form.Item>
      </Form>
      <Paragraph className="np-note" style={{ marginBottom: 6 }}>
        当前生效 API：<Text code>{currentApiBase}</Text>
      </Paragraph>
      <Paragraph className="np-note" style={{ marginBottom: 0 }}>
        可选接口探测：<StatusTag ok={optionalProbeEnabled} onLabel="开启" offLabel="关闭" />
      </Paragraph>
    </Card>
  )
}
