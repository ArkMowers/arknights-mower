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
import { incomeOrderDistribution } from './incomeOrders'
import { incomeManufacturingCosts } from './incomeManufacturingCosts'
import { createClueObservation } from './incomeClues'
import { createRecruitmentObservation } from './incomeRecruitment'
import { createDefaultConfig } from './vendor/domain/defaults'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'

function fixture(
  product,
  {
    warmup = 0,
    stock = 0,
    drone = false,
    staffed = true,
    finite = false,
    initial = {},
    expected = true,
    recycle = false,
    debt = false,
    external = {},
    operators = ['芬'],
    formula = 'fragment-orirock'
  } = {}
) {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  const roomId = ['money', 'orundum'].includes(product) ? 'room_3_1' : 'room_1_1'
  Object.assign(workspace.mainPlan.facilities[roomId], {
    level: 3,
    product,
    slots: staffed
      ? operators.map((operatorId) => ({
          occupant: { kind: 'operator', operatorId },
          groupId: null,
          replacements: []
        }))
      : []
  })
  if (recycle) workspace.mainPlan.facilities.recycle.level = 3
  const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
  const state = createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
  const frame = () => {
    const config = projectScheduleState(schedule, state),
      active = new Set(Object.keys(state.morale)),
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
      expectationMode: expected,
      allowMaterialDebt: debt,
      dailyExternalResources: external,
      fragmentFormulaByRoom: { [roomId]: formula },
      outputMode: finite ? 'settled' : 'potential',
      inventoryMode: finite ? 'finite' : 'unlimited',
      droneTarget: drone
        ? roomId === 'room_3_1'
          ? 'trading'
          : product === 'fragment'
            ? 'gold'
            : product
        : 'none',
      droneRoomId: drone ? roomId : undefined,
      initialResources: { drone: stock, ...initial }
    },
    warmup,
    () => {},
    true
  )
  production.settle(frame)
  function advance(hours) {
    const end = state.time + hours
    while (state.time < end - 1e-10) {
      const maximum = Math.min(
        end - state.time,
        0.1,
        state.time < warmup ? warmup - state.time : Infinity
      )
      const duration = production.nextStep(maximum, frame)
      expect(duration).toBeGreaterThan(0)
      production.advance(duration, frame())
      state.time += duration
      production.settle(frame)
    }
  }
  function report() {
    return {
      success: true,
      production: production.report(),
      observedHours: state.time - warmup,
      elapsedHours: state.time,
      assumptions: { warmupHours: warmup },
      inputs: { options: {} }
    }
  }
  return { advance, report, production, roomId, frame }
}

it.each([
  ['exp', 'exp', 1000 / 3],
  ['gold', 'gold', 60 / 72],
  ['fragment', 'fragments', 1]
])('values fractional %s work before a whole product is completed', (product, field, rate) => {
  const test = fixture(product)
  test.advance(0.5)
  const report = test.report()
  expect(report.production.manufacturing[0].sampleCompletedItems).toBe(0)
  expect(simulationOutputAmounts(report)[field]).toBeCloseTo(rate / 2, 9)
  expect(scoreSimulationProduction(report).total).toBeGreaterThanOrEqual(0)
  if (product === 'fragment')
    expect(incomeManufacturingCosts(report)).toMatchObject({
      lmdConsumed: 38400,
      orirockConsumed: 48,
      deviceConsumed: 0
    })
})

it.each(['exp', 'gold', 'fragment', 'money', 'orundum'])(
  'excludes warmup progress from continuous %s output',
  (product) => {
    const cold = fixture(product),
      warm = fixture(product, { warmup: 0.7 })
    cold.advance(0.5)
    warm.advance(1.2)
    for (const [key, value] of Object.entries(simulationOutputAmounts(cold.report())))
      expect(simulationOutputAmounts(warm.report())[key]).toBeCloseTo(value, 8)
  }
)

it('counts fractional orders, rewards and costs without completing or collecting an order', () => {
  const test = fixture('money')
  test.advance(1)
  const report = test.report(),
    count = 60 / 203.4
  expect(report.production.trading[0].completedOrders).toBe(0)
  expect(simulationOutputAmounts(report).orderLmd).toBeCloseTo(count * 1450, 9)
  expect(incomeOrderDistribution(report)).toMatchObject({ expected: true, total: count })
  expect(report.production.expected.costs.gold).toBeCloseTo(count * 2.9, 9)
  expect(incomeOrderDistribution(report).rows.map((row) => row.count)).toEqual(
    [0.3, 0.5, 0.2].map((p) => expect.closeTo(p * count, 9))
  )
})

