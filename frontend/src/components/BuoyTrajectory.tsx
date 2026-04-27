import { useEffect, useRef, useState } from 'react'
import { Modal, Tag, Descriptions, Divider } from 'antd'
import { Buoy, useAppStore } from '../stores/appStore'
import { mqttService } from '../services/mqtt'

interface PositionPoint {
  lat: number
  lon: number
  time: Date
}

interface BuoyTrajectoryProps {
  buoy: Buoy | null
  visible: boolean
  onClose: () => void
}

export default function BuoyTrajectory({ buoy, visible, onClose }: BuoyTrajectoryProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<any>(null)
  const currentMarkerRef = useRef<any>(null)
  const trailMarkerRefs = useRef<any[]>([])
  const circleRef = useRef<any>(null)
  const trajectoryRef = useRef<PositionPoint[]>([])
  const [currentPos, setCurrentPos] = useState<{ lat: number; lon: number } | null>(null)
  const [trajectory, setTrajectory] = useState<PositionPoint[]>([])
  const [latestData, setLatestData] = useState<any>(null)

  // Draw drift radius circle
  const drawDriftCircle = (map: any, centerLat: number, centerLon: number, radius: number) => {
    if (circleRef.current) {
      circleRef.current.setMap(null)
    }

    const radiusMeters = radius * 111000

    const AMapAny = window.AMap as any
    const circle = new AMapAny.Circle({
      center: new window.AMap.LngLat(centerLon, centerLat),
      radius: radiusMeters,
      fillColor: '#1890ff20',
      fillOpacity: 0.3,
      strokeColor: '#1890ff',
      strokeOpacity: 1,
      strokeWeight: 2,
      strokeStyle: 'dashed'
    })

    circle.setMap(map)
    circleRef.current = circle
  }

  // Initialize map when modal opens
  useEffect(() => {
    if (!visible || !buoy) return

    let map: any = null

    const initMap = () => {
      if (!window.AMap || !mapContainerRef.current || !buoy) {
        return
      }

      const centerLat = buoy.latitude
      const centerLon = buoy.longitude

      map = new window.AMap.Map(mapContainerRef.current, {
        zoom: 12,
        center: new window.AMap.LngLat(centerLon, centerLat),
        viewMode: '2D',
        mapStyle: 'amap://styles/whitesmoke'
      })

      ;(map as any).addControl(new window.AMap.Scale())
      ;(map as any).addControl(new window.AMap.ToolBar())

      mapRef.current = map

      // Draw drift radius circle (default radius 0.01 degree ≈ 1km)
      drawDriftCircle(map, centerLat, centerLon, buoy.drift_radius || 0.01)

      // Add current position marker
      updateCurrentPosition(map, centerLat, centerLon)

      // Add trail markers
      updateTrail(map, trajectory)
    }

    // Wait for next tick to ensure container is rendered
    const timer = setTimeout(() => {
      initMap()
    }, 200)

    return () => {
      clearTimeout(timer)
    }
  }, [visible, buoy])

  // Update current position marker
  const updateCurrentPosition = (map: any, lat: number, lon: number, isDrift: boolean = false) => {
    if (currentMarkerRef.current) {
      currentMarkerRef.current.setMap(null)
    }

    const color = isDrift ? '#ff4d4f' : '#52c41a'

    const markerContent = document.createElement('div')
    markerContent.style.cssText = `
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: ${color};
      border: 3px solid white;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      position: relative;
    `
    if (isDrift) {
      markerContent.style.animation = 'pulse 1s infinite'
    }

    const style = document.createElement('style')
    style.textContent = `
      @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(255, 77, 79, 0.7); }
        70% { box-shadow: 0 0 0 10px rgba(255, 77, 79, 0); }
        100% { box-shadow: 0 0 0 0 rgba(255, 77, 79, 0); }
      }
    `
    document.head.appendChild(style)

    const marker = new window.AMap.Marker({
      position: new window.AMap.LngLat(lon, lat),
      content: markerContent,
      offset: new window.AMap.Pixel(-10, -10)
    })

    marker.setMap(map)
    currentMarkerRef.current = marker
  }

  // Add trail markers
  const updateTrail = (map: any, points: PositionPoint[]) => {
    // Clear existing trail markers
    trailMarkerRefs.current.forEach(m => m.setMap(null))
    trailMarkerRefs.current = []

    points.forEach((point, index) => {
      const opacity = (index + 1) / points.length
      const size = 6 + (index / points.length) * 4

      const trailContent = document.createElement('div')
      trailContent.style.cssText = `
        width: ${size}px;
        height: ${size}px;
        border-radius: 50%;
        background: rgba(24, 144, 255, ${opacity});
        border: 1px solid rgba(24, 144, 255, ${opacity * 0.5});
      `

      const marker = new window.AMap.Marker({
        position: new window.AMap.LngLat(point.lon, point.lat),
        content: trailContent,
        offset: new window.AMap.Pixel(-size/2, -size/2)
      })

      marker.setMap(map)
      trailMarkerRefs.current.push(marker)
    })

    // Draw trail line if we have enough points
    if (points.length > 1) {
      const AMapAny = window.AMap as any
      const line = new AMapAny.Polyline({
        path: points.map(p => new window.AMap.LngLat(p.lon, p.lat)),
        strokeColor: '#1890ff',
        strokeOpacity: 0.6,
        strokeWeight: 2,
        strokeStyle: 'solid'
      })
      line.setMap(map)
      trailMarkerRefs.current.push(line)
    }
  }

  // Load immediate data when modal opens
  useEffect(() => {
    if (!visible || !buoy) return

    // 立即从 store 获取当前数据
    const realtimeData = useAppStore.getState().realtimeData
    const currentBuoyData = realtimeData.find((d: any) => d.buoy_id === buoy.id)

    if (currentBuoyData) {
      const lat = currentBuoyData.latitude ?? buoy.latitude
      const lon = currentBuoyData.longitude ?? buoy.longitude
      if (Number.isFinite(lat) && Number.isFinite(lon)) {
        setCurrentPos({ lat, lon })
        trajectoryRef.current = [{ lat, lon, time: new Date() }]
        setTrajectory([{ lat, lon, time: new Date() }])
      }
      setLatestData(currentBuoyData)
    }
  }, [visible, buoy])

  // MQTT subscription for real-time map updates
  useEffect(() => {
    if (!visible || !buoy) return

    const handleMessage = (topic: string, msg: any) => {
      // 处理状态变化消息
      if (topic.includes('buoy/status/')) {
        if (msg.buoy_id === buoy.id && msg.status) {
          const isDrifting = msg.status === 'drift_alert'
          if (mapRef.current && currentPos) {
            updateCurrentPosition(mapRef.current, currentPos.lat, currentPos.lon, isDrifting)
          }
          setLatestData((prev: any) => prev ? { ...prev, status: msg.status } : prev)
        }
        return
      }

      if (!topic.includes('buoy/data/all') && !topic.includes('buoy/data/')) return
      if (!msg.buoys) return

      msg.buoys.forEach((b: any) => {
        if (b.buoy_id === buoy.id) {
          if (!Number.isFinite(b.latitude) || !Number.isFinite(b.longitude)) {
            return
          }
          const newPos = { lat: b.latitude, lon: b.longitude }
          setCurrentPos(newPos)

          const isDrifting = b.status === 'drift_alert' || b.drift_flagged

          if (mapRef.current) {
            updateCurrentPosition(mapRef.current, b.latitude, b.longitude, isDrifting)

            if (Number.isFinite(b.latitude) && Number.isFinite(b.longitude)) {
              const newTrajectory = [...trajectoryRef.current, { lat: b.latitude, lon: b.longitude, time: new Date() }]
              if (newTrajectory.length > 50) {
                newTrajectory.shift()
              }
              trajectoryRef.current = newTrajectory
              setTrajectory(newTrajectory)
              updateTrail(mapRef.current, newTrajectory)
            }
          }

          setLatestData(b)
        }
      })
    }

    const unsubscribe = mqttService.subscribe(handleMessage)

    return () => {
      unsubscribe()
    }
  }, [visible, buoy, currentPos])

  // Cleanup on modal close
  useEffect(() => {
    if (!visible) {
      setTrajectory([])
      trajectoryRef.current = []
      setCurrentPos(null)
      setLatestData(null)
    }
  }, [visible])

  const getStatusInfo = (status: string) => {
    const config: Record<string, { color: string; label: string }> = {
      online: { color: 'green', label: '在线' },
      offline: { color: 'red', label: '离线' },
      inactive: { color: 'default', label: '未激活' },
      disconnected: { color: 'purple', label: '失联' },
      low_battery: { color: 'orange', label: '低电量' },
      no_power: { color: 'red', label: '无电' },
      drift_alert: { color: 'cyan', label: '漂移告警' },
    }
    return config[status] || { color: 'default', label: status }
  }

  return (
    <Modal
      title={`${buoy?.name} - 实时轨迹`}
      open={visible}
      onCancel={onClose}
      footer={null}
      width={900}
      bodyStyle={{ padding: 0 }}
      destroyOnClose
    >
      <div style={{ display: 'flex', height: 500 }}>
        {/* Map */}
        <div style={{ flex: 1, height: 500 }}>
          <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
        </div>

        {/* Info Panel */}
        <div style={{ width: 280, padding: 16, background: '#fafafa', borderLeft: '1px solid #f0f0f0', overflow: 'auto' }}>
          <Descriptions column={1} size="small" title="浮标信息">
            <Descriptions.Item label="名称">{buoy?.name}</Descriptions.Item>
            <Descriptions.Item label="编码">{buoy?.code}</Descriptions.Item>
            <Descriptions.Item label="海域">{buoy?.sea_area || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={getStatusInfo(latestData?.status || buoy?.status || 'online').color}>
                {getStatusInfo(latestData?.status || buoy?.status || 'online').label}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="电量">
              {latestData?.battery_level ?? buoy?.battery_level ?? '--'}%
            </Descriptions.Item>
          </Descriptions>

          <Divider />

          <div style={{ marginBottom: 8, fontWeight: 500 }}>当前位置</div>
          <div style={{ fontSize: 12, color: '#666' }}>
            <div>纬度: {currentPos?.lat?.toFixed(6) || buoy?.latitude?.toFixed(6) || '--'}</div>
            <div>经度: {currentPos?.lon?.toFixed(6) || buoy?.longitude?.toFixed(6) || '--'}</div>
          </div>

          <Divider />

          <div style={{ marginBottom: 8, fontWeight: 500 }}>实时数据</div>
          {latestData?.data ? (
            <div style={{ fontSize: 12 }}>
              <div>水温: {latestData.data.temperature ?? '--'} °C</div>
              <div>盐度: {latestData.data.salinity ?? '--'} PSU</div>
              <div>pH: {latestData.data.ph ?? '--'}</div>
              <div>溶解氧: {latestData.data.dissolved_oxygen ?? '--'} mg/L</div>
              <div>浊度: {latestData.data.turbidity ?? '--'} NTU</div>
              <div>叶绿素: {latestData.data.chlorophyll ?? '--'} μg/L</div>
              <div>波高: {latestData.data.wave_height ?? '--'} m</div>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: '#999' }}>等待数据...</div>
          )}

          <Divider />

          <div style={{ fontSize: 11, color: '#999' }}>
            <div>* 绿色标记为当前位置</div>
            <div>* 蓝色圆圈为正常漂移范围</div>
            <div>* 轨迹显示最近50个位置点</div>
            <div>* 红色标记表示漂移告警状态</div>
          </div>

          {latestData?.status === 'drift_alert' && (
            <>
              <Divider />
              <Tag color="cyan" style={{ display: 'block', textAlign: 'center', padding: 8 }}>
                当前处于漂移告警状态<br/>
                仅传输位置和电量数据
              </Tag>
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}
