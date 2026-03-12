import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App as AntdApp,
  Button,
  Card,
  Dropdown,
  Form,
  Input,
  List,
  Popconfirm,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import type { AssetHubOverview, GlobalCharacterAsset, GlobalLocationAsset, GlobalVoice } from '../../types/assetHub'
import {
  getAssetHubOverview,
  type AssetScope,
  createAssetFolder,
  createGlobalCharacter,
  createGlobalLocation,
  createGlobalVoice,
  deleteAssetFolder,
  deleteGlobalCharacter,
  deleteGlobalLocation,
  deleteGlobalVoice,
  updateAssetFolder,
  updateGlobalCharacter,
  updateGlobalLocation,
  updateGlobalVoice,
} from '../../api/assetHub'
import { getApiErrorMessage } from '../../utils/error'
import AssetEditorDrawer from './AssetEditorDrawer'
import type { EditorKind, EditorRecord, EditorState } from './AssetEditorDrawer'

const { Text } = Typography

interface GlobalAssetManagerProps {
  overview: AssetHubOverview
  projectOptions: Array<{ label: string; value: string }>
  defaultProjectId?: string | null
}

type ManagerTabKey = 'folders' | 'characters' | 'locations' | 'voices'
const NO_FOLDER_FILTER_KEY = '__none__'

const EDITOR_KIND_LABELS: Record<EditorKind, string> = {
  folder: '资产目录',
  voice: '语音资产',
  character: '角色资产',
  location: '地点资产',
}

type FolderEditorPayload = Parameters<typeof createAssetFolder>[0]
type VoiceEditorPayload = Parameters<typeof createGlobalVoice>[0]
type CharacterEditorPayload = Parameters<typeof createGlobalCharacter>[0]
type LocationEditorPayload = Parameters<typeof createGlobalLocation>[0]
type EditorPayload = FolderEditorPayload | VoiceEditorPayload | CharacterEditorPayload | LocationEditorPayload

const EDITOR_SUBMITTERS: Record<
  EditorKind,
  {
    create: (payload: EditorPayload) => Promise<unknown>
    update: (id: string, payload: EditorPayload) => Promise<unknown>
    remove: (id: string) => Promise<void>
  }
> = {
  folder: {
    create: (payload) => createAssetFolder(payload as FolderEditorPayload),
    update: (id, payload) => updateAssetFolder(id, payload as FolderEditorPayload),
    remove: deleteAssetFolder,
  },
  voice: {
    create: (payload) => createGlobalVoice(payload as VoiceEditorPayload),
    update: (id, payload) => updateGlobalVoice(id, payload as VoiceEditorPayload),
    remove: deleteGlobalVoice,
  },
  character: {
    create: (payload) => createGlobalCharacter(payload as CharacterEditorPayload),
    update: (id, payload) => updateGlobalCharacter(id, payload as CharacterEditorPayload),
    remove: deleteGlobalCharacter,
  },
  location: {
    create: (payload) => createGlobalLocation(payload as LocationEditorPayload),
    update: (id, payload) => updateGlobalLocation(id, payload as LocationEditorPayload),
    remove: deleteGlobalLocation,
  },
}

function normalizeText(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed || undefined
}

function normalizeNullableId(value: unknown): string | null {
  const normalized = normalizeText(value)
  return normalized ?? null
}

function tagsToText(tags: string[]): string {
  if (!Array.isArray(tags) || tags.length === 0) return ''
  return tags.join(', ')
}

function parseTags(value: unknown): string[] {
  if (typeof value !== 'string') return []
  return value
    .split(/[\n,，]/g)
    .map((item) => item.trim())
    .filter(Boolean)
}

function toScopeTag(projectId: string | null | undefined, currentProjectId: string | null): string {
  if (!projectId) return '全局'
  if (currentProjectId && projectId === currentProjectId) return '当前项目'
  return `项目:${projectId.slice(0, 8)}`
}

function matchesSearch(query: string, ...fields: Array<string | null | undefined>): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return fields.some((field) => field && field.toLowerCase().includes(q))
}

