import { Button, Space } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'

type ProjectSectionKey = 'overview' | 'resources' | 'script'

interface ProjectSectionNavProps {
  projectId: string
}

function resolveSection(pathname: string): ProjectSectionKey {
  if (pathname.startsWith('/projects/') && pathname.includes('/resources')) return 'resources'
  if (pathname.startsWith('/projects/') && pathname.includes('/script')) return 'script'
  return 'overview'
}

export default function ProjectSectionNav({ projectId }: ProjectSectionNavProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const activeKey = resolveSection(location.pathname)

  const items: Array<{ key: ProjectSectionKey; label: string; path: string }> = [
    { key: 'overview', label: '项目总览', path: `/projects/${projectId}` },
    { key: 'resources', label: '资源总览', path: `/projects/${projectId}/resources` },
    { key: 'script', label: '剧本分集', path: `/projects/${projectId}/script` },
  ]

  return (
    <div className="np-project-section-nav">
      <Space wrap size={8}>
        {items.map((item) => (
          <Button
            key={item.key}
            type={item.key === activeKey ? 'primary' : 'default'}
            onClick={() => navigate(item.path)}
          >
            {item.label}
          </Button>
        ))}
      </Space>
    </div>
  )
}
