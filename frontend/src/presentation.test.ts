import { describe, expect, it } from 'vitest'
import { NO_CORE_CHANGES_TEXT, hasRevisionChanges } from './revisions'
import { formatChinaTime } from './time'
import { estimationText } from './estimation'
import type { Impact } from './types'
import { deliveryKindLabel, deliveryStatusLabel, eventStatusLabel, revisionChangeLines, sourceName, sourceState } from './presentation'

describe('presentation helpers', () => {
  it('renders database UTC timestamps as China Standard Time', () => {
    expect(formatChinaTime('2026-07-12T07:41:08')).toBe(
      '2026-07-12 15:41:08（北京时间）',
    )
    expect(formatChinaTime('2026-07-12T07:41:08+00:00')).toBe(
      '2026-07-12 15:41:08（北京时间）',
    )
  })

  it('recognizes empty revision changes', () => {
    expect(hasRevisionChanges({})).toBe(false)
    expect(hasRevisionChanges({ magnitude: { from: 4, to: 4.5 } })).toBe(true)
    expect(NO_CORE_CHANGES_TEXT).toBe('没有实质变化：新增数据源，无核心参数变化')
  })

  it('distinguishes intensity estimation states', () => {
    const impact = {
      estimated_intensity: null,
      intensity_level: null,
      estimation_status: 'out_of_range',
    } as Impact
    expect(estimationText(impact)).toBe('超出模型适用范围')
    impact.estimation_status = 'insufficient_data'
    expect(estimationText(impact)).toBe('数据不足，暂无法估算')
    impact.estimation_status = 'failed'
    expect(estimationText(impact)).toBe('估算失败')
    impact.estimation_status = 'estimated'
    impact.estimated_intensity = 3.24
    impact.intensity_level = 4
    expect(estimationText(impact)).toBe('预计烈度 3.2（4度）')
  })

  it('renders stable backend values as Chinese labels', () => {
    expect(sourceName('cenc_eew')).toBe('中国地震台网预警（cenc_eew）')
    expect(eventStatusLabel('preliminary')).toBe('初报')
    expect(deliveryKindLabel('earthquake.update')).toBe('地震更新')
    expect(deliveryStatusLabel('delivered')).toBe('已送达')
    expect(revisionChangeLines({ status: { from: 'preliminary', to: 'final' } })).toEqual(['事件状态：初报 → 正式报'])
  })

  it('distinguishes unreported sources from failures', () => {
    const base = { source: 'ws:cenc_eew', channel: 'ws', logical_source: 'cenc_eew', display_name: '', connected: true, last_message_at: null, last_heartbeat_at: null, last_error: null } as const
    expect(sourceState(base)).toBe('unreported')
    expect(sourceState({ ...base, connected: false, last_error: 'timeout' })).toBe('abnormal')
    expect(sourceState({ ...base, last_message_at: '2026-07-12T00:00:00Z' })).toBe('normal')
  })
})
