import { expect, it } from 'vitest'
import { MowerOperatorState } from './vendor/scheduler/mowerOperatorState'
import { MowerSchedulingData } from './vendor/scheduler/mowerSchedulingData'
import { MowerTask, MOWER_TASK_TYPES as T } from './vendor/scheduler/mowerTaskQueue'
import { splitMowerRecoveryTask } from './vendor/scheduler/mowerGroupRecovery'

it.each(['ordinary', 'shared', 'source-owner-only'])(
  'retains a working cover with its recovering source group while splitting independent work: %s',
  (kind) => {
    const operators = {
      owner: new MowerOperatorState({
        name: 'owner',
        room: 'room_2_2',
        index: 0,
        group: 'recovering',
        operatorType: 'high',
        currentRoom: 'dormitory_1',
        currentIndex: 2
      }),
      peer: new MowerOperatorState({
        name: 'peer',
        room: 'room_1_1',
        index: 0,
        group: 'recovering',
        operatorType: 'high',
        currentRoom: 'dormitory_1',
        currentIndex: 3
      }),
      cover: new MowerOperatorState({
        name: 'cover',
        room: 'room_3_3',
        index: 0,
        group: 'working',
        operatorType: 'high',
        currentRoom: 'room_2_2',
        currentIndex: 0
      }),
      independent: new MowerOperatorState({
        name: 'independent',
        room: 'room_1_2',
        index: 0,
        group: 'independent',
        operatorType: 'high',
        currentRoom: 'dormitory_1',
        currentIndex: 4
      })
    }
    if (kind !== 'ordinary') {
      operators.cover.groupBindings = [
        { group: 'working', replacement: [] },
        { group: 'recovering', replacement: [] }
      ]
      operators.cover.shiftGroup = 'working'
    }
    const data = new MowerSchedulingData({
      alpha: true,
      operators,
      plan: {
        room_2_2: ['owner'],
        room_1_1: ['peer'],
        room_3_3: ['cover'],
        room_1_2: ['independent'],
        dormitory_1: ['Free', 'Free', 'Free', 'Free', 'Free']
      },
      nowMicros: 0,
      groupShiftState: { recovering: true, working: false }
    })
    const plan = {
      room_3_3: ['cover'],
      room_1_2: ['independent'],
      ...(kind === 'source-owner-only' ? {} : { room_1_1: ['peer'] })
    }
    const task = new MowerTask({ time: 2, type: T.SHIFT_ON, plan })
    const pending = []
    splitMowerRecoveryTask(data, task, pending, ['owner'], true)
    expect(task.time).toBe(2)
    expect(task.plan.room_3_3).toEqual(['cover'])
    expect(task.plan.room_1_2).toBeUndefined()
    expect(pending).toHaveLength(1)
    expect(pending[0].time).toBe(2)
    expect(pending[0].plan).toEqual({ room_1_2: ['independent'] })
  }
)

it('does not derive an orphan cover return while its current source owner is waiting for recovery', async () => {
  const { MowerDormState } = await import('./vendor/scheduler/mowerSchedulingData')
  const { MowerTaskQueue } = await import('./vendor/scheduler/mowerTaskQueue')
  const { planMowerAlphaMetadata } = await import('./vendor/scheduler/mowerAlphaMetadata')
  const operators = {
    owner: new MowerOperatorState({
      name: 'owner',
      room: 'room_2_2',
      index: 0,
      group: 'recovering',
      operatorType: 'high',
      currentRoom: 'dormitory_1',
      currentIndex: 2,
      mood: 18,
      timeStampMicros: 0
    }),
    cover: new MowerOperatorState({
      name: 'cover',
      room: 'room_3_3',
      index: 0,
      group: 'working',
      groupBindings: [
        { group: 'working', replacement: ['spare'] },
        { group: 'recovering', replacement: ['spare'] }
      ],
      operatorType: 'high',
      currentRoom: 'room_2_2',
      currentIndex: 0,
      timeStampMicros: 0
    }),
    independent: new MowerOperatorState({
      name: 'independent',
      room: 'room_1_2',
      index: 0,
      group: 'independent',
      operatorType: 'high',
      currentRoom: 'dormitory_1',
      currentIndex: 3,
      timeStampMicros: 0
    }),
    spare: new MowerOperatorState({ name: 'spare', currentRoom: 'room_3_3', currentIndex: 0 })
  }
  operators.cover.shiftGroup = 'working'
  const data = new MowerSchedulingData({
    alpha: true,
    operators,
    plan: {
      room_2_2: ['owner'],
      room_3_3: ['cover'],
      room_1_2: ['independent'],
      dormitory_1: ['Free', 'Free', 'Free', 'Free', 'Free']
    },
    dorms: [
      new MowerDormState(['dormitory_1', 2], 'owner', 7200000000),
      new MowerDormState(['dormitory_1', 3], 'independent', 0)
    ],
    nowMicros: 0,
    groupShiftState: { recovering: true, working: false, independent: true },
    waitingRecoveryNames: new Set(['owner']),
    groupRestInFullOnMoodGap: false
  })
  const queue = new MowerTaskQueue()
  planMowerAlphaMetadata(data, queue, [])
  expect(
    queue.tasks.some(
      (task) => task.type === T.SHIFT_ON && Object.values(task.plan).flat().includes('cover')
    )
  ).toBe(false)
  expect(
    queue.tasks.some(
      (task) => task.type === T.SHIFT_ON && task.plan.room_1_2?.[0] === 'independent'
    )
  ).toBe(true)
  for (let repeat = 0; repeat < 3; repeat++) {
    planMowerAlphaMetadata(data, queue, [])
    expect(
      queue.tasks.some(
        (task) => task.type === T.SHIFT_ON && Object.values(task.plan).flat().includes('cover')
      )
    ).toBe(false)
  }
  data.waitingRecoveryNames.clear()
  operators.owner.mood = 24
  planMowerAlphaMetadata(data, queue, [])
  expect(
    queue.tasks.some(
      (task) =>
        task.type === T.SHIFT_ON &&
        task.plan.room_2_2?.[0] === 'owner' &&
        task.plan.room_3_3?.[0] === 'cover'
    )
  ).toBe(true)
})

