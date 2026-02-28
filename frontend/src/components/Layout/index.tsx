import { Layout, Menu } from 'antd'
import {
  DashboardOutlined,
  DeploymentUnitOutlined,
  ProfileOutlined,
  ProjectOutlined,
  ReadOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import TaskCenter from '../TaskCenter'

const { Content, Sider } = Layout

const menuItems = [
  {
    key: '/dashboard',
    icon: <DashboardOutlined />,
    label: '总览看板',
  },
  {
    key: '/projects',
    icon: <ProjectOutlined />,
    label: '项目工作台',
  },
  {
    key: '/tasks',
    icon: <ProfileOutlined />,
    label: '任务中心',
  },
  {
    key: '/operations',
    icon: <DeploymentUnitOutlined />,
    label: '运营中心',
  },
  {
    key: '/settings',
    icon: <SettingOutlined />,
    label: '系统设置',
  },
  {
    key: '/guide',
    icon: <ReadOutlined />,
    label: '使用指南',
  },
]

function resolveSelectedKey(pathname: string): string {
  if (pathname === '/dashboard' || pathname.startsWith('/dashboard/')) return '/dashboard'
  if (pathname === '/projects' || pathname.startsWith('/projects/')) {
    return '/projects'
  }
  if (pathname === '/tasks' || pathname.startsWith('/tasks/')) {
    return '/tasks'
  }
  if (pathname === '/operations' || pathname.startsWith('/operations/')) {
    return '/operations'
  }
  if (pathname === '/settings' || pathname.startsWith('/settings/')) {
    return '/settings'
  }
  if (pathname === '/guide' || pathname.startsWith('/guide/')) return '/guide'
  return '/dashboard'
}

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const editionDate = new Date().toLocaleDateString('zh-CN')

  const selectedKey = resolveSelectedKey(location.pathname)

  return (
    <div className="np-shell">
      <header className="np-masthead">
        <div>
          <p className="np-kicker">第 1 期 | 创作自动化工作台</p>
          <h1 className="np-brand-line">AbiWorkflow 创作控制台</h1>
        </div>
        <div className="np-meta-stack">
          <TaskCenter />
          <span className="np-meta-pill">剧本到视频</span>
          <span className="np-meta-pill">{editionDate}</span>
          <span className="np-meta-pill">中文版本</span>
        </div>
      </header>

      <Layout className="np-app-frame">
        <Sider width={208} className="np-sider" breakpoint="lg" collapsedWidth={0}>
          <div className="np-sider-scroll">
            <Menu
              className="np-sider-menu"
              mode="inline"
              selectedKeys={[selectedKey]}
              items={menuItems}
              onClick={({ key }) => navigate(key)}
            />
          </div>
        </Sider>
        <Content className="np-content">
          <div className="np-page-host">
            <Outlet />
          </div>
        </Content>
      </Layout>
    </div>
  )
}
