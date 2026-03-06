import { useSearchParams } from 'react-router-dom'
import {
  App as AntdApp,
  Button,
  Card,
  Collapse,
  Empty,
  List,
  Select,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import useOperationsData, { normalizeOperationsTab } from './useOperationsData'
import GlobalAssetManager from './GlobalAssetManager'
import { saveUrlWithPicker } from '../../utils/download'
import { getApiErrorMessage } from '../../utils/error'

const { Text } = Typography

export default function OperationsCenter() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = normalizeOperationsTab(searchParams.get('tab'))
  const { message } = AntdApp.useApp()
  const {
    projectLoading,
    costProjectId,
    setCostProjectId,
    assetsProjectId,
    setAssetsProjectId,
    projectOptions,
    assetsTab,
    setAssetsTab,
    costLoading,
    costPayload,
    costError,
    assetsLoading,
    assetsPayload,
    assetsError,
    globalAssetsLoading,
    globalAssetsPayload,
    globalAssetsError,
    refreshCurrent,
  } = useOperationsData({
    activeTab,
    notifyError: (text) => message.error(text),
  })

  const costsProjectSelector = (
    <Card size="small" className="np-panel-card">
      <Space wrap>
        <Text type="secondary">成本统计项目：</Text>
        <Select
          style={{ minWidth: 260 }}
          value={costProjectId ?? undefined}
          options={projectOptions}
          placeholder="选择项目"
          onChange={setCostProjectId}
        />
      </Space>
    </Card>
  )

  const assetsProjectSelector = (
    <Card size="small" className="np-panel-card">
      <Space wrap>
        <Text type="secondary">项目资产项目：</Text>
        <Select
          style={{ minWidth: 260 }}
          value={assetsProjectId ?? undefined}
          options={projectOptions}
          placeholder="选择项目"
          onChange={setAssetsProjectId}
        />
      </Space>
    </Card>
  )

  const handleExportComposition = async (compositionId: string, downloadUrl: string) => {
    try {
      const result = await saveUrlWithPicker({
        url: downloadUrl,
        title: '导出成片',
        defaultFileName: `composition-${compositionId.slice(0, 8)}.mp4`,
      })
      if (result.mode === 'desktop' && !result.canceled && result.filePath) {
        message.success(`已导出到：${result.filePath}`)
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, '导出成片失败'))
    }
  }

  const costsContent = projectLoading && projectOptions.length === 0 ? (
    <div className="np-page-loading">
      <Spin size="large" />
    </div>
  ) : !costProjectId ? (
    <>
      {costsProjectSelector}
      <Card className="np-panel-card">
        <Empty description="暂无项目，请先创建项目。" />
      </Card>
    </>
  ) : costLoading ? (
    <>
      {costsProjectSelector}
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    </>
  ) : costError ? (
    <>
      {costsProjectSelector}
      <Card className="np-panel-card">
        <Text className="np-task-error">{costError}</Text>
      </Card>
    </>
  ) : costPayload ? (
    <>
      {costsProjectSelector}
      <div className="np-kpi-grid">
        <article className="np-kpi-card">
          <p className="np-kpi-label">调用次数</p>
          <p className="np-kpi-value">{costPayload.summary.count}</p>
        </article>
        <article className="np-kpi-card">
          <p className="np-kpi-label">总成本</p>
          <p className="np-kpi-value">
            {costPayload.summary.total_cost.toFixed(4)} {costPayload.summary.currency}
          </p>
        </article>
        <article className="np-kpi-card">
          <p className="np-kpi-label">计量总量</p>
          <p className="np-kpi-value">{costPayload.summary.total_quantity.toFixed(2)}</p>
        </article>
      </div>

      <Card title="供应商分布" className="np-panel-card">
        {costPayload.summary.by_provider.length === 0 ? (
          <Empty description="暂无供应商统计" />
        ) : (
          <Space wrap>
            {costPayload.summary.by_provider.map((item) => (
              <Tag key={item.provider_type} className="np-status-tag">
                {item.provider_type} · {item.count} 次 · {item.total_cost.toFixed(4)} USD
              </Tag>
            ))}
          </Space>
        )}
      </Card>

      <Card title="成本明细（最近 300 条）" className="np-panel-card">
        {costPayload.items.length === 0 ? (
          <Empty description="暂无成本明细" />
        ) : (
          <List
            dataSource={costPayload.items}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={(
                    <Space size={8}>
                      <Tag className="np-status-tag">{item.provider_type}</Tag>
                      <Text>{item.usage_type}</Text>
                      {item.model_name && <Text type="secondary">{item.model_name}</Text>}
                    </Space>
                  )}
                  description={(
                    <Space size={12} wrap>
                      <Text type="secondary">数量：{item.quantity} {item.unit}</Text>
                      <Text type="secondary">单价：{item.unit_price.toFixed(6)} {item.currency}</Text>
                      <Text type="secondary">总价：{item.total_cost.toFixed(6)} {item.currency}</Text>
                      {item.created_at && (
                        <Text type="secondary">
                          时间：{new Date(item.created_at).toLocaleString('zh-CN')}
                        </Text>
                      )}
                    </Space>
                  )}
                />
              </List.Item>
            )}
          />
        )}
      </Card>
    </>
  ) : (
    <>
      {costsProjectSelector}
      <Card className="np-panel-card">
        <Empty description="暂无统计数据" />
      </Card>
    </>
  )

  const projectAssetsContent = !assetsProjectId ? (
    <>
      {assetsProjectSelector}
      <Card className="np-panel-card">
        <Empty description="暂无项目，请先创建项目。" />
      </Card>
    </>
  ) : assetsLoading ? (
    <>
      {assetsProjectSelector}
      <div className="np-page-loading">
        <Spin size="large" />
      </div>
    </>
  ) : assetsError ? (
    <>
      {assetsProjectSelector}
      <Card className="np-panel-card">
        <Text className="np-task-error">{assetsError}</Text>
      </Card>
    </>
  ) : assetsPayload ? (
    <>
      {assetsProjectSelector}
      <div className="np-kpi-grid">
        <article className="np-kpi-card">
          <p className="np-kpi-label">分镜数</p>
          <p className="np-kpi-value">{assetsPayload.summary.panel_count}</p>
        </article>
        <article className="np-kpi-card">
          <p className="np-kpi-label">片段总数</p>
          <p className="np-kpi-value">{assetsPayload.summary.clip_count}</p>
        </article>
        <article className="np-kpi-card">
          <p className="np-kpi-label">可用成片</p>
          <p className="np-kpi-value">{assetsPayload.summary.composition_count}</p>
        </article>
      </div>

      <Card title="合成成片" className="np-panel-card">
        {assetsPayload.compositions.length === 0 ? (
          <Empty description="暂无合成成片" />
        ) : (
          <div className="np-asset-grid">
            {assetsPayload.compositions.map((item) => {
              const src = item.media_url || item.download_url
              return (
                <Card
                  key={item.id}
                  size="small"
                  title={`成片 ${item.id.slice(0, 8)}`}
                  extra={<Tag className={`np-status-tag np-status-${item.status}`}>{item.status}</Tag>}
                >
                  {src ? (
                    <video controls preload="metadata" className="np-asset-video" src={src} />
                  ) : (
                    <Text type="secondary">文件暂不可用</Text>
                  )}
                  <Space wrap style={{ marginTop: 10 }}>
                    <Tag className="np-status-tag">转场 {item.transition_type}</Tag>
                    {item.include_subtitles && <Tag className="np-status-tag">字幕</Tag>}
                    {item.include_tts && <Tag className="np-status-tag">配音</Tag>}
                  </Space>
                  <div style={{ marginTop: 8 }}>
                    <Button
                      type="link"
                      style={{ padding: 0 }}
                      onClick={() => {
                        void handleExportComposition(item.id, item.download_url)
                      }}
                    >
                      下载成片
                    </Button>
                  </div>
                </Card>
              )
            })}
          </div>
        )}
      </Card>

      <Card title="分镜片段" className="np-panel-card">
        <Collapse
          items={assetsPayload.panels.map((panel) => ({
            key: panel.panel_id,
            label: (
              <Space>
                <Text>分镜 {panel.panel_order + 1} · {panel.title}</Text>
                <Tag className={`np-status-tag np-status-${panel.status}`}>{panel.status}</Tag>
                <Text type="secondary">片段 {panel.clips.length}</Text>
              </Space>
            ),
            children: panel.clips.length === 0 ? (
              <Empty description="该分镜暂无生成片段" />
            ) : (
              <div className="np-asset-grid">
                {panel.clips.map((clip) => (
                  <Card
                    key={clip.id}
                    size="small"
                    title={`片段 ${clip.clip_order + 1}`}
                    extra={<Tag className={`np-status-tag np-status-${clip.status}`}>{clip.status}</Tag>}
                  >
                    {clip.media_url ? (
                      <video controls preload="metadata" className="np-asset-video" src={clip.media_url} />
                    ) : (
                      <Text type="secondary">片段文件不可用</Text>
                    )}
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">时长：{clip.duration_seconds.toFixed(1)} 秒</Text>
                    </div>
                    {clip.error_message && (
                      <div style={{ marginTop: 8 }}>
                        <Text className="np-task-error">{clip.error_message}</Text>
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            ),
          }))}
        />
      </Card>
    </>
  ) : (
    <>
      {assetsProjectSelector}
      <Card className="np-panel-card">
        <Empty description="暂无资产数据" />
      </Card>
    </>
  )

  const globalAssetsContent = globalAssetsLoading ? (
    <div className="np-page-loading">
      <Spin size="large" />
    </div>
  ) : globalAssetsError ? (
    <Card className="np-panel-card">
      <Text className="np-task-error">{globalAssetsError}</Text>
    </Card>
  ) : globalAssetsPayload ? (
    <>
      <div className="np-kpi-grid">
        <article className="np-kpi-card">
          <p className="np-kpi-label">目录</p>
          <p className="np-kpi-value">{globalAssetsPayload.folders.length}</p>
        </article>
        <article className="np-kpi-card">
          <p className="np-kpi-label">角色素材</p>
          <p className="np-kpi-value">{globalAssetsPayload.characters.length}</p>
        </article>
        <article className="np-kpi-card">
          <p className="np-kpi-label">地点素材</p>
          <p className="np-kpi-value">{globalAssetsPayload.locations.length}</p>
        </article>
        <article className="np-kpi-card">
          <p className="np-kpi-label">语音库</p>
          <p className="np-kpi-value">{globalAssetsPayload.voices.length}</p>
        </article>
      </div>

      <Card title="全局语音" className="np-panel-card">
        {globalAssetsPayload.voices.length === 0 ? (
          <Empty description="暂无语音素材" />
        ) : (
          <Space wrap>
            {globalAssetsPayload.voices.map((item) => (
              <Tag key={item.id} className="np-status-tag">
                {item.name} · {item.voice_code}
              </Tag>
            ))}
          </Space>
        )}
      </Card>

      <Card title="全局角色与地点" className="np-panel-card">
        <Collapse
          items={[
            {
              key: 'characters',
              label: `角色素材 (${globalAssetsPayload.characters.length})`,
              children: globalAssetsPayload.characters.length === 0 ? (
                <Empty description="暂无角色素材" />
              ) : (
                <List
                  dataSource={globalAssetsPayload.characters}
                  renderItem={(item) => (
                    <List.Item>
                      <Space>
                        <Text>{item.name}</Text>
                        {item.alias && <Text type="secondary">别名：{item.alias}</Text>}
                      </Space>
                    </List.Item>
                  )}
                />
              ),
            },
            {
              key: 'locations',
              label: `地点素材 (${globalAssetsPayload.locations.length})`,
              children: globalAssetsPayload.locations.length === 0 ? (
                <Empty description="暂无地点素材" />
              ) : (
                <List
                  dataSource={globalAssetsPayload.locations}
                  renderItem={(item) => (
                    <List.Item>
                      <Space>
                        <Text>{item.name}</Text>
                        {item.description && <Text type="secondary">{item.description}</Text>}
                      </Space>
                    </List.Item>
                  )}
                />
              ),
            },
          ]}
        />
      </Card>

      <GlobalAssetManager
        overview={globalAssetsPayload}
        projectOptions={projectOptions}
        defaultProjectId={assetsProjectId}
      />
    </>
  ) : (
    <Card className="np-panel-card">
      <Empty description="暂无全局资产数据" />
    </Card>
  )

  return (
    <section className="np-page">
      <PageHeader
        kicker="运营与资产"
        title="运营中心"
        subtitle="统一查看成本统计、项目资产与全局资产，减少分散入口。"
        actions={(
          <Space>
            <Button
              icon={<ReloadOutlined />}
              loading={costLoading || assetsLoading || globalAssetsLoading}
              onClick={refreshCurrent}
            >
              刷新当前页
            </Button>
          </Space>
        )}
      />

      <div className="np-page-scroll">
        <Tabs
          activeKey={activeTab}
          onChange={(nextKey) => {
            const nextTab = normalizeOperationsTab(nextKey)
            const nextParams = new URLSearchParams(searchParams)
            nextParams.set('tab', nextTab)
            setSearchParams(nextParams, { replace: true })
          }}
          items={[
            {
              key: 'costs',
              label: '成本统计',
              children: costsContent,
            },
            {
              key: 'assets',
              label: '媒体资产',
              children: (
                <Tabs
                  activeKey={assetsTab}
                  onChange={(next) => setAssetsTab(next === 'global' ? 'global' : 'project')}
                  items={[
                    { key: 'project', label: '项目资产', children: projectAssetsContent },
                    { key: 'global', label: '全局资产中心', children: globalAssetsContent },
                  ]}
                />
              ),
            },
          ]}
        />
      </div>
    </section>
  )
}
