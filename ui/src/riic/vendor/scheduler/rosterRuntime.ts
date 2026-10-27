import {mowerInitialMorale} from './mowerInitialMorale'
import type {MowerReloadRequest,MowerReloadObservation} from './mowerReload'
import type {MowerClueRequest,MowerClueObservation} from './mowerClueLifecycle'
import type {MowerTodoTaskRequest,MowerTodoTaskObservation} from './mowerTodoTask'
import type {MowerNotificationRequest,MowerNotificationObservation} from './mowerNotification'
import type {RunOrderIORequest,RunOrderIOObservation} from './mowerRunOrderPlanning'
import type {MowerNativeIOWork} from './mowerRunOrderBridge'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'
import type { BackupTiming } from './backupPlans'
import {settleMowerSource,nextMowerSourceActionHours,type MowerSourceRuntime} from './mowerSourceRuntime'
import type {MowerTask} from './mowerTaskQueue'
import type {MowerShiftModel} from './mowerShiftCycle'
import type {MowerMoodLimitConfig} from './mowerMoodLimits'
import type {MowerBackupContext} from './mowerSourceRuntime'
import { mowerReturnDelay, mowerRescueDelay } from './mowerTiming'
import { applyFiammetta, type FiammettaPolicy } from './fiammettaPolicy'
import type { RunOrderPolicy } from './types'

export { compiledScheduleToRuntimeConfig, scheduleToRuntimeConfig, isShiftRunOperator } from './scheduleAdapter'

