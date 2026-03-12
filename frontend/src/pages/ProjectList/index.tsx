import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Modal, Form, Table, Tag, Space, Dropdown, App as AntdApp } from 'antd'
import { PlusOutlined, DeleteOutlined, RightOutlined, CopyOutlined, EllipsisOutlined } from '@ant-design/icons'
import type { ColumnsType, TableProps } from 'antd/es/table'
import type { SorterResult } from 'antd/es/table/interface'
import { useProjectStore } from '../../stores/projectStore'
import { STATUS_MAP } from '../../types/project'
import type { ProjectListItem, ProjectStatus } from '../../types/project'
import PageHeader from '../../components/PageHeader'
import { getApiErrorMessage } from '../../utils/error'

const ALL_STATUSES = Object.keys(STATUS_MAP) as ProjectStatus[]

export default function ProjectList() {
  const navigate = useNavigate()
  const {
    projects, total, page, loading, stats,
    fetchProjects, createProject, deleteProject, duplicateProject,
  } = useProjectStore()
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [form] = Form.useForm()
  const { message } = AntdApp.useApp()

  // 搜索/筛选/排序的本地状态
  const [keyword, setKeyword] = useState('')
  const [selectedStatuses, setSelectedStatuses] = useState<ProjectStatus[]>([])
  const [sortBy, setSortBy] = useState<string>('created_at')
  const [sortOrder, setSortOrder] = useState<string>('desc')

  // 防抖搜索
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const doFetch = useCallback((overrides?: Record<string, unknown>) => {
    const params = {
      page: 1,
      keyword: keyword.trim() || undefined,
      status: selectedStatuses.length > 0 ? selectedStatuses.join(',') : undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
      ...overrides,
    }
    fetchProjects(params).catch((error) => {
      message.error(getApiErrorMessage(error, '加载项目列表失败'))
    })
  }, [fetchProjects, keyword, selectedStatuses, sortBy, sortOrder, message])

  useEffect(() => {
    doFetch()
    // 仅在首次挂载时执行
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSearch = (value: string) => {
    setKeyword(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      doFetch({ keyword: value.trim() || undefined, page: 1 })
    }, 300)
  }

  const handleStatusToggle = (status: ProjectStatus) => {
    const next = selectedStatuses.includes(status)
      ? selectedStatuses.filter((s) => s !== status)
      : [...selectedStatuses, status]
    setSelectedStatuses(next)
    doFetch({ status: next.length > 0 ? next.join(',') : undefined, page: 1 })
  }

  const handleTableChange: TableProps<ProjectListItem>['onChange'] = (_pagination, _filters, sorter) => {
    const s = sorter as SorterResult<ProjectListItem>
    if (s.columnKey && s.order) {
      const newSortBy = s.columnKey as string
      const newSortOrder = s.order === 'ascend' ? 'asc' : 'desc'
      setSortBy(newSortBy)
      setSortOrder(newSortOrder)
      doFetch({ sort_by: newSortBy, sort_order: newSortOrder, page: 1 })
    }
  }

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      const project = await createProject(values.name, values.description)
      setCreateModalOpen(false)
      form.resetFields()
      message.success('项目创建成功')
      navigate(`/projects/${project.id}`)
    } catch (error) {
      const maybeValidation = error as { errorFields?: unknown[] }
      if (Array.isArray(maybeValidation?.errorFields) && maybeValidation.errorFields.length > 0) {
        return
      }
      message.error(getApiErrorMessage(error, '项目创建失败'))
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteProject(id)
      message.success('项目已删除')
    } catch (error) {
      message.error(getApiErrorMessage(error, '项目删除失败'))
    }
  }

  const handleDuplicate = async (id: string) => {
    try {
      await duplicateProject(id)
      message.success('项目已复制')
    } catch (error) {
      message.error(getApiErrorMessage(error, '项目复制失败'))
    }
  }

  // KPI 使用后端返回的全局统计
  const activeCount = (stats.parsing ?? 0) + (stats.generating ?? 0) + (stats.composing ?? 0)
  const completedCount = stats.completed ?? 0
  const totalAll = Object.values(stats).reduce((sum, n) => sum + n, 0)

  const columns: ColumnsType<ProjectListItem> = [
    {
      title: '项目名称',
      dataIndex: 'name',
      key: 'name',
      sorter: true,
      sortOrder: sortBy === 'name' ? (sortOrder === 'asc' ? 'ascend' : 'descend') : undefined,
      ellipsis: true,
      width: 200,
      render: (name: string, record) => (
        <button type="button" className="np-project-link" onClick={() => navigate(`/projects/${record.id}`)}>
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
      width: 90,
      render: (status: ProjectStatus) => {
        const info = STATUS_MAP[status]
        return <Tag className={`np-status-tag np-status-${status}`}>{info.label}</Tag>
      },
    },
    {
      title: '分镜',
      dataIndex: 'panel_count',
      key: 'panel_count',
      width: 60,
      align: 'center',
    },
    {
      title: '角色',
      dataIndex: 'character_count',
      key: 'character_count',
      width: 60,
      align: 'center',
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 170,
      sorter: true,
      sortOrder: sortBy === 'updated_at' ? (sortOrder === 'asc' ? 'ascend' : 'descend') : undefined,
      render: (val: string) => new Date(val).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <Space size={4}>
          <Button
            size="small"
            type="primary"
            icon={<RightOutlined />}
            onClick={() => navigate(`/projects/${record.id}`)}
          >
            继续
          </Button>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'duplicate',
                  icon: <CopyOutlined />,
                  label: '复制项目',
                  onClick: () => handleDuplicate(record.id),
                },
                {
                  key: 'delete',
                  icon: <DeleteOutlined />,
                  label: '删除项目',
                  danger: true,
                  onClick: () => {
                    Modal.confirm({
                      title: '确认删除此项目？',
                      onOk: () => handleDelete(record.id),
                      okText: '删除',
                      cancelText: '取消',
                      okButtonProps: { danger: true },
                    })
                  },
                },
              ],
            }}
            trigger={['click']}
          >
            <Button size="small" icon={<EllipsisOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ]

  return (
    <section className="np-page">
      <PageHeader
        kicker="项目总览"
        title="项目工作台"
        subtitle="管理剧本生产线：创建项目、追踪状态、进入编辑。"
        actions={(
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            新建项目
          </Button>
        )}
      />

      <div className="np-page-scroll">
        <div className="np-kpi-grid">
          <article className="np-kpi-card">
            <p className="np-kpi-label">项目总数</p>
            <p className="np-kpi-value">{totalAll}</p>
          </article>
          <article className="np-kpi-card">
            <p className="np-kpi-label">进行中</p>
            <p className="np-kpi-value">{activeCount}</p>
          </article>
          <article className="np-kpi-card">
            <p className="np-kpi-label">已完成</p>
            <p className="np-kpi-value">{completedCount}</p>
          </article>
        </div>

        {/* 搜索栏和状态筛选 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <Input.Search
            placeholder="搜索项目名称"
            allowClear
            value={keyword}
            onChange={(e) => handleSearch(e.target.value)}
            onSearch={(v) => handleSearch(v)}
            style={{ width: 260 }}
          />
          <Space size={4} wrap>
            {ALL_STATUSES.map((s) => (
              <Tag.CheckableTag
                key={s}
                checked={selectedStatuses.includes(s)}
                onChange={() => handleStatusToggle(s)}
              >
                {STATUS_MAP[s].label}
              </Tag.CheckableTag>
            ))}
          </Space>
        </div>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={projects}
          loading={loading}
          bordered
          scroll={{ x: 900 }}
          onChange={handleTableChange}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: (p) => {
              doFetch({ page: p })
            },
            showTotal: (t) => `共 ${t} 个项目`,
          }}
        />
      </div>

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
    </section>
  )
}
