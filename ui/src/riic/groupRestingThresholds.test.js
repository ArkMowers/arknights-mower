import { describe, expect, it } from 'vitest'
import {
  MowerOperatorState,
  rescueMoodThreshold,
  restingThresholdFor
} from './vendor/scheduler/mowerOperatorState'
import { MowerSchedulingData, MowerDormState } from './vendor/scheduler/mowerSchedulingData'
import { mowerResting } from './vendor/scheduler/mowerOrdinaryPlanning'
import { MowerTaskQueue } from './vendor/scheduler/mowerTaskQueue'
import { mowerOrdinaryCoordinationNeeded } from './vendor/scheduler/mowerExhaustPolicy'
import { nextMowerMoodPlanningWake } from './vendor/scheduler/mowerPlanningWake'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { createDefaultWorkspace } from './vendor/workbench/defaults'

function fixture(alpha = true) {
  const operators = Object.fromEntries(
    ['A', 'B'].map((name, index) => [
      name,
      new MowerOperatorState({
        name,
        group: name,
        room: `room_1_${index + 1}`,
        index: 0,
        currentRoom: `room_1_${index + 1}`,
        currentIndex: 0,
        replacement: [name + 'R'],
        operatorType: 'high',
        restingPriority: 'high',
        mood: 10,
        timeStampMicros: 0
      })
    ])
  )
  for (const name of ['AR', 'BR'])
    operators[name] = new MowerOperatorState({ name, mood: 24, timeStampMicros: 0 })
  return new MowerSchedulingData({
    alpha,
    operators,
    nowMicros: 0,
    plan: {
      room_1_1: ['A'],
      room_1_2: ['B'],
      dormitory_1: ['Free', 'Free', 'Free', 'Free', 'Free']
    },
    dorms: [new MowerDormState(['dormitory_1', 0]), new MowerDormState(['dormitory_1', 1])],
    policy: {
      restingThreshold: 0.5,
      groupRestingThresholds: { A: 0.35, B: 0.65 },
      rescueThreshold: 0.5
    }
  })
}

describe('收益演算中的各组心情阈值', () => {
  it.each([false, true])('两个组同为 10 心情时只让达到本组阈值的组下班，alpha=%s', (alpha) => {
    const data = fixture(alpha)
    const plan = mowerResting(data, new MowerTaskQueue())
    expect(plan.room_1_1).toBeUndefined()
    expect(plan.room_1_2).toEqual(['BR'])
    expect(data.dorms.filter((bed) => bed.name).map((bed) => bed.name)).toEqual(['B'])
    expect(mowerOrdinaryCoordinationNeeded(fixture(), ['A'])).toBe(false)
    expect(mowerOrdinaryCoordinationNeeded(fixture(), ['B'])).toBe(true)
  })
  it('按组阈值预测下一次下班时间，并按个人上下限换算急救线', () => {
    const data = fixture()
    const wake = nextMowerMoodPlanningWake(
      {
        time: 0,
        occupants: { room_1_1_0: 'A', room_1_2_0: 'B' },
        morale: { A: 10, B: 24 }
      },
      data,
      { workRate: () => 1 }
    )
    expect(wake).toEqual({ timeMicros: 2 * 3_600_000_000, names: ['A'] })
    const op = data.operators.A
    op.lowerLimit = 8
    op.upperLimit = 20
    expect(rescueMoodThreshold(op, data.policy)).toBeCloseTo(10.1)
    expect(restingThresholdFor({ group: '', multiGroup: false }, data.policy)).toBe(0.5)
    expect(restingThresholdFor({ group: 'A', multiGroup: true }, data.policy)).toBe(0.5)
    expect(restingThresholdFor({ group: 'toString' }, data.policy)).toBe(0.5)
  })
  it.each([0.34, 1.01, NaN, Infinity])('演算拒绝非法组阈值 %s', (value) => {
    const schedule = compileRosterSchedule(createDefaultWorkspace(), {
      groupRestingThresholds: { A: value }
    })
    expect(schedule.diagnostics).toContainEqual(
      expect.objectContaining({
        severity: 'error',
        path: 'assumptions.groupRestingThresholds'
      })
    )
  })
})
