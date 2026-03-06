import { Card, Collapse, Image, Input, Modal, Space, Switch, Tag, Typography } from 'antd'
import type { BindPreviewState } from './types'

const { Text } = Typography

interface BindPreviewModalProps {
  bindPreview: BindPreviewState | null
  previewDiffOnly: boolean
  saving: boolean
  onPreviewDiffOnlyChange: (value: boolean) => void
  onConfirm: () => void
  onCancel: () => void
}

export default function BindPreviewModal({
  bindPreview,
  previewDiffOnly,
  saving,
  onPreviewDiffOnlyChange,
  onConfirm,
  onCancel,
}: BindPreviewModalProps) {
  return (
    <Modal
      title={bindPreview ? `绑定预览 · ${bindPreview.panelTitle}` : '绑定预览'}
      open={!!bindPreview}
      width={760}
      confirmLoading={saving}
      okText="确认绑定并写入"
      cancelText="取消"
      onOk={onConfirm}
      onCancel={onCancel}
    >
      {bindPreview ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Tag className="np-status-tag">写入模式：固定追加</Tag>
            {bindPreview.type === 'character' ? (
              <Tag className="np-status-tag">角色：{bindPreview.character.name}</Tag>
            ) : (
              <Tag className="np-status-tag">地点：{bindPreview.location.name}</Tag>
            )}
            {bindPreview.type === 'character' ? (
              <Tag className="np-status-tag">
                语音：{bindPreview.plan.fallbackVoiceName || (bindPreview.plan.fallbackVoiceId ? '已关联' : '不变')}
              </Tag>
            ) : null}
            <Tag className="np-status-tag">
              参考图：{bindPreview.plan.nextReferenceImageUrl ? '将写入/保留' : '不变'}
            </Tag>
          </Space>

          <Space size={8}>
            <Text type="secondary">预览模式：</Text>
            <Switch
              checked={previewDiffOnly}
              onChange={onPreviewDiffOnlyChange}
              checkedChildren="仅看差异"
              unCheckedChildren="完整模式"
            />
          </Space>

          {!previewDiffOnly && bindPreview.plan.nextReferenceImageUrl ? (
            <Space direction="vertical" size={4}>
              <Text type="secondary">绑定后参考图预览：</Text>
              <Space size={8} align="start">
                <Image
                  src={bindPreview.plan.nextReferenceImageUrl}
                  width={120}
                  style={{ border: '1px solid var(--np-frame-line)' }}
                />
                <a href={bindPreview.plan.nextReferenceImageUrl} target="_blank" rel="noreferrer">
                  新窗口查看
                </a>
              </Space>
            </Space>
          ) : null}

          <Card size="small" className="np-panel-card">
            <Text type="secondary">提示词新增行（将写入）：</Text>
            {bindPreview.addedPromptLines.length === 0 ? (
              <div style={{ marginTop: 6 }}>
                <Text type="secondary">无新增行（可能内容已存在）</Text>
              </div>
            ) : (
              <Space direction="vertical" size={4} style={{ marginTop: 6, width: '100%' }}>
                {bindPreview.addedPromptLines.map((line, index) => (
                  <Text key={`${line}-${index}`}>+ {line}</Text>
                ))}
              </Space>
            )}
          </Card>

          <Collapse
            size="small"
            defaultActiveKey={previewDiffOnly ? [] : ['full-prompt']}
            items={[
              {
                key: 'full-prompt',
                label: '展开查看完整前后提示词对比',
                children: (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div>
                      <Text strong>当前提示词</Text>
                      <Input.TextArea
                        value={bindPreview.originPrompt ?? ''}
                        autoSize={{ minRows: 6, maxRows: 12 }}
                        readOnly
                      />
                    </div>
                    <div>
                      <Text strong>写入后提示词</Text>
                      <Input.TextArea
                        value={bindPreview.plan.nextPrompt ?? ''}
                        autoSize={{ minRows: 6, maxRows: 12 }}
                        readOnly
                      />
                    </div>
                  </div>
                ),
              },
            ]}
          />
        </Space>
      ) : null}
    </Modal>
  )
}
