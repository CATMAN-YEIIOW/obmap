import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout, Result, Button } from 'antd'
import { useEffect } from 'react'
import AppHeader from './components/AppHeader'
import Dashboard from './pages/Dashboard'
import Devices from './pages/Devices'
import Statistics from './pages/Statistics'
import Alerts from './pages/Alerts'
import AlertConfig from './pages/AlertConfig'
import AlertRules from './pages/AlertRules'
import UserManagement from './pages/UserManagement'
import Login from './pages/Login'
import Register from './pages/Register'
import { useAuthStore } from './stores/authStore'
import { mqttService } from './services/mqtt'

const { Content } = Layout

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (!isAuthenticated) {
    return (
      <Result
        status="403"
        title="请先登录"
        subTitle="您需要登录才能访问此页面"
        extra={
          <Button type="primary" href="/login">
            去登录
          </Button>
        }
      />
    )
  }

  return <>{children}</>
}

function MainLayout() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <AppHeader />
      <Content style={{ padding: '24px', background: '#f0f2f5' }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/statistics" element={<Statistics />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/alert-config" element={<AlertConfig />} />
          <Route path="/alert-rules" element={<AlertRules />} />
          <Route path="/users" element={<UserManagement />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Content>
    </Layout>
  )
}

function App() {
  const { checkAuth, isAuthenticated } = useAuthStore()

  useEffect(() => {
    checkAuth()
  }, [])

  // Connect MQTT when authenticated, disconnect on logout
  useEffect(() => {
    if (isAuthenticated) {
      mqttService.connect().catch(err => {
        console.error('MQTT initial connection failed:', err)
      })
    } else {
      mqttService.disconnect()
    }
  }, [isAuthenticated])

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

export default App
