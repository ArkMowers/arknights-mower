import { describe, expect, it } from 'vitest'

import {
  buildStageOptions,
  buildTableStageOptions,
  isStageAvailableOnWeekday,
  mergeTableStageOrder,
  normalizeCreatedStage,
  reorderWeeklyPlanStages,
  setStageForWeekday,
  splitStageInventoryLabel
} from './maa_weekly_plan.js'

describe('刷理智周计划双视图同步', () => {
  it('表格动态包含资源包活动关卡，并保留列表中的自定义关卡', () => {
    const options = buildTableStageOptions(
      [{ value: 'ACT-9', label: 'ACT-9:材料', code: 'ACT-9' }],
      [{ weekday: '周一', stage: ['CUSTOM-1', 'ACT-9'] }]
    )

    expect(options.find((option) => option.value === 'ACT-9')).toMatchObject({
      value: 'ACT-9',
      label: 'ACT-9:材料'
    })
    expect(options[0].value).toBe('Annihilation')
    expect(options[1].value).toBe('ACT-9')
    expect(options.map((option) => option.value)).toContain('CUSTOM-1')
    expect(options.filter((option) => option.value === 'ACT-9')).toHaveLength(1)
  })

  it('列表和表格默认将当期剿灭排在活动关卡之前', () => {
    const activity = [{ value: 'ACT-9', label: 'ACT-9:材料' }]
    expect(
      buildStageOptions(activity)
        .slice(0, 2)
        .map((option) => option.value)
    ).toEqual(['Annihilation', 'ACT-9'])
    expect(
      buildTableStageOptions(activity)
        .slice(0, 2)
        .map((option) => option.value)
    ).toEqual(['Annihilation', 'ACT-9'])
  })

  it('新活动插入当期剿灭之后，同时保留用户已有拖动顺序', () => {
    const options = buildTableStageOptions([{ value: 'ACT-9', label: 'ACT-9:材料' }])
    const ordered = mergeTableStageOrder(options, ['Annihilation', '1-7', 'CE-6'], ['ACT-9'])
    expect(ordered.slice(0, 4).map((option) => option.value)).toEqual([
      'Annihilation',
      'ACT-9',
      '1-7',
      'CE-6'
    ])

    const userOrdered = mergeTableStageOrder(options, ['1-7', 'Annihilation', 'ACT-9'], ['ACT-9'])
    expect(userOrdered.slice(0, 3).map((option) => option.value)).toEqual([
      '1-7',
      'Annihilation',
      'ACT-9'
    ])
  })

  it('点击表格格子直接更新列表计划使用的同一份 stage 数组', () => {
    const plan = [{ weekday: '周一', stage: ['1-7'] }]
    setStageForWeekday(plan, '周一', 'ACT-9', true, ['ACT-9', '1-7'])
    expect(plan[0].stage).toEqual(['ACT-9', '1-7'])

    setStageForWeekday(plan, '周一', 'ACT-9', false, ['ACT-9', '1-7'])
    expect(plan[0].stage).toEqual(['1-7'])
  })

  it('表格沿用资源关开放日，并允许活动与自定义关每天配置', () => {
    expect(isStageAvailableOnWeekday('CE-6', '周一')).toBe(false)
    expect(isStageAvailableOnWeekday('CE-6', '周二')).toBe(true)
    expect(isStageAvailableOnWeekday('ACT-9', '周一')).toBe(true)
  })

  it('兼容旧表格使用的磨难难度输入', () => {
    expect(normalizeCreatedStage('14-21磨难')).toBe('14-21-HARD')
    expect(normalizeCreatedStage('14-21困难')).toBe('14-21-HARD')
  })

  it('用户调整表格顺序后，同步更新每天列表计划的关卡优先级', () => {
    const plan = [
      { weekday: '周一', stage: ['1-7', 'ACT-9'] },
      { weekday: '周二', stage: ['CUSTOM-1', 'ACT-9'] }
    ]

    reorderWeeklyPlanStages(plan, ['ACT-9', '1-7', 'CUSTOM-1'])

    expect(plan[0].stage).toEqual(['ACT-9', '1-7'])
    expect(plan[1].stage).toEqual(['ACT-9', 'CUSTOM-1'])
  })

  it('将活动关卡名称和库存拆分为固定的两行', () => {
    expect(splitStageInventoryLabel('SR-6:褐素纤维(库存:100)')).toEqual({
      stageLabel: 'SR-6:褐素纤维',
      inventoryLabel: '(库存:100)'
    })
    expect(splitStageInventoryLabel('SR-6:褐素纤维（库存：100）')).toEqual({
      stageLabel: 'SR-6:褐素纤维',
      inventoryLabel: '（库存：100）'
    })
    expect(splitStageInventoryLabel('当期剿灭')).toEqual({
      stageLabel: '当期剿灭',
      inventoryLabel: ''
    })
  })
})
