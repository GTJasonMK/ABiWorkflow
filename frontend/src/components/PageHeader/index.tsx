import type { ReactNode } from 'react'
import { Button } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'

interface PageHeaderProps {
  kicker?: string
  title: string
  subtitle?: string
  actions?: ReactNode
  onBack?: () => void
  backLabel?: string
}

export default function PageHeader({
  kicker,
  title,
  subtitle,
  actions,
  onBack,
  backLabel = '返回',
}: PageHeaderProps) {
  return (
    <header className="np-page-header">
      <div>
        {kicker && <p className="np-kicker">{kicker}</p>}
        {onBack && (
          <Button icon={<ArrowLeftOutlined />} onClick={onBack} style={{ marginBottom: 8 }}>
            {backLabel}
          </Button>
        )}
        <h2 className="np-page-title">{title}</h2>
        {subtitle && <p className="np-page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="np-page-actions">{actions}</div>}
    </header>
  )
}
