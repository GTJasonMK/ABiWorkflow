import { unstableSetRender } from 'antd'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'

type ContainerWithRoot = HTMLElement & {
  __antdReactRoot?: Root
}

// React 19 下为 antd v5 设置渲染适配，避免兼容性告警。
unstableSetRender((node, container) => {
  const rootContainer = container as ContainerWithRoot
  if (!rootContainer.__antdReactRoot) {
    rootContainer.__antdReactRoot = createRoot(container)
  }

  const root = rootContainer.__antdReactRoot
  root.render(node)

  return async () => {
    await new Promise<void>((resolve) => {
      setTimeout(resolve, 0)
    })
    root.unmount()
    rootContainer.__antdReactRoot = undefined
  }
})
