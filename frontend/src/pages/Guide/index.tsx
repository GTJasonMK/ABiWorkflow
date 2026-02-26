import { useNavigate } from 'react-router-dom'
import { Button, Card, Space, Steps, Tag, Typography } from 'antd'
import { BookOutlined, PlayCircleOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'

const { Paragraph, Text } = Typography

const pipelineSteps = [
  {
    title: '创建项目并输入剧本',
    description: '在“项目工作台”新建项目，进入剧本编辑页粘贴或编写内容。',
  },
  {
    title: '解析剧本',
    description: '点击“解析剧本”，系统会提取角色、场景和视频提示词草案。',
  },
  {
    title: '修订场景与角色',
    description: '在“场景编辑”页调整提示词、运镜、时长和角色档案。',
  },
  {
    title: '生成视频片段',
    description: '进入“视频生成”逐场景渲染，失败条目可单独重试。',
  },
  {
    title: '合成与导出',
    description: '设置转场、字幕与配音，完成后下载最终成片。',
  },
]

export default function Guide() {
  const navigate = useNavigate()

  return (
    <section className="np-page">
      <PageHeader
        kicker="上手文档"
        title="使用指南"
        subtitle="第一次使用建议先走一遍标准主链路，再细调生成参数。"
        actions={(
          <Space>
            <Button icon={<BookOutlined />} onClick={() => navigate('/dashboard')}>
              返回总览
            </Button>
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => navigate('/projects')}>
              开始使用
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
        <Card title="标准流程" className="np-panel-card">
          <Steps direction="vertical" current={-1} items={pipelineSteps} />
        </Card>

        <div className="np-dashboard-grid">
          <Card title="运行方式" className="np-panel-card">
            <Paragraph style={{ marginBottom: 10 }}>
              默认启动命令：
            </Paragraph>
            <div className="np-code-box">
              <code>run.bat</code>
            </div>
            <Paragraph className="np-note" style={{ marginTop: 10, marginBottom: 0 }}>
              可选：`run.bat web` 仅浏览器模式，`run.bat desktop` 桌面模式。
            </Paragraph>
          </Card>

          <Card title="常见检查项" className="np-panel-card">
            <Space direction="vertical" size={8}>
              <div><Tag className="np-status-tag">1</Tag> <Text>确保 `.env` 已配置 LLM 服务商参数。</Text></div>
              <div><Tag className="np-status-tag">2</Tag> <Text>若异步任务异常，先检查 Redis 与 Celery 状态。</Text></div>
              <div><Tag className="np-status-tag">3</Tag> <Text>前端报错时优先看“任务中心”和浏览器 Network。</Text></div>
            </Space>
          </Card>
        </div>
      </div>
    </section>
  )
}
