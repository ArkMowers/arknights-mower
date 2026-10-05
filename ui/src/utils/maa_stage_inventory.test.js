import { describe, expect, it } from 'vitest'

import {
  applyChipLimitPreset,
  createLimitRule,
  createRatioMember,
  evaluateLimitRule,
  inventoryCount,
  previewInventorySelection,
  selectRatioMember
} from './maa_stage_inventory.js'

const chipStageOptions = [
  ['PR-A', ['323', '重装'], ['326', '医疗']],
  ['PR-B', ['324', '狙击'], ['325', '术师']],
  ['PR-C', ['321', '先锋'], ['327', '辅助']],
  ['PR-D', ['322', '近卫'], ['328', '特种']]
].flatMap(([stage, ...materials]) =>
  [1, 2].map((tier) => ({
    value: `${stage}-${tier}`,
    materials: materials.map(([id, name]) => ({
      id: `${id}${tier}`,
      name: `${name}${tier === 1 ? '芯片' : '芯片组'}`
    }))
  }))
)

describe('一键芯片上限', () => {
  it('绑定全部八个芯片关卡的两种掉落，小芯片 5、大芯片 8', () => {
    const rules = applyChipLimitPreset([], chipStageOptions)
    expect(rules.map((rule) => rule.stage)).toEqual(chipStageOptions.map((option) => option.value))
    for (const [index, rule] of rules.entries()) {
      const limit = rule.stage.endsWith('-1') ? 5 : 8
      expect(rule).toEqual({
        stage: chipStageOptions[index].value,
        operator: 'and',
        enabled: true,
        items: chipStageOptions[index].materials.map((item) => ({
          item_id: item.id,
          item_name: item.name,
          limit
        }))
      })
      const [first, second] = rule.items
      expect(
        evaluateLimitRule(rule, { [first.item_id]: limit, [second.item_id]: limit - 1 }).reached
      ).toBe(false)
      expect(
        evaluateLimitRule(rule, { [first.item_id]: limit, [second.item_id]: limit }).reached
      ).toBe(true)
    }
  })

  it('替换已有芯片规则并启用，重复点击不增加规则且保留其他关卡', () => {
    const other = createLimitRule({ value: '1-7', materials: [{ id: '30012', name: '固源岩' }] })
    other.items[0].limit = 100
    const existing = { stage: 'PR-A-1', enabled: false, operator: 'or', items: [] }
    const original = [other, existing, { ...existing }]
    const before = structuredClone(original)
    const rules = applyChipLimitPreset(original, chipStageOptions)
    expect(rules).toHaveLength(9)
    expect(rules[0]).toBe(other)
    expect(original).toEqual(before)
    expect(applyChipLimitPreset(rules, chipStageOptions)).toEqual(rules)
  })

  it('忽略其他关卡且只影响执行计划中的芯片关卡', () => {
    const options = [...chipStageOptions, { value: 'PR-A-3' }, { value: '1-7' }]
    const rules = applyChipLimitPreset([], options)
    expect(rules).toHaveLength(8)
    const plan = ['PR-A-1', '1-7']
    expect(previewInventorySelection(plan, rules, [], { 3231: 5, 3261: 5 }).stages).toEqual(['1-7'])
    expect(plan).toEqual(['PR-A-1', '1-7'])
    expect(applyChipLimitPreset(rules, [])).toEqual(rules)
  })
})

