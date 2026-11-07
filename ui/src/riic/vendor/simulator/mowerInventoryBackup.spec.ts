import { describe, expect, it } from 'vitest'
import { createDefaultWorkspace } from '../workbench/defaults'
import { compileRosterSchedule } from '../scheduler/compileRosterSchedule'
import { simulateSchedule, type ScheduleSimulationReport } from './scheduleSimulation'
import type { ResourceKind } from './resourceLedger'

function inventorySchedule(trigger: string, source: 'gold' | 'fragment' | 'orundum' = 'gold', target = 'orirock') {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) { room.level = 0; room.slots = [] }
  const roomId = source === 'orundum' ? 'room_3_1' : 'room_1_1'
  const room = workspace.mainPlan.facilities[roomId]!
  room.level = 3; room.product = source
  room.slots = [{ occupant: { kind: 'operator', operatorId: 'char_123_fang' }, groupId: null, replacements: [] }]
  workspace.mainPlan.conf.workaholic = ['char_123_fang']
  workspace.compatibility.unrecognizedFields.advanced_settings = {
    product_switching: { enable: true, use_drones_when_leaving_orirock: false, waiting_seconds: 0 },
  }
  workspace.compatibility.backupPlans = [{ name: 'inventory', trigger, plan: { [roomId]: { product: target, plans: [] } } }]
  return compileRosterSchedule(workspace, { idleOperators: [] })
}

function expectConserved(report: ScheduleSimulationReport) {
  expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
  expect(report.production?.success).toBe(true)
  const { ledger, sample } = report.production!
  for (const key of new Set([...Object.keys(ledger.initial), ...Object.keys(ledger.balances)])) {
    const resource = key as ResourceKind
    expect(ledger.balances[resource] ?? 0).toBeGreaterThanOrEqual(0)
    expect(ledger.balances[resource] ?? 0).toBeCloseTo((ledger.initial[resource] ?? 0) + (ledger.inflows[resource] ?? 0) - (ledger.outflows[resource] ?? 0), 7)
    expect((sample.closing[resource] ?? 0) - (sample.opening[resource] ?? 0)).toBeCloseTo((sample.inflows[resource] ?? 0) - (sample.outflows[resource] ?? 0), 7)
  }
}

