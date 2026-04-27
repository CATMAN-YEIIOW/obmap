import { useState, useEffect } from 'react'
import { Table, Button, Modal, Form, Select, InputNumber, message, Tag, Space, Card, Row, Col, Switch, Popconfirm } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, GlobalOutlined, TeamOutlined } from '@ant-design/icons'
import { alertApi, buoyApi } from '../services/api'
import { useAuthStore } from '../stores/authStore'

const { Option } = Select

interface AlertConfig {
  id: string
  buoy_id: string | null
  buoy_name: string | null
  param_name: string
  min_threshold: number | null
  max_threshold: number | null
  severity: string
  enabled: boolean
  is_global: boolean
}

const paramLabels: Record<string, string> = {
  temperature: '水温',
  salinity: '盐度',
  ph: 'pH值',
  dissolved_oxygen: '溶解氧',
  turbidity: '浊度',
  chlorophyll: '叶绿素',
  wave_height: '波高'
}

const paramUnits: Record<string, string> = {
  temperature: '°C',
  salinity: 'PSU',
  ph: '',
  dissolved_oxygen: 'mg/L',
  turbidity: 'NTU',
  chlorophyll: 'μg/L',
  wave_height: 'm'
}

const severityColors: Record<string, string> = {
  info: 'blue',
  warning: 'orange',
  critical: 'red'
}

const AlertConfigPage = () => {
  const [data, setData] = useState<AlertConfig[]>([])
  const [buoys, setBuoys] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingConfig, setEditingConfig] = useState<AlertConfig | null>(null)
  const [form] = Form.useForm()
  const [filterBuoy, setFilterBuoy] = useState<string | undefined>()
  const { user } = useAuthStore()

  const canManage = user?.role === 'admin' || user?.role === 'researcher'
  const canDelete = user?.role === 'admin'

  useEffect(() => {
    fetchConfig()
    fetchBuoys()
  }, [filterBuoy])

  const fetchConfig = async () => {
    setLoading(true)
    try {
      const res = await alertApi.getConfig(filterBuoy)
      setData(res.data.data?.items || [])
    } catch (error) {
      message.error('获取配置失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchBuoys = async () => {
    try {
      const res = await buoyApi.list({ page_size: 100 })
      setBuoys(res.data?.items || [])
    } catch (error) {
      console.error('Failed to fetch buoys:', error)
    }
  }

  const handleAdd = () => {
    setEditingConfig(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (record: AlertConfig) => {
    setEditingConfig(record)
    form.setFieldsValue({
      buoy_id: record.buoy_id,
      param_name: record.param_name,
      min_threshold: record.min_threshold,
      max_threshold: record.max_threshold,
      severity: record.severity,
      enabled: record.enabled
    })
    setModalVisible(true)
  }

  const handleDelete = async (id: string) => {
    try {
      await alertApi.deleteConfig(id)
      message.success('删除成功')
      fetchConfig()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingConfig) {
        await alertApi.updateConfig(editingConfig.id, values)
        message.success('更新成功')
      } else {
        await alertApi.createConfig(values)
        message.success('创建成功')
      }
      setModalVisible(false)
      fetchConfig()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '操作失败')
    }
  }

  const columns = [
    {
      title: '类型',
      dataIndex: 'is_global',
      key: 'is_global',
      render: (is_global: boolean) => (
        is_global
          ? <Tag icon={<GlobalOutlined />} color="default">全局</Tag>
          : <Tag icon={<TeamOutlined />} color="blue">浮标专属</Tag>
      ),
      width: 100
    },
    {
      title: '浮标',
      dataIndex: 'buoy_name',
      key: 'buoy_name',
      render: (name: string | null, record: AlertConfig) =>
        record.is_global ? '-' : (name || record.buoy_id?.slice(0, 8) + '...'),
      width: 120
    },
    {
      title: '参数',
      dataIndex: 'param_name',
      key: 'param_name',
      render: (v: string) => paramLabels[v] || v,
      width: 100
    },
    {
      title: '下限阈值',
      dataIndex: 'min_threshold',
      key: 'min_threshold',
      render: (v: number | null, record: AlertConfig) =>
        v !== null ? `≥ ${v} ${paramUnits[record.param_name] || ''}` : '-',
      width: 120
    },
    {
      title: '上限阈值',
      dataIndex: 'max_threshold',
      key: 'max_threshold',
      render: (v: number | null, record: AlertConfig) =>
        v !== null ? `≤ ${v} ${paramUnits[record.param_name] || ''}` : '-',
      width: 120
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      render: (v: string) => (
        <Tag color={severityColors[v]}>{v === 'info' ? '信息' : v === 'warning' ? '警告' : '严重'}</Tag>
      ),
      width: 100
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'green' : 'default'}>{enabled ? '启用' : '禁用'}</Tag>
      ),
      width: 80
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: AlertConfig) => (
        <Space>
          {canManage && (
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
              编辑
            </Button>
          )}
          {canDelete && (
            <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
      width: 180
    }
  ]

  return (
    <div>
      <Card
        title="告警阈值配置"
        extra={
          canManage && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              添加配置
            </Button>
          )
        }
      >
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Select
              allowClear
              placeholder="筛选浮标"
              style={{ width: '100%' }}
              onChange={(v) => setFilterBuoy(v)}
            >
              {buoys.map(b => (
                <Option key={b.id} value={b.id}>{b.name}</Option>
              ))}
            </Select>
          </Col>
        </Row>

        <Table
          dataSource={data}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>

      <Modal
        title={editingConfig ? '编辑告警配置' : '添加告警配置'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        okText="确定"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="buoy_id"
            label="浮标"
            tooltip="不选择浮标则创建全局配置"
          >
            <Select
              placeholder="选择浮标（不选则为全局配置）"
              allowClear
              disabled={!!editingConfig}
            >
              {buoys.map(b => (
                <Option key={b.id} value={b.id}>{b.name} ({b.code})</Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="param_name"
            label="监测参数"
            rules={editingConfig ? [] : [{ required: true, message: '请选择参数' }]}
          >
            <Select placeholder="选择参数" disabled={!!editingConfig}>
              {Object.entries(paramLabels).map(([k, v]) => (
                <Option key={k} value={k}>{v}</Option>
              ))}
            </Select>
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="min_threshold" label="下限阈值">
                <InputNumber style={{ width: '100%' }} placeholder="最小值" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="max_threshold" label="上限阈值">
                <InputNumber style={{ width: '100%' }} placeholder="最大值" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="severity" label="严重程度" initialValue="warning">
            <Select>
              <Option value="info">信息</Option>
              <Option value="warning">警告</Option>
              <Option value="critical">严重</Option>
            </Select>
          </Form.Item>

          <Form.Item name="enabled" label="启用状态" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default AlertConfigPage