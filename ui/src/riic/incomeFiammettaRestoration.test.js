import { expect, it } from 'vitest'
import process from 'node:process'
import plan from './fixtures/income-automation-rest.json'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'
import { advanceRoster, createRosterRuntime, settleRoster } from './vendor/scheduler/rosterRuntime'
import {
  getMowerSourceRuntime,
  makeMowerSchedulingData
} from './vendor/scheduler/mowerSourceRuntime'
import { mowerUpdateDetail, projectMowerArrangements } from './vendor/scheduler/mowerObservations'
import { retainMowerFailedTask } from './vendor/scheduler/mowerTaskFailure'
import { MowerTask, MOWER_TASK_TYPES as T, toMowerMicros } from './vendor/scheduler/mowerTaskQueue'

function fixture(due = 0) {
  const fia = 'char_300_phenxi'
  const keepers = [fia, 'K2', 'K3', 'K4']
  const state = createRosterRuntime({
    mowerAlpha: true,
    mowerTheoreticalMode: true,
    mowerTaskScheduling: { adjustForRunOrders: false, enableMastery: false },
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
      { id: 'central_0', roomId: 'central', primary: 'B', candidates: [], permanent: true },
      ...keepers.map((primary, i) => ({
        id: `dormitory_1_${i}`,
        roomId: 'dormitory_1',
        primary,
        candidates: [],
        permanent: true,
        dormitory: true
      }))
    ],
    beds: [{ id: 'dormitory_1_4', roomId: 'dormitory_1', vip: true }],
    initialMorale: { A: 0, B: 1, R: 24, [fia]: 24 },
    idleOperators: ['X'],
    fiammetta: { operatorId: fia, orderedTargets: ['B'], fool: false, threshold: 21.6 },
    mowerPolicy: { restingThreshold: 0.65, powerPlantCount: 2, opeRestingPriority: [] },
    mowerSourcePlan: {
      room_1_1: [{ agent: 'A', group: '', replacement: ['R'] }],
      central: [{ agent: 'B', group: '', replacement: [] }],
      dormitory_1: [
        ...keepers.map((agent) => ({ agent, group: '', replacement: [] })),
        { agent: 'Free', group: '', replacement: [] }
      ]
    },
    mowerSourceRules: {
      workaholic: ['B'],
      exhaustRequire: ['A'],
      restInFull: ['A'],
      lowPriority: [],
      refreshDrained: [],
      lingMode: 0
    }
  })
  const source = getMowerSourceRuntime(state)
  source.initial = false
  source.firstInit = false
  state.morale[fia] = 24
  for (const [slot, name] of Object.entries(state.occupants)) {
    Object.assign(source.data.operators[name], {
      currentRoom: slot.slice(0, slot.lastIndexOf('_')),
      currentIndex: Number(slot.slice(slot.lastIndexOf('_') + 1)),
      mood: state.morale[name],
      timeStampMicros: 0
    })
  }
  const charge = new MowerTask({
    type: T.FIAMMETTA,
    plan: { dormitory_1: ['B', fia] },
    metadata: 'B'
  })
  const departure = new MowerTask({
    time: due,
    type: T.SHIFT_OFF,
    plan: { room_1_1: ['R'], dormitory_1: [fia, 'K2', 'K3', 'K4', 'A'] }
  })
  const future = new MowerTask({ time: 4, plan: { central: ['Current'] } })
  source.queue.tasks = [charge, departure, future]
  retainMowerFailedTask(
    state,
    source.data,
    departure,
    'Waiting for the charging room observation',
    ['dormitory_1']
  )
  return { state, source, charge, departure, future, fia }
}

it.each([0, -1])(
  'finishes charging restoration before a released departure due at %s hours',
  (due) => {
    const { state, source, departure, future, fia } = fixture(due)
    const originalTime = departure.timeMicros
    source.data.operators.B.depletionRate = 2.3
    settleRoster(state, { workRate: () => 1, recoveryRate: () => 4 })
    expect(state.events.filter((event) => event.type === 'fiammetta')).toHaveLength(1)
    expect(source.trace.slice(0, 3).map((task) => task.type)).toEqual([
      'FIAMMETTA',
      'FIAMMETTA',
      'SHIFT_OFF'
    ])
    expect(state.bedOccupants.dormitory_1_4).toBe('A')
    expect(state.occupants.room_1_1_0).toBe('R')
    expect(state.occupants.central_0).toBe('B')
    expect(source.data.operators.B.depletionRate).toBe(2.3)
    expect(state.occupants.dormitory_1_0).toBe(fia)
    expect(departure.timeMicros).toBe(originalTime)
    expect(source.queue.tasks).not.toContain(departure)
    expect(source.queue.tasks).toContain(future)
    expect(future.time).toBe(4)
    expect(state.diagnostics.filter((d) => d.code === 'mower-task-exception')).toEqual([])
  }
)

