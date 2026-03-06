import { useState } from 'react'
import { Button, Image, List, Space, Tag, Tooltip, Typography, App as AntdApp } from 'antd'
import { generatePanelVoiceLines, submitPanelLipsync, submitPanelVideo } from '../../api/panels'
import type { Panel } from '../../types/panel'
import PanelStatusTag from '../../components/PanelStatusTag'
import ProviderKeyPromptModal from '../../components/ProviderKeyPromptModal'
import { getApiErrorMessage } from '../../utils/error'

const { Text } = Typography
type PanelSubmitMode = 'video' | 'tts' | 'lipsync'

interface PanelGenerationCardProps {
  panels: Panel[]
  onRefresh: () => Promise<void>
}

interface PanelAssetBindingView {
  characterNames: string[]
  locationNames: string[]
  voiceName?: string
  voiceId?: string
  effectivePrompt?: string
  effectiveReferenceImageUrl?: string
  compiled: boolean
}

function parsePanelAssetBinding(panel: Panel): PanelAssetBindingView {
  const effective = panel.effective_binding
  if (!effective || typeof effective !== 'object') {
    return {
      characterNames: [],
      locationNames: [],
      compiled: false,
    }
  }
  const source = effective as unknown as Record<string, unknown>
  const chars = Array.isArray(source.characters) ? source.characters : []
  const locations = Array.isArray(source.locations) ? source.locations : []
  const effectiveVoice = (source.effective_voice && typeof source.effective_voice === 'object' && !Array.isArray(source.effective_voice))
    ? source.effective_voice as Record<string, unknown>
    : null
  const characterNames = chars
    .map((item) => (item && typeof item === 'object' ? (item as Record<string, unknown>).asset_name : null))
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
  const locationNames = locations
    .map((item) => (item && typeof item === 'object' ? (item as Record<string, unknown>).asset_name : null))
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
  return {
    characterNames,
    locationNames,
    voiceName: typeof effectiveVoice?.voice_name === 'string' ? effectiveVoice.voice_name : undefined,
    voiceId: typeof effectiveVoice?.voice_id === 'string' ? effectiveVoice.voice_id : undefined,
    effectivePrompt: typeof source.effective_visual_prompt === 'string' ? source.effective_visual_prompt : undefined,
    effectiveReferenceImageUrl: typeof source.effective_reference_image_url === 'string' ? source.effective_reference_image_url : undefined,
    compiled: true,
  }
}

