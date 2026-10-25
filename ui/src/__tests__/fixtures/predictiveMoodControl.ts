import { MowerOperatorState } from '../../riic/vendor/scheduler/mowerOperatorState'
import {
  MowerSchedulingData,
  MowerDormState
} from '../../riic/vendor/scheduler/mowerSchedulingData'
import { MowerTaskQueue } from '../../riic/vendor/scheduler/mowerTaskQueue'
import type { MowerRestingOptions } from '../../riic/vendor/scheduler/mowerOrdinaryPlanning'
export interface PredictiveFixtureInput {
  moods: Record<string, number>
  workRate: number
  workBelow12?: number
  recoveryRate: number
  threshold: number
  exhaust: string[]
  restInFull: string[]
  roomSeconds: number
  lower?: number
  enabled?: boolean
  maxEvents?: number
}
export function predictiveFixture(input: PredictiveFixtureInput) {
  const operators = Object.fromEntries(
    ['A', 'B', 'X'].map((name, i) => [
      name,
      new MowerOperatorState({
        name,
        room: i < 2 ? 'room_1_' + (i + 1) : '',
        index: i < 2 ? 0 : -1,
        operatorType: i < 2 ? 'high' : 'low',
        restingPriority: i < 2 ? 'high' : 'low',
        restInFull: input.restInFull.includes(name),
        exhaustRequire: input.exhaust.includes(name),
        replacement: i < 2 ? ['X'] : [],
        mood: input.moods[name],
        lowerLimit: input.lower ?? 0,
        timeStampMicros: 0,
        currentRoom: i < 2 ? 'room_1_' + (i + 1) : '',
        currentIndex: i < 2 ? 0 : -1
      })
    ])
  )
  const data = new MowerSchedulingData({
    alpha: true,
    operators,
    plan: { room_1_1: ['A'], room_1_2: ['B'], dormitory_1: ['Free'] },
    dorms: [new MowerDormState(['dormitory_1', 0])],
    nowMicros: 0,
    policy: { restingThreshold: input.threshold, predictiveMoodControl: input.enabled ?? true },
    groupRestInFullOnMoodGap: false
  })
  const queue = new MowerTaskQueue(),
    diagnostics: import('../../riic/vendor/scheduler/mowerPredictivePlanning').MowerPredictiveDiagnostics[] =
      []
  const options: MowerRestingOptions = {
    predictiveMaxEvents: input.maxEvents,
    predictiveOperationMicros: () => input.roomSeconds * 1_000_000,
    coordinationRates: (state: MowerSchedulingData) => ({
      work: Object.fromEntries(
        Object.values(state.operators)
          .filter((o) => o.currentRoom && !o.isResting())
          .map((o) => [
            o.name,
            o.mood <= 12 + 1e-8 ? (input.workBelow12 ?? input.workRate) : input.workRate
          ])
      ),
      recovery: Object.fromEntries(
        Object.values(state.operators)
          .filter((o) => o.isResting())
          .map((o) => [o.name, input.recoveryRate])
      )
    }),
    onPredictiveDiagnostics: (d) => diagnostics.push(d)
  }
  return { data, queue, options, diagnostics }
}
