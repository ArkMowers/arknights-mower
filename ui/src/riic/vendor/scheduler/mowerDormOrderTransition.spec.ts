import { describe, expect, it } from 'vitest'
import { createDefaultWorkspace } from '../workbench/defaults'
import { resolveOperatorCharId as id } from '../domain/operatorIdentifiers'
import { compileRosterSchedule } from './compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './scheduleAdapter'
import { createRosterRuntime } from './rosterRuntime'
import { createBackupPlanController } from './backupPlans'
import { getMowerSourceRuntime } from './mowerSourceRuntime'
import { projectMowerArrangements } from './mowerObservations'
import { prepareMowerShiftCycle } from './mowerShiftCycle'
import { alphaPosition } from './mowerAlphaDorm'
import { MowerTask, MOWER_TASK_TYPES as T, toMowerMicros } from './mowerTaskQueue'

function fixture(sameOrder = false, leaving = false, ordinaryFirst = false) {
  const workspace = createDefaultWorkspace()
  for (const room of Object.values(workspace.mainPlan.facilities)) room.slots = []
  const slot = (name: string, cover = '') => ({
    occupant: { kind: 'operator' as const, operatorId: id(name) },
    groupId: null,
    replacements: cover ? [id(cover)] : []
  })
  workspace.mainPlan.facilities.central.slots = [slot('芬', '克洛丝')]
  workspace.mainPlan.facilities.meeting.slots = [slot('香草', '空爆')]
  for (const [room, managers] of [['dormitory_1', ['杜林', '闪灵']], ['dormitory_2', ['流明', '蜜莓']]] as const)
    workspace.mainPlan.facilities[room].slots = [
      ...managers.map(name => slot(name)),
      ...Array.from({ length: 3 }, () => ({ occupant: { kind: 'free' as const }, groupId: null, replacements: [] }))
    ]
  workspace.mainPlan.conf.dorm_order = 'dormitory_1,dormitory_2'
  workspace.compatibility.backupPlans = [{
    trigger: "op_data.inventory_count('赤金') >= 10",
    conf: { dorm_order: sameOrder ? 'dormitory_1,dormitory_2' : ordinaryFirst ? 'dormitory_2,dormitory_2_low,dormitory_1' : 'dormitory_2,dormitory_1' }
  }]
  const schedule = compileRosterSchedule(workspace, { dormIsolation: [[id('芬'), id('香草')]] }), config = compiledScheduleToRuntimeConfig(schedule)
  config.mowerAlpha = true
  const state = createRosterRuntime(config)
  state.mowerInventoryCounts = { 赤金: leaving ? 10 : 0 }
  const controller = createBackupPlanController(schedule, state)
  if (leaving) controller.evaluate('END')
  const source = getMowerSourceRuntime(state)
  source.queue.tasks = []
  delete state.mowerBackupGenerated
  for (const op of Object.values(source.data.operators)) {
    op.currentRoom = op.room
    op.currentIndex = op.index
    op.mood = 24
    op.timeStampMicros = 0
  }
  for (const [name, cover, room, dorm, mood] of [
    ['芬', '克洛丝', 'central', leaving ? 'dormitory_2' : 'dormitory_1', 5],
    ['香草', '空爆', 'meeting', leaving ? 'dormitory_1' : 'dormitory_2', 12]
  ] as const) {
    const op = source.data.operators[id(name)]!, replacement = source.data.operators[id(cover)]!
    Object.assign(op, { currentRoom: dorm, currentIndex: 2, mood, dormRecoveryRoom: dorm, dormRecoveryIndex: 2 })
    replacement.currentRoom = room
    replacement.currentIndex = 0
    const bed = source.data.dorms.find(b => b.position[0] === dorm && b.position[1] === 2)!
    bed.name = op.name
    bed.timeMicros = toMowerMicros(2)
  }
  state.mowerInventoryCounts = { 赤金: leaving ? 0 : 10 }
  return { state, source, controller }
}

function finalArrangement(f: ReturnType<typeof fixture>) {
  return projectMowerArrangements(f.source.data, (f.state.mowerBackupGenerated ?? []).map(t => t.plan))
}

