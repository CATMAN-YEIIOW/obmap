import { useState, useEffect } from 'react'
import { Table, Button, Select, message, Tag, Space, Card, Popconfirm } from 'antd'
import { DeleteOutlined, UserOutlined } from '@ant-design/icons'
import { userApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'

const { Option } = Select

interface User {
  id: string
  username: string
  email: string
  full_name?: string
  role: 'admin' | 'researcher' | 'viewer'
  is_active: boolean
}

const roleLabels: Record<string, string> = {
  admin: '管理员',
  researcher: '研究员',
  viewer: '访客'
}

const roleColors: Record<string, string> = {
  admin: 'red',
  researcher: 'blue',
  viewer: 'default'
}

const UserManagementPage = () => {
  const [data, setData] = useState<User[]>([])
  const [loading, setLoading] = useState(false)
  const { user: currentUser } = useAuthStore()

  useEffect(() => {
    fetchUsers()
  }, [])

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const res = await userApi.list()
      setData(res.data || [])
    } catch (error) {
      message.error('获取用户列表失败')
    } finally {
      setLoading(false)
    }
  }

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      await userApi.updateRole(userId, newRole)
      message.success('角色更新成功')
      fetchUsers()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新失败')
    }
  }

  const handleDelete = async (userId: string) => {
    try {
      await userApi.delete(userId)
      message.success('删除成功')
      fetchUsers()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败')
    }
  }

  const columns = [
    {
      title: '用户',
      key: 'user',
      render: (_: any, record: User) => (
        <Space>
          <UserOutlined />
          <div>
            <div>{record.full_name || record.username}</div>
            <div style={{ fontSize: 12, color: '#999' }}>@{record.username}</div>
          </div>
        </Space>
      ),
      width: 180
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      width: 200
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string, record: User) => (
        <Select
          value={role}
          onChange={(v) => handleRoleChange(record.id, v)}
          style={{ width: 120 }}
          disabled={record.id === currentUser?.id}
        >
          <Option value="viewer">
            <Tag color={roleColors.viewer}>{roleLabels.viewer}</Tag>
          </Option>
          <Option value="researcher">
            <Tag color={roleColors.researcher}>{roleLabels.researcher}</Tag>
          </Option>
          <Option value="admin">
            <Tag color={roleColors.admin}>{roleLabels.admin}</Tag>
          </Option>
        </Select>
      ),
      width: 150
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (is_active: boolean) => (
        <Tag color={is_active ? 'green' : 'red'}>
          {is_active ? '正常' : '已禁用'}
        </Tag>
      ),
      width: 100
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: User) => (
        <Space>
          {record.id !== currentUser?.id && (
            <Popconfirm
              title="确认删除此用户？"
              description="删除后无法恢复"
              onConfirm={() => handleDelete(record.id)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
      width: 100
    }
  ]

  return (
    <div>
      <Card title="用户管理">
        <Table
          dataSource={data}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>
    </div>
  )
}

export default UserManagementPage