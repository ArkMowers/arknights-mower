import { describe, expect, it } from 'vitest'
import { planMowerMetadata } from './mowerMetadata'
import { prepareMowerRelease } from './mowerRelease'
import { MowerOperatorState, type MowerOperatorOptions } from './mowerOperatorState'
import { MowerDormState, MowerSchedulingData } from './mowerSchedulingData'
import { MOWER_TASK_TYPES as T, MowerTaskQueue, toMowerMicros } from './mowerTaskQueue'

const now = toMowerMicros(1)
const deadline = toMowerMicros(2)
function fixture(rows: Partial<MowerOperatorOptions>[] = [{}]) {
  const operators = Object.fromEntries(rows.map((overrides, index) => {
    const name = String.fromCharCode(65 + index)
    return [name, new MowerOperatorState({ name, mood: 24, upperLimit: 24, timeStampMicros: now - 1_000_000,
      depletionRate: .5, currentRoom: 'dormitory_1', currentIndex: index + 2, ...overrides })]
  }))
  const data = new MowerSchedulingData({ alpha: true, freeRoom: true, nowMicros: now, operators,
    plan: { dormitory_1: ['K1', 'K2', 'Free', 'Free', 'Free'] },
    dorms: Object.keys(operators).map((name, index) => new MowerDormState(['dormitory_1', index + 2], name, deadline)),
  })
  const queue = new MowerTaskQueue()
  planMowerMetadata(data, queue)
  const task = queue.tasks.find(entry => entry.type === T.RELEASE_DORM)!
  expect(task).toBeDefined()
  return { data, queue, task, operators }
}

describe('observed full morale across alpha metadata and physical release preparation', () => {
  it('releases an observed full resident despite an old positive depletion rate and future bed deadline', () => {
    const { data, queue, task, operators } = fixture()
    expect(operators.A!.currentMood(now)).toBeLessThan(24)
    expect(task.timeMicros).toBe(now)
    expect(prepareMowerRelease(data, queue, task)).toBe(true)
    expect(task.plan.dormitory_1).toEqual(['Current', 'Current', 'Free', 'Current', 'Current'])
    expect(queue.tasks.filter(entry => entry !== task)).toEqual([])
  })

  it('keeps an underfull resident deferred until its recovery deadline', () => {
    const { data, queue, task } = fixture([{ mood: 23.9 }])
    expect(task.timeMicros).toBe(deadline)
    expect(prepareMowerRelease(data, queue, task)).toBe(false)
    expect(task.plan).toEqual({})
    expect(queue.tasks.filter(entry => entry !== task).map(entry => [entry.metadata, entry.timeMicros])).toEqual([['A', deadline]])
  })

  it.each([
    { label: 'missing timestamp', overrides: { timeStampMicros: undefined } },
    { label: 'out-of-range morale', overrides: { mood: 25 } },
    { label: 'infinite morale', overrides: { mood: Infinity } },
  ])('does not turn $label into an observed full release', ({ overrides }) => {
    const { data, queue, task } = fixture([overrides])
    expect(task.timeMicros).toBe(deadline)
    expect(prepareMowerRelease(data, queue, task)).toBe(false)
    expect(task.plan).toEqual({})
    expect(queue.tasks.filter(entry => entry !== task).map(entry => [entry.metadata, entry.timeMicros])).toEqual([['A', deadline]])
  })

  it.each([['dormitory_1', 4], ['dormitory_2', 2]] as const)('rejects a full observation when the resident has moved to %s slot %s', (room, index) => {
    const { data, queue, task, operators } = fixture()
    expect(task.timeMicros).toBe(now)
    operators.A!.setProjectedPosition(room, index)
    expect(prepareMowerRelease(data, queue, task)).toBe(false)
    expect(task.plan).toEqual({})
    expect(queue.tasks.filter(entry => entry !== task)).toEqual([])
  })

  it('uses an ordinary resident’s personal upper limit rather than hardcoded 24', () => {
    const { data, queue, task, operators } = fixture([{ mood: 12, upperLimit: 12 }])
    expect(operators.A!.currentMood(now)).toBeLessThan(12)
    expect(task.strictMoodLimit).toBe(false)
    expect(task.timeMicros).toBe(now)
    expect(prepareMowerRelease(data, queue, task)).toBe(true)
    expect(queue.tasks.filter(entry => entry !== task)).toEqual([])
    expect(operators.A!.upperLimit).toBe(12)
  })

  it('preserves strict personal-limit release timing and its individual limit', () => {
    const { data, queue, task, operators } = fixture([{ mood: 12, upperLimit: 12, restMoodLimit: true }])
    expect(operators.A!.currentMood(now)).toBeLessThan(12)
    expect(task.strictMoodLimit).toBe(true)
    expect(task.moodLimit).toBe(12)
    expect(task.timeMicros).toBe(deadline)
    data.nowMicros = deadline
    expect(prepareMowerRelease(data, queue, task)).toBe(true)
    expect(operators.A!.mood).toBe(12)
    expect(operators.A!.upperLimit).toBe(12)
    expect(queue.tasks.filter(entry => entry !== task)).toEqual([])
  })

  it.each(['removed', 'changed'] as const)('rejects a strict release whose configured personal limit was %s', change => {
    const { data, queue, task, operators } = fixture([{ mood: 12, upperLimit: 12, restMoodLimit: true }])
    if (change === 'removed') operators.A!.restMoodLimit = false
    else operators.A!.upperLimit = 20
    data.nowMicros = deadline
    expect(prepareMowerRelease(data, queue, task)).toBe(false)
    expect(task.plan).toEqual({})
    expect(queue.tasks.filter(entry => entry !== task)).toEqual([])
  })

  it('validates each resident of a merged release against its own observation and bed identity', () => {
    const { data, queue, task, operators } = fixture([{}, {}, {}])
    expect(queue.tasks).toHaveLength(1)
    expect(task.releaseDormTargets()).toEqual({ A: ['dormitory_1', 2], B: ['dormitory_1', 3], C: ['dormitory_1', 4] })
    operators.B!.mood = 23.9
    operators.C!.setProjectedPosition('dormitory_1', 0)
    expect(prepareMowerRelease(data, queue, task)).toBe(true)
    expect(task.releaseDormTargets()).toEqual({ A: ['dormitory_1', 2] })
    expect(task.metadata).toBe('A')
    expect(task.plan.dormitory_1).toEqual(['Current', 'Current', 'Free', 'Current', 'Current'])
    const deferred = queue.tasks.filter(entry => entry !== task)
    expect(deferred.map(entry => [entry.metadata, entry.timeMicros])).toEqual([['B', deadline]])
    expect(deferred[0]!.releaseDormTargets()).toEqual({ B: ['dormitory_1', 3] })
  })
})


