import { expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import { projectScheduleState } from './vendor/simulator/scheduleSimulation'
import { evaluateOperators } from './vendor/engine/operatorRules'
import { createProductionTimeline } from './vendor/simulator/productionTimeline'

it('keeps physical and expected ordinary work aligned when charging ramps through switch settlement', () => {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) {
    room.level = 0
    room.slots = []
  }
  for (const [roomId, product, operatorId] of [
    ['room_1_1', 'exp', '芬'],
    ['room_1_2', 'gold', '杜林'],
    ['room_1_3', null, '空构']
  ])
    Object.assign(workspace.mainPlan.facilities[roomId], {
      level: 3,
      ...(product ? { product } : {}),
      slots: [{ occupant: { kind: 'operator', operatorId }, groupId: null, replacements: [] }]
    })
  workspace.compatibility.unrecognizedFields.advanced_settings = {
    product_switching: { enable: true, grandet_mode: false, waiting_seconds: 0 }
  }
  const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
  const state = createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
  state.config.mowerDroneRoom = 'room_1_1'
  const desiredProducts = { room_1_1: 'exp3', room_1_2: 'gold' }
  const frame = (offset = 0) => {
    const config = projectScheduleState(schedule, state)
    const active = new Set(Object.keys(state.morale))
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
          {
            ...evaluateOperators(room, config, active, morale),
            // Manufacturing stays at 100%; Spuria's supported curve adds one point per hour.
            efficiencyPercent: room.type === 'power' ? 120 + Math.min(5, state.time + offset) : 100
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
      outputMode: 'potential',
      droneTarget: 'exp',
      droneRoomId: 'room_1_1'
    },
    0,
    () => {}
  )
  production.settle(frame)
  desiredProducts.room_1_1 = 'gold'
  production.settle(frame)
  expect(production.report().expected.pendingSwitchDrones).toBe(60)
  while (state.time < 8 - 1e-10) {
    const duration = production.nextStep(Math.min(1, 8 - state.time), frame)
    expect(duration).toBeGreaterThan(0)
    production.advance(duration, frame(duration / 2))
    state.time += duration
    production.settle(frame)
  }
  const report = production.report()
  const physicalGold =
    report.ledger.balances.gold +
    report.manufacturing.reduce((total, room) => total + (72 - room.remainingBaseMinutes) / 72, 0)
  expect(report.expected.pendingSwitchDrones).toBe(0)
  expect(
    report.expected.output.gold,
    JSON.stringify({ physicalGold, expected: report.expected })
  ).toBeCloseTo(physicalGold, 8)
})
