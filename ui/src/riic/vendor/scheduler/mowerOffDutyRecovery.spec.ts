import {describe, expect, it} from 'vitest'
import {mowerCorrectionPlan, mowerOffDutyFullRecoveryMembers, prepareMowerCorrectionRecovery, planMowerCorrection, planMowerReturnRecovery, refreshMowerDerivedCorrection} from './mowerCorrection'
import {projectMowerArrangements} from './mowerObservations'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData, MowerDormState} from './mowerSchedulingData'
import {retainMowerFailedTask, resumeMowerFailedTasks} from './mowerTaskFailure'
import {MowerTask, MowerTaskQueue, MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {createRosterRuntime, advanceRoster, nextRosterActionHours, settleRoster, type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {planMowerMetadata} from './mowerMetadata'
import {mowerRecoveryReady} from './mowerGroupRecovery'
import {mowerPendingReturnAllowsRecovery} from './mowerRetainedRecovery'
import {mowerDormTaskReservations} from './mowerAlphaCandidates'
import {syncMowerBackupGroupTasks} from './mowerBackupGroupTasks'
import {mowerDormFillerId} from './mowerDormFiller'
import {admitMowerDerivedTasks} from './mowerTaskDerivation'
import {parkMowerPreviewRecovery} from './mowerPreviewRecoveryWait'
import {cloneMowerShiftTask} from './mowerShiftCycle'

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

function automaticFixture() {
  const result = fixture(), {data} = result
  Object.assign(data.operators.A!, {
    mood: 21.45297546308452, upperLimit: 24, restMoodLimit: false,
    restInFull: false, timeStampMicros: undefined,
  })
  data.policy.predictiveMoodControl = true
  data.calculatedMoodSnapshot = {timeMicros: data.nowMicros, values: {A: 21.45297546308452, B: 24, K: 24, R: 24, S: 24}}
  for (const op of Object.values(data.operators)) op.calculatedMoodSnapshot = data.calculatedMoodSnapshot
  data.groupRecoveryFullMembers.g = ['A']
  data.groupRecoveryReturnMicros.g = 0
  return result
}

describe('off-duty primaries requiring full recovery', () => {
  it('restores a lost bed for an automatic group recovery member using current physical mood', () => {
    const {data} = automaticFixture()
    const plan = mowerCorrectionPlan(data)
    const projected = projectMowerArrangements(data, [plan])
    expect(plan.central ?? []).not.toContain('A')
    expect(projected.operators.A!.isResting()).toBe(true)
    expect(projected.currentOperator('central', 0)?.name).toBe('R')
    expect(data.operators.A!.currentRoom).toBe('')
    expect(data.operators.A!.timeStampMicros).toBeUndefined()
    expect(data.operators.A!.restInFull).toBe(false)
    expect(data.dorms.every(bed => !bed.name)).toBe(true)
    // 下一次房间观测确认恢复完成后，仍走正常整组回班规划。
    projected.nowMicros = 3_600_000_000
    Object.assign(projected.operators.A!, {mood: 24, timeStampMicros: projected.nowMicros, moodIsPrediction: false})
    projected.calculatedMoodSnapshot = {timeMicros: projected.nowMicros, values: {...projected.calculatedMoodSnapshot!.values, A: 24}}
    for (const op of Object.values(projected.operators)) op.calculatedMoodSnapshot = projected.calculatedMoodSnapshot
    expect(mowerRecoveryReady(projected, projected.operators.A)).toBe(true)
    const returns = new MowerTaskQueue()
    planMowerMetadata(projected, returns)
    expect(returns.tasks.some(task => task.type === T.SHIFT_ON && task.plan.central?.[0] === 'A')).toBe(true)
  })

  it.each([false, true])('rebuilds an automatic group recovery without replacing the retained request, restored=%s', restored => {
    const {data, queue, state, task: original} = automaticFixture()
    const task = restored ? Object.assign(new MowerTask(), structuredClone(original), {type: T.SELF_CORRECTION}) : original
    if (restored) {
      data.groupRecoveryFullMembers = JSON.parse(JSON.stringify(data.groupRecoveryFullMembers))
      data.groupRecoveryReturnMicros = JSON.parse(JSON.stringify(data.groupRecoveryReturnMicros))
    }
    queue.tasks = [task]
    retainMowerFailedTask(state, data, task, '组员尚未确认回满心情，保留回班任务并等待有效恢复观察：A')
    const time = task.timeMicros
    expect(resumeMowerFailedTasks(state, data, queue)).toBe(true)
    expect(queue.tasks).toEqual([task])
    expect(task.timeMicros).toBe(time)
    expect(task.executionFailure).toBeUndefined()
    expect(projectMowerArrangements(data, [task.plan]).operators.A!.isResting()).toBe(true)
    const plan = structuredClone(task.plan)
    for (let i = 0; i < 3; i++) expect(resumeMowerFailedTasks(state, data, queue)).toBe(false)
    expect(task.plan).toEqual(plan)
    expect(task.timeMicros).toBe(time)
  })

  it('keeps automatic group recovery atomic until enough beds become available', () => {
    const {data} = automaticFixture()
    Object.assign(data.operators.B!, {group: 'g', currentRoom: '', currentIndex: -1, mood: 12})
    Object.assign(data.operators.S!, {currentRoom: 'meeting', currentIndex: 0})
    data.calculatedMoodSnapshot = {timeMicros: 0, values: {...data.calculatedMoodSnapshot!.values, B: 12}}
    for (const op of Object.values(data.operators)) op.calculatedMoodSnapshot = data.calculatedMoodSnapshot
    data.groupRecoveryFullMembers.g = ['A', 'B']
    const released = data.dorms.pop()!
    const blocked = mowerCorrectionPlan(data)
    expect(Object.values(blocked).flat()).not.toContain('A')
    expect(Object.values(blocked).flat()).not.toContain('B')
    expect(data.dorms.every(bed => !bed.name)).toBe(true)
    data.dorms.push(released)
    const admitted = projectMowerArrangements(data, [mowerCorrectionPlan(data)])
    expect(admitted.operators.A!.isResting()).toBe(true)
    expect(admitted.operators.B!.isResting()).toBe(true)
    expect(admitted.currentOperator('central', 0)?.name).toBe('R')
    expect(admitted.currentOperator('meeting', 0)?.name).toBe('S')
  })

  it.each(['capped', 'excluded', 'forced-work', 'group-working', 'standby', 'independent', 'working', 'full', 'unknown'] as const)(
    'does not impose automatic group recovery after it becomes ineligible: %s', kind => {
      const {data, task} = automaticFixture(), op = data.operators.A!
      if (kind === 'capped') {
        data.groupMoodGapMaxExtraWaitHours = 1
        data.nowMicros = 2 * 3_600_000_000
        data.calculatedMoodSnapshot = {...data.calculatedMoodSnapshot!, timeMicros: data.nowMicros}
      }
      if (kind === 'excluded') data.groupMoodGapExclusions = ['g']
      if (kind === 'forced-work') {
        data.backupGroupTasks = [[{group: 'g', action: 'on', mode: 'forced'}]]
        data.planConditions = [true]
      }
      if (kind === 'group-working') data.groupShiftState.g = false
      if (kind === 'standby') op.restingPriority = 'standby'
      if (kind === 'independent') op.groupBindings = [{group: 'g', replacement: ['R']}, {group: '', replacement: ['R']}]
      if (kind === 'working') {op.currentRoom = 'central'; op.currentIndex = 0}
      if (kind === 'full') data.calculatedMoodSnapshot = {timeMicros: 0, values: {...data.calculatedMoodSnapshot!.values, A: 24}}
      if (kind === 'unknown') data.calculatedMoodSnapshot = {timeMicros: 0, values: {}}
      for (const worker of Object.values(data.operators)) worker.calculatedMoodSnapshot = data.calculatedMoodSnapshot
      expect(mowerOffDutyFullRecoveryMembers(data).has('A')).toBe(false)
      expect(prepareMowerCorrectionRecovery(data, task, [])).toBe(false)
      expect(data.operators.A!.restInFull).toBe(false)
    },
  )

  it('retains an existing automatic recovery after a legacy group loses all beds without confirmed duty state', () => {
    const {data} = automaticFixture()
    delete data.groupShiftState.g
    expect(projectMowerArrangements(data, [mowerCorrectionPlan(data)]).operators.A!.isResting()).toBe(true)
  })

  it('keeps explicit full recovery binding when the automatic extra-wait cap expires', () => {
    const {data} = automaticFixture()
    data.operators.A!.restInFull = true
    data.groupMoodGapMaxExtraWaitHours = 1
    data.nowMicros = 2 * 3_600_000_000
    data.calculatedMoodSnapshot = {...data.calculatedMoodSnapshot!, timeMicros: data.nowMicros}
    for (const op of Object.values(data.operators)) op.calculatedMoodSnapshot = data.calculatedMoodSnapshot
    expect(projectMowerArrangements(data, [mowerCorrectionPlan(data)]).operators.A!.isResting()).toBe(true)
  })

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

  it.each(['explicit', 'automatic'] as const)('dispatches %s recovery before a stored ordinary correction can recall the idle primary', mode => {
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
      mowerSourceRules: {workaholic: [], exhaustRequire: [], restInFull: mode === 'explicit' ? ['A'] : [], lowPriority: [], refreshDrained: [], lingMode: 0},
      mowerTaskScheduling: {adjustForRunOrders: false}, mowerDeviceTiming: {roomReturnMicros: 500_000},
    }
    const state = createRosterRuntime(config), source = getMowerSourceRuntime(state)
    source.initial = false; source.firstInit = false
    state.occupants.central_0 = 'R'
    Object.assign(source.data.operators.A!, {currentRoom: '', currentIndex: -1, mood: 10.187, timeStampMicros: 0, upperLimit: 12, restMoodLimit: true})
    Object.assign(source.data.operators.R!, {currentRoom: 'central', currentIndex: 0, timeStampMicros: 0})
    source.data.groupShiftState.g = true
    if (mode === 'automatic') {
      source.data.groupRecoveryFullMembers.g = ['A']
      source.data.groupRecoveryReturnMicros.g = 0
    }
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


describe('recovery owned by a pending ordinary return', () => {
  it.each(['queued', 'retained'] as const)('admits an automatic recovery before its own %s return', state => {
    const {data} = automaticFixture()
    const returning = new MowerTask({type: T.SHIFT_ON, plan: {central: ['A']}})
    if (state === 'retained') returning.executionRetained = true
    const plan = structuredClone(returning.plan), time = returning.timeMicros
    const correction = mowerCorrectionPlan(data, false, new Set(), [returning])
    expect(projectMowerArrangements(data, [correction]).operators.A!.isResting()).toBe(true)
    expect(returning.plan).toEqual(plan)
    expect(returning.timeMicros).toBe(time)
  })

  it.each(['queued', 'plain', 'once', 'waiting', 'self-clear', 'neutral-clear', 'stale-slot', 'stale-name', 'no-capacity'] as const)('keeps actual return ownership through %s recovery', mode => {
    const config: RuntimeConfig = {
      mowerAlpha: true,
      positions: [{id: 'central_0', roomId: 'central', primary: 'A', candidates: ['R'], group: 'g'},
        {id: 'dormitory_1_0', roomId: 'dormitory_1', primary: 'K', candidates: [], permanent: true, dormitory: true}],
      beds: [{id: 'dormitory_1_1', roomId: 'dormitory_1', vip: true}],
      initialMorale: {A: 10, R: 24, K: 24},
      mowerPolicy: {restingThreshold: .5, powerPlantCount: 2, opeRestingPriority: []},
      mowerSourcePlan: {central: [{agent: 'A', group: 'g', replacement: ['R']}],
        dormitory_1: [{agent: 'K', group: '', replacement: []}, {agent: 'Free', group: '', replacement: []}]},
      mowerSourceRules: {workaholic: [], exhaustRequire: [], restInFull: [], lowPriority: [], refreshDrained: [], lingMode: 0},
      mowerTaskScheduling: {adjustForRunOrders: false},
    }
    config.mowerDormFillers = mode === 'neutral-clear'
    if (mode === 'stale-slot' || mode === 'stale-name') {config.beds!.push({id:'dormitory_1_2',roomId:'dormitory_1',vip:false});config.mowerSourcePlan!.dormitory_1!.push({agent:'Free',group:'',replacement:[]});config.initialMorale!.S=24;config.idleOperators=['S']}
    const state = createRosterRuntime(config), source = getMowerSourceRuntime(state)
    source.initial = false; source.firstInit = false
    state.occupants.central_0 = 'R'
    state.occupants.dormitory_1_0 = 'K'
    Object.assign(source.data.operators.K!, {currentRoom:'dormitory_1',currentIndex:0,mood:24,timeStampMicros:0})
    if (mode === 'neutral-clear') {const filler=mowerDormFillerId('dormitory_1',1);state.bedOccupants.dormitory_1_1=filler;Object.assign(source.data.operators[filler]!, {currentRoom:'dormitory_1',currentIndex:1,timeStampMicros:0})}
    Object.assign(source.data.operators.A!, {currentRoom: '', currentIndex: -1, mood: 10, timeStampMicros: 0})
    Object.assign(source.data.operators.R!, {currentRoom: 'central', currentIndex: 0, timeStampMicros: 0})
    source.data.groupShiftState.g = true
    source.data.groupRecoveryFullMembers.g = ['A']
    source.data.groupRecoveryReturnMicros.g = 0
    let returning = new MowerTask({type: T.SHIFT_ON, plan: {central: ['A'], ...(mode === 'self-clear' || mode === 'neutral-clear' ? {dormitory_1:['Current','Free']} : {})}})
    if (mode === 'once') {source.data.backupGroupTasks=[[{group:'g',action:'on',mode:'once'}]];source.data.planConditions=[true];syncMowerBackupGroupTasks(source.data,source.queue,{issued:new Set()});returning=source.queue.tasks.find(task=>task.backupGroupRequest)!}
    source.queue.tasks = [returning]
    if (mode === 'waiting') {source.data.planConditions=[true];const original=Object.assign(new MowerTask(),returning,{plan:structuredClone(returning.plan)});returning.plan={};returning.previewReturnVeto={conditions:[0],names:['A']};expect(parkMowerPreviewRecovery(source,returning,original,[returning])).toBe(true)}
    if (mode !== 'queued' && mode !== 'once' && mode !== 'waiting') retainMowerFailedTask(state, source.data, returning, '组员尚未确认回满心情，保留回班任务并等待有效恢复观察：A', ['central'], 'resource-wait')
    const originalPlan = structuredClone(returning.plan), originalTime = returning.timeMicros
    const rates = {workRate: () => 0, recoveryRate: () => 4}
    if (mode === 'stale-slot' || mode === 'stale-name') {
      const child=planMowerReturnRecovery(source.data,source.queue,returning)!
      expect(child.plan.dormitory_1?.[1]).toBe('A')
      const other=new MowerTask({type:T.FILL_DORM,time:10,plan:{dormitory_1:['Current',mode==='stale-slot'?'S':'Current',mode==='stale-name'?'A':'Current']}})
      other.dormFillPlan=structuredClone(other.plan);source.queue.tasks.push(other)
    }
    if (mode === 'no-capacity') {
      source.data.operators.M=new MowerOperatorState({name:'M',room:'contact',index:0,operatorType:'high',currentRoom:'dormitory_1',currentIndex:1,mood:0,timeStampMicros:0})
      source.data.plan.contact=['M'];state.bedOccupants.dormitory_1_1='M';state.morale.M=0;source.data.dorms[0]!.name='M';source.data.dorms[0]!.timeMicros=360_000_000_000
    }
    expect(returning.plan).toEqual(originalPlan)
    expect(returning.timeMicros).toBe(originalTime)
    for (let i = 0; i < 8 && !Object.values(state.bedOccupants).includes('A'); i++) settleRoster(state, rates)
    if (mode === 'stale-name' || mode === 'no-capacity') {
      expect(Object.values(state.bedOccupants)).not.toContain('A')
      const count=source.queue.tasks.length,trace=source.trace.length
      for(let i=0;i<5;i++)settleRoster(state,rates)
      expect(source.queue.tasks).toHaveLength(count);expect(source.trace).toHaveLength(trace)
      expect(source.queue.tasks).toContain(returning);expect(returning.plan.central).toEqual(['A'])
      expect(state.morale.A).toBe(10)
      if(mode==='no-capacity'){delete state.bedOccupants.dormitory_1_1;source.data.dorms[0]!.reset();Object.assign(source.data.operators.M!,{currentRoom:'',currentIndex:-1,mood:24});state.morale.M=24}
      else source.queue.tasks=source.queue.tasks.filter(task=>task===returning||task.type!==T.FILL_DORM)
      for(let i=0;i<8&&!Object.values(state.bedOccupants).includes('A');i++)settleRoster(state,rates)
    }
    expect(state.bedOccupants[mode==='stale-slot'?'dormitory_1_2':'dormitory_1_1']).toBe('A')
    expect(state.occupants.central_0).toBe('R')
    expect(source.queue.tasks.includes(returning)||source.waitingRecovery?.some(wait=>wait.task===returning)).toBe(true)
    expect(returning.plan.central).toEqual(['A'])
    for (let i = 0; i < 40 && state.occupants.central_0 !== 'A'; i++) {
      settleRoster(state, rates)
      if (state.occupants.central_0 === 'A') break
      const delay = nextRosterActionHours(state, rates)
      if (!Number.isFinite(delay)) break
      advanceRoster(state, Math.max(delay, 1 / 3_600_000_000), rates)
    }
    expect(state.occupants.central_0).toBe('A')
    expect(state.time).toBeCloseTo(3.5, 5)
    expect(source.queue.tasks).not.toContain(returning)
    expect(source.trace.filter(task => task.type === 'SHIFT_ON' && task.plan.central?.[0] === 'A')).toHaveLength(1)
  })
})


it.each(['arrangementStarted','backupShiftActive','productShiftLocked','strictMoodLimit','exhaustSupport','ordinaryCoordination','preferredReplacementRestore','advanceSupportSwap','explicit','product-name','product-slot','restore','retry','urgent','fia','other-target','metadata','global-product'] as const)('keeps the %s return reservation binding',kind=>{
 const {data}=automaticFixture(),owner=new MowerTask({type:T.SHIFT_ON,plan:{central:['A']}})
 owner.executionRetained=true
 if(['arrangementStarted','backupShiftActive','productShiftLocked','strictMoodLimit','exhaustSupport','ordinaryCoordination','preferredReplacementRestore','advanceSupportSwap'].includes(kind))Object.assign(owner,{[kind]:true})
 if(kind==='explicit')owner.backupExplicitSlots.add('central\0'+0)
 if(kind==='product-name')owner.productLockNames.add('A')
 if(kind==='product-slot')owner.productLockSlots.add('central\0'+0)
 if(kind==='restore')owner.dormRecoveryRestore=['dormitory_1']
 if(kind==='retry')owner.arrangementRetryRoom='dormitory_1'
 if(kind==='urgent')owner.urgentRecoveryReservedNames=['A']
 if(kind==='fia')owner.fiaReturnTarget='A'
 if(kind==='other-target')owner.plan.meeting=['A']
 if(kind==='metadata')owner.metadata='A'
 if(kind==='global-product')data.reservedProductReplacements.add('A')
 expect(mowerPendingReturnAllowsRecovery(data,owner,'A')).toBe(false)
 const correction=mowerCorrectionPlan(data,false,new Set(),[owner])
 expect(Object.values(correction).flat()).not.toContain('A')
})

it('preserves another owner of the same name and all reserved beds',()=>{
 const {data}=automaticFixture(),owner=new MowerTask({type:T.SHIFT_ON,plan:{central:['A']}}),other=new MowerTask({type:T.FILL_DORM,plan:{dormitory_1:['Current','A','Current']}})
 owner.executionRetained=true
 const reserved=mowerDormTaskReservations(data,[owner,other],'A')
 expect(reserved.names.has('A')).toBe(true)
 expect(reserved.slots.has('dormitory_1\0'+1)).toBe(true)
 expect(Object.values(mowerCorrectionPlan(data,false,new Set(),[owner,other])).flat()).not.toContain('A')
})

it.each(['required','independent','nonrequired'] as const)('uses a same-group %s recovery only when return confirmation requires it',kind=>{
 const {data}=automaticFixture(),actor=data.operators.B!
 Object.assign(actor,{currentRoom:'',currentIndex:-1,group:'g',mood:12,restInFull:kind!=='required'})
 data.calculatedMoodSnapshot={timeMicros:0,values:{...data.calculatedMoodSnapshot!.values,B:12}}
 for(const op of Object.values(data.operators))op.calculatedMoodSnapshot=data.calculatedMoodSnapshot
 if(kind==='required')data.groupRecoveryFullMembers.g=['A','B']
 if(kind==='independent')actor.groupBindings=[{group:'g',replacement:['S']},{group:'',replacement:['S']}]
 if(kind==='nonrequired'){actor.restingPriority='standby';actor.restInFull=false}
 const owner=new MowerTask({type:T.SHIFT_ON,plan:{central:['A']}})
 owner.executionRetained=true
 expect(mowerPendingReturnAllowsRecovery(data,owner,'B')).toBe(kind==='required')
})

it('admits a production once-on request but preserves a forced-on override',()=>{
 const {data}=automaticFixture(),queue=new MowerTaskQueue()
 data.backupGroupTasks=[[{group:'g',action:'on',mode:'once'}]];data.planConditions=[true]
 syncMowerBackupGroupTasks(data,queue,{issued:new Set()})
 const owner=queue.tasks.find(task=>task.backupGroupRequest)!
 expect(owner.metadata).toBe('A')
 expect(mowerPendingReturnAllowsRecovery(data,owner,'A')).toBe(true)
 expect(projectMowerArrangements(data,[mowerCorrectionPlan(data,false,new Set(),[owner])]).operators.A!.isResting()).toBe(true)
 data.operators.A!.restInFull=true
 data.backupGroupTasks=[[{group:'g',action:'on',mode:'forced'}]]
 expect(mowerPendingReturnAllowsRecovery(data,owner,'A')).toBe(false)
})

it('keeps two return owners recovery beds separate during atomic group allocation',()=>{
 const {data}=automaticFixture()
 Object.assign(data.operators.B!,{currentRoom:'',currentIndex:-1,group:'h',restInFull:true,mood:12})
 Object.assign(data.operators.S!,{currentRoom:'meeting',currentIndex:0})
 data.groupShiftState.h=true
 data.calculatedMoodSnapshot={timeMicros:0,values:{...data.calculatedMoodSnapshot!.values,B:12}}
 for(const op of Object.values(data.operators))op.calculatedMoodSnapshot=data.calculatedMoodSnapshot
 const a=new MowerTask({type:T.SHIFT_ON,plan:{central:['A'],dormitory_1:['Current','Current','Free']}})
 const b=new MowerTask({type:T.SHIFT_ON,plan:{meeting:['B'],dormitory_1:['Current','Free','Current']}})
 a.executionRetained=b.executionRetained=true
 const correction=mowerCorrectionPlan(data,false,new Set(),[a,b])
 expect(correction.dormitory_1).toEqual(['Current','B','A'])
 expect(a.plan.dormitory_1).toEqual(['Current','Current','Free'])
 expect(b.plan.dormitory_1).toEqual(['Current','Free','Current'])
 const blocked=new MowerTask({type:T.FILL_DORM,plan:{dormitory_1:['Current','R','Current']}})
 const none=mowerCorrectionPlan(data,false,new Set(),[a,b,blocked])
 expect(Object.values(none).flat()).not.toContain('A')
 expect(Object.values(none).flat()).not.toContain('B')
})


it.each([false,true])('requires an active shared shift binding for implicit automatic recovery, active=%s',active=>{
 const {data}=automaticFixture(),b=data.operators.B!
 Object.assign(b,{currentRoom:'',currentIndex:-1,group:'g',restInFull:false,mood:12,shiftGroup:active?'g':undefined,
  groupBindings:[{group:'g',replacement:['S']},{group:'h',replacement:['S']}]})
 data.groupRecoveryFullMembers.g=['A','B']
 data.calculatedMoodSnapshot={timeMicros:0,values:{...data.calculatedMoodSnapshot!.values,B:12}}
 for(const op of Object.values(data.operators))op.calculatedMoodSnapshot=data.calculatedMoodSnapshot
 const owner=new MowerTask({type:T.SHIFT_ON,plan:{central:['A']}})
 expect(mowerPendingReturnAllowsRecovery(data,owner,'B')).toBe(active)
})

it('does not create an automatic recovery episode while proving an explicit peer prerequisite',()=>{
 const {data}=automaticFixture(),b=data.operators.B!,s=data.operators.S!
 data.groupRecoveryFullMembers={};data.groupRecoveryReturnMicros={}
 Object.assign(b,{group:'g',currentRoom:'',currentIndex:-1,restInFull:true,mood:12})
 Object.assign(data.operators.A!,{currentRoom:'dormitory_1',currentIndex:1})
 Object.assign(s,{room:'contact',index:0,operatorType:'high',group:'g',currentRoom:'dormitory_1',currentIndex:2,mood:0})
 data.plan.contact=['S']
 data.dorms[0]!.name='A';data.dorms[0]!.timeMicros=3_600_000_000
 data.dorms[1]!.name='S';data.dorms[1]!.timeMicros=36_000_000_000
 data.calculatedMoodSnapshot={timeMicros:0,values:{...data.calculatedMoodSnapshot!.values,B:12,S:0}}
 for(const op of Object.values(data.operators))op.calculatedMoodSnapshot=data.calculatedMoodSnapshot
 const owner=new MowerTask({type:T.SHIFT_ON,plan:{central:['A']}})
 expect(mowerPendingReturnAllowsRecovery(data,owner,'B')).toBe(true)
 expect(data.groupRecoveryFullMembers).toEqual({})
 expect(data.groupRecoveryReturnMicros).toEqual({})
})

it('admits only the owned recovery cell without releasing its cover to another correction',()=>{
 const {data}=automaticFixture(),owner=new MowerTask({type:T.SHIFT_ON,plan:{central:['A']}})
 owner.executionRetained=true
 const correction=new MowerTask({type:T.SELF_CORRECTION,plan:{dormitory_1:['Current','A','Current'],meeting:['R']}})
 expect(admitMowerDerivedTasks(data,[owner],[correction])).toEqual([correction])
 expect(correction.plan.dormitory_1).toEqual(['Current','A','Current'])
 expect(correction.plan.meeting).toBeUndefined()
})

it('includes parked owners in correction planning without dispatching the parked task',()=>{
 const {data,queue}=automaticFixture(),owner=new MowerTask({type:T.SHIFT_ON,plan:{central:['A']}})
 const reservation=new MowerTask({type:T.FILL_DORM,plan:{dormitory_1:['Current','S','R']}})
 queue.tasks=[owner]
 expect(planMowerCorrection(data,queue,true,undefined,false,undefined,{},[reservation])).toBeUndefined()
 expect(queue.tasks).toEqual([owner])
 const correction=planMowerCorrection(data,queue,true,undefined,false,undefined,{},[owner])!
 expect(correction.plan.dormitory_1).toContain('A')
 expect(queue.tasks).not.toContain(reservation)
 expect(queue.tasks.filter(task=>task===owner)).toHaveLength(1)
})


it('uses its own reserved recovery bed before public capacity needed by another retained return',()=>{
 const config:RuntimeConfig={mowerAlpha:true,
  positions:[{id:'central_0',roomId:'central',primary:'A',candidates:['R'],group:'g'},
   {id:'meeting_0',roomId:'meeting',primary:'B',candidates:['S'],group:'h'},
   ...['dormitory_1','dormitory_2'].map((room,i)=>({id:room+'_0',roomId:room,primary:'K'+i,candidates:[],permanent:true,dormitory:true}))],
  beds:['dormitory_1','dormitory_2'].map(room=>({id:room+'_1',roomId:room,vip:true})),
  initialMorale:{A:10,B:12,R:24,S:24,K0:24,K1:24},
  mowerPolicy:{restingThreshold:.5,powerPlantCount:2,opeRestingPriority:[]},
  mowerSourcePlan:{central:[{agent:'A',group:'g',replacement:['R']}],meeting:[{agent:'B',group:'h',replacement:['S']}],
   ...Object.fromEntries(['dormitory_1','dormitory_2'].map((room,i)=>[room,[{agent:'K'+i,group:'',replacement:[]},{agent:'Free',group:'',replacement:[]}]]))},
  mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},mowerTaskScheduling:{adjustForRunOrders:false}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 source.initial=false;source.firstInit=false
 state.occupants.central_0='R';state.occupants.meeting_0='S'
 for(const name of ['A','B'])Object.assign(source.data.operators[name]!,{currentRoom:'',currentIndex:-1,mood:state.morale[name],timeStampMicros:0})
 for(const [name,room] of [['R','central'],['S','meeting']])Object.assign(source.data.operators[name]!,{currentRoom:room,currentIndex:0,mood:24,timeStampMicros:0})
 source.data.groupShiftState={g:true,h:true};source.data.groupRecoveryFullMembers={g:['A'],h:['B']};source.data.groupRecoveryReturnMicros={g:0,h:0}
 const a=new MowerTask({type:T.SHIFT_ON,plan:{central:['A'],dormitory_2:['Current','Free']}}),b=new MowerTask({type:T.SHIFT_ON,plan:{meeting:['B']}})
 source.queue.tasks=[a,b]
 for(const owner of [a,b])retainMowerFailedTask(state,source.data,owner,'组员尚未确认回满心情，保留回班任务并等待有效恢复观察',Object.keys(owner.plan),'resource-wait')
 for(const [i,room] of ['dormitory_1','dormitory_2'].entries()){state.occupants[room+'_0']='K'+i;Object.assign(source.data.operators['K'+i]!,{currentRoom:room,currentIndex:0,mood:24,timeStampMicros:0})}
 const rates={workRate:()=>0,recoveryRate:()=>4}
 for(let i=0;i<8&&!Object.values(state.bedOccupants).includes('A');i++)settleRoster(state,rates)
 expect(state.bedOccupants.dormitory_1_1).toBe('B');expect(state.bedOccupants.dormitory_2_1).toBe('A')
 const childCount=source.trace.filter(task=>task.type==='SELF_CORRECTION').length,queued=source.queue.tasks.length
 for(let i=0;i<5;i++)settleRoster(state,rates)
 expect(source.trace.filter(task=>task.type==='SELF_CORRECTION')).toHaveLength(childCount)
 expect(source.queue.tasks).toHaveLength(queued)
 expect(source.trace.filter(task=>task.type==='SELF_CORRECTION').every(task=>Object.keys(task.plan).length>0)).toBe(true)
 expect(source.queue.tasks.includes(a)||source.waitingRecovery?.some(wait=>wait.task===a)).toBe(true)
 expect(source.queue.tasks.includes(b)||source.waitingRecovery?.some(wait=>wait.task===b)).toBe(true)
 for(let i=0;i<60&&state.occupants.central_0!=='A';i++){
  settleRoster(state,rates)
  if(state.occupants.central_0==='A')break
  if(state.occupants.meeting_0==='B')expect(state.bedOccupants.dormitory_2_1).toBe('A')
  const next=nextRosterActionHours(state,rates);if(!Number.isFinite(next))break
  advanceRoster(state,Math.max(next,1/3_600_000_000),rates)
 }
 expect(state.occupants.meeting_0).toBe('B');expect(state.occupants.central_0).toBe('A')
 expect(state.time).toBeCloseTo(3.5,5)
 expect(source.queue.tasks).not.toContain(a);expect(source.queue.tasks).not.toContain(b)
 expect(source.trace.filter(task=>task.type==='SHIFT_ON'&&task.plan.central?.[0]==='A')).toHaveLength(1)
 expect(source.trace.filter(task=>task.type==='SHIFT_ON'&&task.plan.meeting?.[0]==='B')).toHaveLength(1)
})


it.each([false,true])('revalidates only the child recovery scope beside another reserved future child, restored=%s',restored=>{
 const {data,queue}=automaticFixture()
 Object.assign(data.operators.B!,{currentRoom:'',currentIndex:-1,group:'h',restInFull:true,mood:12})
 Object.assign(data.operators.S!,{currentRoom:'meeting',currentIndex:0})
 data.groupShiftState.h=true
 data.calculatedMoodSnapshot={timeMicros:0,values:{...data.calculatedMoodSnapshot!.values,B:12}}
 for(const op of Object.values(data.operators))op.calculatedMoodSnapshot=data.calculatedMoodSnapshot
 const a=new MowerTask({type:T.SHIFT_ON,plan:{central:['A']}}),b=new MowerTask({type:T.SHIFT_ON,plan:{meeting:['B']}})
 a.executionRetained=b.executionRetained=true
 const future=new MowerTask({type:T.SELF_CORRECTION,time:1,plan:{dormitory_1:['Current','Current','B']}})
 future.derivedCorrection=true;future.returnRecoveryNames=['B']
 queue.tasks=[a,b,future]
 const original=planMowerReturnRecovery(data,queue,a)!
 const copied=cloneMowerShiftTask(original)
 expect(copied.returnRecoveryNames).toEqual(['A']);expect(copied.returnRecoveryNames).not.toBe(original.returnRecoveryNames)
 const child=restored?Object.assign(new MowerTask(),structuredClone(original),{type:T.SELF_CORRECTION}):original
 queue.tasks=queue.tasks.map(task=>task===original?child:task)
 expect(child.returnRecoveryNames).toEqual(['A'])
 const before=structuredClone(child.plan),time=child.timeMicros
 for(let i=0;i<5;i++){
  expect(refreshMowerDerivedCorrection(data,child,queue.tasks)).toBe(true)
  expect(child.plan).toEqual(before);expect(child.timeMicros).toBe(time)
  expect(planMowerReturnRecovery(data,queue,a)).toBeUndefined()
 }
 expect(projectMowerArrangements(data,[child.plan]).operators.A!.isResting()).toBe(true)
 expect(Object.values(child.plan).flat()).not.toContain('B')
 expect(queue.tasks).toHaveLength(4)
 expect(JSON.stringify(a)).not.toContain('returnRecoveryNames')
})
