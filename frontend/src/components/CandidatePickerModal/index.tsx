import { useCallback, useEffect, useMemo, useState } from 'react'
import { Modal, Card, Tag, Button, Space, InputNumber, Spin, Empty, App as AntdApp } from 'antd'
import { CheckCircleOutlined, PlusOutlined } from '@ant-design/icons'
import type { CandidateClip } from '../../types/scene'
import { getSceneCandidates, selectCandidate, generateCandidates } from '../../api/generation'
import { getApiErrorMessage } from '../../utils/error'

interface Props {
  open: boolean
  sceneId: string
  sceneTitle: string
  onClose: () => void
  /** 选片操作完成后回调，用于刷新外部场景列表 */
  onSelected?: () => void
}

/** 按 clip_order 分组 */
function groupByClipOrder(clips: CandidateClip[]): Map<number, CandidateClip[]> {
  const map = new Map<number, CandidateClip[]>()
  for (const clip of clips) {
    const group = map.get(clip.clip_order) ?? []
    group.push(clip)
    map.set(clip.clip_order, group)
  }
  return map
}

export default function CandidatePickerModal({ open, sceneId, sceneTitle, onClose, onSelected }: Props) {
  const [clips, setClips] = useState<CandidateClip[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [selectingId, setSelectingId] = useState<string | null>(null)
  const [candidateCount, setCandidateCount] = useState(3)
  const { message } = AntdApp.useApp()

  const fetchCandidates = useCallback(async () => {
    if (!sceneId) return
    setLoading(true)
    try {
      const data = await getSceneCandidates(sceneId)
      setClips(data)
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载候选列表失败'))
    } finally {
      setLoading(false)
    }
  }, [sceneId, message])

  useEffect(() => {
    if (open && sceneId) {
      fetchCandidates()
    }
  }, [open, sceneId, fetchCandidates])

  const grouped = useMemo(() => groupByClipOrder(clips), [clips])

  const handleSelect = async (clipId: string) => {
    setSelectingId(clipId)
    try {
      await selectCandidate(sceneId, clipId)
      // 更新本地状态：同组内切换 is_selected
      setClips((prev) => {
        const target = prev.find((c) => c.id === clipId)
        if (!target) return prev
        return prev.map((c) => {
          if (c.clip_order === target.clip_order) {
            return { ...c, is_selected: c.id === clipId }
          }
          return c
        })
      })
      message.success('已选择候选')
      onSelected?.()
    } catch (error) {
      message.error(getApiErrorMessage(error, '选择候选失败'))
    } finally {
      setSelectingId(null)
    }
  }

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const result = await generateCandidates(sceneId, candidateCount)
      message.success(`生成完成：${result.generated} 成功，${result.failed} 失败`)
      await fetchCandidates()
      onSelected?.()
    } catch (error) {
      message.error(getApiErrorMessage(error, '生成候选失败'))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Modal
      title={`场景选片 · ${sceneTitle}`}
      open={open}
      onCancel={onClose}
      width={860}
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <InputNumber
              min={1}
              max={10}
              value={candidateCount}
              onChange={(v) => setCandidateCount(v ?? 3)}
              size="small"
              style={{ width: 60 }}
            />
            <Button
              icon={<PlusOutlined />}
              onClick={handleGenerate}
              loading={generating}
              disabled={generating}
            >
              生成更多候选
            </Button>
          </Space>
          <Button onClick={onClose}>关闭</Button>
        </div>
      }
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : clips.length === 0 ? (
        <Empty description="暂无候选片段，请先生成候选" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {[...grouped.entries()].map(([clipOrder, candidates]) => (
            <div key={clipOrder}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>
                片段 #{clipOrder + 1}
                <span style={{ fontWeight: 400, color: 'var(--np-text-soft)', marginLeft: 8 }}>
                  ({candidates.length} 个候选)
                </span>
              </div>
              <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
                {candidates.map((clip) => (
                  <Card
                    key={clip.id}
                    size="small"
                    style={{
                      minWidth: 200,
                      flex: '0 0 200px',
                      border: clip.is_selected
                        ? '2px solid var(--np-success)'
                        : '1px solid var(--np-frame-line)',
                      cursor: clip.status === 'completed' ? 'pointer' : 'default',
                      opacity: clip.status === 'failed' ? 0.6 : 1,
                    }}
                    onClick={() => {
                      if (clip.status === 'completed' && !clip.is_selected && !selectingId) {
                        handleSelect(clip.id)
                      }
                    }}
                    loading={selectingId === clip.id}
                  >
                    <div style={{ marginBottom: 8 }}>
                      <Space size={4}>
                        <Tag className="np-status-tag" style={{ fontSize: 10 }}>
                          候选 {String.fromCharCode(65 + clip.candidate_index)}
                        </Tag>
                        <Tag className={`np-status-tag np-status-${clip.status}`} style={{ fontSize: 10 }}>
                          {clip.status === 'completed' ? '已完成' : clip.status === 'failed' ? '失败' : clip.status}
                        </Tag>
                      </Space>
                    </div>
                    {clip.media_url && clip.status === 'completed' ? (
                      <video
                        controls
                        preload="metadata"
                        className="np-asset-video"
                        src={clip.media_url}
                        style={{ width: '100%', maxHeight: 140 }}
                      />
                    ) : (
                      <div style={{
                        width: '100%',
                        height: 100,
                        background: '#000',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#999',
                        fontSize: 12,
                      }}>
                        {clip.status === 'failed' ? '生成失败' : '无预览'}
                      </div>
                    )}
                    <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 12, color: 'var(--np-text-soft)' }}>
                        {clip.duration_seconds.toFixed(1)}s
                      </span>
                      {clip.is_selected && (
                        <Tag className="np-status-tag np-status-completed" icon={<CheckCircleOutlined />} style={{ fontSize: 10, margin: 0 }}>
                          已选中
                        </Tag>
                      )}
                    </div>
                    {clip.error_message && (
                      <div style={{ marginTop: 4, fontSize: 11, color: 'var(--np-error)' }}>
                        {clip.error_message}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
