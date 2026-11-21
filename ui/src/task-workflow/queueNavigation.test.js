import { describe, expect, it } from 'vitest'
import { getEditorQueue, getTaskEditor } from './queueNavigation'

describe('runtime queue configuration navigation', () => {
  it.each([
    ['run_order', 'runorder'],
    ['shifit_off', 'base'],
    ['shifit_on', 'base'],
    ['exhaust_on', 'base'],
    ['菲亚梅塔', 'base'],
    ['宿舍补位', 'base'],
    ['Impart', 'clue'],
    ['maa_Mall', 'credit'],
    ['recruit', 'recruit'],
    ['skland', 'skland'],
    ['技能专精', 'training'],
    ['换协助位', 'training'],
    ['仓库扫描', 'depot'],
    ['加工材料', 'workshop']
  ])('links backend type %s to %s regardless of the display name', (value, editorId) => {
    expect(
      getTaskEditor({ type: { _value_: value, display_value: '其他名称' }, display_name: '自定义' })
    ).toBe(editorId)
  })

  it('supports enum names, public values and legacy display labels', () => {
    expect(getTaskEditor({ type: { _name_: 'RUN_ORDER' } })).toBe('runorder')
    expect(getTaskEditor({ type: { value: 'recruit' } })).toBe('recruit')
    expect(getTaskEditor({ type: { display_value: '技能专精' } })).toBe('training')
    expect(getTaskEditor({ type: { display_value: '无人机加速' } })).toBe('drone')
  })

  it('distinguishes dormitory observations from refreshing run order time', () => {
    expect(getTaskEditor({ type: { _value_: '强制刷新任务时间' } })).toBe('runorder')
    expect(
      getTaskEditor({
        type: { _value_: '强制刷新任务时间' },
        recovery_observation_rooms: ['dormitory_1']
      })
    ).toBe('base')
  })

  it('links untyped room assignments without guessing an editor for unknown tasks', () => {
    expect(getTaskEditor({ plan: { room_1_1: ['能天使'] } })).toBe('base')
    expect(getTaskEditor({ type: { _value_: '' }, plan: { room_1_1: ['能天使'] } })).toBe('base')
    expect(getTaskEditor({ type: { _value_: 'future_type', display_value: '公招' } })).toBeNull()
    expect(getTaskEditor({ type: { display_value: '分解所有重复家具' } })).toBeNull()
    expect(getTaskEditor({ display_name: '公开招募', plan: {} })).toBeNull()
  })

  it('keeps backend times, order and task references for matching queue entries', () => {
    const first = Object.freeze({ type: { _value_: 'run_order' }, time: '2026-10-20T11:30:00' })
    const second = Object.freeze({ type: { _value_: 'recruit' }, time: '2026-10-20T10:00:00' })
    const third = Object.freeze({ type: { _value_: 'run_order' }, time: '2026-10-20T12:00:00' })
    const queue = Object.freeze([first, second, third])
    const selected = getEditorQueue(queue, 'runorder')
    expect(selected).toEqual([first, third])
    expect(selected[0]).toBe(first)
    expect(selected[1]).toBe(third)
    expect(queue).toEqual([first, second, third])
    expect(getEditorQueue(queue, 'mail')).toEqual([])
  })
})
