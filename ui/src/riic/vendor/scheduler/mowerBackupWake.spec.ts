import { describe, it, expect } from 'vitest'
import { createDefaultWorkspace } from '../workbench/defaults'
import { compileRosterSchedule } from './compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './scheduleAdapter'
import { createRosterRuntime, settleRoster, type RuntimeConfig } from './rosterRuntime'
import { retainMowerFailedTask } from './mowerTaskFailure'
import { createBackupPlanController } from './backupPlans'
import { getMowerSourceRuntime, settleMowerSource } from './mowerSourceRuntime'
import { MowerTask, MOWER_TASK_TYPES as T, toMowerMicros } from './mowerTaskQueue'

function fixture() {
  const workspace = createDefaultWorkspace()
  workspace.compatibility.backupPlans = [{ trigger: "op_data.inventory_count('赤金') >= 10" }]
  const schedule = compileRosterSchedule(workspace),
    config = compiledScheduleToRuntimeConfig(schedule)
  config.mowerAlpha = true
  const state = createRosterRuntime(config)
  state.mowerInventoryCounts = { 赤金: 0 }
  const controller = createBackupPlanController(schedule, state),
    source = getMowerSourceRuntime(state)
  source.initial = false
  source.queue.tasks = []
  const apply = (count: number, custom?: number) => {
    state.mowerInventoryCounts = { 赤金: count }
    state.mowerBackupGenerated = []
    state.mowerBackupContext =
      custom === undefined ? undefined : { customTimeMicros: toMowerMicros(custom) }
    controller.evaluate('END')
    delete state.mowerBackupContext
    const generated = state.mowerBackupGenerated ?? []
    for (const task of generated)
      if (!source.queue.tasks.includes(task)) source.queue.tasks.push(task)
    return generated
  }
  return { state, source, apply, controller }
}
const wakes = (f: ReturnType<typeof fixture>) =>
  f.source.queue.tasks.filter(
    (t) => t.type === T.NOT_SPECIFIC && !Object.keys(t.plan).length && !t.metadata
  )

describe('backup ordinary planning wake reuse', () => {
  it('keeps one original wake across sixteen real condition transitions', () => {
    const f = fixture()
    let first: MowerTask | undefined
    for (let index = 0; index < 16; index++) {
      const generated = f.apply(index % 2 ? 0 : 10)
      if (!first) {
        first = wakes(f)[0]
        expect(generated).toEqual([first])
      } else expect(generated).toEqual([])
      expect(wakes(f)).toHaveLength(1)
      expect(wakes(f)[0]).toBe(first)
    }
  })
  it.each([
    [-1, undefined, false],
    [0, undefined, false],
    [1, undefined, true],
    [1, 2, false],
    [2, 1, true]
  ])('preserves an existing deadline at %s for requested %s', (time, custom, added) => {
    const f = fixture(),
      original = new MowerTask({ time: time as number }),
      before = structuredClone(original)
    f.source.queue.tasks = [original]
    const generated = f.apply(10, custom as number | undefined)
    expect(original).toEqual(before)
    expect(f.source.queue.tasks).toContain(original)
    expect(wakes(f)).toHaveLength(added ? 2 : 1)
    expect(generated).toHaveLength(added ? 1 : 0)
    if (added) expect(generated[0]!.time).toBe(custom ?? 0)
  })
  it.each([
    ['metadata', 'other'],
    ['plan', { meeting: ['A'] }],
    ['moodControlEvent', { fingerprint: 'input', timeMicros: 0 }],
    ['workingReplacementCheck', { room: 'central', index: 0, owner: 'A', cover: 'B' }],
    ['executionFailure', { reason: 'failed', rooms: [], snapshot: {} }],
    ['executionRetained', true],
    ['strictMoodLimit', true],
    ['adjusted', true],
    ['moodLimit', 18],
    ['backupExplicitSlots', new Set(['central\0' + 0])],
    ['productLockNames', new Set(['A'])],
    ['urgentRecoveryReservedNames', ['A']],
    ['unknownPhase', undefined]
  ])('keeps different task meaning in %s', (key, value) => {
    const f = fixture(),
      original = new MowerTask({ time: -1 })
    Reflect.set(original, key, value)
    const before = structuredClone(original)
    f.source.queue.tasks = [original]
    const generated = f.apply(10)
    expect(original).toEqual(before)
    expect(f.source.queue.tasks).toContain(original)
    expect(generated).toHaveLength(1)
    expect(generated[0]).not.toBe(original)
  })
  it('does not reuse a task with specialized prototype behavior', () => {
    class SpecializedTask extends MowerTask {}
    const f = fixture(),
      original = new SpecializedTask()
    f.source.queue.tasks = [original]
    const generated = f.apply(10)
    expect(generated).toHaveLength(1)
    expect(generated[0]).not.toBe(original)
    expect(f.source.queue.tasks).toContain(original)
  })
  it('excludes the selected wake during the actual BEGINNING callback', () => {
    const f = fixture(),
      current = new MowerTask()
    f.source.queue.tasks = [current]
    f.source.firstInit = false
    f.state.mowerInventoryCounts = { 赤金: 10 }
    let checked = false
    settleMowerSource(f.state, { workRate: () => 0, recoveryRate: () => 0 }, (phase) => {
      if (phase === 'BEGINNING' && !checked) f.source.queue.tasks = [current]
      const changed = f.controller.evaluate(phase),
        generated = f.state.mowerBackupGenerated ?? []
      if (phase === 'BEGINNING' && !checked) {
        checked = true
        expect(generated).toHaveLength(1)
        expect(generated[0]).not.toBe(current)
      }
      return changed
    })
    expect(checked).toBe(true)
  })
  it('does not reuse the task currently being consumed', () => {
    const f = fixture(),
      current = new MowerTask()
    f.source.queue.tasks = [current]
    f.source.activeTask = current
    expect(f.apply(10)).toHaveLength(1)
    expect(wakes(f)).toHaveLength(2)
  })
})

