import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Spin,
  Switch,
  Tabs,
  Tag,
  Typography,
  App as AntdApp,
} from 'antd'
import {
  ApiOutlined,
  CodeOutlined,
  DatabaseOutlined,
  KeyOutlined,
  LinkOutlined,
  ReloadOutlined,
  SaveOutlined,
  SoundOutlined,
} from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import {
  getHealthStatus,
  importRuntimeFromGgk,
  getRuntimeSummary,
  updateRuntimeSettings,
  type HealthPayload,
  type GgkImportResultPayload,
  type RuntimeSettingsUpdatePayload,
  type RuntimeSummaryPayload,
} from '../../api/system'
import { getApiBaseUrl, getApiBaseUrlOverride, setApiBaseUrlOverride } from '../../runtime'
import { getDefaultHomePath, listSupportedHomePaths, setDefaultHomePath } from '../../preferences'
import { getApiErrorMessage } from '../../utils/error'

const { Text, Paragraph } = Typography
const OPTIONAL_PROBE_ENABLED = import.meta.env.VITE_PROBE_OPTIONAL_ENDPOINTS === 'true'
const CODE_INPUT_STYLE = { fontFamily: "'JetBrains Mono', 'Fira Code', monospace" } as const

const HOME_LABEL: Record<string, string> = {
  '/dashboard': '总览看板',
  '/projects': '项目工作台',
  '/tasks': '任务中心',
  '/assets': '媒体资产库',
  '/settings': '系统设置',
  '/guide': '使用指南',
}

interface BackendSettingsFormValues {
  app_name: string
  debug: boolean
  llm_provider: 'openai' | 'anthropic' | 'deepseek' | 'ggk'
  openai_model: string
  openai_base_url: string
  openai_api_key: string
  anthropic_model: string
  anthropic_api_key: string
  deepseek_model: string
  deepseek_base_url: string
  deepseek_api_key: string
  ggk_base_url: string
  ggk_text_model: string
  ggk_api_key: string
  video_provider: string
  video_output_dir: string
  composition_output_dir: string
  video_provider_max_duration_seconds: number
  video_poll_interval_seconds: number
  video_task_timeout_seconds: number
  ggk_video_model: string
  ggk_video_aspect_ratio: string
  ggk_video_resolution: string
  ggk_video_preset: string
  ggk_video_model_duration_profiles: string
  ggk_request_timeout_seconds: number
  tts_voice: string
  video_http_base_url: string
  video_http_api_key: string
  video_http_generate_path: string
  video_http_status_path: string
  video_http_task_id_path: string
  video_http_status_value_path: string
  video_http_progress_path: string
  video_http_result_url_path: string
  video_http_error_path: string
  video_http_request_timeout_seconds: number
  database_url: string
  redis_url: string
  celery_broker_url: string
  celery_result_backend: string
}

function normalizeInput(value: string | undefined | null): string {
  return (value ?? '').trim()
}

