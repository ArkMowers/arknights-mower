import { describe, expect, it } from 'vitest'
import { MowerOperatorState } from './vendor/scheduler/mowerOperatorState'
import { MowerSchedulingData, MowerDormState } from './vendor/scheduler/mowerSchedulingData'
import {
  alphaFindDormSlot,
  alphaPosition,
  alphaPrioritizeRecovery
} from './vendor/scheduler/mowerAlphaDorm'
import { projectMowerArrangements } from './vendor/scheduler/mowerObservations'
import {
  mowerResting,
  mowerTryReorder,
  mowerGetRestingPlan
} from './vendor/scheduler/mowerOrdinaryPlanning'
import { planMowerDormIsolation } from './vendor/scheduler/mowerDormIsolation'
import { MowerTaskQueue } from './vendor/scheduler/mowerTaskQueue'

function fixture(priority = true) {
  const operators = {}
  for (const [index, name] of ['绮良', '黑键'].entries()) {
    operators[name] = new MowerOperatorState({
      name,
      room: 'room_1_1',
      index,
      group: 'g',
      currentRoom: 'room_1_1',
      currentIndex: index,
      operatorType: 'high',
      restingPriority: 'high',
      mood: 8 + index,
      timeStampMicros: 0,
      replacement: ['R' + index]
    })
    operators['R' + index] = new MowerOperatorState({
      name: 'R' + index,
      mood: 24,
      timeStampMicros: 0
    })
  }
  const plan = { room_1_1: ['绮良', '黑键'] }
  const dorms = []
  for (const room of ['dormitory_1', 'dormitory_2']) {
    plan[room] = [room + 'K0', room + 'K1', 'Free', 'Free', 'Free']
    for (let index = 0; index < 2; index++) {
      const name = plan[room][index]
      operators[name] = new MowerOperatorState({
        name,
        room,
        index,
        currentRoom: room,
        currentIndex: index,
        operatorType: 'high',
        mood: 24,
        timeStampMicros: 0
      })
    }
    for (let index = 2; index < 5; index++) dorms.push(new MowerDormState([room, index]))
  }
  return new MowerSchedulingData({
    alpha: true,
    plan,
    operators,
    dorms,
    nowMicros: 0,
    dormOrder: ['dormitory_1', 'dormitory_1_low', 'dormitory_2', 'dormitory_3', 'dormitory_4'],
    restingPriorityNames: priority ? ['绮良', '黑键'] : []
  })
}
const misplaced = () => ({
  room_1_1: ['R0', 'R1'],
  dormitory_1: ['Current', 'Current', '绮良', 'Current', 'Current'],
  dormitory_2: ['Current', 'Current', '黑键', 'Current', 'Current']
})
const positions = (data) =>
  Object.fromEntries(
    ['绮良', '黑键'].map((name) => [
      name,
      [data.operators[name].currentRoom, data.operators[name].currentIndex]
    ])
  )
const together = { 绮良: ['dormitory_1', 2], 黑键: ['dormitory_1', 3] }

describe('income simulation respects explicit ordinary-bed priority', () => {
  it.each([true, false])(
    'retains both new arrivals in the preferred room, explicit priority=%s',
    (priority) => {
      const data = fixture(priority),
        used = new Set(),
        plan = { room_1_1: ['R0', 'R1'] }
      for (const name of ['绮良', '黑键']) {
        const index = alphaFindDormSlot(data, name, used, undefined, plan)
        used.add(index)
        const [room, slot] = data.dorms[index].position
        ;(plan[room] ??= Array(5).fill('Current'))[slot] = name
      }
      expect(projectMowerArrangements(data, [plan]).operators.黑键.currentRoom).toBe('dormitory_1')
      const before = JSON.stringify({
        positions: positions(data),
        beds: data.dorms,
        moods: Object.values(data.operators).map((o) => o.mood)
      })
      const result = alphaPrioritizeRecovery(data, plan)
      expect(positions(projectMowerArrangements(data, [result]))).toEqual(together)
      expect(
        JSON.stringify({
          positions: positions(data),
          beds: data.dorms,
          moods: Object.values(data.operators).map((o) => o.mood)
        })
      ).toBe(before)
    }
  )
  it('corrects a pending cross-room placement and remains stable after admission', () => {
    const data = fixture(),
      plan = misplaced(),
      before = structuredClone(plan)
    const result = alphaPrioritizeRecovery(data, plan),
      projected = projectMowerArrangements(data, [result])
    expect(positions(projected)).toEqual(together)
    expect(plan).toEqual(before)
    projected.operators.黑键.mood = 0
    expect(alphaPrioritizeRecovery(projected, result)).toEqual(result)
    expect(alphaPrioritizeRecovery(projected, {})).toEqual({})
  })
  it('uses the default single-target-first order when ordinary beds are not listed', () => {
    const data = fixture()
    data.dormOrder = ['dormitory_1', 'dormitory_2']
    expect(
      positions(projectMowerArrangements(data, [alphaPrioritizeRecovery(data, misplaced())]))
    ).toEqual({
      绮良: ['dormitory_1', 2],
      黑键: ['dormitory_2', 2]
    })
  })
  it.each(['queued', 'product'])('preserves a room protected by a %s reservation', (kind) => {
    const data = fixture(),
      plan = misplaced(),
      slot = alphaPosition('dormitory_1', 3)
    const reserved = kind === 'queued' ? new Set([slot]) : new Set()
    if (kind === 'product') data.reservedProductBeds.set(slot, 'R0')
    expect(alphaPrioritizeRecovery(data, plan, {}, reserved)).toEqual(plan)
  })
  it('applies the configured order through ordinary group downshift planning', () => {
    const data = fixture(),
      queue = new MowerTaskQueue()
    const plan = mowerResting(data, queue)
    expect(plan.room_1_1).toEqual(['R0', 'R1'])
    const reorder = mowerTryReorder(data, plan)
    expect(positions(projectMowerArrangements(data, [plan, reorder ?? {}]))).toEqual(together)
  })
})

