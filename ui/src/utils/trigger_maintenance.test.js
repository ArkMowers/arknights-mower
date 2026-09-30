import { describe, expect, it } from 'vitest'
import { maintenance_trigger, parse_maintenance_trigger } from './trigger_maintenance'

describe('停服大更新定时条件', () => {
  it('defaults to half an hour with the existing expression schema', () => {
    expect(maintenance_trigger()).toEqual({
      left: 'op_data.major_maintenance_remaining_hours()',
      operator: '<=',
      right: '0.5'
    })
  })

  it('reads an existing threshold without changing its timing', () => {
    expect(parse_maintenance_trigger(maintenance_trigger(12))).toBe(12)
    expect(parse_maintenance_trigger(maintenance_trigger(0))).toBe(0)
  })

  it('leaves other comparisons and nonnumeric expressions in the normal editor', () => {
    for (const trigger of [
      { ...maintenance_trigger(), operator: '>' },
      { ...maintenance_trigger(), left: '1' },
      { ...maintenance_trigger(), right: '' },
      { ...maintenance_trigger(), right: '-1' },
      { ...maintenance_trigger(), right: 'Infinity' },
      { ...maintenance_trigger(), right: "op_data.group_min_mood('组')" }
    ]) {
      expect(parse_maintenance_trigger(trigger)).toBeNull()
    }
  })
})