function buildUpdatePayload(values: BackendSettingsFormValues): RuntimeSettingsUpdatePayload {
  const payload: RuntimeSettingsUpdatePayload = {
    app_name: normalizeInput(values.app_name),
    debug: values.debug,
    llm_provider: values.llm_provider,
    openai_model: normalizeInput(values.openai_model),
    anthropic_model: normalizeInput(values.anthropic_model),
    deepseek_model: normalizeInput(values.deepseek_model),
    ggk_text_model: normalizeInput(values.ggk_text_model),
    video_provider: normalizeInput(values.video_provider),
    video_output_dir: normalizeInput(values.video_output_dir),
    composition_output_dir: normalizeInput(values.composition_output_dir),
    video_provider_max_duration_seconds: values.video_provider_max_duration_seconds,
    video_poll_interval_seconds: values.video_poll_interval_seconds,
    video_task_timeout_seconds: values.video_task_timeout_seconds,
    ggk_video_model: normalizeInput(values.ggk_video_model),
    ggk_video_aspect_ratio: normalizeInput(values.ggk_video_aspect_ratio),
    ggk_video_resolution: normalizeInput(values.ggk_video_resolution),
    ggk_video_preset: normalizeInput(values.ggk_video_preset),
    ggk_video_model_duration_profiles: normalizeInput(values.ggk_video_model_duration_profiles),
    ggk_request_timeout_seconds: values.ggk_request_timeout_seconds,
    tts_voice: normalizeInput(values.tts_voice),
    video_http_generate_path: normalizeInput(values.video_http_generate_path),
    video_http_status_path: normalizeInput(values.video_http_status_path),
    video_http_task_id_path: normalizeInput(values.video_http_task_id_path),
    video_http_status_value_path: normalizeInput(values.video_http_status_value_path),
    video_http_progress_path: normalizeInput(values.video_http_progress_path),
    video_http_result_url_path: normalizeInput(values.video_http_result_url_path),
    video_http_error_path: normalizeInput(values.video_http_error_path),
    video_http_request_timeout_seconds: values.video_http_request_timeout_seconds,
  }

  // URL 与连接类字段：留空表示不修改已有值，避免空值覆盖 .env 中已有配置。
  if (normalizeInput(values.openai_base_url)) payload.openai_base_url = normalizeInput(values.openai_base_url)
  if (normalizeInput(values.deepseek_base_url)) payload.deepseek_base_url = normalizeInput(values.deepseek_base_url)
  if (normalizeInput(values.ggk_base_url)) payload.ggk_base_url = normalizeInput(values.ggk_base_url)
  if (normalizeInput(values.video_http_base_url)) payload.video_http_base_url = normalizeInput(values.video_http_base_url)

  // 密钥：留空表示不修改已有值。
  if (normalizeInput(values.openai_api_key)) payload.openai_api_key = normalizeInput(values.openai_api_key)
  if (normalizeInput(values.anthropic_api_key)) payload.anthropic_api_key = normalizeInput(values.anthropic_api_key)
  if (normalizeInput(values.deepseek_api_key)) payload.deepseek_api_key = normalizeInput(values.deepseek_api_key)
  if (normalizeInput(values.ggk_api_key)) payload.ggk_api_key = normalizeInput(values.ggk_api_key)
  if (normalizeInput(values.video_http_api_key)) payload.video_http_api_key = normalizeInput(values.video_http_api_key)

  // 连接串：留空表示不修改已有值。
  if (normalizeInput(values.database_url)) payload.database_url = normalizeInput(values.database_url)
  if (normalizeInput(values.redis_url)) payload.redis_url = normalizeInput(values.redis_url)
  if (normalizeInput(values.celery_broker_url)) payload.celery_broker_url = normalizeInput(values.celery_broker_url)
  if (normalizeInput(values.celery_result_backend)) payload.celery_result_backend = normalizeInput(values.celery_result_backend)

  return payload
}

