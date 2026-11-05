import { expect, it } from 'vitest'
import {
  createRosterRuntime,
  settleRoster,
  advanceRoster,
  nextRosterActionHours
} from './vendor/scheduler/rosterRuntime'
import { getMowerSourceRuntime } from './vendor/scheduler/mowerSourceRuntime'
import { MowerTask, MOWER_TASK_TYPES as T } from './vendor/scheduler/mowerTaskQueue'

const rates = { workRate: () => 1, recoveryRate: () => 4 }
function fixture() {
  const keepers = ['K1', 'K2', 'K3', 'K4']
  return createRosterRuntime({
    mowerTheoreticalMode: true,
    mowerRunOrderEnabled: false,
    mowerTaskScheduling: { adjustForRunOrders: false },
    mowerDeviceTiming: { roomReturnMicros: 0 },
    positions: [
      {
        id: 'room_1_1_0',
        roomId: 'room_1_1',
        primary: 'A',
        candidates: ['R'],
        lowerLimit: 0,
        upperLimit: 24,
        shiftOffThreshold: 15
      },
      ...keepers.map((name, index) => ({
        id: 'dormitory_1_' + index,
        roomId: 'dormitory_1',
        primary: name,
        candidates: [],
        permanent: true,
        dormitory: true
      }))
    ],
    beds: [{ id: 'dormitory_1_4', roomId: 'dormitory_1', vip: true }],
    initialMorale: { A: 24, R: 24 },
    idleOperators: [],
    mowerPolicy: { restingThreshold: 0.65, powerPlantCount: 2, opeRestingPriority: [] },
    mowerSourcePlan: {
      room_1_1: [{ agent: 'A', group: '', replacement: ['R'] }],
      dormitory_1: [
        ...keepers.map((agent) => ({ agent, group: '', replacement: [] })),
        { agent: 'Free', group: '', replacement: [] }
      ]
    },
    mowerSourceRules: {
      workaholic: [],
      exhaustRequire: [],
      restInFull: [],
      lowPriority: [],
      refreshDrained: [],
      lingMode: 0
    }
  })
}

it('keeps an idle theoretical run asleep until its mood dependency without adding fallback polls', () => {
  const state = fixture()
  settleRoster(state, rates)
  const source = getMowerSourceRuntime(state)
  const deadline = nextRosterActionHours(state, rates)
  expect(deadline).toBeGreaterThan(2.5)
  expect(deadline).toBeLessThan(24)
  const traceLength = source.trace.length
  for (let index = 0; index < 3; index++) {
    settleRoster(state, rates)
    expect(source.trace).toHaveLength(traceLength)
    expect(nextRosterActionHours(state, rates)).toBeCloseTo(deadline, 9)
    expect(source.queue.tasks.some((task) => task.type === T.NOT_SPECIFIC)).toBe(false)
  }
  advanceRoster(state, deadline, rates)
  settleRoster(state, rates)
  expect(state.time).toBeCloseTo(deadline, 9)
  expect(state.occupants.room_1_1_0).toBe('R')
  expect(state.bedOccupants.dormitory_1_4).toBe('A')
  expect(source.execution).toBeUndefined()
  expect(source.phaseExecution).toBeUndefined()
  expect(nextRosterActionHours(state, rates)).toBeGreaterThan(0)
})

it('executes a due theoretical arrangement without room-return delays or losing an independent future task', () => {
  const state = fixture(),
    source = getMowerSourceRuntime(state)
  const task = new MowerTask({
    type: T.SHIFT_OFF,
    plan: { room_1_1: ['R'], dormitory_1: ['Current', 'Current', 'Current', 'Current', 'A'] }
  })
  const future = new MowerTask({ time: 12, type: T.NOT_SPECIFIC })
  state.morale.A = 10
  source.data.operators.A.mood = 10
  source.queue.tasks = [task, future]
  settleRoster(state, rates)
  expect(state.time).toBe(0)
  expect(state.occupants.room_1_1_0).toBe('R')
  expect(source.queue.tasks).not.toContain(task)
  expect(source.queue.tasks).toContain(future)
  expect(future.time).toBe(12)
  expect(source.execution).toBeUndefined()
})
