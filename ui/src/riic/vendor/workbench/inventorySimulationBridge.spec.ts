import { afterEach, describe, expect, it, vi } from 'vitest'
import { createDefaultWorkspace } from './defaults'
import { runScheduleSimulationBridge } from './scheduleSimulationBridge'
import * as runtime from '../scheduler/rosterRuntime'
import { scoreSimulationProduction } from '../simulator/productionScore'
import { mowerReportMetrics } from './mowerReportMetrics'
import { captureOrder, getOrderDistribution } from '../rules/orderRules'
import { runCalculationBridge, simulationReportToCalculationReport } from './calculationBridge'

function workspace(trigger = "op_data.inventory_count('全部经验（计算）') > 999999") {
  const ws = createDefaultWorkspace()
  for (const room of Object.values(ws.mainPlan.facilities)) { room.level = 0; room.slots = [] }
  ws.mainPlan.facilities.room_1_1.level = 1
  ws.mainPlan.facilities.room_1_1.product = 'gold'
  ws.mainPlan.facilities.room_1_3.level = 3
  ws.compatibility.backupPlans = [{ name: 'inventory', trigger, plan: {} }]
  return ws
}

afterEach(() => vi.restoreAllMocks())

describe('inventory state across the workbench simulation bridge', () => {
  it('exposes all six native item names and the physical product from the configured finite ledger', () => {
    const ws = workspace(), before = structuredClone(ws)
    const create = vi.spyOn(runtime, 'createRosterRuntime')
    const options = { sampleHours: .001, production: {
      outputMode: 'potential' as const, inventoryMode: 'unlimited' as const, droneTarget: 'none' as const,
      initialResources: { gold: 4, fragment: 7, orirock: 6, device: 5, lmd: 1600, exp: 1000 },
    } }
    const originalOptions = structuredClone(options)
    const result = runScheduleSimulationBridge(ws, options, { idleOperators: [] })
    expect(result.error).toBeUndefined()
    expect(result.report?.success, JSON.stringify(result.report?.diagnostics)).toBe(true)
    const state = create.mock.results[0]!.value as runtime.RuntimeState
    expect(state.mowerInventoryCounts).toEqual({ 赤金: 4, 源石碎片: 7, 固源岩: 6, 装置: 5, 龙门币: 1600, '全部经验（计算）': 1000 })
    expect(state.mowerFacilityProducts?.room_1_1).toBe('gold')
    expect(result.report!.production!.assumptions).toMatchObject({ outputMode: 'settled', inventoryMode: 'finite' })
    expect(result.report!.inputs.options.production).toMatchObject({ outputMode: 'settled', inventoryMode: 'finite' })
    expect(options).toEqual(originalOptions)
    expect(ws).toEqual(before)
  })

  it('creates a zero finite ledger when inventory conditions have no production options', () => {
    const create = vi.spyOn(runtime, 'createRosterRuntime')
    const result = runScheduleSimulationBridge(workspace(), { sampleHours: .001 }, { idleOperators: [] })
    expect(result.error).toBeUndefined(); expect(result.report?.success).toBe(true)
    expect(result.report!.production!.assumptions).toMatchObject({ outputMode: 'settled', inventoryMode: 'finite' })
    const state = create.mock.results[0]!.value as runtime.RuntimeState
    expect(state.mowerInventoryCounts).toEqual({ 赤金: 0, 源石碎片: 0, 固源岩: 0, 装置: 0, 龙门币: 0, '全部经验（计算）': 0 })
  })

  it('keeps repeated simulations deterministic with independent inventory and product records', () => {
    const create = vi.spyOn(runtime, 'createRosterRuntime')
    const ws = workspace()
    const options = { sampleHours: .01, production: { droneTarget: 'none' as const, initialResources: { gold: 4 } } }
    const first = runScheduleSimulationBridge(ws, options, { idleOperators: [] })
    const firstState = create.mock.results[0]!.value as runtime.RuntimeState
    const second = runScheduleSimulationBridge(ws, options, { idleOperators: [] })
    const secondState = create.mock.results[1]!.value as runtime.RuntimeState
    expect(first.report?.success).toBe(true); expect(second.report?.success).toBe(true)
    expect(second.report).toEqual(first.report)
    expect(secondState.mowerInventoryCounts).not.toBe(firstState.mowerInventoryCounts)
    expect(secondState.mowerFacilityProducts).not.toBe(firstState.mowerFacilityProducts)
    expect(secondState.mowerInventoryCounts).toEqual(firstState.mowerInventoryCounts)
  })

  it('preserves requested potential and unlimited behavior without inventory conditions', () => {
    const ws = workspace('False')
    const result = runScheduleSimulationBridge(ws, {
      sampleHours: .001, production: { outputMode: 'potential', inventoryMode: 'unlimited', droneTarget: 'none', initialResources: { gold: 4, orirock: 9 } },
    }, { idleOperators: [] })
    expect(result.report?.success).toBe(true)
    expect(result.report!.production!.assumptions).toMatchObject({ outputMode: 'potential', inventoryMode: 'unlimited' })
    expect(result.report!.production!.ledger.initial).toMatchObject({ gold: 0, orirock: 0 })
  })

  it('assigns no settled income to completed orundum orders that lack fragments for payment', () => {
    const ws = workspace("op_data.inventory_count('源石碎片') < 0")
    ws.mainPlan.facilities.room_1_1.level = 0
    ws.mainPlan.facilities.room_3_1.level = 3
    ws.mainPlan.facilities.room_3_1.product = 'orundum'
    const result = runScheduleSimulationBridge(ws, {
      sampleHours: 8, production: { droneTarget: 'none' }, productionWeights: { exp: 1, gold: 1, orders: 1, fragments: 1, orundum: 1 },
    }, { idleOperators: [] })
    expect(result.report?.success).toBe(true)
    expect(result.report!.production!.events.some(event => event.type === 'order-completed')).toBe(true)
    expect(result.report!.production!.events.some(event => event.type === 'order-collected')).toBe(false)
    expect(scoreSimulationProduction(result.report!).total).toBe(0)
    expect(mowerReportMetrics(result.report!)!.orderCount).toBe(0)
  })

  it.each(['money', 'orundum'] as const)('keeps the complete calculation summary consistent with actual %s receipts and costs', product => {
    for (const funded of [false, true]) {
      const ws = workspace("op_data.inventory_count('源石碎片') < 0")
      ws.mainPlan.facilities.room_1_1.level = 0
      ws.mainPlan.facilities.room_3_1.level = 3
      ws.mainPlan.facilities.room_3_1.product = product
      const result = runCalculationBridge(ws, {
        engine: 'simulation', simulationAssumptions: { idleOperators: [] }, simulationOptions: {
          sampleHours: 8, production: { droneTarget: 'none', initialResources: funded ? { gold: 10, fragment: 2 } : {} },
        },
      })
      expect(result.success, result.error).toBe(true)
      const sample = result.simulationReport!.production!.sample
      const summary = result.report!.summary!
      expect(summary.orderLmd).toBe((sample.inflows.lmd ?? 0) * 3)
      expect(summary.orundum).toBe((sample.inflows.orundum ?? 0) * 3)
      expect(summary.goldConsumed).toBe((sample.outflows.gold ?? 0) * 3)
      expect(summary.fragmentsConsumed).toBe((sample.outflows.fragment ?? 0) * 3)
      expect(summary.goldCount).toBe(0)
      if (funded) expect(summary.orderLmd + summary.orundum).toBeGreaterThan(0)
      else expect(summary).toMatchObject({ orderLmd: 0, orundum: 0, goldConsumed: 0, fragmentsConsumed: 0, totalEquivalentLmd: 0 })
    }
  })
})

