import { KeyOutlined, LinkOutlined } from '@ant-design/icons'
import { Collapse, Form, Input, Select } from 'antd'
import { CODE_INPUT_STYLE } from '../../constants'

export default function LlmTab() {
  return (
    <div className="np-settings-section">
      <div className="np-dashboard-grid">
        <Form.Item
          label="Provider"
          name="llm_provider"
          rules={[{ required: true, message: '请选择 LLM Provider' }]}
          tooltip="显式指定 LLM API 协议，不再通过模型名猜测"
        >
          <Select
            options={[
              { label: 'OpenAI 兼容（Chat Completions）', value: 'openai' },
              { label: 'Anthropic（Messages）', value: 'anthropic' },
            ]}
          />
        </Form.Item>
        <Form.Item
          label="模型"
          name="llm_model"
          rules={[{ required: true, message: '请输入模型名称' }]}
          tooltip="模型名称由 Provider 决定协议；例如 gpt-4o / grok-4 / claude-sonnet 等"
        >
          <Input placeholder="gpt-4o / claude-sonnet-4-20250514 / deepseek-chat" />
        </Form.Item>
        <Form.Item
          label="Base URL"
          name="llm_base_url"
          tooltip="留空使用默认地址；OpenAI provider 需要以 /v1 结尾（例如 https://glk.jia4u.de/v1），Anthropic provider 不应包含 /v1"
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
