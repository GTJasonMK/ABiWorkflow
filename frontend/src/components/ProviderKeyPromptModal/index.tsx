import { useEffect, useMemo, useState } from 'react'
import { App as AntdApp, Button, Input, Modal, Select, Space, Typography } from 'antd'

const { Text } = Typography

const DEFAULT_STORAGE_KEY = 'abi_recent_provider_keys'
const DEFAULT_MAX_RECENT = 8

function readRecentKeys(storageKey: string): string[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((item) => String(item || '').trim())
      .filter((item) => !!item)
      .slice(0, DEFAULT_MAX_RECENT)
  } catch {
    return []
  }
}

function writeRecentKeys(storageKey: string, keys: string[]): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(keys))
  } catch {
    // ignore localStorage errors
  }
}

function mergeRecentKeys(current: string[], next: string, maxRecent: number): string[] {
  const normalized = next.trim()
  if (!normalized) return current.slice(0, maxRecent)
  const merged = [normalized, ...current.filter((item) => item !== normalized)]
  return merged.slice(0, maxRecent)
}

interface ProviderKeyPromptModalProps {
  open: boolean
  title?: string
  description?: string
  defaultValue?: string
  okText?: string
  cancelText?: string
  recentStorageKey?: string
  maxRecent?: number
  onCancel: () => void
  onConfirm: (providerKey: string) => Promise<void> | void
}

export default function ProviderKeyPromptModal({
  open,
  title = '输入 Provider Key',
  description,
  defaultValue = '',
  okText = '确认',
  cancelText = '取消',
  recentStorageKey = DEFAULT_STORAGE_KEY,
  maxRecent = DEFAULT_MAX_RECENT,
  onCancel,
  onConfirm,
}: ProviderKeyPromptModalProps) {
  const { message } = AntdApp.useApp()
  const [value, setValue] = useState(defaultValue)
  const [recentKeys, setRecentKeys] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    const recent = readRecentKeys(recentStorageKey)
    setRecentKeys(recent)
    // 优先自动填充最近使用的 key，减少重复输入
    setValue(recent.length > 0 && recent[0] ? recent[0] : defaultValue)
  }, [open, defaultValue, recentStorageKey])

  const recentOptions = useMemo(
    () => recentKeys.map((item) => ({ label: item, value: item })),
    [recentKeys],
  )

  const handleConfirm = async () => {
    const providerKey = value.trim()
    if (!providerKey) {
      message.warning('provider_key 不能为空')
      return
    }

    setSubmitting(true)
    try {
      await onConfirm(providerKey)
      const nextRecent = mergeRecentKeys(recentKeys, providerKey, maxRecent)
      setRecentKeys(nextRecent)
      writeRecentKeys(recentStorageKey, nextRecent)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      title={title}
      onCancel={onCancel}
      onOk={handleConfirm}
      okText={okText}
      cancelText={cancelText}
      confirmLoading={submitting}
      destroyOnHidden
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        {description ? <Text type="secondary">{description}</Text> : null}
        {recentOptions.length > 0 ? (
          <Select
            placeholder="从最近使用中选择"
            options={recentOptions}
            value={recentOptions.some((item) => item.value === value) ? value : undefined}
            onChange={(next) => setValue(String(next))}
            allowClear
            style={{ width: '100%' }}
          />
        ) : null}
        <Input
          autoFocus
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="例如：video.ggk"
          onPressEnter={() => {
            void handleConfirm().catch(() => {})
          }}
        />
        {recentKeys.length > 0 ? (
          <Button
            size="small"
            type="text"
            onClick={() => {
              setRecentKeys([])
              writeRecentKeys(recentStorageKey, [])
            }}
          >
            清空最近使用
          </Button>
        ) : null}
      </Space>
    </Modal>
  )
}
