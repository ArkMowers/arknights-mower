import { afterEach, describe, expect, it, vi } from 'vitest'
import { mowerAlphaDormCandidates, mowerAlphaFillPlan, planMowerAlphaDormFill } from './mowerAlphaCandidates'
import * as dorm from './mowerAlphaDorm'
import { MowerTask, MowerTaskQueue, MOWER_TASK_TYPES as T, toMowerMicros } from './mowerTaskQueue'
import { MowerOperatorState } from './mowerOperatorState'
import { MowerSchedulingData, MowerDormState } from './mowerSchedulingData'

afterEach(() => vi.restoreAllMocks())

function inventoryData() {
  const operators = Object.fromEntries(Array.from({ length: 200 }, (_, index) => {
    const name = `idle-${index}`
    return [name, new MowerOperatorState({ name, mood: 24, timeStampMicros: 0 })]
  }))
  operators.owner = new MowerOperatorState({ name: 'owner', room: 'room_1_1', currentRoom: 'room_1_1',
    operatorType: 'high', replacement: ['idle-150'] })
  return new MowerSchedulingData({ alpha: true, operators, plan: { train: ['', ''], dormitory_1: Array(5).fill('Free') }, dorms: [], nowMicros: 0 })
}

describe('large-library dorm candidate ordering', () => {
  it('computes each candidate tier at most twice in one selection pass', () => {
    const data = inventoryData()
    const replacement = data.operators.owner!.replacement
    let membershipReads = 0
    Object.defineProperty(data.operators.owner!, 'replacement', { get: () => { membershipReads++; return replacement } })
    const tier = vi.spyOn(dorm, 'alphaRestingTier')
    const candidates = mowerAlphaDormCandidates(data)
    expect(candidates.filling).toHaveLength(200)
    expect(candidates.filling[0]).toBe('idle-150')
    expect(candidates.filling.slice(1, 4)).toEqual(['idle-0', 'idle-1', 'idle-2'])
    expect(tier.mock.calls.length).toBeLessThanOrEqual(400)
    expect(membershipReads).toBeLessThanOrEqual(3)
  })

  it('recomputes ordering after policy, replacement membership and observed mood change', () => {
    const data = inventoryData()
    expect(mowerAlphaDormCandidates(data).filling[0]).toBe('idle-150')
    data.operators.owner!.replacement = []
    expect(mowerAlphaDormCandidates(data).filling[0]).toBe('idle-0')
    data.restingPriorityNames.push('idle-90')
    expect(mowerAlphaDormCandidates(data).filling[0]).toBe('idle-90')
    data.operators['idle-80']!.mood = 12
    expect(mowerAlphaDormCandidates(data).recovering).toEqual(['idle-80'])
    expect(mowerAlphaDormCandidates(data).filling[0]).toBe('idle-80')
    expect(mowerAlphaDormCandidates(data, new Set(['idle-80'])).filling[0]).toBe('idle-90')
  })
})


function takeoverData() {
  const operators = {
    owner: new MowerOperatorState({ name: 'owner', room: 'room_1_1', index: 0,
      currentRoom: 'room_1_1', currentIndex: 0, operatorType: 'high', replacement: ['R'],
      mood: 24, timeStampMicros: 0 }),
    R: new MowerOperatorState({ name: 'R', mood: 0, timeStampMicros: 0 }),
    S: new MowerOperatorState({ name: 'S', room: 'room_1_2', index: 0, operatorType: 'high',
      restingPriority: 'standby', currentRoom: 'dormitory_1', currentIndex: 0,
      mood: 24, timeStampMicros: 0 })
  }
  return new MowerSchedulingData({ alpha: true, freeRoom: false, nowMicros: 0,
    operators, priorityReplacement: ['R'], standbyNames: ['S'],
    plan: { room_1_1: ['owner'], room_1_2: ['S'], dormitory_1: ['Free'] },
    dorms: [new MowerDormState(['dormitory_1', 0], 'S', 0)] })
}


