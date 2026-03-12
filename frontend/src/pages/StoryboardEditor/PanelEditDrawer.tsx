import { useCallback, useEffect } from 'react'
import { Button, Card, Empty, Input, InputNumber, Popconfirm, Select, Space, Typography } from 'antd'
import { DeleteOutlined, SaveOutlined } from '@ant-design/icons'
import type { Panel } from '../../types/panel'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import PanelStatusTag from '../../components/PanelStatusTag'
import type { AssetTabKey, PanelEditDraft } from './types'

const { Text } = Typography

interface PanelEditDrawerProps {
  panel: Panel | null
  draft: PanelEditDraft | null
  dirty: boolean
  saving: boolean
  videoProviderKey: string | null
  allowedDurations: number[]
  onDraftChange: React.Dispatch<React.SetStateAction<PanelEditDraft | null>>
  onSave: () => void
  onDelete: (panel: Panel) => void
  onOpenAssetDrawer: (panel: Panel, tab?: AssetTabKey) => void
}

export default function PanelEditDrawer({
  panel,
  draft,
  dirty,
  saving,
  videoProviderKey,
  allowedDurations,
  onDraftChange,
  onSave,
  onDelete,
  onOpenAssetDrawer,
}: PanelEditDrawerProps) {
  useUnsavedChanges(dirty)

  const handleSave = useCallback(() => {
    onSave()
  }, [onSave])

  useEffect(() => {
    if (!panel) return
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [handleSave, panel])

  const canEdit = Boolean(panel && draft)
  const disabled = !canEdit || saving

  return (
    <section className="np-storyboard-column np-storyboard-column-detail">
      <Card
        title={panel ? `分镜详情 · ${panel.panel_order + 1}. ${panel.title}` : '分镜详情'}
        className="np-panel-card np-storyboard-panel-card"
        styles={{ body: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: 0 } }}
        extra={panel ? (
          <Space size={8}>
            <Button
              size="small"
              onClick={() => onOpenAssetDrawer(panel, 'character')}
            >
              角色覆盖
            </Button>
            <Button
              size="small"
              onClick={() => onOpenAssetDrawer(panel, 'location')}
            >
              地点覆盖
            </Button>
            <Button
              size="small"
              onClick={() => onOpenAssetDrawer(panel, 'voice')}
            >
              语音覆盖
            </Button>
            <Popconfirm
              title="确认删除该分镜？"
              onConfirm={() => onDelete(panel)}
              okButtonProps={{ danger: true }}
            >
              <Button size="small" danger icon={<DeleteOutlined />} disabled={saving}>
                删除
              </Button>
            </Popconfirm>
            <Button
              type="primary"
              size="small"
              icon={<SaveOutlined />}
              loading={saving}
              disabled={!dirty || !canEdit}
              onClick={handleSave}
            >
              保存
            </Button>
          </Space>
        ) : null}
      >
        {!panel || !draft ? (
          <div style={{ padding: 16 }}>
            <Empty description="请在左侧选择一个分镜" />
          </div>
        ) : (
          <div className="np-storyboard-column-scroll">
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Space size={8} wrap>
                <PanelStatusTag status={panel.status} />
                <Text type="secondary">ID: {panel.id.slice(0, 8)}</Text>
                {dirty ? <Text type="warning">未保存</Text> : <Text type="secondary">已保存</Text>}
              </Space>

              {panel.video_url ? (
                <video
                  src={panel.video_url}
                  controls
                  style={{ width: '100%', maxHeight: 240, border: '1px solid var(--np-ink)', background: '#000' }}
                />
              ) : null}

              {panel.tts_audio_url ? (
                <audio
                  src={panel.tts_audio_url}
                  controls
                  style={{ width: '100%' }}
                />
              ) : null}

              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">分镜标题</Text>
                <Input
                  value={draft.title}
                  disabled={disabled}
                  onChange={(e) => onDraftChange((prev) => (prev ? { ...prev, title: e.target.value } : prev))}
                  placeholder="请输入分镜标题"
                />
              </Space>

              <Space size={12} style={{ width: '100%' }} align="start">
                <Space direction="vertical" size={4} style={{ width: '50%' }}>
                  <Text type="secondary">时长（秒）</Text>
                  {allowedDurations.length > 0 ? (
                    (() => {
                      const rawValue = Number(draft.duration_seconds)
                      const rounded = Number.isFinite(rawValue) ? Math.round(rawValue) : 0
                      const inRange = allowedDurations.includes(rounded)
                      const selectableValue = inRange ? rounded : undefined

                      return (
                        <>
                          <Select
                            style={{ width: '100%' }}
                            disabled={disabled}
                            value={selectableValue}
                            options={allowedDurations.map((value) => ({ value, label: `${value} 秒` }))}
                            placeholder={inRange ? undefined : `当前值 ${rawValue} 秒不在允许范围内`}
                            onChange={(value) => {
                              const numeric = Number(value ?? 0)
                              onDraftChange((prev) => (prev ? { ...prev, duration_seconds: numeric } : prev))
                            }}
                          />
                          <Text type={inRange ? 'secondary' : 'warning'}>
                            {inRange
                              ? `可选：${allowedDurations.join(' / ')} 秒`
                              : `请改为：${allowedDurations.join(' / ')} 秒`}
                          </Text>
                        </>
                      )
                    })()
                  ) : (
                    <>
                      <InputNumber
                        min={0.1}
                        max={3600}
                        step={0.1}
                        style={{ width: '100%' }}
                        disabled
                        value={draft.duration_seconds}
                      />
                      <Text type={videoProviderKey ? 'warning' : 'secondary'}>
                        {videoProviderKey
                          ? '当前 Provider 未提供合法时长配置（_allowed_video_lengths），请先修正 ProviderConfig'
                          : '请先在分集参数中选择视频 Provider，再编辑时长'}
                      </Text>
                    </>
                  )}
                </Space>
              </Space>

              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">风格预设（可选）</Text>
                <Input
                  value={draft.style_preset}
                  disabled={disabled}
                  onChange={(e) => onDraftChange((prev) => (prev ? { ...prev, style_preset: e.target.value } : prev))}
                  placeholder="例如：cinematic / anime / realistic"
                />
              </Space>

              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">剧情/旁白文案（script_text）</Text>
                <Input.TextArea
                  rows={4}
                  value={draft.script_text}
                  disabled={disabled}
                  onChange={(e) => onDraftChange((prev) => (prev ? { ...prev, script_text: e.target.value } : prev))}
                  placeholder="填写该分镜的剧情正文或语义描述"
                />
              </Space>

              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">视频提示词（visual_prompt）</Text>
                <Input.TextArea
                  rows={4}
                  value={draft.visual_prompt}
                  disabled={disabled}
                  onChange={(e) => onDraftChange((prev) => (prev ? { ...prev, visual_prompt: e.target.value } : prev))}
                  placeholder="用于视频生成的主提示词"
                />
              </Space>

              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">负面提示词（negative_prompt）</Text>
                <Input.TextArea
                  rows={3}
                  value={draft.negative_prompt}
                  disabled={disabled}
                  onChange={(e) => onDraftChange((prev) => (prev ? { ...prev, negative_prompt: e.target.value } : prev))}
                  placeholder="需要规避的元素"
                />
              </Space>

              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">运镜提示（camera_hint）</Text>
                <Input
                  value={draft.camera_hint}
                  disabled={disabled}
                  onChange={(e) => onDraftChange((prev) => (prev ? { ...prev, camera_hint: e.target.value } : prev))}
                  placeholder="例如：tracking / dolly in / static"
                />
              </Space>

              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">参考图 URL（reference_image_url）</Text>
                <Input
                  value={draft.reference_image_url}
                  disabled={disabled}
                  onChange={(e) => onDraftChange((prev) => (prev ? { ...prev, reference_image_url: e.target.value } : prev))}
                  placeholder="http(s)://..."
                />
              </Space>

              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">旁白文本（tts_text）</Text>
                <Input.TextArea
                  rows={3}
                  value={draft.tts_text}
                  disabled={disabled}
                  onChange={(e) => onDraftChange((prev) => (prev ? { ...prev, tts_text: e.target.value } : prev))}
                  placeholder="可选：用于配音的专用文案"
                />
              </Space>
            </Space>
          </div>
        )}
      </Card>
    </section>
  )
}