it.each(['exp', 'gold', 'fragment', 'money', 'orundum'])(
  'values generated drones for %s independent of stock and spending',
  (product) => {
    const empty = fixture(product, { drone: true }),
      loaded = fixture(product, { drone: true, stock: 200 })
    empty.advance(0.25)
    loaded.advance(0.25)
    if (product === 'money' || product === 'orundum')
      loaded.production.nativeSpendTradeDrones(loaded.roomId, 10, loaded.frame())
    else loaded.production.nativeSpendManufacturingDrones(loaded.roomId, 10)
    empty.advance(0.25)
    loaded.advance(0.25)
    const a = empty.report(),
      b = loaded.report()
    for (const [key, value] of Object.entries(simulationOutputAmounts(a)))
      expect(simulationOutputAmounts(b)[key]).toBeCloseTo(value, 8)
    expect(a.production.expected.droneGenerated).toBeCloseTo(5, 9)
    expect(a.production.expected.droneAllocated).toBeCloseTo(5, 9)
    expect(a.production.drones.consumed).toBe(0)
    expect(b.production.drones.consumed).toBe(10)
  }
)

it('keeps finite manufacturing materials and finite order inputs bounded', () => {
  const shards = fixture('fragment', {
    finite: true,
    drone: true,
    initial: { lmd: 1600, orirock: 2 }
  })
  shards.advance(2)
  expect(simulationOutputAmounts(shards.report()).fragments).toBeCloseTo(1, 8)
  const trade = fixture('money', { finite: true, drone: true, initial: { gold: 1 } })
  trade.advance(1)
  expect(simulationOutputAmounts(trade.report()).orderLmd).toBeCloseTo(500, 8)
})

it('produces no expected income in an empty work facility and retains sampled mode', () => {
  const empty = fixture('exp', { staffed: false, drone: true })
  empty.advance(0.5)
  expect(simulationOutputAmounts(empty.report()).exp).toBe(0)
  expect(empty.report().production.expected.droneGenerated).toBeCloseTo(5)
  const sampled = fixture('exp', { expected: false })
  sampled.advance(0.5)
  expect(sampled.report().production.expected).toBeUndefined()
  expect(simulationOutputAmounts(sampled.report()).exp).toBe(0)
})

it('counts fractional recycling, recruitment refreshes and clues without warmup carry', () => {
  const recycle = fixture('exp', { recycle: true, warmup: 1 })
  recycle.advance(1.5)
  expect(recycle.report().production.recycle.sampleCompletedItems).toBe(0)
  expect(recycle.report().production.expected.recycleCount).toBeCloseTo((0.5 * 1.2) / 48, 9)
  const config = createDefaultConfig()
  config.facilityOperatorIds.office = ['char_278_orchid']
  config.facilityOperatorIds.reception = ['char_202_demkni']
  const recruitment = createRecruitmentObservation(1),
    clues = createClueObservation(1)
  for (const observer of [recruitment, clues]) {
    observer.observe(config, 0, 1)
    observer.observe(config, 1, 1.5)
  }
  expect(recruitment.result(true).completed).toBeCloseTo((1.45 * 0.5) / 12, 9)
  expect(clues.result(true).completed).toBeCloseTo((1.62 * 0.5) / 20, 9)
  expect(recruitment.result().completed).toBe(0)
  expect(clues.result().completed).toBe(0)
})

it.each([true, false])(
  'supports material deficits and excludes external supplies from income (expected %s)',
  (expected) => {
    const test = fixture('fragment', {
      finite: true,
      debt: true,
      expected,
      external: { gold: 24, lmd: 2400, orirock: 24, device: 12, fragment: 6 }
    })
    test.advance(0.5)
    const report = test.report(),
      output = simulationOutputAmounts(report)
    expect(output.gold).toBe(0)
    expect(output.orderLmd).toBe(0)
    expect(output.fragments).toBeCloseTo(expected ? 0.5 : 0, 8)
    expect(report.production.sample.external.gold).toBeCloseTo(0.5, 8)
    expect(report.production.sample.external.lmd).toBeCloseTo(50, 8)
    expect(report.production.sample.closing.lmd).toBeLessThan(0)
    expect(report.production.sample.closing.orirock).toBeLessThan(0)
  }
)

