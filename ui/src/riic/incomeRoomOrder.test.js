import { expect, it } from 'vitest'
import { appendFileSync } from 'node:fs'
import process from 'node:process'
import originalPlan from './fixtures/income-21trade-3proviso.json'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'
import {
  mowerArrangementRoomOrder,
  executeMowerTaskArrangementSteps
} from './vendor/scheduler/mowerTaskExecutor'
import { MowerTask, MowerTaskQueue, MOWER_TASK_TYPES as T } from './vendor/scheduler/mowerTaskQueue'

it.each([
  [
    { meeting: ['A'], room_2_3: ['N'] },
    { A: 'room_2_3', N: 'dormitory_1' },
    ['room_2_3', 'meeting']
  ],
  [
    { meeting: ['A'], room_1_1: ['B'], room_3_1: ['N'] },
    { A: 'room_1_1', B: 'room_3_1', N: '' },
    ['room_3_1', 'room_1_1', 'meeting']
  ],
  [{ meeting: ['B'], room_1_1: ['A'] }, { A: 'meeting', B: 'room_1_1' }, ['meeting', 'room_1_1']],
  [
    { dormitory_4: ['A'], meeting: ['N', 'Current'], dormitory_1: ['B'], room_1_1: ['Free'] },
    { N: 'room_3_1' },
    ['meeting', 'room_1_1', 'dormitory_1', 'dormitory_4']
  ]
])('orders pending source workplaces before cross-room moves', (plan, positions, expected) => {
  const original = structuredClone(plan)
  expect(mowerArrangementRoomOrder(plan, (name) => positions[name])).toEqual(expected)
  expect(plan).toEqual(original)
})

it('refills the source through the real room executor before transferring its only occupant', () => {
  const positions = { A: 'room_2_3', N: 'dormitory_1' }
  const task = new MowerTask({
    time: 12,
    type: T.SELF_CORRECTION,
    plan: { meeting: ['A'], room_2_3: ['N'] }
  })
  const other = new MowerTask({ time: 13 })
  const queue = new MowerTaskQueue()
  queue.tasks = [task, other]
  const rooms = []
  const steps = executeMowerTaskArrangementSteps(task, queue, {
    currentRoom: (name) => positions[name],
    backup: () => ({ changed: false, generated: [] }),
    arrangeRoom(room, names) {
      if (room === 'meeting') expect(positions.N).toBe('room_2_3')
      for (const [name, position] of Object.entries(positions))
        if (position === room) positions[name] = ''
      for (const name of names) positions[name] = room
      rooms.push(room)
    },
    metadata() {}
  })
  let next = steps.next()
  while (!next.done) {
    expect(Object.values(positions)).toContain('room_2_3')
    next = steps.next()
  }
  expect(next.value).toBe(true)
  expect(rooms).toEqual(['room_2_3', 'meeting'])
  expect(task.time).toBe(12)
  expect(queue.tasks).toEqual([other])
})

const plan = {
  ...originalPlan,
  advanced_settings: { ...originalPlan.advanced_settings, drone_room: 'room_3_3' }
}

const longRun = process.env.MOWER_ROOM_ORDER_LONG_TEST === '1'
it(
  'keeps the supplied plan staffed through complete cross-room handoffs',
  () => {
    const original = structuredClone(plan)
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      seed: 42,
      warmupDays: longRun ? 3 : 0,
      sampleDays: longRun ? 28 : 1
    })
    expect(result.success, result.error).toBe(true)
    expect(result.observedHours).toBeCloseTo(longRun ? 672 : 24, 6)
    for (const room of result.rooms)
      expect(room.occupiedHours, room.roomId).toBeCloseTo(result.observedHours, 6)
    expect(result.summary.totalScore82).toBeGreaterThan(0)
    expect(plan).toEqual(original)
    if (process.env.MOWER_ROOM_ORDER_TEST_LOG)
      appendFileSync(
        process.env.MOWER_ROOM_ORDER_TEST_LOG,
        JSON.stringify({
          longRun,
          hours: result.observedHours,
          score: result.summary.totalScore82,
          summary: result.summary,
          orders: result.orderDistribution,
          manufacturing: result.simulationReport.production.manufacturing,
          drones: result.simulationReport.production.drones,
          resources: result.resources,
          rooms: result.rooms
        }) + '\n'
      )
  },
  longRun ? 600000 : 30000
)
