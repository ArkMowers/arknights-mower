export const group_mood_mode_options = [
  { label: '最低心情', value: 'min', method: 'group_min_mood' },
  { label: '最高心情', value: 'max', method: 'group_max_mood' }
]

const mode_by_value = Object.fromEntries(
  group_mood_mode_options.map((option) => [option.value, option])
)

export function group_mood_expression(group, mode = 'min') {
  const method = mode_by_value[mode]?.method || mode_by_value.min.method
  return `op_data.${method}(${JSON.stringify(group)})`
}

export function parse_group_mood_expression(expression) {
  for (const option of group_mood_mode_options) {
    const prefix = `op_data.${option.method}(`
    if (!expression.startsWith(prefix) || !expression.endsWith(')')) continue
    try {
      const group = JSON.parse(expression.slice(prefix.length, -1))
      if (typeof group == 'string') return { group, mode: option.value }
    } catch {
      return undefined
    }
  }
  return undefined
}
