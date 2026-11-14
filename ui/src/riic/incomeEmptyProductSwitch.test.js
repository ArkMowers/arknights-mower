import { expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createRosterRuntime } from './vendor/scheduler/rosterRuntime'
import { projectScheduleState } from './vendor/simulator/scheduleSimulation'
import { evaluateOperators } from './vendor/engine/operatorRules'
import { createProductionTimeline } from './vendor/simulator/productionTimeline'

it.each([false, true])(
  'retains a product-switch request without accelerating or polling an empty factory (theoretical=%s)',
  (theoretical) => {
    const workspace = createDefaultWorkspace(),
      roomId = 'room_1_1',
      operatorId = 'char_501_durin'
    for (const room of Object.values(workspace.mainPlan.facilities)) {
      room.level = 0
      room.slots = []
    }
    Object.assign(workspace.mainPlan.facilities[roomId], {
      level: 3,
      product: 'fragment',
      slots: [{ occupant: { kind: 'operator', operatorId }, groupId: null, replacements: [] }]
    })
    workspace.compatibility.unrecognizedFields.advanced_settings = {
      product_switching: {
        enable: true,
        grandet_mode: false,
        waiting_seconds: 0,
        use_drones_when_leaving_orirock: true
      }
    }
    const schedule = compileRosterSchedule(workspace, { idleOperators: [] })
    const state = createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
    let target = 'orirock'
    const frame = () => {
      const config = projectScheduleState(schedule, state)
      const active = new Set(Object.keys(state.morale)),
        morale = new Map(Object.entries(state.morale))
      return {
        time: state.time,
        config,
        active,
        morale,
        desiredProducts: { [roomId]: target },
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
        expectationMode: theoretical,
        theoreticalMode: theoretical,
        outputMode: 'settled',
        inventoryMode: 'finite',
        droneTarget: 'none',
        initialResources: { drone: 40, lmd: 3200, orirock: 4 }
      },
      0,
      () => {},
      !theoretical
    )
    production.settle(frame)
    production.advance(0.25, frame())
    state.time = 0.25
    const started = production.report()
    expect(started.manufacturing[0]).toMatchObject({
      product: 'fragment',
      completedItems: 0,
      remainingBaseMinutes: 45
    })
    expect(started.materialsConsumed).toMatchObject({ lmd: 1600, orirock: 2 })
    expect(started.drones.consumed).toBe(0)

    delete state.occupants[roomId + '_0']
    target = 'gold'
    for (let repeat = 0; repeat < 2; repeat++) {
      production.settle(frame)
      const paused = production.report()
      expect(paused.drones.consumed).toBe(0)
      expect(paused.manufacturing[0]).toMatchObject({
        product: 'fragment',
        completedItems: 0,
        remainingBaseMinutes: 45
      })
      expect(production.nextStep(0.25, frame)).toBe(0.25)
      expect(paused.events.some((event) => event.type === 'product-switch-drone')).toBe(false)
      production.advance(0.25, frame())
      state.time += 0.25
    }

    state.occupants[roomId + '_0'] = operatorId
    production.settle(frame)
    const resumed = production.report()
    expect(resumed.drones.consumed).toBe(theoretical ? 0 : 15)
    if (theoretical) expect(resumed.expected.pendingSwitchDrones).toBe(15)
    expect(resumed.manufacturing[0]).toMatchObject({ product: 'gold', completedItems: 1 })
    expect(resumed.materialsConsumed).toMatchObject({ lmd: 1600, orirock: 2 })
    expect(
      resumed.events.filter(
        (event) =>
          event.type === (theoretical ? 'generated-switch-reserved' : 'product-switch-drone') &&
          event.roomId === roomId
      )
    ).toEqual([expect.objectContaining({ roomId, amount: 15, time: 0.75 })])
    expect(resumed.events.filter((event) => event.type === 'product-switched')).toEqual([
      expect.objectContaining({ roomId, fromProduct: 'orirock', toProduct: 'gold', time: 0.75 })
    ])
  }
)
