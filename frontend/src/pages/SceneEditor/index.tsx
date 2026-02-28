import { useCallback, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Space, Spin, Empty, App as AntdApp, Segmented, Card } from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useSceneStore } from '../../stores/sceneStore'
import type { Scene } from '../../types/scene'
import SceneCard from './SceneCard'
import CharacterPanel from './CharacterPanel'
import PageHeader from '../../components/PageHeader'
import WorkflowSteps from '../../components/WorkflowSteps'
import { getApiErrorMessage } from '../../utils/error'
import EpisodePanelBoard from './EpisodePanelBoard'

/** 可排序的场景卡片包装器 */
function SortableSceneCard({ scene, projectId }: { scene: Scene; projectId: string }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: scene.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div ref={setNodeRef} style={style}>
      <SceneCard
        scene={scene}
        projectId={projectId}
        dragHandleProps={{ ...attributes, ...listeners }}
      />
    </div>
  )
}

export default function SceneEditor() {
  const { id: projectId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { scenes, characters, loading, fetchScenes, fetchCharacters, reorderScenes } = useSceneStore()
  const { message } = AntdApp.useApp()
  const editorMode: 'scene' | 'episode' = searchParams.get('mode') === 'episode' ? 'episode' : 'scene'

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  useEffect(() => {
    if (projectId) {
      Promise.all([fetchScenes(projectId), fetchCharacters(projectId)]).catch((error) => {
        message.error(getApiErrorMessage(error, '加载场景或角色失败'))
      })
    }
  }, [projectId, fetchScenes, fetchCharacters, message])

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id || !projectId) return

      const oldIndex = scenes.findIndex((s) => s.id === active.id)
      const newIndex = scenes.findIndex((s) => s.id === over.id)
      if (oldIndex === -1 || newIndex === -1) return

      // 构建新顺序的 scene ID 数组
      const newSceneIds = scenes.map((s) => s.id)
      const [moved] = newSceneIds.splice(oldIndex, 1)
      newSceneIds.splice(newIndex, 0, moved!)

      reorderScenes(projectId, newSceneIds).catch((error) => {
        message.error(getApiErrorMessage(error, '场景排序失败'))
      })
    },
    [scenes, projectId, reorderScenes, message],
  )

  if (loading && editorMode === 'scene') {
    return (
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <section className="np-page">
      <PageHeader
        kicker="场景工坊"
        title="场景编辑"
        subtitle="拖拽排列场景顺序，修订提示词、运镜与时长，确保叙事连贯。"
        onBack={() => navigate(`/projects/${projectId}/script`)}
        backLabel="返回剧本"
        navigation={<WorkflowSteps />}
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

      <div className="np-page-scroll">
        <Card className="np-panel-card" styles={{ body: { padding: 12 } }}>
          <Segmented
            value={editorMode}
            options={[
              { label: '场景模式', value: 'scene' },
              { label: '分集分镜模式', value: 'episode' },
            ]}
            onChange={(value) => {
              const nextMode = value as 'scene' | 'episode'
              const nextParams = new URLSearchParams(searchParams)
              if (nextMode === 'episode') {
                nextParams.set('mode', 'episode')
              } else {
                nextParams.delete('mode')
              }
              setSearchParams(nextParams, { replace: true })
            }}
          />
        </Card>

        {editorMode === 'scene' ? (
          <div className="np-scene-editor-layout">
            {scenes.length === 0 ? (
              <div className="np-scene-empty">
                <Empty description="暂无场景数据，请先解析剧本" />
              </div>
            ) : (
              <>
                <section className="np-scene-column np-scene-column-main">
                  <div className="np-scene-column-scroll">
                    <DndContext
                      sensors={sensors}
                      collisionDetection={closestCenter}
                      onDragEnd={handleDragEnd}
                    >
                      <SortableContext
                        items={scenes.map((s) => s.id)}
                        strategy={verticalListSortingStrategy}
                      >
                        {scenes.map((scene) => (
                          <SortableSceneCard
                            key={scene.id}
                            scene={scene}
                            projectId={projectId!}
                          />
                        ))}
                      </SortableContext>
                    </DndContext>
                  </div>
                </section>
                <aside className="np-scene-column np-scene-column-side">
                  <CharacterPanel characters={characters} />
                </aside>
              </>
            )}
          </div>
        ) : (
          projectId ? <EpisodePanelBoard projectId={projectId} /> : <Empty description="项目参数缺失" />
        )}
      </div>
    </section>
  )
}
