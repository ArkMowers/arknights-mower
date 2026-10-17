import {hasObservedFullMood} from './mowerOperatorState'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,type MowerTask} from './mowerTaskQueue'

/** Observed returns and completed recovery release this round's recall dependency. */
export function reconcileMowerUrgentRecovery(data:MowerSchedulingData):void {
 for(const name of Object.keys(data.urgentRecoverySupporters)){
  const op=data.operators[name]
  if(!op||!op.moodIsPrediction&&(hasObservedFullMood(op)||!op.currentRoom&&data.restMoodComplete(name)||op.currentRoom===op.room&&op.currentIndex===op.index))delete data.urgentRecoverySupporters[name]
 }
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
 if(!task.exhaustSupport||task.ordinaryCoordination||!task.coordinationRequestNames.length)return
 const supporters=Object.values(data.operators).filter(op=>(data.isGroupShiftAnchor(op)||op.independentRest&&!data.canStandby(op))&&!op.room.startsWith('dorm')&&positions[op.name]?.[0].startsWith('dorm')&&op.currentRoom===op.room&&op.currentIndex===op.index).map(op=>op.name)
 if(!supporters.length)return
 const owner=pending.find(request=>request.type===T.EXHAUST_OFF&&!request.ordinaryCoordination&&request.metadata.split(',').some(name=>task.coordinationRequestNames.includes(name)))
 if(!owner)return
 const explicit=new Set(owner.metadata.split(','))
 owner.urgentRecoveryRequestNames=task.coordinationRequestNames.filter(name=>{const op=data.operators[name];return !!op&&(data.isGroupShiftAnchor(op)||op.independentRest&&explicit.has(name))})
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