function resident(data, name, room, index, mood = 10, priority = 'high') {
  data.operators[name] = new MowerOperatorState({
    name,
    operatorType: 'high',
    room: 'room_9_9',
    index: 0,
    currentRoom: room,
    currentIndex: index,
    mood,
    timeStampMicros: 0,
    restingPriority: priority
  })
  data.dorms.find((b) => b.position[0] === room && b.position[1] === index).name = name
}

it('retains a same-tier first-bed resident despite a more exhausted arrival', () => {
  const data = fixture(false)
  resident(data, '原住客', 'dormitory_1', 2, 20)
  const plan = { dormitory_1: ['Current', 'Current', 'Current', '绮良', '黑键'] }
  const final = projectMowerArrangements(data, [alphaPrioritizeRecovery(data, plan)])
  expect(final.currentOperator('dormitory_1', 2).name).toBe('原住客')
  expect(positions(final)).toEqual({ 绮良: ['dormitory_1', 3], 黑键: ['dormitory_1', 4] })
})
it('moves a lower-tier resident behind incoming high-priority residents without losing anyone', () => {
  const data = fixture(false)
  resident(data, '低优住客', 'dormitory_1', 2, 1, 'low')
  const plan = { dormitory_1: ['Current', 'Current', 'Current', '绮良', '黑键'] }
  const final = projectMowerArrangements(data, [alphaPrioritizeRecovery(data, plan)])
  expect(positions(final)).toEqual(together)
  expect(final.currentOperator('dormitory_1', 4).name).toBe('低优住客')
})
it('promotes an unfinished resident after the first-bed resident leaves', () => {
  const data = fixture(false)
  resident(data, '离开者', 'dormitory_1', 2, 24)
  resident(data, '恢复者', 'dormitory_1', 3, 8)
  const plan = { dormitory_1: ['Current', 'Current', 'Free', 'Current', 'Current'] }
  const result = alphaPrioritizeRecovery(data, plan)
  const final = projectMowerArrangements(data, [result])
  expect(final.currentOperator('dormitory_1', 2).name).toBe('恢复者')
  expect(final.currentOperator('dormitory_1', 3)).toBeUndefined()
  expect(alphaPrioritizeRecovery(final, result)).toEqual(result)
})
it('keeps full-morale fillers in compatible beds while promoting unfinished residents', () => {
  const data = fixture(false)
  resident(data, '满心情', 'dormitory_1', 4, 24)
  const final = projectMowerArrangements(data, [alphaPrioritizeRecovery(data, misplaced())])
  expect(positions(final)).toEqual(together)
  expect(final.currentOperator('dormitory_1', 4).name).toBe('满心情')
})
it('displaces a full-morale filler only when its bed is needed for recovery', () => {
  const data = fixture(false)
  resident(data, '满心情', 'dormitory_1', 2, 24)
  const plan = { dormitory_1: ['Current', 'Current', 'Current', '绮良', '黑键'] }
  const final = projectMowerArrangements(data, [alphaPrioritizeRecovery(data, plan)])
  expect(positions(final)).toEqual(together)
  expect(final.currentOperator('dormitory_1', 4).name).toBe('满心情')
})
it('includes same-round preceding admissions when correcting their placement', () => {
  const data = fixture(),
    preceding = misplaced()
  data.dorms.find((b) => b.position[0] === 'dormitory_1' && b.position[1] === 2).name = '绮良'
  data.dorms.find((b) => b.position[0] === 'dormitory_2' && b.position[1] === 2).name = '黑键'
  const result = alphaPrioritizeRecovery(data, {}, preceding)
  expect(positions(projectMowerArrangements(data, [preceding, result]))).toEqual(together)
})
it('preserves rooms containing a named reservation or a different pending admission', () => {
  const data = fixture(),
    plan = misplaced()
  expect(alphaPrioritizeRecovery(data, plan, {}, new Set(), new Set(['绮良']))).toEqual(plan)
  data.operators['预约者'] = new MowerOperatorState({ name: '预约者', mood: 5, timeStampMicros: 0 })
  data.dorms.find((b) => b.position[0] === 'dormitory_1' && b.position[1] === 4).name = '预约者'
  expect(alphaPrioritizeRecovery(data, plan)).toEqual(plan)
})