type FolderScopedItem = {
  folder_id?: string | null
}

function filterRowsByFolder<Row extends FolderScopedItem>(rows: Row[], filterKey: string): Row[] {
  if (filterKey === NO_FOLDER_FILTER_KEY) {
    return rows.filter((item) => !item.folder_id)
  }
  if (filterKey === 'all') return rows
  return rows.filter((item) => item.folder_id === filterKey)
}

function filterRowsByFolderAndSearch<Row extends FolderScopedItem>(
  rows: Row[],
  filterKey: string,
  query: string,
  fields: (row: Row) => Array<string | null | undefined>,
): Row[] {
  return filterRowsByFolder(rows, filterKey).filter((row) => matchesSearch(query, ...fields(row)))
}

function buildEditorSuccessMessage(kind: EditorKind, mode: 'create' | 'edit'): string {
  return `${EDITOR_KIND_LABELS[kind]}已${mode === 'create' ? '创建' : '更新'}`
}

function buildBaseAssetPayload(values: Record<string, unknown>) {
  return {
    name: String(values.name).trim(),
    project_id: normalizeNullableId(values.project_id),
    folder_id: normalizeNullableId(values.folder_id),
    is_active: Boolean(values.is_active),
  }
}

function buildPromptAssetPayload(values: Record<string, unknown>) {
  return {
    ...buildBaseAssetPayload(values),
    description: normalizeText(values.description),
    prompt_template: normalizeText(values.prompt_template),
    reference_image_url: normalizeText(values.reference_image_url),
    tags: parseTags(values.tags_input),
  }
}

function buildEditorPayload(kind: EditorKind, values: Record<string, unknown>): EditorPayload {
  if (kind === 'folder') {
    return {
      name: String(values.name).trim(),
      folder_type: normalizeText(values.folder_type) ?? 'generic',
      storage_path: normalizeText(values.storage_path),
      description: normalizeText(values.description),
      sort_order: Number(values.sort_order ?? 0),
      is_active: Boolean(values.is_active),
    }
  }

  if (kind === 'voice') {
    return {
      ...buildBaseAssetPayload(values),
      provider: normalizeText(values.provider) ?? 'edge-tts',
      voice_code: String(values.voice_code).trim(),
      language: normalizeText(values.language),
      gender: normalizeText(values.gender),
      sample_audio_url: normalizeText(values.sample_audio_url),
      style_prompt: normalizeText(values.style_prompt),
      meta: {},
    }
  }

  if (kind === 'character') {
    return {
      ...buildPromptAssetPayload(values),
      alias: normalizeText(values.alias),
      default_voice_id: normalizeNullableId(values.default_voice_id),
    }
  }

  return buildPromptAssetPayload(values)
}

async function submitEditorPayload(editor: EditorState, payload: EditorPayload): Promise<void> {
  const submitter = EDITOR_SUBMITTERS[editor.kind]
  if (editor.mode === 'create') {
    await submitter.create(payload)
    return
  }
  if (editor.record) {
    await submitter.update(editor.record.id, payload)
  }
}

