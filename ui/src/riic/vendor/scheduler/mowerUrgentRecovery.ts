import {hasObservedFullMood} from './mowerOperatorState'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,type MowerTask} from './mowerTaskQueue'

function requestOrigins(request:MowerTask):string[] {
 return request.coordinationRequestNames.length ? request.coordinationRequestNames : request.type===T.EXHAUST_OFF ? request.metadata.split(',') : request.urgentRecoveryRequestNames
}

/** A prepared departure retains the recovery request that released its covers. */
export function mowerSupportRequestMatches(request:MowerTask,support:MowerTask):boolean {
 if(request===support||request.ordinaryCoordination!==support.ordinaryCoordination)return false
 const origins=requestOrigins(request)
 return request.type===T.EXHAUST_OFF&&origins.some(name=>support.coordinationRequestNames.includes(name))
  ||request.type===T.SHIFT_OFF&&origins.length>0&&origins.every(name=>support.coordinationRequestNames.includes(name))
}

function sameNames(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every(name => right.includes(name))
}

/** Only the originating departure may reuse a support's freed covers and beds. */
export function mowerReservationOwners(current: MowerTask | undefined, pending: readonly MowerTask[]): Set<MowerTask> {
  if (!current) return new Set()
  const own = current.urgentRecoveryRequestNames
  if (!own.length && (current.ordinaryCoordination || !current.exhaustSupport)) return new Set()
  const origins = requestOrigins(current).filter(Boolean)
  if (!origins.length) return new Set()
  const candidates = pending.filter(task => task !== current && task.urgentRecoveryRequestNames.length && task.ordinaryCoordination === current.ordinaryCoordination)
  if (own.length) {
    const affected = candidates.filter(task => sameNames(task.urgentRecoveryRequestNames, own))
    if (current.type === T.SHIFT_OFF && !current.coordinationRequestNames.length && (current.urgentRecoveryReservedNames.length || current.urgentRecoveryReservedSlots.length)) {
      const copies = affected.filter(task => sameNames(task.urgentRecoveryReservedNames, current.urgentRecoveryReservedNames) && sameNames(task.urgentRecoveryReservedSlots, current.urgentRecoveryReservedSlots))
      return new Set(copies.length === 1 ? copies : [])
    }
    return new Set(affected.filter(task => sameNames(requestOrigins(task), origins)))
  }
  const parents = candidates.filter(task => (task.type === T.EXHAUST_OFF || task.type === T.SHIFT_OFF) && sameNames(requestOrigins(task), origins))
  return new Set(parents.length === 1 ? parents : [])
}

/** Observed returns and completed recovery release this round's recall dependency. */
export function mowerActiveUrgentRecoveryNames(data:MowerSchedulingData):Set<string> {
 return new Set(Object.keys(data.urgentRecoverySupporters).filter(name=>{
  const op=data.operators[name]
  return !!op&&(op.moodIsPrediction||!(hasObservedFullMood(op)||!op.currentRoom&&data.restMoodComplete(name)||op.currentRoom===op.room&&op.currentIndex===op.index))
 }))
}
export function reconcileMowerUrgentRecovery(data:MowerSchedulingData):void {
 const active=mowerActiveUrgentRecoveryNames(data)
 for(const name of Object.keys(data.urgentRecoverySupporters))if(!active.has(name))delete data.urgentRecoverySupporters[name]
}
export function mowerUrgentRecallBlocked(data:MowerSchedulingData,candidates:readonly string[],pending:ReadonlySet<string>=new Set()):boolean {
 const supporters=new Set(Object.values(data.urgentRecoverySupporters).flat())
 return candidates.some(name=>supporters.has(name)||pending.has(name))
}
export function mowerUrgentPendingSupporters(tasks:readonly MowerTask[]):Set<string>{
 return new Set(tasks.flatMap(task=>task.urgentRecoverySupportNames))
}
/** Reserve resources only after a real support return, until its requester enters a dorm. */
export function recordMowerUrgentSupport(data:MowerSchedulingData,task:MowerTask,pending:readonly MowerTask[],positions:Record<string,[string,number]>):void {
 if(!task.exhaustSupport||!task.coordinationRequestNames.length)return
 const supporters=Object.values(data.operators).filter(op=>(data.isGroupShiftAnchor(op)||op.independentRest&&!data.canStandby(op))&&!op.room.startsWith('dorm')&&positions[op.name]?.[0].startsWith('dorm')&&op.currentRoom===op.room&&op.currentIndex===op.index).map(op=>op.name)
 if(!supporters.length)return
 const owner=pending.find(request=>mowerSupportRequestMatches(request,task))??(task.ordinaryCoordination?task:undefined)
 if(!owner)return
 const explicit=new Set([...owner.metadata.split(','),...owner.urgentRecoveryRequestNames,...(owner===task?task.coordinationRequestNames:[])])
 const requestGroups=new Set(data.shiftRequestGroups(task.coordinationRequestNames))
 const requests=[...new Set(task.coordinationRequestNames.flatMap(name=>{const op=data.operators[name];return op?.group?data.shiftGroupMembers(op.group):op?[name]:[]}))]
 owner.urgentRecoveryRequestNames=requests.filter(name=>{const op=data.operators[name];return !!op&&(data.isGroupShiftAnchor(op)&&(!op.group||requestGroups.has(op.group))||op.independentRest&&explicit.has(name))})
 task.urgentRecoveryRequestNames=[...owner.urgentRecoveryRequestNames]
 owner.urgentRecoverySupportNames=[...new Set([...owner.urgentRecoverySupportNames,...supporters])]
 owner.urgentRecoveryReservedNames=[...new Set([...owner.urgentRecoveryReservedNames,...Object.values(data.operators).filter(op=>{
  const previous=positions[op.name]
  return previous&&!previous[0].startsWith('dorm')&&supporters.some(name=>{const worker=data.operators[name]!;return previous[0]===worker.room&&previous[1]===worker.index})&&(!op.currentRoom||op.isResting())
 }).map(op=>op.name)])]
 owner.urgentRecoveryReservedSlots=[...new Set([...owner.urgentRecoveryReservedSlots,...supporters.map(name=>positions[name]!.join('\0'))])]
}
/** Failed previews never create recovery ownership; only confirmed admissions do. */
export function recordMowerUrgentRecovery(data:MowerSchedulingData,task:MowerTask,pending:readonly MowerTask[]):void {
 for(const owner of [task,...pending]){
  if(!owner.urgentRecoverySupportNames.length)continue
  for(const name of owner.urgentRecoveryRequestNames){
   const op=data.operators[name]
   if(op&&!op.moodIsPrediction&&op.isResting()&&(data.isGroupShiftAnchor(op)||op.independentRest)&&!op.room.startsWith('dorm'))data.urgentRecoverySupporters[name]=[...owner.urgentRecoverySupportNames]
  }
 }
}
export function inheritMowerUrgentRecovery(target:MowerTask,source:MowerTask):void {
 target.urgentRecoveryRequestNames=[...source.urgentRecoveryRequestNames]
 target.urgentRecoverySupportNames=[...source.urgentRecoverySupportNames]
 target.urgentRecoveryReservedNames=[...source.urgentRecoveryReservedNames]
 target.urgentRecoveryReservedSlots=[...source.urgentRecoveryReservedSlots]
}
