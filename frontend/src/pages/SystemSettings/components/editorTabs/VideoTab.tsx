import { ApiOutlined, KeyOutlined, LinkOutlined } from '@ant-design/icons'
import { Collapse, Form, Input, InputNumber, Select } from 'antd'
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
        <Form.Item label="GGK Base URL" name="ggk_base_url" tooltip="GGK 视频服务地址，当视频提供者为 GGK 时使用">
          <Input prefix={<LinkOutlined />} style={CODE_INPUT_STYLE} placeholder="例如 http://127.0.0.1:8000/v1" allowClear />
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
        <Form.Item label="立绘 API Base URL" name="portrait_api_base_url" tooltip="OpenAI 兼容的图片生成 API 地址，用于角色立绘生成。">
          <Input prefix={<ApiOutlined />} style={CODE_INPUT_STYLE} placeholder="https://api.x.ai" allowClear />
        </Form.Item>
        <Form.Item label="立绘模型" name="portrait_image_model" rules={[{ required: true, message: '请输入立绘模型名称' }]}>
          <Input prefix={<ApiOutlined />} style={CODE_INPUT_STYLE} allowClear />
        </Form.Item>
        <Form.Item
          label="默认模型绑定（JSON）"
          name="default_model_bindings"
          tooltip="定义业务环节默认使用的模型，如 analysisModel/videoModel 等。"
        >
          <Input.TextArea
            rows={6}
            style={CODE_INPUT_STYLE}
            placeholder={'{"analysisModel":"gpt-4o","videoModel":"grok-imagine-1.0-video"}'}
          />
        </Form.Item>
        <Form.Item
          label="模型能力配置（JSON）"
          name="model_capability_profiles"
          tooltip="按模型配置可选能力，例如时长/比例/分辨率；供前端能力化表单使用。"
        >
          <Input.TextArea
            rows={6}
            style={CODE_INPUT_STYLE}
            placeholder={'{"grok-imagine-1.0-video":{"allowed_seconds":[5,8,10],"aspect_ratios":["16:9","9:16"]}}'}
          />
        </Form.Item>
      </div>
      <Collapse
        items={[
          {
            key: 'portrait-secrets',
            label: '密钥更新（可选，留空不修改）',
            children: (
              <div className="np-dashboard-grid">
                <Form.Item label="GGK API Key" name="ggk_api_key">
                  <Input.Password prefix={<KeyOutlined />} placeholder="sk-..." />
                </Form.Item>
                <Form.Item label="立绘 API Key" name="portrait_api_key">
                  <Input.Password prefix={<KeyOutlined />} placeholder="留空不修改" />
                </Form.Item>
              </div>
            ),
          },
        ]}
      />
    </div>
  )
}
