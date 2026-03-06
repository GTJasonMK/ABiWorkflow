import { useCallback, useEffect, useState } from 'react'
import { Drawer, Input, InputNumber, Space, Button, Typography } from 'antd'
import type { PanelEditDraft } from './types'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'

const { Text } = Typography

interface PanelEditDrawerProps {
  open: boolean
  title: string
  draft: PanelEditDraft | null
  saving: boolean
  onDraftChange: React.Dispatch<React.SetStateAction<PanelEditDraft | null>>
  onSave: () => void
  onClose: () => void
}

export default function PanelEditDrawer({
  open,
  title,
  draft,
  saving,
  onDraftChange,
  onSave,
  onClose,
}: PanelEditDrawerProps) {
  const [dirty, setDirty] = useState(false)

  useUnsavedChanges(open && dirty)

  // 抽屉打开/关闭时重置 dirty 状态
  useEffect(() => {
    if (!open) setDirty(false)
  }, [open])

  const handleDraftChange: typeof onDraftChange = (updater) => {
    onDraftChange(updater)
    setDirty(true)
  }

  const handleSave = useCallback(() => {
    onSave()
    setDirty(false)
  }, [onSave])
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, handleSave])

  return (
    <Drawer
      title={title}
      width={640}
      open={open}
      onClose={onClose}
      destroyOnHidden
      footer={
        <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={saving} onClick={handleSave}>
            保存修改
          </Button>
        </Space>
      }
    >
      {draft ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">分镜标题</Text>
            <Input
              value={draft.title}
              onChange={(e) => handleDraftChange((prev) => (prev ? { ...prev, title: e.target.value } : prev))}
              placeholder="请输入分镜标题"
              aria-label="分镜标题"
              autoFocus
            />
          </Space>

          <Space size={12} style={{ width: '100%' }} align="start">
            <Space direction="vertical" size={4} style={{ width: '50%' }}>
              <Text type="secondary">时长（秒）</Text>
              <InputNumber
                min={0.1}
                max={3600}
                step={0.1}
                style={{ width: '100%' }}
                value={draft.duration_seconds}
                onChange={(value) => {
                  const numeric = Number(value ?? 0)
                  handleDraftChange((prev) => (prev ? { ...prev, duration_seconds: numeric } : prev))
                }}
              />
            </Space>
          </Space>

          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">风格预设（可选）</Text>
            <Input
              value={draft.style_preset}
              onChange={(e) => handleDraftChange((prev) => (prev ? { ...prev, style_preset: e.target.value } : prev))}
              placeholder="例如：cinematic / anime / realistic"
            />
          </Space>

          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">剧情/旁白文案（script_text）</Text>
            <Input.TextArea
              rows={4}
              value={draft.script_text}
              onChange={(e) => handleDraftChange((prev) => (prev ? { ...prev, script_text: e.target.value } : prev))}
              placeholder="填写该分镜的剧情正文或语义描述"
            />
          </Space>

          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">视频提示词（visual_prompt）</Text>
            <Input.TextArea
              rows={4}
              value={draft.visual_prompt}
              onChange={(e) => handleDraftChange((prev) => (prev ? { ...prev, visual_prompt: e.target.value } : prev))}
              placeholder="用于视频生成的主提示词"
            />
          </Space>

          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">负面提示词（negative_prompt）</Text>
            <Input.TextArea
              rows={3}
              value={draft.negative_prompt}
              onChange={(e) => handleDraftChange((prev) => (prev ? { ...prev, negative_prompt: e.target.value } : prev))}
              placeholder="需要规避的元素"
            />
          </Space>

          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">运镜提示（camera_hint）</Text>
            <Input
              value={draft.camera_hint}
              onChange={(e) => handleDraftChange((prev) => (prev ? { ...prev, camera_hint: e.target.value } : prev))}
              placeholder="例如：tracking / dolly in / static"
            />
          </Space>

          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">参考图 URL（reference_image_url）</Text>
            <Input
              value={draft.reference_image_url}
              onChange={(e) => handleDraftChange((prev) => (prev ? { ...prev, reference_image_url: e.target.value } : prev))}
              placeholder="http(s)://..."
            />
          </Space>

          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">旁白文本（tts_text）</Text>
            <Input.TextArea
              rows={3}
              value={draft.tts_text}
              onChange={(e) => handleDraftChange((prev) => (prev ? { ...prev, tts_text: e.target.value } : prev))}
              placeholder="可选：用于配音的专用文案"
            />
          </Space>
        </Space>
      ) : null}
    </Drawer>
  )
}
