import { describe, expect, it } from 'vitest'

import {
  group_mood_expression,
  group_mood_mode_options,
  parse_group_mood_expression
} from './trigger_group.js'

describe('绑组最低心情副表表达式', () => {
  it('生成并解析最低心情及组名', () => {
    const expression = group_mood_expression('鸿雪组')
    expect(expression).toBe('op_data.group_min_mood("鸿雪组")')
    expect(parse_group_mood_expression(expression)).toEqual({ group: '鸿雪组', mode: 'min' })
  })

  it.each(group_mood_mode_options)('生成并解析 $label', ({ value, method }) => {
    const expression = group_mood_expression('鸿雪组', value)
    expect(expression).toBe(`op_data.${method}("鸿雪组")`)
    expect(parse_group_mood_expression(expression)).toEqual({ group: '鸿雪组', mode: value })
  })

  it('正确转义组名中的引号', () => {
    const expression = group_mood_expression('A"组')
    expect(parse_group_mood_expression(expression)).toEqual({ group: 'A"组', mode: 'min' })
  })

  it('忽略自定义表达式', () => {
    expect(parse_group_mood_expression("op_data.group_min_mood('鸿雪组') + 1")).toBeUndefined()
  })
})
