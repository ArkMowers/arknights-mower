import { expect, it } from 'vitest'
import { createRosterRuntime, settleRoster, type RuntimeConfig } from './rosterRuntime'
import { getMowerSourceRuntime } from './mowerSourceRuntime'
import { MowerOperatorState } from './mowerOperatorState'
import { MowerDormState, MowerSchedulingData } from './mowerSchedulingData'
import {
  mowerResting,
  mowerGetRestingPlan,
  mowerTryReorder
} from './mowerOrdinaryPlanning'
import { MowerTask, MowerTaskQueue, MOWER_TASK_TYPES as T, type MowerTaskPlan } from './mowerTaskQueue'
import { planMowerAlphaDormFill } from './mowerAlphaCandidates'
import { projectMowerArrangements } from './mowerObservations'

function fixture() {
  const op = (name:string, room:string, index:number, group = '', replacement:string[] = [], mood = 5) =>
    new MowerOperatorState({
      name,
      room,
      index,
      group,
      replacement,
      mood,
      currentRoom: room,
      currentIndex: index,
      timeStampMicros: 0,
      operatorType: room ? 'high' : 'low',
      restingPriority: 'high'
    })
  const operators = {
    A: op('A', 'room_1_1', 0, 'first', ['X']),
    B: op('B', 'room_1_2', 0, 'second', ['Y']),
    F: op('F', 'dormitory_1', 0, 'first', ['Free'], 24),
    X: op('X', '', -1, '', [], 24),
    Y: op('Y', '', -1, '', [], 24)
  }
  operators.F.groupBindings = [
    { group: 'first', replacement: ['Free'] },
    { group: 'third', replacement: ['Free'] }
  ]
  const data = new MowerSchedulingData({
    alpha: true,
    nowMicros: 0,
    operators,
    plan: { room_1_1: ['A'], room_1_2: ['B'], dormitory_1: ['F', 'Free', 'Free'] },
    dorms: [
      new MowerDormState(['dormitory_1', 0], '', undefined, true),
      new MowerDormState(['dormitory_1', 1]),
      new MowerDormState(['dormitory_1', 2])
    ]
  })
  return data
}

it('keeps earlier group admissions when another group opens shared dorm slots in the same round', () => {
  const data = fixture()
  const plan:MowerTaskPlan = {},
    replacements:string[] = []
  const options = { dormAdmissions: new Map<string,string>() }
  expect(mowerGetRestingPlan(data, ['A', 'F'], replacements, plan, options)).toBe(true)
  expect(mowerGetRestingPlan(data, ['B'], replacements, plan, options)).toBe(true)
  const reorder = mowerTryReorder(data, plan)
  const final = projectMowerArrangements(data, [plan, reorder ?? {}])
  expect(final.operators.A!.currentRoom).toBe('dormitory_1')
  expect(final.operators.B!.currentRoom).toBe('dormitory_1')
  expect(final.operators.A!.currentIndex).not.toBe(final.operators.B!.currentIndex)
  expect(final.currentOperator('room_1_1', 0)?.name).toBe('X')
  expect(final.currentOperator('room_1_2', 0)?.name).toBe('Y')
})

it('retains both groups through the real ordinary planning round', () => {
  const data = fixture(),
    queue = new MowerTaskQueue()
  const plan = mowerResting(data, queue)
  const reorder = mowerTryReorder(data, plan)
  const final = projectMowerArrangements(data, [plan, reorder ?? {}])
  expect(queue.tasks).toHaveLength(1)
  expect(queue.tasks[0]!.plan).toBe(plan)
  expect(final.operators.A!.currentRoom).toBe('dormitory_1')
  expect(final.operators.B!.currentRoom).toBe('dormitory_1')
  expect(final.currentOperator('room_1_1', 0)?.name).toBe('X')
  expect(final.currentOperator('room_1_2', 0)?.name).toBe('Y')
})

it('releases a completed dynamic primary bed without recalling its recovering group', () => {
  const make = (
    name:string,
    room:string,
    index:number,
    mood:number,
    currentRoom:string,
    currentIndex:number,
    group = '',
    operatorType:'high'|'low' = 'high',
    replacement:string[] = []
  ) =>
    new MowerOperatorState({
      name,
      room,
      index,
      mood,
      currentRoom,
      currentIndex,
      group,
      operatorType,
      replacement,
      restingPriority: 'high',
      timeStampMicros: 0
    })
  const operators = {
    A: make('A', 'room_1_1', 0, 24, 'dormitory_1', 0, 'g', 'high', ['X']),
    B: make('B', 'room_1_1', 1, 5, 'dormitory_1', 1, 'g', 'high', ['Y']),
    X: make('X', '', -1, 24, 'room_1_1', 0, '', 'low'),
    Y: make('Y', '', -1, 24, 'room_1_1', 1, '', 'low'),
    L: make('L', '', -1, 10, '', -1, '', 'low')
  }
  const data = new MowerSchedulingData({
    alpha: true,
    freeRoom: true,
    plan: { room_1_1: ['A', 'B'], dormitory_1: ['Free', 'Free'] },
    operators,
    dorms: [
      new MowerDormState(['dormitory_1', 0], 'A', 0),
      new MowerDormState(['dormitory_1', 1], 'B', 10 * 3_600_000_000)
    ],
    nowMicros: 0,
    groupShiftState: { g: true }
  })
  const queue = new MowerTaskQueue(),
    task = planMowerAlphaDormFill(data, queue)
  expect(task?.plan.room_1_1).toBeUndefined()
  const projected=projectMowerArrangements(data,[task!.plan])
  expect(projected.operators.A!.currentRoom).toBe('')
  expect(projected.operators.B!.isResting()).toBe(true)
  expect(projected.operators.L!.isResting()).toBe(true)
  expect(projected.groupIsResting('g')).toBe(true)
  expect(data.operators.A!.currentRoom).toBe('dormitory_1')
  expect(data.operators.B!.currentRoom).toBe('dormitory_1')
  expect(data.currentOperator('room_1_1', 1)?.name).toBe('Y')
})

