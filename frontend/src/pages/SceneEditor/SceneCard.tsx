import { useCallback, useEffect, useState } from 'react'
import { Card, Tag, Input, InputNumber, Button, Space, Collapse, Descriptions, Popconfirm, Modal, Table, Empty, App as AntdApp } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { EditOutlined, DeleteOutlined, SaveOutlined, CloseOutlined, VideoCameraOutlined, HolderOutlined, FolderOpenOutlined, CheckCircleOutlined } from '@ant-design/icons'
import type { Scene, ClipBrief } from '../../types/scene'
import { useSceneStore } from '../../stores/sceneStore'
import { getProjectAssets, type AssetScene } from '../../api/assets'
import { getApiErrorMessage } from '../../utils/error'

interface Props {
  scene: Scene
  projectId: string
  /** dnd-kit 拖拽手柄属性，由父组件通过 useSortable 传入 */
  dragHandleProps?: Record<string, unknown>
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待处理',
  generating: '生成中',
  generated: '已完成',
  completed: '已完成',
  failed: '失败',
}

const CLIP_STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  generating: '生成中',
  completed: '已完成',
  failed: '失败',
}

const clipColumns: ColumnsType<ClipBrief> = [
  { title: '片段', dataIndex: 'clip_order', key: 'clip_order', width: 60, render: (v: number) => `#${v + 1}` },
  {
    title: '状态', dataIndex: 'status', key: 'status', width: 80,
    render: (s: string) => <Tag className={`np-status-tag np-status-${s}`}>{CLIP_STATUS_LABEL[s] ?? s}</Tag>,
  },
  { title: '时长', dataIndex: 'duration_seconds', key: 'duration', width: 80, render: (v: number) => `${v.toFixed(1)}s` },
  { title: '错误信息', dataIndex: 'error_message', key: 'error', ellipsis: true, render: (v: string | null) => v ?? '-' },
]

function sceneToForm(scene: Scene) {
  return {
    title: scene.title,
    video_prompt: scene.video_prompt ?? '',
    negative_prompt: scene.negative_prompt ?? '',
    camera_movement: scene.camera_movement ?? '',
    dialogue: scene.dialogue ?? '',
    duration_seconds: scene.duration_seconds,
  }
}

