import type { Impact } from './types'

export const ESTIMATION_STATUS_LABELS: Record<Impact['estimation_status'], string> = {
  insufficient_data: '数据不足，暂无法估算',
  out_of_range: '超出模型适用范围',
  estimated: '预计烈度',
  failed: '估算失败',
}

export function estimationText(impact: Impact): string {
  if (impact.estimation_status === 'estimated' && impact.estimated_intensity != null) {
    return `预计烈度 ${impact.estimated_intensity.toFixed(1)}（${impact.intensity_level}度）`
  }
  return ESTIMATION_STATUS_LABELS[impact.estimation_status] ?? ESTIMATION_STATUS_LABELS.failed
}