export const MORALE_EPSILON = 1e-8
export interface RuntimePosition {
  id: string; roomId: string; primary: string; candidates: string[]; group?: string
  shiftOffThreshold?: number; lowerLimit?: number; upperLimit?: number; exhaustRequired?: boolean; restToFull?: boolean; restMoodLimit?: boolean
  permanent?: boolean; dormitory?: boolean; restingPriority?: 'high' | 'low'
}
export interface RuntimeBed { id: string; roomId: string; vip: boolean; managedRecovery?: boolean }
export interface RuntimeConfig {
 majorMaintenanceStartHours?:number
 majorMaintenanceDurationHours?:number
 /** The application simulation selects the October 3 source contract. */
 mowerDormIsolation?:string[][]
 mowerAlpha?:boolean;mowerDormOrder?:string[]
 /** Operators with an unlocked single-target recovery skill in the active simulation roster. */
 mowerSingleRecoverySkillNames?:string[]
 mowerMoodLimits?:MowerMoodLimitConfig
  positions: RuntimePosition[]; beds: RuntimeBed[]; initialMorale?: Record<string, number>
  /** Default scene input uses native policy upper limits; explicit overrides remain unchanged except the fixed Fiammetta initial condition. */
  mowerInitialMorale?: { fromUpperLimit: boolean; explicitOperators: string[] }
  mowerSourcePlan?: Record<string,{agent:string;group:string;replacement:string[];groupBindings?:{group:string;replacement:string[]}[]}[]>
  mowerRecycleBuilt?: boolean
  /** Disable order tasks only for the old no-wake comparison. */
  mowerRunOrderEnabled?: boolean
  mowerDroneCountLimit?: number
  /** Source device back(0.5); absent for pure, frozen-clock decision fixtures. */
  mowerDeviceTiming?: {roomReturnMicros:number}
  /** Explicit headless outer-clock adapter, never used to alter task timestamps. */
  mowerRunLoopClock?: {minimumClockStepMicros:number;notificationSleepMicros:number}
  mowerSourceRules?: {workaholic:string[];exhaustRequire:string[];restInFull:string[];lowPriority:string[];refreshDrained:string[];refreshTrading?:string[];lingMode:number;standby?:string[];priorityReplacement?:string[];freeRoomExclusions?:string[]}
  fiammetta?: FiammettaPolicy; excludedCandidates?: string[]
  idleOperators?: string[]
  /** Game-owned Free card pool; omitted only by direct source-oracle fixtures. */
  availableIdleOperators?: string[]
  freeBlacklist?: string[]
  mowerDroneRoom?:string|null
  mowerDeviceObservations?:{initialManufactureDroneSelection:number|'max'}
  mowerServices?:{enableParty:boolean;droneIntervalHours:number;reloadRooms:readonly string[]|null;maaGapHours:number;leifengMode:boolean}
  mowerClueObservations?:{partyEndMicros:number|null;clueCount:number}
  mowerTaskScheduling?:MowerTaskSchedulingOptions
  mowerPolicy?: { predictiveMoodControl?:boolean; groupRestInFullOnMoodGap?:boolean; groupMoodGapThresholdMinutes?:number; groupMoodGapMaxExtraWaitHours?:number; groupMoodGapExclusions?:string[]; mergeIntervalMinutes?:number; restMoodLimits?: Record<string,number>; freeRoom?: boolean; taskBuffers?: boolean; rescueThreshold?: number; restingThreshold: number; groupRestingThresholds?: Record<string,number>; powerPlantCount: number; opeRestingPriority: string[] }
  runOrderPolicies?: RunOrderPolicy[]
}
export interface RuntimeEvent {
  time: number; type: 'shift-off' | 'shift-on' | 'fiammetta' | 'backup-plan' | 'backup-task' | 'rest-limit-release' | 'rest-bed-takeover' | 'exhaust-support'; operators: string[]
  backupIndex?: number; backupName?: string; active?: boolean; timing?: BackupTiming
  beds?: string[]; moraleBefore?: number[]; moraleAfter?: number[]; reason?: 'position-correction'
}
export interface RuntimeState {
  /** Current simulation inventory, keyed by the six native Chinese item names. */
  mowerInventoryCounts?: Readonly<Record<string, number>>
  /** Observed products with the base-plan fallback already applied by the host. */
  mowerFacilityProducts?: Readonly<Record<string, string | null>>
  /** Non-enumerable live query installed only for observed inventory/product conditions. */
  mowerBackupObservationWakeMicros?: () => number | undefined
  /** Explicit stable scene input shared by headless facility adapters. */
  mowerUI?:{scene:string;lastRoom:string}
  mowerSource?:MowerSourceRuntime; mowerBackupContext?:MowerBackupContext; mowerBackupGenerated?:MowerTask[]
  mowerShiftModel?:MowerShiftModel
  config: RuntimeConfig; time: number; occupants: Record<string, string>; morale: Record<string, number>
  /** First physical mood, including operators first introduced by a later backup. */
  initialMorale?: Record<string, number>
  workPositionChanges?: Record<string, number>
  bedOccupants: Record<string, string>; events: RuntimeEvent[]
  backupBedOccupants?: Set<string>
  pendingRest?: string[]
  /** Primaries with completed rest wait idle until their group returns. */
  completedRest?: string[]
  /** Workaholics follow group swaps but do not reserve recovery beds. */
  standbyWorkaholics?: string[]
  recoveryCompletedAt?: Record<string,number>
  recoveryCompletionTargets?: Record<string,number>
  nextPlanningTime?: number
  nextFiammettaCheckTime?: number
  returnDeadlines?: Record<string, number>; timingSignature?: string
  diagnostics: { code: string; message: string }[]; lastFiammettaTime: number
}
export interface RuntimeRates {
  mowerReloadIO?:(request:MowerReloadRequest,state:RuntimeState)=>MowerNativeIOWork<MowerReloadObservation>
  mowerClueIO?:(request:MowerClueRequest,state:RuntimeState)=>MowerNativeIOWork<MowerClueObservation>
  mowerTodoTaskIO?:(request:MowerTodoTaskRequest,state:RuntimeState)=>MowerNativeIOWork<MowerTodoTaskObservation>
  mowerNotificationIO?:(request:MowerNotificationRequest,state:RuntimeState)=>MowerNativeIOWork<MowerNotificationObservation>
  mowerTodoListVisible?:()=>boolean
  /** Real lifecycle observations; host advances time, morale and production. */
  mowerRunOrderIO?:(request:RunOrderIORequest,state:RuntimeState)=>MowerNativeIOWork<RunOrderIOObservation>
  workRate: (operatorId: string, roomId: string, state: RuntimeState) => number
  recoveryRate: (operatorId: string, roomId: string, state: RuntimeState) => number
  /** Stable rate tables for one physical-state sweep; callers must not mutate state while using them. */
  snapshotRates?:()=>{work:Readonly<Record<string,number>>;recovery:Readonly<Record<string,number>>}
  /** Isolated recall forecast: current projected consumption and conservative recovery. */
  forecastRates?:(state:RuntimeState)=>{work:Readonly<Record<string,number>>;recovery:Readonly<Record<string,number>>}
  /** Additional skill morale boundaries; callers can split intervals at non-roster events too. */
  thresholds?: (operatorId: string, state: RuntimeState) => number[]
}
export function createRosterRuntime(config: RuntimeConfig): RuntimeState {
  const s: RuntimeState = { config: structuredClone(config), time: 0, occupants: {}, morale: {}, bedOccupants: {}, events: [], diagnostics: [], lastFiammettaTime: -Infinity }
  const ids = new Set<string>()
  for (const p of config.positions) {
    if (s.occupants[p.id] || Object.values(s.occupants).includes(p.primary)) throw new Error('Duplicate roster occupancy')
    s.occupants[p.id] = p.primary
    ids.add(p.primary); p.candidates.forEach(id => ids.add(id))
  }
  if (new Set(config.beds.map(b => b.id)).size !== config.beds.length) throw new Error('Duplicate bed')
  if (config.fiammetta) { ids.add(config.fiammetta.operatorId); config.fiammetta.orderedTargets.forEach(id => ids.add(id)) }
  config.idleOperators?.forEach(id => ids.add(id))
  if(config.mowerSourcePlan)for(const slots of Object.values(config.mowerSourcePlan))for(const slot of slots){if(!['Free','Current',''].includes(slot.agent))ids.add(slot.agent);slot.replacement.forEach(id=>ids.add(id))}
  config.runOrderPolicies?.forEach(policy => policy.orderedOperatorIds.forEach(id => ids.add(id)))
  for (const id of ids) {
    const m = mowerInitialMorale(id, config.initialMorale?.[id] ?? 24)
    if (!Number.isFinite(m) || m < 0 || m > 24) throw new Error(`Invalid morale: ${id}`)
    s.morale[id] = m
  }
  s.initialMorale = {...s.morale}
  if (config.mowerPolicy && config.beds.length && config.idleOperators === undefined && config.availableIdleOperators === undefined) rosterDiagnostic(s,'idle-roster-unspecified','Mower Free card pool is unspecified in this direct fixture')
  return s
}
const lower = (p: RuntimePosition) => p.shiftOffThreshold ?? (p.exhaustRequired ? 0 : (p.lowerLimit ?? 0))
const upper = (p: RuntimePosition) => p.shiftOffThreshold !== undefined ? (p.upperLimit ?? 24) : p.restToFull ? 24 : (p.upperLimit ?? 24)
export function rosterDiagnostic(s: RuntimeState, code: string, message: string) {
  if (!s.diagnostics.some(d => d.code === code && d.message === message)) s.diagnostics.push({ code, message })
}
function freeBed(s: RuntimeState, p: RuntimePosition, occupied: Record<string, string>) {
  const ordered=s.config.beds.filter(b => b.managedRecovery !== false).sort((a, b) => p.restingPriority === 'low' ? Number(a.vip) - Number(b.vip) : Number(b.vip) - Number(a.vip))
  return ordered.find(b => {
    const id = occupied[b.id]
    if (!id) return true
    if (!s.config.mowerPolicy) return false
    // alpha _slot_takable: completed timers can yield even a main bed.
    if ((s.recoveryCompletedAt?.[id] ?? Infinity) < s.time - MORALE_EPSILON
      && (s.morale[id] ?? 0) >= restTarget(s,id) - MORALE_EPSILON) return true
    return !s.config.positions.some(q => q.primary === id) && p.restingPriority !== 'low'
  })
}
/** Mower's ordinary replacement pass is ordered greedy reservation, without backtracking. */
export function nextCandidate(p: RuntimePosition, s: RuntimeState, reserved = new Set<string>(), activeBeds: Record<string, string> = s.bedOccupants) {
  return p.candidates.find(id => !s.config.excludedCandidates?.includes(id) && !reserved.has(id)
    && !Object.values(s.occupants).includes(id)
    && (s.config.mowerPolicy ? !s.config.positions.some(pos => pos.primary === id) : !Object.values(activeBeds).includes(id) && (s.morale[id] ?? 0) > lower(p) + MORALE_EPSILON))
}
function restMoodLimit(s: RuntimeState, id: string): number | undefined {
  return s.config.mowerPolicy?.restMoodLimits?.[id] ?? s.config.positions.find(p => p.primary === id && p.restMoodLimit)?.upperLimit
}
function restTarget(s: RuntimeState, id: string): number {
  return restMoodLimit(s,id) ?? s.config.positions.find(p => p.primary === id)?.upperLimit ?? 24
}
function refreshRecoveryCompletion(s: RuntimeState): void {
  if (!s.config.mowerPolicy) return
  const completed = s.recoveryCompletedAt ??= {}
  const residents = new Set(s.config.beds.filter(b => b.managedRecovery !== false).map(b => s.bedOccupants[b.id]).filter((id): id is string => Boolean(id)))
  const targets = s.recoveryCompletionTargets ??= {}
  for (const id of Object.keys(targets)) if (!residents.has(id)) delete targets[id]
  for (const id of residents) {
    const target = restTarget(s,id)
    if (targets[id] !== undefined && targets[id] !== target) delete completed[id]
    targets[id] = target
  }
  for (const id of Object.keys(completed)) if (!residents.has(id) || (s.morale[id] ?? 0) < restTarget(s,id)-MORALE_EPSILON) delete completed[id]
  for (const id of residents) if ((s.morale[id] ?? 0) >= restTarget(s,id)-MORALE_EPSILON) completed[id] ??= s.time
}
function parkBedTakeover(s: RuntimeState, bed: string, incoming?: string): void {
  const id = s.bedOccupants[bed]
  if (!s.config.mowerPolicy || !id || !incoming || id === incoming || !s.config.positions.some(p => p.primary === id)
    || (s.morale[id] ?? 0) < restTarget(s,id)-MORALE_EPSILON) return
  s.completedRest = [...new Set([...(s.completedRest ?? []), id])]
  s.events.push({time:s.time,type:'rest-bed-takeover',operators:[id,incoming],beds:[bed]})
}
/** alpha plan_mood_limit_releases is independent of global free_room. */
function releaseLimitedRest(s: RuntimeState): void {
  if (!s.config.mowerPolicy) return
  const complete = (id: string) => { const target=restMoodLimit(s,id); return target !== undefined && (s.morale[id] ?? 0) >= target - MORALE_EPSILON }
  const parked = new Set([...(s.completedRest ?? []), ...(s.pendingRest ?? [])].filter(id => s.config.positions.some(p => p.primary === id) && (s.morale[id] ?? 0) >= restTarget(s,id)-MORALE_EPSILON && !Object.values(s.occupants).includes(id)))
  for (const [bed,id] of Object.entries(s.bedOccupants)) if (s.config.beds.find(b => b.id === bed)?.managedRecovery !== false && complete(id)) {
    delete s.bedOccupants[bed]
    parked.add(id)
    s.events.push({time:s.time,type:'rest-limit-release',operators:[id],beds:[bed]})
  }
  s.completedRest = [...parked].filter(id => s.config.positions.some(p => p.primary === id) && !Object.values(s.bedOccupants).includes(id))
  s.pendingRest = s.pendingRest?.filter(id => !parked.has(id))
  s.standbyWorkaholics = s.standbyWorkaholics?.filter(id => s.config.positions.some(p => p.permanent && !p.dormitory && p.primary === id && s.occupants[p.id] !== id) && !Object.values(s.occupants).includes(id) && !Object.values(s.bedOccupants).includes(id))
}
function releaseRecoveredSubstitutes(s: RuntimeState): void {
  // alpha scheduler_task.py: ordinary release tasks require global free_room.
  if (s.config.mowerPolicy && !s.config.mowerPolicy.freeRoom) return
  // Rested substitutes become available without occupying a work slot.
  for (const [bed, id] of Object.entries(s.bedOccupants)) {
    if (s.config.beds.find(b => b.id === bed)?.managedRecovery === false || s.backupBedOccupants?.has(id)) continue
    if ((s.morale[id] ?? 0) >= 24 - MORALE_EPSILON && !s.config.positions.some(p => p.primary === id && s.occupants[p.id] !== id)) delete s.bedOccupants[bed]
  }
}
function shiftThreshold(p: RuntimePosition, s: RuntimeState, rates?: RuntimeRates): number {
  if (!p.exhaustRequired || !s.config.mowerPolicy?.taskBuffers || !rates) return s.config.mowerPolicy && !p.exhaustRequired ? Math.min(lower(p),upper(p)-2) : lower(p)
  // base_schedule.py:1467–1497; first refresh at lower+2, fallback lower+.25 minus 30 minutes.
  return (p.lowerLimit ?? 0) + Math.min(2, .25 + rates.workRate(p.primary,p.roomId,s) * .5)
}
/** Guard against empty recovery cycles using the operator's mood floor.
 * The planning threshold is not a minimum return mood: Mower returns groups
 * according to their high-priority rest deadlines, including low-priority peers.
 */
