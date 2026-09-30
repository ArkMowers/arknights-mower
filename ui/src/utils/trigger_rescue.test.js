import { describe, expect, it } from 'vitest'
import {
  rescue_condition_expression,
  rescue_condition_help,
  rescue_trigger
} from './trigger_rescue'

describe('救急副表条件', () => {
  it('creates a normal boolean backup condition', () => {
    expect(rescue_trigger()).toEqual({
      left: 'op_data.rescue_needed()',
      operator: '==',
      right: 'True'
    })
    expect(rescue_trigger().left).toBe(rescue_condition_expression)
  })

  it('keeps independently edited conditions isolated', () => {
    const edited = rescue_trigger()
    edited.right = 'False'
    expect(rescue_trigger().right).toBe('True')
  })

  it('states the priority and zero-mood assignment rules', () => {
    expect(rescue_condition_help).toContain('主表主班与主表高优替补')
    expect(rescue_condition_help).toContain('无需填写替班')
    expect(rescue_condition_help).toContain('不清空宿舍')
    expect(rescue_condition_help).toContain('多数主班达到主表心情上限')
  })
})
