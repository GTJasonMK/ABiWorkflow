import type { ReactNode } from 'react'
import { Button } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'

interface PageHeaderProps {
  kicker?: string
  title: string
  subtitle?: string
  actions?: ReactNode
  /** 返回按钮右侧的导航区域（如工作流步骤条） */
  navigation?: ReactNode
  onBack?: () => void
  backLabel?: string
}

export default function PageHeader({
  kicker,
  title,
  subtitle,
  actions,
  navigation,
  onBack,
  backLabel = '返回',
}: PageHeaderProps) {
  return (
    <header className="np-page-header">
      <div>
        {kicker && <p className="np-kicker">{kicker}</p>}
        {(onBack || navigation) && (
          <div className="np-page-nav-row">
            {onBack && (
              <Button icon={<ArrowLeftOutlined />} onClick={onBack}>
                {backLabel}
              </Button>
            )}
            {navigation && <div className="np-page-nav-slot">{navigation}</div>}
          </div>
        )}
        <h2 className="np-page-title">{title}</h2>
        {subtitle && <p className="np-page-subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="np-page-actions">{actions}</div>}
    </header>
  )
}
