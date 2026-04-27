import { useState } from 'react'
import { Form, Input, Button, Card, message, Typography } from 'antd'
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

const { Title, Text } = Typography

export default function Register() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { register } = useAuthStore()

  const onFinish = async (values: {
    username: string
    email: string
    password: string
    full_name?: string
  }) => {
    setLoading(true)
    try {
      await register(values)
      message.success('注册成功')
      navigate('/')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '注册失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    }}>
      <Card style={{ width: 400, boxShadow: '0 14px 26px rgba(0,0,0,0.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2}>海洋浮标监测数据管理与分析平台</Title>
          <Text type="secondary">创建新账户</Text>
        </div>

        <Form
          name="register"
          onFinish={onFinish}
          autoComplete="off"
          size="large"
        >
          <Form.Item
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, message: '用户名至少3个字符' }
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
            />
          </Form.Item>

          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' }
            ]}
          >
            <Input
              prefix={<MailOutlined />}
              placeholder="邮箱"
            />
          </Form.Item>

          <Form.Item
            name="full_name"
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="姓名（可选）"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少6个字符' }
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
            />
          </Form.Item>

          <Form.Item
            name="confirmPassword"
            dependencies={['password']}
            rules={[
              { required: true, message: '请确认密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'))
                }
              })
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="确认密码"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
            >
              注册
            </Button>
          </Form.Item>

          <div style={{ textAlign: 'center' }}>
            <Text>已有账户？</Text>
            <Link to="/login" style={{ marginLeft: 8 }}>
              登录
            </Link>
          </div>
        </Form>
      </Card>
    </div>
  )
}
