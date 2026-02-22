import { useState } from 'react'
import { Card, Tag, Input, Button, Space, Collapse, Descriptions, Popconfirm, message } from 'antd'
import { EditOutlined, DeleteOutlined, SaveOutlined, CloseOutlined, VideoCameraOutlined } from '@ant-design/icons'
import type { Scene } from '../../types/scene'
import { useSceneStore } from '../../stores/sceneStore'

interface Props {
  scene: Scene
  projectId: string
}

export default function SceneCard({ scene, projectId }: Props) {
  const { updateScene, deleteScene } = useSceneStore()
  const [editing, setEditing] = useState(false)
  const statusLabelMap: Record<string, string> = {
    pending: '待处理',
    generating: '生成中',
    generated: '已完成',
    failed: '失败',
  }

  const [form, setForm] = useState({
    title: scene.title,
    video_prompt: scene.video_prompt ?? '',
    negative_prompt: scene.negative_prompt ?? '',
    camera_movement: scene.camera_movement ?? '',
    dialogue: scene.dialogue ?? '',
    duration_seconds: scene.duration_seconds,
  })

  const handleSave = async () => {
    await updateScene(scene.id, form)
    setEditing(false)
    message.success('场景已更新')
  }

  const handleDelete = async () => {
    await deleteScene(scene.id, projectId)
    message.success('场景已删除')
  }

  return (
    <Card
      className="np-scene-card"
      size="small"
      title={
        <Space>
          <VideoCameraOutlined />
          <span>场景 {scene.sequence_order + 1}: {scene.title}</span>
          <Tag className={`np-status-tag np-status-${scene.status}`}>
            {statusLabelMap[scene.status] ?? scene.status}
          </Tag>
        </Space>
      }
      extra={
        <Space>
          {!editing ? (
            <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(true)}>编辑</Button>
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
        </Space>
      ) : (
        <Collapse
          ghost
          items={[{
            key: '1',
            label: '详细信息',
            children: (
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
            ),
          }]}
        />
      )}
    </Card>
  )
}
