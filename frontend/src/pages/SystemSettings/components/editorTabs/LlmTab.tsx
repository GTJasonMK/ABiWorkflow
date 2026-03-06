import { KeyOutlined, LinkOutlined } from '@ant-design/icons'
import { Collapse, Form, Input } from 'antd'
import { CODE_INPUT_STYLE } from '../../constants'

export default function LlmTab() {
  return (
    <div className="np-settings-section">
      <div className="np-dashboard-grid">
        <Form.Item
          label="模型"
          name="llm_model"
          rules={[{ required: true, message: '请输入模型名称' }]}
          tooltip="根据模型名自动检测 API 格式：含 claude 使用 Anthropic API，其余使用 OpenAI 兼容 API"
        >
          <Input placeholder="gpt-4o / claude-sonnet-4-20250514 / deepseek-chat" />
        </Form.Item>
        <Form.Item
          label="Base URL"
          name="llm_base_url"
          tooltip="留空使用官方默认地址；可填写 DeepSeek、GGK 等第三方兼容服务地址"
        >
          <Input
            prefix={<LinkOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder="留空使用默认地址"
            allowClear
          />
        </Form.Item>
      </div>
      <Collapse
        items={[
          {
            key: 'llm-secrets',
            label: '密钥更新（可选，留空不修改）',
            children: (
              <div className="np-dashboard-grid">
                <Form.Item label="API Key" name="llm_api_key">
                  <Input.Password prefix={<KeyOutlined />} placeholder="sk-..." />
                </Form.Item>
              </div>
            ),
          },
        ]}
      />
    </div>
  )
}