function releaseObservationFixture({ merged = false, future = false, strict = false } = {}) {
  const config:RuntimeConfig = {
    mowerAlpha: true,
    mowerRunOrderEnabled: false,
    positions: [
      { id: 'room_1_1_0', roomId: 'room_1_1', primary: 'A', group: 'g', candidates: ['X'] },
      { id: 'room_1_1_1', roomId: 'room_1_1', primary: 'B', group: 'g', candidates: ['Y'] }
    ],
    beds: [
      { id: 'dormitory_1_0', roomId: 'dormitory_1', vip: true },
      { id: 'dormitory_1_1', roomId: 'dormitory_1', vip: false }
    ],
    initialMorale: { A: 24, B: 5, X: 24, Y: 24, I: 24 },
    idleOperators: ['I'],
    mowerPolicy: { restingThreshold: 0.65, freeRoom: true, opeRestingPriority: [], powerPlantCount: 2 },
    mowerSourceRules: {
      workaholic: [],
      exhaustRequire: [],
      restInFull: [],
      lowPriority: [],
      refreshDrained: [],
      lingMode: 0
    },
    mowerSourcePlan: {
      room_1_1: [
        { agent: 'A', group: 'g', replacement: ['X'] },
        { agent: 'B', group: 'g', replacement: ['Y'] }
      ],
      dormitory_1: [
        { agent: 'Free', group: '', replacement: [] },
        { agent: 'Free', group: '', replacement: [] }
      ]
    }
  }
  const state = createRosterRuntime(config),
    source = getMowerSourceRuntime(state),
    data = source.data
  state.time = 1
  data.nowMicros = 3_600_000_000
  source.initial = false
  source.firstInit = false
  state.occupants = { room_1_1_0: 'X', room_1_1_1: 'Y' }
  state.bedOccupants = { dormitory_1_0: 'A', dormitory_1_1: 'B' }
  for (const [name, room, index] of [
    ['A', 'dormitory_1', 0],
    ['B', 'dormitory_1', 1],
    ['X', 'room_1_1', 0],
    ['Y', 'room_1_1', 1]
  ] as const) {
    const o = data.operators[name]!
    o.currentRoom = room
    o.currentIndex = index
    o.timeStampMicros = 0
  }
  data.operators.A!.mood = 22
  data.operators.A!.depletionRate = 1
  data.operators.B!.mood = 5
  data.dorms[0]!.name = 'A'
  data.dorms[0]!.timeMicros = data.nowMicros + (future ? 3_600_000_000 : 0)
  data.dorms[1]!.name = 'B'
  data.dorms[1]!.timeMicros = data.nowMicros + 4 * 3_600_000_000
  data.groupShiftState.g = true
  const queue = new MowerTaskQueue()
  queue.tasks = [
    new MowerTask({
      time: 1,
      type: T.RELEASE_DORM,
      plan: { dormitory_1: ['Free', 'Current'] },
      metadata: 'A',
      strictMoodLimit: strict,
      moodLimit: strict ? 12 : undefined
    })
  ]
  source.queue = queue

  if (strict) {
    data.operators.A!.upperLimit = 12
    data.operators.A!.restMoodLimit = true
    state.morale.A = 12
    data.operators.A!.mood = 10
  }
  if (merged) {
    queue.tasks[0]!.releaseTargets = { A: ['dormitory_1', 0] }
  }
  return { state, source, data, task: queue.tasks[0]! }
}