function minimumNumericalReturnMorale(p: RuntimePosition, s: RuntimeState, rates: RuntimeRates): number {
  if ((p.roomId === 'factory' || p.roomId === 'train') && rates.workRate(p.primary, p.roomId, s) <= 0) return 0
  // Only prevent a zero-length recovery cycle in the ideal clock; alpha has no +2 return floor.
  return Math.min(upper(p), MORALE_EPSILON * 4)
}
/** alpha agent_get_mood: preserve valid all-resting peers, then correct positions.
 * Mixed groups include workaholics, as in the default alpha group sync pass.
 */
function reconcileMowerPositions(s: RuntimeState): void {
  const work = s.config.positions.filter(p => !p.dormitory)
  const actual = new Map(Object.entries(s.occupants).map(([slot,id]) => [id,slot]))
  const resting = new Set([...Object.values(s.bedOccupants), ...s.config.positions.filter(p => p.dormitory).map(p => s.occupants[p.id]).filter(Boolean)])
  const validRest = (p: RuntimePosition) => resting.has(p.primary) && !p.permanent && (s.morale[p.primary] ?? 0) < upper(p) - MORALE_EPSILON
  const targets = new Set<RuntimePosition>()
  const add = (p: RuntimePosition) => {
    const peers = p.group ? work.filter(q => q.group === p.group) : [p]
    peers.filter(q => actual.get(q.primary) !== q.id).forEach(q => targets.add(q))
  }
  // alpha's room pass repairs occupants outside the planned primary/candidate list.
  for (const p of work) {
    const current = s.occupants[p.id]
    if ((!current && p.candidates.length > 0) || (current && current !== p.primary && !p.candidates.includes(current))) targets.add(p)
  }
  for (const p of work) {
    const slot = actual.get(p.primary)
    if (slot === p.id || validRest(p)) continue
    // Failed bed admission is not a valid resting member; recall its group.
    // alpha: a valid resting peer protects full or workaholic group members.
    if (p.group && (p.permanent || (s.morale[p.primary] ?? 0) >= upper(p) - MORALE_EPSILON)
      && work.some(q => q.group === p.group && validRest(q))) continue
    add(p)
  }
  const groups = new Map<string,RuntimePosition[]>()
  for (const p of work) if (p.group) groups.set(p.group,[...(groups.get(p.group) ?? []),p])
  for (const ps of groups.values()) {
    const working = ps.some(p => actual.has(p.primary) && !resting.has(p.primary))
    if (working && ps.some(p => resting.has(p.primary) || !actual.has(p.primary))) ps.filter(p => actual.get(p.primary) !== p.id).forEach(p => targets.add(p))
  }
  // A BEFORE_DORM plan switch can remove the beds after work rooms moved.
  // Never leave a group queued forever when the new plan cannot house it.
  for (const p of work) if (s.pendingRest?.includes(p.primary)) {
    const members = p.group ? work.filter(q => q.group === p.group && !q.permanent) : [p]
    if (members.length > s.config.beds.filter(b => b.managedRecovery !== false).length) {
      members.filter(q => actual.get(q.primary) !== q.id).forEach(q => targets.add(q))
      rosterDiagnostic(s,'group-blocked', (p.group ? 'group:'+p.group : 'slot:'+p.id)+': insufficient available candidates or beds; original occupants retained')
    }
  }
  // alpha resting_correction.py: preserve a complete resting group's real covers.
  const protectedRest = new Set(work.filter(p => !p.permanent && resting.has(p.primary)
    && ((s.returnDeadlines?.[p.group ? 'group:'+p.group : 'slot:'+p.id] ?? -Infinity) > s.time + MORALE_EPSILON || (s.morale[p.primary] ?? 0) < upper(p)-MORALE_EPSILON)))
  for (const ps of groups.values()) if (ps.some(p => protectedRest.has(p))) {
    const ordinary = ps.filter(p => !p.permanent)
    if (ordinary.some(p => !resting.has(p.primary) && (actual.has(p.primary) || (s.morale[p.primary] ?? 0) < upper(p)-MORALE_EPSILON))) ordinary.forEach(p => protectedRest.delete(p))
    else ordinary.forEach(p => protectedRest.add(p))
  }
  const desired = new Map<RuntimePosition,string>(), recalling = new Set<string>(), reserved = new Set<string>()
  for (const p of targets) {
    if (!protectedRest.has(p)) { desired.set(p,p.primary); reserved.add(p.primary); continue }
    const current = s.occupants[p.id]
    if (current && p.candidates.includes(current)) continue
    const candidate = p.candidates.find(id => !s.config.excludedCandidates?.includes(id) && !reserved.has(id)
      && !work.some(q => q.primary === id) && !s.config.positions.some(q => q.dormitory && q.primary === id)
      && ![...protectedRest].some(q => q.primary === id)
      && (!Object.values(s.occupants).includes(id) || work.some(q => s.occupants[q.id] === id && targets.has(q) && !protectedRest.has(q) && q.primary !== id)))
    if (candidate) { desired.set(p,candidate); reserved.add(candidate) }
    else if (p.group) recalling.add(p.group)
    else desired.set(p,p.primary)
  }
  for (const group of recalling) work.filter(p => p.group === group).forEach(p => desired.set(p,p.primary))
  if (!desired.size) return
  const ids = new Set(desired.values())
  // Remove every mover before assigning any destination; cross-slot cycles are atomic.
  for (const [slot,id] of Object.entries(s.occupants)) if (ids.has(id)) delete s.occupants[slot]
  for (const [bed,id] of Object.entries(s.bedOccupants)) if (ids.has(id)) delete s.bedOccupants[bed]
  for (const [p,id] of desired) s.occupants[p.id] = id
  s.pendingRest = s.pendingRest?.filter(id => !ids.has(id))
  const corrected = new Map<string,string[]>()
  for (const [p,id] of desired) { const key = p.group ? 'group:'+p.group : 'slot:'+p.id; corrected.set(key,[...(corrected.get(key) ?? []),id]) }
  for (const operators of corrected.values()) s.events.push({time:s.time,type:'shift-on',operators,reason:'position-correction'})
  s.timingSignature = undefined
}
export function settleRoster(s: RuntimeState, rates?: RuntimeRates, retryDepth = 0, onPhase?: (phase: BackupTiming) => boolean): void {
  if(s.config.mowerSourcePlan&&rates){settleMowerSource(s,rates,onPhase);return}
  if (retryDepth > 64) throw new Error('副表同刻调度无法稳定')
  // alpha handle_error preserves an already queued NOT_SPECIFIC task.
  if (s.config.mowerPolicy && (s.nextPlanningTime === undefined || s.nextPlanningTime <= s.time + MORALE_EPSILON)) s.nextPlanningTime = s.time + 2.5
  refreshRecoveryCompletion(s)
  releaseLimitedRest(s)
  if (s.pendingRest?.length) {
    const pending = s.pendingRest.filter(id => !Object.values(s.occupants).includes(id) && !Object.values(s.bedOccupants).includes(id) && s.config.positions.some(p => p.primary === id))
    const groups = new Map<string,RuntimePosition[]>()
    for (const id of pending) {
      const p = s.config.positions.find(p => p.primary === id)!
      const key = s.config.mowerPolicy && p.group ? 'group:'+p.group : 'slot:'+p.id
      groups.set(key,[...(groups.get(key) ?? []),p])
    }
    const admitted = new Set<string>()
    for (const members of groups.values()) {
      const beds = {...s.bedOccupants}, assignments:{id:string;bed:string}[]=[],standby:string[]=[]
      const ordered = s.config.mowerPolicy ? [...members].sort((a,b) => Number(a.restingPriority !== 'low')-Number(b.restingPriority !== 'low')) : members
      let complete = true
      for (const p of ordered) {
        if (s.config.mowerPolicy && p.permanent) { standby.push(p.primary); continue }
        const bed = freeBed(s,p,beds)
        if (!bed) { complete=false; break }
        beds[bed.id]=p.primary
        assignments.push({id:p.primary,bed:bed.id})
      }
      if (!complete) continue
      for (const {bed,id} of assignments) parkBedTakeover(s,bed,id)
      s.bedOccupants=beds
      s.standbyWorkaholics=[...new Set([...(s.standbyWorkaholics ?? []),...standby])]
      members.forEach(p=>admitted.add(p.primary))
    }
    s.pendingRest=pending.filter(id=>!admitted.has(id))
  }
  releaseLimitedRest(s)
  if (s.config.mowerPolicy) reconcileMowerPositions(s)
  const swapped = applyFiammetta(s)
  const fiaTarget = swapped ? s.events[s.events.length - 1]?.operators[1] : undefined
  // Resolve completed rest before testing candidate availability at this timestamp.
  releaseRecoveredSubstitutes(s)
  const groups = new Map<string, RuntimePosition[]>()
  for (const p of s.config.positions.filter(p => !p.dormitory && !p.permanent)) {
    const key = p.group ? `group:${p.group}` : `slot:${p.id}`
    groups.set(key, [...(groups.get(key) ?? []), p])
  }
  if (rates && s.config.mowerPolicy) updateMowerReturnDeadlines(s,rates)
  const orderedGroups = [...groups].sort((a, b) => s.config.mowerPolicy ? Number(b[1].every(p => s.occupants[p.id] !== p.primary))-Number(a[1].every(p => s.occupants[p.id] !== p.primary)) || Math.min(...a[1].map(p => s.morale[p.primary]! - (p.lowerLimit ?? 0))) - Math.min(...b[1].map(p => s.morale[p.primary]! - (p.lowerLimit ?? 0))) : 0)
  // alpha average_mood counts non-resting high primaries, including a cap-completed
  // idle member. The ideal quota is a planning snapshot, not recomputed after each move.
  const recoveryBeds=s.config.beds.filter(b=>b.managedRecovery !== false)
  const restingIds=new Set([...Object.values(s.bedOccupants),...s.config.positions.filter(p=>p.dormitory).map(p=>s.occupants[p.id]).filter(Boolean)])
  const moodMembers=s.config.positions.filter(p=>!p.dormitory&&!p.permanent&&!restingIds.has(p.primary))
  const totalMoodRange=moodMembers.reduce((n,p)=>n+upper(p)-(p.lowerLimit??0),0)
  const averageMood=totalMoodRange?moodMembers.reduce((n,p)=>n+s.morale[p.primary]!-(p.lowerLimit??0),0)/totalMoodRange:0
  const idealResting=s.config.mowerPolicy && averageMood>s.config.mowerPolicy.restingThreshold*(s.config.mowerPolicy.rescueThreshold??.75)?Math.min(4,recoveryBeds.length):recoveryBeds.length
  // alpha resting() reserves one SHIFT_OFF batch before physically moving any covers.
  let ordinaryPlanning: RuntimeState | undefined
  let initialResting = 0, plannedCoverCount = 0, highDone = false
  const plannedCovers = new Set<string>()
  const ordinaryGroups: {members:RuntimePosition[];swaps:RestSwap[]}[] = []
  const activeResting = (state: RuntimeState) => recoveryBeds.map(b=>state.bedOccupants[b.id]).filter(id=>id && !((state.recoveryCompletedAt?.[id] ?? Infinity)<state.time-MORALE_EPSILON && (state.morale[id] ?? 0)>=restTarget(state,id)-MORALE_EPSILON) && state.config.positions.some(p=>p.primary===id && p.roomId !== 'factory' && p.roomId !== 'train'))
  // Each group is evaluated once per timestamp: return cannot immediately trigger another shift.
  for (const [key, original] of orderedGroups) {
    const ps = s.config.mowerPolicy ? [...original].sort((a,b) => Number(!s.config.fiammetta?.orderedTargets.includes(a.primary)) - Number(!s.config.fiammetta?.orderedTargets.includes(b.primary)) || (s.morale[a.primary]! - (a.lowerLimit ?? 0)) - (s.morale[b.primary]! - (b.lowerLimit ?? 0))) : original
    const resting = ps.every(p => s.occupants[p.id] !== p.primary)
    const high = ps.filter(p => p.restingPriority !== 'low')
    const returnMembers = high.length ? high : ps
    const fullMembers = returnMembers.filter(p => p.restToFull)
    const recovered = (p: RuntimePosition) => (s.morale[p.primary] ?? 0) >= upper(p) - MORALE_EPSILON
    const fiaReturn = Boolean(s.config.mowerPolicy && fiaTarget && ps.some(p => p.primary === fiaTarget))
    const deadline = s.returnDeadlines?.[key]
    const usefulRecovery = !s.config.mowerPolicy || !rates || ps.every(p => (s.morale[p.primary] ?? 0) >= minimumNumericalReturnMorale(p, s, rates) - MORALE_EPSILON)
    const ready = usefulRecovery && (fiaReturn || (s.config.mowerPolicy && deadline !== undefined ? s.time >= deadline - MORALE_EPSILON : s.config.mowerPolicy ? (fullMembers.length ? fullMembers.every(recovered) : returnMembers.some(recovered)) : ps.every(recovered)))
    if (resting && ready) {
      if (onPhase?.('BEFORE_WORK')) { settleRoster(s, rates, retryDepth + 1, onPhase); return }
      // generate_plan_by_drom recalls the whole group, including a released workaholic.
      const recalled = [...ps, ...s.config.positions.filter(p => p.permanent && !p.dormitory && p.group === ps[0]?.group && Boolean(p.group) && (s.config.mowerPolicy ? s.occupants[p.id] !== p.primary : s.completedRest?.includes(p.primary)))]
      const covers = recalled.map(p => s.occupants[p.id]!)
      for (const p of recalled) {
        for (const [bed, id] of Object.entries(s.bedOccupants)) if (id === p.primary) delete s.bedOccupants[bed]
        for (const [slot, id] of Object.entries(s.occupants)) if (id === p.primary && slot !== p.id) delete s.occupants[slot]
        s.occupants[p.id] = p.primary
      }
      s.pendingRest = [...new Set([...(s.pendingRest ?? []), ...covers.filter(Boolean)])]
      s.events.push({ time: s.time, type: 'shift-on', operators: recalled.map(p => p.primary) })
      if (onPhase?.('BEFORE_DORM')) { settleRoster(s, rates, retryDepth + 1, onPhase); return }
      covers.forEach((id, i) => {
        if (id && (s.morale[id] ?? 24) < 24 - MORALE_EPSILON) {
          const bed = freeBed(s, { ...recalled[i]!, restingPriority: 'low' }, s.bedOccupants)
          if (bed) { parkBedTakeover(s,bed.id,id); s.bedOccupants[bed.id] = id }
        }
      })
      if (s.returnDeadlines) delete s.returnDeadlines[key]
      s.pendingRest = s.pendingRest.filter(id => !covers.includes(id))
      if (onPhase?.('AFTER_PLANNING')) { settleRoster(s, rates, retryDepth + 1, onPhase); return }
      continue
    }
    if (s.config.mowerPolicy && s.events.some(e => e.time === s.time && (e.type === 'shift-on' || e.type === 'exhaust-support') && e.operators.some(id => ps.some(p => p.primary === id)))) continue
    if (resting || !ps.some(p => (s.morale[p.primary] ?? 0) <= shiftThreshold(p,s,rates) + MORALE_EPSILON && (p.exhaustRequired || !s.config.mowerPolicy || upper(p)-(s.morale[p.primary] ?? 0) >= 2-MORALE_EPSILON))) continue
    const ordinaryBatch = Boolean(s.config.mowerPolicy && !ps.some(p => p.exhaustRequired))
    if (ordinaryBatch) {
      if (!ordinaryPlanning) { ordinaryPlanning=supportProjection(s); initialResting=activeResting(s).length }
      const primaryResting=activeResting(ordinaryPlanning)
      const highCount=primaryResting.filter(id=>s.config.positions.some(p=>p.primary===id && p.restingPriority !== 'low')).length
      if (recoveryBeds.length && initialResting+plannedCoverCount >= idealResting && highCount >= new Set(recoveryBeds.map(b=>b.roomId)).size) highDone=true
      if (highDone) continue
    }
    // alpha selects all replacements first, then admits low-priority beds first.
    const shiftMembers = s.config.mowerPolicy && ps[0]?.group
      ? s.config.positions.filter(p => !p.dormitory && p.group === ps[0]!.group)
      : [...ps]
    if (s.config.mowerPolicy) shiftMembers.sort((a,b) => {
      const auxiliary = (p: RuntimePosition) => s.config.positions.some(q => s.occupants[q.id] === p.primary && (q.roomId === 'factory' || q.roomId === 'train'))
      return Number(!s.config.fiammetta?.orderedTargets.includes(a.primary)) - Number(!s.config.fiammetta?.orderedTargets.includes(b.primary))
        || Number(auxiliary(a))-Number(auxiliary(b))
        || (s.morale[a.primary]!-(a.lowerLimit ?? 0))-(s.morale[b.primary]!-(b.lowerLimit ?? 0))
    })
    const planningState = ordinaryBatch && ordinaryPlanning ? ordinaryPlanning : s
    const plannedSwaps = planRestSwaps(planningState,shiftMembers)
    const completeGroup = plannedSwaps !== undefined
    if (!completeGroup && s.config.mowerPolicy && ps.some(p => p.exhaustRequired) && retryDepth < s.config.positions.length) {
      const support = planExhaustSupport(s,shiftMembers)
      if (support) {
        if (onPhase?.('BEFORE_WORK')) { settleRoster(s,rates,retryDepth+1,onPhase); return }
        applyExhaustSupport(s,support)
        settleRoster(s,rates,retryDepth+1,onPhase); return
      }
    }
    const {swaps,beds,reserved} = plannedSwaps ?? {swaps:[],beds:{...s.bedOccupants},reserved:new Set<string>()}
    if (!completeGroup) { rosterDiagnostic(s, 'group-blocked', `${key}: insufficient available candidates or beds; original occupants retained`); continue }
    if (ordinaryBatch && ordinaryPlanning) {
      ordinaryPlanning.bedOccupants={...beds}
      plannedCoverCount+=reserved.size
      reserved.forEach(id=>plannedCovers.add(id))
      for(const {p,candidate} of swaps) ordinaryPlanning.occupants[p.id]=candidate
      ordinaryGroups.push({members:shiftMembers,swaps})
      continue
    }
    if (onPhase?.('BEFORE_WORK')) { settleRoster(s, rates, retryDepth + 1, onPhase); return }
    for (const { p, candidate } of swaps) {
      for (const [bed,id] of Object.entries(s.bedOccupants)) if (id === candidate) delete s.bedOccupants[bed]
      s.occupants[p.id] = candidate
    }
    // Selected candidates leave their original beds only when work rooms move.
    if (s.config.mowerPolicy) for (const [bed,id] of Object.entries(beds)) if (reserved.has(id) || ordinaryBatch && plannedCovers.has(id)) delete beds[bed]
    s.pendingRest = [...new Set([...(s.pendingRest ?? []), ...ps.map(p => p.primary)])]
    s.standbyWorkaholics = [...new Set([...(s.standbyWorkaholics ?? []), ...swaps.filter(x => x.p.permanent && s.config.mowerPolicy).map(x => x.p.primary)])]
    s.events.push({ time: s.time, type: 'shift-off', operators: shiftMembers.map(p => p.primary), beds: swaps.flatMap(x => x.bed ? [x.bed] : []) })
    if (onPhase?.('BEFORE_DORM')) { settleRoster(s, rates, retryDepth + 1, onPhase); return }
    for (const bed of Object.keys(s.bedOccupants)) parkBedTakeover(s,bed,beds[bed])
    s.bedOccupants = beds
    s.completedRest = [...new Set([...(s.completedRest ?? []), ...swaps.filter(x => !x.bed && !x.p.permanent).map(x => x.p.primary)])]
    s.pendingRest = s.pendingRest.filter(id => !ps.some(p => p.primary === id))
    if (onPhase?.('BEFORE_PLANNING')) { settleRoster(s, rates, retryDepth + 1, onPhase); return }
    // Exhaustion is a separate queued task; replan ordinary groups from its real result.
    if(s.config.mowerPolicy && ps.some(p=>p.exhaustRequired)) { settleRoster(s,rates,retryDepth+1,onPhase); return }
  }
  if(ordinaryGroups.length && ordinaryPlanning) {
    if(onPhase?.('BEFORE_WORK')) { settleRoster(s,rates,retryDepth+1,onPhase); return }
    const swaps=ordinaryGroups.flatMap(group=>group.swaps),members=ordinaryGroups.flatMap(group=>group.members)
    for(const {p,candidate} of swaps) {
      for(const [bed,id] of Object.entries(s.bedOccupants))if(id===candidate)delete s.bedOccupants[bed]
      s.occupants[p.id]=candidate
    }
    s.pendingRest=[...new Set([...(s.pendingRest??[]),...members.filter(p=>!p.permanent).map(p=>p.primary)])]
    s.standbyWorkaholics=[...new Set([...(s.standbyWorkaholics??[]),...swaps.filter(x=>x.p.permanent).map(x=>x.p.primary)])]
    for(const group of ordinaryGroups)s.events.push({time:s.time,type:'shift-off',operators:group.members.map(p=>p.primary),beds:group.swaps.flatMap(x=>x.bed?[x.bed]:[])})
    if(onPhase?.('BEFORE_DORM')) { settleRoster(s,rates,retryDepth+1,onPhase); return }
    const beds={...ordinaryPlanning.bedOccupants}
    for(const [bed,id] of Object.entries(beds))if(plannedCovers.has(id))delete beds[bed]
    for(const bed of Object.keys(s.bedOccupants))parkBedTakeover(s,bed,beds[bed])
    s.bedOccupants=beds
    s.completedRest=[...new Set([...(s.completedRest??[]),...swaps.filter(x=>!x.bed&&!x.p.permanent).map(x=>x.p.primary)])]
    s.pendingRest=s.pendingRest.filter(id=>!members.some(p=>p.primary===id))
    if(onPhase?.('BEFORE_PLANNING')) { settleRoster(s,rates,retryDepth+1,onPhase); return }
  }
  releaseLimitedRest(s)
  releaseRecoveredSubstitutes(s)
  if (s.config.mowerPolicy) {
    fillIdleBeds(s)
    reorderMowerBeds(s)
    refreshRecoveryCompletion(s)
    if (rates) updateMowerReturnDeadlines(s, rates)
  }
}

