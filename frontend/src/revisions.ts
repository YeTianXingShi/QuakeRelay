export function hasRevisionChanges(changes: unknown): boolean {
  return Boolean(
    changes
    && typeof changes === 'object'
    && !Array.isArray(changes)
    && Object.keys(changes).length > 0,
  )
}

export const NO_CORE_CHANGES_TEXT = '没有实质变化：新增数据源，无核心参数变化'

