import { ApiOutlined } from '@ant-design/icons'
import { Form, Input, InputNumber, Select } from 'antd'
import { CODE_INPUT_STYLE } from '../../constants'

export default function VideoTab() {
  return (
    <div className="np-settings-section">
      <div className="np-dashboard-grid">
        <Form.Item label="单段最大时长（秒）" name="video_provider_max_duration_seconds" rules={[{ required: true, message: '请输入最大时长' }]}>
          <InputNumber min={1} max={3600} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="轮询间隔（秒）" name="video_poll_interval_seconds" rules={[{ required: true, message: '请输入轮询间隔' }]}>
          <InputNumber min={0.1} max={300} step={0.1} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="任务超时（秒）" name="video_task_timeout_seconds" rules={[{ required: true, message: '请输入任务超时' }]}>
          <InputNumber min={1} max={7200} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="GGK 视频模型" name="ggk_video_model" rules={[{ required: true, message: '请输入 GGK 视频模型' }]}>
          <Input prefix={<ApiOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item label="GGK 画面比例" name="ggk_video_aspect_ratio" rules={[{ required: true, message: '请选择画面比例' }]}>
          <Select
            options={[
              { label: '16:9', value: '16:9' },
              { label: '9:16', value: '9:16' },
              { label: '3:2', value: '3:2' },
              { label: '2:3', value: '2:3' },
              { label: '1:1', value: '1:1' },
            ]}
          />
        </Form.Item>
        <Form.Item label="GGK 分辨率" name="ggk_video_resolution" rules={[{ required: true, message: '请选择分辨率' }]}>
          <Select
            options={[
              { label: 'SD', value: 'SD' },
              { label: 'HD', value: 'HD' },
            ]}
          />
        </Form.Item>
        <Form.Item label="GGK 风格" name="ggk_video_preset" rules={[{ required: true, message: '请选择生成风格' }]}>
          <Select
            options={[
              { label: 'normal', value: 'normal' },
              { label: 'fun', value: 'fun' },
              { label: 'spicy', value: 'spicy' },
              { label: 'custom', value: 'custom' },
            ]}
          />
        </Form.Item>
        <Form.Item
          label="模型时长策略（JSON，可选）"
          name="ggk_video_model_duration_profiles"
          tooltip="按模型配置时长区间、可选时长和提示词模板。留空使用默认策略。"
        >
          <Input.TextArea
            rows={6}
            style={CODE_INPUT_STYLE}
            placeholder={'{"grok-imagine-1.0-video":{"min_seconds":5,"max_seconds":15,"allowed_seconds":[5,6,8,10,15],"prompt_hint_template":"请将时长控制在约 {seconds} 秒。"}}'}
          />
        </Form.Item>
        <Form.Item label="GGK 请求超时（秒）" name="ggk_request_timeout_seconds" rules={[{ required: true, message: '请输入 GGK 请求超时' }]}>
          <InputNumber min={10} max={1200} style={{ width: '100%' }} />
        </Form.Item>
      </div>
    </div>
  )
}