describe('effective dorm order changes through backup transitions', () => {
  it.each([false, true])('reallocates existing single targets when leaving=%s', leaving => {
    const f = fixture(false, leaving), originalRoom = leaving ? 'dormitory_2' : 'dormitory_1'
    f.controller.evaluate('END')
    expect(f.controller.active).toEqual([!leaving])
    const final = finalArrangement(f), expected = leaving ? 'dormitory_1' : 'dormitory_2'
    expect(final.operators[id('芬')]!.currentRoom).toBe(expected)
    expect(final.operators[id('香草')]!.currentRoom).not.toBe(expected)
    expect(final.currentOperator('dormitory_1', 0)?.name).toBe(id('杜林'))
    expect(final.currentOperator('dormitory_2', 0)?.name).toBe(id('流明'))
    expect(final.operators[id('芬')]!.dormRecoveryRoom).toBe('')
    expect(final.getDormByName(id('芬'))?.[1].timeMicros).toBeUndefined()
    expect(f.source.data.operators[id('芬')]!.currentRoom).toBe(originalRoom)
    expect(f.source.data.operators[id('芬')]!.dormRecoveryRoom).toBe(originalRoom)
  })

  it('keeps existing single targets when a backup leaves the effective order unchanged', () => {
    const f = fixture(true)
    f.controller.evaluate('END')
    expect(f.controller.active).toEqual([true])
    const final = finalArrangement(f)
    expect(final.operators[id('芬')]!.currentRoom).toBe('dormitory_1')
    expect(final.operators[id('芬')]!.dormRecoveryRoom).toBe('dormitory_1')
    expect(final.operators[id('香草')]!.currentRoom).toBe('dormitory_2')
  })

  it.each(['name', 'slot', 'product', 'locked-return'] as const)('preserves a real %s reservation during reallocation', reservation => {
    const f = fixture(), deadline = toMowerMicros(1)
    if (reservation === 'product') f.source.data.reservedProductBeds.set(alphaPosition('dormitory_1', 2), id('芬'))
    else {
      const task = new MowerTask({ type: reservation === 'locked-return' ? T.SHIFT_ON : T.RE_ORDER, time: 1, plan: {
        dormitory_1: ['Current', 'Current', reservation === 'slot' ? 'Free' : id('芬'), 'Current', 'Current']
      } })
      task.productShiftLocked = reservation === 'locked-return'
      f.source.queue.tasks = [task]
    }
    const pending = f.source.queue.tasks[0]
    f.controller.evaluate('END')
    expect(finalArrangement(f).operators[id('芬')]!.currentRoom).toBe('dormitory_1')
    if (pending) {
      expect(f.source.queue.tasks).toContain(pending)
      expect(pending.timeMicros).toBe(deadline)
    }
  })

  it('retains the new allocation through the complete shift preview', () => {
    const f = fixture(), task = new MowerTask({ type: T.SHIFT_OFF })
    const observed = f.source.data.dorms.map(b => [b.name, b.timeMicros])
    f.source.queue.tasks = [task]
    prepareMowerShiftCycle(f.source.data, task, f.source.queue, f.state.mowerShiftModel!)
    const final = projectMowerArrangements(f.source.data, [task.plan])
    expect(final.operators[id('芬')]!.currentRoom).toBe('dormitory_2')
    expect(final.operators[id('香草')]!.currentRoom).toBe('dormitory_1')
    expect(f.controller.active).toEqual([false])
    expect(task.backupShiftConditions).toEqual([true])
    expect(f.source.data.dorms.map(b => [b.name, b.timeMicros])).toEqual(observed)
  })

  it.each(['controller', 'shift', 'product'] as const)('preserves isolation when ordinary beds precede another dorm through %s', path => {
    const f = fixture(false, false, true)
    let final
    if (path === 'controller') {
      f.controller.evaluate('END')
      final = finalArrangement(f)
    } else {
      const task = new MowerTask({ type: T.SHIFT_OFF })
      task.productShiftLocked = path === 'product'
      f.source.queue.tasks = [task]
      prepareMowerShiftCycle(f.source.data, task, f.source.queue, f.state.mowerShiftModel!)
      const arranged = structuredClone(task.plan)
      prepareMowerShiftCycle(f.source.data, task, f.source.queue, f.state.mowerShiftModel!)
      expect(task.plan).toEqual(arranged)
      final = projectMowerArrangements(f.source.data, [task.plan])
    }
    expect(final.operators[id('芬')]!.currentRoom).toBe('dormitory_2')
    expect(final.operators[id('香草')]!.currentRoom).toBe('dormitory_1')
    expect(final.operators[id('香草')]!.currentIndex).toBe(2)
  })
})
