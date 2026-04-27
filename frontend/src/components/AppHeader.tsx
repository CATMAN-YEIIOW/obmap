import { Layout, Menu, Dropdown, Avatar, Space, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import {
  DashboardOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  AlertOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined
} from '@ant-design/icons'
import { useAuthStore } from '../stores/authStore'
import { alertApi } from '../services/api'

const { Header } = Layout
const { Text } = Typography

const AppHeader = () => {
  const navigate = useNavigate()
  const { user, isAuthenticated, logout } = useAuthStore()
  const [activeAlertCount, setActiveAlertCount] = useState(0)

  // 定期轮询获取未处理告警数量
  useEffect(() => {
    if (!isAuthenticated) return

    const fetchAlertCount = async () => {
      try {
        const res = await alertApi.list({ page_size: 100 })
        const items = res.data.data.items || []
        const activeCount = items.filter((a: any) => a.status !== 'resolved').length
        setActiveAlertCount(activeCount)
      } catch (error) {
        console.error('Failed to fetch alert count:', error)
      }
    }

    fetchAlertCount()
    const timer = setInterval(fetchAlertCount, 2000)
    return () => clearInterval(timer)
  }, [isAuthenticated])

  const canManageAlert = user?.role === 'admin' || user?.role === 'researcher'

  const getAlertLabel = () => {
    if (activeAlertCount > 0) {
      return <span>告警中心 <span style={{ background: '#ff4d4f', color: '#fff', borderRadius: '50%', padding: '0 6px', fontSize: '12px', marginLeft: 4 }}>{activeAlertCount}</span></span>
    }
    return '告警中心'
  }

  const items = [
    { key: '/', icon: <DashboardOutlined />, label: '实时监测' },
    { key: '/devices', icon: <DatabaseOutlined />, label: '设备管理' },
    { key: '/statistics', icon: <BarChartOutlined />, label: '统计报表' },
    { key: '/alerts', icon: <AlertOutlined />, label: getAlertLabel() }
  ]

  if (canManageAlert) {
    items.push({ key: '/alert-config', icon: <SettingOutlined />, label: '阈值配置' })
    items.push({ key: '/alert-rules', icon: <SettingOutlined />, label: '组合规则' })
  }

  if (user?.role === 'admin') {
    items.push({ key: '/users', icon: <UserOutlined />, label: '用户管理' })
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const userMenuItems: any[] = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: user?.full_name || user?.username,
      disabled: true
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout
    }
  ]

  const roleLabels: Record<string, string> = {
    admin: '管理员',
    researcher: '研究员',
    viewer: '访客'
  }

  return (
    <Header style={{ display: 'flex', alignItems: 'center', background: '#001529', padding: '0 24px' }}>
      <div style={{ color: '#fff', fontSize: '20px', fontWeight: 'bold', marginRight: '48px' }}>
        海洋浮标监测数据管理与分析平台
      </div>
      <Menu
        theme="dark"
        mode="horizontal"
        selectedKeys={[location.pathname]}
        items={items}
        onClick={({ key }) => navigate(key)}
        style={{ flex: 1 }}
      />

      {isAuthenticated && user && (
        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
          <div style={{ cursor: 'pointer', marginLeft: '16px', display: 'flex', alignItems: 'center', height: '32px' }}>
            <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#1890ff', marginRight: 8 }} />
            <div style={{ color: '#fff', overflow: 'hidden' }}>
              <div style={{ color: '#fff', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: '20px' }}>
                {user.full_name || user.username}
              </div>
              <div style={{ color: 'rgba(255,255,255,0.65)', fontSize: '12px', lineHeight: '16px' }}>
                {roleLabels[user.role] || user.role}
              </div>
            </div>
          </div>
        </Dropdown>
      )}

      {!isAuthenticated && (
        <Space style={{ marginLeft: '16px' }}>
          <Text
            style={{ color: '#fff', cursor: 'pointer' }}
            onClick={() => navigate('/login')}
          >
            登录
          </Text>
          <Text style={{ color: 'rgba(255,255,255,0.65)' }}>|</Text>
          <Text
            style={{ color: '#fff', cursor: 'pointer' }}
            onClick={() => navigate('/register')}
          >
            注册
          </Text>
        </Space>
      )}
    </Header>
  )
}

export default AppHeader
