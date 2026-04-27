import { useState, useEffect, useCallback, memo } from 'react'
import { Row, Col, Card, Statistic, Tag, Select, Badge, notification, Button } from 'antd'
import { BellOutlined } from '@ant-design/icons'
import { buoyApi } from '../services/api'
import { useAppStore, BuoyData, AlertNotification } from '../stores/appStore'
import BuoyMap, { getBuoyMapInstance } from '../components/BuoyMap'
import BuoyTrajectory from '../components/BuoyTrajectory'
import { mqttService, BuoyDataMessage, AlertWebSocketMessage } from '../services/mqtt'

const PARAM_OPTIONS = [
  { label: '水温', value: 'temperature', unit: '°C' },
  { label: '盐度', value: 'salinity', unit: 'PSU' },
  { label: 'pH', value: 'ph', unit: '' },
  { label: '溶解氧', value: 'dissolved_oxygen', unit: 'mg/L' },
  { label: '浊度', value: 'turbidity', unit: 'NTU' },
  { label: '叶绿素', value: 'chlorophyll', unit: 'μg/L' },
  { label: '波高', value: 'wave_height', unit: 'm' }
]

// Memoized buoy card component - only re-renders when its data actually changes
const BuoyCard = memo(({
  buoy,
  data,
  selectedParam,
  selectedParamConfig,
  onClick
}: {
  buoy: any
  data: BuoyData | undefined
  selectedParam: string
  selectedParamConfig: { label: string; unit: string }
  onClick: () => void
}) => {
  const sensorData = data?.data as Record<string, number | undefined> | undefined
  const hasData = data?.data && Object.keys(data.data).length > 0
  const value = sensorData?.[selectedParam]
  const effectiveStatus = data?.status || buoy.status
  const isSpecialStatus = effectiveStatus === 'drift_alert' || effectiveStatus === 'offline' || effectiveStatus === 'disconnected'
  const statusColor = effectiveStatus === 'online' ? 'green' : effectiveStatus === 'warning' ? 'orange' : effectiveStatus === 'offline' ? 'red' : effectiveStatus === 'disconnected' ? 'purple' : isSpecialStatus ? 'blue' : effectiveStatus === 'low_battery' ? 'orange' : effectiveStatus === 'no_power' ? 'gray' : effectiveStatus === 'inactive' ? 'default' : 'default'
  const statusLabel = effectiveStatus === 'online' ? '在线' : effectiveStatus === 'warning' ? '告警' : effectiveStatus === 'offline' ? '离线' : effectiveStatus === 'disconnected' ? '失联' : isSpecialStatus ? '漂移告警' : effectiveStatus === 'low_battery' ? '低电量' : effectiveStatus === 'no_power' ? '断电' : effectiveStatus === 'inactive' ? '未激活' : '未知'

  return (
    <Card
      size="small"
      hoverable
      style={{ cursor: 'pointer' }}
      onClick={onClick}
    >
      <Statistic
        title={<span>{buoy.name} <Tag color={statusColor}>{statusLabel}</Tag></span>}
        value={isSpecialStatus || !hasData ? '-' : (value ?? '-')}
        suffix={isSpecialStatus || !hasData ? '' : selectedParamConfig.unit}
        valueStyle={{ fontSize: 20 }}
      />
      <div style={{ marginTop: 4, fontSize: 11, color: '#999' }}>
        {effectiveStatus === 'drift_alert' ? '数据异常（漂移中）' : hasData ? `更新: ${new Date().toLocaleTimeString()}` : '暂无数据'}
      </div>
    </Card>
  )
})

