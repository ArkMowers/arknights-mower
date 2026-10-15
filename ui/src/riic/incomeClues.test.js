import { expect, it } from 'vitest'
import { createDefaultConfig } from './vendor/domain/defaults'
import { OPERATORS } from './vendor/domain/operators'
import {
  fullCatalogIdleInventory,
  compileOperatorInventory
} from './vendor/domain/operatorInventory'
import { inventoryOperatorRecords } from './vendor/domain/operatorContext'
import { clueEfficiency, createClueObservation } from './incomeClues'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings, incomeImageMetrics, incomeMetrics, incomeRequest } from './income'
import { runCalculationBridge } from './vendor/workbench/calculationBridge'

const phases = new Map(
  compileOperatorInventory(fullCatalogIdleInventory()).operators.map((o) => [
    o.charId,
    o.elitePhase
  ])
)
function reception(...ids) {
  const config = createDefaultConfig()
  config.facilityOperatorIds.reception = ids
  return config
}
it('applies room, ambience, rarity, promotion and awake bonuses independently', () => {
  const config = reception('char_202_demkni')
  // 111% room + 15% ambience + 5% rarity + 16% promotion + 5% awake + 10% skill.
  expect(clueEfficiency(config, phases)).toBeCloseTo(1.62)
  config.operatorMorale.char_202_demkni = 0
  expect(clueEfficiency(config, phases)).toBeCloseTo(1.47)
  config.facilities.reception = 1
  config.facilities.dormitories = [1, 1, 0, 0]
  expect(clueEfficiency(config, phases)).toBeCloseTo(1.33)
  expect(clueEfficiency(reception(), phases)).toBe(0)
  config.facilities.reception = 0
  expect(clueEfficiency(config, phases)).toBe(0)
})
it('uses supplied promotion and skills instead of maximum assumptions', () => {
  const owned = compileOperatorInventory([{ operator: '塞雷娅', elitePhase: 0, level: 1 }])
  const config = reception('char_202_demkni')
  config.operatorRecords = inventoryOperatorRecords(owned)
  expect(clueEfficiency(config, new Map([['char_202_demkni', 0]]))).toBeCloseTo(1.46)
})
it('handles all pinned reception skills without counting clue-type effects as speed', () => {
  for (const operator of OPERATORS) {
    for (const slot of operator.skillSlots ?? []) {
      for (const skill of slot.filter((skill) => skill.roomType === 'MEETING')) {
        const config = reception(operator.charId)
        config.operatorRecords = { [operator.charId]: { ...operator, skills: [skill] } }
        expect(clueEfficiency(config, phases), skill.buffId).toBeGreaterThan(1)
      }
    }
  }
  expect(clueEfficiency(reception('char_4220_kormr'), phases)).toBeCloseTo(1.31)
})
it('gates single-operator skills on awake coworkers and cooperative bonuses on providers', () => {
  const config = reception('char_1015_aglna2', 'char_202_demkni')
  expect(clueEfficiency(config, phases)).toBeCloseTo(1.88)
  config.operatorMorale.char_202_demkni = 0
  expect(clueEfficiency(config, phases)).toBeCloseTo(2.23)
  const pair = reception('char_4231_clemnt', 'char_202_demkni')
  expect(clueEfficiency(pair, phases)).toBeCloseTo(2.23)
  pair.operatorMorale.char_202_demkni = 0
  expect(clueEfficiency(pair, phases)).toBeCloseTo(1.93)
})
it('carries unfinished warmup progress and stops in an empty room', () => {
  const observer = createClueObservation(20)
  const config = reception('char_202_demkni')
  observer.observe(config, 0, 20)
  observer.observe(reception(), 20, 30)
  observer.observe(config, 30, 50)
  expect(observer.result().completed).toBe(2)
  expect(observer.result().progress).toBeCloseTo(0.24)
})
it('integrates Ines ramp through its cap and resets after leaving reception', () => {
  const observer = createClueObservation(0)
  const config = reception('char_4087_ines')
  observer.observe(config, 0, 10)
  // Base 172%, plus 0.25 rate-hours for the first five hours and 0.5 thereafter.
  expect(observer.result().progress).toBeCloseTo((17.2 + 0.75) / 20)
  observer.observe(reception(), 10, 11)
  observer.observe(config, 11, 12)
  expect(observer.result().progress).toBeCloseTo((17.95 + 1.73) / 20)
})
it('reports clue counts through the Worker without changing income, inventory or scheduling', () => {
  const plan = {
    default: 'plan1',
    conf: { workaholic: ['塞雷娅'] },
    backup_plans: [],
    plan1: {
      meeting: { name: '', plans: [{ agent: '塞雷娅' }] },
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
  const result = calculateIncome(plan, settings)
  expect(result.success, result.error).toBe(true)
  expect(result.summary.clueCount).toBeCloseTo(1)
  const days = result.observedHours / 24
  for (const metric of [
    incomeImageMetrics(result.summary, days).find((row) => row.key === 'clue'),
    incomeMetrics(result.summary, days).find((row) => row.label === '会客室线索')
  ]) {
    expect(metric.daily).toBeCloseTo(1)
    expect(metric.total).toBeCloseTo(1)
    expect(metric.unit).toBe('个')
  }
  const request = incomeRequest(plan, settings)
  const baseline = runCalculationBridge(request.workspace, request.options)
  expect(result.summary.totalScore82).toBe(baseline.report.summary.totalScore82)
  expect(result.resources).toEqual(baseline.simulationReport.production.sample)
  expect(result.simulationReport.segments).toEqual(baseline.simulationReport.segments)
  plan.plan1.meeting.plans = []
  const empty = calculateIncome(plan, settings)
  expect(empty.summary.clueCount).toBe(0)
  expect(incomeImageMetrics(empty.summary, 1).some((row) => row.key === 'clue')).toBe(false)
  expect(incomeMetrics({}, 1).some((row) => row.label === '会客室线索')).toBe(false)
})