describe('inventory backup conditions on the shared alpha production clock', () => {
  it('enters above the high threshold, stays on the actual rock recipe, and exits after consuming the low threshold', () => {
    const schedule = inventorySchedule("op_data.inventory_count('固源岩') > 3 or (op_data.inventory_count('固源岩') > 0 and op_data.facility_product('room_1_1') == 'orirock')")
    const report = simulateSchedule(schedule, {
      schedulingModel: 'mower-alpha', sampleHours: 6, maxEvents: 10000,
      production: { outputMode: 'potential', inventoryMode: 'unlimited', droneTarget: 'none', initialResources: { orirock: 4, lmd: 3200 } },
    })
    expectConserved(report)
    const production = report.production!
    expect(production.assumptions).toMatchObject({ outputMode: 'settled', inventoryMode: 'finite' })
    expect(report.events.filter(event => event.type === 'backup-plan').map(event => event.active)).toEqual([true, false])
    expect(production.events.filter(event => event.type === 'product-switched').map(event => [event.fromProduct, event.toProduct])).toEqual([['gold', 'orirock'], ['orirock', 'gold']])
    expect(production.ledger.outflows).toMatchObject({ orirock: 4, lmd: 3200 })
    expect(production.ledger.inflows.orirock ?? 0).toBe(0)
    expect(production.ledger.inflows.device ?? 0).toBe(0)
    expect(production.ledger.balances.orirock).toBe(0)
    expect(production.ledger.entries.filter(entry => entry.reason.includes('manufacture-start:') && entry.delta.orirock)).toHaveLength(2)
  })

  it('defaults unspecified inventory to zero and does not activate a material-funded backup', () => {
    const report = simulateSchedule(inventorySchedule("op_data.inventory_count('固源岩') > 0"), {
      schedulingModel: 'mower-alpha', sampleHours: .1, production: { droneTarget: 'none' },
    })
    expectConserved(report)
    expect(report.production!.ledger.initial).toMatchObject({ gold: 0, fragment: 0, orirock: 0, device: 0, lmd: 0, exp: 0 })
    expect(report.events.some(event => event.type === 'backup-plan' && event.active)).toBe(false)
    expect(report.production!.materialsConsumed.orirock ?? 0).toBe(0)
  })

  it('reads the configured raw product of an unbuilt room when no physical production state exists', () => {
    const workspace = inventorySchedule("op_data.facility_product('room_2_1') == 'orirock_device'", 'gold', 'gold').sourceWorkspace
    workspace.mainPlan.facilities.room_2_1.product = 'fragment'
    workspace.compatibility.facilityMetadata = { room_2_1: { rawProduct: 'orirock_device' } }
    const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
      schedulingModel: 'mower-alpha', sampleHours: .01, production: { droneTarget: 'none' },
    })
    expectConserved(report)
    expect(report.production!.manufacturing.some(room => room.roomId === 'room_2_1')).toBe(false)
    expect(report.events.some(event => event.type === 'backup-plan' && event.active)).toBe(true)
  })


  it('runs composite product counts with finite inventory and observes actual switched products over the original main plan', () => {
    const workspace = inventorySchedule("(op_data.inventory_count('赤金') == 0 and op_data.facility_product_count('gold') == 1) or op_data.facility_product_count('exp3') == 1", 'gold', 'exp3').sourceWorkspace
    for (const room of Object.values(workspace.mainPlan.facilities)) if (room.roomId !== 'room_1_1') room.product = undefined
    const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
      schedulingModel: 'mower-alpha', sampleHours: 2, maxEvents: 10000,
      production: { outputMode: 'potential', inventoryMode: 'unlimited', droneTarget: 'none' },
    })
    expectConserved(report)
    expect(report.production!.assumptions).toMatchObject({ outputMode: 'settled', inventoryMode: 'finite' })
    expect(report.production!.events.filter(event => event.type === 'product-switched').map(event => [event.fromProduct, event.toProduct])).toEqual([['gold', 'exp3']])
    expect(report.events.filter(event => event.type === 'backup-plan').map(event => event.active)).toEqual([true])
  })

  it('initializes production for a count-only condition and counts unobserved main-plan types with live actual products', () => {
    const workspace = inventorySchedule("op_data.facility_product_count('gold') == 1 and op_data.facility_product_count('orirock_device') == 1 and op_data.facility_product_type_count() == 2", 'gold', 'gold').sourceWorkspace
    for (const room of Object.values(workspace.mainPlan.facilities)) if (room.roomId !== 'room_1_1') room.product = undefined
    workspace.mainPlan.facilities.room_2_1.product = 'fragment'
    workspace.compatibility.facilityMetadata = { room_2_1: { rawProduct: 'orirock_device' } }
    const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
      schedulingModel: 'mower-alpha', sampleHours: .01,
    })
    expectConserved(report)
    expect(report.production!.manufacturing.some(room => room.roomId === 'room_2_1')).toBe(false)
    expect(report.events.some(event => event.type === 'backup-plan' && event.active)).toBe(true)
  })

  it('blocks a rock recipe without partially charging rocks when LMD is absent', () => {
    const report = simulateSchedule(inventorySchedule("op_data.inventory_count('固源岩') > 0", 'fragment'), {
      schedulingModel: 'mower-alpha', sampleHours: 2.5,
      production: { droneTarget: 'none', initialResources: { orirock: 4 } },
    })
    expectConserved(report)
    expect(report.production!.ledger.balances.orirock).toBe(4)
    expect(report.production!.ledger.outflows.orirock ?? 0).toBe(0)
    expect(report.production!.manufacturing[0]!.completedItems).toBe(0)
    expect(report.production!.manufacturing[0]!.blockedMaterialHours).toBeGreaterThan(2)
  })

  it('activates from collected gold, while completed but uncollected gold remains outside inventory', () => {
    const report = simulateSchedule(inventorySchedule("op_data.inventory_count('赤金') >= 1", 'gold', 'exp3'), {
      schedulingModel: 'mower-alpha', sampleHours: 12, maxEvents: 10000, production: { droneTarget: 'none' },
    })
    expectConserved(report)
    const collection = report.production!.events.find(event => event.type === 'collect-manufacture:room_1_1' && (event.delta?.gold ?? 0) > 0)
    const activation = report.events.find(event => event.type === 'backup-plan' && event.active)
    expect(collection).toBeDefined(); expect(activation).toBeDefined()
    expect(activation!.time).toBeGreaterThanOrEqual(collection!.time)
    expect(activation!.time - collection!.time).toBeLessThan(.01)
    expect(report.production!.events.some(event => event.type === 'product-switched' && event.toProduct === 'exp3')).toBe(true)
  })

  it('debits fragments only on a paid orundum order and exits without fulfilling unfunded orders', () => {
    const report = simulateSchedule(inventorySchedule("op_data.inventory_count('源石碎片') > 0", 'orundum', 'orundum'), {
      schedulingModel: 'mower-alpha', sampleHours: 8, maxEvents: 10000,
      production: { droneTarget: 'none', initialResources: { fragment: 2 } },
    })
    expectConserved(report)
    const production = report.production!
    expect(report.events.filter(event => event.type === 'backup-plan').map(event => event.active)).toEqual([true, false])
    expect(production.ledger.outflows.fragment).toBe(2)
    expect(production.ledger.inflows.orundum).toBe(20)
    expect(production.ledger.balances.fragment).toBe(0)
    expect(production.events.filter(event => event.type === 'order-collected')).toHaveLength(1)
    expect(production.trading[0]!.pendingOrders.length).toBeGreaterThan(0)
  })

  it('carries a paid warmup batch and depleted inventory into the observation window once', () => {
    const report = simulateSchedule(inventorySchedule("op_data.inventory_count('全部经验（计算）') > 0", 'fragment'), {
      schedulingModel: 'mower-alpha', warmupHours: .5, sampleHours: .75,
      production: { droneTarget: 'none', initialResources: { orirock: 2, lmd: 1600 } },
    })
    expectConserved(report)
    const { sample, ledger, manufacturing } = report.production!
    expect(sample.opening).toMatchObject({ orirock: 0, lmd: 0 })
    expect(sample.outflows).toMatchObject({ orirock: 0, lmd: 0 })
    expect(ledger.outflows).toMatchObject({ orirock: 2, lmd: 1600 })
    expect(ledger.entries.filter(entry => entry.reason.includes('manufacture-start:'))).toHaveLength(1)
    expect(manufacturing[0]!.completedItems).toBe(1)
  })

  it('integrates the new duty after an inventory-triggered assignment without restoring a cached pre-assignment morale endpoint', () => {
    const workspace = inventorySchedule("op_data.inventory_count('赤金') > 0").sourceWorkspace
    workspace.mainPlan.conf.workaholic = ['char_123_fang', 'char_240_wyvern']
    workspace.compatibility.backupPlans = [{
      name: 'inventory-shift', trigger: "op_data.inventory_count('赤金') > 0",
      plan: { room_1_1: { plans: [{ agent: '香草', group: '', replacement: [] }] } },
      task: { room_1_1: ['香草'] },
    }]
    const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
    const reports = [.25, .125].map(maxStepHours => simulateSchedule(schedule, {
      schedulingModel: 'mower-alpha', sampleHours: 8, maxStepHours, recordSegments: true,
      consumptionOverrides: { char_123_fang: 1, char_240_wyvern: 3 },
      production: { droneTarget: 'none' },
    }))
    for (const report of reports) {
      expectConserved(report)
      expect(report.events.some(event => event.type === 'backup-plan' && event.active)).toBe(true)
      const fang = report.operators.find(operator => operator.operatorId === 'char_123_fang')!
      const vanilla = report.operators.find(operator => operator.operatorId === 'char_240_wyvern')!
      expect(fang.idleHours).toBeGreaterThan(0)
      expect(vanilla.workHours).toBeGreaterThan(0)
      // With no dorm or mood skills, the exact result is initial mood minus actual staffed time.
      expect(fang.finalMorale).toBeCloseTo(fang.initialMorale - fang.workHours, 7)
      expect(vanilla.finalMorale).toBeCloseTo(vanilla.initialMorale - 3 * vanilla.workHours, 7)
    }
    for (const id of ['char_123_fang', 'char_240_wyvern']) {
      const left = reports[0]!.operators.find(operator => operator.operatorId === id)!
      const right = reports[1]!.operators.find(operator => operator.operatorId === id)!
      expect(left.finalMorale).toBeCloseTo(right.finalMorale, 6)
      expect(left.workHours).toBeCloseTo(right.workHours, 6)
    }
  })

  it('keeps morale integration exact when starting a new recipe batch wakes an inventory assignment between integration endpoints', () => {
    const workspace = inventorySchedule("op_data.inventory_count('固源岩') == 0", 'fragment').sourceWorkspace
    workspace.mainPlan.facilities.room_1_1.slots[0]!.occupant = { kind: 'operator', operatorId: 'char_240_wyvern' }
    workspace.mainPlan.conf.workaholic = ['char_123_fang', 'char_240_wyvern']
    workspace.compatibility.backupPlans = [{
      name: 'material-shift', trigger: "op_data.inventory_count('固源岩') == 0",
      plan: { room_1_1: { plans: [{ agent: '芬', group: '', replacement: [] }] } },
      task: { room_1_1: ['芬'] },
    }]
    const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
    const reports = [.25, .125].map(maxStepHours => simulateSchedule(schedule, {
      schedulingModel: 'mower-alpha', sampleHours: 3, maxStepHours, recordSegments: true,
      consumptionOverrides: { char_123_fang: 3, char_240_wyvern: 1 },
      production: { droneTarget: 'none', initialResources: { orirock: 4, lmd: 3200 } },
    }))
    for (const report of reports) {
      expectConserved(report)
      expect(report.events.some(event => event.type === 'backup-plan' && event.active)).toBe(true)
      for (const [id, rate] of [['char_123_fang', 3], ['char_240_wyvern', 1]] as const) {
        const operator = report.operators.find(operator => operator.operatorId === id)!
        expect(operator.workHours).toBeGreaterThan(0)
        expect(operator.finalMorale, JSON.stringify({ maxStep: report.inputs.options.maxStepHours, operator, events: report.events })).toBeCloseTo(operator.initialMorale - rate * operator.workHours, 7)
      }
    }
    for (const id of ['char_123_fang', 'char_240_wyvern']) {
      const left = reports[0]!.operators.find(operator => operator.operatorId === id)!
      const right = reports[1]!.operators.find(operator => operator.operatorId === id)!
      expect(left.finalMorale).toBeCloseTo(right.finalMorale, 6)
    }
  })
})