describe('mandatory full recovery before ordinary dorm release', () => {
  it.each(['explicit', 'delayed'] as const)('retains an overdue %s full-rest release until valid recovery evidence arrives', mode => {
    const { data, queue, task, operators } = fixture([{ mood: 23.8 }])
    if (mode === 'explicit') operators.A!.restInFull = true
    else { data.groupRecoveryFullMembers.g = ['A']; Object.assign(operators.A!, { group: 'g', operatorType: 'high', room: 'room_1_1' }) }
    data.dorms[0]!.timeMicros = now
    const plan = structuredClone(task.plan), timestamp = task.timeMicros
    expect(() => prepareMowerRelease(data, queue, task)).toThrow('尚未确认回满心情')
    expect(task.plan).toEqual(plan)
    expect(task.timeMicros).toBe(timestamp)
    expect(operators.A!.mood).toBe(23.8)
    expect(queue.tasks).toEqual([task])
  })

  it('does not accept a predicted full mood for mandatory recovery', () => {
    const { data, queue, task } = fixture([{ mood: 24, moodIsPrediction: true, restInFull: true }])
    data.dorms[0]!.timeMicros = now
    expect(() => prepareMowerRelease(data, queue, task)).toThrow('尚未确认回满心情')
  })

  it('defers a mandatory release to its refreshed recovery deadline and releases after measurement', () => {
    const { data, queue, task, operators } = fixture([{ mood: 23.8, restInFull: true }])
    expect(prepareMowerRelease(data, queue, task)).toBe(false)
    const pending = queue.tasks.find(entry => entry !== task)!
    expect(pending.timeMicros).toBe(deadline)
    data.nowMicros = deadline; operators.A!.mood = 24; operators.A!.timeStampMicros = deadline
    expect(prepareMowerRelease(data, queue, pending)).toBe(true)
  })

  it('preserves timer-based release for an ordinary resident', () => {
    const { data, queue, task } = fixture([{ mood: 23.8 }])
    data.dorms[0]!.timeMicros = now
    expect(prepareMowerRelease(data, queue, task)).toBe(true)
  })
})


describe('mandatory release policy boundaries', () => {
  it('requires measured recovery when a personal mood limit also requires full rest', () => {
    const { data, queue, task, operators } = fixture([{ mood: 11.8, upperLimit: 12, restMoodLimit: true, restInFull: true }])
    data.dorms[0]!.timeMicros = now
    expect(() => prepareMowerRelease(data, queue, task)).toThrow('尚未确认回满心情')
    operators.A!.mood = 12; operators.A!.timeStampMicros = now
    expect(prepareMowerRelease(data, queue, task)).toBe(true)
  })

  it.each(['removed', 'workaholic'] as const)('ignores stale delayed-return membership after becoming %s', change => {
    const { data, queue, task, operators } = fixture([{ mood: 23.8 }])
    Object.assign(operators.A!, { group: 'g', operatorType: 'high', room: 'room_1_1' })
    data.groupRecoveryFullMembers.g = ['A']
    data.dorms[0]!.timeMicros = now
    if (change === 'removed') operators.A!.group = 'other'
    if (change === 'workaholic') operators.A!.workaholic = true
    expect(prepareMowerRelease(data, queue, task)).toBe(true)
  })
})


it.each(['excluded', 'removed-limit', 'changed-limit'] as const)('discards an invalid mandatory release after configuration becomes %s', change => {
  const { data, queue, task, operators } = fixture([{ mood: 11.8, upperLimit: 12, restMoodLimit: change !== 'excluded', restInFull: true }])
  data.dorms[0]!.timeMicros = now
  if (change === 'excluded') data.freeRoomExclusions = ['A']
  if (change === 'removed-limit') operators.A!.restMoodLimit = false
  if (change === 'changed-limit') operators.A!.upperLimit = 20
  expect(prepareMowerRelease(data, queue, task)).toBe(false)
  expect(task.plan).toEqual({})
})
