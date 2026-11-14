import { expect, it } from 'vitest'
import { createDefaultConfig, createRoom } from './vendor/domain/defaults'
import { resolveOperatorCharId as id } from './vendor/domain/operatorIdentifiers'
import { compileOperatorInventory } from './vendor/domain/operatorInventory'
import { inventoryOperatorRecords } from './vendor/domain/operatorContext'
import { evaluateOperators } from './vendor/engine/operatorRules'
import { evaluateTradeOrderCapacity } from './vendor/engine/orderCapacity'

it.each([
  { phase: 0, absent: 25, present: 30 },
  { phase: 2, absent: 30, present: 40 }
])('grants Bellone the cross-station Vigil bonus at phase $phase', ({ phase, absent, present }) => {
  const config = createDefaultConfig()
  config.operatorRecords = inventoryOperatorRecords(
    compileOperatorInventory([
      { operator: '贝洛内', elitePhase: phase, level: 1 },
      { operator: '伺夜', elitePhase: 2, level: 1 }
    ])
  )
  const bellone = createRoom('B101', 'trading')
  const other = createRoom('B201', 'trading')
  bellone.operatorIds = [id('贝洛内')]
  config.rooms = [bellone, other]
  const contribution = () =>
    evaluateOperators(bellone, config).operatorContributions.find(
      (operator) => operator.operatorId === id('贝洛内')
    ).skillBonus

  const capacity = () =>
    evaluateTradeOrderCapacity(
      bellone,
      config,
      new Set([id('贝洛内'), id('伺夜')]),
      evaluateOperators(bellone, config)
    ).limit
  expect(contribution()).toBe(absent)
  const absentCapacity = capacity()
  const absentEfficiency = evaluateOperators(bellone, config).efficiencyPercent
  other.operatorIds = [id('伺夜')]
  expect(contribution()).toBe(present)
  expect(evaluateOperators(bellone, config).efficiencyPercent).toBe(
    absentEfficiency + present - absent
  )
  expect(capacity()).toBe(absentCapacity)
  config.zeroMoraleOperatorIds = [id('伺夜')]
  expect(contribution()).toBe(present)
  config.zeroMoraleOperatorIds = []
  other.operatorIds = []
  bellone.operatorIds.push(id('伺夜'))
  expect(contribution()).toBe(present)
  expect(capacity()).toBe(absentCapacity + 2)
  bellone.operatorIds.pop()
  config.facilityOperatorIds.dormitories[0] = [id('伺夜')]
  expect(contribution()).toBe(present)
  expect(capacity()).toBe(absentCapacity)
  config.facilityOperatorIds.dormitories[0] = []
  expect(contribution()).toBe(absent)
})
