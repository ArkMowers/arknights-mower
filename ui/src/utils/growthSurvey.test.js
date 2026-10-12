import { describe, it, expect } from 'vitest'
import { defaultSurveyFilters, operatorSurvey, surveyRate, moduleSurveyField } from './growthSurvey'
const row = {
  own: 100,
  sampleSize: 1000,
  elite: { 0: 5, 1: 15, 2: 80 },
  skill1: { 0: 20, 3: 80 },
  skill2: { 0: 90, 3: 10 },
  modX: { 0: 10, 1: 30, 2: 20, 3: 40 },
  modD: { 0: 100 }
}
const op = {
  elite: 0,
  skill_levels: [0, 3],
  recommendations: [],
  modules: [
    { id: 'x', type: 'ABC-X', current_level: 0 },
    { id: 'd', type: 'ABC-D', current_level: 0 }
  ]
}
describe('公开大数据推荐', () => {
  it('以拥有者而非全样本为分母，模组累加1至3级', () => {
    expect(surveyRate(row, 'skill1', [3])).toBe(80)
    expect(surveyRate(row, 'modX', [1, 2, 3])).toBe(90)
    expect(surveyRate(row, 'elite', [1, 2])).toBe(95)
    expect(operatorSurvey(op, row, defaultSurveyFilters()).elite1).toBe(95)
  })
  it('缺失、空样本与未识别模组保持未知', () => {
    expect(surveyRate(null, 'elite', [2])).toBeNull()
    expect(surveyRate({ ...row, own: 0 }, 'elite', [2])).toBeNull()
    expect(surveyRate(row, 'modZ', [1])).toBeNull()
    expect(moduleSurveyField({ type: 'ABC-Z' })).toBeNull()
  })
  it('门槛只高亮匹配项目，不改变目标或隐藏干员', () => {
    const before = JSON.stringify(op)
    const result = operatorSurvey(op, row, { ...defaultSurveyFilters(), mastery: 80, module: 90 })
    expect(result.skillHighlights).toEqual([0])
    expect(result.moduleHighlights).toEqual(['x'])
    expect(result.visible).toBe(true)
    expect(JSON.stringify(op)).toBe(before)
  })
  it('同时勾选条件时只隐藏全部已满足的干员', () => {
    const filters = {
      ...defaultSurveyFilters(),
      mastery: 80,
      module: 80,
      elite2: 80,
      hideCompleted: true
    }
    expect(operatorSurvey(op, row, filters).visible).toBe(true)
    const done = {
      ...op,
      elite: 2,
      skill_levels: [3, 3],
      modules: [{ id: 'x', type: 'ABC-X', current_level: 1 }]
    }
    expect(operatorSurvey(done, row, filters).visible).toBe(false)
    expect(operatorSurvey({ ...done, skill_levels: [2, 3] }, row, filters).visible).toBe(true)
  })
  it('缺少统计时不把干员误判为已完成', () => {
    const filters = { ...defaultSurveyFilters(), mastery: 70, hideCompleted: true }
    expect(operatorSurvey(op, null, filters).visible).toBe(true)
    expect(operatorSurvey(op, null, filters).known).toBe(false)
    expect(operatorSurvey(op, { own: 100 }, filters).visible).toBe(true)
    expect(surveyRate({ own: 100, skill1: {} }, 'skill1', [3])).toBeNull()
    expect(operatorSurvey({ ...op, skill_levels: [] }, row, filters).visible).toBe(true)
    expect(operatorSurvey({ ...op, skill_levels: [undefined] }, row, filters).visible).toBe(true)
    expect(operatorSurvey(op, { ...row, skill1: { 3: 50 } }, filters).visible).toBe(true)
  })
  it('未启用门槛时隐藏完成开关不清空列表', () => {
    expect(
      operatorSurvey(op, row, { ...defaultSurveyFilters(), hideCompleted: true }).visible
    ).toBe(true)
  })
})

it('低星已知不支持的推荐维度不生成不可能目标，也不视为未知进度', () => {
  const filters = {
    ...defaultSurveyFilters(),
    mastery: 0.325,
    module: 0.325,
    elite2: 0.325,
    hideCompleted: true
  }
  const op = {
    rarity: 3,
    max_phase: 1,
    elite: 0,
    skill_levels: [0],
    recommendations: [],
    modules: []
  }
  const row = { own: 100, skill1: { 0: 100 }, elite: { 0: 50, 1: 50 }, modX: { 0: 100 } }
  const result = operatorSurvey(op, row, filters)
  expect(result.visible).toBe(false)
  expect(result.skillHighlights).toEqual([])
  expect(result.eliteHighlight).toBe(false)
  expect(operatorSurvey(op, row, { ...filters, elite1: 30 }).visible).toBe(true)
  expect(
    operatorSurvey({ ...op, rarity: 1, max_phase: 0 }, row, { ...filters, elite1: 30 }).visible
  ).toBe(false)
})
