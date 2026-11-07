import { expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import { projectScheduleState, simulateSchedule } from './vendor/simulator/scheduleSimulation'
import { evaluateOperators } from './vendor/engine/operatorRules'
import { createProductionTimeline } from './vendor/simulator/productionTimeline'

function setup({
  stock = 0,
  warmup = 0,
  staffed = true,
  trade = false,
  product = 'exp',
  switching = false,
  finite = false,
  initial = {},
  coupledTrade = false,
  switchSettings = {}
} = {}) {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  const primary = trade ? 'room_3_1' : 'room_1_1'
  const rooms = [
    [primary, trade ? 'orundum' : product],
    coupledTrade ? ['room_3_1', 'money'] : ['room_1_2', 'gold']
  ]
  for (const [roomId, product] of rooms)
    Object.assign(workspace.mainPlan.facilities[roomId], {
      level: coupledTrade && roomId === 'room_3_1' ? 1 : 3,
      product,
      slots: staffed
        ? [
            {
              occupant: { kind: 'operator', operatorId: roomId === primary ? '芬' : '杜林' },
              groupId: null,
              replacements: []
            }
          ]
        : []
    })
  workspace.compatibility.unrecognizedFields.advanced_settings = {
    product_switching: {
      enable: switching,
      grandet_mode: false,
      waiting_seconds: 0,
      ...switchSettings
    }
  }
  const desiredProducts = Object.fromEntries(
    rooms.map(([room, value]) => [
      room,
      value === 'exp'
        ? 'exp3'
        : value === 'fragment'
          ? 'orirock'
          : value === 'money'
            ? 'lmd'
            : value
    ])
  )
  const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
  const state = createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
  state.config.mowerDroneRoom = primary
  const frame = (offset = 0) => {
    const config = projectScheduleState(schedule, state)
    const active = new Set(
      Object.entries(state.morale)
        .filter(([, mood]) => mood > 0)
        .map(([id]) => id)
    )
    const morale = new Map(Object.entries(state.morale))
    return {
      time: state.time + offset,
      config,
      active,
      morale,
      desiredProducts,
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
      expectationMode: true,
      theoreticalMode: true,
      outputMode: finite ? 'settled' : 'potential',
      inventoryMode: finite ? 'finite' : 'unlimited',
      droneTarget: trade ? 'trading' : product === 'exp' ? 'exp' : 'gold',
      droneRoomId: primary,
      initialResources: { drone: stock, ...initial }
    },
    warmup,
    () => {},
    false
  )
  production.settle(frame)
  const advance = (hours) => {
    const end = state.time + hours
    while (state.time < end - 1e-10) {
      const maximum = Math.min(
        end - state.time,
        0.1,
        state.time < warmup ? warmup - state.time : Infinity
      )
      const step = production.nextStep(maximum, frame)
      expect(step).toBeGreaterThan(0)
      production.advance(step, frame(step / 2))
      state.time += step
      production.settle(frame)
    }
    const budget = production.report().expected
    expect(budget.droneAllocated + budget.droneLost + budget.droneUnallocated).toBeCloseTo(
      budget.droneGenerated,
      8
    )
    expect(budget.droneSwitchAllocated).toBeLessThanOrEqual(budget.droneAllocated + 1e-8)
    expect(budget.pendingSwitchDrones).toBeGreaterThanOrEqual(0)
  }
  const switchTo = (value) => {
    desiredProducts[primary] = value
    production.settle(frame)
  }
  return { production, state, schedule, frame, advance, switchTo }
}

it.each([0, 250])(
  'values only sampled generated acceleration independently of initial stock %s',
  (stock) => {
    const test = setup({ stock })
    test.advance(2)
    const report = test.production.report()
    // Natural EXP is 120/180*1000; twenty generated drones provide sixty base minutes.
    expect(report.expected.output.exp).toBeCloseTo(1000, 8)
    expect(report.expected.droneGenerated).toBeCloseTo(20, 8)
    expect(report.expected.droneAllocated).toBeCloseTo(20, 8)
    expect(report.assumptions.droneAllocationModel).toBe('generated-capacity-v1')
    expect(report.sampleDrones).toBeUndefined()
  }
)

it('excludes warmup generation without deducting carried drone inventory from sampling', () => {
  const test = setup({ stock: 250, warmup: 3 })
  test.advance(4)
  const report = test.production.report()
  expect(report.expected.output.exp).toBeCloseTo(500, 8)
  expect(report.expected.droneGenerated).toBeCloseTo(10, 8)
  expect(report.expected.droneAllocated).toBeCloseTo(10, 8)
})

it('assigns future generated work to the currently effective target after a room switch', () => {
  const test = setup()
  test.advance(1)
  test.state.config.mowerDroneRoom = 'room_1_2'
  test.production.settle(test.frame)
  test.advance(1)
  const report = test.production.report()
  // Both rooms work naturally for two hours; each target receives thirty generated base minutes.
  expect(report.expected.output.exp).toBeCloseTo(((120 + 30) / 180) * 1000, 8)
  expect(report.expected.output.gold).toBeCloseTo((120 + 30) / 72, 8)
  expect(report.expected.droneAllocated).toBeCloseTo(20, 8)
})

it('does not invent production for an unstaffed generated-drone target', () => {
  const test = setup({ staffed: false })
  test.advance(2)
  const report = test.production.report()
  expect(report.expected.output.exp).toBe(0)
  expect(report.expected.output.gold).toBe(0)
  expect(report.expected.droneGenerated).toBeCloseTo(20, 8)
  expect(report.expected.droneAllocated).toBe(0)
})

it('does not assign generated acceleration to an Orundum trading target', () => {
  const test = setup({ trade: true })
  test.advance(2)
  const report = test.production.report()
  expect(report.expected.output.orundum).toBeCloseTo(20, 8)
  expect(report.expected.droneGenerated).toBeCloseTo(20, 8)
  expect(report.expected.droneAllocated).toBe(0)
})

it.each([0, 250])(
  'switches independently of stock %s and repays generated work to the old formula first',
  (stock) => {
    const test = setup({ switching: true, stock })
    test.switchTo('gold')
    let report = test.production.report()
    expect(report.events.filter((event) => event.type === 'product-switched')).toEqual([
      expect.objectContaining({ time: 0, fromProduct: 'exp3', toProduct: 'gold' })
    ])
    expect(report.expected.output.exp).toBe(0)
    expect(report.expected.pendingSwitchDrones).toBeCloseTo(60, 8)
    test.advance(1)
    report = test.production.report()
    // Ten generated drones repay thirty of the old EXP formula's 180 base minutes.
    expect(report.expected.output.exp).toBeCloseTo(1000 / 6, 8)
    // The new gold formula receives natural work only while the switch is being repaid.
    expect(report.expected.output.gold).toBeCloseTo(120 / 72, 8)
    expect(report.expected.pendingSwitchDrones).toBeCloseTo(50, 8)
    expect(report.expected.droneAllocated).toBeCloseTo(10, 8)
    test.advance(6)
    report = test.production.report()
    expect(report.expected.pendingSwitchDrones).toBeCloseTo(0, 8)
    expect(report.expected.output.exp).toBeCloseTo(1000, 8)
    // Both rooms now produce gold naturally, plus the ten ordinary drones after repayment.
    expect(report.expected.output.gold).toBeCloseTo((7 * 60 * 2 + 30) / 72, 8)
    expect(report.expected.droneAllocated).toBeCloseTo(70, 8)
  }
)

it('keeps a committed switch allocation when ordinary acceleration is disabled afterwards', () => {
  const test = setup({ switching: true })
  test.switchTo('gold')
  test.state.config.mowerDroneRoom = null
  test.advance(1)
  const report = test.production.report()
  expect(report.expected.output.exp).toBeCloseTo(1000 / 6, 8)
  expect(report.expected.output.gold).toBeCloseTo(120 / 72, 8)
  expect(report.expected.pendingSwitchDrones).toBeCloseTo(50, 8)
})

it('charges rounded switch loss to the same generated budget without manufacturing extra output', () => {
  const test = setup({ switching: true })
  test.advance(0.05)
  test.switchTo('gold')
  // 4.5 base minutes are already worked; finishing the remaining 175.5 takes 59 drones.
  expect(test.production.report().expected.pendingSwitchDrones).toBeCloseTo(59, 8)
  test.advance(5.9)
  const report = test.production.report()
  expect(report.expected.output.exp).toBeCloseTo(1000, 8)
  // The second gold room also worked naturally during the initial 0.05 hour.
  expect(report.expected.output.gold).toBeCloseTo((5.9 * 120 + 0.05 * 60) / 72, 8)
  expect(report.expected.droneGenerated).toBeCloseTo(59.5, 8)
  expect(report.expected.droneLost).toBeCloseTo(0.5, 8)
  expect(report.expected.pendingSwitchDrones).toBeCloseTo(0, 8)
})

it('attributes warmup switch repayment to the sampling generation without discarding that capability', () => {
  const test = setup({ warmup: 3, switching: true })
  test.switchTo('gold')
  test.advance(4)
  const report = test.production.report()
  expect(report.expected.output.exp).toBeCloseTo(1000 / 6, 8)
  expect(report.expected.output.gold).toBeCloseTo(120 / 72, 8)
  expect(report.expected.droneGenerated).toBeCloseTo(10, 8)
  expect(report.expected.droneAllocated).toBeCloseTo(10, 8)
  expect(report.expected.pendingSwitchDrones).toBeCloseTo(20, 8)
})

it('reserves finite switch recipe costs once and does not credit unpaid borrowed production', () => {
  const test = setup({
    product: 'fragment',
    switching: true,
    finite: true,
    initial: { lmd: 1600, orirock: 2 }
  })
  test.switchTo('exp3')
  let report = test.production.report()
  expect(report.expected.output.fragments).toBe(0)
  expect(report.expected.pendingSwitchDrones).toBeCloseTo(20, 8)
  test.advance(1)
  report = test.production.report()
  expect(report.expected.output.fragments).toBeCloseTo(0.5, 8)
  expect(report.expected.costs.lmd).toBeCloseTo(800, 8)
  expect(report.expected.costs.orirock).toBeCloseTo(1, 8)
  expect(report.expected.output.exp).toBeCloseTo(1000 / 3, 8)
  test.advance(2)
  report = test.production.report()
  expect(report.expected.output.fragments).toBeCloseTo(1, 8)
  expect(report.expected.costs.lmd).toBeCloseTo(1600, 8)
  expect(report.expected.costs.orirock).toBeCloseTo(2, 8)
  expect(report.expected.output.exp).toBeCloseTo(1000 + 1000 / 6, 8)
  expect(report.expected.pendingSwitchDrones).toBeCloseTo(0, 8)
})

it('does not bypass a natural-only shard switch through ordinary generated acceleration', () => {
  const test = setup({
    product: 'fragment',
    switching: true,
    switchSettings: {
      grandet_mode: true,
      use_drones_when_leaving_orirock: false
    }
  })
  test.switchTo('exp3')
  test.advance(0.5)
  let report = test.production.report()
  expect(report.events.some((event) => event.type === 'product-switched')).toBe(false)
  expect(report.expected.output.fragments).toBeCloseTo(0.5, 8)
  expect(report.expected.droneAllocated).toBe(0)
  expect(report.expected.droneUnallocated).toBeCloseTo(5, 8)
  test.advance(0.5)
  report = test.production.report()
  expect(report.events.filter((event) => event.type === 'product-switched')).toEqual([
    expect.objectContaining({
      time: expect.closeTo(1, 8),
      fromProduct: 'orirock',
      toProduct: 'exp3'
    })
  ])
  expect(report.expected.pendingSwitchDrones).toBe(0)
  test.advance(1)
  report = test.production.report()
  expect(report.expected.output.fragments).toBeCloseTo(1, 8)
  expect(report.expected.output.exp).toBeCloseTo(500, 8)
  expect(report.expected.droneGenerated).toBeCloseTo(20, 8)
  expect(report.expected.droneAllocated).toBeCloseTo(10, 8)
  expect(report.expected.droneUnallocated).toBeCloseTo(10, 8)
})

function simulateChosenTarget(targetRoom, backupTarget) {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  for (const [roomId, product, operatorId] of [
    ['room_1_1', 'exp', '芬'],
    ['room_1_2', 'gold', '杜林']
  ])
    Object.assign(workspace.mainPlan.facilities[roomId], {
      level: 3,
      product,
      slots: [{ occupant: { kind: 'operator', operatorId }, groupId: null, replacements: [] }]
    })
  workspace.mainPlan.conf.drone_room = 'room_1_1'
  workspace.mainPlan.conf.workaholic = ['芬', '杜林']
  if (backupTarget)
    workspace.compatibility.backupPlans = [
      {
        name: 'generated-target-override',
        trigger: 'True',
        conf: { drone_room: backupTarget },
        plan: {},
        task: {}
      }
    ]
  const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
    schedulingModel: 'mower-alpha',
    sampleHours: 2,
    maxStepHours: 24,
    maxEvents: 1000,
    production: {
      expectationMode: true,
      theoreticalMode: true,
      outputMode: 'potential',
      droneTarget: targetRoom ? 'gold' : 'none',
      droneRoomId: targetRoom || undefined
    }
  })
  expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
  return report.production.expected
}

