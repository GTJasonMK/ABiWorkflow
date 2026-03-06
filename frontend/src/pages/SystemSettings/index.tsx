import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Form, Space, Spin, App as AntdApp } from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import {
  getHealthStatus,
  getRuntimeSummary,
  updateRuntimeSettings,
  type HealthPayload,
  type RuntimeSummaryPayload,
} from '../../api/system'
import { getApiBaseUrl, getApiBaseUrlOverride, setApiBaseUrlOverride } from '../../runtime'
import { getDefaultHomePath, listSupportedHomePaths, setDefaultHomePath } from '../../preferences'
import { getApiErrorMessage } from '../../utils/error'
import { HOME_LABEL, OPTIONAL_PROBE_ENABLED } from './constants'
import { buildUpdatePayload, mapRuntimeToFormValues, resetSensitiveFields } from './formMapping'
import type { BackendSettingsFormValues } from './types'
import RuntimeOverviewCard from './components/RuntimeOverviewCard'
import SensitiveStatusCard from './components/SensitiveStatusCard'
import BackendSettingsEditor from './components/BackendSettingsEditor'
import FrontendPreferencesCard from './components/FrontendPreferencesCard'
import ProviderConfigsCard from './components/ProviderConfigsCard'

export default function SystemSettings() {
  const { message } = AntdApp.useApp()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
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
    backendForm.setFieldsValue(mapRuntimeToFormValues(runtime))
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
      backendForm.setFieldsValue(resetSensitiveFields())

      message.success('设置已保存。后端配置已写入 .env，部分配置需重启后生效。')
    } catch (err) {
      message.error(getApiErrorMessage(err, '保存系统配置失败'))
    } finally {
      setSaving(false)
    }
  }

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

            <RuntimeOverviewCard health={health} runtime={runtime} />
            <SensitiveStatusCard runtime={runtime} />
            <BackendSettingsEditor runtime={runtime} backendForm={backendForm} canPickDirectory={canPickDirectory} />
            <ProviderConfigsCard />
            <FrontendPreferencesCard
              homePath={homePath}
              homeOptions={homeOptions}
              onHomePathChange={setHomePath}
              apiOverride={apiOverride}
              onApiOverrideChange={setApiOverride}
              currentApiBase={getApiBaseUrl()}
              optionalProbeEnabled={OPTIONAL_PROBE_ENABLED}
            />
          </div>
        )}
      </div>
    </section>
  )
}