describe('刷理智库存选关', () => {
  it('新绑定的比例成员默认比例为 0', () => {
    expect(createRatioMember()).toEqual({
      stage: '',
      item_id: '',
      item_name: '',
      ratio: 0
    })
  })

  it('绑定关卡时载入默认常规掉落且上限为 0', () => {
    expect(
      createLimitRule({
        value: 'PR-A-2',
        materials: [
          { id: '3232', name: '重装芯片组' },
          { id: '3262', name: '医疗芯片组' }
        ]
      })
    ).toMatchObject({
      stage: 'PR-A-2',
      operator: 'and',
      items: [
        { item_id: '3232', limit: 0 },
        { item_id: '3262', limit: 0 }
      ]
    })
  })

  it('上限 0 不参与判断，多物品默认全部达到才跳过', () => {
    const result = evaluateLimitRule(
      {
        enabled: true,
        operator: 'and',
        items: [
          { item_id: 'A', limit: 100 },
          { item_id: 'B', limit: 50 },
          { item_id: 'C', limit: 0 }
        ]
      },
      { A: 100, B: 49, C: 999 }
    )
    expect(result.active).toBe(true)
    expect(result.reached).toBe(false)
    expect(result.conditions).toHaveLength(2)
  })

  it('或规则任一物品达到上限即跳过', () => {
    expect(
      evaluateLimitRule(
        {
          enabled: true,
          operator: 'or',
          items: [
            { item_id: 'A', limit: 100 },
            { item_id: 'B', limit: 50 }
          ]
        },
        { A: 100, B: 0 }
      ).reached
    ).toBe(true)
  })

  it('比例为 0 的成员不参与，并选择库存除以比例最小的关卡', () => {
    const selected = selectRatioMember(
      {
        enabled: true,
        members: [
          { stage: 'A-1', item_id: 'A', ratio: 2 },
          { stage: 'B-1', item_id: 'B', ratio: 1 },
          { stage: 'C-1', item_id: 'C', ratio: 0 }
        ]
      },
      { A: 100, B: 60, C: 0 }
    )
    expect(selected.member.stage).toBe('A-1')
  })

  it('比例得分相同时按周计划顺序选择关卡', () => {
    const result = previewInventorySelection(
      ['B-1', 'A-1'],
      [],
      [
        {
          enabled: true,
          members: [
            { stage: 'A-1', item_id: 'A', ratio: 1 },
            { stage: 'B-1', item_id: 'B', ratio: 1 }
          ]
        }
      ],
      { A: 10, B: 10 }
    )
    expect(result.stages).toEqual(['B-1'])
    expect(result.ratioDecisions[0].selected).toBe('B-1')
  })

  it('物品名称通过别名读取真实库存 ID', () => {
    const itemAliases = new Map([['固源岩', '30012']])
    expect(inventoryCount({ item_id: '固源岩' }, { 30012: 100 }, itemAliases)).toBe(100)
    expect(inventoryCount({ item_name: '固源岩' }, { 30012: 100 }, itemAliases)).toBe(100)

    for (const item of [{ item_id: '固源岩' }, { item_name: '固源岩' }]) {
      const result = previewInventorySelection(
        ['1-7', 'CE-6'],
        [{ stage: '1-7', enabled: true, items: [{ ...item, limit: 100 }] }],
        [],
        { 30012: 100 },
        itemAliases
      )
      expect(result.stages).toEqual(['CE-6'])
      expect(result.limitSkipped).toEqual(['1-7'])
    }
  })

  it('上限优先，达到上限的关卡不参与比例计算', () => {
    const result = previewInventorySelection(
      ['A-1', 'B-1', '1-7'],
      [{ stage: 'A-1', enabled: true, items: [{ item_id: 'A', limit: 100 }] }],
      [
        {
          enabled: true,
          members: [
            { stage: 'A-1', item_id: 'A', ratio: 1 },
            { stage: 'B-1', item_id: 'B', ratio: 1 }
          ]
        }
      ],
      { A: 100, B: 999 }
    )
    expect(result.stages).toEqual(['B-1', '1-7'])
    expect(result.limitSkipped).toEqual(['A-1'])
    expect(result.ratioDecisions).toEqual([])
  })

  it('全部关卡达到上限时恢复原计划', () => {
    const result = previewInventorySelection(
      ['A-1', 'B-1'],
      [
        { stage: 'A-1', enabled: true, items: [{ item_id: 'A', limit: 1 }] },
        { stage: 'B-1', enabled: true, items: [{ item_id: 'B', limit: 1 }] }
      ],
      [],
      { A: 1, B: 1 }
    )
    expect(result.limitFallback).toBe(true)
    expect(result.stages).toEqual(['A-1', 'B-1'])
  })

  it('库存规则不会把周计划未选择的关卡加入执行列表', () => {
    const result = previewInventorySelection(
      ['1-7'],
      [{ stage: 'ACT-A', enabled: true, items: [{ item_id: 'A', limit: 10 }] }],
      [
        {
          enabled: true,
          members: [
            { stage: 'ACT-A', item_id: 'A', ratio: 1 },
            { stage: 'ACT-B', item_id: 'B', ratio: 1 }
          ]
        }
      ],
      { A: 0, B: 0 }
    )
    expect(result.stages).toEqual(['1-7'])
    expect(result.ratioDecisions).toEqual([])
  })
})
