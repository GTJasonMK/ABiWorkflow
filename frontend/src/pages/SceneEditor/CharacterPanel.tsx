import { useMemo, useState } from 'react'
import { Button, Card, Descriptions, Empty, Image, Input, Space, Tag, Typography, App as AntdApp } from 'antd'
import { CloseOutlined, EditOutlined, LoadingOutlined, PictureOutlined, SaveOutlined, UserOutlined } from '@ant-design/icons'
import type { Character } from '../../types/scene'
import { useSceneStore } from '../../stores/sceneStore'
import { generatePortrait } from '../../api/scenes'
import { getApiErrorMessage } from '../../utils/error'

interface Props {
  characters: Character[]
}

interface CharacterDraft {
  name: string
  appearance: string
  personality: string
  costume: string
  reference_image_url: string
}

export default function CharacterPanel({ characters }: Props) {
  const { updateCharacter } = useSceneStore()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<CharacterDraft | null>(null)
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set())
  const { message } = AntdApp.useApp()

  const handleGeneratePortrait = async (char: Character) => {
    setGeneratingIds((prev) => new Set(prev).add(char.id))
    try {
      const updated = await generatePortrait(char.id)
      useSceneStore.setState((state) => ({
        characters: state.characters.map((c) => (c.id === char.id ? updated : c)),
      }))
      message.success(`角色「${char.name}」立绘生成成功`)
    } catch (error) {
      message.error(getApiErrorMessage(error, '立绘生成失败'))
    } finally {
      setGeneratingIds((prev) => {
        const next = new Set(prev)
        next.delete(char.id)
        return next
      })
    }
  }

  const isGeneratingAny = generatingIds.size > 0

  const handleGenerateAll = async () => {
    let successCount = 0
    let failCount = 0
    for (const char of characters) {
      setGeneratingIds((prev) => new Set(prev).add(char.id))
      try {
        const updated = await generatePortrait(char.id)
        useSceneStore.setState((state) => ({
          characters: state.characters.map((c) => (c.id === char.id ? updated : c)),
        }))
        successCount++
      } catch {
        failCount++
      } finally {
        setGeneratingIds((prev) => {
          const next = new Set(prev)
          next.delete(char.id)
          return next
        })
      }
    }
    if (failCount === 0) {
      message.success(`全部 ${successCount} 个角色立绘生成完成`)
    } else {
      message.warning(`立绘生成完成：${successCount} 成功，${failCount} 失败`)
    }
  }

  const editingCharacter = useMemo(
    () => characters.find((item) => item.id === editingId) ?? null,
    [characters, editingId],
  )

  const startEdit = (character: Character) => {
    setEditingId(character.id)
    setDraft({
      name: character.name,
      appearance: character.appearance ?? '',
      personality: character.personality ?? '',
      costume: character.costume ?? '',
      reference_image_url: character.reference_image_url ?? '',
    })
  }

  const cancelEdit = () => {
    setEditingId(null)
    setDraft(null)
  }

  const patchDraft = (patch: Partial<CharacterDraft>) => {
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  const saveEdit = async () => {
    if (!editingCharacter || !draft) return

    const normalizedName = draft.name.trim()
    if (!normalizedName) {
      message.error('角色姓名不能为空')
      return
    }

    try {
      await updateCharacter(editingCharacter.id, {
        name: normalizedName,
        appearance: draft.appearance.trim() || null,
        personality: draft.personality.trim() || null,
        costume: draft.costume.trim() || null,
        reference_image_url: draft.reference_image_url.trim() || null,
      })
      message.success('角色信息已更新')
      cancelEdit()
    } catch (error) {
      message.error(getApiErrorMessage(error, '角色更新失败'))
    }
  }

  if (characters.length === 0) {
    return (
      <div className="np-character-panel">
        <h3 style={{ marginBottom: 12, fontFamily: "'Playfair Display', 'Noto Serif SC', serif" }}>
          <UserOutlined style={{ marginRight: 8 }} />
          角色档案 (0)
        </h3>
        <Empty description="暂无角色数据" style={{ border: '1px solid #111', padding: 24 }} />
      </div>
    )
  }

  return (
    <div className="np-character-panel">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontFamily: "'Playfair Display', 'Noto Serif SC', serif" }}>
          <UserOutlined style={{ marginRight: 8 }} />
          角色档案 ({characters.length})
        </h3>
        <Button
          size="small"
          icon={isGeneratingAny ? <LoadingOutlined /> : <PictureOutlined />}
          loading={isGeneratingAny}
          disabled={characters.length === 0}
          onClick={handleGenerateAll}
        >
          一键生成立绘
        </Button>
      </div>
      <div className="np-character-list">
        {characters.map((char) => {
          const isEditing = editingId === char.id && draft !== null

          return (
            <Card
              key={char.id}
              size="small"
              className="np-panel-card"
              extra={isEditing ? (
                <Space>
                  <Button size="small" type="primary" icon={<SaveOutlined />} onClick={saveEdit}>
                    保存
                  </Button>
                  <Button size="small" icon={<CloseOutlined />} onClick={cancelEdit}>
                    取消
                  </Button>
                </Space>
              ) : (
                <Button size="small" icon={<EditOutlined />} onClick={() => startEdit(char)}>
                  编辑
                </Button>
              )}
            >
              {isEditing && draft ? (
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <div>
                    <label style={{ fontWeight: 600 }}>姓名</label>
                    <Input
                      value={draft.name}
                      onChange={(e) => patchDraft({ name: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ fontWeight: 600 }}>外貌</label>
                    <Input.TextArea
                      rows={2}
                      value={draft.appearance}
                      onChange={(e) => patchDraft({ appearance: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ fontWeight: 600 }}>性格</label>
                    <Input.TextArea
                      rows={2}
                      value={draft.personality}
                      onChange={(e) => patchDraft({ personality: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ fontWeight: 600 }}>服装</label>
                    <Input.TextArea
                      rows={2}
                      value={draft.costume}
                      onChange={(e) => patchDraft({ costume: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ fontWeight: 600 }}>参考图链接</label>
                    <Input
                      placeholder="请输入参考图链接（https://）"
                      value={draft.reference_image_url}
                      onChange={(e) => patchDraft({ reference_image_url: e.target.value })}
                    />
                  </div>
                </Space>
              ) : (
                <>
                  {char.portrait_url && (
                    <div style={{ marginBottom: 8, textAlign: 'center' }}>
                      <Image
                        src={char.portrait_url}
                        alt={`${char.name} 立绘`}
                        width={120}
                        style={{ borderRadius: 4, border: '1px solid #333' }}
                        placeholder
                      />
                    </div>
                  )}
                  <Descriptions column={1} size="small" title={<Tag className="np-status-tag">{char.name}</Tag>}>
                    {char.appearance && <Descriptions.Item label="外貌">{char.appearance}</Descriptions.Item>}
                    {char.personality && <Descriptions.Item label="性格">{char.personality}</Descriptions.Item>}
                    {char.costume && <Descriptions.Item label="服装">{char.costume}</Descriptions.Item>}
                    {char.reference_image_url && (
                      <Descriptions.Item label="参考图">
                        <Typography.Link href={char.reference_image_url} target="_blank" rel="noreferrer">
                          {char.reference_image_url}
                        </Typography.Link>
                      </Descriptions.Item>
                    )}
                  </Descriptions>
                  <div style={{ marginTop: 8 }}>
                    <Button
                      size="small"
                      icon={generatingIds.has(char.id) ? <LoadingOutlined /> : <PictureOutlined />}
                      loading={generatingIds.has(char.id)}
                      onClick={() => handleGeneratePortrait(char)}
                    >
                      {char.portrait_url ? '重新生成立绘' : '生成立绘'}
                    </Button>
                  </div>
                </>
              )}
            </Card>
          )
        })}
      </div>
    </div>
  )
}
