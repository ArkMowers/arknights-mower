import { expect, it } from 'vitest'
import { defaultIncomeSettings } from './income'
import { revalueIncome } from './incomeValuation'

function completed() {
  return {
    success: true,
    observedHours: 48,
    summary: {
      exp: 1000,
      goldCount: 2,
      goldValue: 1000,
      virtualGoldCount: 1,
      virtualGoldValue: 500,
      orderLmd: 3000,
      fragments: 0,
      orundum: 0,
      lmdConsumed: 0,
      orirockConsumed: 0,
      deviceConsumed: 0,
      recycleCount: 0,
      recruitmentCount: 0,
      clueCount: 0,
      totalScore82: 2800
    },
    simulationReport: {
      observedHours: 48,
      inputs: { schedule: { rooms: [] } },
      production: { assumptions: { expectationMode: true }, expected: { costs: { gold: 6 } } }
    },
    timelineData: { segments: ['original'] },
    eventLog: { entries: ['original'] }
  }
}
it('revalues completed output with shared or custom weights without changing production', () => {
  const original = completed()
  const before = structuredClone(original)
  const settings = {
    ...defaultIncomeSettings(),
    weightMode: 'mower',
    mowerAlgorithm: 3,
    mowerWeights: { exp: 1, gold: 0.8, orders: 0.4 }
  }
  const { result, valuation } = revalueIncome(original, settings)
  expect(result.summary.totalScore82).toBe(3400)
  expect(result.summary.scoreBreakdown.weightedGold).toBe(1200)
  expect(result.observedHours).toBe(48)
  expect(result.simulationReport).toBe(original.simulationReport)
  expect(result.timelineData).toBe(original.timelineData)
  expect(result.eventLog).toBe(original.eventLog)
  expect(original).toEqual(before)
  expect(valuation).not.toHaveProperty('sampleDays')
  settings.mowerWeights.orders = 99
  expect(valuation.mowerWeights.orders).toBe(0.4)
  const custom = revalueIncome(result, {
    ...settings,
    weightMode: 'custom',
    productionWeights: { exp: 2, gold: 0, orders: 1 }
  })
  expect(custom.result.summary.totalScore82).toBe(5000)
})
it('switches to sanity with saved material consumption and back to 82 without stale sanity values', () => {
  const original = completed()
  const settings = {
    ...defaultIncomeSettings(),
    weightMode: 'sanity',
    sanityValuation: {
      version: 1,
      creditDailyLimit: null,
      unitValues: {
        exp: 0.01,
        gold: 2,
        lmd: 0.001,
        fragment: 0,
        orundum: 0,
        orirock: 0,
        device: 0,
        recycle: 0,
        recruitment: 0,
        clue: 0,
        exchange: 0
      }
    }
  }
  const sanity = revalueIncome(original, settings).result
  expect(sanity.summary.sanity.total).toBe(11)
  const conventional = revalueIncome(sanity, {
    ...settings,
    weightMode: 'custom',
    productionWeights: { exp: 1, gold: 0.8, orders: 0.2 }
  }).result
  expect(conventional.summary.totalScore82).toBe(2800)
  expect(conventional.summary).not.toHaveProperty('sanity')
  expect(original.summary).not.toHaveProperty('sanity')
})
it('rejects incomplete historical output and unavailable prices without changing the saved result', () => {
  const original = completed()
  const before = structuredClone(original)
  expect(() => revalueIncome({ success: true }, defaultIncomeSettings())).toThrow('历史记录')
  expect(() => revalueIncome(original, defaultIncomeSettings())).toThrow('材料价值')
  expect(original).toEqual(before)
})