export default function PanelGenerationCard({ panels, onRefresh }: PanelGenerationCardProps) {
  const [submittingAction, setSubmittingAction] = useState<{ panelId: string; mode: PanelSubmitMode } | null>(null)
  const [providerPrompt, setProviderPrompt] = useState<{ panel: Panel; mode: PanelSubmitMode } | null>(null)
  const { message } = AntdApp.useApp()

  const handleConfirmPanelProvider = async (providerKey: string) => {
    if (!providerPrompt) return
    const { panel, mode } = providerPrompt

    setSubmittingAction({ panelId: panel.id, mode })
    try {
      const result = mode === 'video'
        ? await submitPanelVideo(panel.id, { provider_key: providerKey, payload: {} })
        : mode === 'tts'
          ? await generatePanelVoiceLines(panel.id, { provider_key: providerKey, payload: {} })
          : await submitPanelLipsync(panel.id, { provider_key: providerKey, payload: {} })
      const task = (result.task ?? {}) as { id?: string; source_task_id?: string }
      const taskName = task.id || task.source_task_id || '未知'
      const modeLabel = mode === 'video' ? '分镜视频' : mode === 'tts' ? '语音' : '口型同步'
      message.success(`${modeLabel}任务已提交：${taskName}`)
      await onRefresh()
      setProviderPrompt(null)
    } catch (error) {
      const fallback = mode === 'video' ? '提交分镜生成失败' : mode === 'tts' ? '提交语音生成失败' : '提交口型同步失败'
      message.error(getApiErrorMessage(error, fallback))
      throw error
    } finally {
      setSubmittingAction(null)
    }
  }

  return (
    <>
      {panels.length === 0 ? (
        <Text type="secondary">该分集暂无分镜数据。</Text>
      ) : (
        <List
          size="small"
          dataSource={panels}
          renderItem={(panel) => {
            const binding = parsePanelAssetBinding(panel)
            const promptPreview = (binding.effectivePrompt || panel.visual_prompt || panel.script_text || '').trim()
            const referenceImageUrl = binding.effectiveReferenceImageUrl || panel.reference_image_url

            return (
              <List.Item
                actions={[
                  <Tooltip
                    key="video-tip"
                    title={(!panel.visual_prompt && !panel.script_text) ? '缺少 visual_prompt / script_text' : '提交分镜视频生成任务'}
                  >
                    <span>
                      <Button
                        size="small"
                        type="primary"
                        loading={submittingAction?.panelId === panel.id && submittingAction.mode === 'video'}
                        disabled={!panel.visual_prompt && !panel.script_text}
                        onClick={() => setProviderPrompt({ panel, mode: 'video' })}
                        aria-label={`为分镜"${panel.title}"生成视频`}
                      >
                        视频
                      </Button>
                    </span>
                  </Tooltip>,
                  <Tooltip
                    key="tts-tip"
                    title={(!panel.tts_text && !panel.script_text) ? '缺少 tts_text / script_text' : '提交语音生成任务'}
                  >
                    <span>
                      <Button
                        size="small"
                        loading={submittingAction?.panelId === panel.id && submittingAction.mode === 'tts'}
                        disabled={!panel.tts_text && !panel.script_text}
                        onClick={() => setProviderPrompt({ panel, mode: 'tts' })}
                        aria-label={`为分镜"${panel.title}"生成语音`}
                      >
                        语音
                      </Button>
                    </span>
                  </Tooltip>,
                  <Tooltip
                    key="lipsync-tip"
                    title={(!panel.video_url || !panel.tts_audio_url) ? '口型同步需要 video_url + tts_audio_url' : '提交口型同步任务'}
                  >
                    <span>
                      <Button
                        size="small"
                        loading={submittingAction?.panelId === panel.id && submittingAction.mode === 'lipsync'}
                        disabled={!panel.video_url || !panel.tts_audio_url}
                        onClick={() => setProviderPrompt({ panel, mode: 'lipsync' })}
                        aria-label={`为分镜"${panel.title}"生成口型同步`}
                      >
                        口型
                      </Button>
                    </span>
                  </Tooltip>,
                ]}
              >
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Space size={8} wrap>
                    <Text>#{panel.panel_order + 1} · {panel.title}</Text>
                    <PanelStatusTag status={panel.status} />
                    <Text type="secondary">{panel.duration_seconds.toFixed(1)} 秒</Text>
                    {panel.video_url && <Tag className="np-status-tag">有视频</Tag>}
                    {panel.tts_audio_url && <Tag className="np-status-tag">有语音</Tag>}
                  </Space>

                  <Space size={8} wrap>
                    <Tag className="np-status-tag">
                      角色：{binding.characterNames.length > 0 ? binding.characterNames.join(' / ') : '未绑定'}
                    </Tag>
                    <Tag className="np-status-tag">
                      地点：{binding.locationNames.length > 0 ? binding.locationNames.join(' / ') : '未绑定'}
                    </Tag>
                    <Tag className="np-status-tag">
                      语音：{binding.voiceName || (binding.voiceId ? `ID:${binding.voiceId.slice(0, 8)}` : '未绑定')}
                    </Tag>
                    <Tag className="np-status-tag">
                      编译状态：{binding.compiled ? '已编译' : '未编译'}
                    </Tag>
                    <Tag className="np-status-tag">
                      参考图：{referenceImageUrl ? '已绑定' : '未绑定'}
                    </Tag>
                  </Space>

                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Text type="secondary">
                      提示词预览：{promptPreview ? `${promptPreview.slice(0, 100)}${promptPreview.length > 100 ? '...' : ''}` : '暂无'}
                    </Text>
                    <Space size={8} align="start" wrap>
                      {panel.video_url ? (
                        <video
                          src={panel.video_url}
                          style={{ width: 120, height: 68, objectFit: 'cover', borderRadius: 8, border: '1px solid #f0f0f0' }}
                          muted
                          preload="metadata"
                        />
                      ) : null}
                      {referenceImageUrl ? (
                        <Space size={8} align="start">
                          <Image
                            src={referenceImageUrl}
                            width={108}
                            style={{ borderRadius: 8, border: '1px solid #f0f0f0' }}
                          />
                          <a href={referenceImageUrl} target="_blank" rel="noreferrer">
                            预览参考图
                          </a>
                        </Space>
                      ) : (
                        <Text type="secondary">无参考图可预览</Text>
                      )}
                    </Space>
                  </Space>
                </Space>
              </List.Item>
            )
          }}
        />
      )}

      <ProviderKeyPromptModal
        open={!!providerPrompt}
        title={
          providerPrompt?.mode === 'video'
            ? '输入分镜视频 Provider Key'
            : providerPrompt?.mode === 'tts'
              ? '输入语音生成 Provider Key'
              : '输入口型同步 Provider Key'
        }
        description={providerPrompt ? `分镜：${providerPrompt.panel.title}` : undefined}
        defaultValue={
          providerPrompt?.mode === 'video'
            ? 'video.ggk'
            : providerPrompt?.mode === 'tts'
              ? 'tts.ggk'
              : 'lipsync.ggk'
        }
        okText="提交"
        cancelText="取消"
        recentStorageKey={
          providerPrompt?.mode === 'video'
            ? 'abi_recent_panel_video_provider_keys'
            : providerPrompt?.mode === 'tts'
              ? 'abi_recent_panel_tts_provider_keys'
              : 'abi_recent_panel_lipsync_provider_keys'
        }
        onCancel={() => setProviderPrompt(null)}
        onConfirm={handleConfirmPanelProvider}
      />
    </>
  )
}
