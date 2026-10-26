import { expect, it } from 'vitest'
import { createDefaultConfig } from './vendor/domain/defaults'
import { compileOperatorInventory } from './vendor/domain/operatorInventory'
import { inventoryOperatorRecords } from './vendor/domain/operatorContext'
import { OPERATORS } from './vendor/domain/operators'
import { createRecruitmentObservation, recruitmentEfficiency } from './incomeRecruitment'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings, incomeImageMetrics, incomeMetrics, incomeRequest } from './income'
import { runCalculationBridge } from './vendor/workbench/calculationBridge'

function office(id = 'char_278_orchid') {
  const config = createDefaultConfig()
  config.facilityOperatorIds.office = id ? [id] : []
  return config
}

it('uses the occupied office baseline and disables exhausted skills and staffing bonus', () => {
  const config = office()
  expect(recruitmentEfficiency(config)).toBeCloseTo(1.45)
  config.operatorMorale.char_278_orchid = 0
  expect(recruitmentEfficiency(config)).toBe(1)
  expect(recruitmentEfficiency(office(''))).toBe(0)
  config.facilities.office = 0
  expect(recruitmentEfficiency(config)).toBe(0)
})

it('uses unlocked skills and dynamic office/dormitory conditions', () => {
  const config = office('char_145_prove')
  config.operatorRecords = inventoryOperatorRecords(
    compileOperatorInventory([{ operator: '普罗旺斯', elitePhase: 0, level: 1 }])
  )
  expect(recruitmentEfficiency(config)).toBeCloseTo(1.35)
  const lin = office('char_4080_lin')
  lin.facilities.office = 1
  expect(recruitmentEfficiency(lin)).toBeCloseTo(1.25)
  lin.facilities.office = 3
  expect(recruitmentEfficiency(lin)).toBeCloseTo(1.45)
  const tinman = office('char_4151_tinman')
  tinman.facilities.dormitories = [1, 2, 3, 4]
  expect(recruitmentEfficiency(tinman)).toBeCloseTo(1.3)
})

it('handles every unlocked office skill in the pinned catalog', () => {
  for (const operator of OPERATORS) {
    for (const slot of operator.skillSlots ?? []) {
      for (const skill of slot.filter((skill) => skill.roomType === 'HIRE')) {
        const config = office(operator.charId)
        config.operatorRecords = { [operator.charId]: { ...operator, skills: [skill] } }
        expect(
          recruitmentEfficiency(config),
          `${operator.name}: ${skill.buffId}`
        ).toBeGreaterThanOrEqual(1.05)
      }
    }
  }
})

it('counts active control providers and disables their bonuses when exhausted', () => {
  const config = office('char_457_blitz')
  config.controlOperatorIds = ['char_456_ash', 'char_459_tachak', 'char_197_poca']
  // Ash and Tachanka: two Rainbow operators; Poca: one Ursus student.
  expect(recruitmentEfficiency(config)).toBeCloseTo(1.4)
  config.zeroMoraleOperatorIds = ['char_456_ash', 'char_459_tachak']
  expect(recruitmentEfficiency(config)).toBeCloseTo(1.25)
  const silverash = office('char_1046_sbell2')
  silverash.controlOperatorIds = ['char_1045_svash2']
  expect(recruitmentEfficiency(silverash)).toBeCloseTo(1.5)
  silverash.operatorMorale.char_1045_svash2 = 0
  expect(recruitmentEfficiency(silverash)).toBeCloseTo(1.4)
})

it('carries partial warmup progress, excluding warmup completions and empty shifts', () => {
  const config = office()
  config.operatorMorale.char_278_orchid = 0
  const observer = createRecruitmentObservation(18)
  observer.observe(config, 0, 18)
  observer.observe(office(''), 18, 30)
  observer.observe(config, 30, 36)
  expect(observer.result().completed).toBe(1)
  expect(observer.result().progress).toBeCloseTo(0)
})

it('reports actual office interval production through the complete Worker calculation', () => {
  const plan = {
    default: 'plan1',
    conf: { workaholic: ['梓兰'] },
    backup_plans: [],
    plan1: {
      contact: { name: '', plans: [{ agent: '梓兰' }] },
      room_1_1: { name: '制造站', product: 'gold', plans: [] },
      room_1_3: { name: '发电站', plans: [] }
    }
  }
  const settings = {
    ...defaultIncomeSettings(),
    operatorMode: 'maximum',
    weightMode: 'custom',
    finiteInventory: false,
    warmupDays: 0,
    sampleDays: 1
  }
  const original = structuredClone(plan)
  const result = calculateIncome(plan, settings)
  expect(result.success, JSON.stringify(result)).toBe(true)
  // 24 h at 145% produces 2 complete refreshes, with partial progress retained.
  expect(result.summary.recruitmentCount).toBeCloseTo(2, 8)
  expect(result.summary.goldCount).toBeGreaterThan(0)
  expect(result.summary.valuation.completedScore.daily).toBeCloseTo(result.summary.goldCount * 400)
  expect(result.summary.totalScore82).toBeCloseTo(
    (result.summary.goldCount + result.summary.valuation.adjustment.amounts.gold) * 400
  )
  expect(
    incomeMetrics(result.summary, result.observedHours / 24).find((row) => row.label === '公招刷新')
      .total
  ).toBeCloseTo(2, 8)
  const badge = incomeImageMetrics(result.summary, result.observedHours / 24).find(
    (row) => row.key === 'recruitment'
  )
  expect(badge.daily).toBeCloseTo(2, 8)
  expect(badge.total).toBeCloseTo(2, 8)
  expect(badge.unit).toBe('次')
  expect(plan).toEqual(original)
  const request = incomeRequest(plan, settings)
  const unobserved = runCalculationBridge(request.workspace, request.options)
  expect(unobserved.success).toBe(true)
  expect(result.summary.goldCount).toBe(unobserved.report.summary.goldCount)
  expect(result.summary.totalScore82).toBe(unobserved.report.summary.totalScore82)
  expect(result.resources).toEqual(unobserved.simulationReport.production.sample)
  expect(result.simulationReport.operators).toEqual(unobserved.simulationReport.operators)
  expect(result.simulationReport.segments).toEqual(unobserved.simulationReport.segments)
  plan.plan1.contact.plans = []
  const empty = calculateIncome(plan, settings)
  expect(empty.success, empty.error).toBe(true)
  expect(empty.summary.recruitmentCount).toBe(0)
  expect(incomeImageMetrics(empty.summary, 1).some((row) => row.key === 'recruitment')).toBe(false)
})
