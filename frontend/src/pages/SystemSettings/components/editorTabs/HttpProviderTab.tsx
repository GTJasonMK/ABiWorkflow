import { CodeOutlined, KeyOutlined, LinkOutlined } from '@ant-design/icons'
import { Collapse, Form, Input, InputNumber } from 'antd'
import { CODE_INPUT_STYLE } from '../../constants'

export default function HttpProviderTab() {
  return (
    <div className="np-settings-section">
      <div className="np-dashboard-grid">
        <Form.Item label="HTTP Base URL" name="video_http_base_url">
          <Input
            prefix={<LinkOutlined />}
            style={CODE_INPUT_STYLE}
            placeholder="https://api.example.com"
            allowClear
          />
        </Form.Item>
        <Form.Item label="Generate Path" name="video_http_generate_path" rules={[{ required: true, message: '请输入生成路径' }]}>
          <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item label="Status Path" name="video_http_status_path" rules={[{ required: true, message: '请输入状态查询路径' }]}>
          <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item label="Task ID 字段路径" name="video_http_task_id_path" rules={[{ required: true, message: '请输入 task_id 路径' }]}>
          <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item label="状态字段路径" name="video_http_status_value_path" rules={[{ required: true, message: '请输入状态字段路径' }]}>
          <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item label="进度字段路径" name="video_http_progress_path" rules={[{ required: true, message: '请输入进度字段路径' }]}>
          <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item label="结果 URL 字段路径" name="video_http_result_url_path" rules={[{ required: true, message: '请输入结果 URL 路径' }]}>
          <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item label="错误字段路径" name="video_http_error_path" rules={[{ required: true, message: '请输入错误字段路径' }]}>
          <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item label="HTTP 请求超时（秒）" name="video_http_request_timeout_seconds" rules={[{ required: true, message: '请输入请求超时' }]}>
          <InputNumber min={1} max={600} style={{ width: '100%' }} />
        </Form.Item>
      </div>
      <Collapse
        items={[
          {
            key: 'http-secret',
            label: 'HTTP API Key（可选，留空不修改）',
            children: (
              <Form.Item label="HTTP API Key" name="video_http_api_key">
                <Input.Password prefix={<KeyOutlined />} />
              </Form.Item>
            ),
          },
        ]}
      />
    </div>
  )
}
