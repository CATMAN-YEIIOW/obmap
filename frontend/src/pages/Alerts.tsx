import { useState, useEffect, useCallback } from 'react'
import { Table, Tag, Button, Card, Row, Col, Statistic, Modal, Input, message, Tabs, Badge, notification } from 'antd'
import { CheckOutlined, CheckCircleOutlined, NotificationOutlined, ReloadOutlined } from '@ant-design/icons'
import { alertApi } from '../services/api'
import { mqttService, AlertWebSocketMessage } from '../services/mqtt'
import { useAppStore } from '../stores/appStore'
import dayjs from 'dayjs'

const { TextArea } = Input

interface Alert {
  id: string
  buoy_id: string
  buoy_name: string
  alert_type: string
  param_name: string
  threshold_value: number
  actual_value: number
  severity: string
  status: string
  triggered_at: string
  acknowledged_at?: string
  acknowledged_by?: string
  resolved_at?: string
  resolved_by?: string
  remarks?: string
}

interface RecoveredAlert {
  id: string
  buoy_id: string
  buoy_name?: string
  alert_type?: string
  param_name: string
  actual_value: number
  threshold_value?: number
  triggered_at: string
  resolved_at: string
  remarks?: string
}

const Alerts = () => {
  const [data, setData] = useState<Alert[]>([])
  const [recoveredData, setRecoveredData] = useState<RecoveredAlert[]>([])
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [mqttConnected, setMqttConnected] = useState(false)
  const [activeTab, setActiveTab] = useState('active')
  const [activeAlerts, setActiveAlerts] = useState<Alert[]>([])
  const [newAlertCount, setNewAlertCount] = useState(0)
  const { setActiveAlertCount } = useAppStore()

  // Modal state for remarks
  const [ackModalVisible, setAckModalVisible] = useState(false)
  const [resolveModalVisible, setResolveModalVisible] = useState(false)
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null)
  const [remarks, setRemarks] = useState('')

  // 同步活跃告警数量到全局状态
  useEffect(() => {
    setActiveAlertCount(activeAlerts.length)
  }, [activeAlerts, setActiveAlertCount])

  useEffect(() => {
    fetchData()
    fetchStats()
    fetchRecoveredAlerts()

    let mqttUnsubscribe: () => void
    initMQTT().then(unsubscribe => {
      mqttUnsubscribe = unsubscribe
    })

    // 每30秒自动刷新数据，确保告警列表始终最新
    const refreshTimer = setInterval(() => {
      fetchData()
      fetchStats()
      fetchRecoveredAlerts()
    }, 2000)

    return () => {
      clearInterval(refreshTimer)
      if (mqttUnsubscribe) mqttUnsubscribe()
    }
  }, [])

  const initMQTT = async () => {
    try {
      const unsubscribe = mqttService.subscribe((topic, msg) => {
        if (topic === 'buoy/alert' || topic.startsWith('buoy/alert')) {
          handleAlertMessage(msg as AlertWebSocketMessage)
        }
      })
      setMqttConnected(true)
      return unsubscribe
    } catch (error) {
      console.error('MQTT subscription failed:', error)
      return () => {}
    }
  }

  const handleAlertMessage = useCallback((msg: AlertWebSocketMessage) => {
    if (msg.type === 'alert_triggered') {
      const alert = msg.alert
      const newAlert: Alert = {
        id: alert.id,
        buoy_id: alert.buoy_id,
        buoy_name: alert.buoy_name,
        alert_type: 'threshold_exceeded',
        param_name: alert.param_name,
        threshold_value: alert.threshold_value || 0,
        actual_value: alert.actual_value,
        severity: alert.severity,
        status: 'triggered',
        triggered_at: alert.triggered_at || new Date().toISOString()
      }

      // Play notification sound and show browser notification
      notification.warning({
        message: `🚨 新告警 - ${alert.buoy_name}`,
        description: `${alert.param_name}: ${alert.actual_value} (阈值: ${alert.threshold_value})`,
        duration: 5,
        icon: <NotificationOutlined style={{ color: '#fa8c16' }} />
      })

      // Update active alerts
      setActiveAlerts(prev => {
        const exists = prev.find(a => a.id === alert.id)
        if (exists) return prev
        return [newAlert, ...prev]
      })

      setNewAlertCount(prev => prev + 1)
      setData(prev => [newAlert, ...prev.filter(a => a.id !== alert.id)])
    } else if (msg.type === 'alert_recovered') {
      const alert = msg.alert
      notification.success({
        message: `✅ 告警恢复 - ${alert.buoy_name}`,
        description: `${alert.param_name} 已恢复正常: ${alert.current_value}`,
        duration: 3
      })

      // Remove from active alerts
      setActiveAlerts(prev => prev.filter(a => a.id !== alert.id))

      // Update data
      setData(prev => prev.map(a => {
        if (a.id === alert.id) {
          return { ...a, status: 'resolved', resolved_at: alert.resolved_at }
        }
        return a
      }))

      // Add to recovered data
      const recoveredAlert: RecoveredAlert = {
        id: alert.id,
        buoy_id: alert.buoy_id,
        param_name: alert.param_name,
        actual_value: alert.actual_value,
        threshold_value: alert.threshold_value,
        triggered_at: alert.triggered_at || new Date().toISOString(),
        resolved_at: alert.resolved_at || new Date().toISOString()
      }
      setRecoveredData(prev => [recoveredAlert, ...prev.filter(a => a.id !== alert.id)])
    }
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await alertApi.list({ page_size: 100 })
      const items = res.data.data.items
      setData(items)
      // Active alerts = triggered + acknowledged
      setActiveAlerts(items.filter((a: Alert) => a.status !== 'resolved'))
    } catch (error) {
      console.error('Failed to fetch alerts:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchStats = async () => {
    try {
      const res = await alertApi.statistics()
      setStats(res.data.data)
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    }
  }

  const fetchRecoveredAlerts = async () => {
    try {
      const res = await alertApi.getRecovered(7)
      setRecoveredData(res.data.data?.items || [])
    } catch (error) {
      console.error('Failed to fetch recovered alerts:', error)
    }
  }

  const handleAcknowledge = (record: Alert) => {
    setSelectedAlert(record)
    setRemarks('')
    setAckModalVisible(true)
  }

  const handleResolve = (record: Alert) => {
    setSelectedAlert(record)
    setRemarks('')
    setResolveModalVisible(true)
  }

  const confirmAcknowledge = async () => {
    if (!selectedAlert) return
    try {
      await alertApi.acknowledge(selectedAlert.id, remarks)
      message.success('告警已确认')
      setAckModalVisible(false)
      fetchData()
      fetchStats()
    } catch (error) {
      message.error('确认失败')
    }
  }

  const confirmResolve = async () => {
    if (!selectedAlert) return
    try {
      await alertApi.resolve(selectedAlert.id, remarks)
      message.success('告警已解决')
      setResolveModalVisible(false)
      fetchData()
      fetchStats()
      fetchRecoveredAlerts()
    } catch (error) {
      message.error('解决失败')
    }
  }

  const clearNewAlertCount = () => {
    setNewAlertCount(0)
  }

  const severityColors: Record<string, string> = {
    info: 'blue',
    warning: 'orange',
    critical: 'red'
  }

  const severityLabels: Record<string, string> = {
    info: '信息',
    warning: '警告',
    critical: '严重'
  }

  const statusColors: Record<string, string> = {
    triggered: 'red',
    acknowledged: 'orange',
    resolved: 'green'
  }

  const statusLabels: Record<string, string> = {
    triggered: '触发',
    acknowledged: '已确认',
    resolved: '已解决'
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

  const columns = [
    { title: '浮标', dataIndex: 'buoy_name', key: 'buoy_name', width: 120 },
    {
      title: '参数',
      dataIndex: 'param_name',
      key: 'param_name',
      render: (v: string, record: Alert) => {
        const isCombined = record.alert_type === 'combined_rule'
        return isCombined ? <Tag color="purple">{v}</Tag> : (paramLabels[v] || v)
      },
      width: 100
    },
    {
      title: '告警值',
      key: 'value',
      render: (_: any, record: Alert) => {
        const direction = record.actual_value > record.threshold_value ? '↑' : '↓'
        return (
          <span>
            {direction} {record.actual_value}
            <span style={{ color: '#999', fontSize: 12 }}> (阈值: {record.threshold_value})</span>
          </span>
        )
      },
      width: 160
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      render: (v: string) => (
        <Tag color={severityColors[v]}>{severityLabels[v] || v}</Tag>
      ),
      width: 100
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => (
        <Tag color={statusColors[v]}>{statusLabels[v] || v}</Tag>
      ),
      width: 100
    },
    {
      title: '触发时间',
      dataIndex: 'triggered_at',
      key: 'triggered_at',
      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss'),
      width: 160
    },
    {
      title: '备注',
      dataIndex: 'remarks',
      key: 'remarks',
      render: (r: string) => r ? <span style={{ color: '#666', fontSize: 12 }}>{r}</span> : '-',
      ellipsis: true
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Alert) => (
        <>
          {record.status === 'triggered' && (
            <Button type="link" size="small" icon={<CheckOutlined />} onClick={() => handleAcknowledge(record)}>
              确认
            </Button>
          )}
          {record.status !== 'resolved' && (
            <Button type="link" size="small" icon={<CheckCircleOutlined />} onClick={() => handleResolve(record)} style={{ color: '#52c41a' }}>
              解决
            </Button>
          )}
        </>
      ),
      width: 160
    }
  ]

  const recoveredColumns = [
    { title: '浮标', dataIndex: 'buoy_name', key: 'buoy_name', width: 120 },
    { title: '参数', dataIndex: 'param_name', key: 'param_name', render: (v: string) => paramLabels[v] || v },
    { title: '告警值', dataIndex: 'actual_value', key: 'actual_value' },
    { title: '阈值', dataIndex: 'threshold_value', key: 'threshold_value', render: (v: number) => v?.toFixed(2) || '-' },
    { title: '触发时间', dataIndex: 'triggered_at', key: 'triggered_at', render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm') },
    { title: '恢复时间', dataIndex: 'resolved_at', key: 'resolved_at', render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm') },
    {
      title: '持续时间',
      key: 'duration',
      render: (_: any, record: RecoveredAlert) => {
        const start = dayjs(record.triggered_at)
        const end = dayjs(record.resolved_at)
        const mins = end.diff(start, 'minute')
        if (mins < 60) return `${mins}分钟`
        const hours = Math.floor(mins / 60)
        return `${hours}小时${mins % 60}分钟`
      }
    }
  ]

  // For recovered tab, we need to track alert_type separately since RecoveredAlert interface doesn't have it
  const recoveredColumnsWithType = [
    ...recoveredColumns.slice(0, 1),
    {
      title: '类型',
      key: 'alert_type',
      render: (_: any, record: RecoveredAlert & { alert_type?: string }) => {
        const isCombined = record.alert_type === 'combined_rule'
        return isCombined ? <Tag color="purple">组合规则</Tag> : <Tag color="blue">阈值告警</Tag>
      }
    },
    ...recoveredColumns.slice(1)
  ]

  const tabItems = [
    {
      key: 'active',
      label: <span>告警列表 {activeAlerts.length > 0 && <Badge count={activeAlerts.length} size="small" />}</span>,
      children: (
        <Table
          dataSource={data.filter(a => a.status !== 'resolved')}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      )
    },
    {
      key: 'all',
      label: '全部记录',
      children: (
        <Table
          dataSource={data}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      )
    },
    {
      key: 'recovered',
      label: <span>已恢复 {recoveredData.length > 0 && <Badge count={recoveredData.length} size="small" />}</span>,
      children: (
        <Table
          dataSource={recoveredData}
          columns={recoveredColumnsWithType}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      )
    }
  ]

  return (
    <div>
      {/* MQTT 连接状态 */}
      {!mqttConnected && (
        <div style={{ background: '#fff3cd', padding: '8px 16px', marginBottom: 16, borderRadius: 4 }}>
          MQTT 连接中... 告警将实时推送
        </div>
      )}

      {/* 告警统计卡片 */}
      {stats && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={6}>
            <Card size="small">
              <Statistic title="总告警数" value={stats.total} suffix={newAlertCount > 0 && <span style={{ color: 'red', fontSize: 14 }}>(+{newAlertCount})</span>} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="触发中" value={stats.by_status?.triggered || 0} valueStyle={{ color: '#cf1322' }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="已确认" value={stats.by_status?.acknowledged || 0} valueStyle={{ color: '#fa8c16' }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="近24小时触发"
                value={stats.recent_24h || 0}
                suffix={<Button size="small" icon={<ReloadOutlined />} onClick={() => { fetchData(); fetchStats(); clearNewAlertCount(); }} style={{ marginLeft: 8 }} />}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* 告警级别分布 */}
      {stats && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Card size="small">
              <Statistic title="信息级" value={stats.by_severity?.info || 0} valueStyle={{ color: '#1890ff' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="警告级" value={stats.by_severity?.warning || 0} valueStyle={{ color: '#fa8c16' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="严重级" value={stats.by_severity?.critical || 0} valueStyle={{ color: '#f5222d' }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="近24h已恢复" value={stats.recovered_24h || 0} valueStyle={{ color: '#52c41a' }} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="当前活跃告警" value={activeAlerts.length} valueStyle={{ color: activeAlerts.length > 0 ? '#f5222d' : '#52c41a' }} />
            </Card>
          </Col>
        </Row>
      )}

      {/* 告警列表 tabs */}
      <Card>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
      </Card>

      {/* 确认告警 Modal */}
      <Modal
        title="确认告警"
        open={ackModalVisible}
        onOk={confirmAcknowledge}
        onCancel={() => setAckModalVisible(false)}
        okText="确认"
        cancelText="取消"
      >
        {selectedAlert && (
          <div>
            <p>确认来自 <b>{selectedAlert.buoy_name}</b> 的告警：</p>
            <p>{paramLabels[selectedAlert.param_name] || selectedAlert.param_name} = {selectedAlert.actual_value} (阈值: {selectedAlert.threshold_value})</p>
            <div style={{ marginTop: 16 }}>
              <label>处理备注（可选）：</label>
              <TextArea
                rows={3}
                value={remarks}
                onChange={e => setRemarks(e.target.value)}
                placeholder="记录告警确认时的处理说明..."
              />
            </div>
          </div>
        )}
      </Modal>

      {/* 解决告警 Modal */}
      <Modal
        title="解决告警"
        open={resolveModalVisible}
        onOk={confirmResolve}
        onCancel={() => setResolveModalVisible(false)}
        okText="解决"
        cancelText="取消"
      >
        {selectedAlert && (
          <div>
            <p>解决来自 <b>{selectedAlert.buoy_name}</b> 的告警：</p>
            <p>{paramLabels[selectedAlert.param_name] || selectedAlert.param_name} = {selectedAlert.actual_value} (阈值: {selectedAlert.threshold_value})</p>
            <div style={{ marginTop: 16 }}>
              <label>解决备注（可选）：</label>
              <TextArea
                rows={3}
                value={remarks}
                onChange={e => setRemarks(e.target.value)}
                placeholder="记录告警解决原因和处理过程..."
              />
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

export default Alerts