it('uses the calculation target instead of a different saved main-plan target', () => {
  const accelerated = simulateChosenTarget('room_1_2'),
    baseline = simulateChosenTarget(null)
  expect(accelerated.output.exp).toBeCloseTo(baseline.output.exp, 7)
  expect(accelerated.output.gold - baseline.output.gold).toBeCloseTo(60 / 72, 7)
  expect(accelerated.droneAllocated).toBeCloseTo(20, 8)
})

it('lets an active backup override the calculation target', () => {
  const accelerated = simulateChosenTarget('room_1_2', 'room_1_1'),
    baseline = simulateChosenTarget(null)
  expect(accelerated.output.exp - baseline.output.exp).toBeCloseTo(1000 / 3, 7)
  expect(accelerated.output.gold).toBeCloseTo(baseline.output.gold, 7)
  expect(accelerated.droneAllocated).toBeCloseTo(20, 8)
})

it('does not spend a physically borrowed gold bar twice in continuous trade income', () => {
  const test = setup({ product: 'gold', switching: true, finite: true, coupledTrade: true })
  test.switchTo('exp3')
  const switched = test.production.report()
  // The physical scheduler receives the completed bar, but its generated budget is still unpaid.
  expect(switched.sample.closing.gold).toBe(1)
  expect(switched.expected.output.gold).toBe(0)
  test.advance(1)
  const report = test.production.report()
  // Ten generated drones pay for 30/72 of one gold bar; no other room makes gold.
  const affordableGold = 30 / 72
  expect(report.expected.output.gold).toBeCloseTo(affordableGold, 8)
  expect(report.expected.costs.gold).toBeLessThanOrEqual(affordableGold + 1e-8)
  expect(report.expected.output.orderLmd).toBeGreaterThan(0)
  expect(report.expected.output.orderLmd).toBeLessThanOrEqual(affordableGold * 500 + 1e-6)
  expect(report.expected.pendingSwitchDrones).toBeCloseTo(14, 8)
})

