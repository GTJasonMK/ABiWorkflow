import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import type { ThemeConfig } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AppLayout from './components/Layout'
import ProjectList from './pages/ProjectList'
import ScriptInput from './pages/ScriptInput'
import SceneEditor from './pages/SceneEditor'
import VideoGeneration from './pages/VideoGeneration'
import CompositionPreview from './pages/CompositionPreview'

const newsprintTheme: ThemeConfig = {
  token: {
    colorPrimary: '#111111',
    colorInfo: '#111111',
    colorSuccess: '#1f7a1f',
    colorWarning: '#a65e00',
    colorError: '#b42318',
    colorTextBase: '#111111',
    colorBorder: '#111111',
    colorBgBase: '#f9f9f7',
    borderRadius: 0,
    lineWidth: 1,
    fontFamily: "'Inter', 'Noto Sans SC', sans-serif",
    wireframe: true,
  },
  components: {
    Layout: {
      bodyBg: '#f9f9f7',
      siderBg: '#f9f9f7',
      headerBg: '#f9f9f7',
      headerColor: '#111111',
    },
    Card: {
      headerBg: '#f9f9f7',
    },
    Button: {
      borderColorDisabled: '#a3a3a3',
      colorTextDisabled: '#666666',
    },
    Table: {
      headerBg: '#f2f2ee',
      rowHoverBg: '#f2f2ed',
    },
    Menu: {
      itemBg: '#f9f9f7',
      itemSelectedBg: '#111111',
      itemSelectedColor: '#f9f9f7',
      itemColor: '#111111',
      itemHoverColor: '#111111',
      itemHoverBg: '#f2f2ed',
    },
    Modal: {
      contentBg: '#f9f9f7',
      headerBg: '#f9f9f7',
    },
  },
}

function App() {
  return (
    <ConfigProvider locale={zhCN} theme={newsprintTheme}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Navigate to="/projects" replace />} />
            <Route path="projects" element={<ProjectList />} />
            <Route path="projects/:id/script" element={<ScriptInput />} />
            <Route path="projects/:id/scenes" element={<SceneEditor />} />
            <Route path="projects/:id/generate" element={<VideoGeneration />} />
            <Route path="projects/:id/compose" element={<CompositionPreview />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
