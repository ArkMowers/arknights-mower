import { describe, expect, it } from 'vitest'
import { createRosterRuntime, settleRoster, type RuntimeConfig } from './rosterRuntime'
import { getMowerSourceRuntime } from './mowerSourceRuntime'
import { mowerHasMeasuredDormDeparture } from './mowerObservations'
import { MowerTask, MOWER_TASK_TYPES as T, toMowerMicros } from './mowerTaskQueue'

const room = 'dormitory_1'
const rates = { workRate: () => 1, recoveryRate: () => 4 }
function fixture(mood = 12, upperLimit = 12) {
  const keepers = ['K1', 'K2', 'K3']
  const config: RuntimeConfig = {
    positions: [
      { id: 'room_1_1_0', roomId: 'room_1_1', primary: 'A', candidates: ['R'], group: 'g', upperLimit },
      { id: 'room_1_2_0', roomId: 'room_1_2', primary: 'B', candidates: ['S'], group: 'g' },
      ...keepers.map((primary, index) => ({ id: room + '_' + index, roomId: room, primary, candidates: [], permanent: true, dormitory: true })),
    ],
    beds: [{ id: room + '_3', roomId: room, vip: true }, { id: room + '_4', roomId: room, vip: false }],
    initialMorale: { A: mood, B: 8, R: 24, S: 24, Incoming: 2 }, idleOperators: ['Incoming'],
    mowerAlpha: true,
    mowerPolicy: { restingThreshold: .65, powerPlantCount: 2, opeRestingPriority: [] },
    mowerTaskScheduling: { adjustForRunOrders: false },
    mowerDeviceTiming: { roomReturnMicros: 500_000 },
    mowerSourcePlan: {
      room_1_1: [{ agent: 'A', group: 'g', replacement: ['R'] }],
      room_1_2: [{ agent: 'B', group: 'g', replacement: ['S'] }],
      [room]: [...keepers.map(agent => ({ agent, group: '', replacement: [] })), ...['Free', 'Free'].map(agent => ({ agent, group: '', replacement: [] }))],
    },
    mowerSourceRules: { workaholic: [], exhaustRequire: [], restInFull: [], lowPriority: [], refreshDrained: [], lingMode: 0 },
  }
  const state = createRosterRuntime(config), source = getMowerSourceRuntime(state)
  source.initial = false; source.firstInit = false
  state.time = 1; source.data.nowMicros = toMowerMicros(1)
  state.occupants.room_1_1_0 = 'R'; state.occupants.room_1_2_0 = 'S'
  state.bedOccupants[room + '_3'] = 'A'; state.bedOccupants[room + '_4'] = 'B'
  for (const [slot, name] of Object.entries({ ...state.occupants, ...state.bedOccupants })) {
    const op = source.data.operators[name]!
    op.currentRoom = slot.slice(0, slot.lastIndexOf('_')); op.currentIndex = Number(slot.slice(slot.lastIndexOf('_') + 1))
    op.mood = state.morale[name] ?? 24; op.timeStampMicros = 0
  }
  source.data.operators.A!.upperLimit = upperLimit
  source.data.operators.A!.depletionRate = -2
  source.data.dorms[0]!.name = 'A'; source.data.dorms[0]!.timeMicros = toMowerMicros(2)
  source.data.dorms[1]!.name = 'B'; source.data.dorms[1]!.timeMicros = toMowerMicros(5)
  source.data.groupShiftState.g = true
  const task = new MowerTask({ time: 1, type: T.RELEASE_DORM, metadata: 'A', plan: { [room]: [...keepers, 'Free', 'B'] } })
  task.backupShiftActive = true
  source.queue.tasks = [task]
  return { state, source, task }
}

function finish(f: ReturnType<typeof fixture>) {
  settleRoster(f.state, rates)
}

describe('confirmed ordinary dorm departure keeps measured morale', () => {
  it.each([12, 24])('stops the old recovery rate after leaving at personal limit %s', upperLimit => {
    const f = fixture(upperLimit, upperLimit), op = f.source.data.operators.A!
    finish(f)
    expect(op.currentRoom).toBe('')
    expect(op.mood).toBe(upperLimit)
    expect(op.timeStampMicros).toBe(toMowerMicros(1))
    expect(op.moodIsPrediction).toBe(false)
    expect(op.depletionRate).toBe(0)
    expect(op.currentMood(toMowerMicros(2))).toBe(upperLimit)
    expect(f.source.data.operators.B!.isResting()).toBe(true)
    expect(f.source.data.groupShiftState.g).toBe(true)
  })

  it('replaces a predicted full mood with the departure observation', () => {
    const f = fixture(), op = f.source.data.operators.A!
    op.moodIsPrediction = true
    finish(f)
    expect(op.currentRoom).toBe('')
    expect(op.timeStampMicros).toBe(toMowerMicros(1))
    expect(op.moodIsPrediction).toBe(false)
    expect(op.depletionRate).toBe(0)
  })

  it('invalidates below-limit morale after the physical departure', () => {
    const f = fixture(11), op = f.source.data.operators.A!
    finish(f)
    expect(op.currentRoom).toBe('')
    expect(op.timeStampMicros).toBeUndefined()
  })
})

describe('ordinary departure observation evidence', () => {
  it.each(['no-task', 'no-plan', 'mismatch', 'unknown', 'prediction', 'below-limit', 'still-present'] as const)('rejects %s as measured completion', evidence => {
    const { source, task } = fixture(), op = source.data.operators.A!
    const observed = ['K1', 'K2', 'K3', 'Incoming', 'B']
    task.plan[room] = [...observed]
    if (evidence === 'no-plan') task.plan = {}
    if (evidence === 'mismatch') observed[4] = 'Other'
    if (evidence === 'unknown') op.timeStampMicros = undefined
    if (evidence === 'prediction') op.moodIsPrediction = true
    if (evidence === 'below-limit') op.mood = 11.9
    if (evidence === 'still-present') { observed[3] = 'A'; task.plan[room] = [...observed] }
    expect(mowerHasMeasuredDormDeparture(source.data, op, room, observed, evidence === 'no-task' ? undefined : task)).toBe(false)
  })
})