it.each([
  [0, 20, 0],
  [250, 250, 24]
])(
  'ignores stock %s, reserve %s and interval %s in the complete theoretical clock',
  (stock, reserve, interval) => {
    const workspace = createDefaultWorkspace()
    for (const room of Object.values(workspace.mainPlan.facilities)) {
      room.level = 0
      room.slots = []
    }
    Object.assign(workspace.mainPlan.facilities.room_1_1, {
      level: 3,
      product: 'exp',
      slots: [
        { occupant: { kind: 'operator', operatorId: '杜林' }, groupId: null, replacements: [] }
      ]
    })
    workspace.mainPlan.conf.workaholic = ['杜林']
    workspace.compatibility.unrecognizedFields.advanced_settings = {
      drone_count_limit: reserve,
      drone_interval: interval
    }
    const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
    const simulate = (target) =>
      simulateSchedule(schedule, {
        schedulingModel: 'mower-alpha',
        sampleHours: 2,
        maxStepHours: 24,
        maxEvents: 1000,
        production: {
          expectationMode: true,
          theoreticalMode: true,
          outputMode: 'potential',
          droneTarget: target ? 'exp' : 'none',
          droneRoomId: target ? 'room_1_1' : undefined,
          initialResources: { drone: stock }
        }
      })
    const accelerated = simulate(true),
      baseline = simulate(false)
    expect(accelerated.success, JSON.stringify(accelerated.diagnostics)).toBe(true)
    expect(baseline.success, JSON.stringify(baseline.diagnostics)).toBe(true)
    expect(
      accelerated.production.expected.output.exp - baseline.production.expected.output.exp
    ).toBeCloseTo(1000 / 3, 7)
    expect(accelerated.production.expected.droneGenerated).toBeCloseTo(20, 8)
    expect(accelerated.production.expected.droneAllocated).toBeCloseTo(20, 8)
    expect(
      accelerated.production.events.some((event) => /^native-.*-drone$/.test(event.type))
    ).toBe(false)
  }
)
