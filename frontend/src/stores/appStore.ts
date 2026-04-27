import { create } from 'zustand'

export interface Buoy {
  id: string
  name: string
  code: string
  latitude: number
  longitude: number
  depth: number
  status: 'online' | 'offline' | 'warning' | 'inactive' | 'disconnected' | 'low_battery' | 'no_power' | 'drift_alert'
  sea_area: string
  mqtt_client_id?: string
  activation_key?: string
  battery_level?: number
  drift_radius?: number
  drift_alert_enabled?: boolean
  created_at: string
  updated_at: string
}

export interface BuoyData {
  buoy_id: string
  buoy_name: string
  status?: string
  battery_level?: number
  no_power?: boolean
  low_battery?: boolean
  latitude?: number
  longitude?: number
  drift_flagged?: boolean
  data: {
    temperature?: number
    salinity?: number
    ph?: number
    dissolved_oxygen?: number
    turbidity?: number
    chlorophyll?: number
    wave_height?: number
  }
}

export interface AlertNotification {
  id: string
  buoy_id: string
  buoy_name: string
  param_name: string
  actual_value: number
  threshold_value: number
  severity: string
  status: string
  triggered_at: string
  type: 'alert_triggered' | 'alert_recovered'
}

interface AppState {
  buoys: Buoy[]
  realtimeData: BuoyData[]
  selectedBuoy: Buoy | null
  alertNotifications: AlertNotification[]
  unreadAlertCount: number
  activeAlertCount: number
  setBuoys: (buoys: Buoy[]) => void
  setRealtimeData: (data: BuoyData[]) => void
  setSelectedBuoy: (buoy: Buoy | null) => void
  addAlertNotification: (alert: AlertNotification) => void
  clearAlertNotifications: () => void
  markAlertsRead: () => void
  setActiveAlertCount: (count: number) => void
}

export const useAppStore = create<AppState>((set) => ({
  buoys: [],
  realtimeData: [],
  selectedBuoy: null,
  alertNotifications: [],
  unreadAlertCount: 0,
  activeAlertCount: 0,
  setBuoys: (buoys) => set({ buoys }),
  setRealtimeData: (realtimeData) => set({ realtimeData }),
  setSelectedBuoy: (selectedBuoy) => set({ selectedBuoy }),
  addAlertNotification: (alert) =>
    set((state) => ({
      alertNotifications: [alert, ...state.alertNotifications].slice(0, 50),
      unreadAlertCount: state.unreadAlertCount + 1
    })),
  clearAlertNotifications: () => set({ alertNotifications: [] }),
  markAlertsRead: () => set({ unreadAlertCount: 0 }),
  setActiveAlertCount: (count) => set({ activeAlertCount: count })
}))
