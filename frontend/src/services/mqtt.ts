import mqtt, { MqttClient, IClientOptions } from 'mqtt'

// MQTT Configuration - WebSocket connection to EMQX
const MQTT_WS_URL = 'ws://localhost:8083/mqtt'
const MQTT_USERNAME = 'admin'
const MQTT_PASSWORD = 'asdfghjkl66'

// Topic definitions
export const MQTT_TOPICS = {
  BUOY_DATA: 'buoy/data/#',
  BUOY_DATA_ALL: 'buoy/data/all',
  BUOY_COMMAND: 'buoy/command/#',
  BUOY_STATUS: 'buoy/status/#',
  BUOY_ALERT: 'buoy/alert'
}

export interface BuoyDataMessage {
  buoy_id: string
  buoy_name: string
  status: string
  timestamp: string
  latitude?: number
  longitude?: number
  battery_level?: number
  drift_flagged?: boolean
  low_battery?: boolean
  no_power?: boolean
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

export interface AlertMessage {
  buoy_id: string
  buoy_name: string
  param_name: string
  actual_value: number
  threshold_value?: number
  direction?: string
  severity: string
  status: string
  triggered_at?: string
}

export interface AlertWebSocketMessage {
  type: 'alert_triggered' | 'alert_recovered'
  alert: {
    id: string
    buoy_id: string
    buoy_name: string
    param_name: string
    actual_value: number
    threshold_value?: number
    direction?: string
    severity: string
    status: string
    triggered_at?: string
    resolved_at?: string
    previous_status?: string
    old_value?: number
    current_value?: number
  }
}

export interface CommandMessage {
  type: 'set_interval' | 'reboot' | 'calibrate' | 'set_status' | 'recover'
  params: Record<string, any>
}

class MQTTService {
  private client: MqttClient | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 10
  private messageHandlers: Set<(topic: string, message: BuoyDataMessage | CommandMessage | AlertWebSocketMessage) => void> = new Set()

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.client && this.client.connected) {
        resolve()
        return
      }

      const options: IClientOptions = {
        username: MQTT_USERNAME,
        password: MQTT_PASSWORD,
        reconnectPeriod: 5000,
        connectTimeout: 30000,
        clean: true,
        keepalive: 60
      }

      console.log('Connecting to MQTT broker at', MQTT_WS_URL)

      this.client = mqtt.connect(MQTT_WS_URL, options)

      this.client.on('connect', () => {
        console.log('MQTT Connected successfully')
        this.reconnectAttempts = 0

        // Subscribe to topics
        this.client?.subscribe([
          MQTT_TOPICS.BUOY_DATA,
          MQTT_TOPICS.BUOY_STATUS,
          MQTT_TOPICS.BUOY_ALERT
        ], (err) => {
          if (err) {
            console.error('MQTT Subscribe error:', err)
            reject(err)
          } else {
            console.log('MQTT subscribed to topics')
            resolve()
          }
        })
      })

      this.client.on('error', (err) => {
        console.error('MQTT Error:', err)
        if (!this.client?.connected) {
          reject(err)
        }
      })

      this.client.on('message', (topic, payload) => {
        try {
          const message = JSON.parse(payload.toString())
          console.log('MQTT message on', topic, ':', message)
          this.messageHandlers.forEach(handler => handler(topic, message))
        } catch (err) {
          console.error('Failed to parse MQTT message:', err)
        }
      })

      this.client.on('reconnect', () => {
        this.reconnectAttempts++
        console.log(`MQTT reconnecting... attempt ${this.reconnectAttempts}`)
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
          console.error('Max reconnection attempts reached')
          this.client?.end()
        }
      })

      this.client.on('close', () => {
        console.log('MQTT connection closed')
      })

      this.client.on('offline', () => {
        console.log('MQTT client offline')
      })
    })
  }

  disconnect() {
    if (this.client) {
      this.client.end()
      this.client = null
      console.log('MQTT disconnected')
    }
  }

  isConnected(): boolean {
    return this.client?.connected ?? false
  }

  subscribe(handler: (topic: string, message: BuoyDataMessage | CommandMessage | AlertWebSocketMessage) => void) {
    this.messageHandlers.add(handler)
    return () => {
      this.messageHandlers.delete(handler)
    }
  }

  publishCommand(buoyId: string, command: CommandMessage) {
    if (!this.client?.connected) {
      console.error('Cannot publish command: MQTT not connected')
      return
    }

    const topic = `buoy/command/${buoyId}`
    const payload = JSON.stringify(command)

    this.client.publish(topic, payload, (err) => {
      if (err) {
        console.error('Failed to publish command:', err)
      } else {
        console.log(`Published command to ${topic}:`, command)
      }
    })
  }

  setSamplingInterval(buoyId: string, intervalSeconds: number) {
    this.publishCommand(buoyId, {
      type: 'set_interval',
      params: { interval: intervalSeconds }
    })
  }

  rebootBuoy(buoyId: string) {
    this.publishCommand(buoyId, {
      type: 'reboot',
      params: {}
    })
  }

  calibrateSensor(buoyId: string, sensor: string) {
    this.publishCommand(buoyId, {
      type: 'calibrate',
      params: { sensor }
    })
  }

  recoverBuoy(buoyId: string, reason: string = 'disconnected') {
    this.publishCommand(buoyId, {
      type: 'recover',
      params: { reason }
    })
  }
}

export const mqttService = new MQTTService()
export default mqttService
