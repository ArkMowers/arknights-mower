import {describe, expect, it} from 'vitest'
import {mowerCorrectionPlan, prepareMowerCorrectionRecovery} from './mowerCorrection'
import {projectMowerArrangements} from './mowerObservations'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData, MowerDormState} from './mowerSchedulingData'
import {retainMowerFailedTask, resumeMowerFailedTasks} from './mowerTaskFailure'
import {MowerTask, MowerTaskQueue, MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {createRosterRuntime, advanceRoster, nextRosterActionHours, settleRoster, type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'

function fixture() {
  const operators: Record<string, MowerOperatorState> = {}
  for (const [name, room, group, replacement] of [
    ['A', 'central', 'g', ['R']], ['B', 'meeting', '', ['S']],
    ['K', 'dormitory_1', '', []], ['R', '', '', []], ['S', '', '', []],
  ] as const) {
    operators[name] = new MowerOperatorState({
      name, room, group, index: room ? 0 : -1, replacement: [...replacement],
      currentRoom: room, currentIndex: room ? 0 : -1,
      operatorType: room ? 'high' : 'low', mood: 24, timeStampMicros: 0,
    })
  }
  Object.assign(operators.A!, {
    currentRoom: '', currentIndex: -1, mood: 10.18732413638751,
    upperLimit: 12, restMoodLimit: true, restInFull: true,
  })
  Object.assign(operators.R!, {currentRoom: 'central', currentIndex: 0})
  const data = new MowerSchedulingData({
    alpha: true, operators,
    plan: {central: ['A'], meeting: ['B'], dormitory_1: ['K', 'Free', 'Free']},
    dorms: [1, 2].map(i => new MowerDormState(['dormitory_1', i])),
    groupShiftState: {g: true}, nowMicros: 0,
  })
  const task = new MowerTask({type: T.SELF_CORRECTION, time: -1, plan: {central: ['A']}})
  task.derivedCorrection = true
  const queue = new MowerTaskQueue()
  queue.tasks = [task]
  const state = createRosterRuntime({positions: [], beds: []})
  return {data, task, queue, state}
}

describe('off-duty primaries requiring full recovery', () => {
  it.each([false, true])('assigns a bed below the personal limit without a recovery deadline, exhausted=%s', exhausted => {
    const {data} = fixture()
    data.operators.A!.exhaustRequire = exhausted
    const plan = mowerCorrectionPlan(data)
    const projected = projectMowerArrangements(data, [plan])
    expect(plan.central ?? []).not.toContain('A')
    expect(projected.operators.A!.isResting()).toBe(true)
    expect(projected.currentOperator('central', 0)?.name).toBe('R')
    expect(data.operators.A!.currentRoom).toBe('')
    expect(data.dorms.every(bed => !bed.name)).toBe(true)
  })

  it('uses a newer valid card observation when the saved mood is unknown', () => {
    const {data} = fixture()
    data.operators.A!.mood = 24
    data.operators.A!.timeStampMicros = undefined
    data.dormMoodEstimates.set('A', [10.187, 0])
    expect(projectMowerArrangements(data, [mowerCorrectionPlan(data)]).operators.A!.isResting()).toBe(true)
  })

  it('also restores an ordinary 24-mood full-recovery primary with no group or cover', () => {
    const {data} = fixture()
    Object.assign(data.operators.A!, {upperLimit: 24, restMoodLimit: false, group: '', replacement: []})
    Object.assign(data.operators.R!, {currentRoom: '', currentIndex: -1})
    const projected = projectMowerArrangements(data, [mowerCorrectionPlan(data)])
    expect(projected.operators.A!.isResting()).toBe(true)
    expect(projected.currentOperator('central', 0)).toBeUndefined()
  })

  it('keeps completed peers waiting with their covers while the off-duty member recovers', () => {
    const {data, task} = fixture()
    Object.assign(data.operators.B!, {group: 'g', currentRoom: '', currentIndex: -1})
    Object.assign(data.operators.S!, {currentRoom: 'meeting', currentIndex: 0})
    task.plan.meeting = ['B']
    expect(prepareMowerCorrectionRecovery(data, task, [])).toBe(true)
    const projected = projectMowerArrangements(data, [task.plan])
    expect(projected.operators.A!.isResting()).toBe(true)
    expect(projected.operators.B!.currentRoom).toBe('')
    expect(projected.currentOperator('meeting', 0)?.name).toBe('S')
  })

  it.each(['working', 'full', 'unknown', 'prediction', 'workaholic'])('does not invent an off-duty recovery for %s', kind => {
    const {data} = fixture(), op = data.operators.A!
    if (kind === 'working') {
      op.currentRoom = 'central'; op.currentIndex = 0
      data.operators.R!.currentRoom = ''; data.operators.R!.currentIndex = -1
    }
    if (kind === 'full') op.mood = 12
    if (kind === 'unknown') op.timeStampMicros = undefined
    if (kind === 'prediction') op.moodIsPrediction = true
    if (kind === 'workaholic') op.workaholic = true
    const plan = mowerCorrectionPlan(data)
    expect(Object.entries(plan).filter(([room]) => room.startsWith('dorm')).flatMap(([, row]) => row)).not.toContain('A')
  })

  it('keeps independent correction available when recovery beds are reserved, then admits after release', () => {
    const {data} = fixture()
    Object.assign(data.operators.B!, {currentRoom: '', currentIndex: -1, workaholic: true})
    const reservation = new MowerTask({type: T.FILL_DORM, time: 1, plan: {dormitory_1: ['Current', 'R', 'S']}})
    const plan = mowerCorrectionPlan(data, false, new Set(), [reservation])
    expect(plan.meeting).toEqual(['B'])
    expect(plan.central ?? []).not.toContain('A')
    expect(Object.values(plan).flat()).not.toContain('A')
    expect(projectMowerArrangements(data, [mowerCorrectionPlan(data)]).operators.A!.isResting()).toBe(true)
  })

  it('preserves a dorm assignment already present in the correction', () => {
    const {data, task} = fixture()
    task.plan.dormitory_1 = ['Current', 'S', 'Current']
    expect(prepareMowerCorrectionRecovery(data, task, [])).toBe(true)
    expect(task.plan.dormitory_1).toEqual(['Current', 'S', 'A'])
    expect(data.operators.A!.currentRoom).toBe('')
    expect(data.dorms.every(bed => !bed.name)).toBe(true)
  })

  it('does not duplicate recovery already owned by another pending task', () => {
    const {data, task} = fixture()
    const reserved = new MowerTask({type: T.FILL_DORM, time: 1, plan: {dormitory_1: ['Current', 'A', 'Current']}})
    const original = structuredClone(reserved.plan)
    prepareMowerCorrectionRecovery(data, task, [task, reserved])
    expect(Object.values(task.plan).flat()).not.toContain('A')
    expect(reserved.plan).toEqual(original)
    expect(projectMowerArrangements(data, [reserved.plan]).operators.A!.isResting()).toBe(true)
  })

  it('does not partially assign a group when too few recovery beds remain', () => {
    const {data} = fixture()
    Object.assign(data.operators.B!, {currentRoom: '', currentIndex: -1, mood: 10, restInFull: true, group: 'g'})
    Object.assign(data.operators.S!, {currentRoom: 'meeting', currentIndex: 0})
    data.dorms.pop()
    const plan = mowerCorrectionPlan(data)
    expect(Object.values(plan).flat()).not.toContain('A')
    expect(Object.values(plan).flat()).not.toContain('B')
    expect(data.dorms[0]!.name).toBe('')
  })

  it('rebuilds a retained ordinary recall as recovery without changing its identity or deadline', () => {
    const {data, task, queue, state} = fixture()
    task.backupShiftIntent = structuredClone(task.plan)
    task.backupShiftConditions = []
    retainMowerFailedTask(state, data, task, '组员尚未确认回满心情，保留回班任务并等待有效恢复观察：A')
    const time = task.timeMicros
    expect(resumeMowerFailedTasks(state, data, queue)).toBe(true)
    expect(queue.tasks).toEqual([task])
    expect(task.timeMicros).toBe(time)
    expect(task.executionFailure).toBeUndefined()
    expect(projectMowerArrangements(data, [task.plan]).operators.A!.isResting()).toBe(true)
    expect(task.backupShiftIntent).toBeUndefined()
    expect(resumeMowerFailedTasks(state, data, queue)).toBe(false)
  })

  it.each(['arrangementStarted', 'ordinaryCoordination', 'exhaustSupport', 'productShiftLocked'] as const)(
    'preserves a retained %s request while its actual recovery dependency remains unchanged', flag => {
      const {data, task, queue, state} = fixture()
      task[flag] = true
      retainMowerFailedTask(state, data, task, '组员尚未确认回满心情，保留回班任务并等待有效恢复观察：A')
      const plan = structuredClone(task.plan)
      for (let i = 0; i < 3; i++) expect(resumeMowerFailedTasks(state, data, queue)).toBe(false)
      expect(task.plan).toEqual(plan)
      expect(task.executionFailure).toBeDefined()
    },
  )

  it('dispatches recovery before a stored ordinary correction can recall the idle primary', () => {
    const config: RuntimeConfig = {
      mowerAlpha: true,
      positions: [
        {id: 'central_0', roomId: 'central', primary: 'A', candidates: ['R'], group: 'g', upperLimit: 12},
        {id: 'dormitory_1_0', roomId: 'dormitory_1', primary: 'K', candidates: [], permanent: true, dormitory: true},
      ],
      beds: [{id: 'dormitory_1_1', roomId: 'dormitory_1', vip: true}],
      initialMorale: {A: 10.187, R: 24, K: 24},
      mowerPolicy: {restingThreshold: .5, powerPlantCount: 2, opeRestingPriority: []},
      mowerSourcePlan: {
        central: [{agent: 'A', group: 'g', replacement: ['R']}],
        dormitory_1: [{agent: 'K', group: '', replacement: []}, {agent: 'Free', group: '', replacement: []}],
      },
      mowerSourceRules: {workaholic: [], exhaustRequire: [], restInFull: ['A'], lowPriority: [], refreshDrained: [], lingMode: 0},
      mowerTaskScheduling: {adjustForRunOrders: false}, mowerDeviceTiming: {roomReturnMicros: 500_000},
    }
    const state = createRosterRuntime(config), source = getMowerSourceRuntime(state)
    source.initial = false; source.firstInit = false
    state.occupants.central_0 = 'R'
    Object.assign(source.data.operators.A!, {currentRoom: '', currentIndex: -1, mood: 10.187, timeStampMicros: 0, upperLimit: 12, restMoodLimit: true})
    Object.assign(source.data.operators.R!, {currentRoom: 'central', currentIndex: 0, timeStampMicros: 0})
    source.data.groupShiftState.g = true
    const task = new MowerTask({type: T.SELF_CORRECTION, plan: {central: ['A']}})
    task.derivedCorrection = true
    source.queue.tasks = [task]
    const rates = {workRate: () => 0, recoveryRate: () => 4}
    for (let i = 0; i < 20 && !Object.values(state.bedOccupants).includes('A'); i++) {
      settleRoster(state, rates)
      const delay = nextRosterActionHours(state, rates)
      if (!Number.isFinite(delay) || delay > .1) break
      advanceRoster(state, Math.max(delay, 1 / 3_600_000_000), rates)
    }
    expect(state.bedOccupants.dormitory_1_1).toBe('A')
    expect(state.occupants.central_0).toBe('R')
    expect(task.executionFailure).toBeUndefined()
    expect(task.timeMicros).toBe(0)
  })
})
