import { expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { simulateSchedule } from './vendor/simulator/scheduleSimulation'

function simulate({
  stock = 0,
  threshold = 30,
  interval = 3,
  hours = 2,
  product = 'exp',
  target = true,
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
    drone_interval: interval
  }
  const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
    schedulingModel: 'mower-alpha',
    sampleHours: hours,
    maxStepHours: 24,
    maxEvents: 5000,
    production: {
      expectationMode: false,
      theoreticalMode: false,
      seed: 42,
      outputMode: finite ? 'settled' : 'potential',
      inventoryMode: finite ? 'finite' : 'unlimited',
      droneTarget: target ? (trading ? 'trading' : 'exp') : 'none',
      droneRoomId: target ? roomId : undefined,
      initialResources: { drone: stock, ...initial }
    }
  })
  expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
  const production = report.production
  const drones = production.sampleDrones
  expect(drones.closing).toBeCloseTo(
    drones.opening + drones.generated - drones.consumed - drones.overflow,
    8
  )
  return production
}

function spending(production, type = 'manufacture') {
  return production.events.filter(
    (event) => event.type === `native-${type}-drone` && event.amount > 0
  )
}

it('retains random-mode inventory below the manufacturing threshold', () => {
  const production = simulate({ stock: 20, hours: 0.5 })
  expect(production.sampleDrones.consumed).toBe(0)
  expect(production.sampleDrones.closing).toBeCloseTo(25, 8)
  expect(spending(production)).toEqual([])
})

it('spends whole drones above the manufacturing reserve using native I/O timing', () => {
  const production = simulate({ stock: 71, hours: 0.5 })
  const events = spending(production)
  expect(events).toHaveLength(1)
  expect(events[0].amount).toBe(41)
  expect(events[0].time).toBeGreaterThan(0)
  expect(events[0].time).toBeLessThan(0.1)
  expect(production.sampleDrones.consumed).toBe(41)
  expect(production.sampleDrones.closing).toBeCloseTo(35, 8)
})

it('keeps the configured service interval between random-mode accelerations', () => {
  const before = simulate({ stock: 71, hours: 2.9 })
  const after = simulate({ stock: 71, hours: 5.5 })
  expect(spending(before)).toHaveLength(1)
  const events = spending(after)
  expect(events).toHaveLength(2)
  expect(events[1].time - events[0].time).toBeGreaterThanOrEqual(3)
  expect(events.every((event) => Number.isInteger(event.amount))).toBe(true)
  expect(after.sampleDrones.closing).toBeGreaterThanOrEqual(30)
})

it('retains full-stock overflow without forced endpoint acceleration', () => {
  const production = simulate({ stock: 250, threshold: 250, hours: 1 })
  expect(production.sampleDrones).toMatchObject({ opening: 250, closing: 250, consumed: 0 })
  expect(production.sampleDrones.generated).toBeCloseTo(10, 8)
  expect(production.sampleDrones.overflow).toBeCloseTo(10, 8)
  expect(spending(production)).toEqual([])
})

it('uses the random trading policy without applying the manufacturing reserve', () => {
  const production = simulate({ stock: 20, product: 'money', hours: 0.5 })
  const events = spending(production, 'trade')
  expect(events).toHaveLength(1)
  expect(events[0].amount).toBe(20)
  expect(events[0].time).toBeGreaterThan(0)
  expect(production.sampleDrones.consumed).toBe(20)
  expect(production.sampleDrones.closing).toBeCloseTo(5, 8)
})

it('never accelerates a random Orundum trading target', () => {
  const production = simulate({ product: 'orundum', stock: 100, hours: 4 })
  const baseline = simulate({ product: 'orundum', stock: 100, hours: 4, target: false })
  expect(production.sampleDrones.consumed).toBe(0)
  expect(production.sampleDrones.closing).toBeCloseTo(140, 8)
  expect(spending(production, 'trade')).toEqual([])
  expect(production.trading[0].completedOrders).toBe(baseline.trading[0].completedOrders)
  expect(production.trading[0].completedOrders).toBeGreaterThan(0)
})

it('leaves drones unused at an unstaffed random manufacturing target', () => {
  const production = simulate({ staffed: false, stock: 71, hours: 4 })
  expect(production.sampleDrones.consumed).toBe(0)
  expect(production.sampleDrones.closing).toBeCloseTo(111, 8)
  expect(production.sample.completed.exp).toBe(0)
  expect(spending(production)).toEqual([])
})

it('stops funding random shard manufacture when its finite materials are exhausted', () => {
  const production = simulate({
    product: 'fragment',
    hours: 4,
    finite: true,
    initial: { lmd: 1600, orirock: 2 }
  })
  expect(production.sample.completed.fragments).toBe(1)
  expect(production.sample.closing).toMatchObject({ lmd: 0, orirock: 0, fragment: 1 })
  expect(production.materialsConsumed).toMatchObject({ lmd: 1600, orirock: 2 })
  expect(production.sampleDrones.consumed).toBe(0)
})
