import { Button, Drawer, Form, Input, InputNumber, Select, Space, Switch } from 'antd'
import type { FormInstance } from 'antd'
import type { AssetFolder, GlobalCharacterAsset, GlobalLocationAsset, GlobalVoice } from '../../types/assetHub'

export type EditorKind = 'folder' | 'voice' | 'character' | 'location'
export type EditorMode = 'create' | 'edit'
export type EditorRecord = AssetFolder | GlobalVoice | GlobalCharacterAsset | GlobalLocationAsset

export interface EditorState {
  kind: EditorKind
  mode: EditorMode
  record?: EditorRecord
}

interface AssetEditorDrawerProps {
  editor: EditorState | null
  form: FormInstance
  saving: boolean
  folderOptions: Array<{ label: string; value: string }>
  voiceOptions: Array<{ label: string; value: string }>
  projectScopeOptions: Array<{ label: string; value: string }>
  onSubmit: () => void
  onClose: () => void
}

const KIND_LABELS: Record<EditorKind, string> = {
  folder: '资产目录',
  voice: '语音资产',
  character: '角色资产',
  location: '地点资产',
}

function buildTitle(editor: EditorState | null): string {
  if (!editor) return ''
  const prefix = editor.mode === 'create' ? '新建' : '编辑'
  return `${prefix}${KIND_LABELS[editor.kind]}`
}

export default function AssetEditorDrawer({
  editor,
  form,
  saving,
  folderOptions,
  voiceOptions,
  projectScopeOptions,
  onSubmit,
  onClose,
}: AssetEditorDrawerProps) {
  const renderFields = () => {
    if (!editor) return null

    if (editor.kind === 'folder') {
      return (
        <>
          <Form.Item label="目录名称" name="name" rules={[{ required: true, message: '请输入目录名称' }]}>
            <Input placeholder="例如：角色参考图" />
          </Form.Item>
          <Form.Item label="目录类型" name="folder_type" rules={[{ required: true, message: '请输入目录类型' }]}>
            <Input placeholder="generic / character / location / voice" />
          </Form.Item>
          <Form.Item label="存储路径" name="storage_path">
            <Input placeholder="本地目录路径（可选）" />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} placeholder="目录用途说明（可选）" />
          </Form.Item>
          <Form.Item label="排序" name="sort_order">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="启用" name="is_active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      )
    }

    if (editor.kind === 'voice') {
      return (
        <>
          <Form.Item label="语音名称" name="name" rules={[{ required: true, message: '请输入语音名称' }]}>
            <Input placeholder="例如：温柔旁白-女声A" />
          </Form.Item>
          <Form.Item label="资产归属" name="project_id">
            <Select allowClear options={projectScopeOptions} placeholder="留空表示全局复用，或选择归属项目" />
          </Form.Item>
          <Form.Item label="Provider" name="provider" rules={[{ required: true, message: '请输入 Provider' }]}>
            <Input placeholder="例如：edge-tts / aliyun / ggk" />
          </Form.Item>
          <Form.Item label="语音编码" name="voice_code" rules={[{ required: true, message: '请输入语音编码' }]}>
            <Input placeholder="例如：zh-CN-XiaoxiaoNeural" />
          </Form.Item>
          <Form.Item label="所属目录" name="folder_id">
            <Select allowClear options={folderOptions} placeholder="可选：归档到目录" />
          </Form.Item>
          <Form.Item label="语言" name="language">
            <Input placeholder="例如：zh-CN" />
          </Form.Item>
          <Form.Item label="性别" name="gender">
            <Input placeholder="例如：female / male" />
          </Form.Item>
          <Form.Item label="示例音频 URL" name="sample_audio_url">
            <Input placeholder="http(s)://..." />
          </Form.Item>
          <Form.Item label="风格提示词" name="style_prompt">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="启用" name="is_active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      )
    }

    if (editor.kind === 'character') {
      return (
        <>
          <Form.Item label="角色名称" name="name" rules={[{ required: true, message: '请输入角色名称' }]}>
            <Input placeholder="例如：女主-安宁" />
          </Form.Item>
          <Form.Item label="资产归属" name="project_id">
            <Select allowClear options={projectScopeOptions} placeholder="留空表示全局复用，或选择归属项目" />
          </Form.Item>
          <Form.Item label="所属目录" name="folder_id">
            <Select allowClear options={folderOptions} placeholder="可选：归档到目录" />
          </Form.Item>
          <Form.Item label="别名" name="alias">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="提示词模板" name="prompt_template">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item label="参考图 URL" name="reference_image_url">
            <Input placeholder="http(s)://..." />
          </Form.Item>
          <Form.Item label="默认语音" name="default_voice_id">
            <Select allowClear options={voiceOptions} placeholder="选择语音（可选）" />
          </Form.Item>
          <Form.Item label="标签（逗号分隔）" name="tags_input">
            <Input placeholder="例如：女主, 现代, 职场" />
          </Form.Item>
          <Form.Item label="启用" name="is_active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      )
    }

    return (
      <>
        <Form.Item label="地点名称" name="name" rules={[{ required: true, message: '请输入地点名称' }]}>
          <Input placeholder="例如：城市天台-夜景" />
        </Form.Item>
        <Form.Item label="资产归属" name="project_id">
          <Select allowClear options={projectScopeOptions} placeholder="留空表示全局复用，或选择归属项目" />
        </Form.Item>
        <Form.Item label="所属目录" name="folder_id">
          <Select allowClear options={folderOptions} placeholder="可选：归档到目录" />
        </Form.Item>
        <Form.Item label="描述" name="description">
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item label="提示词模板" name="prompt_template">
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item label="参考图 URL" name="reference_image_url">
          <Input placeholder="http(s)://..." />
        </Form.Item>
        <Form.Item label="标签（逗号分隔）" name="tags_input">
          <Input placeholder="例如：室外, 夜景, 都市" />
        </Form.Item>
        <Form.Item label="启用" name="is_active" valuePropName="checked">
          <Switch />
        </Form.Item>
      </>
    )
  }

  return (
    <Drawer
      title={buildTitle(editor)}
      width={480}
      open={Boolean(editor)}
      onClose={onClose}
      forceRender
      destroyOnHidden
      footer={(
        <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={onSubmit} loading={saving}>
            {editor?.mode === 'create' ? '创建' : '保存'}
          </Button>
        </Space>
      )}
    >
      <Form form={form} layout="vertical" preserve={false}>
        {renderFields()}
      </Form>
    </Drawer>
  )
}
