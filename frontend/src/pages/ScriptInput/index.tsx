import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Input, Space, message, Spin, Typography } from 'antd'
import { SaveOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useProjectStore } from '../../stores/projectStore'
import { useSceneStore } from '../../stores/sceneStore'
import PageHeader from '../../components/PageHeader'

const { TextArea } = Input
const { Paragraph } = Typography

export default function ScriptInput() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { currentProject, loading, fetchProject, updateProject } = useProjectStore()
  const { parsing, parseScript } = useSceneStore()
  const [scriptText, setScriptText] = useState('')

  useEffect(() => {
    if (id) {
      fetchProject(id)
    }
  }, [id, fetchProject])

  useEffect(() => {
    if (currentProject?.script_text) {
      setScriptText(currentProject.script_text)
    }
  }, [currentProject])

  const handleSave = async () => {
    if (!id) return
    await updateProject(id, { script_text: scriptText })
    message.success('剧本已保存')
  }

  const handleParse = async () => {
    if (!scriptText.trim()) {
      message.warning('请先输入剧本内容')
      return
    }
    if (!id) return

    // 先保存再解析
    await updateProject(id, { script_text: scriptText })

    try {
      const result = await parseScript(id)
      message.success(`解析完成：${result.character_count} 个角色，${result.scene_count} 个场景`)
      navigate(`/projects/${id}/scenes`)
    } catch {
      message.error('剧本解析失败，请检查 LLM 配置')
    }
  }

  if (loading || !currentProject) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  return (
    <div>
      <PageHeader
        kicker="Script Desk"
        title={`${currentProject.name} · 剧本编辑`}
        subtitle="输入或修改剧本后，触发 AI 解析生成角色与场景草案。"
        onBack={() => navigate('/projects')}
        backLabel="返回项目"
        actions={(
          <Space>
            <Button icon={<SaveOutlined />} onClick={handleSave}>
              保存剧本
            </Button>
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleParse} loading={parsing}>
              {parsing ? '解析中...' : '解析剧本'}
            </Button>
          </Space>
        )}
      />

      <TextArea
        className="np-script-input"
        rows={22}
        value={scriptText}
        onChange={(e) => setScriptText(e.target.value)}
        placeholder={'在此输入剧本内容...\n\n示例：\n场景一：清晨，城市街道\n小明背着书包走在上学的路上，阳光透过树叶洒在地面上。\n小明（独白）：今天是新学期的第一天...'}
      />
      <section className="np-script-tip">
        <Paragraph style={{ margin: 0 }}>
          建议写法：每个场景以“场景 X”开头，包含时间、地点、角色动作、运镜、台词和氛围关键词，
          这样模型能更稳定地拆分为可生成的视频片段。
        </Paragraph>
      </section>
    </div>
  )
}
