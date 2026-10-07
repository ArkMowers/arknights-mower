import { describe, expect, it } from 'vitest'
import {
  goalSelected,
  selectedRecommendation,
  sumGrowthStatistics,
  selectedLevelGoal
} from './growthPlanning'

describe('养成规划', () => {
  it('星级统计只累加勾选类别，全部取消显示零', () => {
    const data = { 6: { elite2: 10, modules: 8 }, 5: { elite2: 7, modules: 2 } }
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