it.each([1, 2])(
  'opens manufacturing at the calculated external funding threshold (rate multiplier %s)',
  (multiplier) => {
    const test = fixture('fragment', {
      finite: true,
      expected: false,
      external: { lmd: 1600 * multiplier, orirock: 2 * multiplier }
    })
    const wait = 24 / multiplier
    expect(test.production.nextStep(30, test.frame)).toBeCloseTo(wait, 8)
    test.advance(wait)
    expect(test.report().production.manufacturing[0].completedItems).toBe(0)
    test.advance(1)
    expect(test.report().production.manufacturing[0].completedItems).toBe(1)
    test.production.finalize(test.frame())
    expect(simulationOutputAmounts(test.report()).fragments).toBeCloseTo(1, 8)
    expect(test.report().production.sample.external.orirock).toBeCloseTo(
      ((wait + 1) * 2 * multiplier) / 24,
      8
    )
  }
)

it.each([true, false])(
  'does not score external supplies or warmup inputs (expected %s)',
  (expected) => {
    const test = fixture('exp', {
      finite: true,
      expected,
      staffed: false,
      warmup: 0.5,
      external: { lmd: 2400, gold: 24, fragment: 12 }
    })
    test.advance(1)
    const report = test.report()
    expect(report.production.sample.external.lmd).toBeCloseTo(50, 8)
    expect(report.production.sample.opening.lmd).toBeCloseTo(50, 8)
    expect(scoreSimulationProduction(report).total).toBe(0)
  }
)

it.each([true, false])(
  'allows all raw material deficits without an external source (expected %s)',
  (expected) => {
    for (const product of ['fragment', 'orundum']) {
      const test = fixture(product, { finite: true, debt: true, expected })
      test.advance(2.1)
      test.production.finalize(test.frame())
      const report = test.report()
      expect(
        simulationOutputAmounts(report)[product === 'fragment' ? 'fragments' : 'orundum']
      ).toBeGreaterThan(0)
      expect(
        report.production.sample.closing[product === 'fragment' ? 'orirock' : 'fragment']
      ).toBeLessThan(0)
    }
  }
)

it.each([{ gold: -1 }, { device: NaN }, { drone: 1 }, { exp: 1000 }])(
  'rejects invalid external input %j',
  (external) => {
    expect(() => fixture('exp', { external })).toThrow()
  }
)

it.each([true, false])(
  'excludes external LMD from Worker income and frozen report metrics (expected %s)',
  (expectationMode) => {
    const plan = {
      default: 'plan1',
      conf: {},
      backup_plans: [],
      plan1: {
        room_1_1: { name: '制造站', product: 'gold', plans: [] },
        room_1_3: { name: '发电站', plans: [] }
      }
    }
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      expectationMode,
      seed: 42,
      warmupDays: 0,
      sampleDays: 1,
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: true,
      weightMode: 'custom',
      dailyExternalResources: { lmd: 2400, fragment: 12 },
      initialInventory: {}
    })
    expect(result.success, result.error).toBe(true)
    expect(result.summary.orderLmd).toBe(0)
    expect(result.summary.netLmd).toBeCloseTo(0, 8)
    expect(result.resources.external.lmd).toBeCloseTo(2400, 8)
    expect(result.resources.closing.lmd).toBeCloseTo(2400, 8)
    expect(result.summary.fragments).toBeCloseTo(0, 8)
  }
)

it('integrates tier-specific Proviso and Tequila effects before the first order completes', () => {
  const test = fixture('money', { operators: ['但书', '龙舌兰'] })
  test.advance(1)
  const report = test.report(),
    count = 60 / 203.4
  expect(report.production.trading[0].completedOrders).toBe(0)
  expect(simulationOutputAmounts(report).orderLmd).toBeCloseTo(count * 2350, 8)
  expect(simulationOutputAmounts(report).virtualGold).toBeCloseTo(count * 0.2, 8)
  expect(report.production.expected.costs.gold).toBeCloseTo(count * 4.5, 8)
})

it('integrates Device recipe costs with fractional shard production', () => {
  const test = fixture('fragment', { formula: 'fragment-device' })
  test.advance(0.5)
  const report = test.report()
  expect(simulationOutputAmounts(report).fragments).toBeCloseTo(0.5, 8)
  expect(report.production.expected.costs).toMatchObject({
    lmd: expect.closeTo(500, 8),
    device: expect.closeTo(0.5, 8)
  })
  expect(report.production.expected.costs.orirock ?? 0).toBe(0)
})
