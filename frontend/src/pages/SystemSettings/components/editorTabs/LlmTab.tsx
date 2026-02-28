import { ApiOutlined, KeyOutlined, LinkOutlined } from '@ant-design/icons'
import { Collapse, Form, Input } from 'antd'
import { CODE_INPUT_STYLE } from '../../constants'

export default function LlmTab() {
  return (
    <div className="np-settings-section">
      <div className="np-dashboard-grid">
        <Form.Item label="OpenAI 模型" name="openai_model" rules={[{ required: true, message: '请输入 OpenAI 模型' }]}>
          <Input />
        </Form.Item>
        <Form.Item label="OpenAI Base URL" name="openai_base_url">
          <Input
            prefix={<LinkOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder="留空使用默认 OpenAI 地址"
            allowClear
          />
        </Form.Item>
        <Form.Item label="Anthropic 模型" name="anthropic_model" rules={[{ required: true, message: '请输入 Anthropic 模型' }]}>
          <Input />
        </Form.Item>
        <Form.Item label="DeepSeek 模型" name="deepseek_model" rules={[{ required: true, message: '请输入 DeepSeek 模型' }]}>
          <Input />
        </Form.Item>
        <Form.Item label="DeepSeek Base URL" name="deepseek_base_url">
          <Input prefix={<LinkOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item label="GGK Base URL" name="ggk_base_url">
          <Input
            prefix={<LinkOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder="例如 http://127.0.0.1:8000/v1"
            allowClear
          />
        </Form.Item>
        <Form.Item label="GGK 文本模型" name="ggk_text_model" rules={[{ required: true, message: '请输入 GGK 文本模型' }]}>
          <Input
            prefix={<ApiOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder="例如 grok-3 / grok-4.1"
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
                <Form.Item label="OpenAI API Key" name="openai_api_key">
                  <Input.Password prefix={<KeyOutlined />} placeholder="sk-..." />
                </Form.Item>
                <Form.Item label="Anthropic API Key" name="anthropic_api_key">
                  <Input.Password prefix={<KeyOutlined />} placeholder="sk-ant-..." />
                </Form.Item>
                <Form.Item label="DeepSeek API Key" name="deepseek_api_key">
                  <Input.Password prefix={<KeyOutlined />} />
                </Form.Item>
                <Form.Item label="GGK API Key" name="ggk_api_key">
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
