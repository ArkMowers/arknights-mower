import { expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import { projectScheduleState } from './vendor/simulator/scheduleSimulation'
import { evaluateOperators } from './vendor/engine/operatorRules'
import { createProductionTimeline } from './vendor/simulator/productionTimeline'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'

function fixture(product, { stock = 1, debt = false, goldDebt = false, potential = false } = {}) {
  const workspace = createDefaultWorkspace(),
    roomId = 'room_3_1',
    operatorId = 'char_212_ansel'
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  Object.assign(workspace.mainPlan.facilities[roomId], {
    level: product === 'money' ? 1 : 3,
    product,
    slots: [{ occupant: { kind: 'operator', operatorId }, groupId: null, replacements: [] }]
  })
  const resource = product === 'money' ? 'gold' : 'fragment'
  const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
  const state = createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
  state.morale[operatorId] = 0
  delete state.occupants[roomId + '_0']
  const frame = () => {
    const config = projectScheduleState(schedule, state),
      morale = new Map(Object.entries(state.morale)),
      active = new Set()
    return {
      time: state.time,
      config,
      morale,
      active,
      evaluations: Object.fromEntries(
        config.rooms.map((room) => [room.id, evaluateOperators(room, config, active, morale)])
      )
    }
  }
  const production = createProductionTimeline(
    schedule,
    state,
    {
      expectationMode: true,
      theoreticalMode: true,
      outputMode: potential ? 'potential' : 'settled',
      inventoryMode: 'finite',
      allowMaterialDebt: debt,
      allowGoldDebt: goldDebt,
      initialResources: { [resource]: stock, drone: 0 },
      droneTarget: 'none'
    },
    72,
    () => {},
    false
  )
  production.settle(frame)
  const advanceTo = (end) => {
    let iterations = 0
    while (state.time < end - 1e-10) {
      expect(++iterations).toBeLessThan(2000)
      const dt = production.nextStep(
        Math.min(0.25, end - state.time, state.time < 72 ? 72 - state.time : Infinity),
        frame
      )
      expect(dt).toBeGreaterThan(0)
      production.advance(dt, frame())
      state.time += dt
      production.settle(frame)
    }
  }
  const staff = () => {
    state.occupants[roomId + '_0'] = operatorId
    production.settle(frame)
  }
  return { production, advanceTo, staff, resource }
}

it.each(['money', 'orundum'])(
  'reserves %s materials consumed by completed unpaid warmup orders',
  (product) => {
    const test = fixture(product)
    test.advanceTo(69)
    test.staff()
    test.advanceTo(72)
    const opening = test.production.report()
    expect(opening.trading[0].pendingOrders.length).toBeGreaterThan(0)
    expect(opening.trading[0].collectedOrders).toBe(0)
    expect(opening.sample.opening[test.resource]).toBe(1)
    test.advanceTo(96)
    const sampled = test.production.report().expected
    expect(sampled.output.orderLmd).toBe(0)
    expect(sampled.output.orundum).toBe(0)
    expect(sampled.costs[test.resource] ?? 0).toBe(0)
  }
)

it.each(['money', 'orundum'])(
  'reserves the already-worked warmup share of an unfinished %s order',
  (product) => {
    const duration = product === 'money' ? 2.4 : 2
    const test = fixture(product)
    test.advanceTo(72 - duration / 4)
    test.staff()
    test.advanceTo(72)
    const opening = test.production.report()
    expect(opening.trading[0].pendingOrders).toHaveLength(0)
    expect(opening.trading[0].remainingBaseMinutes).toBeCloseTo(duration * 60 * 0.75, 8)
    test.advanceTo(96)
    const sampled = test.production.report().expected
    // One unit of stock minus the quarter-order warmup share (two units per order).
    expect(sampled.costs[test.resource]).toBeCloseTo(0.5, 8)
    expect(product === 'money' ? sampled.output.orderLmd : sampled.output.orundum).toBeCloseTo(
      product === 'money' ? 250 : 5,
      8
    )
  }
)

it.each(['money', 'orundum'])('does not reserve already-paid %s warmup orders twice', (product) => {
  const duration = product === 'money' ? 2.4 : 2
  const test = fixture(product, { stock: 10 })
  test.advanceTo(72 - duration)
  test.staff()
  test.advanceTo(72)
  const opening = test.production.report()
  expect(opening.trading[0].collectedOrders).toBe(1)
  expect(opening.trading[0].pendingOrders).toHaveLength(0)
  expect(opening.sample.opening[test.resource]).toBeCloseTo(8, 8)
  test.advanceTo(96)
  const sampled = test.production.report().expected
  expect(sampled.costs[test.resource]).toBeCloseTo(8, 8)
  expect(product === 'money' ? sampled.output.orderLmd : sampled.output.orundum).toBeCloseTo(
    product === 'money' ? 4000 : 80,
    8
  )
})

it.each([
  ['money', { debt: true }],
  ['money', { goldDebt: true }],
  ['orundum', { debt: true }],
  ['money', { potential: true }],
  ['orundum', { potential: true }]
])('retains unrestricted %s sampled work under %j', (product, options) => {
  const test = fixture(product, options)
  test.advanceTo(69)
  test.staff()
  test.advanceTo(96)
  const sampled = test.production.report().expected
  expect(product === 'money' ? sampled.output.orderLmd : sampled.output.orundum).toBeCloseTo(
    product === 'money' ? 10000 : 240,
    7
  )
})

function workerInput(dailyGold) {
  const plan = {
    default: 'plan1',
    conf: { workaholic: '安赛尔' },
    backup_plans: [],
    facility_levels: { room_3_1: 1, room_1_3: 3, room_2_3: 3 },
    plan1: {
      room_1_3: { name: '发电站', plans: [] },
      room_2_3: { name: '发电站', plans: [] },
      room_3_1: { name: '贸易站', product: 'lmd', plans: [{ agent: '安赛尔', replacement: [] }] }
    }
  }
  const settings = {
    ...defaultIncomeSettings(),
    operatorMode: 'maximum',
    inventorySource: 'manual',
    finiteInventory: true,
    allowMaterialDebt: false,
    weightMode: 'custom',
    warmupDays: 3,
    sampleDays: 1,
    dailyExternalResources: { gold: dailyGold }
  }
  return { plan, settings }
}

it('keeps a real three-day warmup plus one-day Worker run within the externally supplied gold budget', () => {
  const { plan, settings } = workerInput(19.2)
  const result = calculateIncome(plan, settings)
  expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
  expect(result.simulationReport.elapsedHours).toBeCloseTo(96, 8)
  const production = result.simulationReport.production
  expect(production.trading[0].pendingOrders.length).toBeGreaterThan(0)
  // Warmup already owes more gold than its opening stock; sampled income cannot use that stock again.
  expect(production.expected.costs.gold).toBeLessThanOrEqual(19.2 + 1e-8)
  expect(result.summary.orderLmd).toBeLessThanOrEqual(19.2 * 500 + 1e-6)
})

it('spends the four daily external gold on unpaid warmup orders rather than sampled income through the Worker entry', () => {
  const { plan, settings } = workerInput(4)
  const result = calculateIncome(plan, settings)
  expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
  expect(result.simulationReport.elapsedHours).toBeCloseTo(96, 8)
  const production = result.simulationReport.production
  expect(production.sample.external.gold).toBeCloseTo(4, 8)
  expect(production.sample.outflows.gold).toBeCloseTo(4, 8)
  expect(production.trading[0].collectedOrders).toBe(8)
  expect(result.summary.orderLmd).toBe(0)
  expect(production.expected.costs.gold).toBe(0)
})