it('relearns the working rate from two ordinary readings after charging', () => {
  const { state, source } = fixture()
  const rates = { workRate: () => 1, recoveryRate: () => 4 }
  const target = source.data.operators.B
  target.depletionRate = 2.3
  settleRoster(state, rates)
  expect([target.currentRoom, target.mood, target.depletionRate]).toEqual(['central', 24, 2.3])

  advanceRoster(state, 4, rates)
  settleRoster(state, rates)
  expect([target.mood, target.depletionRate]).toEqual([20, 2.3])

  advanceRoster(state, 4, rates)
  source.queue.tasks.push(new MowerTask({ time: state.time }))
  settleRoster(state, rates)
  expect([target.mood, target.depletionRate]).toEqual([16, 1])
})

it.each([
  'partial charge',
  'position only',
  'estimated mood',
  'legacy full mood',
  'ordinary reading'
])('preserves %s sampling eligibility across a plan rebuild and projection', (evidence) => {
  const { state, source } = fixture()
  const target = source.data.operators.B
  target.mood = 19
  target.depletionRate = 2.3
  if (evidence === 'partial charge') {
    mowerUpdateDetail(source.data, 'B', 19, 'central', 0, true, undefined, undefined, true)
  } else if (evidence === 'position only') {
    target.currentIndex = 1
    mowerUpdateDetail(source.data, 'B', 19, 'central', 0, false)
  } else if (evidence === 'estimated mood') {
    target.moodIsPrediction = true
  } else if (evidence === 'legacy full mood') {
    target.mood = 24
  }
  const rebuilt = makeMowerSchedulingData(state, source)
  const data = projectMowerArrangements(rebuilt, [])
  const previousRate = evidence === 'position only' ? 0 : 2.3
  data.nowMicros = toMowerMicros(1)
  mowerUpdateDetail(data, 'B', 17, 'central', 0, true)
  expect(data.operators.B.depletionRate).toBe(evidence === 'ordinary reading' ? 2 : previousRate)
  data.nowMicros = toMowerMicros(2)
  mowerUpdateDetail(data, 'B', 16, 'central', 0, true)
  expect(data.operators.B.depletionRate).toBe(1)
  expect(target.mood).toBe(evidence === 'legacy full mood' ? 24 : 19)
})

it.each(['failed', 'future'])('allows ready work past a %s restoration', (condition) => {
  const { state, source } = fixture()
  state.morale.A = 24
  source.data.operators.A.mood = 24
  const restore = new MowerTask({
    time: condition === 'future' ? 4 : 0,
    type: T.FIAMMETTA,
    plan: { central: ['Current'] }
  })
  restore.fiaRestoration = true
  const ready = new MowerTask({ plan: { room_1_1: ['Current'] } })
  source.queue.tasks = [restore, ready]
  if (condition === 'failed')
    retainMowerFailedTask(state, source.data, restore, 'Waiting for a new central observation', [
      'central'
    ])
  const originalTime = restore.timeMicros
  const originalPlan = structuredClone(restore.plan)
  for (let attempt = 0; attempt < 3; attempt++)
    settleRoster(state, { workRate: () => 1, recoveryRate: () => 4 })
  expect(source.queue.tasks).not.toContain(ready)
  expect(source.queue.tasks).toContain(restore)
  expect(restore.timeMicros).toBe(originalTime)
  expect(restore.plan).toEqual(originalPlan)
  expect(source.trace.some((task) => task.type === 'FIAMMETTA')).toBe(false)
})

const longRun = process.env.MOWER_INCOME_LONG_TEST === '1'
it(
  'keeps the supplied automation group rotating after Fiammetta restoration',
  () => {
    const original = structuredClone(plan)
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      warmupDays: longRun ? 3 : 0,
      sampleDays: longRun ? 28 : 1
    })
    expect(result.success, result.error).toBe(true)
    expect(result.observedHours).toBeCloseTo(longRun ? 672 : 24, 6)
    const names = ['森蚺', '绮良', '鸿雪', '图耶', '承曦格雷伊', '清流', '温蒂']
    for (const name of names) {
      const op = result.simulationReport.operators.find((op) => op.operatorName === name)
      expect(op.exhaustedHours, name).toBe(0)
      expect(op.restHours, name).toBeGreaterThan(0)
    }
    expect(plan).toEqual(original)
  },
  longRun ? 1200000 : 60000
)
