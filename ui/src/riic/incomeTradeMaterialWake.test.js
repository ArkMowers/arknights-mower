import { expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import { projectScheduleState } from './vendor/simulator/scheduleSimulation'
import { evaluateOperators } from './vendor/engine/operatorRules'
import { createProductionTimeline } from './vendor/simulator/productionTimeline'

function fixture(
  product,
  { step = 0.25, external, debt = false, goldDebt = false, unlimited = false } = {}
) {
  const workspace = createDefaultWorkspace(),
    roomId = 'room_3_1'
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  Object.assign(workspace.mainPlan.facilities[roomId], {
    level: product === 'money' ? 1 : 3,
    product,
    slots: [
      {
        occupant: { kind: 'operator', operatorId: 'char_212_ansel' },
        groupId: null,
        replacements: []
      }
    ]
  })
  const resource = product === 'money' ? 'gold' : 'fragment'
  const deadline = product === 'money' ? 20.125 : 25.125
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
          {
            ...evaluateOperators(room, config, active, morale),
            efficiencyPercent: 100
          }
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
      inventoryMode: unlimited ? 'unlimited' : 'finite',
      outputMode: 'settled',
      allowMaterialDebt: debt,
      allowGoldDebt: goldDebt,
      initialResources: { gold: 0, fragment: 0, drone: 0 },
      droneTarget: 'none',
      dailyExternalResources: external ?? { [resource]: (2 * 24) / deadline }
    },
    0,
    () => {},
    false
  )
  production.settle(frame)
  const advance = (hours) => {
    production.advance(hours, frame())
    state.time += hours
    production.settle(frame)
  }
  const advanceTo = (end) => {
    let count = 0
    while (state.time < end - 1e-10) {
      expect(++count).toBeLessThan(10000)
      const hours = production.nextStep(Math.min(step, end - state.time), frame)
      expect(hours).toBeGreaterThan(0)
      advance(hours)
    }
  }
  return { production, state, frame, advance, advanceTo, deadline, resource }
}

it.each(['money', 'orundum'])(
  'wakes a full %s order queue exactly when external payment material arrives',
  (product) => {
    const test = fixture(product)
    test.advanceTo(Math.floor(test.deadline))
    const before = test.production.report().trading[0]
    expect(before.completedOrders).toBe(product === 'money' ? 6 : 10)
    expect(before.pendingOrders).toHaveLength(product === 'money' ? 6 : 10)
    expect(before.collectedOrders).toBe(0)
    expect(before.remainingBaseMinutes).toBeNull()
    const wake = test.production.nextStep(0.25, test.frame)
    expect(wake).toBeCloseTo(0.125, 9)
    test.advance(0.05)
    expect(test.production.nextStep(0.25, test.frame)).toBeCloseTo(0.075, 9)
    test.advance(test.deadline - test.state.time)
    const after = test.production.report()
    expect(after.trading[0].collectedOrders).toBe(1)
    expect(after.trading[0].pendingOrders).toHaveLength(product === 'money' ? 5 : 9)
    expect(after.trading[0].remainingBaseMinutes).toBe(product === 'money' ? 144 : 120)
    expect(after.events.filter((event) => event.type === 'order-collected')).toEqual([
      expect.objectContaining({ roomId: 'room_3_1', time: expect.closeTo(test.deadline, 9) })
    ])
  }
)

