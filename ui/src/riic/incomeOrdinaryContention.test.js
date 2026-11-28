import process from 'node:process'
import { expect, it } from 'vitest'
import plan from './fixtures/income-shared-ordinary-contention.json'
import { defaultIncomeSettings } from './income'
import { createRosterRuntime, settleRoster } from './vendor/scheduler/rosterRuntime'
import { getMowerSourceRuntime } from './vendor/scheduler/mowerSourceRuntime'
import { calculateIncome } from './incomeWorker'
import { executeMowerTaskArrangement } from './vendor/scheduler/mowerTaskExecutor'
import { planMowerOrdinary } from './vendor/scheduler/mowerOrdinaryPlanning'
import {
  mowerUpdateDetail,
  projectMowerArrangements,
  shouldMowerReadMood
} from './vendor/scheduler/mowerObservations'
import { MowerOperatorState } from './vendor/scheduler/mowerOperatorState'
import { MowerDormState, MowerSchedulingData } from './vendor/scheduler/mowerSchedulingData'
import {
  fromMowerMicros,
  MowerTask,
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

it.each([
  'rate',
  'countdown',
  'unknown after',
  'unknown between',
  'calculated',
  'calculated zero',
  'calculated recovering',
  'different seat',
  'observed seat',
  'source observed first',
  'projected seat',
  'projected countdown',
  'projected same seat',
  'legacy full mood timer',
  'previous full working mood',
  'crafting primary',
  'crafting primary without cover',
  'prediction and card',
  'unknown',
  'newer card',
  'at floor',
  'above threshold',
  'equal time'
])('allocates the last bed by mood margin with %s', (evidence) => {
  const { data, queue } = contention(true)
  const { A, B, X } = data.operators
  Object.assign(A, { mood: 6, lowerLimit: 4, depletionRate: 0.5 })
  Object.assign(B, {
    mood: 4,
    depletionRate: 2,
    currentRoom: B.room,
    currentIndex: B.index,
    replacement: ['Y']
  })
  X.currentRoom = ''
  data.dorms = [new MowerDormState(['dormitory_1', 0])]
  if (evidence === 'countdown')
    Object.assign(B, { depletionRate: 0.25, exhaustTimeMicros: toMowerMicros(2) })
  const options = {}
  const rateInputs = []
  if (evidence.startsWith('calculated')) {
    data.policy.predictiveMoodControl = true
    const snapshot = { timeMicros: data.nowMicros, values: { A: 6, B: 4, X: 24, Y: 24 } }
    data.calculatedMoodSnapshot = snapshot
    for (const op of Object.values(data.operators)) op.calculatedMoodSnapshot = snapshot
    A.depletionRate = 8
    B.depletionRate = 0.1
    options.coordinationRates = (roster) => {
      rateInputs.push(roster)
      const rate = { calculated: 0.5, 'calculated zero': 0, 'calculated recovering': -0.1 }[
        evidence
      ]
      return { work: { A: rate, B: 2 }, recovery: {} }
    }
  }
  if (evidence.startsWith('unknown ')) {
    data.operators.C = new MowerOperatorState({
      name: 'C',
      operatorType: 'high',
      room: 'room_2_1',
      currentRoom: 'room_2_1',
      index: 0,
      currentIndex: 0,
      mood: evidence === 'unknown after' ? 8 : 3,
      timeStampMicros: 0
    })
    data.plan.room_2_1 = ['C']
  }
  if (evidence === 'different seat') B.currentIndex = 2
  if (evidence === 'prediction and card') {
    A.moodIsPrediction = true
    data.dormMoodEstimates.set('A', [6, 0])
  }
  if (evidence === 'unknown') A.depletionRate = 0
  if (evidence === 'newer card') {
    A.timeStampMicros = -toMowerMicros(5 / 60)
    data.dormMoodEstimates.set('A', [6, 0])
  }
  if (evidence === 'at floor') A.mood = A.lowerLimit
  if (evidence === 'above threshold') Object.assign(B, { mood: 23, depletionRate: 50 })
  if (evidence === 'equal time') B.depletionRate = 1

  if (evidence === 'observed seat' || evidence === 'source observed first') {
    if (evidence === 'source observed first') {
      B.currentRoom = ''
      B.currentIndex = -1
      B.timeStampMicros = undefined
    } else B.currentIndex = 2
    B.exhaustTimeMicros = 1
    expect(shouldMowerReadMood(data, 'B', B.room, B.index, [])).toBe(true)
    mowerUpdateDetail(data, 'B', B.mood, B.room, B.index, true, new Set([B.room]))
    expect(B.exhaustTimeMicros).toBeUndefined()
    expect(B.depletionRate).toBe(0)
  }
  let planning = data
  if (evidence.startsWith('projected ')) {
    if (evidence !== 'projected same seat') B.currentIndex = 2
    if (evidence === 'projected countdown') B.exhaustTimeMicros = toMowerMicros(1 / 60)
    planning = projectMowerArrangements(projectMowerArrangements(data, [{ [B.room]: ['B'] }]), [])
    expect(B.currentIndex).toBe(evidence === 'projected same seat' ? 0 : 2)
  }
  if (evidence === 'previous full working mood') {
    const previousTime = -toMowerMicros(3)
    Object.assign(A, { mood: 7.5, timeStampMicros: previousTime })
    Object.assign(B, { mood: 24, timeStampMicros: previousTime, lowerLimit: 8, depletionRate: 0.5 })
    mowerUpdateDetail(data, 'A', 6, A.room, A.index, true)
    mowerUpdateDetail(data, 'B', 12, B.room, B.index, true)
    expect([A.depletionRate, B.depletionRate]).toEqual([0.5, 0.5])
  }
  if (evidence === 'legacy full mood timer') {
    Object.assign(A, {
      mood: 24,
      lowerLimit: 19,
      depletionRate: 1,
      timeStampMicros: -toMowerMicros(2),
      exhaustTimeMicros: -toMowerMicros(2) + 2000
    })
    B.depletionRate = 4
  }
  if (evidence.startsWith('crafting primary')) {
    B.nativeName = '年'
    B.workshop = true
    B.mood = 1
    if (evidence.endsWith('without cover')) B.replacement = []
  }

  const plan = planMowerOrdinary(planning, queue, options)
  expect(rateInputs).toEqual([])
  const expected = evidence === 'crafting primary' ? 'B' : 'A'
  expect(plan.dormitory_1[0]).toBe(expected)
  expect(plan[expected === 'A' ? A.room : B.room]).toEqual([expected === 'A' ? 'X' : 'Y'])
  expect(plan[expected === 'A' ? B.room : A.room]).toBeUndefined()
})

it.each([
  ['measured rate', true],
  ['calculated rate', true],
  ['at floor', true],
  ['countdown', true],
  ['equal time', false],
  ['unknown', false],
  ['retained', false],
  ['different map entry', false],
  ['resolved Current', true],
  ['unknown Current', false],
  ['conflicting Current', false],
  ['duplicate occupancy', false],
  ['another departing primary', true],
  ['trailing primary', true],
  ['unknown departing primary', false],
  ['unknown alongside an exhausted primary', true],
  ['card only at floor', false],
  ['displayed zero with time left', false],
  ['calculated zero with time left', false],
  ['special departure', false],
  ['positive floor with zero display', true],
  ['model missing but timer known', false],
  ['observed swapped seats', true],
  ['observed in another room', true],
  ['borrowed cover goes idle', false],
  ['workaholic', false],
  ['source first', false]
])('orders confirmations in the generated task using %s', (evidence, fastFirst) => {
  const { data, queue } = contention(true)
  const { A, B, X, Y } = data.operators
  Object.assign(A, { mood: 6, lowerLimit: 4, depletionRate: 0.5 })
  const oldRoom = B.room,
    room = evidence === 'different map entry' ? 'room_2_1' : 'room_3_1'
  data.plan[room] = data.plan[oldRoom]
  delete data.plan[oldRoom]
  Object.assign(B, {
    room,
    currentRoom: room,
    currentIndex: 0,
    mood: 4,
    lowerLimit: 0,
    depletionRate: 2,
    replacement: ['Y']
  })
  Object.assign(X, { currentRoom: '', currentIndex: -1 })
  data.dorms = [new MowerDormState(['dormitory_1', 0]), new MowerDormState(['dormitory_1', 1])]
  const plan = planMowerOrdinary(data, queue)
  const task = queue.tasks.find((task) => task.type === T.SHIFT_OFF)
  expect(task.plan).toBe(plan)
  expect(Object.keys(plan)).toEqual([A.room, B.room, 'dormitory_1'])
  expect([plan[A.room], plan[B.room]]).toEqual([['X'], ['Y']])
  expect(new Set(plan.dormitory_1)).toEqual(new Set(['A', 'B']))
  const workRates = { A: 0.5, B: 2 }
  if (evidence === 'equal time') B.depletionRate = 1
  if (evidence === 'unknown') B.depletionRate = 0
  if (evidence === 'at floor') {
    B.mood = 0
    B.depletionRate = 0
  }
  if (evidence === 'countdown') {
    B.exhaustTimeMicros = toMowerMicros(1)
    B.depletionRate = 0.1
  }
  if (evidence === 'retained') task.executionRetained = true
  if (evidence === 'card only at floor') {
    B.timeStampMicros = undefined
    data.dormMoodEstimates.set(B.name, [0, data.nowMicros])
  }
  if (evidence.endsWith('zero with time left')) {
    A.depletionRate = workRates.A = 8
    B.mood = 0
    B.exhaustTimeMicros = toMowerMicros(0.5)
  }
  if (evidence === 'calculated rate' || evidence === 'calculated zero with time left') {
    data.policy.predictiveMoodControl = true
    data.calculatedMoodSnapshot = { timeMicros: 0, values: { A: A.mood, B: B.mood } }
    A.depletionRate = 10
    B.depletionRate = 0.1
  }
  if (evidence.endsWith('Current')) {
    plan[B.room].push('Current')
    if (evidence !== 'unknown Current')
      data.operators.C = new MowerOperatorState({ name: 'C', currentRoom: B.room, currentIndex: 1 })
  }
  if (evidence === 'conflicting Current') plan.dormitory_1.push('C')
  if (evidence === 'duplicate occupancy')
    data.operators.C = new MowerOperatorState({ name: 'C', currentRoom: B.room, currentIndex: 0 })
  if (evidence.endsWith('primary')) {
    const known = evidence === 'another departing primary'
    B.depletionRate = 0.5
    if (evidence === 'unknown alongside an exhausted primary') B.mood = 0
    data.operators.C = new MowerOperatorState({
      name: 'C',
      room: B.room,
      index: 1,
      currentRoom: B.room,
      currentIndex: 1,
      operatorType: 'high',
      mood: 3,
      depletionRate: known ? 6 : 0,
      timeStampMicros: 0
    })
    plan[B.room].push('Z')
    plan.dormitory_1.push('C')
  }
  if (evidence === 'trailing primary') {
    B.depletionRate = 0.5
    data.operators.C = new MowerOperatorState({
      name: 'C',
      room: B.room,
      index: 1,
      currentRoom: B.room,
      currentIndex: 1,
      operatorType: 'high',
      mood: 1,
      depletionRate: 4,
      timeStampMicros: 0
    })
    plan.dormitory_1.push('C')
  }
  if (evidence === 'special departure') task.ordinaryCoordination = false
  if (evidence === 'positive floor with zero display') {
    A.depletionRate = 8
    Object.assign(B, { mood: 0, lowerLimit: 4, exhaustTimeMicros: toMowerMicros(0.75) })
  }
  if (evidence === 'model missing but timer known') {
    data.policy.predictiveMoodControl = true
    data.calculatedMoodSnapshot = { timeMicros: 0, values: { A: 6 } }
    workRates.A = 8
    Object.assign(B, { mood: 0, exhaustTimeMicros: toMowerMicros(0.75) })
    // B101 must be allowed to overtake B301 using its observed timer alone.
    const first = plan[A.room]
    delete plan[A.room]
    plan[A.room] = first
  }
  if (evidence === 'observed in another room' || evidence === 'borrowed cover goes idle') {
    A.lowerLimit = 0
    data.nowMicros -= toMowerMicros(1)
    mowerUpdateDetail(data, 'A', 6, B.room, 0, true)
    mowerUpdateDetail(data, 'B', 3.5, A.room, 0, true)
    data.nowMicros += toMowerMicros(1)
    mowerUpdateDetail(data, 'A', 1, B.room, 0, true)
    mowerUpdateDetail(data, 'B', 3, A.room, 0, true)
    expect([A.depletionRate, B.depletionRate]).toEqual([5, 0.5])
    if (evidence === 'borrowed cover goes idle')
      plan.dormitory_1[plan.dormitory_1.indexOf('A')] = 'Free'
  }
  if (evidence === 'observed swapped seats' || evidence === 'workaholic') {
    const swap = evidence === 'observed swapped seats'
    B.currentIndex = swap ? 1 : 0
    if (!swap) B.depletionRate = 0.5
    data.operators.C = new MowerOperatorState({
      name: 'C',
      room: B.room,
      index: 1,
      currentRoom: B.room,
      currentIndex: swap ? 0 : 1,
      operatorType: 'high',
      timeStampMicros: 0,
      mood: swap ? 4 : 0,
      depletionRate: 1,
      workaholic: !swap
    })
    plan[B.room].push('Z')
    if (swap) plan.dormitory_1.push('C')
  }
  if (evidence === 'source first') {
    Y.currentRoom = A.room
    Y.currentIndex = 1
  }
  const original = structuredClone(plan),
    time = task.timeMicros,
    confirmed = []
  expect(
    executeMowerTaskArrangement(task, queue, {
      alpha: true,
      currentRoom: (name) => data.operators[name]?.currentRoom,
      handoff: { data, workRate: (name) => workRates[name] },
      backup: () => ({ changed: false, generated: [] }),
      metadata() {},
      arrangeRoom(room, names) {
        confirmed.push([room, [...names]])
      }
    })
  ).toBe(true)
  expect(confirmed.map(([room]) => room)).toEqual([
    ...(fastFirst ? [B.room, A.room] : [A.room, B.room]),
    'dormitory_1'
  ])
  expect(Object.fromEntries(confirmed)).toEqual(original)
  expect(task.timeMicros).toBe(time)
  expect(task.plan).toEqual({})
})

it.each([
  [['contact', 'room_1_3', 'recycle', 'meeting'], [3, 1, 2, 4], ['room_2_1']],
  [
    ['contact', 'meeting', 'recycle'],
    [3, 1, 2],
    ['room_2_1', 'room_1_3']
  ],
  [['contact', 'recycle', 'central'], [3, 2, 1], [], ['recycle', 'contact', 'central']]
])(
  'keeps the drag budget when run orders may interrupt %j',
  (rooms, hours, interruptions, preferred = rooms) => {
    const { data, queue } = contention(true)
    const names = ['A', 'B', 'C', 'D'].slice(0, rooms.length)
    data.operators = Object.fromEntries(
      rooms.map((room, i) => {
        const name = names[i]
        return [
          name,
          new MowerOperatorState({
            name,
            room,
            currentRoom: room,
            index: 0,
            currentIndex: 0,
            operatorType: 'high',
            timeStampMicros: 0,
            mood: hours[i],
            depletionRate: 1
          })
        ]
      })
    )
    const plan = Object.fromEntries(rooms.map((room, i) => [room, [['X', 'Y', 'Z', 'W'][i]]]))
    plan.dormitory_1 = names
    const task = new MowerTask({ type: T.SHIFT_OFF, plan })
    task.ordinaryCoordination = true
    queue.tasks.push(task)
    const visits = []
    const hooks = {
      alpha: true,
      currentRoom: (name) => data.operators[name]?.currentRoom,
      handoff: { data, workRate: () => 1 },
      backup: () => ({ changed: false, generated: [] }),
      metadata() {},
      deferRoom: () => visits.length % 2 === 1 && visits.length < 2 * interruptions.length,
      arrangeRoom: (room) => {
        visits.push(room)
      }
    }
    const deadline = task.timeMicros
    for (const stop of interruptions) {
      expect(executeMowerTaskArrangement(task, queue, hooks)).toBe(false)
      visits.push(stop)
    }
    expect(executeMowerTaskArrangement(task, queue, hooks)).toBe(true)
    expect(visits).toEqual([
      ...preferred.flatMap((room, i) => (interruptions[i] ? [room, interruptions[i]] : [room])),
      'dormitory_1'
    ])
    expect(task.timeMicros).toBe(deadline)
    expect(task.plan).toEqual({})
  }
)

it.each([
  [2, 'room_3_1'],
  [0.5, 'room_1_1']
])('uses the live roster rate %s at the first simulated handoff', (fastRate, first) => {
  const rooms = ['room_1_1', 'room_3_1']
  const primaries = ['A', 'B'],
    covers = ['X', 'Y']
  const state = createRosterRuntime({
    positions: rooms.map((roomId, i) => ({
      id: `${roomId}_0`,
      roomId,
      primary: primaries[i],
      candidates: [covers[i]],
      lowerLimit: 0,
      upperLimit: 24
    })),
    beds: [0, 1].map((i) => ({ id: `dormitory_1_${i}`, roomId: 'dormitory_1', vip: i === 0 })),
    initialMorale: { A: 2, B: 4, X: 24, Y: 24 },
    idleOperators: [],
    mowerAlpha: true,
    mowerDeviceTiming: { roomReturnMicros: 500000 },
    mowerPolicy: {
      predictiveMoodControl: true,
      restingThreshold: 0.6,
      powerPlantCount: 2,
      opeRestingPriority: []
    },
    mowerSourcePlan: {
      ...Object.fromEntries(
        rooms.map((room, i) => [
          room,
          [{ agent: primaries[i], group: '', replacement: [covers[i]] }]
        ])
      ),
      dormitory_1: [0, 1].map(() => ({ agent: 'Free', group: '', replacement: [] }))
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
  const source = getMowerSourceRuntime(state)
  const task = new MowerTask({
    time: 0,
    type: T.SHIFT_OFF,
    plan: { room_1_1: ['X'], room_3_1: ['Y'], dormitory_1: ['A', 'B'] }
  })
  task.ordinaryCoordination = true
  task.coordinationRequestNames = primaries
  source.queue.tasks = [task]
  const rates = { workRate: (name) => (name === 'B' ? fastRate : 0.5), recoveryRate: () => 4 }
  const order = [first, ...rooms.filter((room) => room !== first), 'dormitory_1']
  for (const room of order) {
    settleRoster(state, rates)
    expect(source.execution?.task).toBe(task)
    expect(source.execution.lastBoundary.room).toBe(room)
    state.time = fromMowerMicros(source.execution.wakeMicros)
  }
  expect(state.occupants).toMatchObject({ room_1_1_0: 'X', room_3_1_0: 'Y' })
  expect(state.bedOccupants).toMatchObject({ dormitory_1_0: 'A', dormitory_1_1: 'B' })
  expect(task.timeMicros).toBe(0)
})

it.each([
  [24, 1, 0, undefined],
  [20, 0, 0, undefined],
  [20, 1, 0, 20],
  [24, 1, 22, 2]
])('reads control-center mood %s at rate %s and floor %s', (mood, rate, floor, hours) => {
  const state = createRosterRuntime({
    positions: [
      {
        id: 'central_0',
        roomId: 'central',
        primary: 'A',
        candidates: ['R'],
        lowerLimit: floor,
        upperLimit: 24,
        shiftOffThreshold: 1
      }
    ],
    beds: [],
    initialMorale: { A: mood, R: 24 },
    mowerMoodLimits: { operators: { A: { lower: floor, upper: 24 } } },
    idleOperators: [],
    mowerAlpha: true,
    mowerPolicy: { restingThreshold: 0.05, powerPlantCount: 2, opeRestingPriority: [] },
    mowerSourcePlan: { central: [{ agent: 'A', group: '', replacement: ['R'] }] },
    mowerSourceRules: {
      workaholic: [],
      exhaustRequire: floor ? ['A'] : [],
      restInFull: [],
      lowPriority: [],
      refreshDrained: [],
      lingMode: 0
    }
  })
  settleRoster(state, { workRate: () => rate, recoveryRate: () => 4 })
  const op = getMowerSourceRuntime(state).data.operators.A
  expect([op.currentRoom, op.mood, op.lowerLimit]).toEqual(['central', mood, floor])
  expect(op.exhaustTimeMicros).toBe(hours === undefined ? undefined : toMowerMicros(hours))
})

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
