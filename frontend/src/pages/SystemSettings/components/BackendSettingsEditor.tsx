import { Card, Form, Tabs, Typography, type FormInstance } from 'antd'
import type { RuntimeSummaryPayload } from '../../../api/system'
import type { BackendSettingsFormValues } from '../types'
import BasicTab from './editorTabs/BasicTab'
import HttpProviderTab from './editorTabs/HttpProviderTab'
import InfraTab from './editorTabs/InfraTab'
import LlmTab from './editorTabs/LlmTab'
import VideoTab from './editorTabs/VideoTab'

const { Paragraph } = Typography

interface BackendSettingsEditorProps {
  runtime: RuntimeSummaryPayload | null
  backendForm: FormInstance<BackendSettingsFormValues>
  canPickDirectory: boolean
}

export default function BackendSettingsEditor({
  runtime,
  backendForm,
  canPickDirectory,
}: BackendSettingsEditorProps) {
  return (
    <Card title="后端配置编辑（保存即写入 .env）" className="np-panel-card np-settings-editor">
      <Paragraph className="np-note" style={{ marginBottom: 12 }}>
        配置已按模块分组。密钥和连接串字段支持“留空不修改”。
        {canPickDirectory ? ' 桌面版可直接选择目录。' : ''}
      </Paragraph>
      <Form form={backendForm} layout="vertical">
        <Tabs
          className="np-settings-tabs"
          defaultActiveKey="basic"
          items={[
            { key: 'basic', label: '基础', children: <BasicTab /> },
            { key: 'llm', label: 'LLM', children: <LlmTab /> },
            { key: 'video', label: '视频', children: <VideoTab /> },
            { key: 'http-provider', label: 'HTTP 提供者', children: <HttpProviderTab /> },
            { key: 'infra', label: '数据库与队列', children: <InfraTab runtime={runtime} /> },
          ]}
        />
      </Form>
    </Card>
  )
}
