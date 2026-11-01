export const maintenance_expression = 'op_data.major_maintenance_remaining_hours()'
export const default_maintenance_hours = 0.5
export const maintenance_duration_options = [
  { label: '不限', value: '' },
  ...['>', '>=', '<', '<=', '==', '!='].map((operator) => ({ label: operator, value: operator }))
]

export function maintenance_duration_expression(operator = '', hours = 6) {
  return operator
    ? `op_data.major_maintenance_remaining_hours('${operator}', ${hours})`
    : maintenance_expression
}

export function parse_maintenance_expression(expression) {
  if (expression === maintenance_expression) return { operator: '', hours: 6 }
  if (typeof expression !== 'string') return null
  const match = expression.match(
    /^op_data\.major_maintenance_remaining_hours\(\s*['"]([<>=!]=?)['"]\s*,\s*(\d+(?:\.\d*)?|\.\d+)(?:([eE][+-]?\d+))?\s*\)$/
  )
  if (!match || !maintenance_duration_options.some(({ value }) => value === match[1])) return null
  const hours = Number(match[2] + (match[3] || ''))
  return Number.isFinite(hours) ? { operator: match[1], hours } : null
}

export function maintenance_trigger(
  hours = default_maintenance_hours,
  duration_operator = '',
  duration_hours = 6
) {
  return {
    left: maintenance_duration_expression(duration_operator, duration_hours),
    operator: '<=',
    right: String(hours)
  }
}

export function parse_maintenance_trigger(trigger) {
  if (
    !parse_maintenance_expression(trigger.left) ||
    trigger.operator !== '<=' ||
    typeof trigger.right !== 'string' ||
    !trigger.right.trim()
  ) {
    return null
  }
  const hours = Number(trigger.right)
  return Number.isFinite(hours) && hours >= 0 ? hours : null
}