describe('backup planning after actual arrangement completion', () => {
  it.each([T.RE_ORDER, T.SELF_CORRECTION])(
    'restores a plain wake after $key when the earlier wake was consumed and a failed empty task remains',
    (type) => {
      const config: RuntimeConfig = {
        mowerAlpha: true,
        mowerRunOrderEnabled: false,
        mowerTaskScheduling: { adjustForRunOrders: false },
        mowerSourcePlan: { room_1_1: [{ agent: 'A', group: '', replacement: ['R'] }] },
        positions: [{ id: 'room_1_1_0', roomId: 'room_1_1', primary: 'A', candidates: ['R'] }],
        beds: [],
        initialMorale: { A: 24, R: 24 },
        idleOperators: [],
        mowerPolicy: { restingThreshold: 0.65, powerPlantCount: 2, opeRestingPriority: [] },
        mowerRunLoopClock: { minimumClockStepMicros: 1, notificationSleepMicros: 1_000_000 },
        mowerDeviceTiming: { roomReturnMicros: 0 },
        mowerSourceRules: {
          workaholic: [],
          exhaustRequire: [],
          restInFull: [],
          lowPriority: [],
          refreshDrained: [],
          lingMode: 0
        }
      }
      const state = createRosterRuntime(config)
      state.occupants.room_1_1_0 = 'R'
      const source = getMowerSourceRuntime(state)
      source.initial = false
      source.firstInit = false
      const earlier = new MowerTask({ time: -1 }),
        failed = new MowerTask({ time: -1 }),
        physical = new MowerTask({ type, metadata: '副表内存收敛', plan: { room_1_1: ['A'] } })
      source.queue.tasks = [earlier, physical, failed]
      source.queue.consume(earlier)
      retainMowerFailedTask(state, source.data, failed, 'waiting for a relevant observation', [])
      const failure = failed.executionFailure,
        deadline = failed.timeMicros
      settleRoster(state, { workRate: () => 0, recoveryRate: () => 0 })
      expect(state.occupants.room_1_1_0).toBe('A')
      expect(source.queue.tasks).not.toContain(physical)
      expect(source.queue.tasks).toContain(failed)
      expect(failed.executionFailure).toBe(failure)
      expect(failed.timeMicros).toBe(deadline)
      expect(
        source.queue.tasks.some(
          (task) =>
            task !== failed &&
            task.type === T.NOT_SPECIFIC &&
            !task.executionFailure &&
            task.timeMicros <= toMowerMicros(state.time)
        )
      ).toBe(true)
      expect(source.queue.find()).not.toBe(failed)
      expect(state.diagnostics.filter((d) => d.code === 'mower-task-exception')).toEqual([])
    }
  )
})