type RestSwap = {p:RuntimePosition;candidate:string;bed?:string}
/** The same greedy replacement and atomic bed trial is used by normal and emergency planning. */
function planRestSwaps(s:RuntimeState, members:RuntimePosition[]) {
  const reserved=new Set<string>(),beds={...s.bedOccupants},swaps:RestSwap[]=[]
  for(const p of members){
    const existingBed=s.config.beds.find(b=>beds[b.id]===p.primary),current=s.occupants[p.id]
    const candidate=existingBed&&current&&p.candidates.includes(current)&&!reserved.has(current)?current:nextCandidate(p,s,reserved,beds)
    const allowEmpty=p.candidates.length===0&&(p.exhaustRequired||!p.group)
    if(!candidate&&!allowEmpty)return undefined
    if(candidate)reserved.add(candidate)
    swaps.push({p,candidate:candidate??''})
  }
  const admissions=s.config.mowerPolicy?[...swaps].sort((a,b)=>Number(a.p.restingPriority!=='low')-Number(b.p.restingPriority!=='low')):swaps
  for(const swap of admissions){
    const p=swap.p,cap=restMoodLimit(s,p.primary)
    if((p.permanent&&s.config.mowerPolicy)||cap!==undefined&&(s.morale[p.primary]??0)>=cap-MORALE_EPSILON)continue
    const bed=s.config.beds.find(b=>(!s.config.mowerPolicy||b.managedRecovery!==false)&&beds[b.id]===p.primary)??freeBed(s,p,beds)
    if(!bed)return undefined
    beds[bed.id]=p.primary;swap.bed=bed.id
  }
  return {swaps,beds,reserved}
}
function supportProjection(s:RuntimeState):RuntimeState {
  return {...s,occupants:{...s.occupants},bedOccupants:{...s.bedOccupants},returnDeadlines:{...s.returnDeadlines},pendingRest:[...(s.pendingRest??[])],completedRest:[...(s.completedRest??[])],standbyWorkaholics:[...(s.standbyWorkaholics??[])],recoveryCompletedAt:{...s.recoveryCompletedAt},recoveryCompletionTargets:{...s.recoveryCompletionTargets}}
}
function supportAssign(s:RuntimeState,p:RuntimePosition,id:string):void {
  for(const [slot,other] of Object.entries(s.occupants))if(other===id)delete s.occupants[slot]
  for(const [bed,other] of Object.entries(s.bedOccupants))if(other===id)delete s.bedOccupants[bed]
  s.occupants[p.id]=id
}
/** Fixed alpha exhaust_replacement.py: free occupied covers first, then try actual bed admission. */
function planExhaustSupport(s:RuntimeState, members:RuntimePosition[]):RuntimeState|undefined {
  const required=new Set(members.map(p=>p.primary)),coverNames=new Set(members.flatMap(p=>p.candidates)),selected=new Set<string>()
  let trial=supportProjection(s)
  const eligible=(state:RuntimeState,id:string)=>!required.has(id)&&!selected.has(id)&&!state.config.excludedCandidates?.includes(id)&&!state.config.positions.some(p=>p.primary===id)
  const available=(state:RuntimeState,id:string)=>eligible(state,id)&&(!Object.values(state.occupants).includes(id)||Object.values(state.bedOccupants).includes(id))
  const recall=(state:RuntimeState,owner:RuntimePosition):RuntimeState|undefined=>{
    const group=state.config.positions.filter(p=>owner.group?p.group===owner.group:p.id===owner.id)
    if(group.some(p=>required.has(p.primary)))return undefined
    const exhaustionFull=group.some(p=>p.exhaustRequired)&&group.some(p=>p.restToFull)
    if(group.some(p=>Object.values(state.bedOccupants).includes(p.primary)&&(p.exhaustRequired&&p.restToFull||exhaustionFull)))return undefined
    if(group.some(p=>Object.entries(state.occupants).some(([slot,id])=>id===p.primary&&slot!==p.id&&!state.config.positions.find(q=>q.id===slot)?.dormitory)))return undefined
    const next=supportProjection(state)
    // No invented minimum recovery mood: alpha only protects exhaustion plus full-rest.
    for(const p of group)supportAssign(next,p,p.primary)
    const recalled=new Set(group.map(p=>p.primary))
    next.pendingRest=next.pendingRest?.filter(id=>!recalled.has(id));next.completedRest=next.completedRest?.filter(id=>!recalled.has(id));next.standbyWorkaholics=next.standbyWorkaholics?.filter(id=>!recalled.has(id))
    delete next.returnDeadlines?.[owner.group?'group:'+owner.group:'slot:'+owner.id]
    return next
  }
  for(const p of members){
    const free=p.candidates.find(id=>available(trial,id))
    if(free){selected.add(free);continue}
    if(!p.candidates.length&&(p.exhaustRequired||!p.group))continue
    const occupied=p.candidates.filter(id=>eligible(trial,id)).flatMap(id=>{
      const owner=trial.config.positions.find(q=>!q.dormitory&&q.roomId!=='train'&&trial.occupants[q.id]===id&&q.primary!==id&&q.candidates.includes(id)&&!required.has(q.primary)&&!Object.values(trial.occupants).includes(q.primary))
      return owner?[{id,owner}]:[]
    })
    let resolved=false
    for(const {id,owner} of occupied){
      const alternate=owner.candidates.find(other=>!coverNames.has(other)&&available(trial,other))
      if(!alternate)continue
      supportAssign(trial,owner,alternate);selected.add(id);resolved=true;break
    }
    if(!resolved)for(const {id,owner} of occupied){
      const next=recall(trial,owner)
      if(!next||!available(next,id))continue
      trial=next;selected.add(id);resolved=true;break
    }
    if(!resolved)return undefined
  }
  selected.clear()
  for(const p of members){const cover=p.candidates.find(id=>available(trial,id));if(cover)selected.add(cover);else if(p.candidates.length||!(p.exhaustRequired||!p.group))return undefined}
  if(planRestSwaps(trial,members))return trial
  const beds=trial.config.beds.filter(b=>b.managedRecovery!==false).sort((a,b)=>(trial.morale[trial.bedOccupants[b.id]!]??25)-(trial.morale[trial.bedOccupants[a.id]!]??25))
  for(const bed of beds){
    const id=trial.bedOccupants[bed.id],owner=trial.config.positions.find(p=>p.primary===id)
    if(!id||!owner||!(id in trial.morale)||(trial.recoveryCompletedAt?.[id]??Infinity)<trial.time-MORALE_EPSILON)continue
    const next=recall(trial,owner)
    if(!next||JSON.stringify(next.occupants)===JSON.stringify(trial.occupants))continue
    trial=next
    if(planRestSwaps(trial,members))return trial
  }
  return undefined
}
function applyExhaustSupport(s:RuntimeState,trial:RuntimeState):void {
  const changed=s.config.positions.filter(p=>s.occupants[p.id]!==trial.occupants[p.id])
  Object.assign(s,{occupants:trial.occupants,bedOccupants:trial.bedOccupants,returnDeadlines:trial.returnDeadlines,pendingRest:trial.pendingRest,completedRest:trial.completedRest,standbyWorkaholics:trial.standbyWorkaholics})
  for(const id of Object.keys(s.recoveryCompletedAt??{}))if(!Object.values(s.bedOccupants).includes(id)){delete s.recoveryCompletedAt![id];delete s.recoveryCompletionTargets?.[id]}
  s.events.push({time:s.time,type:'exhaust-support',operators:changed.map(p=>s.occupants[p.id]!).filter(Boolean)})
  s.timingSignature=undefined
}
function fillIdleBeds(s: RuntimeState): void {
  const pool = [...new Set([...s.config.positions.flatMap(p=>p.candidates),...(s.config.runOrderPolicies?.flatMap(p=>p.orderedOperatorIds) ?? []),...(s.config.idleOperators ?? []),...(s.config.availableIdleOperators ?? [])])]
  const available = pool.filter(id => !s.config.freeBlacklist?.includes(id) && !s.config.positions.some(p => p.primary === id) && !Object.values(s.occupants).includes(id) && !Object.values(s.bedOccupants).includes(id) && (s.morale[id] ?? 24) < (restMoodLimit(s,id) ?? Infinity)-MORALE_EPSILON && (!s.config.mowerPolicy?.freeRoom || (s.morale[id] ?? 24) < 24 - MORALE_EPSILON)).sort((a,b) => (s.morale[a] ?? 24) - (s.morale[b] ?? 24))
  for (const bed of s.config.beds) if (!s.bedOccupants[bed.id] && available.length) {const name=available.shift()!;s.morale[name]??=mowerInitialMorale(name,s.config.initialMorale?.[name]??24);s.bedOccupants[bed.id]=name}
}
/** Mower try_reorder: explicit list, then high/normal primaries, then substitutes. */
function reorderMowerBeds(s: RuntimeState): void {
  const policy = s.config.mowerPolicy!
  const beds = s.config.beds.filter(b => b.managedRecovery !== false).sort((a,b) => Number(b.vip)-Number(a.vip))
  const rank = (id: string) => {
    const explicit = policy.opeRestingPriority.indexOf(id)
    if (explicit >= 0) return explicit
    const p = s.config.positions.find(p => p.primary === id)
    return policy.opeRestingPriority.length + (p ? p.restingPriority === 'low' ? 1 : 0 : 2)
  }
  const occupants = beds.map(b => s.bedOccupants[b.id]).filter((id): id is string => Boolean(id)).sort((a,b) => rank(a)-rank(b))
  const managed = new Set(beds.map(b => b.id))
  s.bedOccupants = {...Object.fromEntries(Object.entries(s.bedOccupants).filter(([bed]) => !managed.has(bed))), ...Object.fromEntries(occupants.map((id,i) => [beds[i]!.id,id]))}
}
function updateMowerReturnDeadlines(s: RuntimeState, rates: RuntimeRates): void {
  const signature = JSON.stringify([s.occupants,s.bedOccupants,Object.keys(s.morale).map(id => moraleDerivative(s,id,rates))])
  if (signature === s.timingSignature) return
  s.timingSignature = signature
  const workers = s.config.positions.filter(p => !p.dormitory && s.occupants[p.id] === p.primary)
  const rescue = mowerRescueDelay(workers.map(p => ({ morale:s.morale[p.primary]!, lower:p.lowerLimit ?? 0, rate:rates.workRate(p.primary,p.roomId,s), ignore:p.permanent || p.exhaustRequired || p.roomId === 'factory' || p.roomId === 'train' })))
  const grouped = new Map<string, RuntimePosition[]>()
  // Stable bed order reproduces grouped_dorms insertion order.
  for (const bed of s.config.beds.filter(b => b.managedRecovery !== false).sort((a,b) => Number(b.vip)-Number(a.vip))) {
    const id = s.bedOccupants[bed.id]
    const p = s.config.positions.find(p => !p.dormitory && !p.permanent && p.primary === id && s.occupants[p.id] !== id)
    if (p) { const key=p.group ? `group:${p.group}` : `slot:${p.id}`; grouped.set(key,[...(grouped.get(key) ?? []),p]) }
  }
  const deadlines: Record<string,number> = {}
  for (const [key,bedMembers] of grouped) {
    const firstMember = bedMembers[0]!
    const ps = s.config.positions.filter(p => !p.dormitory && !p.permanent && (firstMember.group ? p.group === firstMember.group : p.id === firstMember.id))
    // Partial groups can occur after explicit backup tasks. Replan them normally;
    // a return deadline is valid only when the entire group is off its main posts.
    if (ps.some(p => s.occupants[p.id] === p.primary)) continue
    // scheduler_task.py retains grouped_dorms order when selecting high_dorms.
    // Main-plan order changes which member controls the mismatch deadline.
    const high=bedMembers.filter(p => p.restingPriority !== 'low'); const members=high.length ? high : bedMembers
    const values=members.map(p => { const rate=moraleDerivative(s,p.primary,rates); return {hours:rate>0 ? Math.max(0,(upper(p)-s.morale[p.primary]!)/rate) : Infinity,full:p.restToFull} })
    let delay=mowerReturnDelay(values,s.config.mowerPolicy!.powerPlantCount,rescue)
    if (s.config.mowerPolicy!.taskBuffers) {
      const first=members[0]!
      const full=members.some(p => p.restToFull)
      const mismatch=members.length>1 && values.some(v => values[0]!.hours-v.hours > (s.config.mowerPolicy!.powerPlantCount === 2 ? 1.5 : 1))
      if (first.group && (full || mismatch) && !first.exhaustRequired) delay -= .4*members.length/60
      // Ordinary returns include the 8-minute lead; full+exhaust keeps its exact recovery time.
      if (!full || !members.some(p => p.exhaustRequired)) delay -= 8/60
    }
    // A numerical empty-cycle guard is separate from the alpha policy; queued returns
    // must not be delayed to lower+2 or until explicit full-rest members reach 24.
    const usefulRecoveryDelay = Math.max(0, ...ps.map(p => {
      const deficit = minimumNumericalReturnMorale(p, s, rates) - (s.morale[p.primary] ?? 0)
      if (deficit <= MORALE_EPSILON) return 0
      const rate = moraleDerivative(s, p.primary, rates)
      return rate > 0 ? deficit / rate : Infinity
    }))
    deadlines[key]=s.time+Math.max(0,delay,usefulRecoveryDelay)
  }
  s.returnDeadlines=deadlines
}

