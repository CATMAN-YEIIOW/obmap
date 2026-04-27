import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor to add auth token
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

// Response interceptor
api.interceptors.response.use(
  response => response,
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

// Buoy APIs
export const buoyApi = {
  list: (params?: { page?: number; page_size?: number; status?: string; sea_area?: string }) =>
    api.get('/buoys', { params }),
  get: (buoyId: string) => api.get(`/buoys/${buoyId}`),
  create: (data: any) => api.post('/buoys', data),
  update: (buoyId: string, data: any) => api.put(`/buoys/${buoyId}`, data),
  delete: (buoyId: string) => api.delete(`/buoys/${buoyId}`)
}

// Data APIs
export const dataApi = {
  realtime: (buoyIds?: string) => api.get('/data/realtime', { params: { buoy_ids: buoyIds } }),
  history: (params: { buoy_id: string; start_time: string; end_time: string; param?: string; page?: number; page_size?: number }) =>
    api.get('/data/history', { params }),
  latest: (buoyId: string) => api.get(`/data/latest/${buoyId}`)
}

// Alert APIs
export const alertApi = {
  list: (params?: { buoy_id?: string; status?: string; severity?: string; start_time?: string; end_time?: string; page?: number; page_size?: number }) =>
    api.get('/alerts', { params }),
  statistics: () => api.get('/alerts/statistics'),
  acknowledge: (alertId: string, remarks?: string) =>
    api.put(`/alerts/${alertId}/acknowledge`, remarks ? { remarks } : {}),
  resolve: (alertId: string, remarks?: string) =>
    api.put(`/alerts/${alertId}/resolve`, remarks ? { remarks } : {}),
  getConfig: (buoyId?: string) => api.get('/alerts/config', { params: buoyId ? { buoy_id: buoyId } : {} }),
  getBuoyParamConfig: (buoyId: string, paramName: string) => api.get(`/alerts/config/${buoyId}/${paramName}`),
  createConfig: (data: { buoy_id?: string; param_name: string; min_threshold?: number; max_threshold?: number; severity: string; enabled: boolean }) =>
    api.post('/alerts/config', data),
  updateConfig: (configId: string, data: { min_threshold?: number; max_threshold?: number; severity?: string; enabled?: boolean }) =>
    api.put(`/alerts/config/${configId}`, data),
  deleteConfig: (configId: string) => api.delete(`/alerts/config/${configId}`),
  getRules: (params?: { buoy_id?: string; enabled?: boolean }) => api.get('/alerts/rules', { params }),
  createRule: (data: { name: string; buoy_id?: string; conditions: any[]; severity: string; enabled: boolean }) =>
    api.post('/alerts/rules', data),
  updateRule: (ruleId: string, data: { name?: string; buoy_id?: string; conditions?: any[]; severity?: string; enabled?: boolean }) =>
    api.put(`/alerts/rules/${ruleId}`, data),
  deleteRule: (ruleId: string) => api.delete(`/alerts/rules/${ruleId}`),
  getRecovered: (days?: number) => api.get('/alerts/recovery', { params: { days: days || 7 } })
}

// Statistics APIs
export const statisticsApi = {
  summary: (params: { buoy_id: string; start_time: string; end_time: string }) =>
    api.get('/statistics/summary', { params }),
  timeseries: (params: { buoy_id: string; param: string; start_time: string; end_time: string; bucket?: string }) =>
    api.get('/statistics/timeseries', { params }),
  raw: (params: { buoy_id: string; param: string; start_time: string; end_time: string }) =>
    api.get('/statistics/raw', { params }),
  thresholds: (params: { buoy_id: string }) =>
    api.get('/statistics/thresholds', { params }),
  alertEvents: (params: { buoy_id: string; start_time: string; end_time: string }) =>
    api.get('/statistics/alert-events', { params }),
  compare: (params: { buoy_ids: string; param: string; start_time: string; end_time: string }) =>
    api.get('/statistics/compare', { params }),
  period: (params: { buoy_id: string; period: 'day' | 'week' | 'month' }) =>
    api.get('/statistics/period', { params }),
  exportData: (params: { buoy_id: string; start_time: string; end_time: string; format: 'csv' | 'xlsx' }) => {
    return api.get('/statistics/export/data', {
      params,
      responseType: params.format === 'xlsx' ? 'blob' : 'json'
    })
  },
  // 报表生成
  generateReport: (params: {
    buoy_ids: string[];
    report_type: 'daily' | 'weekly' | 'monthly' | 'quarterly';
    start_time?: string;
    end_time?: string;
    include_trends?: boolean;
  }) => {
    return api.post('/statistics/report', params, {
      responseType: 'blob'
    })
  }
}

// Simulator Command APIs
export const simulatorApi = {
  setScenario: (scenario: string, duration?: number) =>
    api.post('/commands/simulator/scenario', { scenario, duration: duration || 60 }),
  setBuoyScenario: (buoyId: string, scenario: string, duration?: number) =>
    api.post('/commands/simulator/buoy_scenario', { buoy_id: buoyId, scenario, duration: duration || 60 }),
  injectFault: (buoyId: string, faultType: string, duration?: number) =>
    api.post('/commands/simulator/inject_fault', { buoy_id: buoyId, fault_type: faultType, duration: duration || 0 }),
  setBuoyOffline: (buoyId: string, duration?: number) =>
    api.post('/commands/simulator/buoy_offline', { buoy_id: buoyId, duration: duration || 60 }),
  setBuoyOnline: (buoyId: string) =>
    api.post('/commands/simulator/buoy_online', { buoy_id: buoyId }),
  setBuoyActivate: (buoyId: string) =>
    api.post('/commands/simulator/buoy_activate', { buoy_id: buoyId }),
  getStatus: () => api.get('/commands/simulator/status')
}

// Command APIs - for MQTT bidirectional communication
export const commandApi = {
  setInterval: (buoyId: string, interval: number) =>
    api.post('/commands/set_interval', { buoy_id: buoyId, interval }),
  reboot: (buoyId: string) =>
    api.post('/commands/reboot', { buoy_id: buoyId }),
  calibrate: (buoyId: string, sensor: string) =>
    api.post('/commands/calibrate', { buoy_id: buoyId, sensor }),
  setStatus: (buoyId: string, status: 'online' | 'offline' | 'warning') =>
    api.post('/commands/status', { buoy_id: buoyId, status })
}

// User Management APIs
export const userApi = {
  list: () => api.get('/auth/users'),
  updateRole: (userId: string, role: string) =>
    api.put(`/auth/users/${userId}/role`, null, { params: { role } }),
  delete: (userId: string) => api.delete(`/auth/users/${userId}`)
}

export default api
