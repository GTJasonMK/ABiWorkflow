import { useState } from 'react'
import { Button, Image, List, Space, Tag, Tooltip, Typography, App as AntdApp } from 'antd'
import { generatePanelVoiceLines, submitPanelLipsync, submitPanelVideo } from '../../api/panels'
import type { Episode } from '../../types/episode'
import type { Panel } from '../../types/panel'
import { summarizePanelBinding } from '../../utils/panelBinding'
import PanelStatusTag from '../../components/PanelStatusTag'
import { getApiErrorMessage } from '../../utils/error'

const { Text } = Typography
type PanelSubmitMode = 'video' | 'tts' | 'lipsync'

interface PanelGenerationCardProps {
  episode: Episode | null
  panels: Panel[]
  onRefresh: () => Promise<void>
}

export default function PanelGenerationCard({ episode, panels, onRefresh }: PanelGenerationCardProps) {
  const [submittingAction, setSubmittingAction] = useState<{ panelId: string; mode: PanelSubmitMode } | null>(null)
  const { message } = AntdApp.useApp()

  const handleSubmitTask = async (panel: Panel, mode: PanelSubmitMode) => {
    setSubmittingAction({ panelId: panel.id, mode })
    try {
      const result = mode === 'video'
        ? await submitPanelVideo(panel.id, { payload: {} })
        : mode === 'tts'
          ? await generatePanelVoiceLines(panel.id, { payload: {} })
          : await submitPanelLipsync(panel.id, { payload: {} })
      const task = (result.task ?? {}) as { id?: string; source_task_id?: string }
      const taskName = task.id || task.source_task_id || '未知'
      const modeLabel = mode === 'video' ? '视频' : mode === 'tts' ? '语音' : '口型同步'
      message.success(`${modeLabel}任务已提交：${taskName}`)
      await onRefresh()
    } catch (error) {
      const fallback = mode === 'video' ? '提交视频生成失败' : mode === 'tts' ? '提交语音生成失败' : '提交口型同步失败'
      message.error(getApiErrorMessage(error, fallback))
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
            const binding = summarizePanelBinding(panel)
            const promptPreview = (binding.effectivePrompt ?? '').trim()
            const referenceImageUrl = binding.effectiveReferenceImageUrl ?? null
            const videoProviderReady = Boolean(episode?.video_provider_key)
            const ttsProviderReady = Boolean(episode?.tts_provider_key)
            const lipsyncProviderReady = Boolean(episode?.lipsync_provider_key)

            return (
              <List.Item
                actions={[
                  <Tooltip
                    key="video-tip"
                    title={!videoProviderReady
                      ? '当前分集未配置视频 Provider'
                      : (!panel.visual_prompt && !panel.script_text)
                        ? '缺少 visual_prompt / script_text'
                        : '提交视频生成任务'}
                  >
                    <span>
                      <Button
                        size="small"
                        type="primary"
                        loading={submittingAction?.panelId === panel.id && submittingAction.mode === 'video'}
                        disabled={!videoProviderReady || (!panel.visual_prompt && !panel.script_text)}
                        onClick={() => { void handleSubmitTask(panel, 'video') }}
                        aria-label={`为分镜"${panel.title}"生成视频`}
                      >
                        视频
                      </Button>
                    </span>
                  </Tooltip>,
                  <Tooltip
                    key="tts-tip"
                    title={!ttsProviderReady
                      ? '当前分集未配置语音 Provider'
                      : (!panel.tts_text && !panel.script_text)
                        ? '缺少 tts_text / script_text'
                        : '提交语音生成任务'}
                  >
                    <span>
                      <Button
                        size="small"
                        loading={submittingAction?.panelId === panel.id && submittingAction.mode === 'tts'}
                        disabled={!ttsProviderReady || (!panel.tts_text && !panel.script_text)}
                        onClick={() => { void handleSubmitTask(panel, 'tts') }}
                        aria-label={`为分镜"${panel.title}"生成语音`}
                      >
                        语音
                      </Button>
                    </span>
                  </Tooltip>,
                  <Tooltip
                    key="lipsync-tip"
                    title={!lipsyncProviderReady
                      ? '当前分集未配置口型同步 Provider'
                      : (!panel.video_url || !panel.tts_audio_url)
                        ? '口型同步需要 video_url + tts_audio_url'
                        : '提交口型同步任务'}
                  >
                    <span>
                      <Button
                        size="small"
                        loading={submittingAction?.panelId === panel.id && submittingAction.mode === 'lipsync'}
                        disabled={!lipsyncProviderReady || !panel.video_url || !panel.tts_audio_url}
                        onClick={() => { void handleSubmitTask(panel, 'lipsync') }}
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
                    <Tag className="np-status-tag">视频阶段</Tag>
                    <PanelStatusTag status={panel.video_status} />
                    <Tag className="np-status-tag">语音阶段</Tag>
                    <PanelStatusTag status={panel.tts_status} />
                    <Tag className="np-status-tag">口型阶段</Tag>
                    <PanelStatusTag status={panel.lipsync_status} />
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
    </>
  )
}
