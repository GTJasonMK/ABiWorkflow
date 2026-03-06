import { useCallback, useEffect } from 'react'
import { useBlocker } from 'react-router-dom'
import { Modal } from 'antd'

/**
 * 导航守卫 hook：检测未保存更改，阻止用户意外离开页面。
 * 同时注册 window.beforeunload 事件防止浏览器关闭/刷新丢失数据。
 */
export function useUnsavedChanges(dirty: boolean) {
  const blocker = useBlocker(
    useCallback(() => dirty, [dirty]),
  )

  useEffect(() => {
    if (blocker.state === 'blocked') {
      Modal.confirm({
        title: '有未保存的更改',
        content: '当前页面有未保存的内容，确定要离开吗？',
        okText: '离开',
        okButtonProps: { danger: true },
        cancelText: '留下',
        onOk: () => { blocker.proceed() },
        onCancel: () => { blocker.reset() },
      })
    }
  }, [blocker])

  useEffect(() => {
    if (!dirty) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  return { blocker }
}
