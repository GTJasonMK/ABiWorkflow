import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Input, Space, App as AntdApp, Spin, Typography, Card } from 'antd'
import { SaveOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useProjectStore } from '../../stores/projectStore'
import { useSceneStore } from '../../stores/sceneStore'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { getApiErrorMessage } from '../../utils/error'
import { useWebSocket } from '../../hooks/useWebSocket'
import ProgressBar from '../../components/ProgressBar'
import { shouldSuggestForceRecover } from '../../utils/forceRecover'

const { TextArea } = Input
const { Paragraph } = Typography

export default function ScriptInput() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { currentProject, loading, fetchProject, updateProject } = useProjectStore()
  const { parsing, parseScript } = useSceneStore()
  const [scriptText, setScriptText] = useState('')
  const { message, modal } = AntdApp.useApp()
  const { messages, connected, clearMessages } = useWebSocket(id)
  const parseLastMessage = useMemo(
    () => [...messages].reverse().find((item) => item.type.startsWith('parse_')) ?? null,
    [messages],
  )

  useEffect(() => {
    if (id) {
      fetchProject(id).catch((error) => {
        message.error(getApiErrorMessage(error, '加载项目失败'))
      })
    }
  }, [id, fetchProject, message])

  useEffect(() => {
    setScriptText(currentProject?.script_text ?? '')
  }, [currentProject])

  const handleSave = async () => {
    if (!id) return
    try {
      await updateProject(id, { script_text: scriptText })
      message.success('剧本已保存')
    } catch (error) {
      message.error(getApiErrorMessage(error, '保存失败'))
    }
  }

  const handleParse = async () => {
    if (!scriptText.trim()) {
      message.warning('请先输入剧本内容')
      return
    }
    if (!id) return

    try {
      // 先保存再解析
      clearMessages()
      await updateProject(id, { script_text: scriptText })
      const result = await parseScript(id)
      message.success(`解析完成：${result.character_count} 个角色，${result.scene_count} 个场景`)
      navigate(`/projects/${id}/scenes`)
    } catch (error) {
      if (shouldSuggestForceRecover(error)) {
        modal.confirm({
          title: '检测到解析任务可能中断',
          content: '是否强制恢复项目状态并重试解析？若旧任务仍在执行，可能被新的解析流程覆盖。',
          okText: '强制恢复并重试',
          cancelText: '取消',
          onOk: async () => {
            try {
              clearMessages()
              const result = await parseScript(id, { forceRecover: true })
              message.success(`解析完成：${result.character_count} 个角色，${result.scene_count} 个场景`)
              navigate(`/projects/${id}/scenes`)
            } catch (retryError) {
              message.error(getApiErrorMessage(retryError, '强制恢复后解析仍失败，请检查配置后重试'))
            }
          },
        })
        return
      }
      message.error(getApiErrorMessage(error, '剧本保存或解析失败，请检查配置后重试'))
    }
  }

  if (loading || !currentProject) {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="剧本工作台"
        title={`${currentProject.name} · 剧本编辑`}
        subtitle="输入或修改剧本后，触发智能解析生成角色与场景草案。"
        onBack={() => navigate('/projects')}
        backLabel="返回项目"
        navigation={<WorkflowSteps />}
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

      <div className="np-page-scroll np-script-workspace">
        {(parsing || parseLastMessage) && (
          <Card size="small" className="np-panel-card">
            <ProgressBar
              lastMessage={parseLastMessage}
              connected={connected}
              active={parsing}
              activeText="正在解析剧本并生成场景提示词..."
            />
          </Card>
        )}

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
    </section>
  )
}
