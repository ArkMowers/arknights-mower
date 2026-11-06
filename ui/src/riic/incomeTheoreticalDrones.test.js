import { expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { simulateSchedule } from './vendor/simulator/scheduleSimulation'

function simulate({
  stock = 0,
  threshold = 30,
  interval = 3,
  hours = 2,
  warmup = 0,
  target = true,
  switchToGold = false,
  product = 'exp',
  expected = true,
  staffed = true,
  finite = false,
  initial = {}
} = {}) {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  const trading = ['money', 'orundum'].includes(product)
  const roomId = trading ? 'room_3_1' : 'room_1_1'
  Object.assign(workspace.mainPlan.facilities[roomId], {
    level: 3,
    product,
    slots: staffed
      ? [{ occupant: { kind: 'operator', operatorId: '杜林' }, groupId: null, replacements: [] }]
      : []
  })
  workspace.mainPlan.conf.workaholic = ['杜林']
  workspace.compatibility.unrecognizedFields.advanced_settings = {
    drone_count_limit: threshold,
    drone_interval: interval,
    product_switching: {
      enable: switchToGold,
      max_drones_per_switch: 0,
      grandet_mode: true,
      waiting_seconds: 0,
      direct_when_drones_insufficient: false
    }
  }
  if (switchToGold)
    workspace.compatibility.backupPlans = [
      {
        name: 'manufacture-gold-after-current-unit',
        trigger: 'True',
        plan: {
          [roomId]: {
            product: 'gold',
            plans: [{ agent: 'Current', group: '', replacement: [] }]
          }
        }
      }
    ]
  const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
    schedulingModel: 'mower-alpha',
    warmupHours: warmup,
    sampleHours: hours,
    maxStepHours: 24,
    maxEvents: 1000,
    production: {
      expectationMode: expected,
      theoreticalMode: expected,
      seed: 42,
      outputMode: finite ? 'settled' : 'potential',
      inventoryMode: finite ? 'finite' : 'unlimited',
      droneTarget: target ? (trading ? 'trading' : 'exp') : 'none',
      droneRoomId: target ? roomId : undefined,
      initialResources: { drone: stock, ...initial }
    }
  })
  expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
  return report.production
}

function spending(production) {
  return production.events.filter(
    (event) => event.type === 'native-manufacture-drone' && event.amount > 0
  )
}

it('keeps generated drones in stock and adds no acceleration income below the manufacturing threshold', () => {
  const production = simulate()
  const baseline = simulate({ target: false })
  expect(production.sampleDrones.generated).toBeCloseTo(20, 8)
  expect(production.sampleDrones.closing).toBeCloseTo(20, 8)
  expect(production.sampleDrones.consumed).toBe(0)
  expect(production.expected.droneAllocated).toBe(0)
  expect(production.expected.output.exp).toBeCloseTo(baseline.expected.output.exp, 8)
  expect(spending(production)).toEqual([])
})

it('uses only stock above the configured manufacturing reserve and excludes initial drones from income', () => {
  const production = simulate({ stock: 71, hours: 0.5 })
  const baseline = simulate({ stock: 71, hours: 0.5, target: false })
  expect(spending(production)).toEqual([
    expect.objectContaining({ roomId: 'room_1_1', amount: 41, time: 0 })
  ])
  expect(production.sampleDrones.consumed).toBe(41)
  expect(production.sampleDrones.closing).toBeCloseTo(35, 8)
  expect(production.expected.droneAllocated).toBe(0)
  expect(production.expected.output.exp).toBeCloseTo(baseline.expected.output.exp, 8)
})

it('does not spend newly generated stock again before the configured service interval', () => {
  const production = simulate({ stock: 71, hours: 2.9 })
  expect(spending(production)).toHaveLength(1)
  expect(production.sampleDrones.consumed).toBe(41)
  expect(production.sampleDrones.closing).toBeCloseTo(59, 8)
  expect(production.expected.droneAllocated).toBe(0)
})

it('wakes the event clock for drone service and values only sampled drones actually spent', () => {
  const production = simulate({ hours: 6.1 })
  const baseline = simulate({ hours: 6.1, target: false })
  const events = spending(production)
  expect(events).toHaveLength(1)
  expect(events[0].time).toBeGreaterThanOrEqual(6)
  expect(events[0].time).toBeLessThan(6.001)
  expect(events[0].amount).toBe(30)
  expect(production.sampleDrones.generated).toBeCloseTo(61, 8)
  expect(production.sampleDrones.consumed).toBe(30)
  expect(production.sampleDrones.closing).toBeCloseTo(31, 8)
  expect(production.expected.droneAllocated).toBe(30)
  // Each drone supplies three base minutes; one EXP batch needs 180 and yields 1000.
  expect(production.expected.output.exp - baseline.expected.output.exp).toBeCloseTo(500, 8)
})

it('does not value overflow or unspent drones as manufacturing income', () => {
  const production = simulate({ stock: 250, threshold: 250, hours: 1 })
  const baseline = simulate({ stock: 250, threshold: 250, hours: 1, target: false })
  expect(production.sampleDrones).toMatchObject({
    opening: 250,
    closing: 250,
    consumed: 0
  })
  expect(production.sampleDrones.generated).toBeCloseTo(10, 8)
  expect(production.sampleDrones.overflow).toBeCloseTo(10, 8)
  expect(production.expected.droneAllocated).toBe(0)
  expect(production.expected.output.exp).toBeCloseTo(baseline.expected.output.exp, 8)
})

