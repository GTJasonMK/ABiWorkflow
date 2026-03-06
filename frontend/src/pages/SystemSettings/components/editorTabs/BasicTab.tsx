import { Form, Input, Select, Switch } from 'antd'
import { SoundOutlined } from '@ant-design/icons'

export default function BasicTab() {
  return (
    <div className="np-settings-section">
      <div className="np-dashboard-grid">
        <Form.Item label="应用名称" name="app_name" rules={[{ required: true, message: '请输入应用名称' }]}>
          <Input />
        </Form.Item>
        <Form.Item label="调试模式" name="debug" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item label="视频提供者" name="video_provider" rules={[{ required: true, message: '请输入视频提供者' }]}>
          <Select
            options={[
              { label: 'Mock（本地测试）', value: 'mock' },
              { label: 'HTTP（任务轮询）', value: 'http' },
              { label: 'GGK（OpenAI 兼容视频）', value: 'ggk' },
            ]}
          />
        </Form.Item>
        <Form.Item
          label="项目沉淀默认同步全局"
          name="project_asset_publish_global_default"
          valuePropName="checked"
          tooltip="开启后，分镜编辑页中“沉淀目标=当前项目”时默认勾选“同步全局”。"
        >
          <Switch />
        </Form.Item>
        <Form.Item label="TTS 音色" name="tts_voice" rules={[{ required: true, message: '请输入 TTS 音色' }]}>
          <Input prefix={<SoundOutlined />} allowClear />
        </Form.Item>
      </div>
    </div>
  )
}