it.each([false, true])(
  'does not reserve a waiting owner against another independent return or handoff: handoff=%s',
  async (handoff) => {
    const { admitMowerDerivedTasks } = await import('./vendor/scheduler/mowerTaskDerivation')
    const operators = {
      owner: new MowerOperatorState({
        name: 'owner',
        room: 'room_2_2',
        index: 0,
        group: 'recovering',
        replacement: ['cover', 'spare'],
        operatorType: 'high',
        currentRoom: 'dormitory_1',
        currentIndex: 2
      }),
      cover: new MowerOperatorState({
        name: 'cover',
        room: 'room_3_3',
        index: 0,
        group: 'working',
        operatorType: 'high',
        currentRoom: 'room_2_2',
        currentIndex: 0
      }),
      spare: new MowerOperatorState({ name: 'spare' })
    }
    const data = new MowerSchedulingData({
      alpha: true,
      operators,
      plan: { room_2_2: ['owner'], room_3_3: ['cover'] },
      nowMicros: 0,
      waitingRecoveryNames: new Set(['owner'])
    })
    const plan = { room_3_3: ['cover'], ...(handoff ? { room_2_2: ['spare'] } : {}) }
    const task = new MowerTask({ time: 2, type: T.SHIFT_ON, plan })
    expect(admitMowerDerivedTasks(data, [], [task])).toEqual([task])
    expect(task.plan).toEqual(plan)
    expect(task.time).toBe(2)
  }
)

it('removes a chain of cover movements dependent on a removed return without trimming independent work', async () => {
  const { admitMowerDerivedTasks } = await import('./vendor/scheduler/mowerTaskDerivation')
  const operators = Object.fromEntries(
    [
      ['owner', 'room_2_2', 'dormitory_1', 'recovering'],
      ['first', 'room_3_3', 'room_2_2', 'working'],
      ['second', 'room_1_1', 'room_3_3', 'other'],
      ['independent', 'room_1_2', 'dormitory_1', 'independent']
    ].map(([name, room, currentRoom, group]) => [
      name,
      new MowerOperatorState({
        name,
        room,
        index: 0,
        group,
        operatorType: 'high',
        currentRoom,
        currentIndex: 0
      })
    ])
  )
  const data = new MowerSchedulingData({
    alpha: true,
    operators,
    plan: {
      room_2_2: ['owner'],
      room_3_3: ['first'],
      room_1_1: ['second'],
      room_1_2: ['independent']
    },
    nowMicros: 0,
    waitingRecoveryNames: new Set(['owner'])
  })
  const task = new MowerTask({
    type: T.SHIFT_ON,
    plan: {
      room_1_1: ['second'],
      room_3_3: ['first'],
      room_2_2: ['owner'],
      room_1_2: ['independent']
    }
  })
  expect(admitMowerDerivedTasks(data, [], [task])).toEqual([task])
  expect(task.plan).toEqual({ room_1_2: ['independent'] })
  expect(operators.first.currentRoom).toBe('room_2_2')
  expect(operators.second.currentRoom).toBe('room_3_3')
})
