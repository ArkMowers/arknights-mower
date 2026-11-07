import { describe, expect, it } from 'vitest'
import {
  goalSelected,
  selectedRecommendation,
  sumGrowthStatistics,
  selectedLevelGoal,
  operatorLevelGoals,
  isGrowthOperatorIdle
} from './growthPlanning'

describe('养成规划', () => {
  it('星级统计只累加勾选类别，全部取消显示零', () => {
    const data = { 6: { elite2: 10, modules: 8 }, 5: { elite2: 7, modules: 2 }, 4: { modules: 0 } }
    expect(sumGrowthStatistics(data, [6]).elite2).toBe(10)
    expect(sumGrowthStatistics(data, [6, 5, 4]).modules).toBe(10)
    expect(sumGrowthStatistics(data, []).elite2).toBe(0)
  })
  it('切换目标选择对应材料和时间而不修改推荐源数据', () => {
    const rec = {
      skill_index: 0,
      targets: { 1: { total_time: 8, material_summary: { materials: [1] } }, 2: { total_time: 24 } }
    }
    expect(selectedRecommendation(rec, 1)).toMatchObject({
      total_time: 8,
      target_level: 1,
      skill_index: 0
    })
    expect(selectedRecommendation(rec, 2).total_time).toBe(24)
    expect(rec.target_level).toBeUndefined()
  })
  it('模组计划按干员与模组同时匹配', () => {
    const goals = [{ char_id: 'a', module_id: 'x' }]
    expect(goalSelected(goals, 'a', 'x')).toBe(true)
    expect(goalSelected(goals, 'b', 'x')).toBe(false)
  })
})

describe('等级前置互斥', () => {
  const op = {
    char_id: 'a',
    elite: 0,
    level: 1,
    modules: [{ id: 'm', elite: 2, level: 60, current_level: 0 }]
  }
  it('技能自动选择精二一级，模组提高到模组等级', () => {
    expect(selectedLevelGoal(op, true, [])).toBe('elite2')
    expect(selectedLevelGoal(op, true, [{ char_id: 'a', module_id: 'm' }])).toBe('elite2_module')
  })
  it('满练保留更高目标，已满足的前置不再选择', () => {
    expect(
      selectedLevelGoal(op, true, [
        { char_id: 'a', module_id: 'elite2_max' },
        { char_id: 'a', module_id: 'm' }
      ])
    ).toBe('elite2_max')
    expect(
      selectedLevelGoal({ ...op, elite: 2, level: 60 }, true, [{ char_id: 'a', module_id: 'm' }])
    ).toBeNull()
  })
})

describe('低星等级目标与历史', () => {
  const op = {
    char_id: 'three',
    rarity: 3,
    elite: 0,
    level: 40,
    max_phase: 1,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级' },
      { id: 'level_max', elite: 1, level: 55, label: '精一 55 级（满练）' }
    ]
  }
  it('三星基础7选择最低精一，更高满练目标优先', () => {
    expect(selectedLevelGoal(op, false, [{ char_id: 'three', module_id: 'skill7' }])).toBe('elite1')
    expect(
      selectedLevelGoal(op, false, [
        { char_id: 'three', module_id: 'skill7' },
        { char_id: 'three', module_id: 'level_max' }
      ])
    ).toBe('level_max')
    expect(
      selectedLevelGoal({ ...op, elite: 1, level: 1 }, false, [
        { char_id: 'three', module_id: 'skill7' }
      ])
    ).toBeNull()
  })
  it('缺低星的旧快照对每个指标都不补零', () => {
    const data = { 6: { elite2: 10, modules: 8, max_level: 2 } }
    expect(sumGrowthStatistics(data, [6, 3]).elite2).toBeNull()
    expect(sumGrowthStatistics(data, [6, 3]).modules).toBeNull()
    expect(sumGrowthStatistics(data, [6, 3]).max_level).toBeNull()
    expect(sumGrowthStatistics(data, []).max_level).toBe(0)
  })
})

it('低星只提供真实等级节点，满练不会虚构精二', () => {
  const op = {
    rarity: 2,
    level_goals: [{ id: 'level_max', elite: 0, level: 30, label: '精零 30 级' }]
  }
  expect(operatorLevelGoals(op)).toEqual([
    { id: 'level_max', key: 'level_max', elite: 0, level: 30, label: '精零 30 级' }
  ])
})

it('空闲依据基地占用，独立于干员养成计划', () => {
  const none = new Set()
  expect(isGrowthOperatorIdle('甲', none, none, none, [])).toBe(true)
  expect(isGrowthOperatorIdle('甲', new Set(['甲']), none, none, [])).toBe(false)
  expect(isGrowthOperatorIdle('甲', none, new Set(['甲']), none, [])).toBe(false)
  expect(isGrowthOperatorIdle('甲', none, none, new Set(['甲']), [])).toBe(false)
  expect(isGrowthOperatorIdle('甲', none, none, none, ['甲'])).toBe(false)
})