it('still applies explicit dorm isolation after recovery allocation', () => {
  const data = fixture()
  data.dormIsolation = [['绮良', '黑键']]
  const recovery = alphaPrioritizeRecovery(data, misplaced())
  expect(positions(projectMowerArrangements(data, [recovery]))).toEqual(together)
  const result = planMowerDormIsolation(data, recovery)
  const final = projectMowerArrangements(data, [result])
  expect(final.operators.绮良.currentRoom).not.toBe(final.operators.黑键.currentRoom)
  expect([final.operators.绮良.currentRoom, final.operators.黑键.currentRoom].sort()).toEqual([
    'dormitory_1',
    'dormitory_2'
  ])
})

function singleBedTakeover(moods = [2, 15, 18, 16, 19]) {
  const data = fixture(false)
  for (const [index, [name, room, slot]] of [
    ['冬时', 'dormitory_1', 2],
    ['芬', 'dormitory_1', 3],
    ['香草', 'dormitory_1', 4],
    ['翎羽', 'dormitory_2', 2],
    ['黑角', 'dormitory_2', 3]
  ].entries()) {
    resident(data, name, room, slot, moods[index])
  }
  data.operators.歌蕾蒂娅 = new MowerOperatorState({
    name: '歌蕾蒂娅',
    room: 'room_1_1',
    index: 2,
    currentRoom: 'room_1_1',
    currentIndex: 2,
    operatorType: 'high',
    restingPriority: 'high',
    mood: 10,
    timeStampMicros: 0
  })
  data.plan.room_1_1.push('歌蕾蒂娅')
  data.restingPriorityNames = ['歌蕾蒂娅']
  const plan = {
    room_1_1: ['Current', 'Current', 'Free'],
    dormitory_2: ['Current', 'Current', 'Current', 'Current', '歌蕾蒂娅']
  }
  return { data, plan }
}

function checkTakeover(data, plan) {
  const result = alphaPrioritizeRecovery(data, plan)
  const final = projectMowerArrangements(data, [result])
  expect(final.currentOperator('dormitory_1', 2)?.name).toBe('歌蕾蒂娅')
  for (const room of ['dormitory_1', 'dormitory_2']) {
    for (const index of [0, 1]) {
      expect(final.currentOperator(room, index)?.name).toBe(data.currentOperator(room, index)?.name)
    }
  }
  const resting = final.dorms.map((bed) => final.currentOperator(...bed.position)?.name).sort()
  expect(resting).toEqual(['冬时', '芬', '香草', '翎羽', '黑角', '歌蕾蒂娅'].sort())
  expect(alphaPrioritizeRecovery(final, result)).toEqual(result)
  expect(alphaPrioritizeRecovery(final, {})).toEqual({})
  return final
}

it('gives a displaced single-recovery resident a faster ordinary bed before less exhausted peers', () => {
  const { data, plan } = singleBedTakeover()
  const final = checkTakeover(data, plan)
  expect(final.operators.冬时.currentRoom).toBe('dormitory_1')
  expect(final.operators.香草.currentRoom).toBe('dormitory_2')
  // These ordinary beds have the same rate; the eligible incumbent need not move.
  expect(final.currentOperator('dormitory_1', 3)?.name).toBe('芬')
})

