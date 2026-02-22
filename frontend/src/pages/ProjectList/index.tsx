import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Modal, Form, Input, Table, Tag, Space, Popconfirm, message } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useProjectStore } from '../../stores/projectStore'
import { STATUS_MAP } from '../../types/project'
import type { ProjectListItem, ProjectStatus } from '../../types/project'
import PageHeader from '../../components/PageHeader'

export default function ProjectList() {
  const navigate = useNavigate()
  const { projects, total, page, loading, fetchProjects, createProject, deleteProject } = useProjectStore()
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      const project = await createProject(values.name, values.description)
      setCreateModalOpen(false)
      form.resetFields()
      message.success('项目创建成功')
      navigate(`/projects/${project.id}/script`)
    } catch {
      // 表单校验失败
    }
  }

  const handleDelete = async (id: string) => {
    await deleteProject(id)
    message.success('项目已删除')
  }

  const completedCount = projects.filter((project) => project.status === 'completed').length
  const activeCount = projects.filter(
    (project) => project.status === 'parsing' || project.status === 'generating' || project.status === 'composing',
  ).length

  const columns: ColumnsType<ProjectListItem> = [
    {
      title: '项目名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record) => (
        <button type="button" className="np-project-link" onClick={() => navigate(`/projects/${record.id}/script`)}>
          {name}
        </button>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: ProjectStatus) => {
        const info = STATUS_MAP[status]
        return <Tag className={`np-status-tag np-status-${status}`}>{info.label}</Tag>
      },
    },
    {
      title: '场景数',
      dataIndex: 'scene_count',
      key: 'scene_count',
      width: 80,
      align: 'center',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (val: string) => new Date(val).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => navigate(`/projects/${record.id}/script`)}
          >
            编辑
          </Button>
          {record.status === 'parsed' && (
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={() => navigate(`/projects/${record.id}/scenes`)}
            >
              场景
            </Button>
          )}
          <Popconfirm title="确认删除此项目？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        kicker="Project Desk"
        title="项目工作台"
        subtitle="管理剧本生产线：创建项目、追踪状态、进入编辑。"
        actions={(
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            新建项目
          </Button>
        )}
      />

      <div className="np-kpi-grid">
        <article className="np-kpi-card">
          <p className="np-kpi-label">Total Projects</p>
          <p className="np-kpi-value">{total}</p>
        </article>
        <article className="np-kpi-card">
          <p className="np-kpi-label">In Progress</p>
          <p className="np-kpi-value">{activeCount}</p>
        </article>
        <article className="np-kpi-card">
          <p className="np-kpi-label">Completed</p>
          <p className="np-kpi-value">{completedCount}</p>
        </article>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={projects}
        loading={loading}
        bordered
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => fetchProjects(p),
          showTotal: (t) => `共 ${t} 个项目`,
        }}
      />

      <Modal
        title="新建项目"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateModalOpen(false); form.resetFields() }}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="输入项目名称" />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea rows={3} placeholder="输入项目描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