export default function SceneCard({ scene, projectId, dragHandleProps }: Props) {
  const { updateScene, deleteScene } = useSceneStore()
  const [editing, setEditing] = useState(false)
  const [assetModalOpen, setAssetModalOpen] = useState(false)
  const [assetScene, setAssetScene] = useState<AssetScene | null>(null)
  const [assetLoading, setAssetLoading] = useState(false)
  const { message } = AntdApp.useApp()

  const [form, setForm] = useState(() => sceneToForm(scene))

  useEffect(() => {
    if (!editing) {
      setForm(sceneToForm(scene))
    }
  }, [scene, editing])

  const handleSave = async () => {
    try {
      const payload = {
        ...form,
        duration_seconds: Math.max(0.1, Number(form.duration_seconds) || scene.duration_seconds),
      }
      await updateScene(scene.id, payload)
      setEditing(false)
      message.success('场景已更新')
    } catch (error) {
      message.error(getApiErrorMessage(error, '场景更新失败'))
    }
  }

  const handleDelete = async () => {
    try {
      await deleteScene(scene.id, projectId)
      message.success('场景已删除')
    } catch (error) {
      message.error(getApiErrorMessage(error, '场景删除失败'))
    }
  }

  const handleViewAssets = useCallback(async () => {
    setAssetModalOpen(true)
    setAssetLoading(true)
    try {
      const data = await getProjectAssets(projectId)
      const matched = data.scenes.find((s) => s.scene_id === scene.id) ?? null
      setAssetScene(matched)
    } catch (error) {
      message.error(getApiErrorMessage(error, '获取场景资产失败'))
    } finally {
      setAssetLoading(false)
    }
  }, [projectId, scene.id, message])

  // 摘要行信息
  const { clip_summary } = scene
  const charCount = scene.characters.length
  const clipProgress = clip_summary.total > 0 ? `${clip_summary.completed}/${clip_summary.total}` : '0'

  return (
    <Card
      className="np-scene-card"
      size="small"
      title={
        <div className="np-scene-card-title">
          <div className="np-scene-card-title-main">
            {dragHandleProps && (
              <span {...dragHandleProps} style={{ cursor: 'grab', touchAction: 'none' }}>
                <HolderOutlined />
              </span>
            )}
            <VideoCameraOutlined />
            <span className="np-scene-card-name">场景 {scene.sequence_order + 1}: {scene.title}</span>
            <Tag className={`np-status-tag np-status-${scene.status}`}>
              {STATUS_LABEL[scene.status] ?? scene.status}
            </Tag>
          </div>
          <div className="np-scene-card-meta">
            {charCount > 0 && <Tag className="np-status-tag">角色 ×{charCount}</Tag>}
            <Tag className="np-status-tag">片段 {clipProgress}</Tag>
            <Tag className="np-status-tag">{scene.duration_seconds}s</Tag>
            {scene.transition_hint && <Tag className="np-status-tag">→{scene.transition_hint}</Tag>}
          </div>
        </div>
      }
      extra={
        <Space>
          <Button
            size="small"
            icon={<FolderOpenOutlined />}
            onClick={handleViewAssets}
          >
            资产
          </Button>
          {!editing ? (
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => {
                setForm(sceneToForm(scene))
                setEditing(true)
              }}
            >
              编辑
            </Button>
          ) : (
            <>
              <Button size="small" icon={<SaveOutlined />} type="primary" onClick={handleSave}>保存</Button>
              <Button size="small" icon={<CloseOutlined />} onClick={() => setEditing(false)}>取消</Button>
            </>
          )}
          <Popconfirm title="确认删除此场景？" onConfirm={handleDelete}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      }
    >
      <div className="np-scene-card-scroll">
        {editing ? (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <label style={{ fontWeight: 600 }}>场景标题</label>
              <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </div>
            <div>
              <label style={{ fontWeight: 600 }}>视频提示词</label>
              <Input.TextArea rows={3} value={form.video_prompt} onChange={(e) => setForm({ ...form, video_prompt: e.target.value })} />
            </div>
            <div>
              <label style={{ fontWeight: 600 }}>负面提示词</label>
              <Input.TextArea rows={2} value={form.negative_prompt} onChange={(e) => setForm({ ...form, negative_prompt: e.target.value })} />
            </div>
            <div>
              <label style={{ fontWeight: 600 }}>运镜</label>
              <Input value={form.camera_movement} onChange={(e) => setForm({ ...form, camera_movement: e.target.value })} />
            </div>
            <div>
              <label style={{ fontWeight: 600 }}>台词</label>
              <Input.TextArea rows={2} value={form.dialogue} onChange={(e) => setForm({ ...form, dialogue: e.target.value })} />
            </div>
            <div>
              <label style={{ fontWeight: 600 }}>时长（秒）</label>
              <InputNumber
                min={0.1}
                max={60}
                step={0.1}
                value={form.duration_seconds}
                onChange={(value) => setForm({ ...form, duration_seconds: Number(value) || scene.duration_seconds })}
                style={{ width: '100%' }}
              />
            </div>
          </Space>
        ) : (
          <Collapse
            ghost
            items={[
              {
                key: 'detail',
                label: '详细信息',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size="middle">
                    <Descriptions column={1} size="small">
                      <Descriptions.Item label="场景描述">{scene.description}</Descriptions.Item>
                      <Descriptions.Item label="视频提示词">
                        <code style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{scene.video_prompt}</code>
                      </Descriptions.Item>
                      {scene.negative_prompt && (
                        <Descriptions.Item label="负面提示词">{scene.negative_prompt}</Descriptions.Item>
                      )}
                      <Descriptions.Item label="运镜">{scene.camera_movement}</Descriptions.Item>
                      <Descriptions.Item label="场景环境">{scene.setting}</Descriptions.Item>
                      <Descriptions.Item label="风格关键词">{scene.style_keywords}</Descriptions.Item>
                      {scene.dialogue && <Descriptions.Item label="台词">{scene.dialogue}</Descriptions.Item>}
                      <Descriptions.Item label="时长">{scene.duration_seconds} 秒</Descriptions.Item>
                      <Descriptions.Item label="转场">{scene.transition_hint}</Descriptions.Item>
                      {scene.characters.length > 0 && (
                        <Descriptions.Item label="出场角色">
                          {scene.characters.map((c) => (
                            <Tag key={c.character_id} className="np-status-tag">{c.character_name}</Tag>
                          ))}
                        </Descriptions.Item>
                      )}
                    </Descriptions>

                    {/* 视频片段表格 */}
                    {scene.clips.length > 0 && (
                      <div>
                        <div style={{ fontWeight: 600, marginBottom: 8 }}>视频片段</div>
                        <Table<ClipBrief>
                          rowKey="id"
                          columns={clipColumns}
                          dataSource={scene.clips}
                          pagination={false}
                          size="small"
                          bordered
                        />
                      </div>
                    )}
                  </Space>
                ),
              },
            ]}
          />
        )}
      </div>

      {/* 资产查看弹窗 */}
      <Modal
        title={`场景资产 · ${scene.title}`}
        open={assetModalOpen}
        onCancel={() => setAssetModalOpen(false)}
        footer={null}
        width={720}
      >
        {assetLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>加载中...</div>
        ) : assetScene ? (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>视频片段（{assetScene.clips.length}）</div>
              {assetScene.clips.length === 0 ? (
                <Empty description="该场景暂无生成片段" />
              ) : (
                <div className="np-asset-grid">
                  {assetScene.clips.map((clip) => (
                    <Card key={clip.id} size="small" title={`片段 ${clip.clip_order + 1}${clip.candidate_index > 0 ? ` · 候选 ${String.fromCharCode(65 + clip.candidate_index)}` : ''}`} extra={
                      <Space size={4}>
                        {clip.is_selected && <Tag className="np-status-tag np-status-completed" icon={<CheckCircleOutlined />} style={{ fontSize: 10, margin: 0 }}>已选中</Tag>}
                        <Tag className={`np-status-tag np-status-${clip.status}`}>{CLIP_STATUS_LABEL[clip.status] ?? clip.status}</Tag>
                      </Space>
                    }>
                      {clip.media_url ? (
                        <video controls preload="metadata" className="np-asset-video" src={clip.media_url} />
                      ) : (
                        <span style={{ color: 'var(--np-text-secondary)' }}>片段文件不可用</span>
                      )}
                      <div style={{ marginTop: 8 }}>
                        <span style={{ color: 'var(--np-text-secondary)' }}>时长：{clip.duration_seconds.toFixed(1)} 秒</span>
                      </div>
                      {clip.error_message && (
                        <div style={{ marginTop: 8 }} className="np-task-error">{clip.error_message}</div>
                      )}
                    </Card>
                  ))}
                </div>
              )}
            </div>

            {/* 出场角色 */}
            {scene.characters.length > 0 && (
              <div>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>出场角色（{scene.characters.length}）</div>
                <Space wrap>
                  {scene.characters.map((c) => (
                    <Tag key={c.character_id} className="np-status-tag">{c.character_name}</Tag>
                  ))}
                </Space>
              </div>
            )}
          </Space>
        ) : (
          <Empty description="未找到该场景的资产数据" />
        )}
      </Modal>
    </Card>
  )
}