describe('native priority replacement bed takeover', () => {
  it.each([false, true])('takes a standby bed with free room disabled (emptyOnly=%s)', emptyOnly => {
    const data = takeoverData(), queue = new MowerTaskQueue()
    const task = planMowerAlphaDormFill(data, queue, emptyOnly)
    expect(task?.plan.dormitory_1).toEqual(['R'])
    expect(task?.timeMicros).toBe(0)
    expect(data.dorms[0]!.name).toBe('S')
    expect(data.operators.R!.currentRoom).toBe('')
  })
  it('keeps the old return task and occupied bed until takeover execution', () => {
    const data = takeoverData(), queue = new MowerTaskQueue()
    const returning = new MowerTask({ type: T.SHIFT_ON, time: 4, plan: { room_1_2: ['S'] } })
    queue.tasks.push(returning)
    const task = planMowerAlphaDormFill(data, queue)
    expect(task?.plan.dormitory_1).toEqual(['R'])
    expect(queue.tasks).toContain(returning)
    expect(returning.plan).toEqual({ room_1_2: ['S'] })
    expect(returning.time).toBe(4)
    expect(data.dorms[0]!.name).toBe('S')
    expect(data.operators.S!.currentRoom).toBe('dormitory_1')
  })
  it('retains a displaced standby group anchor while another primary is recovering', () => {
    const data = takeoverData()
    data.operators.S!.group = 'g'
    data.operators.B = new MowerOperatorState({ name: 'B', room: 'room_1_2', index: 1,
      group: 'g', operatorType: 'high', restingPriority: 'high', mood: 3, timeStampMicros: 0,
      currentRoom: 'dormitory_1', currentIndex: 1 })
    data.plan.room_1_2!.push('B')
    data.plan.dormitory_1!.push('Free')
    data.dorms.push(new MowerDormState(['dormitory_1', 1], 'B', toMowerMicros(5)))
    const task = planMowerAlphaDormFill(data, new MowerTaskQueue())
    expect(task?.plan.dormitory_1).toEqual(['B', 'R'])
    expect(task?.plan.room_1_2).toBeUndefined()
    expect(data.dorms.map(bed => bed.name)).toEqual(['S', 'B'])
  })
  it('enforces protected tiers even if the physical-slot helper permits the bed', () => {
    const data = takeoverData()
    data.freeRoom = true
    data.restingPriorityNames.push('S')
    vi.spyOn(dorm, 'alphaSlotTakable').mockReturnValue(true)
    expect(planMowerAlphaDormFill(data, new MowerTaskQueue())).toBeUndefined()
  })
  it('uses the same takeover in the shared fill projection', () => {
    expect(mowerAlphaFillPlan(takeoverData(), []).dormitory_1).toEqual(['R'])
  })
  it.each(['high', 'low'] as const)('keeps completed %s primary beds protected', priority => {
    const data = takeoverData()
    data.freeRoom = true
    data.operators.S!.restingPriority = priority
    expect(planMowerAlphaDormFill(data, new MowerTaskQueue())).toBeUndefined()
  })
  it('keeps a completed equal-priority replacement bed protected', () => {
    const data = takeoverData()
    data.freeRoom = true
    data.operators.S!.operatorType = 'low'
    data.operators.owner!.replacement.push('S')
    data.priorityReplacement.push('S')
    expect(planMowerAlphaDormFill(data, new MowerTaskQueue())).toBeUndefined()
  })
  it.each(['name', 'slot', 'excluded'] as const)('preserves %s reservations', kind => {
    const data = takeoverData(), queue = new MowerTaskQueue()
    if (kind === 'excluded') { data.freeRoom = true; data.freeRoomExclusions.push('S') }
    else queue.tasks.push(new MowerTask({ type: T.SHIFT_OFF, time: 1,
      plan: kind === 'name' ? { room_1_1: ['R'] } : { dormitory_1: ['Free'] } }))
    expect(planMowerAlphaDormFill(data, queue)).toBeUndefined()
  })
  it.each([false, true])('does not invent measured mood for unknown replacements (estimate=%s)', estimated => {
    const data = takeoverData()
    data.operators.R!.timeStampMicros = undefined
    if (estimated) data.dormMoodEstimates.set('R', [2, 0])
    const task = planMowerAlphaDormFill(data, new MowerTaskQueue(), true)
    expect(task?.plan.dormitory_1).toEqual(estimated ? ['R'] : undefined)
    expect(data.operators.R!.timeStampMicros).toBeUndefined()
  })
  it('does not name unregistered cards in an occupied-bed takeover', () => {
    const data = takeoverData()
    data.operators.R!.timeStampMicros = undefined
    data.unregisteredIdleNames.push('unknown-card')
    data.restingPriorityNames.push('unknown-card')
    data.dormMoodEstimates.set('unknown-card', [1, 0])
    expect(planMowerAlphaDormFill(data, new MowerTaskQueue(), true)).toBeUndefined()
  })
  it('rejects expired card estimates for occupied beds', () => {
    const data = takeoverData()
    data.operators.R!.timeStampMicros = undefined
    data.dormMoodEstimates.set('R', [2, -toMowerMicros(1)])
    expect(planMowerAlphaDormFill(data, new MowerTaskQueue())).toBeUndefined()
  })
  it.each([0, 20])('requires measured low mood for ordinary takeover (mood=%s)', mood => {
    const data = takeoverData()
    data.priorityReplacement = []
    data.operators.S!.operatorType = 'low'
    data.operators.R!.mood = mood
    expect(planMowerAlphaDormFill(data, new MowerTaskQueue())?.plan.dormitory_1)
      .toEqual(mood <= 19.2 ? ['R'] : undefined)
  })
  it('restricts empty-only occupied-bed takeover to priority replacements', () => {
    const data = takeoverData()
    data.priorityReplacement = []
    data.operators.S!.operatorType = 'low'
    expect(planMowerAlphaDormFill(data, new MowerTaskQueue(), true)).toBeUndefined()
  })
  it('keeps filling an ordinary empty bed with free room disabled', () => {
    const data = takeoverData()
    data.dorms[0]!.reset()
    data.operators.S!.currentRoom = 'room_1_2'
    data.priorityReplacement = []
    expect(planMowerAlphaDormFill(data, new MowerTaskQueue(), true)?.plan.dormitory_1).toEqual(['R'])
  })
})