it.each(['money', 'orundum'])(
  'keeps external payment and resumed %s production independent of coarse/fine steps',
  (product) => {
    const results = [1, 0.07].map((step) => {
      const test = fixture(product, { step })
      test.advanceTo(test.deadline * 2 + 0.5)
      return test.production.report()
    })
    const [coarse, fine] = results
    for (const result of results) {
      expect(result.trading[0].collectedOrders).toBe(2)
      expect(
        result.events.filter((event) => event.type === 'order-collected').map((event) => event.time)
      ).toEqual([
        expect.closeTo(product === 'money' ? 20.125 : 25.125, 8),
        expect.closeTo(product === 'money' ? 40.25 : 50.25, 8)
      ])
    }
    expect(coarse.trading[0].completedOrders).toBe(fine.trading[0].completedOrders)
    expect(coarse.trading[0].remainingBaseMinutes).toBeCloseTo(
      fine.trading[0].remainingBaseMinutes,
      8
    )
    expect(coarse.sample.outflows.gold ?? 0).toBeCloseTo(fine.sample.outflows.gold ?? 0, 8)
    expect(coarse.sample.outflows.fragment ?? 0).toBeCloseTo(fine.sample.outflows.fragment ?? 0, 8)
  }
)

it.each(['money', 'orundum'])(
  'does not invent a %s material deadline from unrelated external supplies',
  (product) => {
    const test = fixture(product, { external: { lmd: 100 } })
    test.advanceTo(product === 'money' ? 20 : 25)
    expect(test.production.report().trading[0].remainingBaseMinutes).toBeNull()
    expect(test.production.nextStep(0.25, test.frame)).toBe(0.25)
    test.advance(0.25)
    expect(test.production.report().trading[0].collectedOrders).toBe(0)
  }
)

it.each([
  ['money', { goldDebt: true }],
  ['orundum', { debt: true }],
  ['money', { unlimited: true }],
  ['orundum', { unlimited: true }]
])(
  'does not wait for external materials when %s payment is already allowed by %j',
  (product, options) => {
    const test = fixture(product, { ...options, external: {} })
    test.advanceTo(3)
    expect(test.production.report().trading[0].collectedOrders).toBe(1)
    expect(test.production.report().trading[0].pendingOrders).toHaveLength(0)
    expect(test.production.nextStep(0.25, test.frame)).toBe(0.25)
  }
)

it.each(['money', 'orundum'])(
  'continues acquiring unpaid %s orders until the queue is full',
  (product) => {
    const duration = product === 'money' ? 2.4 : 2
    const test = fixture(product)
    test.advanceTo(duration + duration / 2)
    const first = test.production.report().trading[0]
    expect(first.completedOrders).toBe(1)
    expect(first.collectedOrders).toBe(0)
    expect(first.pendingOrders).toHaveLength(1)
    expect(first.remainingBaseMinutes).toBeCloseTo(duration * 30, 8)
    test.advanceTo(duration * 2)
    const second = test.production.report().trading[0]
    expect(second.completedOrders).toBe(2)
    expect(second.collectedOrders).toBe(0)
    expect(second.pendingOrders).toHaveLength(2)
    expect(second.remainingBaseMinutes).toBeCloseTo(duration * 60, 8)
    expect(test.production.nextStep(1, test.frame)).toBe(1)
  }
)

it.each(['money', 'orundum'])(
  'pays the waiting %s head order before storage is full without interrupting current acquisition',
  (product) => {
    const deadline = product === 'money' ? 3.125 : 2.125
    const resource = product === 'money' ? 'gold' : 'fragment'
    const test = fixture(product, { external: { [resource]: (2 * 24) / deadline } })
    test.advanceTo(Math.floor(deadline))
    const before = test.production.report().trading[0]
    expect(before.pendingOrders).toHaveLength(1)
    expect(before.collectedOrders).toBe(0)
    expect(before.remainingBaseMinutes).toBeGreaterThan(0)
    expect(test.production.nextStep(0.25, test.frame)).toBeCloseTo(0.125, 9)
    test.advance(deadline - test.state.time)
    const after = test.production.report().trading[0]
    expect(after.collectedOrders).toBe(1)
    expect(after.pendingOrders).toHaveLength(0)
    expect(after.remainingBaseMinutes).toBeCloseTo(before.remainingBaseMinutes - 7.5, 8)
    expect(
      test.production.report().events.filter((event) => event.type === 'order-started')
    ).toHaveLength(2)
  }
)