const Dashboard = () => {
  const { buoys, realtimeData, setBuoys, setRealtimeData, alertNotifications, unreadAlertCount, addAlertNotification, markAlertsRead } = useAppStore()
  const [mqttConnected, setMqttConnected] = useState(false)
  const [selectedParam, setSelectedParam] = useState('temperature')
  const [trajectoryVisible, setTrajectoryVisible] = useState(false)
  const [selectedBuoy, setSelectedBuoy] = useState<any>(null)

  useEffect(() => {
    fetchBuoys()
    initMQTT()
  }, [])

  useEffect(() => {
    if (!mqttConnected) return
    const timer = setTimeout(() => setMqttConnected(false), 2000)
    return () => clearTimeout(timer)
  }, [mqttConnected])

  // Sync selectedBuoy with buoys when buoys changes
  useEffect(() => {
    if (selectedBuoy) {
      const updatedBuoy = buoys.find((b: any) => b.id === selectedBuoy.id)
      if (updatedBuoy && updatedBuoy.status !== selectedBuoy.status) {
        setSelectedBuoy(updatedBuoy)
      }
    }
  }, [buoys, selectedBuoy])

  const fetchBuoys = async () => {
    try {
      const res = await buoyApi.list({ page_size: 100 })
      setBuoys(res.data.items)
    } catch (error) {
      console.error('Failed to fetch buoys:', error)
    }
  }

  const initMQTT = async () => {
    try {
      console.log('Subscribing to MQTT topics...')
      mqttService.subscribe((topic: string, msg: BuoyDataMessage | AlertWebSocketMessage | any) => {
        if (topic === 'buoy/alert' || topic.startsWith('buoy/alert')) {
          handleAlertMessage(msg as AlertWebSocketMessage)
        } else if (topic.startsWith('buoy/data/')) {
          handleBuoyDataMessage(msg as BuoyDataMessage)
        } else if (topic.startsWith('buoy/status/')) {
          const statusMsg = msg as any
          if (statusMsg.buoy_id && statusMsg.status) {
            handleStatusChange(statusMsg.buoy_id, statusMsg.status)
          }
        }
      })
      setMqttConnected(true)
    } catch (error) {
      console.error('Failed to subscribe to MQTT:', error)
    }
  }

  const handleAlertMessage = useCallback((msg: AlertWebSocketMessage) => {
    const alert: AlertNotification = {
      id: msg.alert.id,
      buoy_id: msg.alert.buoy_id,
      buoy_name: msg.alert.buoy_name,
      param_name: msg.alert.param_name,
      actual_value: msg.alert.actual_value,
      threshold_value: msg.alert.threshold_value || 0,
      severity: msg.alert.severity,
      status: msg.alert.status,
      triggered_at: msg.alert.triggered_at || new Date().toISOString(),
      type: msg.type
    }

    addAlertNotification(alert)

    if (msg.type === 'alert_triggered') {
      notification.warning({
        message: `告警 - ${msg.alert.buoy_name}`,
        description: `${msg.alert.param_name}: ${msg.alert.actual_value} (阈值: ${msg.alert.threshold_value})`,
        duration: 5,
        icon: <BellOutlined style={{ color: '#fa8c16' }} />
      })
    } else {
      notification.success({
        message: `恢复 - ${msg.alert.buoy_name}`,
        description: `${msg.alert.param_name} 已恢复正常`,
        duration: 3
      })
    }
  }, [addAlertNotification])

  const handleStatusChange = useCallback((buoyId: string, newStatus: string) => {
    const currentBuoys = useAppStore.getState().buoys
    const currentRealtimeData = useAppStore.getState().realtimeData
    setBuoys(currentBuoys.map((buoy: any) =>
      buoy.id === buoyId ? { ...buoy, status: newStatus } : buoy
    ))
    // 离线、失联等状态保留数据条目但更新状态
    if (newStatus === 'offline' || newStatus === 'disconnected') {
      const existing = currentRealtimeData.find((d: BuoyData) => d.buoy_id === buoyId)
      if (existing) {
        setRealtimeData(currentRealtimeData.map((data: BuoyData) =>
          data.buoy_id === buoyId ? { ...data, status: newStatus, data: {} } : data
        ))
      }
    } else {
      setRealtimeData(currentRealtimeData.map((data: BuoyData) =>
        data.buoy_id === buoyId ? { ...data, status: newStatus } : data
      ))
    }
  }, [setBuoys, setRealtimeData])

  const handleBuoyDataMessage = useCallback((msg: BuoyDataMessage) => {
    if ('buoys' in msg && Array.isArray((msg as any).buoys)) {
      const allData = (msg as any).buoys as BuoyDataMessage[]
      const currentData = useAppStore.getState().realtimeData
      const updatedData = [...currentData]

      allData.forEach((buoyMsg: BuoyDataMessage) => {
        const buoyData: BuoyData = {
          buoy_id: buoyMsg.buoy_id,
          buoy_name: buoyMsg.buoy_name,
          status: buoyMsg.status,
          battery_level: buoyMsg.battery_level,
          low_battery: buoyMsg.low_battery,
          no_power: buoyMsg.no_power,
          latitude: buoyMsg.latitude,
          longitude: buoyMsg.longitude,
          drift_flagged: buoyMsg.drift_flagged,
          data: {
            temperature: buoyMsg.data?.temperature,
            salinity: buoyMsg.data?.salinity,
            ph: buoyMsg.data?.ph,
            dissolved_oxygen: buoyMsg.data?.dissolved_oxygen,
            turbidity: buoyMsg.data?.turbidity,
            chlorophyll: buoyMsg.data?.chlorophyll,
            wave_height: buoyMsg.data?.wave_height
          }
        }
        const existingIndex = updatedData.findIndex((d: BuoyData) => d.buoy_id === buoyData.buoy_id)
        if (existingIndex >= 0) {
          updatedData[existingIndex] = buoyData
        } else {
          updatedData.push(buoyData)
        }
      })

      setRealtimeData(updatedData)
      return
    }

    const buoyData: BuoyData = {
      buoy_id: msg.buoy_id,
      buoy_name: msg.buoy_name,
      status: msg.status,
      battery_level: msg.battery_level,
      low_battery: msg.low_battery,
      no_power: msg.no_power,
      latitude: msg.latitude,
      longitude: msg.longitude,
      drift_flagged: msg.drift_flagged,
      data: {
        temperature: msg.data?.temperature,
        salinity: msg.data?.salinity,
        ph: msg.data?.ph,
        dissolved_oxygen: msg.data?.dissolved_oxygen,
        turbidity: msg.data?.turbidity,
        chlorophyll: msg.data?.chlorophyll,
        wave_height: msg.data?.wave_height
      }
    }

    const currentData = useAppStore.getState().realtimeData
    const updatedData = [...currentData]
    const existingIndex = updatedData.findIndex((d: BuoyData) => d.buoy_id === buoyData.buoy_id)
    if (existingIndex >= 0) {
      updatedData[existingIndex] = buoyData
    } else {
      updatedData.push(buoyData)
    }
    setRealtimeData(updatedData)
  }, [setRealtimeData])

  const selectedParamConfig = PARAM_OPTIONS.find(p => p.value === selectedParam) || PARAM_OPTIONS[0]

  return (
    <div>
      {/* MQTT 连接状态 & 告警通知 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={18}>
          {!mqttConnected && (
            <div style={{ background: '#fff3cd', padding: '8px 16px', borderRadius: 4 }}>
              MQTT 连接中... 数据将实时更新
            </div>
          )}
          {mqttConnected && (
            <div style={{ background: '#f6ffed', padding: '8px 16px', borderRadius: 4, border: '1px solid #b7eb8f' }}>
              MQTT 已连接 - 数据实时同步中
            </div>
          )}
        </Col>
        <Col span={6}>
          {unreadAlertCount > 0 && (
            <Badge count={unreadAlertCount} overflowCount={99}>
              <Button icon={<BellOutlined />} onClick={markAlertsRead}>
                未读告警 ({unreadAlertCount})
              </Button>
            </Badge>
          )}
          {unreadAlertCount === 0 && alertNotifications.length > 0 && (
            <span style={{ color: '#999' }}>
              最近告警: {alertNotifications[0]?.buoy_name} - {alertNotifications[0]?.param_name}
            </span>
          )}
        </Col>
      </Row>

      {/* 地图区域 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <div style={{ height: 450 }}>
            <BuoyMap
              buoys={buoys}
              realtimeData={realtimeData}
              onTrajectoryClick={(buoy) => {
                setSelectedBuoy(buoy)
                setTrajectoryVisible(true)
              }}
            />
          </div>
        </Col>
      </Row>

      {/* 参数选择 & 浮标卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small" title="监测参数">
            <Select
              value={selectedParam}
              onChange={setSelectedParam}
              options={PARAM_OPTIONS}
              style={{ width: '100%' }}
            />
          </Card>
        </Col>
        {buoys.map((buoy: any) => {
          const data = realtimeData.find((d: BuoyData) => d.buoy_id === buoy.id)
          return (
            <Col span={6} key={buoy.id}>
              <BuoyCard
                buoy={buoy}
                data={data}
                selectedParam={selectedParam}
                selectedParamConfig={selectedParamConfig}
                onClick={() => {
                  const instance = getBuoyMapInstance()
                  instance.panToBuoy(buoy.id)
                }}
              />
            </Col>
          )
        })}
      </Row>

      <BuoyTrajectory
        buoy={selectedBuoy}
        visible={trajectoryVisible}
        onClose={() => {
          setTrajectoryVisible(false)
          setSelectedBuoy(null)
        }}
      />
    </div>
  )
}

export default Dashboard