function placedMoraleDerivative(s:RuntimeState,id:string,rates:RuntimeRates,p?:RuntimePosition,bed?:RuntimeBed,snapshot?:ReturnType<NonNullable<RuntimeRates['snapshotRates']>>):number {
  if (id === s.config.fiammetta?.operatorId && (p?.dormitory || bed)) return 2
  const recovery=(room:string)=>snapshot?(snapshot.recovery[id]??0):rates.recoveryRate(id,room,s)
  const work=(room:string)=>snapshot?(snapshot.work[id]??0):rates.workRate(id,room,s)
  const rate = bed ? recovery(bed.roomId) : p ? (p.dormitory ? recovery(p.roomId) : -work(p.roomId)) : 0
  if (!Number.isFinite(rate)) throw new Error(`Non-finite morale rate: ${id}`)
  return rate
}
export function moraleDerivative(s: RuntimeState, id: string, rates: RuntimeRates): number {
  const p = s.config.positions.find(p => s.occupants[p.id] === id)
  const bed = s.config.beds.find(b => s.bedOccupants[b.id] === id)
  return placedMoraleDerivative(s,id,rates,p,bed)
}
/** Index the current physical roster once for a whole rate sweep. */
function moraleRateSnapshot(s:RuntimeState,rates:RuntimeRates):{derivatives:Record<string,number>;primary:Map<string,RuntimePosition>} {
 const occupied=new Map<string,RuntimePosition>(),beds=new Map<string,RuntimeBed>(),primary=new Map<string,RuntimePosition>()
 for(const p of s.config.positions){
  const id=s.occupants[p.id]
  if(id&&!occupied.has(id))occupied.set(id,p)
  if(!primary.has(p.primary))primary.set(p.primary,p)
 }
 for(const bed of s.config.beds){const id=s.bedOccupants[bed.id];if(id&&!beds.has(id))beds.set(id,bed)}
 const rateSnapshot=rates.snapshotRates?.()
 const derivatives:Record<string,number>={}
 for(const id of Object.keys(s.morale))derivatives[id]=placedMoraleDerivative(s,id,rates,occupied.get(id),beds.get(id),rateSnapshot)
 return {derivatives,primary}
}
export function currentMoraleDerivatives(s:RuntimeState,rates:RuntimeRates):Record<string,number>{return moraleRateSnapshot(s,rates).derivatives}
/** Planning events only. Skill boundaries and a substitute reaching 24 do not run Mower's planner. */
export function nextRosterActionHours(s: RuntimeState, rates: RuntimeRates): number {
  if(s.config.mowerSourcePlan)return nextMowerSourceActionHours(s,rates)
  if (!s.config.mowerPolicy) return nextRosterEventHours(s,rates)
  updateMowerReturnDeadlines(s,rates)
  const deadlines=[s.nextPlanningTime ?? Infinity,s.nextFiammettaCheckTime ?? Infinity,...Object.values(s.returnDeadlines ?? {})]
  if (deadlines.some(t=>Number.isFinite(t) && t<=s.time+MORALE_EPSILON)) return 0
  let next=Math.min(Infinity,...deadlines.map(t=>t-s.time))
  for (const id of s.config.beds.filter(b => b.managedRecovery !== false).map(b => s.bedOccupants[b.id]).filter((id): id is string => Boolean(id))) {
    const target = restMoodLimit(s,id)
    if (target === undefined) continue
    if ((s.morale[id] ?? 0) >= target - MORALE_EPSILON) return 0
    const rate = moraleDerivative(s,id,rates)
    if (rate > 0) next = Math.min(next,(target-(s.morale[id] ?? 0))/rate)
  }
  if (s.config.mowerPolicy.freeRoom) for (const id of s.config.beds.filter(b => b.managedRecovery !== false).map(b => s.bedOccupants[b.id]).filter((id): id is string => Boolean(id))) {
    if (s.backupBedOccupants?.has(id) || s.config.positions.some(p => p.primary === id && s.occupants[p.id] !== id)) continue
    const morale = s.morale[id] ?? 0
    if (morale >= 24 - MORALE_EPSILON) return 0
    const rate = moraleDerivative(s,id,rates)
    if (rate > 0) next = Math.min(next,(24-morale)/rate)
  }
  for (const p of s.config.positions) {
    if (p.dormitory || p.permanent || s.occupants[p.id]!==p.primary) continue
    const rate=moraleDerivative(s,p.primary,rates)
    if (rate>=0) continue
    const t=(shiftThreshold(p,s,rates)-s.morale[p.primary]!)/rate
    if (t>MORALE_EPSILON) next=Math.min(next,t)
  }
  const fia=s.config.fiammetta?.operatorId
  if (fia) { const rate=moraleDerivative(s,fia,rates);const t=(24-(s.morale[fia] ?? 24))/rate;if (rate>0 && t>MORALE_EPSILON) next=Math.min(next,t) }
  return next
}
export function nextRosterEventHours(s: RuntimeState, rates: RuntimeRates, includePlanning = true, preparedDerivatives?:Readonly<Record<string,number>>): number {
  if (includePlanning && s.config.mowerPolicy&&!s.config.mowerSourcePlan) updateMowerReturnDeadlines(s,rates)
  let next = includePlanning ? Math.min(s.config.mowerPolicy ? nextRosterActionHours(s,rates) : Infinity,...[s.nextPlanningTime ?? Infinity,s.nextFiammettaCheckTime ?? Infinity,...Object.values(s.returnDeadlines ?? {})].map(t => t-s.time).filter(t => t > MORALE_EPSILON)) : Infinity
  const primary=new Map<string,RuntimePosition>()
  if(preparedDerivatives)for(const p of s.config.positions)if(!primary.has(p.primary))primary.set(p.primary,p)
  const snapshot=preparedDerivatives?{derivatives:preparedDerivatives,primary}:moraleRateSnapshot(s,rates)
  for (const [id, m] of Object.entries(s.morale)) {
    const rate = snapshot.derivatives[id]!
    if (!rate) continue
    const p = snapshot.primary.get(id)
    const thresholds = [0, 24, ...(p ? [shiftThreshold(p,s,rates), upper(p)] : []), ...(rates.thresholds?.(id, s) ?? [])]
    if (s.config.fiammetta?.orderedTargets.includes(id)) thresholds.push(s.config.fiammetta.threshold ?? 21.6)
    for (const threshold of thresholds) {
      const t = (threshold - m) / rate
      if (t > MORALE_EPSILON && t < next) next = t
    }
  }
  return next
}
export function advanceRoster(s: RuntimeState, hours: number, rates: RuntimeRates, preparedDerivatives?:Readonly<Record<string,number>>): void {
  if (!Number.isFinite(hours) || hours <= 0) throw new Error('Roster advance must be finite and positive')
  const derivatives = preparedDerivatives??moraleRateSnapshot(s,rates).derivatives
  if (s.config.mowerPolicy) for (const id of s.config.beds.filter(b => b.managedRecovery !== false).map(b => s.bedOccupants[b.id]).filter((id): id is string => Boolean(id))) {
    const target = restTarget(s,id), before = s.morale[id] ?? 0, rate = derivatives[id] ?? 0
    const targets = s.recoveryCompletionTargets ??= {}
    if (targets[id] !== undefined && targets[id] !== target && s.recoveryCompletedAt) delete s.recoveryCompletedAt[id]
    targets[id] = target
    if (before >= target-MORALE_EPSILON) (s.recoveryCompletedAt ??= {})[id] ??= s.time
    else if (rate > 0 && before+rate*hours >= target-MORALE_EPSILON) (s.recoveryCompletedAt ??= {})[id] = s.time+Math.max(0,(target-before)/rate)
  }
  for (const id of Object.keys(s.morale)) {
    const value = Math.max(0, Math.min(24, s.morale[id]! + derivatives[id]! * hours))
    // Canonical physical endpoints prevent roundoff from changing full-rest pools
    // and same-time return ordering. Do not snap internal skill thresholds.
    s.morale[id] = value <= MORALE_EPSILON ? 0 : value >= 24 - MORALE_EPSILON ? 24 : value
  }
  s.time += hours
}
