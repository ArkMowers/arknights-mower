import { describe, expect, it } from 'vitest'

import {
  apply_operator_replace,
  collect_plan_operators,
  swapSubstrings,
  swapTask,
  updateTrigger
} from './plan_edit.js'

const empty_conf = {
  rest_in_full: [],
  exhaust_require: [],
  workaholic: [],
  resting_priority: [],
  refresh_trading: [],
  refresh_drained: [],
  free_blacklist: [],
  ope_resting_priority: []
}

function make_state() {
  return {
    main_plan: {
      room_1_1: {
        name: '贸易站',
        plans: [
          { agent: '能天使', group: '', replacement: ['德克萨斯'] },
          { agent: '德克萨斯', group: '', replacement: [] }
        ]
      }
    },
    main_conf: {
      ...empty_conf,
      rest_in_full: ['能天使', '德克萨斯'],
      workaholic: ['能天使'],
      free_blacklist: ['德克萨斯']
    },
    backup_plans: [
      {
        name: 'plan1',
        plan: {
          room_1_1: {
            name: '制造站',
            plans: [{ agent: '能天使', group: '', replacement: [] }]
          }
        },
        conf: { ...empty_conf, rest_in_full: ['能天使'] },
        trigger: {
          left: "op_data.operators['能天使'].is_working()",
          operator: 'and',
          right: { left: '', operator: '', right: "op_data.operators['德克萨斯'].current_mood()" }
        },
        task: { room_1_1: ['能天使', '德克萨斯'], train: [] }
      }
    ]
  }
}

describe('apply_operator_replace 覆盖范围', () => {
  it('替换主表 agent + replacement', () => {
    const state = make_state()
    apply_operator_replace(state, '能天使', '风笛')
    expect(state.main_plan.room_1_1.plans[0].agent).toBe('风笛')
    expect(state.main_plan.room_1_1.plans[0].replacement).toEqual(['德克萨斯'])
    expect(state.main_plan.room_1_1.plans[1].agent).toBe('德克萨斯')
  })

  it('替换主表 conf 8 处', () => {
    const state = make_state()
    apply_operator_replace(state, '能天使', '风笛')
    expect(state.main_conf.rest_in_full).toEqual(['风笛', '德克萨斯'])
    expect(state.main_conf.workaholic).toEqual(['风笛'])
    expect(state.main_conf.free_blacklist).toEqual(['德克萨斯'])
    expect(state.main_conf.exhaust_require).toEqual([])
  })

  it('替换副表 plan + conf', () => {
    const state = make_state()
    apply_operator_replace(state, '能天使', '风笛')
    const backup = state.backup_plans[0]
    expect(backup.plan.room_1_1.plans[0].agent).toBe('风笛')
    expect(backup.conf.rest_in_full).toEqual(['风笛'])
  })

  it('替换副表 trigger（含嵌套表达式）', () => {
    const state = make_state()
    apply_operator_replace(state, '能天使', '风笛')
    const trigger = state.backup_plans[0].trigger
    expect(trigger.left).toBe("op_data.operators['风笛'].is_working()")
    expect(trigger.right.right).toBe("op_data.operators['德克萨斯'].current_mood()")
  })

  it('替换副表 task 数组', () => {
    const state = make_state()
    apply_operator_replace(state, '能天使', '风笛')
    expect(state.backup_plans[0].task.room_1_1).toEqual(['风笛', '德克萨斯'])
  })

  it('单向替换：target 若出现在表达式里保持不变', () => {
    const state = make_state()
    state.backup_plans[0].trigger.left = "op_data.operators['风笛'].is_resting()"
    apply_operator_replace(state, '能天使', '风笛')
    expect(state.backup_plans[0].trigger.left).toBe("op_data.operators['风笛'].is_resting()")
  })

  it('子串碰撞：source 是更长干员名前缀时不误伤', () => {
    // 阿 ⊂ 阿米娅；按引号边界替换 ['阿'] 不得命中 ['阿米娅']
    const state = make_state()
    state.backup_plans[0].trigger.left = "op_data.operators['阿米娅'].is_resting()"
    apply_operator_replace(state, '阿', '风笛')
    expect(state.backup_plans[0].trigger.left).toBe("op_data.operators['阿米娅'].is_resting()")
    expect(state.backup_plans[0].trigger.left).not.toContain('风笛米娅')
  })

  it('backup 缺 conf/task 不崩', () => {
    const state = make_state()
    state.backup_plans[0].conf = undefined
    state.backup_plans[0].task = undefined
    expect(() => apply_operator_replace(state, '能天使', '风笛')).not.toThrow()
  })
})

describe('collect_plan_operators', () => {
  it('收集主表+副表的 agent/replacement/conf/task 干员并去重', () => {
    const ops = collect_plan_operators(make_state())
    expect(ops).toEqual(expect.arrayContaining(['能天使', '德克萨斯']))
    expect(new Set(ops).size).toBe(ops.length)
    expect(ops).not.toContain('风笛')
  })

  it('source 下拉只含排班里出现过的干员', () => {
    const ops = collect_plan_operators(make_state())
    expect(ops).toEqual(['能天使', '德克萨斯'])
  })
})

describe('复用自 PlanEditor 的换位工具', () => {
  it('swapSubstrings 双向交换', () => {
    expect(swapSubstrings('a-b-a-c', 'a', 'b')).toBe('b-a-b-c')
  })

  it('swapTask 交换对象键', () => {
    const tasks = { a: 1, b: 2 }
    swapTask(tasks, 'a', 'b')
    expect(tasks).toEqual({ a: 2, b: 1 })
  })

  it('updateTrigger 递归替换嵌套表达式', () => {
    const trigger = {
      left: '能天使',
      operator: 'and',
      right: { left: '', operator: '', right: '能天使' }
    }
    updateTrigger(trigger, '能天使', '德克萨斯')
    expect(trigger.left).toBe('德克萨斯')
    expect(trigger.right.right).toBe('德克萨斯')
  })
})
