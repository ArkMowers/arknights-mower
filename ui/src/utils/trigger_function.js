export const function_options = [
  { label: 'max（最大值）', value: 'max' },
  { label: 'min（最小值）', value: 'min' },
  { label: 'sum（求和）', value: 'sum' },
  { label: 'any（任一成立）', value: 'any' },
  { label: 'all（全部成立）', value: 'all' },
  { label: 'abs（绝对值）', value: 'abs' }
]

export function expression_type(value) {
  if (typeof value === 'string') return 'string'
  return value?.function ? 'function' : 'expression'
}

export function new_expression(type) {
  if (type === 'string') return ''
  if (type === 'function') return { function: 'max', args: [''] }
  return { left: '', operator: '', right: '' }
}
