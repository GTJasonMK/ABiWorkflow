import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom'
import { ConfigProvider, App as AntdApp, Spin } from 'antd'
import type { ThemeConfig } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import AppLayout from './components/Layout'
import { getDefaultHomePath } from './preferences'

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

function HomeRedirect() {
  return <Navigate to={getDefaultHomePath()} replace />
}

const Dashboard = lazy(() => import('./pages/Dashboard'))
const ProjectList = lazy(() => import('./pages/ProjectList'))
const ProjectWorkbench = lazy(() => import('./pages/ProjectWorkbench'))
const ProjectResources = lazy(() => import('./pages/ProjectResources'))
const ScriptInput = lazy(() => import('./pages/ScriptInput'))
const AssetBinding = lazy(() => import('./pages/AssetBinding'))
const StoryboardEditor = lazy(() => import('./pages/StoryboardEditor'))
const VideoGeneration = lazy(() => import('./pages/VideoGeneration'))
const CompositionPreview = lazy(() => import('./pages/CompositionPreview'))
const TaskHub = lazy(() => import('./pages/TaskHub'))
const OperationsCenter = lazy(() => import('./pages/OperationsCenter'))
const SystemSettings = lazy(() => import('./pages/SystemSettings'))
const Guide = lazy(() => import('./pages/Guide'))

function pageSuspense(node: ReactNode) {
  return (
    <Suspense
      fallback={(
        <div className="np-page-loading">
          <Spin size="large" />
        </div>
      )}
    >
      {node}
    </Suspense>
  )
}

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <HomeRedirect /> },
      { path: 'dashboard', element: pageSuspense(<Dashboard />) },
      { path: 'projects', element: pageSuspense(<ProjectList />) },
      { path: 'projects/:id', element: pageSuspense(<ProjectWorkbench />) },
      { path: 'projects/:id/resources', element: pageSuspense(<ProjectResources />) },
      { path: 'projects/:id/script', element: pageSuspense(<ScriptInput />) },
      { path: 'projects/:id/assets/:episodeId', element: pageSuspense(<AssetBinding />) },
      { path: 'projects/:id/storyboard/:episodeId', element: pageSuspense(<StoryboardEditor />) },
      { path: 'projects/:id/video/:episodeId', element: pageSuspense(<VideoGeneration />) },
      { path: 'projects/:id/preview/:episodeId', element: pageSuspense(<CompositionPreview />) },
      { path: 'tasks', element: pageSuspense(<TaskHub />) },
      { path: 'operations', element: pageSuspense(<OperationsCenter />) },
      { path: 'settings', element: pageSuspense(<SystemSettings />) },
      { path: 'guide', element: pageSuspense(<Guide />) },
    ],
  },
])

function App() {
  return (
    <ConfigProvider locale={zhCN} theme={newsprintTheme}>
      <AntdApp>
        <RouterProvider router={router} />
      </AntdApp>
    </ConfigProvider>
  )
}

export default App
