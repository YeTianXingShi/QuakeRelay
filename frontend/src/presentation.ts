import type { SourceStatus } from './types'

const SOURCE_NAMES: Record<string, string> = {
  cenc_eew: '中国地震台网预警',
  sc_eew: '四川省地震预警',
  fj_eew: '福建省地震预警',
  cq_eew: '重庆市地震预警',
  cenc_eqlist: '中国地震台网地震信息',
  wolfx_ws: 'Wolfx 实时连接',
}

const EVENT_STATUS_LABELS: Record<string, string> = {
  preliminary: '初报',
  reviewed: '已审定',
  final: '正式报',
  cancelled: '已取消',
}

const DELIVERY_STATUS_LABELS: Record<string, string> = {
  pending: '等待发送',
  processing: '发送中',
  delivered: '已送达',
  failed: '发送失败',
}

const DELIVERY_KIND_LABELS: Record<string, string> = {
  'earthquake.initial': '地震首报',
  'earthquake.update': '地震更新',
  'earthquake.cancelled': '地震取消',
  'system.test': '测试推送',
  'system.source_down': '数据源异常',
  'system.source_recovered': '数据源恢复',
}

const CONFIDENCE_LABELS: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

export function sourceName(source: string): string {
  const name = SOURCE_NAMES[source]
  return name ? `${name}（${source}）` : source
}

export function eventStatusLabel(status: string): string {
  return EVENT_STATUS_LABELS[status] ?? status
}

export function deliveryStatusLabel(status: string): string {
  return DELIVERY_STATUS_LABELS[status] ?? status
}

export function deliveryKindLabel(kind: string): string {
  return DELIVERY_KIND_LABELS[kind] ?? kind
}

export function confidenceLabel(confidence: string): string {
  return CONFIDENCE_LABELS[confidence] ?? confidence
}

export type SourceState = 'normal' | 'abnormal' | 'unreported'

export function sourceState(source: SourceStatus): SourceState {
  const activity = source.channel === 'transport' ? source.last_heartbeat_at : source.last_message_at
  if (!activity && !source.last_error) return 'unreported'
  return source.connected ? 'normal' : 'abnormal'
}

export function sourceStateLabel(state: SourceState): string {
  return { normal: '正常', abnormal: '异常', unreported: '未报告' }[state]
}

export function sourceChannelLabel(channel: SourceStatus['channel']): string {
  return { transport: '连接通道', ws: '实时源', http: 'HTTP 补偿', unknown: '其他' }[channel]
}

export function sourceDisplayName(source: SourceStatus): string {
  return sourceName(source.logical_source)
}

const CHANGE_FIELD_LABELS: Record<string, string> = {
  magnitude: '震级',
  depth_km: '深度',
  epicenter: '震中位置',
  hypocenter: '震中名称',
  status: '事件状态',
}

export function revisionChangeLines(changes: Record<string, any>): string[] {
  return Object.entries(changes).map(([field, change]) => {
    const label = CHANGE_FIELD_LABELS[field] ?? field
    if (field === 'epicenter') return `${label}：移动 ${change.moved_km ?? '—'} 公里`
    const from = field === 'status' ? eventStatusLabel(String(change.from)) : (change.from ?? '—')
    const to = field === 'status' ? eventStatusLabel(String(change.to)) : (change.to ?? '—')
    const unit = field === 'depth_km' ? ' 公里' : ''
    return `${label}：${from}${unit} → ${to}${unit}`
  })
}
