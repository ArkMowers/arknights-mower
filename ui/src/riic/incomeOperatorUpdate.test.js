import { expect, it } from 'vitest'
import { createDefaultConfig } from './vendor/domain/defaults'
import { OPERATORS } from './vendor/domain/operators'
import {
  compileOperatorInventory,
  fullCatalogIdleInventory
} from './vendor/domain/operatorInventory'
import { inventoryOperatorRecords } from './vendor/domain/operatorContext'
import { evaluateOperators } from './vendor/engine/operatorRules'
import { evaluateDormitoryRecovery } from './vendor/engine/dormitoryRecovery'
import { evaluateRecycleEfficiency } from './vendor/engine/supportFacilities/recycle'
import { currentMoraleRates } from './vendor/engine/morale'
import { clueEfficiency } from './incomeClues'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'

const id = (name) => OPERATORS.find((op) => op.name === name).charId
const phases = new Map(
  compileOperatorInventory(fullCatalogIdleInventory()).operators.map((op) => [
    op.charId,
    op.elitePhase
  ])
)
function config() {
  const c = createDefaultConfig()
  c.rooms = []
  c.controlOperatorIds = []
  return c
}
function trade(name, phase = 2) {
  const c = config()
  const room = {
    ...createDefaultConfig().rooms.find((room) => room.type === 'trading'),
    operatorIds: [id(name), id('芬'), id('香草')]
  }
  c.rooms = [room]
  c.operatorRecords = inventoryOperatorRecords(
    compileOperatorInventory([
      { operator: name, elitePhase: phase, level: 1 },
      { operator: '芬', elitePhase: 0, level: 1 },
      { operator: '香草', elitePhase: 0, level: 1 }
    ])
  )
  return [c, room]
}
it('reuses coworker trade rates for 冻河 and respects unlocked stages and zero mood', () => {
  for (const [phase, expected] of [
    [0, 133],
    [2, 143]
  ]) {
    const [c, room] = trade('冻河', phase)
    const result = evaluateOperators(room, c)
    expect(result.efficiencyPercent).toBe(expected)
    expect(result.unquantifiedSkills).toEqual([])
    c.zeroMoraleOperatorIds = [id('芬')]
    expect(evaluateOperators(room, c).efficiencyPercent).toBe(phase === 2 ? 122 : 117)
    c.zeroMoraleOperatorIds = [id('冻河')]
    expect(evaluateOperators(room, c).efficiencyPercent).toBe(102)
  }
  const [tocka, tRoom] = trade('冻河')
  const [justice, jRoom] = trade('吉星')
  expect(evaluateOperators(tRoom, tocka).efficiencyPercent).toBe(
    evaluateOperators(jRoom, justice).efficiencyPercent
  )
})
it('takes the maximum of 冻河 and 波卜 all-room recovery amounts', () => {
  const c = config()
  c.facilities.dormitories = [5]
  c.facilityOperatorIds.dormitories = [[id('冻河'), id('芬')]]
  const moods = new Map([
    [id('冻河'), 10],
    [id('芬'), 10]
  ])
  expect(evaluateDormitoryRecovery(c, 0, moods, 5000).rates.get(id('芬'))).toBeCloseTo(4.12)
  moods.set(id('冻河'), 24)
  expect(evaluateDormitoryRecovery(c, 0, moods, 5000).rates.get(id('芬'))).toBeCloseTo(4.11)
  c.facilityOperatorIds.dormitories[0].push(id('波卜'))
  moods.set(id('波卜'), 10)
  const paired = evaluateDormitoryRecovery(c, 0, moods, 5000)
  expect(paired.rates.get(id('芬'))).toBeCloseTo(4.22)
  expect(paired.unquantified).toEqual([])
})
it('supports the new recycling skills and Dminons separate mood reduction', () => {
  const c = config()
  c.facilities.recycle = 3
  c.facilityOperatorIds.recycle = [id('行铃'), id('国度')]
  expect(evaluateRecycleEfficiency(c).efficiencyPercent).toBe(182)
  expect(currentMoraleRates(c).rates[id('国度')]).toBeCloseTo(0.9)
  expect(currentMoraleRates(c).rates[id('行铃')]).toBeCloseTo(1)
  c.operatorRecords = inventoryOperatorRecords(
    compileOperatorInventory([
      { operator: '行铃', elitePhase: 0, level: 1 },
      { operator: '国度', elitePhase: 0, level: 1 }
    ])
  )
  expect(evaluateRecycleEfficiency(c).efficiencyPercent).toBe(162)
  c.zeroMoraleOperatorIds = [id('国度')]
  expect(evaluateRecycleEfficiency(c).efficiencyPercent).toBe(141)
  c.zeroMoraleOperatorIds = []
  c.facilityOperatorIds.recycle = []
  const power = {
    ...createDefaultConfig().rooms.find((room) => room.type === 'power'),
    operatorIds: [id('国度')]
  }
  c.rooms = [power]
  expect(evaluateOperators(power, c).efficiencyPercent).toBe(120)
  expect(currentMoraleRates(c).rates[id('国度')]).toBe(1)
})
it('uses explicit Ursus student membership and unlocked skills for Algas clue bonus', () => {
  const c = config()
  c.facilities.dormitories = [5, 5, 5, 5]
  c.facilities.reception = 3
  c.facilityOperatorIds.reception = [id('奥尔佳'), id('凛冬')]
  expect(clueEfficiency(c, phases)).toBeCloseTo(2.06)
  c.zeroMoraleOperatorIds = [id('凛冬')]
  expect(clueEfficiency(c, phases)).toBeCloseTo(1.81)
  c.zeroMoraleOperatorIds = []
  c.facilityOperatorIds.reception[1] = id('冻河')
  expect(clueEfficiency(c, phases)).toBeCloseTo(1.87)
  c.facilityOperatorIds.reception[1] = id('凛冬')
  c.operatorRecords = inventoryOperatorRecords(
    compileOperatorInventory([{ operator: '奥尔佳', elitePhase: 0, level: 1 }])
  )
  expect(clueEfficiency(c, new Map([...phases, [id('奥尔佳'), 0]]))).toBeCloseTo(1.7)
})
it('runs all six new operators through cached-roster income calculation', () => {
  const names = ['行铃', '奥尔佳', '镜匠', '冻河', '国度', '塔露拉', '芬', '香草', '凛冬']
  const plans = (names) => names.map((agent) => ({ agent, group: '', replacement: [] }))
  const plan = {
    default: 'plan1',
    conf: { workaholic: names.join(',') },
    backup_plans: [],
    plan1: {
      room_1_1: { name: '贸易站', product: 'lmd', plans: plans(['冻河', '芬', '香草']) },
      room_1_3: { name: '发电站', plans: [] },
      recycle: { name: '', plans: plans(['行铃', '国度']) },
      meeting: { name: '', plans: plans(['奥尔佳', '凛冬']) },
      factory: { name: '', plans: plans(['镜匠']) },
      train: { name: '', plans: plans(['塔露拉']) }
    }
  }
  const result = calculateIncome(plan, {
    ...defaultIncomeSettings(),
    warmupDays: 0,
    sampleDays: 1,
    weightMode: 'custom',
    inventorySource: 'manual',
    initialInventory: { gold: 10000 },
    operatorMode: 'cache',
    cachedOperators: fullCatalogIdleInventory().filter((op) =>
      names.some((name) => id(name) === op.operator)
    )
  })
  expect(result.success, result.error).toBe(true)
  expect(result.observedHours).toBeCloseTo(24, 6)
  expect(result.summary.orderLmd).toBeGreaterThan(0)
  expect(result.summary.clueCount).toBeGreaterThan(0)
  expect(
    result.diagnostics.filter((d) => /UNKNOWN_OPERATOR|UNQUANTIFIED|INVALID/.test(d.code))
  ).toEqual([])
})
