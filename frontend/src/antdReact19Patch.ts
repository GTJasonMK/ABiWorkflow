import { unstableSetRender } from 'antd'
import { createRoot, type Root } from 'react-dom/client'

// 直接对当前项目实际使用的 antd 实例打补丁，避免开发期出现 React 19 兼容告警，
// 同时修复 message / modal / notification / wave 等内部挂载逻辑。
const reactRoots = new WeakMap<Element | DocumentFragment, Root>()

unstableSetRender((node, container) => {
  let root = reactRoots.get(container)

  if (!root) {
    root = createRoot(container)
    reactRoots.set(container, root)
  }

  root.render(node)

  return () => new Promise<void>((resolve) => {
    window.setTimeout(() => {
      root?.unmount()
      reactRoots.delete(container)
      resolve()
    }, 0)
  })
})