function buildEditorFormValues(
  editor: EditorState,
  defaultProjectId: string | null,
  scope: AssetScope,
  scopeProjectId: string | null,
): Record<string, unknown> {
  const defaultAssetProjectId = scope === 'global' ? undefined : (scopeProjectId ?? defaultProjectId ?? undefined)

  if (editor.mode === 'create') {
    if (editor.kind === 'folder') {
      return { folder_type: 'generic', sort_order: 0, is_active: true }
    }
    if (editor.kind === 'voice') {
      return {
        provider: 'edge-tts',
        language: 'zh-CN',
        project_id: defaultAssetProjectId,
        folder_id: undefined,
        is_active: true,
      }
    }
    return { project_id: defaultAssetProjectId, folder_id: undefined, is_active: true }
  }

  const record = editor.record
  if (!record) return {}

  if (editor.kind === 'folder') {
    const folder = record as AssetHubOverview['folders'][number]
    return {
      name: folder.name,
      folder_type: folder.folder_type,
      storage_path: folder.storage_path ?? '',
      description: folder.description ?? '',
      sort_order: folder.sort_order,
      is_active: folder.is_active,
    }
  }

  if (editor.kind === 'voice') {
    const voice = record as GlobalVoice
    return {
      name: voice.name,
      project_id: voice.project_id ?? undefined,
      provider: voice.provider,
      voice_code: voice.voice_code,
      folder_id: voice.folder_id ?? undefined,
      language: voice.language ?? '',
      gender: voice.gender ?? '',
      sample_audio_url: voice.sample_audio_url ?? '',
      style_prompt: voice.style_prompt ?? '',
      is_active: voice.is_active,
    }
  }

  if (editor.kind === 'character') {
    const character = record as GlobalCharacterAsset
    return {
      name: character.name,
      project_id: character.project_id ?? undefined,
      folder_id: character.folder_id ?? undefined,
      alias: character.alias ?? '',
      description: character.description ?? '',
      prompt_template: character.prompt_template ?? '',
      reference_image_url: character.reference_image_url ?? '',
      default_voice_id: character.default_voice_id ?? undefined,
      tags_input: tagsToText(character.tags),
      is_active: character.is_active,
    }
  }

  const location = record as GlobalLocationAsset
  return {
    name: location.name,
    project_id: location.project_id ?? undefined,
    folder_id: location.folder_id ?? undefined,
    description: location.description ?? '',
    prompt_template: location.prompt_template ?? '',
    reference_image_url: location.reference_image_url ?? '',
    tags_input: tagsToText(location.tags),
    is_active: location.is_active,
  }
}

