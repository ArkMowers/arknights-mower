import { expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import { projectScheduleState } from './vendor/simulator/scheduleSimulation'
import { evaluateOperators } from './vendor/engine/operatorRules'
import { createProductionTimeline } from './vendor/simulator/productionTimeline'
import {
  simulationOutputAmounts,
  scoreSimulationProduction
} from './vendor/simulator/productionScore'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'

const runs = new Map()
function externalRun(warmupReceipt = false) {
  if (runs.has(warmupReceipt)) return structuredClone(runs.get(warmupReceipt))
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  if (warmupReceipt)
    Object.assign(workspace.mainPlan.facilities.room_3_1, {
      level: 1,
      product: 'money',
      slots: [
        {
          occupant: { kind: 'operator', operatorId: 'char_212_ansel' },
          groupId: null,
          replacements: []
        }
      ]
    })
  const warmupHours = 72,
    sampleHours = 2160
  const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
  const state = createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
  const frame = () => {
    const config = projectScheduleState(schedule, state)
    const active = new Set(Object.keys(state.morale)),
      morale = new Map(Object.entries(state.morale))
    return {
      time: state.time,
      config,
      active,
      morale,
      evaluations: Object.fromEntries(
        config.rooms.map((room) => [
          room.id,
          { ...evaluateOperators(room, config, active, morale), efficiencyPercent: 100 }
        ])
      )
    }
  }
  const production = createProductionTimeline(
    schedule,
    state,
    {
      expectationMode: false,
      seed: 42,
      outputMode: 'settled',
      inventoryMode: 'finite',
      allowMaterialDebt: false,
      droneTarget: 'none',
      initialResources: { gold: warmupReceipt === 'generated' ? 1000 : warmupReceipt ? 2 : 0 },
      dailyExternalResources: { lmd: 100000 }
    },
    warmupHours,
    () => {},
    warmupReceipt !== 'generated'
  )
  production.settle(frame)
  while (state.time < warmupHours + sampleHours) {
    const maximum = Math.min(
      0.25,
      warmupHours + sampleHours - state.time,
      state.time < warmupHours ? warmupHours - state.time : Infinity
    )
    const duration = production.nextStep(maximum, frame)
    production.advance(duration, frame())
    state.time += duration
    if (warmupReceipt === 'opening' && state.time === 72)
      production.nativeAcceptOrder('room_3_1', frame())
    production.settle(frame)
    if (warmupReceipt === 'generated' && state.time === 72) {
      delete state.occupants.room_3_1_0
      production.settle(frame)
    }
    if (warmupReceipt === true && state.time === 72.25)
      production.nativeAcceptOrder('room_3_1', frame())
  }
  production.finalize(frame())
  const report = {
    success: true,
    production: production.report(),
    observedHours: sampleHours,
    elapsedHours: warmupHours + sampleHours,
    assumptions: { warmupHours, maxStepHours: 0.25 },
    inputs: { options: {} }
  }
  runs.set(warmupReceipt, report)
  return structuredClone(report)
}

it.each([false, true, 'opening', 'generated'])(
  'does not score external LMD as a negative receipt over ninety days (warmup receipt=%s)',
  (warmupReceipt) => {
    const report = externalRun(warmupReceipt)
    expect(report.production.sample.external.lmd).toBeCloseTo(9000000, 4)
    if (warmupReceipt === true) expect(report.production.sample.warmupReceipts.lmd).toBe(1000)
    expect(simulationOutputAmounts(report).orderLmd).toBe(0)
    expect(scoreSimulationProduction(report).total).toBe(0)
  },
  30000
)

it('retains a genuine small non-external receipt alongside large external supplies', () => {
  const report = externalRun()
  report.production.events.push({ time: 73, type: 'collect-order:small', delta: { lmd: 1e-9 } })
  report.production.sample.inflows.lmd += 1e-9
  expect(simulationOutputAmounts(report).orderLmd).toBe(1e-9)
  expect(scoreSimulationProduction(report).total).toBeGreaterThan(0)
})

it('retains small positive receipts and rejects an actual negative aggregate without external roundoff', () => {
  const report = externalRun()
  report.production.events = []
  report.production.sample.inflows = { lmd: 1e-12 }
  report.production.sample.external = {}
  report.production.sample.warmupReceipts = {}
  expect(simulationOutputAmounts(report).orderLmd).toBe(1e-12)
  report.production.sample.inflows = {}
  report.production.sample.external = { lmd: 1e-12 }
  expect(() => scoreSimulationProduction(report)).toThrow('无效的完成产出')
})

const workerInput = {
  plan: {
    default: 'plan1',
    conf: {},
    backup_plans: [],
    plan1: {
      room_1_1: { name: '制造站', product: 'gold', plans: [] },
      room_1_3: { name: '发电站', plans: [] }
    }
  },
  settings: {
    ...defaultIncomeSettings(),
    expectationMode: false,
    seed: 42,
    operatorMode: 'maximum',
    inventorySource: 'manual',
    finiteInventory: true,
    allowMaterialDebt: false,
    weightMode: 'custom',
    warmupDays: 3,
    sampleDays: 90,
    dailyExternalResources: { lmd: 100000 }
  }
}

it('returns the complete Worker calculation for ninety days of external LMD without trade income', () => {
  const result = calculateIncome(workerInput.plan, workerInput.settings)
  expect(result.success, result.error).toBe(true)
  expect(result.observedHours).toBeCloseTo(2160, 8)
  expect(result.summary.orderLmd).toBe(0)
  expect(result.summary.totalScore82).toBe(0)
}, 30000)

it('keeps old reports without transaction events usable while rejecting a material negative discrepancy', () => {
  const report = externalRun('generated')
  report.production.events = []
  expect(simulationOutputAmounts(report).orderLmd).toBe(0)
  expect(scoreSimulationProduction(report).total).toBe(0)
  report.production.sample.inflows.lmd -= 0.01
  expect(() => scoreSimulationProduction(report)).toThrow('无效的完成产出')
})
