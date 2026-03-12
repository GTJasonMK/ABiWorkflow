import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Empty,
  Image,
  Input,
  Segmented,
  Space,
  Spin,
  Switch,
  Tag,
  Tabs,
  Typography,
} from 'antd'
import { ArrowRightOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { useProjectWorkspace } from '../../hooks/useProjectWorkspace'
import { getApiErrorMessage } from '../../utils/error'
import { buildWorkflowStepPath } from '../../utils/workflow'
import { listEpisodes, updateEpisode } from '../../api/episodes'
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
import type { GlobalCharacterAsset, GlobalLocationAsset } from '../../types/assetHub'

const { Text, Paragraph } = Typography
const { TextArea } = Input

type PromptAssetType = 'character' | 'location'
type BindingMode = 'direct' | 'generate'
type PromptAssetRecord = GlobalCharacterAsset | GlobalLocationAsset

interface DraftFormState {
  name: string
  description: string
  prompt_template: string
}

type GenerationErrorStage = 'draft' | 'create' | 'render' | 'bind'

type CreatePromptAssetInput = {
  name: string
  project_id: string
  description?: string
  prompt_template: string
  tags: string[]
}

type PromptAssetPreview = {
  id: string
  name: string
  description: string | null
  prompt_template: string | null
  reference_image_url: string | null
  type: PromptAssetType
  isBoundToEpisode: boolean
}

interface PromptAssetWorkspaceState {
  draftLoading: boolean
  creatingAsset: boolean
  bindingCreatedAsset: boolean
  renderingReference: boolean
  renderReference: boolean
  draftForm: DraftFormState
  createdAssetPreview: PromptAssetPreview | null
  generationError: {
    stage: GenerationErrorStage
    message: string
  } | null
}

type PromptAssetConfig = {
  label: string
  boundTagLabel: string
  missingLabel: string
  createAsset: (payload: CreatePromptAssetInput) => Promise<PromptAssetRecord>
  renderReference: (assetId: string) => Promise<PromptAssetRecord>
}

interface EpisodeBindingProgress {
  counts: Record<PromptAssetType, number>
  ready: boolean
  label: string
  className: string
  blockers: string[]
  skipped: boolean
  source: 'workflow' | 'fallback'
}

const EMPTY_DRAFT_FORM: DraftFormState = {
  name: '',
  description: '',
  prompt_template: '',
}

function createEmptyWorkspaceState(): PromptAssetWorkspaceState {
  return {
    draftLoading: false,
    creatingAsset: false,
    bindingCreatedAsset: false,
    renderingReference: false,
    renderReference: true,
    draftForm: { ...EMPTY_DRAFT_FORM },
    createdAssetPreview: null,
    generationError: null,
  }
}

function createInitialWorkspaceStates(): Record<PromptAssetType, PromptAssetWorkspaceState> {
  return {
    character: createEmptyWorkspaceState(),
    location: createEmptyWorkspaceState(),
  }
}

const PROMPT_ASSET_TYPES: PromptAssetType[] = ['character', 'location']
const ASSET_BINDING_CHECK_KEY = 'asset_binding_ready'

const PROMPT_ASSET_CONFIG: Record<PromptAssetType, PromptAssetConfig> = {
  character: {
    label: '角色',
    boundTagLabel: '角色实体已绑定',
    missingLabel: '未绑定角色实体',
    createAsset: createGlobalCharacter,
    renderReference: renderGlobalCharacterReference,
  },
  location: {
    label: '地点',
    boundTagLabel: '地点实体已绑定',
    missingLabel: '未绑定地点实体',
    createAsset: createGlobalLocation,
    renderReference: renderGlobalLocationReference,
  },
}

function resolveEpisodeBindingProgress(episode: Episode, entities: ScriptEntity[]): EpisodeBindingProgress {
  const workflowSummary = episode.workflow_summary
  if (workflowSummary) {
    const counts: Record<PromptAssetType, number> = {
      character: Number(workflowSummary.counts.bound_characters || 0),
      location: Number(workflowSummary.counts.bound_locations || 0),
    }
    const skipped = workflowSummary.skipped_checks.includes(ASSET_BINDING_CHECK_KEY)
    const ready = Boolean(workflowSummary.checks.asset_binding_ready) || skipped
    if (skipped) {
      return {
        counts,
        ready: true,
        label: '已跳过检查',
        className: 'np-status-tag',
        blockers: workflowSummary.blockers,
        skipped: true,
        source: 'workflow',
      }
    }
    if (ready) {
      return {
        counts,
        ready: true,
        label: '绑定完成',
        className: 'np-status-tag np-status-completed',
        blockers: workflowSummary.blockers,
        skipped: false,
        source: 'workflow',
      }
    }
    return {
      counts,
      ready: false,
      label: '待绑定',
      className: workflowSummary.blockers.length > 0 ? 'np-status-tag np-status-failed' : 'np-status-tag',
      blockers: workflowSummary.blockers,
      skipped: false,
      source: 'workflow',
    }
  }

  const scriptLength = (episode.script_text || '').trim().length
  const counts = PROMPT_ASSET_TYPES.reduce<Record<PromptAssetType, number>>((result, type) => {
    result[type] = entities.filter((item) => (
      item.entity_type === type
      && item.bindings.some((binding) => (
        binding.asset_type === type
        && bindingMatchesEpisode(binding, episode.id, { includeSharedDefault: true })
      ))
    )).length
    return result
  }, { character: 0, location: 0 })
  const missingCount = PROMPT_ASSET_TYPES.filter((type) => counts[type] <= 0).length

  if (scriptLength <= 0) {
    return {
      counts,
      ready: false,
      label: '待填充',
      className: 'np-status-tag is-unbound',
      blockers: ['分集正文为空'],
      skipped: false,
      source: 'fallback',
    }
  }
  if (missingCount >= PROMPT_ASSET_TYPES.length) {
    return {
      counts,
      ready: false,
      label: '待绑定',
      className: 'np-status-tag np-status-failed',
      blockers: ['未绑定角色实体', '未绑定地点实体'],
      skipped: false,
      source: 'fallback',
    }
  }
  if (missingCount > 0) {
    return {
      counts,
      ready: false,
      label: '部分绑定',
      className: 'np-status-tag',
      blockers: PROMPT_ASSET_TYPES
        .filter((type) => counts[type] <= 0)
        .map((type) => PROMPT_ASSET_CONFIG[type].missingLabel),
      skipped: false,
      source: 'fallback',
    }
  }
  return {
    counts,
    ready: true,
    label: '绑定完成',
    className: 'np-status-tag np-status-completed',
    blockers: [],
    skipped: false,
    source: 'fallback',
  }
}

export default function AssetBinding() {
  const { id: projectId, episodeId } = useParams<{ id: string; episodeId?: string }>()
  const navigate = useNavigate()
  const scopedEpisodeId = (episodeId || '').trim() || null
  const { workspace, loading: workspaceLoading, refreshWorkspace } = useProjectWorkspace(projectId, '加载资产绑定上下文失败')
  const { message, modal } = AntdApp.useApp()

  const [loading, setLoading] = useState(false)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [assetType, setAssetType] = useState<PromptAssetType>('character')
  const [bindingMode, setBindingMode] = useState<BindingMode>('direct')
  const [workspaceByType, setWorkspaceByType] = useState<Record<PromptAssetType, PromptAssetWorkspaceState>>(
    () => createInitialWorkspaceStates(),
  )
  const [entityRows, setEntityRows] = useState<ScriptEntity[]>([])
  const [consoleVersion, setConsoleVersion] = useState(0)
  const [consoleFocusSignal, setConsoleFocusSignal] = useState(0)
  const [showManualConsole, setShowManualConsole] = useState(true)
  const currentProject = workspace?.project ?? null

  const selectedEpisode = useMemo(() => {
    if (!scopedEpisodeId) return null
    return episodes.find((item) => item.id === scopedEpisodeId) ?? null
  }, [episodes, scopedEpisodeId])
  const currentAssetConfig = PROMPT_ASSET_CONFIG[assetType]
  const currentWorkspace = workspaceByType[assetType]
  const {
    draftLoading,
    creatingAsset,
    bindingCreatedAsset,
    renderingReference,
    renderReference,
    draftForm,
    createdAssetPreview,
    generationError,
  } = currentWorkspace
  const updateWorkspace = useCallback((
    type: PromptAssetType,
    updater: (prev: PromptAssetWorkspaceState) => PromptAssetWorkspaceState,
  ) => {
    setWorkspaceByType((prev) => ({
      ...prev,
      [type]: updater(prev[type]),
    }))
  }, [])
  const patchWorkspace = useCallback((
    type: PromptAssetType,
    patch: Partial<PromptAssetWorkspaceState>,
  ) => {
    updateWorkspace(type, (prev) => ({ ...prev, ...patch }))
  }, [updateWorkspace])
  const resetCurrentWorkspace = useCallback((type: PromptAssetType) => {
    updateWorkspace(type, () => createEmptyWorkspaceState())
  }, [updateWorkspace])
  const resetAllWorkspaces = useCallback(() => {
    setWorkspaceByType(createInitialWorkspaceStates())
  }, [])
  const selectedEpisodeProgress = useMemo(() => {
    if (!selectedEpisode) return null
    return resolveEpisodeBindingProgress(selectedEpisode, entityRows)
  }, [entityRows, selectedEpisode])
  const selectedEpisodeBindingTags = useMemo(() => {
    return PROMPT_ASSET_TYPES.map((type) => ({
      type,
      label: PROMPT_ASSET_CONFIG[type].boundTagLabel,
      count: selectedEpisodeProgress?.counts[type] ?? 0,
    }))
  }, [selectedEpisodeProgress])
  const missingChecklist = useMemo(() => {
    if (!selectedEpisodeProgress) return []
    return selectedEpisodeProgress.blockers
  }, [selectedEpisodeProgress])
  const canCreateAsset = useMemo(() => {
    return draftForm.name.trim().length > 0 && draftForm.prompt_template.trim().length > 0
  }, [draftForm.name, draftForm.prompt_template])
  const hasDraftSeed = useMemo(() => {
    return (
      draftForm.name.trim().length > 0
      || draftForm.prompt_template.trim().length > 0
      || draftForm.description.trim().length > 0
    )
  }, [draftForm.description, draftForm.name, draftForm.prompt_template])

  const refreshEpisodes = useCallback(async () => {
    if (!projectId) return []
    const episodeRows = await listEpisodes(projectId)
    const sortedEpisodes = [...episodeRows].sort((a, b) => a.episode_order - b.episode_order)
    setEpisodes(sortedEpisodes)
    return sortedEpisodes
  }, [projectId])

  const refreshEntities = useCallback(async () => {
    if (!projectId) return []
    const latest = await listScriptEntities(projectId)
    setEntityRows(latest)
    return latest
  }, [projectId])

  const applyEpisodeUpdate = useCallback((updatedEpisode: Episode) => {
    setEpisodes((prev) => prev.map((item) => (
      item.id === updatedEpisode.id ? updatedEpisode : item
    )))
  }, [])

  const loadData = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      await Promise.all([
        refreshEpisodes(),
        refreshEntities(),
      ])
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载资产绑定上下文失败'))
    } finally {
      setLoading(false)
    }
  }, [message, projectId, refreshEntities, refreshEpisodes])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const focusManualConsole = useCallback(() => {
    setShowManualConsole(true)
    setConsoleFocusSignal((prev) => prev + 1)
  }, [])

  useEffect(() => {
    resetAllWorkspaces()
  }, [resetAllWorkspaces, selectedEpisode?.id])

  useEffect(() => {
    setShowManualConsole(bindingMode === 'direct')
  }, [bindingMode])

  const handleEntitiesChange = useCallback((rows: ScriptEntity[]) => {
    setEntityRows(rows)
    void refreshEpisodes()
  }, [refreshEpisodes])

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
    patchWorkspace(assetType, {
      draftLoading: true,
      createdAssetPreview: null,
      generationError: null,
    })
    try {
      const draft = await generateAssetDraftFromPanel({
        asset_type: assetType,
        panel_title: selectedEpisode.title,
        script_text: scriptText,
      })
      updateWorkspace(assetType, (prev) => ({
        ...prev,
        draftForm: {
          name: (draft.name || '').trim(),
          description: (draft.description || '').trim(),
          prompt_template: (draft.prompt_template || '').trim(),
        },
        generationError: null,
        draftLoading: false,
      }))
      message.success(`已生成${currentAssetConfig.label}草案，可先预览并决定是否创建资产`)
    } catch (error) {
      const errorMessage = getApiErrorMessage(error, `生成${currentAssetConfig.label}草案失败`)
      patchWorkspace(assetType, {
        generationError: { stage: 'draft', message: errorMessage },
        draftLoading: false,
      })
      message.error(errorMessage)
    }
  }

  const upsertEntityBinding = useCallback(async (
    type: PromptAssetType,
    payload: { assetId: string; assetName: string; description: string; entityName: string },
  ) => {
    if (!projectId || !selectedEpisode) return
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
      item.entity_type === type && item.name.trim() === payload.entityName.trim()
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
      entity_type: type,
      name: payload.entityName,
      description: payload.description || null,
      bindings: [binding],
    })
  }, [projectId, selectedEpisode])

  const handleCreateAsset = async () => {
    if (!projectId || !selectedEpisode) return
    const entityName = draftForm.name.trim()
    const promptTemplate = draftForm.prompt_template.trim()
    const description = draftForm.description.trim()
    if (!entityName || !promptTemplate) {
      message.warning('请先完善名称和提示词后再创建资产')
      return
    }
    patchWorkspace(assetType, {
      creatingAsset: true,
      createdAssetPreview: null,
      generationError: null,
    })
    try {
      let createdAsset = await currentAssetConfig.createAsset({
        name: entityName,
        project_id: projectId,
        description: description || undefined,
        prompt_template: promptTemplate,
        tags: [`episode:${selectedEpisode.episode_order + 1}`],
      })

      if (renderReference) {
        try {
          patchWorkspace(assetType, { renderingReference: true })
          createdAsset = await currentAssetConfig.renderReference(createdAsset.id)
        } catch (error) {
          const errorMessage = getApiErrorMessage(error, `生成${currentAssetConfig.label}参考图失败`)
          patchWorkspace(assetType, {
            generationError: { stage: 'render', message: errorMessage },
            renderingReference: false,
          })
          message.warning(`资产已创建，但参考图生成失败：${errorMessage}`)
        } finally {
          patchWorkspace(assetType, { renderingReference: false })
        }
      }

      setConsoleVersion((prev) => prev + 1)
      updateWorkspace(assetType, (prev) => ({
        ...prev,
        creatingAsset: false,
        renderingReference: false,
        createdAssetPreview: {
          id: createdAsset.id,
          name: createdAsset.name,
          description: createdAsset.description,
          prompt_template: createdAsset.prompt_template,
          reference_image_url: createdAsset.reference_image_url,
          type: assetType,
          isBoundToEpisode: false,
        },
      }))
      message.success(`已创建${currentAssetConfig.label}资产，可先预览后决定是否绑定`)
    } catch (error) {
      const errorMessage = getApiErrorMessage(error, `创建${currentAssetConfig.label}资产失败`)
      patchWorkspace(assetType, {
        generationError: { stage: 'create', message: errorMessage },
        creatingAsset: false,
        renderingReference: false,
      })
      message.error(errorMessage)
    }
  }

  const handleRenderCreatedAssetReference = async () => {
    if (!createdAssetPreview) {
      message.warning('请先创建资产，再生成参考图')
      return
    }
    patchWorkspace(assetType, {
      renderingReference: true,
      generationError: generationError?.stage === 'render' ? null : generationError,
    })
    try {
      const refreshed = await PROMPT_ASSET_CONFIG[createdAssetPreview.type].renderReference(createdAssetPreview.id)
      updateWorkspace(assetType, (prev) => ({
        ...prev,
        renderingReference: false,
        createdAssetPreview: prev.createdAssetPreview && prev.createdAssetPreview.id === refreshed.id
          ? {
            ...prev.createdAssetPreview,
            name: refreshed.name,
            description: refreshed.description,
            prompt_template: refreshed.prompt_template,
            reference_image_url: refreshed.reference_image_url,
          }
          : prev.createdAssetPreview,
      }))
      setConsoleVersion((prev) => prev + 1)
      message.success(`已生成${PROMPT_ASSET_CONFIG[createdAssetPreview.type].label}参考图`)
    } catch (error) {
      const errorMessage = getApiErrorMessage(error, `生成${PROMPT_ASSET_CONFIG[createdAssetPreview.type].label}参考图失败`)
      patchWorkspace(assetType, {
        generationError: { stage: 'render', message: errorMessage },
        renderingReference: false,
      })
      message.error(errorMessage)
    }
  }

  const handleBindCreatedAsset = async () => {
    if (!createdAssetPreview || !projectId || !selectedEpisode) {
      message.warning('请先创建资产，再执行绑定')
      return
    }
    patchWorkspace(assetType, {
      bindingCreatedAsset: true,
      generationError: generationError?.stage === 'bind' ? null : generationError,
    })
    try {
      await upsertEntityBinding(createdAssetPreview.type, {
        assetId: createdAssetPreview.id,
        assetName: createdAssetPreview.name,
        description: createdAssetPreview.description || '',
        entityName: createdAssetPreview.name,
      })
      await Promise.all([refreshEntities(), refreshEpisodes()])
      setConsoleVersion((prev) => prev + 1)
      updateWorkspace(assetType, (prev) => ({
        ...prev,
        bindingCreatedAsset: false,
        generationError: null,
        createdAssetPreview: prev.createdAssetPreview
          ? { ...prev.createdAssetPreview, isBoundToEpisode: true }
          : prev.createdAssetPreview,
      }))
      message.success(`已绑定${PROMPT_ASSET_CONFIG[createdAssetPreview.type].label}资产到当前分集`)
    } catch (error) {
      const errorMessage = getApiErrorMessage(error, `绑定${PROMPT_ASSET_CONFIG[createdAssetPreview.type].label}资产失败`)
      patchWorkspace(assetType, {
        generationError: { stage: 'bind', message: errorMessage },
        bindingCreatedAsset: false,
      })
      message.error(errorMessage)
    }
  }

  const goToStoryboardEditor = useCallback(() => {
    if (!projectId || !selectedEpisode) return
    navigate(buildWorkflowStepPath(projectId, 'storyboard', selectedEpisode.id))
  }, [navigate, projectId, selectedEpisode])

  const clearAssetBindingSkipIfNeeded = useCallback(async () => {
    if (
      !selectedEpisode
      || !selectedEpisode.skipped_checks.includes(ASSET_BINDING_CHECK_KEY)
      || !selectedEpisode.workflow_summary.checks.asset_binding_ready
    ) {
      return
    }
    const updated = await updateEpisode(selectedEpisode.id, {
      skipped_checks: selectedEpisode.skipped_checks.filter((item) => item !== ASSET_BINDING_CHECK_KEY),
    })
    applyEpisodeUpdate(updated)
  }, [applyEpisodeUpdate, selectedEpisode])

  const handleGoNext = async () => {
    if (!selectedEpisodeProgress?.ready) {
      message.warning('当前仍有缺失项，如需继续请使用“跳过检查继续”')
      return
    }
    try {
      await clearAssetBindingSkipIfNeeded()
      goToStoryboardEditor()
    } catch (error) {
      message.error(getApiErrorMessage(error, '更新分集跳过状态失败'))
    }
  }

  const handleForceGoNext = () => {
    if (!projectId || !selectedEpisode) return
    if (selectedEpisodeProgress?.ready) {
      void handleGoNext()
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
      onOk: async () => {
        const nextChecks = Array.from(new Set([
          ...selectedEpisode.skipped_checks,
          ASSET_BINDING_CHECK_KEY,
        ]))
        const updated = await updateEpisode(selectedEpisode.id, { skipped_checks: nextChecks })
        applyEpisodeUpdate(updated)
        goToStoryboardEditor()
      },
    })
  }

  if ((loading || workspaceLoading) && !currentProject) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  if (!projectId || !currentProject) {
    return (
      <section className="np-page">
        <PageHeader
          kicker="资产绑定"
          title="角色/地点资产绑定"
          subtitle="项目不存在或工作台数据加载失败。"
          onBack={() => navigate('/projects')}
          backLabel="返回项目列表"
          navigation={<WorkflowSteps />}
        />
        <div className="np-page-scroll np-asset-binding-scroll">
          <Card className="np-panel-card">
            <Empty description="未找到项目工作台数据" />
          </Card>
        </div>
      </section>
    )
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="资产绑定"
        title={`${currentProject.name} · 角色/地点资产绑定`}
        subtitle="当前页面仅处理已选分集，完成角色/地点绑定后进入分镜编辑。"
        onBack={() => navigate(`/projects/${projectId}/script`)}
        backLabel="返回剧本分集"
        navigation={<WorkflowSteps />}
        actions={(
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                void Promise.all([refreshWorkspace(), loadData()])
              }}
              loading={loading}
            >
              刷新
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll np-asset-binding-scroll">
        <div className="np-asset-binding-main">
          {episodes.length <= 0 ? (
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
                  {selectedEpisodeBindingTags.map((item) => (
                    <Tag key={item.type} className="np-status-tag">{item.label}：{item.count}</Tag>
                  ))}
                  <Tag className={selectedEpisodeProgress?.className ?? 'np-status-tag'}>
                    状态：{selectedEpisodeProgress?.label ?? '待绑定'}
                  </Tag>
                </Space>
                <Paragraph className="np-asset-binding-script-preview">
                  {(selectedEpisode.script_text || '').trim() || '当前分集正文为空，请回剧本页补充内容。'}
                </Paragraph>
                {selectedEpisodeProgress?.skipped ? (
                  <Alert
                    style={{ marginTop: 10 }}
                    type="info"
                    showIcon
                    message="当前分集已记录为“跳过资产检查”"
                    description={missingChecklist.join('、') || '后续可在分镜编辑中继续补齐资产信息。'}
                  />
                ) : selectedEpisodeProgress?.ready ? (
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

                  <Tabs
                    activeKey={assetType}
                    onChange={(value) => setAssetType(value as PromptAssetType)}
                    items={PROMPT_ASSET_TYPES.map((type) => ({
                      key: type,
                      label: `${PROMPT_ASSET_CONFIG[type].label}子页`,
                    }))}
                  />

                  {bindingMode === 'direct' ? (
                    <div className="np-asset-generation-shell">
                      <div className="np-asset-generation-section">
                        <Space wrap>
                          <Text strong>当前子页：直接绑定现有{currentAssetConfig.label}资产</Text>
                          <Tag className={`np-status-tag${(selectedEpisodeProgress?.counts[assetType] ?? 0) > 0 ? ' np-status-completed' : ''}`}>
                            已绑定 {selectedEpisodeProgress?.counts[assetType] ?? 0} 个{currentAssetConfig.label}实体
                          </Tag>
                        </Space>
                        <Text type="secondary">
                          当前子页只显示{currentAssetConfig.label}实体和现有资产，直接完成绑定即可，不会自动生成提示词草案或新资产。
                        </Text>
                        <Alert
                          type="info"
                          showIcon
                          message={`下方规划台仅处理当前子页的${currentAssetConfig.label}绑定`}
                          description="先在左侧选择实体，再从右侧添加已有资产并保存；切到另一子页时不会混入别的类型。"
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="np-asset-generation-shell">
                      <div className="np-asset-generation-section">
                        <Space wrap>
                          <Text strong>阶段1：草案编辑并创建资产</Text>
                          <Tag className={`np-status-tag${hasDraftSeed ? ' np-status-completed' : ''}`}>
                            {draftLoading ? '草案生成中' : hasDraftSeed ? '草案已就绪' : '待生成'}
                          </Tag>
                          {createdAssetPreview ? <Tag className="np-status-tag np-status-generated">已创建资产</Tag> : null}
                        </Space>
                        <Text type="secondary">当前子页只处理{currentAssetConfig.label}资产。先生成或手动编辑草案，再创建资产；此阶段不会自动绑定。</Text>
                        <Space wrap>
                          <Button
                            icon={<ThunderboltOutlined />}
                            onClick={() => { void handleGenerateDraft() }}
                            loading={draftLoading}
                          >
                            生成提示词草案
                          </Button>
                          <Text type="secondary">如果草案不理想，可以直接修改下面的名称、描述和提示词后再创建。</Text>
                        </Space>
                        <Text strong>资产名称</Text>
                        <Input
                          value={draftForm.name}
                          onChange={(event) => updateWorkspace(assetType, (prev) => ({
                            ...prev,
                            draftForm: { ...prev.draftForm, name: event.target.value },
                          }))}
                          placeholder="资产名称"
                        />
                        <Text strong>资产描述（可选）</Text>
                        <Input
                          value={draftForm.description}
                          onChange={(event) => updateWorkspace(assetType, (prev) => ({
                            ...prev,
                            draftForm: { ...prev.draftForm, description: event.target.value },
                          }))}
                          placeholder="资产描述（可选）"
                        />
                        <Text strong>提示词模板</Text>
                        <TextArea
                          rows={4}
                          value={draftForm.prompt_template}
                          onChange={(event) => updateWorkspace(assetType, (prev) => ({
                            ...prev,
                            draftForm: { ...prev.draftForm, prompt_template: event.target.value },
                          }))}
                          placeholder="提示词模板"
                        />
                        <Space wrap>
                          <Switch
                            checked={renderReference}
                            onChange={(value) => patchWorkspace(assetType, { renderReference: value })}
                            checkedChildren="创建时带参考图"
                            unCheckedChildren="仅创建资产"
                          />
                          <Button
                            type="primary"
                            onClick={() => { void handleCreateAsset() }}
                            loading={creatingAsset || renderingReference}
                            disabled={!canCreateAsset}
                          >
                            创建资产
                          </Button>
                          <Button
                            onClick={() => resetCurrentWorkspace(assetType)}
                            disabled={!hasDraftSeed && !generationError}
                          >
                            清空当前子页草案
                          </Button>
                        </Space>
                        {!canCreateAsset ? (
                          <Text type="secondary">请至少填写“资产名称 + 提示词模板”后再创建资产。</Text>
                        ) : null}
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
                        {generationError?.stage === 'create' ? (
                          <Alert
                            type="error"
                            showIcon
                            message="创建资产失败"
                            description={generationError.message}
                            action={(
                              <Button
                                size="small"
                                onClick={() => { void handleCreateAsset() }}
                                loading={creatingAsset}
                              >
                                重试创建
                              </Button>
                            )}
                          />
                        ) : null}
                      </div>

                      <div className="np-asset-generation-section">
                        <Space wrap>
                          <Text strong>阶段2：预览并决定是否绑定</Text>
                          {createdAssetPreview ? (
                            <Tag className={`np-status-tag${createdAssetPreview.isBoundToEpisode ? ' np-status-completed' : ' np-status-generated'}`}>
                              {createdAssetPreview.isBoundToEpisode ? '已绑定当前分集' : '待确认绑定'}
                            </Tag>
                          ) : null}
                        </Space>
                        {!createdAssetPreview ? (
                          <Alert
                            type="info"
                            showIcon
                              message="请先在阶段1创建资产"
                            description="资产创建完成后，会在这里显示预览信息，你再决定是否绑定到当前分集。"
                          />
                        ) : (
                          <>
                            <Space wrap>
                              <Tag className="np-status-tag">{PROMPT_ASSET_CONFIG[createdAssetPreview.type].label}</Tag>
                              <Tag className="np-status-tag">
                                参考图：{createdAssetPreview.reference_image_url ? '已生成' : '未生成'}
                              </Tag>
                            </Space>
                            <Text strong>资产名称</Text>
                            <Input value={createdAssetPreview.name} readOnly />
                            <Text strong>资产描述</Text>
                            <TextArea rows={3} value={createdAssetPreview.description ?? ''} readOnly placeholder="无资产描述" />
                            <Text strong>提示词模板</Text>
                            <TextArea rows={4} value={createdAssetPreview.prompt_template ?? ''} readOnly />
                            <Text strong>资产预览</Text>
                            {createdAssetPreview.reference_image_url ? (
                              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                <Image
                                  src={createdAssetPreview.reference_image_url}
                                  alt={`${createdAssetPreview.name} 参考图`}
                                  className="np-asset-preview-image"
                                />
                                <a href={createdAssetPreview.reference_image_url} target="_blank" rel="noreferrer">
                                  新窗口查看参考图
                                </a>
                              </Space>
                            ) : (
                              <Text type="secondary">当前还没有参考图，可先生成后再决定是否绑定。</Text>
                            )}
                            <Space wrap>
                              <Button
                                onClick={() => { void handleRenderCreatedAssetReference() }}
                                loading={renderingReference}
                              >
                                {createdAssetPreview.reference_image_url ? '重新生成参考图' : '生成参考图'}
                              </Button>
                              <Button
                                type="primary"
                                onClick={() => { void handleBindCreatedAsset() }}
                                loading={bindingCreatedAsset}
                                disabled={createdAssetPreview.isBoundToEpisode}
                              >
                                {createdAssetPreview.isBoundToEpisode ? '已绑定当前分集' : '绑定到当前分集'}
                              </Button>
                            </Space>
                          </>
                        )}
                        {generationError?.stage === 'render' ? (
                          <Alert
                            type="warning"
                            showIcon
                            message="参考图生成失败"
                            description={generationError.message}
                          />
                        ) : null}
                        {generationError?.stage === 'bind' ? (
                          <Alert
                            type="error"
                            showIcon
                            message="绑定失败"
                            description={generationError.message}
                            action={createdAssetPreview && !createdAssetPreview.isBoundToEpisode ? (
                              <Button
                                size="small"
                                onClick={() => { void handleBindCreatedAsset() }}
                                loading={bindingCreatedAsset}
                              >
                                重试绑定
                              </Button>
                            ) : undefined}
                          />
                        ) : null}
                      </div>
                    </div>
                  )}

                  {bindingMode === 'generate' ? (
                    <Space wrap>
                      <Button
                        size="small"
                        onClick={() => {
                          if (showManualConsole) {
                            setShowManualConsole(false)
                            return
                          }
                          focusManualConsole()
                        }}
                      >
                        {showManualConsole ? '收起手动绑定区（高级）' : '展开手动绑定区（高级）'}
                      </Button>
                      <Text type="secondary">自动生成不理想时，再展开当前子页的手动绑定区进行精修。</Text>
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
                    enabledTypes={[assetType]}
                    initialType={assetType}
                    hideTypeTabs
                    refreshSignal={consoleVersion}
                    focusSignal={consoleFocusSignal}
                    scopeEpisodeId={selectedEpisode.id}
                    enforceEpisodeScope
                    embedded
                    onEntitiesChange={handleEntitiesChange}
                  />
                )
              ) : null}

              <div className="np-asset-binding-footer-bar">
                <Space size={8} wrap>
                  <Tag className={selectedEpisodeProgress?.className ?? 'np-status-tag'}>
                    当前状态：{selectedEpisodeProgress?.label ?? '待绑定'}
                  </Tag>
                  {missingChecklist.length > 0 ? (
                    <Text type="secondary">
                      {selectedEpisodeProgress?.skipped ? '已跳过项：' : '缺失项：'}
                      {missingChecklist.join('、')}
                    </Text>
                  ) : (
                    <Text type="secondary">已满足进入分镜编辑条件</Text>
                  )}
                </Space>
                <Space wrap>
                  <Button
                    danger
                    onClick={handleForceGoNext}
                    disabled={!projectId || !selectedEpisode || missingChecklist.length <= 0 || !!selectedEpisodeProgress?.skipped}
                  >
                    跳过检查继续
                  </Button>
                  <Button
                    type="primary"
                    icon={<ArrowRightOutlined />}
                    onClick={() => { void handleGoNext() }}
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
