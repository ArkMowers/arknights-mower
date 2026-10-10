export const maintenance_expression = 'op_data.major_maintenance_remaining_hours()'
export const default_maintenance_hours = 0.5

export function maintenance_trigger(hours = default_maintenance_hours) {
  return { left: maintenance_expression, operator: '<=', right: String(hours) }
}

export function parse_maintenance_trigger(trigger) {
  if (
    trigger.left !== maintenance_expression ||
    trigger.operator !== '<=' ||
    typeof trigger.right !== 'string' ||
    !trigger.right.trim()
  ) {
    return null
  }
  const hours = Number(trigger.right)
  return Number.isFinite(hours) && hours >= 0 ? hours : null
}
