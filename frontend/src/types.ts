export interface PublicConfig {
  amap_js_key: string
  amap_security_code: string
  timezone: string
  disclaimer: string
}

export interface SourceStatus {
  source: string
  channel: 'transport' | 'ws' | 'http' | 'unknown'
  logical_source: string
  display_name: string
  connected: boolean
  last_message_at: string | null
  last_heartbeat_at: string | null
  last_error: string | null
  updated_at?: string
  latest_payload?: Record<string, unknown> | null
}

export interface Overview {
  event_count: number
  location_count: number
  failed_deliveries: number
  sources: SourceStatus[]
}

export interface EventSummary {
  id: string
  origin_time: string
  hypocenter: string
  latitude: number
  longitude: number
  gcj02_latitude: number
  gcj02_longitude: number
  magnitude: number | null
  depth_km: number | null
  status: string
  revision: number
  latest_source: string
  affected_locations: number
  max_estimated_intensity: number | null
}

export interface Impact {
  location_id: string
  location_name: string
  latitude: number
  longitude: number
  gcj02_latitude: number
  gcj02_longitude: number
  distance_km: number
  estimated_intensity: number | null
  intensity_level: number | null
  confidence: string
  triggered: boolean
  model_version: string
  estimation_status: 'estimated' | 'insufficient_data' | 'out_of_range' | 'failed'
}

export interface EventDetail extends EventSummary {
  impacts: Impact[]
  reports: Array<Record<string, unknown>>
  revisions: Array<Record<string, unknown>>
}

export interface Location {
  id: string
  name: string
  address: string
  latitude: number
  longitude: number
  gcj02_latitude: number
  gcj02_longitude: number
  enabled: boolean
}

export interface Webhook {
  id: string
  name: string
  channel_type: 'generic' | 'telegram'
  url: string | null
  header_names: string[]
  chat_id: string | null
  message_thread_id: number | null
  disable_notification: boolean
  has_bot_token: boolean
  timeout_seconds: number
  enabled: boolean
}
