import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Empty,
  Input,
  Segmented,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
} from 'antd'
import { ArrowRightOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { useProjectStore } from '../../stores/projectStore'
import { getApiErrorMessage } from '../../utils/error'
import { buildWorkflowStepPath } from '../../utils/workflow'
import { listEpisodes } from '../../api/episodes'
import type { Episode } from '../../types/episode'
import ScriptAssetConsole from '../ScriptInput/ScriptAssetConsole'
import {
  createGlobalCharacter,
  createGlobalLocation,
  generateAssetDraftFromPanel,
  renderGlobalCharacterReference,
  renderGlobalLocationReference,
} from '../../api/assetHub'
import { createScriptEntity, listScriptEntities, replaceScriptEntityBindings } from '../../api/scriptAssets'
import { bindingMatchesEpisode } from '../../utils/scriptAssetScope'
import type { ScriptAssetBinding, ScriptEntity } from '../../types/scriptAssets'

const { Text, Paragraph } = Typography
const { TextArea } = Input

type PromptAssetType = 'character' | 'location'
type BindingMode = 'direct' | 'generate'

interface DraftFormState {
  name: string
  description: string
  prompt_template: string
}

type GenerationErrorStage = 'draft' | 'create'

interface EpisodeBindingProgress {
  characterBound: number
  locationBound: number
  ready: boolean
  label: string
  className: string
}

function resolveEpisodeBindingProgress(episode: Episode, entities: ScriptEntity[]): EpisodeBindingProgress {
  const scriptLength = (episode.script_text || '').trim().length
  const characterBound = entities.filter((item) => (
    item.entity_type === 'character'
    && item.bindings.some((binding) => binding.asset_type === 'character' && bindingMatchesEpisode(binding, episode.id))
  )).length
  const locationBound = entities.filter((item) => (
    item.entity_type === 'location'
    && item.bindings.some((binding) => binding.asset_type === 'location' && bindingMatchesEpisode(binding, episode.id))
  )).length

  if (scriptLength <= 0) {
    return {
      characterBound,
      locationBound,
      ready: false,
      label: '待填充',
      className: 'np-status-tag is-unbound',
    }
  }
  if (characterBound <= 0 && locationBound <= 0) {
    return {
      characterBound,
      locationBound,
      ready: false,
      label: '待绑定',
      className: 'np-status-tag np-status-failed',
    }
  }
  if (characterBound <= 0 || locationBound <= 0) {
    return {
      characterBound,
      locationBound,
      ready: false,
      label: '部分绑定',
      className: 'np-status-tag',
    }
  }
  return {
    characterBound,
    locationBound,
    ready: true,
    label: '绑定完成',
    className: 'np-status-tag np-status-completed',
  }
}

export default function AssetBinding() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const scopedEpisodeId = (searchParams.get('episodeId') || '').trim() || null
  const { currentProject, fetchProject } = useProjectStore()
  const { message, modal } = AntdApp.useApp()

  const [loading, setLoading] = useState(false)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [assetType, setAssetType] = useState<PromptAssetType>('character')
  const [bindingMode, setBindingMode] = useState<BindingMode>('direct')
  const [draftLoading, setDraftLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [renderReference, setRenderReference] = useState(true)
  const [draftForm, setDraftForm] = useState<DraftFormState>({
    name: '',
    description: '',
    prompt_template: '',
  })
  const [entityRows, setEntityRows] = useState<ScriptEntity[]>([])
  const [consoleVersion, setConsoleVersion] = useState(0)
  const [consoleFocusSignal, setConsoleFocusSignal] = useState(0)
  const [showManualConsole, setShowManualConsole] = useState(true)
  const [lastCreatedAssetName, setLastCreatedAssetName] = useState('')
  const [generationError, setGenerationError] = useState<{
    stage: GenerationErrorStage
    message: string
  } | null>(null)

  const selectedEpisode = useMemo(() => {
    if (!scopedEpisodeId) return null
    return episodes.find((item) => item.id === scopedEpisodeId) ?? null
  }, [episodes, scopedEpisodeId])
  const contextEpisodeId = selectedEpisode?.id ?? null
  const selectedEpisodeProgress = useMemo(() => {
    if (!selectedEpisode) return null
    return resolveEpisodeBindingProgress(selectedEpisode, entityRows)
  }, [entityRows, selectedEpisode])
  const missingChecklist = useMemo(() => {
    if (!selectedEpisode || !selectedEpisodeProgress) return []
    const missing: string[] = []
    if ((selectedEpisode.script_text || '').trim().length <= 0) {
      missing.push('分集正文为空')
    }
    if (selectedEpisodeProgress.characterBound <= 0) {
      missing.push('未绑定角色实体')
    }
    if (selectedEpisodeProgress.locationBound <= 0) {
      missing.push('未绑定地点实体')
    }
    return missing
  }, [selectedEpisode, selectedEpisodeProgress])
  const generationPhase = useMemo<'idle' | 'drafting' | 'review' | 'creating' | 'done'>(() => {
    if (draftLoading) return 'drafting'
    if (creating) return 'creating'
    if (lastCreatedAssetName) return 'done'
    if (draftForm.name.trim() || draftForm.prompt_template.trim() || draftForm.description.trim()) return 'review'
    return 'idle'
  }, [creating, draftForm.description, draftForm.name, draftForm.prompt_template, draftLoading, lastCreatedAssetName])
  const canCreateAndBind = useMemo(() => {
    return draftForm.name.trim().length > 0 && draftForm.prompt_template.trim().length > 0
  }, [draftForm.name, draftForm.prompt_template])
  const hasDraftSeed = useMemo(() => {
    return (
      draftForm.name.trim().length > 0
      || draftForm.prompt_template.trim().length > 0
      || draftForm.description.trim().length > 0
    )
  }, [draftForm.description, draftForm.name, draftForm.prompt_template])

  const loadData = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      await fetchProject(projectId)
      const [episodeRows, entities] = await Promise.all([
        listEpisodes(projectId),
        listScriptEntities(projectId),
      ])
      const sortedEpisodes = [...episodeRows].sort((a, b) => a.episode_order - b.episode_order)
      setEpisodes(sortedEpisodes)
      setEntityRows(entities)
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载资产绑定上下文失败'))
    } finally {
      setLoading(false)
    }
  }, [fetchProject, message, projectId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  useEffect(() => {
    setDraftForm({
      name: '',
      description: '',
      prompt_template: '',
    })
    setLastCreatedAssetName('')
    setGenerationError(null)
  }, [selectedEpisode?.id])

  useEffect(() => {
    setShowManualConsole(bindingMode === 'direct')
  }, [bindingMode])

  const refreshEntities = useCallback(async () => {
    if (!projectId) return
    const latest = await listScriptEntities(projectId)
    setEntityRows(latest)
  }, [projectId])

  const handleGenerateDraft = async () => {
    if (!selectedEpisode) {
      message.warning('请先选择分集')
      return
    }
    const scriptText = (selectedEpisode.script_text || '').trim()
    if (!scriptText) {
      message.warning('当前分集正文为空，无法生成提示词草案')
      return
    }
    setDraftLoading(true)
    setLastCreatedAssetName('')
    setGenerationError(null)
    try {
      const draft = await generateAssetDraftFromPanel({
        asset_type: assetType,
        panel_title: selectedEpisode.title,
        script_text: scriptText,
      })
      setDraftForm({
        name: (draft.name || '').trim(),
        description: (draft.description || '').trim(),
        prompt_template: (draft.prompt_template || '').trim(),
      })
      setGenerationError(null)
      message.success(`已生成${assetType === 'character' ? '角色' : '地点'}草案，可微调后创建`)
    } catch (error) {
      const errorMessage = getApiErrorMessage(error, `生成${assetType === 'character' ? '角色' : '地点'}草案失败`)
      setGenerationError({ stage: 'draft', message: errorMessage })
      message.error(errorMessage)
    } finally {
      setDraftLoading(false)
    }
  }

  const upsertEntityBinding = useCallback(async (
    type: PromptAssetType,
    payload: { assetId: string; assetName: string; description: string; entityName: string },
  ) => {
    if (!projectId || !selectedEpisode) return
    const entityType = type === 'character' ? 'character' : 'location'
    const binding: ScriptAssetBinding = {
      asset_type: type,
      asset_id: payload.assetId,
      asset_name: payload.assetName,
      priority: 0,
      is_primary: true,
      strategy: {
        source: 'asset_binding_page',
        episode_id: selectedEpisode.id,
      },
    }

    const latest = await listScriptEntities(projectId)
    const hit = latest.find((item) => (
      item.entity_type === entityType && item.name.trim() === payload.entityName.trim()
    ))
    if (hit) {
      const kept = hit.bindings.filter((item) => !(item.asset_type === type && item.asset_id === payload.assetId))
      const next = [
        binding,
        ...kept.map((item, index) => ({ ...item, priority: index + 1, is_primary: false })),
      ]
      await replaceScriptEntityBindings(hit.id, next)
      return
    }

    await createScriptEntity(projectId, {
      entity_type: entityType,
      name: payload.entityName,
      description: payload.description || null,
      bindings: [binding],
    })
  }, [projectId, selectedEpisode])

  const handleCreateAndBind = async () => {
    if (!projectId || !selectedEpisode) return
    const entityName = draftForm.name.trim()
    const promptTemplate = draftForm.prompt_template.trim()
    if (!entityName || !promptTemplate) {
      message.warning('请先完善名称和提示词后再创建')
      return
    }
    setCreating(true)
    setGenerationError(null)
    try {
      if (assetType === 'character') {
        const created = await createGlobalCharacter({
          name: entityName,
          project_id: projectId,
          description: draftForm.description.trim() || undefined,
          prompt_template: promptTemplate,
          tags: [`episode:${selectedEpisode.episode_order + 1}`],
        })
        if (renderReference) {
          await renderGlobalCharacterReference(created.id)
        }
        await upsertEntityBinding('character', {
          assetId: created.id,
          assetName: created.name,
          description: draftForm.description.trim(),
          entityName,
        })
      } else {
        const created = await createGlobalLocation({
          name: entityName,
          project_id: projectId,
          description: draftForm.description.trim() || undefined,
          prompt_template: promptTemplate,
          tags: [`episode:${selectedEpisode.episode_order + 1}`],
        })
        if (renderReference) {
          await renderGlobalLocationReference(created.id)
        }
        await upsertEntityBinding('location', {
          assetId: created.id,
          assetName: created.name,
          description: draftForm.description.trim(),
          entityName,
        })
      }

      await refreshEntities()
      setConsoleVersion((prev) => prev + 1)
      setLastCreatedAssetName(entityName)
      setGenerationError(null)
      message.success(`已创建并绑定${assetType === 'character' ? '角色' : '地点'}资产`)
    } catch (error) {
      const errorMessage = getApiErrorMessage(error, `创建并绑定${assetType === 'character' ? '角色' : '地点'}资产失败`)
      setGenerationError({ stage: 'create', message: errorMessage })
      message.error(errorMessage)
    } finally {
      setCreating(false)
    }
  }

  const handleGoNext = () => {
    if (!projectId || !selectedEpisode) return
    if (!selectedEpisodeProgress?.ready) {
      message.warning('当前仍有缺失项，如需继续请使用“跳过检查继续”')
      return
    }
    navigate(buildWorkflowStepPath(projectId, 'scenes', selectedEpisode.id))
  }

  const handleForceGoNext = () => {
    if (!projectId || !selectedEpisode) return
    if (selectedEpisodeProgress?.ready) {
      navigate(buildWorkflowStepPath(projectId, 'scenes', selectedEpisode.id))
      return
    }
    modal.confirm({
      title: '确认跳过资产检查并继续？',
      content: (
        <Space direction="vertical" size={4}>
          <Text>当前分集仍有缺失项：</Text>
          <Text type="secondary">{missingChecklist.join('、') || '未满足角色/地点绑定要求'}</Text>
          <Text type="secondary">你仍可在分镜编辑中继续补充，但可能导致返工。</Text>
        </Space>
      ),
      okText: '确认继续',
      okButtonProps: { danger: true },
      cancelText: '返回完善',
      onOk: () => {
        navigate(buildWorkflowStepPath(projectId, 'scenes', selectedEpisode.id))
      },
    })
  }

  if (loading && !currentProject) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="资产绑定"
        title={`${currentProject?.name ?? ''} · 角色/地点资产绑定`}
        subtitle="当前页面仅处理已选分集，完成角色/地点绑定后进入分镜编辑。"
        onBack={() => navigate(`/projects/${projectId}/script`)}
        backLabel="返回剧本分集"
        navigation={<WorkflowSteps episodeIdOverride={contextEpisodeId} />}
        actions={(
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => { void loadData() }} loading={loading}>
              刷新
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll np-asset-binding-scroll">
        <div className="np-asset-binding-main">
          {!scopedEpisodeId ? (
            <Card size="small" className="np-panel-card">
              <Empty description="缺少分集上下文，请返回剧本分集后从目标分集进入资产绑定。" />
            </Card>
          ) : episodes.length <= 0 ? (
            <Card size="small" className="np-panel-card">
              <Empty description="暂无分集，请先回剧本页导入并切分剧本" />
            </Card>
          ) : !selectedEpisode ? (
            <Card size="small" className="np-panel-card">
              <Empty description="当前分集不存在或已删除，请返回剧本分集重新选择。" />
            </Card>
          ) : (
            <>
              <Card size="small" className="np-panel-card" title={`当前分集：${selectedEpisode.title}`}>
                <Space size={8} wrap style={{ marginBottom: 10 }}>
                  <Tag className="np-status-tag">角色实体已绑定：{selectedEpisodeProgress?.characterBound ?? 0}</Tag>
                  <Tag className="np-status-tag">地点实体已绑定：{selectedEpisodeProgress?.locationBound ?? 0}</Tag>
                  <Tag className={selectedEpisodeProgress?.className ?? 'np-status-tag'}>
                    状态：{selectedEpisodeProgress?.label ?? '待绑定'}
                  </Tag>
                </Space>
                <Paragraph className="np-asset-binding-script-preview">
                  {(selectedEpisode.script_text || '').trim() || '当前分集正文为空，请回剧本页补充内容。'}
                </Paragraph>
                {selectedEpisodeProgress?.ready ? (
                  <Alert
                    style={{ marginTop: 10 }}
                    type="success"
                    showIcon
                    message="当前分集已满足进入下一步条件"
                  />
                ) : (
                  <Alert
                    style={{ marginTop: 10 }}
                    type="warning"
                    showIcon
                    message={`尚未完成：${missingChecklist.join('、') || '请补齐绑定信息'}`}
                  />
                )}
              </Card>

              <Card size="small" className="np-panel-card" title="绑定操作">
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <div className="np-asset-binding-mode-row">
                    <Space wrap size={8}>
                      <Text strong>绑定模式</Text>
                      <Segmented
                        value={bindingMode}
                        options={[
                          { label: '直接绑定', value: 'direct' },
                          { label: '先生成再绑定', value: 'generate' },
                        ]}
                        onChange={(value) => setBindingMode(value as BindingMode)}
                      />
                    </Space>
                    <Tag className={selectedEpisodeProgress?.className ?? 'np-status-tag'}>
                      分集状态：{selectedEpisodeProgress?.label ?? '待绑定'}
                    </Tag>
                  </div>

                  {bindingMode === 'direct' ? (
                    <Alert
                      type="info"
                      showIcon
                      message="直接绑定现有资产"
                      description="在下方资产规划台按实体绑定，可在角色/地点标签间切换，适合已有素材场景。"
                      action={(
                        <Button
                          onClick={() => {
                            setShowManualConsole(true)
                            setConsoleFocusSignal((prev) => prev + 1)
                          }}
                        >
                          定位到规划台
                        </Button>
                      )}
                    />
                  ) : (
                    <div className="np-asset-generation-shell">
                      <div className="np-asset-generation-section">
                        <Space wrap size={8}>
                          <Text strong>生成目标</Text>
                          <Segmented
                            value={assetType}
                            options={[
                              { label: '角色', value: 'character' },
                              { label: '地点', value: 'location' },
                            ]}
                            onChange={(value) => setAssetType(value as PromptAssetType)}
                          />
                        </Space>
                        <Space wrap>
                          <Text strong>阶段1：生成草案（LLM）</Text>
                          <Tag className={`np-status-tag${generationPhase === 'idle' ? '' : ' np-status-completed'}`}>
                            {generationPhase === 'drafting' ? '草案生成中' : '草案阶段'}
                          </Tag>
                        </Space>
                        <Text type="secondary">根据当前分集正文生成资产名称、描述和提示词草案。</Text>
                        <Space wrap>
                          <Switch
                            checked={renderReference}
                            onChange={setRenderReference}
                            checkedChildren="生成参考图"
                            unCheckedChildren="仅建资产"
                          />
                          <Button
                            icon={<ThunderboltOutlined />}
                            onClick={() => { void handleGenerateDraft() }}
                            loading={draftLoading}
                          >
                            生成提示词草案
                          </Button>
                        </Space>
                        {generationError?.stage === 'draft' ? (
                          <Alert
                            type="error"
                            showIcon
                            message="草案生成失败"
                            description={generationError.message}
                            action={(
                              <Button
                                size="small"
                                onClick={() => { void handleGenerateDraft() }}
                                loading={draftLoading}
                              >
                                重试生成
                              </Button>
                            )}
                          />
                        ) : null}
                      </div>

                      <div className="np-asset-generation-section">
                        <Space wrap>
                          <Text strong>阶段2：确认并创建绑定</Text>
                          {hasDraftSeed ? <Tag className="np-status-tag np-status-generated">已生成草案</Tag> : null}
                        </Space>
                        <Text strong>资产名称</Text>
                        <Input
                          value={draftForm.name}
                          onChange={(event) => setDraftForm((prev) => ({ ...prev, name: event.target.value }))}
                          placeholder="资产名称"
                        />
                        <Text strong>资产描述（可选）</Text>
                        <Input
                          value={draftForm.description}
                          onChange={(event) => setDraftForm((prev) => ({ ...prev, description: event.target.value }))}
                          placeholder="资产描述（可选）"
                        />
                        <Text strong>提示词模板</Text>
                        <TextArea
                          rows={4}
                          value={draftForm.prompt_template}
                          onChange={(event) => setDraftForm((prev) => ({ ...prev, prompt_template: event.target.value }))}
                          placeholder="提示词模板"
                        />
                        <Space wrap>
                          <Button
                            type="primary"
                            onClick={() => { void handleCreateAndBind() }}
                            loading={creating}
                            disabled={!canCreateAndBind}
                          >
                            创建资产并绑定到当前分集
                          </Button>
                          <Button
                            onClick={() => {
                              setDraftForm({ name: '', description: '', prompt_template: '' })
                              setGenerationError(null)
                              setLastCreatedAssetName('')
                            }}
                            disabled={!hasDraftSeed && !generationError}
                          >
                            清空草案
                          </Button>
                        </Space>
                        {!canCreateAndBind ? (
                          <Text type="secondary">请至少填写“资产名称 + 提示词模板”后再创建。</Text>
                        ) : null}
                        {generationError?.stage === 'create' ? (
                          <Alert
                            type="error"
                            showIcon
                            message="创建并绑定失败"
                            description={generationError.message}
                            action={(
                              <Button
                                size="small"
                                onClick={() => { void handleCreateAndBind() }}
                                loading={creating}
                              >
                                重试创建绑定
                              </Button>
                            )}
                          />
                        ) : null}
                        {lastCreatedAssetName ? (
                          <Text type="secondary">
                            最近完成：{lastCreatedAssetName}（{assetType === 'character' ? '角色' : '地点'}）
                          </Text>
                        ) : null}
                      </div>
                    </div>
                  )}

                  {bindingMode === 'generate' ? (
                    <Space wrap>
                      <Button size="small" onClick={() => setShowManualConsole((prev) => !prev)}>
                        {showManualConsole ? '收起手动绑定区（高级）' : '展开手动绑定区（高级）'}
                      </Button>
                      <Text type="secondary">自动生成不理想时，再展开手动绑定区进行精修。</Text>
                    </Space>
                  ) : null}
                </Space>
              </Card>

              {projectId ? (
                bindingMode === 'generate' && !showManualConsole ? (
                  <Card size="small" className="np-panel-card np-asset-binding-console-placeholder">
                    <Text type="secondary">手动绑定区已收起。需要时可在上方展开。</Text>
                  </Card>
                ) : (
                  <ScriptAssetConsole
                    projectId={projectId}
                    enabledTypes={['character', 'location']}
                    initialType={assetType}
                    refreshSignal={consoleVersion}
                    focusSignal={consoleFocusSignal}
                    scopeEpisodeId={selectedEpisode.id}
                    enforceEpisodeScope
                    embedded
                    onEntitiesChange={setEntityRows}
                  />
                )
              ) : null}

              <div className="np-asset-binding-footer-bar">
                <Space size={8} wrap>
                  <Tag className={selectedEpisodeProgress?.className ?? 'np-status-tag'}>
                    当前状态：{selectedEpisodeProgress?.label ?? '待绑定'}
                  </Tag>
                  {missingChecklist.length > 0 ? (
                    <Text type="secondary">缺失项：{missingChecklist.join('、')}</Text>
                  ) : (
                    <Text type="secondary">已满足进入分镜编辑条件</Text>
                  )}
                </Space>
                <Space wrap>
                  <Button
                    danger
                    onClick={handleForceGoNext}
                    disabled={!projectId || !selectedEpisode || missingChecklist.length <= 0}
                  >
                    跳过检查继续
                  </Button>
                  <Button
                    type="primary"
                    icon={<ArrowRightOutlined />}
                    onClick={handleGoNext}
                    disabled={!projectId || !selectedEpisode}
                  >
                    下一步：分镜编辑
                  </Button>
                </Space>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
