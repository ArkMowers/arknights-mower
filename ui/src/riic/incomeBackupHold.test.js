import { describe, expect, it } from 'vitest'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './vendor/scheduler/scheduleAdapter'
import { createBackupPlanController } from './vendor/scheduler/backupPlans'
import {
  advanceRoster,
  createRosterRuntime,
  nextRosterActionHours,
  settleRoster
} from './vendor/scheduler/rosterRuntime'
import { getMowerSourceRuntime } from './vendor/scheduler/mowerSourceRuntime'
import { MowerTask, MOWER_TASK_TYPES as T } from './vendor/scheduler/mowerTaskQueue'

const fang = 'char_123_fang'
const vanilla = 'char_240_wyvern'
const melantha = 'char_208_melan'
const beagle = 'char_122_beagle'
const nightingale = 'char_179_cgbird'
const keepers = ['char_124_kroos', 'char_120_hibisc', nightingale]
const rates = { workRate: () => 1, recoveryRate: () => 4 }

function fixture(observedHold = false, recovering = false) {
  const workspace = createDefaultWorkspace()
  const slot = (operatorId, groupId, replacements = []) => ({
    occupant: { kind: 'operator', operatorId },
    groupId,
    replacements
  })
  workspace.mainPlan.facilities.room_1_1.slots = [slot(fang, 'g', [vanilla])]
  workspace.mainPlan.facilities.room_1_2.slots = [slot(melantha, null, [beagle])]
  if (recovering) workspace.mainPlan.conf.rest_in_full = [fang]
  workspace.mainPlan.facilities.dormitory_1.slots = Array.from({ length: 5 }, () => ({
    occupant: { kind: 'free' },
    groupId: null,
    replacements: []
  }))
  keepers.forEach((name, index) => {
    workspace.mainPlan.facilities.dormitory_1.slots[index + 2] = slot(name, null)
  })
  workspace.compatibility.backupPlans = [
    {
      name: '共同休息',
      trigger: observedHold
        ? "op_data.operators['夜莺'].current_mood() < 10"
        : "op_data.operators['玫兰莎'].is_working() != True",
      plan: {},
      group_tasks: [{ group: 'g', action: 'off', mode: 'forced' }]
    }
  ]
  const schedule = compileRosterSchedule(workspace)
  const config = compiledScheduleToRuntimeConfig(schedule)
  config.mowerAlpha = true
  config.mowerRunLoopClock = { minimumClockStepMicros: 1, notificationSleepMicros: 1_000_000 }
  config.mowerDeviceTiming = { roomReturnMicros: 0 }
  const state = createRosterRuntime(config)
  const controller = createBackupPlanController(schedule, state)
  state.mowerShiftModel.activate([true], new MowerTask())
  const source = getMowerSourceRuntime(state)
  const data = source.data
  source.initial = false
  for (const op of Object.values(data.operators)) {
    Object.assign(op, {
      currentRoom: '',
      currentIndex: -1,
      mood: 24,
      timeStampMicros: 0,
      depletionRate: 0
    })
    state.morale[op.name] = 24
  }
  state.occupants = {
    room_1_1_0: vanilla,
    room_1_2_0: beagle,
    ...Object.fromEntries(keepers.map((name, index) => ['dormitory_1_' + (index + 2), name]))
  }
  state.bedOccupants = { dormitory_1_0: fang, dormitory_1_1: melantha }
  for (const [position, name] of Object.entries({ ...state.occupants, ...state.bedOccupants })) {
    data.operators[name].setProjectedPosition(
      position.slice(0, position.lastIndexOf('_')),
      Number(position.slice(position.lastIndexOf('_') + 1))
    )
  }
  for (const [index, name] of [
    [0, fang],
    [1, melantha]
  ]) {
    const bed = data.dorms.find(
      (item) => item.position[0] === 'dormitory_1' && item.position[1] === index
    )
    bed.name = name
    bed.timeMicros = 0
  }
  data.groupShiftState.g = true
  if (observedHold) {
    data.operators[nightingale].mood = 5
    state.morale[nightingale] = 5
  }
  if (recovering) {
    data.operators[fang].mood = 12
    state.morale[fang] = 12
    data.getDormByName(fang)[1].timeMicros = 3 * 3_600_000_000
  }
  const task = new MowerTask({
    type: T.SELF_CORRECTION,
    plan: { room_1_1: [fang], room_1_2: [melantha] }
  })
  source.queue.tasks = [task]
  return { state, source, data, task, controller }
}

function dispatch(state, controller, done) {
  for (let step = 0; step < 40 && !done(); step++) {
    settleRoster(state, rates, 0, controller.evaluate)
    if (done()) break
    const next = nextRosterActionHours(state, rates)
    if (!Number.isFinite(next)) break
    if (next > 0) advanceRoster(state, next, rates)
  }
}

describe('effective backup holds during return dispatch', () => {
  it('executes the return that exits a forced-rest backup', () => {
    const { state, source, task, controller } = fixture()
    const time = task.timeMicros
    dispatch(
      state,
      controller,
      () => state.occupants.room_1_1_0 === fang && state.occupants.room_1_2_0 === melantha
    )
    expect(state.occupants.room_1_1_0).toBe(fang)
    expect(state.occupants.room_1_2_0).toBe(melantha)
    expect(source.data.planConditions).toEqual([false])
    expect(task.arrangementStarted).toBe(true)
    expect(task.timeMicros).toBe(time)
    expect(task.executionFailure).toBeUndefined()
  })

  it('retains a still-held return, allows independent work and resumes the original task after exit', () => {
    const { state, source, task, controller } = fixture(true)
    const time = task.timeMicros
    const plan = structuredClone(task.plan)
    settleRoster(state, rates, 0, controller.evaluate)
    expect(task.executionFailure?.reason).toBe('副表要求整组强制下班，等待副表退出')
    const failure = task.executionFailure
    const independent = new MowerTask()
    source.queue.tasks.push(independent)
    for (let repeat = 0; repeat < 4; repeat++) settleRoster(state, rates, 0, controller.evaluate)
    expect(source.queue.tasks).not.toContain(independent)
    expect(source.queue.tasks).toContain(task)
    expect(task.executionFailure).toBe(failure)
    expect(task.timeMicros).toBe(time)
    expect(task.plan).toEqual(plan)
    expect(state.occupants.room_1_1_0).toBe(vanilla)
    state.morale[nightingale] = 24
    Object.assign(source.data.operators[nightingale], { mood: 24, timeStampMicros: 1 })
    dispatch(state, controller, () => !source.queue.tasks.includes(task))
    expect(state.occupants.room_1_1_0).toBe(fang)
    expect(state.occupants.room_1_2_0).toBe(melantha)
    expect(task.arrangementStarted).toBe(true)
    expect(task.timeMicros).toBe(time)
    expect(task.executionFailure).toBeUndefined()
  })

  it('keeps mandatory physical recovery when a projected return exits the hold', () => {
    const { state, source, controller } = fixture(false, true)
    settleRoster(state, rates, 0, controller.evaluate)
    expect(state.occupants.room_1_1_0).toBe(vanilla)
    expect(Object.values(state.bedOccupants)).toContain(fang)
    dispatch(state, controller, () => state.occupants.room_1_1_0 === fang)
    expect(state.occupants.room_1_1_0).toBe(fang)
    expect(state.time).toBeGreaterThanOrEqual(3)
    expect(source.data.planConditions).toEqual([false])
  })
})