/** Synthetic output isolates accounting from task timing and order RNG. */
function scoringReport(mode: 'settled' | 'potential') {
  const ws = workspace('False')
  const report = runScheduleSimulationBridge(ws, { sampleHours: .001, production: { droneTarget: 'none' } }, { idleOperators: [] }).report!
  report.observedHours = 2; report.elapsedHours = 3; report.assumptions.warmupHours = 1
  report.inputs.options.productionWeights = { exp: 1, gold: .8, orders: .2, fragments: 10, orundum: 5 }
  const production = report.production!
  production.assumptions.outputMode = mode
  production.ledger.initial = { exp: 1000000, gold: 1000, lmd: 1000000, fragment: 100, orundum: 1000 }
  production.sample.completed = { exp: 9000, gold: 9, orderLmd: 2250 }
  production.sample.inflows = { exp: 1000, gold: 2, lmd: 2500, fragment: 3, orundum: 20 }
  production.sample.outflows = { gold: 4, fragment: 2 }
  production.manufacturing = [{ roomId: 'room_1_1', product: 'fragment', completedItems: 12, sampleCompletedItems: 8, pendingItems: 5, remainingBaseMinutes: 0, blockedHours: 0, blockedMaterialHours: 0 }]
  const base = getOrderDistribution(3).find(order => order.goldCost === 4)!
  const order = (id: string, completedAt: number, tequila: 1 | 2 = 2) => ({ ...captureOrder(base, { tequila }, completedAt), id, startedAt: 0 })
  const paidAt = mode === 'settled' ? 1.25 : .5
  production.events = [
    { time: .25, type: 'order-completed', order: order('warmup', .25) },
    { time: .75, type: 'order-collected', order: order('warmup', .25) },
    { time: paidAt, type: 'order-completed', order: order('paid', paidAt) },
    { time: 1.5, type: 'order-collected', order: order('paid', paidAt) },
    { time: 2, type: 'order-completed', order: order('unpaid', 2, 1) },
  ]
  return report
}

describe('inventory-aware report accounting', () => {
  it('scores sampled receipts and paid premiums, excluding warmup receipts, initial stock and pending output', () => {
    const report = scoringReport('settled'), before = structuredClone(report)
    const score = scoreSimulationProduction(report)
    expect(score).toMatchObject({ exp: 12000, goldValue: 12000, orderValue: 30000, weightedGold: 14400, weightedFragments: 360, weightedOrundum: 1200 })
    expect(score.total).toBe(33960)
    const metrics = mowerReportMetrics(report)!
    expect(metrics).toMatchObject({ orderCount: 1, meanOrderValue: 2500, virtualGoldCount: 12, virtualGoldValue: 6000, mower82: 33960 })
    expect(metrics.orderDistribution).toEqual({ tequila: { count: 1, lmd: 2500 } })
    expect(simulationReportToCalculationReport(workspace('False'), report).summary).toMatchObject({
      exp: 12000, goldCount: 24, orderLmd: 30000, fragments: 36, orundum: 240,
      goldConsumed: 48, fragmentsConsumed: 24, virtualGoldCount: 12, totalScore82: 33960,
    })
    expect(report).toEqual(before)
  })

  it('retains completed-output scoring and completion-window premiums in potential mode', () => {
    const report = scoringReport('potential')
    expect(scoreSimulationProduction(report)).toMatchObject({ exp: 108000, goldValue: 54000, orderValue: 27000, weightedGold: 45600, weightedFragments: 960, weightedOrundum: 0, total: 159960 })
    expect(mowerReportMetrics(report)).toMatchObject({ orderCount: 1, meanOrderValue: 2250, virtualGoldCount: 6, virtualGoldValue: 3000 })
  })
})
