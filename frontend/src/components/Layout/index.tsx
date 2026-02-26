import { Layout, Menu } from 'antd'
import {
  DashboardOutlined,
  ProfileOutlined,
  ProjectOutlined,
  ReadOutlined,
  SettingOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'

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
    key: '/assets',
    icon: <VideoCameraOutlined />,
    label: '媒体资产库',
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

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const editionDate = new Date().toLocaleDateString('zh-CN')

  const selectedKey = menuItems.find((item) => (
    location.pathname === item.key || location.pathname.startsWith(`${item.key}/`)
  ))?.key ?? '/dashboard'

  return (
    <div className="np-shell">
      <header className="np-masthead">
        <div>
          <p className="np-kicker">第 1 期 | 创作自动化工作台</p>
          <h1 className="np-brand-line">AbiWorkflow 创作控制台</h1>
        </div>
        <div className="np-meta-stack">
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
