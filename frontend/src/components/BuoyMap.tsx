import { useEffect, useRef, useState } from 'react'
import { Card, Spin } from 'antd'
import { BuoyData } from '../stores/appStore'

interface BuoyInfo {
  id: string
  name: string
  code: string
  latitude: number
  longitude: number
  status: string
  sea_area?: string
}

interface BuoyMapProps {
  buoys: BuoyInfo[]
  realtimeData: BuoyData[]
  onTrajectoryClick?: (buoy: BuoyInfo) => void
}

export interface BuoyMapHandle {
  panToBuoy: (buoyId: string) => void
}

interface MarkerData {
  marker: any
  infoWindow: any
}

// Global ref for external access
const buoyMapInstance = {
  panToBuoy: (_buoyId: string) => {}
}

if (typeof window !== 'undefined') {
  (window as any).buoyMapInstance = buoyMapInstance
}

export function getBuoyMapInstance() {
  return buoyMapInstance
}

export default function BuoyMap({ buoys, realtimeData, onTrajectoryClick }: BuoyMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<any>(null)
  const markersRef = useRef<Map<string, MarkerData>>(new Map())
  const [loading, setLoading] = useState(true)
  const buoysLoadedRef = useRef<boolean>(false)

  // Update global instance when map is ready
  useEffect(() => {
    if (mapRef.current) {
      buoyMapInstance.panToBuoy = (buoyId: string) => {
        const markerData = markersRef.current.get(buoyId)
        if (mapRef.current && markerData) {
          mapRef.current.panTo(markerData.marker.getPosition())
          markerData.infoWindow.open(mapRef.current, markerData.marker.getPosition())
        }
      }
    }
  }, [loading])

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return

    const initMap = () => {
      if (!window.AMap || !mapContainerRef.current) return

      const map = new window.AMap.Map(mapContainerRef.current, {
        zoom: 5,
        center: new window.AMap.LngLat(120, 30),
        viewMode: '3D',
        mapStyle: 'amap://styles/whitesmoke'
      }) as any

      ;(map as any).addControl(new window.AMap.Scale())
      ;(map as any).addControl(new window.AMap.ToolBar())

      mapRef.current = map
      setLoading(false)
    }

    if (window.AMap) {
      initMap()
    } else {
      window.addEventListener('load', initMap)
      return () => window.removeEventListener('load', initMap)
    }
  }, [])

  // Create markers only when buoys first load
  useEffect(() => {
    const map = mapRef.current
    if (!map || buoys.length === 0 || buoysLoadedRef.current) return

    buoysLoadedRef.current = true
    createMarkers(buoys)
  }, [buoys])

  // Update info windows when realtimeData changes
  useEffect(() => {
    if (realtimeData.length === 0) return
    updateInfoWindows()
  }, [realtimeData])

  const createMarkers = (buoys: BuoyInfo[]) => {
    const map = mapRef.current
    if (!map) return

    // Clear existing markers
    markersRef.current.forEach((data) => {
      data.marker.setMap(null)
    })
    markersRef.current.clear()

    const statusColors: Record<string, string> = {
      online: '#52c41a',
      offline: '#8c8c8c',
      warning: '#fa8c16',
      drift_alert: '#1890ff',
      low_battery: '#fa8c16',
      no_power: '#ff4d4f',
      disconnected: '#722ed1'
    }

    // 获取浮标颜色，支持低电量/无电和漂移告警叠加
    const getMarkerColor = (status: string, buoyData?: BuoyData): string => {
      // 漂移告警+无电：一半蓝色一半红色
      if (status === 'drift_alert' && buoyData?.no_power) {
        return 'linear-gradient(135deg, #1890ff 50%, #ff4d4f 50%)'
      }
      // 漂移告警+低电量：一半蓝色一半橙色
      if (status === 'drift_alert' && buoyData?.low_battery) {
        return 'linear-gradient(135deg, #1890ff 50%, #fa8c16 50%)'
      }
      // 无电状态：红色
      if (status === 'no_power' || buoyData?.no_power) {
        return statusColors.no_power
      }
      return statusColors[status] || '#8c8c8c'
    }

    // 获取状态标签文本
    const getStatusLabelText = (status: string, buoyData?: BuoyData): string => {
      if (status === 'drift_alert' && buoyData?.no_power) {
        return '漂移+无电'
      }
      if (status === 'drift_alert' && buoyData?.low_battery) {
        return '漂移+低电量'
      }
      if (status === 'no_power' || buoyData?.no_power) return '无电'
      if (status === 'drift_alert') return '漂移告警'
      if (status === 'low_battery') return '低电量'
      if (status === 'online') return '在线'
      if (status === 'warning') return '告警'
      if (status === 'offline') return '离线'
      if (status === 'disconnected') return '失联'
      return status
    }

    buoys.forEach((buoy) => {
      // 跳过无效坐标的浮标
      if (!buoy.latitude || !buoy.longitude || !Number.isFinite(buoy.latitude) || !Number.isFinite(buoy.longitude)) {
        console.warn(`[BuoyMap] Skipping buoy ${buoy.id} with invalid coordinates:`, buoy.latitude, buoy.longitude)
        return
      }

      const buoyData = realtimeData.find(d => d.buoy_id === buoy.id)
      const markerColor = getMarkerColor(buoy.status, buoyData)

      const markerContent = document.createElement('div')
      markerContent.style.cssText = `
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background: ${markerColor};
        border: 3px solid white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        cursor: pointer;
      `

      const marker = new window.AMap.Marker({
        position: new window.AMap.LngLat(buoy.longitude, buoy.latitude),
        title: buoy.name,
        content: markerContent,
        offset: new window.AMap.Pixel(-12, -12)
      })

      const infoWindow = createInfoWindow(buoy, buoyData, statusColors, getStatusLabelText, onTrajectoryClick)

      marker.on('click', () => {
        infoWindow.open(map, marker.getPosition())
      })

      marker.setMap(map)
      markersRef.current.set(buoy.id, { marker, infoWindow })
    })

    // Fit bounds only once on initial load
    if (buoys.length > 0) {
      map.setFitView()
    }
  }

  const createInfoWindow = (buoy: BuoyInfo, buoyData: BuoyData | undefined, statusColors: Record<string, string>, getStatusLabelText: (status: string, buoyData?: BuoyData) => string, onTrajectoryClick?: (buoy: BuoyInfo) => void) => {
    const infoContent = document.createElement('div')
    infoContent.style.cssText = `
      padding: 8px;
      min-width: 200px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    `

    const getStatusDisplayStyle = (status: string, buoyData?: BuoyData): string => {
      // 漂移告警+无电：左右分割显示
      if (status === 'drift_alert' && buoyData?.no_power) {
        return 'background: linear-gradient(90deg, #1890ff 50%, #ff4d4f 50%); -webkit-background-clip: text; background-clip: text; color: transparent; font-weight: bold;'
      }
      // 漂移告警+低电量：左右分割显示
      if (status === 'drift_alert' && buoyData?.low_battery) {
        return 'background: linear-gradient(90deg, #1890ff 50%, #fa8c16 50%); -webkit-background-clip: text; background-clip: text; color: transparent; font-weight: bold;'
      }
      // 无电状态：红色
      if (status === 'no_power' || buoyData?.no_power) {
        return `color: ${statusColors.no_power}; font-weight: bold;`
      }
      return `color: ${statusColors[status]}; font-weight: bold;`
    }

    const renderContent = () => {
      const temp = buoyData?.data?.temperature ?? '-'
      const salinity = buoyData?.data?.salinity ?? '-'
      const ph = buoyData?.data?.ph ?? '-'
      const dissolved_oxygen = buoyData?.data?.dissolved_oxygen ?? '-'
      const turbidity = buoyData?.data?.turbidity ?? '-'
      const chlorophyll = buoyData?.data?.chlorophyll ?? '-'
      const wave_height = buoyData?.data?.wave_height ?? '-'
      return `
        <div style="font-weight: bold; font-size: 14px; margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 8px;">
          ${buoy.name}
        </div>
        <div style="font-size: 12px; color: #666; margin-bottom: 4px;">
          <span style="font-weight: 500;">编码:</span> ${buoy.code}
        </div>
        <div style="font-size: 12px; color: #666; margin-bottom: 4px;">
          <span style="font-weight: 500;">海域:</span> ${buoy.sea_area || '-'}
        </div>
        <div style="font-size: 12px; color: #666; margin-bottom: 4px;">
          <span style="font-weight: 500;">状态:</span>
          <span style="${getStatusDisplayStyle(buoy.status, buoyData)}">
            ${getStatusLabelText(buoy.status, buoyData)}
          </span>
        </div>
        <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #eee;">
          <div style="font-size: 12px; margin-bottom: 2px;">
            <span style="color: #888;">水温:</span>
            <span style="font-weight: 500; margin-left: 4px;">${temp} °C</span>
          </div>
          <div style="font-size: 12px; margin-bottom: 2px;">
            <span style="color: #888;">盐度:</span>
            <span style="font-weight: 500; margin-left: 4px;">${salinity} PSU</span>
          </div>
          <div style="font-size: 12px; margin-bottom: 2px;">
            <span style="color: #888;">pH:</span>
            <span style="font-weight: 500; margin-left: 4px;">${ph}</span>
          </div>
          <div style="font-size: 12px; margin-bottom: 2px;">
            <span style="color: #888;">溶解氧:</span>
            <span style="font-weight: 500; margin-left: 4px;">${dissolved_oxygen} mg/L</span>
          </div>
          <div style="font-size: 12px; margin-bottom: 2px;">
            <span style="color: #888;">浊度:</span>
            <span style="font-weight: 500; margin-left: 4px;">${turbidity} NTU</span>
          </div>
          <div style="font-size: 12px; margin-bottom: 2px;">
            <span style="color: #888;">叶绿素:</span>
            <span style="font-weight: 500; margin-left: 4px;">${chlorophyll} μg/L</span>
          </div>
          <div style="font-size: 12px; margin-bottom: 2px;">
            <span style="color: #888;">波高:</span>
            <span style="font-weight: 500; margin-left: 4px;">${wave_height} m</span>
          </div>
        </div>
        <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #eee; text-align: center;">
          <button id="trajectory-btn-${buoy.id}" style="
            background: #1890ff;
            color: white;
            border: none;
            padding: 4px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
          ">查看轨迹</button>
        </div>
      `
    }

    infoContent.innerHTML = renderContent()

    // Store updateData function for realtime updates
    ;(infoContent as any).updateData = (newBuoyData: BuoyData) => {
      buoyData = newBuoyData
      infoContent.innerHTML = renderContent()
      // Rebind trajectory button
      const btn = document.getElementById(`trajectory-btn-${buoy.id}`)
      if (btn && onTrajectoryClick) {
        btn.onclick = () => onTrajectoryClick(buoy)
      }
    }

    // Bind trajectory button
    setTimeout(() => {
      const btn = document.getElementById(`trajectory-btn-${buoy.id}`)
      if (btn && onTrajectoryClick) {
        btn.onclick = () => onTrajectoryClick(buoy)
      }
    }, 0)

    return new window.AMap.InfoWindow({
      content: infoContent,
      offset: new window.AMap.Pixel(0, -30),
      closeWhenClickMap: true
    })
  }

  const updateInfoWindows = () => {
    const map = mapRef.current
    if (!map) return

    const statusColors: Record<string, string> = {
      online: '#52c41a',
      offline: '#8c8c8c',
      warning: '#fa8c16',
      drift_alert: '#1890ff',
      low_battery: '#fa8c16',
      no_power: '#ff4d4f',
      disconnected: '#722ed1'
    }

    // 获取状态标签文本
    const getStatusLabelText = (status: string, buoyData?: BuoyData): string => {
      if (status === 'drift_alert' && buoyData?.no_power) {
        return '漂移+无电'
      }
      if (status === 'drift_alert' && buoyData?.low_battery) {
        return '漂移+低电量'
      }
      if (status === 'no_power' || buoyData?.no_power) return '无电'
      if (status === 'drift_alert') return '漂移告警'
      if (status === 'low_battery') return '低电量'
      if (status === 'online') return '在线'
      if (status === 'warning') return '告警'
      if (status === 'offline') return '离线'
      if (status === 'disconnected') return '失联'
      return status
    }

    markersRef.current.forEach((data, buoyId) => {
      const buoy = buoys.find(b => b.id === buoyId)
      const buoyData = realtimeData.find(d => d.buoy_id === buoyId)

      if (buoy) {
        // Validate marker's position before using it
        const markerPosition = data.marker.getPosition()
        if (!markerPosition || !Number.isFinite(markerPosition.lng) || !Number.isFinite(markerPosition.lat)) {
          console.warn(`[BuoyMap] Skipping update for buoy ${buoyId} - invalid marker position`)
          return
        }

        // Check if info window is currently open
        const isOpen = data.infoWindow.getIsOpen()

        if (isOpen) {
          // Update content directly without closing/reopening
          const content = data.infoWindow.getContent()
          if (content && (content as any).updateData) {
            (content as any).updateData(buoyData)
          }
        }

        // Recreate info window with updated data
        data.infoWindow = createInfoWindow(buoy, buoyData, statusColors, getStatusLabelText, onTrajectoryClick)

        // Re-bind click handler
        data.marker.off('click')
        data.marker.on('click', () => {
          data.infoWindow.open(map, markerPosition)
        })

        // If was open, reopen with new content
        if (isOpen) {
          data.infoWindow.open(map, markerPosition)
        }
      }
    })
  }

  return (
    <Card
      title="浮标分布地图"
      style={{ height: '100%' }}
      bodyStyle={{ padding: 0, height: 'calc(100% - 57px)', position: 'relative' }}
    >
      <Spin spinning={loading} tip="地图加载中...">
        <div
          ref={mapContainerRef}
          style={{ width: '100%', height: '100%', minHeight: 400 }}
        />
      </Spin>
    </Card>
  )
}