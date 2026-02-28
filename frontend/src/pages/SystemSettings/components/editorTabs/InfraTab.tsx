import { DatabaseOutlined } from '@ant-design/icons'
import { Alert, Form, Input } from 'antd'
import type { RuntimeSummaryPayload } from '../../../../api/system'
import { CODE_INPUT_STYLE } from '../../constants'

interface InfraTabProps {
  runtime: RuntimeSummaryPayload | null
}

export default function InfraTab({ runtime }: InfraTabProps) {
  const queue = runtime?.queue

  return (
    <div className="np-settings-section">
      <Alert
        type="info"
        showIcon
        message="以下配置修改后需要重启后端服务才能完全生效"
        style={{ marginBottom: 12 }}
      />
      <div className="np-dashboard-grid">
        <Form.Item
          label="数据库连接（可选，留空不改）"
          name="database_url"
          tooltip="修改后需重启后端服务。留空表示不修改现有连接串。"
        >
          <Input
            prefix={<DatabaseOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder={runtime?.app.database_url || 'sqlite+aiosqlite:///./abi_workflow.db'}
            allowClear
          />
        </Form.Item>
        <Form.Item
          label="Redis URL（可选，留空不改）"
          name="redis_url"
          tooltip="修改后需重启后端服务和 Celery Worker。留空表示不修改现有连接串。"
        >
          <Input
            prefix={<DatabaseOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder={queue?.redis_url || 'redis://localhost:6379/0'}
            allowClear
          />
        </Form.Item>
        <Form.Item
          label="Celery Broker（可选，留空不改）"
          name="celery_broker_url"
          tooltip="修改后需重启 Celery Worker。"
        >
          <Input
            prefix={<DatabaseOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder={queue?.celery_broker_url || 'redis://localhost:6379/1'}
            allowClear
          />
        </Form.Item>
        <Form.Item
          label="Celery Result Backend（可选，留空不改）"
          name="celery_result_backend"
          tooltip="修改后需重启 Celery Worker。"
        >
          <Input
            prefix={<DatabaseOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder={queue?.celery_result_backend || 'redis://localhost:6379/2'}
            allowClear
          />
        </Form.Item>
      </div>
    </div>
  )
}
