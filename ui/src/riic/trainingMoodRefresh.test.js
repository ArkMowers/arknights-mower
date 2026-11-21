import { describe, expect, it } from 'vitest'
import {
  createRosterRuntime,
  settleRoster,
  advanceRoster,
  nextRosterActionHours
} from './vendor/scheduler/rosterRuntime'
import { getMowerSourceRuntime } from './vendor/scheduler/mowerSourceRuntime'
import { mowerUpdateDetail } from './vendor/scheduler/mowerObservations'
import { MowerTask, toMowerMicros } from './vendor/scheduler/mowerTaskQueue'

const rates = { workRate: (_name, room) => (room === 'train' ? 0 : 1), recoveryRate: () => 4 }

function fixture() {
  const keepers = ['K1', 'K2', 'K3', 'K4']
  return {
    mowerAlpha: true,
    mowerTheoreticalMode: true,
    mowerRunOrderEnabled: false,
    mowerTaskScheduling: { adjustForRunOrders: false },
    positions: [
      {
        id: 'room_1_1_0',
        roomId: 'room_1_1',
        primary: 'A',
        candidates: ['R'],
        lowerLimit: 0,
        upperLimit: 24,
        shiftOffThreshold: 0
      },
      ...keepers.map((name, i) => ({
        id: 'dormitory_1_' + i,
        roomId: 'dormitory_1',
        primary: name,
        candidates: [],
        permanent: true,
        dormitory: true
      }))
    ],
    beds: [{ id: 'dormitory_1_4', roomId: 'dormitory_1', vip: true }],
    initialMorale: { A: 10, R: 24 },
    idleOperators: [],
    mowerPolicy: { restingThreshold: 0, powerPlantCount: 2, opeRestingPriority: [] },
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
  }
}

function observeInitialOccupants(state) {
  const source = getMowerSourceRuntime(state)
  source.initial = false
  source.firstInit = false
  for (const [slot, name] of Object.entries({ ...state.occupants, ...state.bedOccupants })) {
    const split = slot.lastIndexOf('_')
    mowerUpdateDetail(
      source.data,
      name,
      state.morale[name],
      slot.slice(0, split),
      Number(slot.slice(split + 1)),
      true
    )
  }
  return source
}

function trainingFixture() {
  const config = fixture()
  for (const [index, name] of ['Trainer', 'Trainee'].entries()) {
    config.positions.push({ id: 'train_' + index, roomId: 'train', primary: name, candidates: [] })
  }
  config.mowerSourcePlan.train = ['Trainer', 'Trainee'].map((agent) => ({
    agent,
    group: '',
    replacement: []
  }))
  return config
}

describe('training room mood refresh', () => {
  it.each(['Trainer', 'Trainee'])(
    'refreshes stale same-slot %s without correction churn',
    (name) => {
      const config = trainingFixture()
      const state = createRosterRuntime(config)
      const source = observeInitialOccupants(state)
      advanceRoster(state, 1, rates)
      getMowerSourceRuntime(state)
      mowerUpdateDetail(
        source.data,
        name,
        state.morale[name],
        'train',
        name === 'Trainer' ? 0 : 1,
        true
      )
      advanceRoster(state, 1.6, rates)
      source.queue.tasks = [new MowerTask({ time: state.time })]
      settleRoster(state, rates)
      expect(source.lastTrainMoodReadMicros).toBe(toMowerMicros(2.6))
      expect(source.data.operators[name].timeStampMicros).toBe(toMowerMicros(1))
      advanceRoster(state, 1, rates)
      const before = { ...state.occupants }
      const independent = new MowerTask({ time: 4, metadata: 'independent work' })
      source.queue.tasks = [new MowerTask({ time: state.time }), independent]

      settleRoster(state, rates)

      expect({
        trainerObservedAt: source.data.operators.Trainer.timeStampMicros,
        traineeObservedAt: source.data.operators.Trainee.timeStampMicros,
        emptyCorrections: source.trace.filter(
          (task) => task.type === 'SELF_CORRECTION' && !Object.keys(task.plan).length
        ).length
      }).toEqual({
        trainerObservedAt: toMowerMicros(name === 'Trainer' ? 3.6 : 2.6),
        traineeObservedAt: toMowerMicros(name === 'Trainee' ? 3.6 : 2.6),
        emptyCorrections: 0
      })
      expect(state.occupants).toEqual(before)
      expect(
        state.events.some((event) => event.type === 'shift-on' || event.type === 'shift-off')
      ).toBe(false)
      expect(nextRosterActionHours(state, rates)).toBeGreaterThan(0)
      for (let repeat = 0; repeat < 4; repeat++) {
        source.queue.tasks.push(new MowerTask({ time: state.time }))
        settleRoster(state, rates)
      }
      expect(source.data.operators[name].timeStampMicros).toBe(toMowerMicros(3.6))
      expect(source.queue.tasks).toContain(independent)
      expect(independent.timeMicros).toBe(toMowerMicros(4))
      advanceRoster(state, 4 - state.time, rates)
      settleRoster(state, rates)
      expect(source.queue.tasks).not.toContain(independent)
      expect(source.trace.some((task) => task.metadata === 'independent work')).toBe(true)
    }
  )

  it.each(['workaholic', 'protected'])(
    'preserves the %s exemption from training correction',
    (exemption) => {
      const state = createRosterRuntime(trainingFixture())
      const source = observeInitialOccupants(state)
      for (const name of ['Trainer', 'Trainee']) {
        if (exemption === 'workaholic') source.data.operators[name].workaholic = true
        else source.data.busyRestingNames.add(name)
      }
      advanceRoster(state, 3, rates)
      source.lastTrainMoodReadMicros = toMowerMicros(2)
      source.queue.tasks = [new MowerTask({ time: state.time })]
      settleRoster(state, rates)
      expect(source.data.operators.Trainer.timeStampMicros).toBe(0)
      expect(source.data.operators.Trainee.timeStampMicros).toBe(0)
      expect(source.trace.some((task) => task.type === 'SELF_CORRECTION')).toBe(false)
    }
  )

  it('still corrects genuinely misplaced training occupants during the room interval', () => {
    const state = createRosterRuntime(trainingFixture())
    state.occupants.train_0 = 'Trainee'
    state.occupants.train_1 = 'Trainer'
    const source = observeInitialOccupants(state)
    advanceRoster(state, 3, rates)
    source.lastTrainMoodReadMicros = toMowerMicros(2)
    source.queue.tasks = [new MowerTask({ time: state.time })]
    settleRoster(state, rates)
    expect(state.occupants.train_0).toBe('Trainer')
    expect(state.occupants.train_1).toBe('Trainee')
    expect(source.data.operators.Trainer.timeStampMicros).toBe(toMowerMicros(3))
    expect(source.data.operators.Trainee.timeStampMicros).toBe(toMowerMicros(3))
    expect(nextRosterActionHours(state, rates)).toBeGreaterThan(0)
  })
})
