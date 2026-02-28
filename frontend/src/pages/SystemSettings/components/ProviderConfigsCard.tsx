import { useCallback, useEffect, useMemo, useState } from 'react'
import { App as AntdApp, Button, Card, Divider, Empty, Input, List, Select, Space, Switch, Typography } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { listProviderConfigs, testProviderConfig, upsertProviderConfig } from '../../../api/providers'
import type { ProviderConfig, ProviderUpsertPayload } from '../../../types/provider'
import { getApiErrorMessage } from '../../../utils/error'

const { Text } = Typography

interface ProviderDraft extends ProviderUpsertPayload {
  provider_key: string
  api_key?: string
}

function buildDraft(config: ProviderConfig): ProviderDraft {
  return {
    provider_key: config.provider_key,
    provider_type: config.provider_type,
    name: config.name,
    base_url: config.base_url,
    submit_path: config.submit_path,
    status_path: config.status_path,
    result_path: config.result_path,
    auth_scheme: config.auth_scheme,
    api_key: '',
    api_key_header: config.api_key_header,
    extra_headers: config.extra_headers ?? {},
    request_template: config.request_template ?? {},
    response_mapping: config.response_mapping ?? {},
    status_mapping: config.status_mapping ?? {},
    timeout_seconds: config.timeout_seconds,
    enabled: config.enabled,
  }
}

function defaultDraft(providerKey: string): ProviderDraft {
  return {
    provider_key: providerKey,
    provider_type: 'video',
    name: providerKey,
    base_url: '',
    submit_path: '/submit',
    status_path: '/status/{task_id}',
    result_path: '/result/{task_id}',
    auth_scheme: 'bearer',
    api_key: '',
    api_key_header: 'Authorization',
    extra_headers: {},
    request_template: {},
    response_mapping: {},
    status_mapping: {},
    timeout_seconds: 60,
    enabled: true,
  }
}