export default function GlobalAssetManager({ overview, projectOptions, defaultProjectId }: GlobalAssetManagerProps) {
  const { message } = AntdApp.useApp()
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)
  const [editor, setEditor] = useState<EditorState | null>(null)
  const [activeTab, setActiveTab] = useState<ManagerTabKey>('folders')
  const [scope, setScope] = useState<AssetScope>('all')
  const [scopeProjectId, setScopeProjectId] = useState<string | null>(defaultProjectId ?? null)
  const [currentOverview, setCurrentOverview] = useState<AssetHubOverview>(overview)
  const [searchText, setSearchText] = useState('')
  const [folderFiltersByTab, setFolderFiltersByTab] = useState<Record<Exclude<ManagerTabKey, 'folders'>, string>>({
    characters: 'all',
    locations: 'all',
    voices: 'all',
  })

  useEffect(() => {
    setCurrentOverview(overview)
  }, [overview])

  useEffect(() => {
    if (scopeProjectId) return
    const fallbackProjectId = defaultProjectId ?? projectOptions[0]?.value ?? null
    if (fallbackProjectId) {
      setScopeProjectId(fallbackProjectId)
    }
  }, [defaultProjectId, projectOptions, scopeProjectId])

  const folderMap = useMemo(() => {
    return new Map(currentOverview.folders.map((item) => [item.id, item.name]))
  }, [currentOverview.folders])

  const voiceNameMap = useMemo(() => {
    return new Map(currentOverview.voices.map((item) => [item.id, item.name]))
  }, [currentOverview.voices])

  const folderUsageMap = useMemo(() => {
    const usage = new Map<string, { characters: number; locations: number; voices: number }>()
    const ensureCounter = (folderId: string) => {
      const current = usage.get(folderId)
      if (current) return current
      const created = { characters: 0, locations: 0, voices: 0 }
      usage.set(folderId, created)
      return created
    }

    currentOverview.characters.forEach((item) => {
      if (!item.folder_id) return
      ensureCounter(item.folder_id).characters += 1
    })
    currentOverview.locations.forEach((item) => {
      if (!item.folder_id) return
      ensureCounter(item.folder_id).locations += 1
    })
    currentOverview.voices.forEach((item) => {
      if (!item.folder_id) return
      ensureCounter(item.folder_id).voices += 1
    })
    return usage
  }, [currentOverview.characters, currentOverview.locations, currentOverview.voices])

  const folderOptions = useMemo(
    () => currentOverview.folders.map((item) => ({ label: item.name, value: item.id })),
    [currentOverview.folders],
  )

  const folderFilterOptions = useMemo(() => ([
    { label: '全部目录', value: 'all' },
    { label: '未分组', value: NO_FOLDER_FILTER_KEY },
    ...currentOverview.folders.map((item) => ({ label: item.name, value: item.id })),
  ]), [currentOverview.folders])

  const voiceOptions = useMemo(
    () => currentOverview.voices.map((item) => ({ label: item.name, value: item.id })),
    [currentOverview.voices],
  )
  const projectScopeOptions = useMemo(
    () => [{ label: '全局复用', value: '' }, ...projectOptions],
    [projectOptions],
  )

  const currentFolderFilter = activeTab === 'folders' ? 'all' : folderFiltersByTab[activeTab]

  const setCurrentFolderFilter = (value: string) => {
    if (activeTab === 'folders') return
    setFolderFiltersByTab((prev) => ({ ...prev, [activeTab]: value }))
  }

  const displayedFolders = useMemo(() => {
    return currentOverview.folders.filter((item) =>
      matchesSearch(searchText, item.name, item.description),
    )
  }, [currentOverview.folders, searchText])

  const filteredCharacters = useMemo(() => filterRowsByFolderAndSearch(
    currentOverview.characters,
    folderFiltersByTab.characters,
    searchText,
    (item) => [item.name, item.description, item.alias],
  ), [currentOverview.characters, folderFiltersByTab.characters, searchText])

  const filteredLocations = useMemo(() => filterRowsByFolderAndSearch(
    currentOverview.locations,
    folderFiltersByTab.locations,
    searchText,
    (item) => [item.name, item.description],
  ), [currentOverview.locations, folderFiltersByTab.locations, searchText])

  const filteredVoices = useMemo(() => filterRowsByFolderAndSearch(
    currentOverview.voices,
    folderFiltersByTab.voices,
    searchText,
    (item) => [item.name, item.style_prompt, item.voice_code],
  ), [currentOverview.voices, folderFiltersByTab.voices, searchText])

  const loadScopedOverview = useCallback(async (force = false) => {
    if (scope === 'project' && !scopeProjectId) {
      setCurrentOverview((prev) => ({ ...prev, characters: [], locations: [], voices: [] }))
      return
    }
    setLoading(true)
    try {
      const next = await getAssetHubOverview({
        scope,
        projectId: scope === 'global' ? undefined : scopeProjectId,
      })
      setCurrentOverview(next)
    } catch (error) {
      if (!force) return
      message.error(getApiErrorMessage(error, '获取资产列表失败'))
    } finally {
      setLoading(false)
    }
  }, [message, scope, scopeProjectId])

  useEffect(() => {
    void loadScopedOverview()
  }, [loadScopedOverview])

  const reloadGlobalAssets = async () => {
    await loadScopedOverview(true)
  }

  useEffect(() => {
    if (!editor) return
    form.resetFields()
    form.setFieldsValue(buildEditorFormValues(editor, defaultProjectId ?? null, scope, scopeProjectId))
  }, [defaultProjectId, editor, form, scope, scopeProjectId])

  const openCreateEditor = (kind: EditorKind) => {
    setEditor({ kind, mode: 'create' })
  }

  const openEditEditor = (kind: EditorKind, record: EditorRecord) => {
    setEditor({ kind, mode: 'edit', record })
  }

  const closeEditor = () => {
    setEditor(null)
  }

  const handleSubmitEditor = async () => {
    if (!editor) return
    try {
      const values = await form.validateFields()
      setSaving(true)
      const payload = buildEditorPayload(editor.kind, values as Record<string, unknown>)
      await submitEditorPayload(editor, payload)
      message.success(buildEditorSuccessMessage(editor.kind, editor.mode))
      await reloadGlobalAssets()
      closeEditor()
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return
      }
      message.error(getApiErrorMessage(error, '资产保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (kind: EditorKind, id: string) => {
    try {
      await EDITOR_SUBMITTERS[kind].remove(id)
      await reloadGlobalAssets()
      message.success('删除成功')
    } catch (error) {
      message.error(getApiErrorMessage(error, '删除失败'))
    }
  }

  const renderListActions = (kind: EditorKind, record: EditorRecord) => [
    <Button key="edit" size="small" icon={<EditOutlined />} onClick={() => openEditEditor(kind, record)}>
      编辑
    </Button>,
    <Popconfirm key="delete" title="确认删除？" onConfirm={() => void handleDelete(kind, record.id)}>
      <Button size="small" danger icon={<DeleteOutlined />}>
        删除
      </Button>
    </Popconfirm>,
  ]

  const createMenuItems = [
    { key: 'folder', label: '新建目录' },
    { key: 'character', label: '新建角色' },
    { key: 'location', label: '新建地点' },
    { key: 'voice', label: '新建语音' },
  ]

  return (
    <>
      <Card
        title="资产管理台"
        className="np-panel-card"
        extra={(
          <Space size={8}>
            <Dropdown menu={{ items: createMenuItems, onClick: ({ key }) => openCreateEditor(key as EditorKind) }}>
              <Button size="small" icon={<PlusOutlined />}>新建</Button>
            </Dropdown>
            <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={() => void reloadGlobalAssets()}>
              刷新
            </Button>
          </Space>
        )}
      >
        <div className="np-asset-filter-bar">
          <Text type="secondary">范围：</Text>
          <Select
            style={{ minWidth: 200 }}
            value={scope}
            options={[
              { label: '全局 + 指定项目', value: 'all' },
              { label: '仅全局资产', value: 'global' },
              { label: '仅指定项目资产', value: 'project' },
            ]}
            onChange={(value) => setScope(value as AssetScope)}
          />
          {scope === 'global' ? null : (
            <>
              <Text type="secondary">项目：</Text>
              <Select
                style={{ minWidth: 240 }}
                value={scopeProjectId ?? undefined}
                options={projectOptions}
                placeholder="选择项目"
                onChange={(value) => setScopeProjectId(value ?? null)}
              />
            </>
          )}
          {activeTab !== 'folders' ? (
            <>
              <Text type="secondary">目录：</Text>
              <Select
                style={{ minWidth: 180 }}
                value={currentFolderFilter}
                options={folderFilterOptions}
                onChange={setCurrentFolderFilter}
              />
            </>
          ) : null}
        </div>

        <Input
          allowClear
          placeholder="搜索资产名称 / 描述 / 别名"
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          style={{ marginBottom: 12 }}
        />

        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as ManagerTabKey)}
          items={[
            {
              key: 'folders',
              label: `目录(${currentOverview.folders.length})`,
              children: (
                <List
                  dataSource={displayedFolders}
                  locale={{ emptyText: '暂无目录' }}
                  renderItem={(item) => (
                    <List.Item actions={renderListActions('folder', item)}>
                      <List.Item.Meta
                        title={(
                          <Space>
                            <Text>{item.name}</Text>
                            <Tag className="np-status-tag">{item.folder_type}</Tag>
                            {!item.is_active ? <Tag className="np-status-tag">停用</Tag> : null}
                          </Space>
                        )}
                        description={(
                          <Space wrap>
                            {item.description ? <Text type="secondary">{item.description}</Text> : null}
                            <Tag className="np-status-tag">
                              角{folderUsageMap.get(item.id)?.characters ?? 0} / 地{folderUsageMap.get(item.id)?.locations ?? 0} / 音{folderUsageMap.get(item.id)?.voices ?? 0}
                            </Tag>
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              ),
            },
            {
              key: 'characters',
              label: `角色(${currentOverview.characters.length})`,
              children: (
                <List
                  dataSource={filteredCharacters}
                  locale={{ emptyText: '暂无角色资产' }}
                  renderItem={(item) => (
                    <List.Item actions={renderListActions('character', item)}>
                      <List.Item.Meta
                        title={(
                          <Space>
                            <Text>{item.name}</Text>
                            <Tag className="np-status-tag">{toScopeTag(item.project_id, scopeProjectId)}</Tag>
                            {item.folder_id ? <Tag className="np-status-tag">{folderMap.get(item.folder_id) ?? '已失效目录'}</Tag> : null}
                            {item.alias ? <Tag className="np-status-tag">{item.alias}</Tag> : null}
                            {!item.is_active ? <Tag className="np-status-tag">停用</Tag> : null}
                          </Space>
                        )}
                        description={(
                          <Space wrap>
                            {item.default_voice_id ? (
                              <Tag className="np-status-tag">语音：{voiceNameMap.get(item.default_voice_id) ?? '未知语音'}</Tag>
                            ) : null}
                            {item.reference_image_url ? <Text type="secondary">参考图</Text> : null}
                            {item.tags.length > 0 ? <Text type="secondary">{item.tags.join(' / ')}</Text> : null}
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              ),
            },
            {
              key: 'locations',
              label: `地点(${currentOverview.locations.length})`,
              children: (
                <List
                  dataSource={filteredLocations}
                  locale={{ emptyText: '暂无地点资产' }}
                  renderItem={(item) => (
                    <List.Item actions={renderListActions('location', item)}>
                      <List.Item.Meta
                        title={(
                          <Space>
                            <Text>{item.name}</Text>
                            <Tag className="np-status-tag">{toScopeTag(item.project_id, scopeProjectId)}</Tag>
                            {item.folder_id ? <Tag className="np-status-tag">{folderMap.get(item.folder_id) ?? '已失效目录'}</Tag> : null}
                            {!item.is_active ? <Tag className="np-status-tag">停用</Tag> : null}
                          </Space>
                        )}
                        description={(
                          <Space wrap>
                            {item.reference_image_url ? <Text type="secondary">参考图</Text> : null}
                            {item.tags.length > 0 ? <Text type="secondary">{item.tags.join(' / ')}</Text> : null}
                            {item.description ? <Text type="secondary">{item.description}</Text> : null}
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              ),
            },
            {
              key: 'voices',
              label: `语音(${currentOverview.voices.length})`,
              children: (
                <List
                  dataSource={filteredVoices}
                  locale={{ emptyText: '暂无语音资产' }}
                  renderItem={(item) => (
                    <List.Item actions={renderListActions('voice', item)}>
                      <List.Item.Meta
                        title={(
                          <Space>
                            <Text>{item.name}</Text>
                            <Tag className="np-status-tag">{toScopeTag(item.project_id, scopeProjectId)}</Tag>
                            {item.folder_id ? <Tag className="np-status-tag">{folderMap.get(item.folder_id) ?? '已失效目录'}</Tag> : null}
                            <Tag className="np-status-tag">{item.provider}</Tag>
                            {!item.is_active ? <Tag className="np-status-tag">停用</Tag> : null}
                          </Space>
                        )}
                        description={(
                          <Space wrap>
                            <Text type="secondary">{item.voice_code}</Text>
                            {item.language ? <Text type="secondary">{item.language}</Text> : null}
                            {item.gender ? <Text type="secondary">{item.gender}</Text> : null}
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              ),
            },
          ]}
        />
      </Card>

      <Card size="small" className="np-panel-card">
        <Text type="secondary">
          资产可设置为"全局复用"或"项目沉淀"。项目内沉淀后，可在分镜绑定抽屉按来源筛选复用。
        </Text>
      </Card>

      <AssetEditorDrawer
        editor={editor}
        form={form}
        saving={saving}
        folderOptions={folderOptions}
        voiceOptions={voiceOptions}
        projectScopeOptions={projectScopeOptions}
        onSubmit={() => { void handleSubmitEditor() }}
        onClose={closeEditor}
      />
    </>
  )
}
