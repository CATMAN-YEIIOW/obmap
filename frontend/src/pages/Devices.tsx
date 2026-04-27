import { useState, useEffect } from 'react'
import { Table, Button, Modal, Form, Input, InputNumber, Switch, message, Popconfirm, Space, Tag, Tooltip, Divider } from 'antd'
import { PlusOutlined, DeleteOutlined, EditOutlined, PoweroffOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { buoyApi, simulatorApi } from '../services/api'
import { Buoy } from '../stores/appStore'
import { mqttService } from '../services/mqtt'

const Devices = () => {
  const [data, setData] = useState<Buoy[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [createResult, setCreateResult] = useState<any>(null)
  const [editingBuoy, setEditingBuoy] = useState<Buoy | null>(null)
  const [form] = Form.useForm()
  const [mqttConnected, setMqttConnected] = useState(false)

  useEffect(() => {
    fetchData()
    initMQTT()

    // 每10秒自动刷新数据
    const refreshTimer = setInterval(() => {
      fetchData()
    }, 10000)

    return () => clearInterval(refreshTimer)
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await buoyApi.list({ page_size: 100 })
      setData(res.data.items)
    } catch (error) {
      message.error('获取数据失败')
    } finally {
      setLoading(false)
    }
  }

  const initMQTT = async () => {
    try {
      mqttService.subscribe((topic, _msg) => {
        if (topic.startsWith('buoy/status/')) {
          fetchData()
        }
      })
      setMqttConnected(true)
    } catch (error) {
      console.error('MQTT subscription failed:', error)
    }
  }

  const handleAdd = () => {
    setEditingBuoy(null)
    setCreateResult(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (record: Buoy) => {
    setEditingBuoy(record)
    setCreateResult(null)
    form.setFieldsValue(record)
    setModalVisible(true)
  }

  const handleDelete = async (id: string) => {
    try {
      await buoyApi.delete(id)
      message.success('删除成功')
      fetchData()
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingBuoy) {
        await buoyApi.update(editingBuoy.id, values)
        message.success('更新成功')
        setModalVisible(false)
      } else {
        const res = await buoyApi.create(values)
        message.success('创建成功，请在MQTT客户端发送激活指令')
        setCreateResult(res.data.data)
      }
      fetchData()
    } catch (error: any) {
      console.error('Submit error:', error)
      if (error.response?.data?.detail) {
        message.error(error.response.data.detail)
      } else {
        message.error('操作失败')
      }
    }
  }

  const handleOnlineOffline = async (buoy: Buoy) => {
    try {
      if (buoy.status === 'online') {
        await simulatorApi.setBuoyOffline(buoy.id, 3600)
        message.success(`已发送下线指令`)
      } else {
        await simulatorApi.setBuoyOnline(buoy.id)
        message.success(`已发送上线指令`)
      }
    } catch (error) {
      message.error('操作失败')
    }
  }

  const getStatusTag = (status: string) => {
    const config: Record<string, { color: string; label: string }> = {
      online: { color: 'green', label: '在线' },
      offline: { color: 'red', label: '离线' },
      inactive: { color: 'default', label: '未激活' },
      disconnected: { color: 'purple', label: '失联' },
      low_battery: { color: 'orange', label: '低电量' },
      no_power: { color: 'red', label: '无电' },
      drift_alert: { color: 'cyan', label: '漂移告警' },
    }
    const c = config[status] || { color: 'default', label: status }
    return <Tag color={c.color}>{c.label}</Tag>
  }

  const getBatteryTag = (level: number | undefined) => {
    if (level === undefined || level === null) return <Tag>--</Tag>
    let color = 'green'
    if (level <= 10) color = 'red'
    else if (level <= 20) color = 'orange'
    else if (level <= 50) color = 'yellow'
    return (
      <Tag color={color} icon={<ThunderboltOutlined />}>
        {level}%
      </Tag>
    )
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '编码', dataIndex: 'code', key: 'code' },
    { title: '海域', dataIndex: 'sea_area', key: 'sea_area' },
    { title: '电量', dataIndex: 'battery_level', key: 'battery_level', render: (v: number) => getBatteryTag(v) },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => getStatusTag(status)
    },
    {
      title: 'Buoy ID',
      dataIndex: 'id',
      key: 'id',
      render: (id: string) => id ? (
        <Tooltip title="点击复制，用于MQTT命令">
          <Input
            size="small"
            style={{ width: 200, fontSize: 10 }}
            value={id}
            readOnly
            onClick={() => {
              navigator.clipboard.writeText(id)
              message.success('已复制')
            }}
          />
        </Tooltip>
      ) : <Tag>--</Tag>
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Buoy) => (
        <Space size="small">
          {record.status !== 'inactive' && record.status !== 'disconnected' && record.status !== 'no_power' && record.status !== 'drift_alert' && (
            <Button size="small" icon={<PoweroffOutlined />} onClick={() => handleOnlineOffline(record)}>
              {record.status === 'online' ? '下线' : '上线'}
            </Button>
          )}
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          添加浮标
        </Button>
        <Space>
          <Tag color={mqttConnected ? 'green' : 'red'}>
            MQTT {mqttConnected ? '已连接' : '未连接'}
          </Tag>
        </Space>
      </div>

      <Table
        dataSource={data}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editingBuoy ? '编辑浮标' : '添加浮标'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={editingBuoy ? 500 : 700}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="code" label="编码" rules={[{ required: true }]}>
            <Input disabled={!!editingBuoy} />
          </Form.Item>
          <Form.Item name="sea_area" label="海域">
            <Input />
          </Form.Item>
          <Form.Item name="latitude" label="纬度" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="longitude" label="经度" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="depth" label="深度">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          {editingBuoy && (
            <>
              <Divider>漂移检测设置</Divider>
              <Form.Item name="drift_radius" label="允许偏移半径（度）" initialValue={editingBuoy.drift_radius || 0.01}>
                <InputNumber style={{ width: '100%' }} min={0} max={1} step={0.001} />
              </Form.Item>
              <Form.Item name="drift_alert_enabled" label="开启漂移检测" valuePropName="checked" initialValue={editingBuoy.drift_alert_enabled || false}>
                <Switch />
              </Form.Item>
            </>
          )}
        </Form>

        {createResult && (
          <>
            <Divider>激活指令（请使用MQTTX发送）</Divider>
            <p><strong>Topic:</strong> <code>{createResult.activate_topic}</code></p>
            <p><strong>Payload:</strong></p>
            <pre style={{ background: '#f5f5f5', padding: 10, borderRadius: 4 }}>
              {JSON.stringify(createResult.activate_payload, null, 2)}
            </pre>
            <p style={{ fontSize: 12, color: '#888' }}>
              创建浮标后需要通过MQTT客户端发送激活指令才能开始发送数据
            </p>
          </>
        )}
      </Modal>
    </div>
  )
}

export default Devices