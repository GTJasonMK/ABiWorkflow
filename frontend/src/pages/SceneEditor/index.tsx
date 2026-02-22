import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Space, Spin, Empty, Row, Col } from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
import { useSceneStore } from '../../stores/sceneStore'
import SceneCard from './SceneCard'
import CharacterPanel from './CharacterPanel'
import PageHeader from '../../components/PageHeader'

export default function SceneEditor() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { scenes, characters, loading, fetchScenes, fetchCharacters } = useSceneStore()

  useEffect(() => {
    if (projectId) {
      fetchScenes(projectId)
      fetchCharacters(projectId)
    }
  }, [projectId, fetchScenes, fetchCharacters])

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  return (
    <div>
      <PageHeader
        kicker="Scene Workshop"
        title="场景编辑"
        subtitle="逐条修订提示词、运镜与时长，确保最终视频叙事连贯。"
        onBack={() => navigate(`/projects/${projectId}/script`)}
        backLabel="返回剧本"
        actions={(
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              disabled={scenes.length === 0}
              onClick={() => navigate(`/projects/${projectId}/generate`)}
            >
              开始生成视频
            </Button>
          </Space>
        )}
      />

      {scenes.length === 0 ? (
        <Empty description="暂无场景数据，请先解析剧本" />
      ) : (
        <Row gutter={16}>
          <Col xs={24} lg={16}>
            {scenes.map((scene) => (
              <SceneCard key={scene.id} scene={scene} projectId={projectId!} />
            ))}
          </Col>
          <Col xs={24} lg={8}>
            <CharacterPanel characters={characters} />
          </Col>
        </Row>
      )}
    </div>
  )
}