it('compares personal mood deficits after a single-recovery takeover, rather than raw mood', () => {
  const { data, plan } = singleBedTakeover([8, 2, 3, 16, 19])
  data.operators.芬.upperLimit = 12
  data.operators.香草.upperLimit = 12
  const final = checkTakeover(data, plan)
  expect(final.operators.冬时.currentRoom).toBe('dormitory_1')
  expect(final.operators.芬.currentRoom).toBe('dormitory_1')
  expect(final.operators.香草.currentRoom).toBe('dormitory_2')
})

it('retains existing beds when displaced and resident peers have equal priority and deficit', () => {
  const { data, plan } = singleBedTakeover([15, 15, 15, 15, 15])
  const final = checkTakeover(data, plan)
  for (const name of ['芬', '香草', '翎羽', '黑角']) {
    expect([final.operators[name].currentRoom, final.operators[name].currentIndex]).toEqual([
      data.operators[name].currentRoom,
      data.operators[name].currentIndex
    ])
  }
  expect(final.currentOperator('dormitory_2', 4)?.name).toBe('冬时')
})

it.each([12, 24])(
  'admits a retained full primary at cap %s through a completed filler bed',
  (upper) => {
    const data = fixture(false)
    for (const [index, bed] of data.dorms.entries())
      resident(data, '住客' + index, ...bed.position, index === 5 ? 24 : 14)
    const primary = data.operators.绮良
    primary.mood = primary.upperLimit = upper
    primary.restingPriority = 'standby'
    data.standbyNames = [primary.name]
    data.freeRoomExclusions = [primary.name]
    const plan = {}
    expect(mowerGetRestingPlan(data, [primary.name], [], plan)).toBe(true)
    const final = projectMowerArrangements(data, [plan, mowerTryReorder(data, plan) ?? {}])
    expect(final.operators.绮良.isResting()).toBe(true)
    expect(final.operators.住客5.currentRoom).toBe('')
    expect(final.currentOperator('room_1_1', 0)?.name).toBe('R0')
    expect(final.operators.住客0.isResting()).toBe(true)
  }
)

it.each(['primary', 'retained', 'excluded', 'reserved', 'unknown'])(
  'preserves %s protection for a full retained applicant',
  (restriction) => {
    const data = fixture(false)
    for (const [index, bed] of data.dorms.entries())
      resident(data, '住客' + index, ...bed.position, index === 5 ? 24 : 14)
    const primary = data.operators.绮良
    primary.mood = 24
    primary.restingPriority = 'standby'
    data.standbyNames = [primary.name]
    data.freeRoomExclusions = [primary.name]
    if (restriction === 'primary') data.operators.住客5.mood = 14
    if (restriction === 'unknown') primary.timeStampMicros = undefined
    if (restriction === 'retained') data.freeRoomExclusions.push('住客5')
    if (restriction === 'excluded') data.freeBlacklist.push(primary.name)
    const plan = {}
    const reservedSlots =
      restriction === 'reserved' ? new Set([alphaPosition(...data.dorms[5].position)]) : new Set()
    mowerGetRestingPlan(data, [primary.name], [], plan, { reservedSlots })
    expect(plan).toEqual({})
    expect(data.operators.住客5.isResting()).toBe(true)
  }
)

it.each(['high', 'standby'])(
  'keeps %s applicant priority when a retained full primary requests a standby bed',
  (priority) => {
    for (const mood of [5, 24]) {
      const data = fixture(false)
      for (const [index, bed] of data.dorms.entries())
        resident(data, '住客' + index, ...bed.position, 14)
      const primary = data.operators.绮良
      primary.mood = 24
      primary.restingPriority = priority
      data.standbyNames = ['住客5', ...(priority === 'standby' ? [primary.name] : [])]
      data.freeRoomExclusions = [primary.name]
      data.operators.住客5.mood = mood
      expect(alphaFindDormSlot(data, primary.name, new Set())).toBe(
        priority === 'high' || mood === 24 ? 5 : undefined
      )
    }
  }
)

it.each([5, 24])('admits a retained full standby over a lower-tier resident at mood %s', (mood) => {
  const data = fixture(false)
  for (const [index, bed] of data.dorms.entries())
    resident(data, '住客' + index, ...bed.position, 14)
  const primary = data.operators.绮良
  primary.mood = 24
  primary.restingPriority = 'standby'
  data.standbyNames = [primary.name]
  data.freeRoomExclusions = [primary.name]
  data.operators.住客5.mood = mood
  data.operators.住客5.operatorType = 'low'
  expect(alphaFindDormSlot(data, primary.name, new Set())).toBe(5)
})
