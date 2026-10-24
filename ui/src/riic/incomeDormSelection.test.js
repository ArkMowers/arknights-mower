import { describe, expect, it } from 'vitest'
import { createRosterRuntime, settleRoster } from './vendor/scheduler/rosterRuntime'
import { getMowerSourceRuntime } from './vendor/scheduler/mowerSourceRuntime'
import { MowerOperatorState } from './vendor/scheduler/mowerOperatorState'
import { mowerUpdateDetail } from './vendor/scheduler/mowerObservations'
import { MowerSchedulingData } from './vendor/scheduler/mowerSchedulingData'
import { prepareMowerDormSelection } from './vendor/scheduler/mowerSelection'
import { ensureMowerDormRecovery } from './vendor/scheduler/mowerDormRecovery'
import { MowerTask, MowerTaskQueue } from './vendor/scheduler/mowerTaskQueue'

const rates = { workRate: () => 1, recoveryRate: () => 4 }

function runtimeFixture() {
  const keepers = ['K1', 'K2', 'K3', 'K4']
  const state = createRosterRuntime({
    mowerAlpha: true,
    mowerRunOrderEnabled: false,
    mowerPolicy: { restingThreshold: 0.65, powerPlantCount: 2, opeRestingPriority: [] },
    mowerTaskScheduling: { adjustForRunOrders: false },
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
    initialMorale: { A: 24, R: 9, X: 10, Y: 11 },
    idleOperators: ['X', 'Y'],
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
  const source = getMowerSourceRuntime(state)
  source.initial = false
  source.firstInit = false
  for (const [index, name] of keepers.entries())
    mowerUpdateDetail(source.data, name, 24, 'dormitory_1', index, true)
  mowerUpdateDetail(source.data, 'A', 24, 'room_1_1', 0, true)
  source.data.operators.K1.singleRecoveryManager = true
  source.data.operators.R.mood = 9
  source.data.operators.R.timeStampMicros = 0
  source.data.operators.X = new MowerOperatorState({
    name: 'X',
    alpha: true,
    mood: 10,
    timeStampMicros: 0
  })
  source.data.operators.Y = new MowerOperatorState({
    name: 'Y',
    alpha: true,
    mood: 11,
    timeStampMicros: 0
  })
  const list = [...keepers, 'R']
  const task = new MowerTask({ plan: { dormitory_1: list } })
  source.queue.tasks = [task]
  return { state, source, task, list }
}

describe('income dorm selection follows the native execution order', () => {
  it.each(['workaholic', 'blacklist', 'personal-limit'])(
    'cancels %s admission before confirming recovery',
    (rule) => {
      const { state, source, task } = runtimeFixture()
      if (rule === 'workaholic') source.data.operators.R.workaholic = true
      if (rule === 'blacklist') source.data.freeBlacklist.push('R')
      if (rule === 'personal-limit') {
        source.data.operators.R.restMoodLimit = true
        source.data.operators.R.upperLimit = 9
      }
      settleRoster(state, rates)
      expect(state.diagnostics.filter((d) => d.code === 'mower-task-exception')).toEqual([])
      expect(source.queue.tasks).not.toContain(task)
      expect(state.bedOccupants.dormitory_1_4).toBe('X')
      expect(source.data.currentRoom('dormitory_1', true)).toEqual(['K1', 'K2', 'K3', 'K4', 'X'])
      expect(source.data.operators.R.dormRecoveryRoom).toBe('')
    }
  )

  it.each(['workaholic', 'blacklist'])(
    'preserves a temporary explicit %s resident after admission',
    (rule) => {
      const { source } = runtimeFixture()
      if (rule === 'workaholic') source.data.operators.R.workaholic = true
      else source.data.freeBlacklist.push('R')
      const names = ['K1', 'K2', 'K3', 'K4', 'R']
      prepareMowerDormSelection(source.data, names, 'dormitory_1', true)
      expect(names[4]).toBe('R')
      source.data.operators.R.restMoodLimit = true
      source.data.operators.R.upperLimit = 9
      prepareMowerDormSelection(source.data, names, 'dormitory_1', true)
      expect(names[4]).toBe('Free')
    }
  )

  it.each([false, true])(
    'checks the selected temporary roster and still rejects incorrect observations: %s',
    (wrongObservation) => {
      const room = 'dormitory_1'
      const operators = Object.fromEntries(
        ['Manager', 'Keeper', 'Owner', 'Cover', 'Target', 'Padding', 'Other'].map((name) => [
          name,
          new MowerOperatorState({ name, mood: 24, timeStampMicros: 0 })
        ])
      )
      operators.Manager.singleRecoveryManager = true
      operators.Manager.room = room
      operators.Keeper.room = room
      operators.Owner.room = room
      operators.Owner.operatorType = 'high'
      operators.Owner.index = 2
      operators.Owner.group = 'G'
      operators.Owner.replacement = ['Cover']
      operators.Cover.mood = 3
      operators.Target.mood = 9
      operators.Target.room = 'room_1_1'
      const names = ['Manager', 'Keeper', 'Cover', 'Target', 'Free']
      const data = new MowerSchedulingData({
        alpha: true,
        plan: { [room]: ['Manager', 'Keeper', 'Owner', 'Free', 'Free'] },
        operators,
        dorms: [],
        nowMicros: 0
      })
      const task = new MowerTask({ plan: { [room]: names } })
      const queue = new MowerTaskQueue()
      queue.tasks = [task]
      const run = () =>
        ensureMowerDormRecovery(data, queue, task, room, names, {
          arrangeTemporary: (selected) => {
            expect(selected).toEqual(['Manager', 'Keeper', 'Padding', 'Target'])
            selected[2] = 'Other'
            for (const [index, name] of selected.entries()) {
              const actual = wrongObservation && index === 2 ? 'Padding' : name
              operators[actual].currentRoom = room
              operators[actual].currentIndex = index
            }
          }
        })
      if (wrongObservation) expect(run).toThrow('dorm recovery ordering observation failed')
      else {
        expect(run()).toBe(true)
        expect(data.currentRoom(room, true)).toEqual(['Manager', 'Keeper', 'Other', 'Target', ''])
        expect(operators.Target.dormRecoveryRoom).toBe(room)
      }
      expect(task.plan[room]).toEqual(['Manager', 'Keeper', 'Cover', 'Target', 'Free'])
    }
  )
})