export default function SystemSettings() {
  const { message } = AntdApp.useApp()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [importingGgk, setImportingGgk] = useState(false)
  const [health, setHealth] = useState<HealthPayload | null>(null)
  const [runtime, setRuntime] = useState<RuntimeSummaryPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [apiOverride, setApiOverride] = useState('')
  const [homePath, setHomePath] = useState('/dashboard')
  const [backendForm] = Form.useForm<BackendSettingsFormValues>()

  const homeOptions = useMemo(
    () => listSupportedHomePaths().map((path) => ({ value: path, label: HOME_LABEL[path] || path })),
    [],
  )
  const canPickDirectory = Boolean(window.__ABI_DESKTOP__?.pickDirectory)

  const refreshRuntime = async () => {
    setLoading(true)
    const [healthResult, runtimeResult] = await Promise.allSettled([getHealthStatus(), getRuntimeSummary()])

    if (healthResult.status === 'fulfilled') {
      setHealth(healthResult.value)
    } else {
      setHealth(null)
    }

    if (runtimeResult.status === 'fulfilled') {
      setRuntime(runtimeResult.value)
    } else {
      setRuntime(null)
    }

    if (healthResult.status === 'rejected' || runtimeResult.status === 'rejected') {
      let rootError: unknown = null
      if (runtimeResult.status === 'rejected') {
        rootError = runtimeResult.reason
      } else if (healthResult.status === 'rejected') {
        rootError = healthResult.reason
      }
      setError(getApiErrorMessage(rootError, '部分系统信息获取失败'))
    } else {
      setError(null)
    }

    setLoading(false)
  }

  useEffect(() => {
    setApiOverride(getApiBaseUrlOverride() ?? '')
    setHomePath(getDefaultHomePath())
    void refreshRuntime()
  }, [])

  useEffect(() => {
    if (!runtime) return

    backendForm.setFieldsValue({
      app_name: runtime.app?.name || runtime.app_name || 'AbiWorkflow',
      debug: Boolean(runtime.app?.debug ?? runtime.debug),
      llm_provider: (runtime.llm?.provider || runtime.llm_provider || 'openai') as 'openai' | 'anthropic' | 'deepseek' | 'ggk',
      openai_model: runtime.llm?.openai.model || 'gpt-4o',
      openai_base_url: runtime.llm?.openai.base_url ?? '',
      openai_api_key: '',
      anthropic_model: runtime.llm?.anthropic.model || 'claude-sonnet-4-20250514',
      anthropic_api_key: '',
      deepseek_model: runtime.llm?.deepseek.model || 'deepseek-chat',
      deepseek_base_url: runtime.llm?.deepseek.base_url || 'https://api.deepseek.com/v1',
      deepseek_api_key: '',
      ggk_base_url: runtime.llm?.ggk?.base_url ?? '',
      ggk_text_model: runtime.llm?.ggk?.text_model || 'grok-3',
      ggk_api_key: '',
      video_provider: runtime.video?.provider || runtime.video_provider || 'mock',
      video_output_dir: runtime.video?.output_dir || runtime.video_output_dir || './outputs/videos',
      composition_output_dir: runtime.video?.composition_output_dir || runtime.composition_output_dir || './outputs/compositions',
      video_provider_max_duration_seconds: runtime.video?.provider_max_duration_seconds ?? 6,
      video_poll_interval_seconds: runtime.video?.poll_interval_seconds ?? 1,
      video_task_timeout_seconds: runtime.video?.task_timeout_seconds ?? 300,
      ggk_video_model: runtime.video?.ggk_provider?.video_model || 'grok-imagine-1.0-video',
      ggk_video_aspect_ratio: runtime.video?.ggk_provider?.aspect_ratio || '16:9',
      ggk_video_resolution: runtime.video?.ggk_provider?.resolution || 'SD',
      ggk_video_preset: runtime.video?.ggk_provider?.preset || 'normal',
      ggk_video_model_duration_profiles: runtime.video?.ggk_provider?.model_duration_profiles ?? '',
      ggk_request_timeout_seconds: runtime.video?.ggk_provider?.request_timeout_seconds ?? 300,
      tts_voice: runtime.video?.tts_voice || 'zh-CN-XiaoxiaoNeural',
      video_http_base_url: runtime.video?.http_provider.base_url ?? '',
      video_http_api_key: '',
      video_http_generate_path: runtime.video?.http_provider.generate_path || '/v1/video/generations',
      video_http_status_path: runtime.video?.http_provider.status_path || '/v1/video/generations/{task_id}',
      video_http_task_id_path: runtime.video?.http_provider.task_id_path || 'task_id',
      video_http_status_value_path: runtime.video?.http_provider.status_value_path || 'status',
      video_http_progress_path: runtime.video?.http_provider.progress_path || 'progress_percent',
      video_http_result_url_path: runtime.video?.http_provider.result_url_path || 'result_url',
      video_http_error_path: runtime.video?.http_provider.error_path || 'error_message',
      video_http_request_timeout_seconds: runtime.video?.http_provider.request_timeout_seconds ?? 60,
      // 连接串默认留空，避免覆盖为脱敏值；输入新值才会更新。
      database_url: '',
      redis_url: '',
      celery_broker_url: '',
      celery_result_backend: '',
    })
  }, [runtime, backendForm])

  const saveSettings = async () => {
    setSaving(true)
    try {
      const values = await backendForm.validateFields()
      const payload = buildUpdatePayload(values)
      const updatedRuntime = await updateRuntimeSettings(payload)

      setRuntime(updatedRuntime)
      setApiBaseUrlOverride(apiOverride || null)
      setDefaultHomePath(homePath)

      backendForm.setFieldsValue({
        openai_api_key: '',
        anthropic_api_key: '',
        deepseek_api_key: '',
        ggk_api_key: '',
        video_http_api_key: '',
        database_url: '',
        redis_url: '',
        celery_broker_url: '',
        celery_result_backend: '',
      })
      message.success('设置已保存。后端配置已写入 .env，部分配置需重启后生效。')
    } catch (err) {
      message.error(getApiErrorMessage(err, '保存系统配置失败'))
    } finally {
      setSaving(false)
    }
  }

  const importSettingsFromGgk = async () => {
    setImportingGgk(true)
    try {
      const result: GgkImportResultPayload = await importRuntimeFromGgk({
        auto_switch_provider: true,
      })
      setRuntime(result.runtime)
      setError(null)
      message.success(
        `已从 GGK 导入配置（来源：${result.source.api_key_source}，${
          result.source.base_url_reachable ? '已探测到在线服务' : '未探测到在线服务，已写入默认地址'
        }）。`,
      )
    } catch (err) {
      message.error(getApiErrorMessage(err, '从 GGK 导入配置失败'))
    } finally {
      setImportingGgk(false)
    }
  }

  const llm = runtime?.llm
  const queue = runtime?.queue
  const video = runtime?.video
  const httpProvider = runtime?.video?.http_provider

  const renderStatusTag = (ok: boolean, onLabel: string, offLabel: string) => (
    <Tag className={ok ? 'np-status-tag np-status-generated' : 'np-status-tag np-status-failed'}>
      {ok ? onLabel : offLabel}
    </Tag>
  )

  return (
    <section className="np-page">
      <PageHeader
        kicker="系统参数"
        title="系统设置"
        subtitle="查看运行状态，并在页面内直接编辑后端配置与前端偏好。"
        actions={(
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void refreshRuntime()} loading={loading}>
              刷新状态
            </Button>
            <Button
              icon={<ApiOutlined />}
              onClick={() => void importSettingsFromGgk()}
              loading={importingGgk}
            >
              从 GGK 自动导入
            </Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={() => void saveSettings()} loading={saving}>
              保存设置
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
        {loading && !runtime ? (
          <div className="np-page-loading">
            <Spin size="large" />
          </div>
        ) : (
          <div className="np-settings-grid">
            {error ? (
              <Alert
                className="np-panel-card"
                type="warning"
                showIcon
                message="部分系统信息加载失败"
                description={error}
              />
            ) : null}

            <Card title="运行状态总览" className="np-panel-card">
              <Descriptions column={1} size="small" styles={{ label: { width: 150 } }}>
                <Descriptions.Item label="后端健康">
                  {renderStatusTag(health?.status === 'ok', '正常', '异常')}
                </Descriptions.Item>
                <Descriptions.Item label="应用名称">
                  <Text>{runtime?.app?.name ?? runtime?.app_name ?? '-'}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="调试模式">
                  <Switch checked={Boolean(runtime?.app?.debug ?? runtime?.debug)} disabled />
                </Descriptions.Item>
                <Descriptions.Item label="当前 LLM">
                  <Text>{llm?.provider ?? runtime?.llm_provider ?? '-'} / {llm?.active_model ?? runtime?.llm_model ?? '-'}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="视频提供者">
                  <Text>{video?.provider ?? runtime?.video_provider ?? '-'}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="Celery Worker">
                  {renderStatusTag(Boolean(queue?.celery_worker_online ?? runtime?.celery_worker_online), '在线', '离线')}
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <Card title="敏感项当前状态" className="np-panel-card">
              <Descriptions column={1} size="small" styles={{ label: { width: 180 } }}>
                <Descriptions.Item label="OpenAI Key">
                  <Space size={6} wrap>
                    {renderStatusTag(Boolean(llm?.openai.api_key_configured), '已配置', '未配置')}
                    {llm?.openai.api_key_preview ? <Text code>{llm.openai.api_key_preview}</Text> : null}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="Anthropic Key">
                  <Space size={6} wrap>
                    {renderStatusTag(Boolean(llm?.anthropic.api_key_configured), '已配置', '未配置')}
                    {llm?.anthropic.api_key_preview ? <Text code>{llm.anthropic.api_key_preview}</Text> : null}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="DeepSeek Key">
                  <Space size={6} wrap>
                    {renderStatusTag(Boolean(llm?.deepseek.api_key_configured), '已配置', '未配置')}
                    {llm?.deepseek.api_key_preview ? <Text code>{llm.deepseek.api_key_preview}</Text> : null}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="GGK Key">
                  <Space size={6} wrap>
                    {renderStatusTag(Boolean(llm?.ggk?.api_key_configured), '已配置', '未配置')}
                    {llm?.ggk?.api_key_preview ? <Text code>{llm.ggk.api_key_preview}</Text> : null}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="HTTP Provider Key">
                  <Space size={6} wrap>
                    {renderStatusTag(Boolean(httpProvider?.api_key_configured), '已配置', '未配置')}
                    {httpProvider?.api_key_preview ? <Text code>{httpProvider.api_key_preview}</Text> : null}
                  </Space>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <Card title="后端配置编辑（保存即写入 .env）" className="np-panel-card np-settings-editor">
              <Paragraph className="np-note" style={{ marginBottom: 12 }}>
                配置已按模块分组。密钥和连接串字段支持“留空不修改”。
                {canPickDirectory ? ' 桌面版可直接选择目录。' : ''}
              </Paragraph>
              <Form form={backendForm} layout="vertical">
                <Tabs
                  className="np-settings-tabs"
                  defaultActiveKey="basic"
                  items={[
                    {
                      key: 'basic',
                      label: '基础',
                      children: (
                        <div className="np-settings-section">
                          <div className="np-dashboard-grid">
                            <Form.Item label="应用名称" name="app_name" rules={[{ required: true, message: '请输入应用名称' }]}>
                              <Input />
                            </Form.Item>
                            <Form.Item label="调试模式" name="debug" valuePropName="checked">
                              <Switch />
                            </Form.Item>
                            <Form.Item label="LLM Provider" name="llm_provider" rules={[{ required: true, message: '请选择 LLM Provider' }]}>
                              <Select
                                options={[
                                  { label: 'OpenAI', value: 'openai' },
                                  { label: 'Anthropic', value: 'anthropic' },
                                  { label: 'DeepSeek', value: 'deepseek' },
                                  { label: 'GGK', value: 'ggk' },
                                ]}
                              />
                            </Form.Item>
                            <Form.Item label="视频提供者" name="video_provider" rules={[{ required: true, message: '请输入视频提供者' }]}>
                              <Select
                                options={[
                                  { label: 'Mock（本地测试）', value: 'mock' },
                                  { label: 'HTTP（任务轮询）', value: 'http' },
                                  { label: 'GGK（OpenAI 兼容视频）', value: 'ggk' },
                                ]}
                              />
                            </Form.Item>
                            <Form.Item label="TTS 音色" name="tts_voice" rules={[{ required: true, message: '请输入 TTS 音色' }]}>
                              <Input prefix={<SoundOutlined />} allowClear />
                            </Form.Item>
                          </div>
                        </div>
                      ),
                    },
                    {
                      key: 'llm',
                      label: 'LLM',
                      children: (
                        <div className="np-settings-section">
                          <div className="np-dashboard-grid">
                            <Form.Item label="OpenAI 模型" name="openai_model" rules={[{ required: true, message: '请输入 OpenAI 模型' }]}>
                              <Input />
                            </Form.Item>
                            <Form.Item label="OpenAI Base URL" name="openai_base_url">
                              <Input
                                prefix={<LinkOutlined />}
                                style={CODE_INPUT_STYLE}
                                placeholder="留空使用默认 OpenAI 地址"
                                allowClear
                              />
                            </Form.Item>
                            <Form.Item label="Anthropic 模型" name="anthropic_model" rules={[{ required: true, message: '请输入 Anthropic 模型' }]}>
                              <Input />
                            </Form.Item>
                            <Form.Item label="DeepSeek 模型" name="deepseek_model" rules={[{ required: true, message: '请输入 DeepSeek 模型' }]}>
                              <Input />
                            </Form.Item>
                            <Form.Item label="DeepSeek Base URL" name="deepseek_base_url">
                              <Input prefix={<LinkOutlined />} style={CODE_INPUT_STYLE} allowClear />
                            </Form.Item>
                            <Form.Item label="GGK Base URL" name="ggk_base_url">
                              <Input
                                prefix={<LinkOutlined />}
                                style={CODE_INPUT_STYLE}
                                placeholder="例如 http://127.0.0.1:8000/v1"
                                allowClear
                              />
                            </Form.Item>
                            <Form.Item label="GGK 文本模型" name="ggk_text_model" rules={[{ required: true, message: '请输入 GGK 文本模型' }]}>
                              <Input
                                prefix={<ApiOutlined />}
                                style={CODE_INPUT_STYLE}
                                placeholder="例如 grok-3 / grok-4.1"
                                allowClear
                              />
                            </Form.Item>
                          </div>
                          <Collapse
                            items={[
                              {
                                key: 'llm-secrets',
                                label: '密钥更新（可选，留空不修改）',
                                children: (
                                  <div className="np-dashboard-grid">
                                    <Form.Item label="OpenAI API Key" name="openai_api_key">
                                      <Input.Password prefix={<KeyOutlined />} placeholder="sk-..." />
                                    </Form.Item>
                                    <Form.Item label="Anthropic API Key" name="anthropic_api_key">
                                      <Input.Password prefix={<KeyOutlined />} placeholder="sk-ant-..." />
                                    </Form.Item>
                                    <Form.Item label="DeepSeek API Key" name="deepseek_api_key">
                                      <Input.Password prefix={<KeyOutlined />} />
                                    </Form.Item>
                                    <Form.Item label="GGK API Key" name="ggk_api_key">
                                      <Input.Password prefix={<KeyOutlined />} placeholder="sk-..." />
                                    </Form.Item>
                                  </div>
                                ),
                              },
                            ]}
                          />
                        </div>
                      ),
                    },
                    {
                      key: 'video',
                      label: '视频',
                      children: (
                        <div className="np-settings-section">
                          <div className="np-dashboard-grid">
                            <Form.Item label="单段最大时长（秒）" name="video_provider_max_duration_seconds" rules={[{ required: true, message: '请输入最大时长' }]}>
                              <InputNumber min={1} max={3600} style={{ width: '100%' }} />
                            </Form.Item>
                            <Form.Item label="轮询间隔（秒）" name="video_poll_interval_seconds" rules={[{ required: true, message: '请输入轮询间隔' }]}>
                              <InputNumber min={0.1} max={300} step={0.1} style={{ width: '100%' }} />
                            </Form.Item>
                            <Form.Item label="任务超时（秒）" name="video_task_timeout_seconds" rules={[{ required: true, message: '请输入任务超时' }]}>
                              <InputNumber min={1} max={7200} style={{ width: '100%' }} />
                            </Form.Item>
                            <Form.Item label="GGK 视频模型" name="ggk_video_model" rules={[{ required: true, message: '请输入 GGK 视频模型' }]}>
                              <Input prefix={<ApiOutlined />} style={CODE_INPUT_STYLE} allowClear />
                            </Form.Item>
                            <Form.Item label="GGK 画面比例" name="ggk_video_aspect_ratio" rules={[{ required: true, message: '请选择画面比例' }]}>
                              <Select
                                options={[
                                  { label: '16:9', value: '16:9' },
                                  { label: '9:16', value: '9:16' },
                                  { label: '3:2', value: '3:2' },
                                  { label: '2:3', value: '2:3' },
                                  { label: '1:1', value: '1:1' },
                                ]}
                              />
                            </Form.Item>
                            <Form.Item label="GGK 分辨率" name="ggk_video_resolution" rules={[{ required: true, message: '请选择分辨率' }]}>
                              <Select
                                options={[
                                  { label: 'SD', value: 'SD' },
                                  { label: 'HD', value: 'HD' },
                                ]}
                              />
                            </Form.Item>
                            <Form.Item label="GGK 风格" name="ggk_video_preset" rules={[{ required: true, message: '请选择生成风格' }]}>
                              <Select
                                options={[
                                  { label: 'normal', value: 'normal' },
                                  { label: 'fun', value: 'fun' },
                                  { label: 'spicy', value: 'spicy' },
                                  { label: 'custom', value: 'custom' },
                                ]}
                              />
                            </Form.Item>
                            <Form.Item
                              label="模型时长策略（JSON，可选）"
                              name="ggk_video_model_duration_profiles"
                              tooltip="按模型配置时长区间、可选时长和提示词模板。留空使用默认策略。"
                            >
                              <Input.TextArea
                                rows={6}
                                style={CODE_INPUT_STYLE}
                                placeholder={'{"grok-imagine-1.0-video":{"min_seconds":5,"max_seconds":15,"allowed_seconds":[5,6,8,10,15],"prompt_hint_template":"请将时长控制在约 {seconds} 秒。"}}'}
                              />
                            </Form.Item>
                            <Form.Item label="GGK 请求超时（秒）" name="ggk_request_timeout_seconds" rules={[{ required: true, message: '请输入 GGK 请求超时' }]}>
                              <InputNumber min={10} max={1200} style={{ width: '100%' }} />
                            </Form.Item>
                          </div>
                        </div>
                      ),
                    },
                    {
                      key: 'http-provider',
                      label: 'HTTP 提供者',
                      children: (
                        <div className="np-settings-section">
                          <div className="np-dashboard-grid">
                            <Form.Item label="HTTP Base URL" name="video_http_base_url">
                              <Input
                                prefix={<LinkOutlined />}
                                style={CODE_INPUT_STYLE}
                                placeholder="https://api.example.com"
                                allowClear
                              />
                            </Form.Item>
                            <Form.Item label="Generate Path" name="video_http_generate_path" rules={[{ required: true, message: '请输入生成路径' }]}>
                              <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
                            </Form.Item>
                            <Form.Item label="Status Path" name="video_http_status_path" rules={[{ required: true, message: '请输入状态查询路径' }]}>
                              <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
                            </Form.Item>
                            <Form.Item label="Task ID 字段路径" name="video_http_task_id_path" rules={[{ required: true, message: '请输入 task_id 路径' }]}>
                              <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
                            </Form.Item>
                            <Form.Item label="状态字段路径" name="video_http_status_value_path" rules={[{ required: true, message: '请输入状态字段路径' }]}>
                              <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
                            </Form.Item>
                            <Form.Item label="进度字段路径" name="video_http_progress_path" rules={[{ required: true, message: '请输入进度字段路径' }]}>
                              <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
                            </Form.Item>
                            <Form.Item label="结果 URL 字段路径" name="video_http_result_url_path" rules={[{ required: true, message: '请输入结果 URL 路径' }]}>
                              <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
                            </Form.Item>
                            <Form.Item label="错误字段路径" name="video_http_error_path" rules={[{ required: true, message: '请输入错误字段路径' }]}>
                              <Input prefix={<CodeOutlined />} style={CODE_INPUT_STYLE} allowClear />
                            </Form.Item>
                            <Form.Item label="HTTP 请求超时（秒）" name="video_http_request_timeout_seconds" rules={[{ required: true, message: '请输入请求超时' }]}>
                              <InputNumber min={1} max={600} style={{ width: '100%' }} />
                            </Form.Item>
                          </div>
                          <Collapse
                            items={[
                              {
                                key: 'http-secret',
                                label: 'HTTP API Key（可选，留空不修改）',
                                children: (
                                  <Form.Item label="HTTP API Key" name="video_http_api_key">
                                    <Input.Password prefix={<KeyOutlined />} />
                                  </Form.Item>
                                ),
                              },
                            ]}
                          />
                        </div>
                      ),
                    },
                    {
                      key: 'infra',
                      label: '数据库与队列',
                      children: (
                        <div className="np-settings-section">
                          <Alert
                            type="info"
                            showIcon
                            message="以下配置修改后需要重启后端服务才能完全生效"
                            style={{ marginBottom: 12 }}
                          />
                          <div className="np-dashboard-grid">
                            <Form.Item
                              label="数据库连接（可选，留空不改）"
                              name="database_url"
                              tooltip="修改后需重启后端服务。留空表示不修改现有连接串。"
                            >
                              <Input
                                prefix={<DatabaseOutlined />}
                                style={CODE_INPUT_STYLE}
                                placeholder={runtime?.app?.database_url || 'sqlite+aiosqlite:///./abi_workflow.db'}
                                allowClear
                              />
                            </Form.Item>
                            <Form.Item
                              label="Redis URL（可选，留空不改）"
                              name="redis_url"
                              tooltip="修改后需重启后端服务和 Celery Worker。留空表示不修改现有连接串。"
                            >
                              <Input
                                prefix={<DatabaseOutlined />}
                                style={CODE_INPUT_STYLE}
                                placeholder={queue?.redis_url || runtime?.redis_url || 'redis://localhost:6379/0'}
                                allowClear
                              />
                            </Form.Item>
                            <Form.Item
                              label="Celery Broker（可选，留空不改）"
                              name="celery_broker_url"
                              tooltip="修改后需重启 Celery Worker。"
                            >
                              <Input
                                prefix={<DatabaseOutlined />}
                                style={CODE_INPUT_STYLE}
                                placeholder={queue?.celery_broker_url || 'redis://localhost:6379/1'}
                                allowClear
                              />
                            </Form.Item>
                            <Form.Item
                              label="Celery Result Backend（可选，留空不改）"
                              name="celery_result_backend"
                              tooltip="修改后需重启 Celery Worker。"
                            >
                              <Input
                                prefix={<DatabaseOutlined />}
                                style={CODE_INPUT_STYLE}
                                placeholder={queue?.celery_result_backend || 'redis://localhost:6379/2'}
                                allowClear
                              />
                            </Form.Item>
                          </div>
                        </div>
                      ),
                    },
                  ]}
                />
              </Form>
            </Card>

            <Card title="前端偏好设置" className="np-panel-card">
              <Form layout="vertical">
                <Form.Item label="默认首页">
                  <Select
                    value={homePath}
                    options={homeOptions}
                    onChange={setHomePath}
                  />
                </Form.Item>

                <Form.Item label="API 地址覆盖（可选）">
                  <Input
                    prefix={<LinkOutlined />}
                    style={CODE_INPUT_STYLE}
                    placeholder="例如 /api 或 http://127.0.0.1:8000/api"
                    value={apiOverride}
                    onChange={(event) => setApiOverride(event.target.value)}
                    allowClear
                  />
                </Form.Item>
              </Form>
              <Paragraph className="np-note" style={{ marginBottom: 6 }}>
                当前生效 API：<Text code>{getApiBaseUrl()}</Text>
              </Paragraph>
              <Paragraph className="np-note" style={{ marginBottom: 0 }}>
                可选接口探测：{renderStatusTag(OPTIONAL_PROBE_ENABLED, '开启', '关闭')}
              </Paragraph>
            </Card>
          </div>
        )}
      </div>
    </section>
  )
}
