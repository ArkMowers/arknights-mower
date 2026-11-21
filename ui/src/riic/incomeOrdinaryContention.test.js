import process from 'node:process'
import { expect, it } from 'vitest'
import plan from './fixtures/income-shared-ordinary-contention.json'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'
import { planMowerOrdinary } from './vendor/scheduler/mowerOrdinaryPlanning'
import { projectMowerArrangements } from './vendor/scheduler/mowerObservations'
import { MowerOperatorState } from './vendor/scheduler/mowerOperatorState'
import { MowerDormState, MowerSchedulingData } from './vendor/scheduler/mowerSchedulingData'
import {
  MowerTaskQueue,
  MOWER_TASK_TYPES as T,
  toMowerMicros
} from './vendor/scheduler/mowerTaskQueue'

function contention(alternate = false) {
  const data = new MowerSchedulingData({
    alpha: true,
    nowMicros: 0,
    policy: { restingThreshold: 0.6 },
    operators: {
      A: new MowerOperatorState({
        name: 'A',
        room: 'room_1_1',
        index: 0,
        currentRoom: 'room_1_1',
        currentIndex: 0,
        operatorType: 'high',
        replacement: ['X'],
        mood: 12,
        timeStampMicros: 0
      }),
      B: new MowerOperatorState({
        name: 'B',
        room: 'room_1_2',
        index: 0,
        currentRoom: 'dormitory_1',
        currentIndex: 0,
        operatorType: 'high',
        replacement: alternate ? ['X', 'Y'] : ['X'],
        restInFull: true,
        mood: 8,
        timeStampMicros: 0
      }),
      X: new MowerOperatorState({
        name: 'X',
        currentRoom: 'room_1_2',
        currentIndex: 0,
        mood: 24,
        timeStampMicros: 0
      }),
      ...(alternate
        ? { Y: new MowerOperatorState({ name: 'Y', mood: 24, timeStampMicros: 0 }) }
        : {})
    },
    plan: { room_1_1: ['A'], room_1_2: ['B'], dormitory_1: ['Free', 'Free'] },
    dorms: [
      new MowerDormState(['dormitory_1', 0], 'B', toMowerMicros(4)),
      new MowerDormState(['dormitory_1', 1])
    ]
  })
  return { data, queue: new MowerTaskQueue() }
}

it('leaves ordinary contention in planning until the shared cover is released', () => {
  const { data, queue } = contention()
  for (let run = 0; run < 3; run++) {
    expect(planMowerOrdinary(data, queue)).toEqual({})
    expect(queue.tasks.some((task) => task.type === T.EXHAUST_OFF || task.exhaustSupport)).toBe(
      false
    )
    expect(data.operators.A.currentRoom).toBe('room_1_1')
    expect(data.operators.B.currentRoom).toBe('dormitory_1')
    expect(data.operators.X.currentRoom).toBe('room_1_2')
  }
  const released = projectMowerArrangements(data, [{ room_1_2: ['B'] }])
  released.operators.B.mood = 24
  const departure = planMowerOrdinary(released, queue)
  expect(departure.room_1_1).toEqual(['X'])
  expect(departure.dormitory_1).toContain('A')
  expect(
    queue.tasks.some((task) => task.type === T.SHIFT_OFF && task.plan.room_1_1?.[0] === 'X')
  ).toBe(true)
})

it('queues only a complete available handoff and preserves the resting primary', () => {
  const { data, queue } = contention(true)
  planMowerOrdinary(data, queue)
  const support = queue.tasks.find((task) => task.exhaustSupport)
  expect(support?.type).toBe(T.SELF_CORRECTION)
  expect(support?.plan).toEqual({ room_1_2: ['Y'] })
  expect(support?.ordinaryCoordination).toBe(true)
  expect(support?.coordinationRequestNames).toEqual(['A'])
  expect(queue.tasks.some((task) => task.type === T.EXHAUST_OFF)).toBe(false)
  expect(data.operators.B.currentRoom).toBe('dormitory_1')
  const confirmed = projectMowerArrangements(data, [support.plan])
  const departure = planMowerOrdinary(confirmed, new MowerTaskQueue())
  expect(departure.room_1_1).toEqual(['X'])
  expect(departure.dormitory_1).toContain('A')
  expect(confirmed.operators.B.currentRoom).toBe('dormitory_1')
})

it('finishes the supplied shared-group plan beyond the former theoretical-clock loop', () => {
  const sampleDays = process.env.MOWER_INCOME_LONG_TEST === '1' ? 28 : 4
  const original = structuredClone(plan)
  const result = calculateIncome(plan, {
    ...defaultIncomeSettings(),
    expectationMode: true,
    warmupDays: 3,
    sampleDays,
    operatorMode: 'maximum',
    inventorySource: 'manual',
    weightMode: 'custom'
  })
  expect(result.success, result.error).toBe(true)
  expect(result.observedHours).toBeCloseTo(sampleDays * 24, 6)
  expect(result.simulationReport.elapsedHours).toBeCloseTo((sampleDays + 3) * 24, 6)
  expect(result.simulationReport.production.success).toBe(true)
  expect(result.simulationReport.events.some((event) => event.type === 'fiammetta')).toBe(true)
  expect(plan).toEqual(original)
}, 1200000)