it.each([false, true])(
  'observes full recovery before ordinary release at the exact deadline (merged=%s)',
  (merged) => {
    const { state, data } = releaseObservationFixture({ merged })
    settleRoster(state, { workRate: () => 1, recoveryRate: () => 4 })
    expect(data.operators.A!.currentRoom).toBe('')
    expect(data.operators.A!.mood).toBe(24)
    expect(data.operators.A!.timeStampMicros).toBe(3_600_000_000)
    expect(data.operators.A!.depletionRate).toBe(0)
    expect(data.operators.B!.currentRoom).toBe('dormitory_1')
    expect(data.currentOperator('room_1_1', 1)?.name).toBe('Y')
  }
)
it('retains ordinary recovery until its observed future deadline', () => {
  const { state, data, source } = releaseObservationFixture({ future: true })
  state.morale.A = 22
  settleRoster(state, { workRate: () => 1, recoveryRate: () => 4 })
  expect(data.operators.A!.currentRoom).toBe('dormitory_1')
  expect(data.operators.B!.currentRoom).toBe('dormitory_1')
  const release = source.queue.tasks.find(
    (task) => task.type === T.RELEASE_DORM && task.metadata === 'A'
  )
  expect(release?.timeMicros).toBe(2 * 3_600_000_000)
})
it('observes a strict personal limit departure without requiring full morale', () => {
  const { state, data } = releaseObservationFixture({ strict: true })
  settleRoster(state, { workRate: () => 1, recoveryRate: () => 4 })
  expect(data.operators.A!.currentRoom).toBe('')
  expect(data.operators.A!.mood).toBe(12)
  expect(data.operators.A!.timeStampMicros).toBe(3_600_000_000)
  expect(data.operators.A!.depletionRate).toBe(0)
  expect(data.operators.A!.restMoodReleaseLimit).toBe(12)
  expect(data.operators.B!.currentRoom).toBe('dormitory_1')
})

it('admits an idle priority replacement through the real runtime with free room disabled', () => {
  const state = createRosterRuntime({
    mowerAlpha: true,
    mowerRunOrderEnabled: false,
    positions: [{ id: 'room_1_1_0', roomId: 'room_1_1', primary: 'A', candidates: ['R'] }],
    beds: [{ id: 'dormitory_1_0', roomId: 'dormitory_1', vip: true }],
    initialMorale: { A: 24, R: 0, I: 24 },
    idleOperators: ['I'],
    mowerPolicy: { restingThreshold: 0.65, freeRoom: false, opeRestingPriority: [], powerPlantCount: 2 },
    mowerSourceRules: { workaholic: [], exhaustRequire: [], restInFull: [], lowPriority: [],
      refreshDrained: [], lingMode: 0, priorityReplacement: ['R'] },
    mowerSourcePlan: {
      room_1_1: [{ agent: 'A', group: '', replacement: ['R'] }],
      dormitory_1: [{ agent: 'Free', group: '', replacement: [] }]
    }
  })
  const source = getMowerSourceRuntime(state), data = source.data
  source.initial = false
  source.firstInit = false
  state.occupants = { room_1_1_0: 'A' }
  state.bedOccupants = { dormitory_1_0: 'I' }
  data.operators.A!.currentRoom = 'room_1_1'
  data.operators.A!.currentIndex = 0
  data.operators.I!.currentRoom = 'dormitory_1'
  data.operators.I!.currentIndex = 0
  for (const op of Object.values(data.operators)) op.timeStampMicros = 0
  data.operators.R!.mood = 0
  data.dorms[0]!.name = 'I'
  data.dorms[0]!.timeMicros = 0
  settleRoster(state, { workRate: () => 1, recoveryRate: () => 4 })
  expect(state.bedOccupants.dormitory_1_0).toBe('R')
  expect(data.operators.R!.currentRoom).toBe('dormitory_1')
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(data.freeRoom).toBe(false)
})

it.each([false, true])('uses a selected priority cover’s bed without moving actual residents (freeRoom=%s)', freeRoom => {
  const data = fixture()
  data.freeRoom = freeRoom
  data.dorms = [new MowerDormState(['dormitory_1', 1], 'X')]
  data.operators.X!.currentRoom = 'dormitory_1'
  data.operators.X!.currentIndex = 1
  data.operators.X!.mood = 10
  data.priorityReplacement = ['X']
  data.restingPriorityNames = ['X']
  delete data.operators.F
  data.plan.dormitory_1 = ['Free', 'Free', 'Free']
  const before = JSON.stringify(data.operators), plan:MowerTaskPlan = {}, covers:string[] = []
  expect(mowerGetRestingPlan(data, ['A'], covers, plan)).toBe(true)
  expect(plan).toEqual({ room_1_1: ['X'] })
  expect(covers).toEqual(['X'])
  expect(data.dorms[0]!.name).toBe('A')
  expect(JSON.stringify(data.operators)).toEqual(before)
})

it('keeps beds and observations unchanged when departing covers cannot fit the entire group', () => {
  const data = fixture()
  data.dorms = [new MowerDormState(['dormitory_1', 1], 'X')]
  Object.assign(data.operators.X!, { currentRoom: 'dormitory_1', currentIndex: 1, mood: 10 })
  data.priorityReplacement = ['X']
  data.restingPriorityNames = ['X']
  delete data.operators.F
  data.plan.dormitory_1 = ['Free', 'Free', 'Free']
  const before = JSON.stringify({ operators: data.operators, dorms: data.dorms }), plan:MowerTaskPlan = {}, covers:string[] = []
  expect(mowerGetRestingPlan(data, ['A', 'B'], covers, plan)).toBe(false)
  expect(plan).toEqual({})
  expect(covers).toEqual([])
  expect(JSON.stringify({ operators: data.operators, dorms: data.dorms })).toEqual(before)
})
