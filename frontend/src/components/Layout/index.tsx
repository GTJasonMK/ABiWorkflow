import { Layout, Menu } from 'antd'
import {
  ProjectOutlined,
  ReadOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'

const { Content, Sider } = Layout

const menuItems = [
  {
    key: '/projects',
    icon: <ProjectOutlined />,
    label: '项目工作台',
  },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const editionDate = new Date().toLocaleDateString('zh-CN')

  const selectedKey = location.pathname.startsWith('/projects') ? '/projects' : '/projects'

  return (
    <div className="np-shell">
      <header className="np-masthead">
        <div>
          <p className="np-kicker">Vol. 1 | Creative Automation Desk</p>
          <h1 className="np-brand-line">AbiWorkflow Editorial Console</h1>
        </div>
        <div className="np-meta-stack">
          <span className="np-meta-pill">Script-to-Video</span>
          <span className="np-meta-pill">{editionDate}</span>
          <span className="np-meta-pill">China Edition</span>
        </div>
      </header>

      <Layout className="np-app-frame">
        <Sider width={208} className="np-sider" breakpoint="lg" collapsedWidth={0}>
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ height: '100%', borderRight: 0 }}
          />
          <div className="np-side-note">
            <div><ReadOutlined /> 编辑流程</div>
            <div style={{ marginTop: 6 }}>01 剧本输入</div>
            <div>02 场景编辑</div>
            <div>03 视频生成</div>
            <div>04 合成导出</div>
          </div>
        </Sider>
        <Content className="np-content">
          <Outlet />
        </Content>
      </Layout>
    </div>
  )
}