it('assigns stored sampled drones to the room product when service executes after a product switch', () => {
  const production = simulate({ hours: 6.1, switchToGold: true })
  const baseline = simulate({ hours: 6.1, switchToGold: true, target: false })
  expect(production.events.filter((event) => event.type === 'product-switched')).toEqual([
    expect.objectContaining({ roomId: 'room_1_1', fromProduct: 'exp3', toProduct: 'gold' })
  ])
  for (const result of [production, baseline])
    expect(
      result.events.filter((event) => event.type === 'product-switch-drone' && event.amount)
    ).toEqual([expect.objectContaining({ roomId: 'room_1_1', amount: 19 })])
  expect(spending(production)).toEqual([
    expect.objectContaining({ roomId: 'room_1_1', amount: 11 })
  ])
  expect(production.expected.droneAllocated).toBe(30)
  expect(baseline.expected.droneAllocated).toBe(19)
  expect(production.expected.output.exp).toBeCloseTo(baseline.expected.output.exp, 8)
  // Both runs spend nineteen drones switching; the next service spends eleven on gold.
  expect(production.expected.output.gold - baseline.expected.output.gold).toBeCloseTo(
    (11 * 3) / 72,
    8
  )
})

it('excludes drones carried out of warmup when the next service spends them during sampling', () => {
  const production = simulate({ warmup: 3.1, hours: 3 })
  const baseline = simulate({ warmup: 3.1, hours: 3, target: false })
  expect(production.sampleDrones.opening).toBeCloseTo(31, 8)
  expect(production.sampleDrones.consumed).toBe(30)
  expect(production.expected.droneGenerated).toBeCloseTo(30, 8)
  expect(production.expected.droneAllocated).toBe(0)
  expect(production.expected.output.exp).toBeCloseTo(baseline.expected.output.exp, 8)
})

it('uses a zero service interval without polling before newly charged stock exceeds the reserve', () => {
  const production = simulate({ interval: 0, hours: 3.15 })
  const baseline = simulate({ interval: 0, hours: 3.15, target: false })
  const events = spending(production)
  expect(events).toHaveLength(1)
  expect(events[0].time).toBeCloseTo(3.1, 8)
  expect(events[0].amount).toBe(1)
  expect(production.sampleDrones.generated).toBeCloseTo(31.5, 8)
  expect(production.sampleDrones.consumed).toBe(1)
  expect(production.sampleDrones.closing).toBeCloseTo(30.5, 8)
  expect(production.expected.droneAllocated).toBe(1)
  expect(production.expected.output.exp - baseline.expected.output.exp).toBeCloseTo(1000 / 60, 8)
})

it('uses the ordinary trading policy without applying the manufacturing reserve to its stock', () => {
  const production = simulate({ product: 'money', stock: 20, hours: 0.5 })
  const baseline = simulate({ product: 'money', stock: 20, hours: 0.5, target: false })
  expect(
    production.events.filter((event) => event.type === 'native-trade-drone' && event.amount)
  ).toEqual([expect.objectContaining({ roomId: 'room_3_1', amount: 20, time: 0 })])
  expect(production.sampleDrones.consumed).toBe(20)
  expect(production.sampleDrones.closing).toBeCloseTo(5, 8)
  expect(production.expected.droneAllocated).toBe(0)
  expect(production.expected.output.orderLmd).toBeCloseTo(baseline.expected.output.orderLmd, 8)
})

it.each([true, false])('never accelerates an Orundum trade target (expectation=%s)', (expected) => {
  const production = simulate({ product: 'orundum', stock: 100, hours: 4, expected })
  const baseline = simulate({ product: 'orundum', stock: 100, hours: 4, expected, target: false })
  expect(production.sampleDrones.consumed).toBe(0)
  expect(production.sampleDrones.closing).toBeCloseTo(140, 8)
  expect(
    production.events.filter((event) => event.type === 'native-trade-drone' && event.amount)
  ).toEqual([])
  expect(production.trading[0].completedOrders).toBe(baseline.trading[0].completedOrders)
  expect(production.trading[0].completedOrders).toBeGreaterThan(0)
  if (expected) {
    expect(production.expected.droneAllocated).toBe(0)
    expect(production.expected.output.orundum).toBeCloseTo(baseline.expected.output.orundum, 8)
  }
})

it('keeps drones unused when the selected manufacturing facility has no occupants', () => {
  const production = simulate({ staffed: false, stock: 71, hours: 4 })
  expect(production.sampleDrones.consumed).toBe(0)
  expect(production.sampleDrones.closing).toBeCloseTo(111, 8)
  expect(production.expected.droneAllocated).toBe(0)
  expect(production.expected.output.exp).toBe(0)
  expect(spending(production)).toEqual([])
})

it('stops drone acceleration and expected costs when a finite shard recipe runs out of materials', () => {
  const production = simulate({
    product: 'fragment',
    interval: 0,
    threshold: 0,
    hours: 2,
    finite: true,
    initial: { lmd: 1600, orirock: 2 }
  })
  // One sixty-minute batch costs two Orirock and 1600 LMD. At 101% natural
  // efficiency it finishes after the sixth newly charged drone, before the seventh.
  expect(production.sampleDrones.generated).toBeCloseTo(20, 8)
  expect(production.sampleDrones.consumed).toBe(6)
  expect(production.sampleDrones.closing).toBeCloseTo(14, 8)
  expect(production.expected.droneAllocated).toBe(6)
  expect(production.expected.output.fragments).toBeCloseTo(1, 8)
  expect(production.expected.costs).toMatchObject({
    lmd: expect.closeTo(1600, 8),
    orirock: expect.closeTo(2, 8)
  })
  expect(production.sample.closing).toMatchObject({ lmd: 0, orirock: 0, fragment: 1 })
  expect(spending(production).every((event) => event.time < 0.7)).toBe(true)
})
