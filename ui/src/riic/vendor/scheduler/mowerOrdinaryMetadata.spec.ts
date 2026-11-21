import { afterEach, describe, expect, it, vi } from 'vitest'
import * as metadata from './mowerMetadata'
import { MowerOperatorState } from './mowerOperatorState'
import { mowerResting, planMowerOrdinary } from './mowerOrdinaryPlanning'
import { MowerDormState, MowerSchedulingData } from './mowerSchedulingData'
import { MOWER_TASK_TYPES as T, MowerTask, MowerTaskQueue, toMowerMicros } from './mowerTaskQueue'
import { alphaRestingTier } from './mowerAlphaDorm'

function fixture(alpha = false) {
  const operators = {
    A: new MowerOperatorState({ name: 'A', room: 'room_1_1', index: 0, group: 'g', replacement: ['R1'], operatorType: 'high', restingPriority: 'high', mood: 23, currentRoom: 'dormitory_1', currentIndex: 3, timeStampMicros: 0 }),
    B: new MowerOperatorState({ name: 'B', room: 'room_1_2', index: 0, group: 'g', replacement: ['R2'], operatorType: 'high', restingPriority: 'high', mood: 14, currentRoom: 'dormitory_1', currentIndex: 4, timeStampMicros: 0 }),
    R1: new MowerOperatorState({ name: 'R1', mood: 24, currentRoom: 'room_1_1', currentIndex: 0, timeStampMicros: 0 }),
    R2: new MowerOperatorState({ name: 'R2', mood: 24, currentRoom: 'room_1_2', currentIndex: 0, timeStampMicros: 0 }),
  }
  const data = new MowerSchedulingData({
    alpha, operators,
    plan: { room_1_1: ['A'], room_1_2: ['B'], dormitory_1: ['Free', 'Free', 'Free', 'Free', 'Free'] },
    dorms: [new MowerDormState(['dormitory_1', 3], 'A', toMowerMicros(2)), new MowerDormState(['dormitory_1', 4], 'B', toMowerMicros(4))],
    nowMicros: 0, policy: { restingThreshold: .65 },
  })
  return { data, queue: new MowerTaskQueue(), operators }
}

const taskFields = (queue: MowerTaskQueue) => queue.tasks.map(task => ({
  type: task.type, timeMicros: task.timeMicros, plan: task.plan, metadata: task.metadata,
  strictMoodLimit: task.strictMoodLimit, moodLimit: task.moodLimit, adjusted: task.adjusted,
}))

afterEach(() => vi.restoreAllMocks())

describe('ordinary Mower metadata preparation', () => {
  it('builds default metadata once while retaining the real standalone resting result', () => {
    const reference = fixture()
    const referencePlan = mowerResting(reference.data, reference.queue)
    const { data, queue } = fixture()
    const build = vi.spyOn(metadata, 'planMowerMetadata')
    const plan = planMowerOrdinary(data, queue)
    expect(plan).toEqual(referencePlan)
    expect(taskFields(queue)).toEqual(taskFields(reference.queue))
    expect(queue.tasks).toHaveLength(1)
    expect(queue.tasks[0]!.type).toBe(T.SHIFT_ON)
    expect(queue.tasks[0]!.plan).toEqual({ room_1_1: ['A'], room_1_2: ['B'] })
    expect(queue.tasks[0]!.timeMicros).toBe(toMowerMicros(2) - toMowerMicros(8 / 60))
    expect(build).toHaveBeenCalledTimes(1)
  })

  it('keeps public resting responsible for rebuilding after a dorm deadline changes', () => {
    const { data, queue } = fixture()
    const build = vi.spyOn(metadata, 'planMowerMetadata')
    mowerResting(data, queue)
    const original = queue.tasks[0]!
    const due = original.timeMicros
    data.dorms[0]!.timeMicros! -= 60_000_000
    mowerResting(data, queue)
    expect(build).toHaveBeenCalledTimes(2)
    expect(queue.tasks).toHaveLength(1)
    expect(queue.tasks[0]).not.toBe(original)
    expect(queue.tasks[0]!.timeMicros).toBe(due - 60_000_000)
    expect(queue.tasks[0]!.plan).toEqual(original.plan)
  })

  it('retains standby priority through alpha metadata preparation', () => {
    const { data, queue, operators } = fixture(true)
    data.standbyNames = ['A']
    operators.A.restingPriority = 'standby'
    operators.A.mood = 10
    const actualBuild = metadata.planMowerMetadata
    const observed: number[] = []
    const build = vi.spyOn(metadata, 'planMowerMetadata').mockImplementation((state, tasks) => {
      observed.push(alphaRestingTier(state, 'A'))
      actualBuild(state, tasks)
    })
    planMowerOrdinary(data, queue)
    expect(build).toHaveBeenCalledTimes(2)
    expect(observed).toEqual([4, 4])
    expect(alphaRestingTier(data, 'A')).toBe(4)
    expect(data.canStandby(operators.A)).toBe(true)
  })

  it('keeps the actual metadata guard and queue identity during a protected arrangement', () => {
    const { data, queue } = fixture()
    const active = new MowerTask({ type: T.SELF_CORRECTION, plan: { room_1_1: ['R1'] } })
    active.backupShiftActive = true
    const returning = new MowerTask({ time: 2, type: T.SHIFT_ON, plan: { room_1_1: ['A'] } })
    queue.tasks.push(active, returning)
    const originalQueue = queue.tasks
    const before = taskFields(queue)
    const build = vi.spyOn(metadata, 'planMowerMetadata')
    planMowerOrdinary(data, queue)
    expect(build).toHaveBeenCalledTimes(1)
    expect(queue.tasks).toBe(originalQueue)
    expect(queue.tasks).toEqual([active, returning])
    expect(taskFields(queue)).toEqual(before)
    expect(active.backupShiftActive).toBe(true)
  })
})