export default function ProviderConfigsCard() {
  const { message } = AntdApp.useApp()
  const [loading, setLoading] = useState(false)
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [testingKey, setTestingKey] = useState<string | null>(null)
  const [configs, setConfigs] = useState<ProviderConfig[]>([])
  const [drafts, setDrafts] = useState<Record<string, ProviderDraft>>({})
  const [newProviderKey, setNewProviderKey] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const rows = await listProviderConfigs()
      setConfigs(rows)
      setDrafts((prev) => {
        const next: Record<string, ProviderDraft> = {}
        rows.forEach((item) => {
          next[item.provider_key] = prev[item.provider_key] ?? buildDraft(item)
        })
        return next
      })
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载 Provider 配置失败'))
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void load()
  }, [load])

  const mergedKeys = useMemo(() => {
    const keys = new Set<string>([...Object.keys(drafts), ...configs.map((item) => item.provider_key)])
    return [...keys].sort()
  }, [configs, drafts])

  const updateDraft = (key: string, patch: Partial<ProviderDraft>) => {
    setDrafts((prev) => ({
      ...prev,
      [key]: { ...(prev[key] ?? defaultDraft(key)), ...patch },
    }))
  }

  const handleAddDraft = () => {
    const key = newProviderKey.trim()
    if (!key) {
      message.warning('请输入 provider_key')
      return
    }
    setDrafts((prev) => ({ ...prev, [key]: prev[key] ?? defaultDraft(key) }))
    setNewProviderKey('')
  }

  const handleSave = async (key: string) => {
    const draft = drafts[key]
    if (!draft) return
    if (!draft.base_url.trim()) {
      message.warning('base_url 不能为空')
      return
    }
    setSavingKey(key)
    try {
      const payload: ProviderUpsertPayload = {
        provider_type: draft.provider_type,
        name: draft.name,
        base_url: draft.base_url,
        submit_path: draft.submit_path,
        status_path: draft.status_path,
        result_path: draft.result_path,
        auth_scheme: draft.auth_scheme,
        api_key: draft.api_key || undefined,
        api_key_header: draft.api_key_header,
        extra_headers: draft.extra_headers,
        request_template: draft.request_template,
        response_mapping: draft.response_mapping,
        status_mapping: draft.status_mapping,
        timeout_seconds: Number(draft.timeout_seconds || 60),
        enabled: draft.enabled,
      }
      await upsertProviderConfig(key, payload)
      message.success(`已保存 ${key}`)
      await load()
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存 Provider 配置失败'))
    } finally {
      setSavingKey(null)
    }
  }

  const handleTest = async (key: string) => {
    setTestingKey(key)
    try {
      const result = await testProviderConfig(key)
      const code = Number(result.status_code ?? 0)
      if (Number(result.ok) === 1 || Boolean(result.ok)) {
        message.success(`连通性测试通过（HTTP ${code}）`)
      } else {
        message.warning(`连通性测试返回异常状态（HTTP ${code}）`)
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, 'Provider 连通性测试失败'))
    } finally {
      setTestingKey(null)
    }
  }

  return (
    <Card title="Provider 配置（视频 / 语音 / 口型）" className="np-panel-card">
      <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
        <Input
          placeholder="新增 provider_key，例如 video.ggk"
          value={newProviderKey}
          onChange={(event) => setNewProviderKey(event.target.value)}
          onPressEnter={handleAddDraft}
        />
        <Button icon={<PlusOutlined />} onClick={handleAddDraft}>添加</Button>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>
      </Space.Compact>

      {mergedKeys.length === 0 ? (
        <Empty description="暂无 Provider 配置" />
      ) : (
        <List
          dataSource={mergedKeys}
          renderItem={(key) => {
            const draft = drafts[key] ?? defaultDraft(key)
            return (
              <List.Item key={key}>
                <div style={{ width: '100%' }}>
                  <Space direction="vertical" style={{ width: '100%' }} size={8}>
                    <Space wrap>
                      <Text strong>{key}</Text>
                      <Select
                        size="small"
                        value={draft.provider_type}
                        style={{ width: 120 }}
                        options={[
                          { label: 'video', value: 'video' },
                          { label: 'tts', value: 'tts' },
                          { label: 'lipsync', value: 'lipsync' },
                          { label: 'script', value: 'script' },
                        ]}
                        onChange={(value) => updateDraft(key, { provider_type: value })}
                      />
                      <Switch
                        checked={draft.enabled}
                        checkedChildren="启用"
                        unCheckedChildren="禁用"
                        onChange={(checked) => updateDraft(key, { enabled: checked })}
                      />
                    </Space>

                    <Input
                      value={draft.name}
                      placeholder="显示名称"
                      onChange={(event) => updateDraft(key, { name: event.target.value })}
                    />
                    <Input
                      value={draft.base_url}
                      placeholder="Base URL"
                      onChange={(event) => updateDraft(key, { base_url: event.target.value })}
                    />

                    <Space.Compact style={{ width: '100%' }}>
                      <Input
                        value={draft.submit_path}
                        placeholder="submit_path"
                        onChange={(event) => updateDraft(key, { submit_path: event.target.value })}
                      />
                      <Input
                        value={draft.status_path}
                        placeholder="status_path"
                        onChange={(event) => updateDraft(key, { status_path: event.target.value })}
                      />
                      <Input
                        value={draft.result_path}
                        placeholder="result_path"
                        onChange={(event) => updateDraft(key, { result_path: event.target.value })}
                      />
                    </Space.Compact>

                    <Space.Compact style={{ width: '100%' }}>
                      <Select
                        value={draft.auth_scheme}
                        style={{ width: 120 }}
                        options={[
                          { label: 'bearer', value: 'bearer' },
                          { label: 'plain', value: 'plain' },
                          { label: 'none', value: 'none' },
                        ]}
                        onChange={(value) => updateDraft(key, { auth_scheme: value })}
                      />
                      <Input
                        value={draft.api_key_header}
                        placeholder="API Key Header"
                        onChange={(event) => updateDraft(key, { api_key_header: event.target.value })}
                      />
                      <Input.Password
                        value={draft.api_key}
                        placeholder="API Key（留空保持不变）"
                        onChange={(event) => updateDraft(key, { api_key: event.target.value })}
                      />
                    </Space.Compact>

                    <Space>
                      <Button loading={savingKey === key} type="primary" onClick={() => void handleSave(key)}>
                        保存
                      </Button>
                      <Button loading={testingKey === key} onClick={() => void handleTest(key)}>
                        测试连通
                      </Button>
                    </Space>
                  </Space>
                  <Divider style={{ margin: '12px 0 0' }} />
                </div>
              </List.Item>
            )
          }}
        />
      )}
    </Card>
  )
}
