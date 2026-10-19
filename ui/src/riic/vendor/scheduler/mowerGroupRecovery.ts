import {mowerDormCandidateMood,mowerSchedulingMoodObservation} from './mowerAlphaCandidates'
import {type MowerOperatorState} from './mowerOperatorState'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {toMowerMicros,roundMowerMicros,MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {mowerArrangementGroupTransitions} from './mowerSharedGroups'
import {alphaDormMinutes} from './mowerAlphaTaskProtection'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'

export function mowerRecoveryMoodComplete(data:MowerSchedulingData,op:MowerOperatorState|undefined):boolean {
 const mood=op?mowerDormCandidateMood(data,op.name):undefined
 return !!op&&mood!==undefined&&mood>=op.upperLimit
}
export function mowerObservedRecoveryDeadline(data:MowerSchedulingData,op:MowerOperatorState):number|undefined {
 const bed=data.getDormByName(op.name)?.[1]
 if(bed)return bed.timeMicros
 const observed=op.dormRecoveryObservation
 if(!observed||op.moodIsPrediction||observed[0]!==op.currentRoom||observed[1]!==op.currentIndex||observed[2]!==op.timeStampMicros)return undefined
 return op.mood<24?observed[2]+roundMowerMicros((op.upperLimit-op.mood)*(observed[3]-observed[2])/(24-op.mood)):observed[3]
}
/** Work primaries participating in group recovery, excluding standby and personal rest. */
export function mowerGroupRecoveryWorkers(data:MowerSchedulingData,group:string):MowerOperatorState[]{
 return data.shiftGroupMembers(group).map(name=>data.operators[name]!).filter(op=>op.isHigh()&&!op.room.startsWith('dorm')&&!op.workaholic&&!op.independentRest&&!data.canStandby(op)&&(op.isResting()||!op.currentRoom))
}
function completedAt(data:MowerSchedulingData,op:MowerOperatorState):number|undefined {
 if(mowerRecoveryMoodComplete(data,op)||!op.currentRoom&&!op.moodIsPrediction&&data.restMoodComplete(op.name))return data.nowMicros
 return mowerObservedRecoveryDeadline(data,op)
}
/** The extra-wait cap limits only the gap wait; explicit full recovery remains binding. */
export function mowerGroupRecoveryDeadline(data:MowerSchedulingData,group:string):{requiredNames:string[];timeMicros:number|undefined}{
 const workers=mowerGroupRecoveryWorkers(data,group),gapWorkers=workers.filter(op=>!op.multiGroup)
 if(data.groupMoodGapExclusions.includes(group)){delete data.groupRecoveryFullMembers[group];delete data.groupRecoveryReturnMicros[group]}
 else if(data.groupRecoveryFullMembers[group])data.groupRecoveryFullMembers[group]=gapWorkers.filter(op=>op.isResting()||data.groupRecoveryFullMembers[group]!.includes(op.name)).map(op=>op.name)
 if(data.groupRestInFullOnMoodGap&&!data.groupMoodGapExclusions.includes(group)&&!data.groupRecoveryFullMembers[group]){
  const times=gapWorkers.flatMap(op=>{const time=completedAt(data,op);return time===undefined?[]:[time]})
  if(times.length>1&&Math.max(...times)-Math.min(...times)>toMowerMicros(data.groupMoodGapThresholdMinutes/60))data.groupRecoveryFullMembers[group]=gapWorkers.map(op=>op.name)
 }
 const gapNames=data.groupRecoveryFullMembers[group]??[]
 if(gapNames.length&&data.groupRecoveryReturnMicros[group]===undefined){
  const residents=gapWorkers.filter(op=>op.isResting()),high=residents.filter(op=>op.restingPriority==='high')
  const times=(high.length?high:residents.length?residents:gapWorkers).flatMap(op=>{const time=completedAt(data,op);return time===undefined?[]:[time]})
  if(times.length)data.groupRecoveryReturnMicros[group]=Math.max(data.nowMicros,Math.min(...times)-toMowerMicros(8/60))
 }
 const anchor=data.groupRecoveryReturnMicros[group]
 const cap=gapNames.length&&data.groupMoodGapMaxExtraWaitHours>0&&anchor!==undefined?anchor+toMowerMicros(data.groupMoodGapMaxExtraWaitHours):undefined
 const explicit=workers.filter(op=>op.restInFull).map(op=>op.name)
 const requiredNames=[...new Set([...explicit,...(cap===undefined||data.nowMicros<cap?gapNames:[])])]
 const explicitTimes=explicit.map(name=>completedAt(data,data.operators[name]!))
 if(explicitTimes.some(time=>time===undefined))return {requiredNames,timeMicros:undefined}
 const deadlines=explicitTimes as number[]
 if(gapNames.length){
  const times=gapNames.map(name=>completedAt(data,data.operators[name]!))
  if(times.some(time=>time===undefined)){
   if(cap===undefined)return {requiredNames,timeMicros:undefined}
   deadlines.push(cap)
  }else{
   const latest=Math.max(...times as number[])
   deadlines.push(cap===undefined?latest:Math.min(latest,cap))
  }
 }
 return {requiredNames,timeMicros:deadlines.length?Math.max(data.nowMicros,...deadlines):undefined}
}

/** Actual recovery may finish within the existing room-operation allowance. */
export function mowerRecoveryReady(data:MowerSchedulingData,op:MowerOperatorState|undefined,options:MowerTaskSchedulingOptions={}):boolean {
 if(!op)return false
 if(mowerRecoveryMoodComplete(data,op))return true
 if(op.moodIsPrediction||op.timeStampMicros===undefined||!Number.isFinite(op.mood)||op.mood<0||op.mood>24)return false
 const observation=mowerSchedulingMoodObservation(data,op.name)
 if(observation&&observation[1]>op.timeStampMicros)return false
 if(!op.currentRoom&&data.restMoodComplete(op.name))return true
 if(!op.isResting())return false
 const due=mowerObservedRecoveryDeadline(data,op)
 return due!==undefined&&due>data.nowMicros&&due-data.nowMicros<=toMowerMicros(alphaDormMinutes(op.currentRoom,options)/60)
}

/** Split only untouched ordinary rooms with no shared occupants or group dependencies. */
export function splitMowerRecoveryTask(data:MowerSchedulingData,task:MowerTask,pending:MowerTask[],unfinished:Iterable<string>):void {
 if(![T.SHIFT_ON,T.SELF_CORRECTION,T.RE_ORDER].includes(task.type)||task.metadata||task.arrangementStarted||task.backupShiftActive||task.backupExplicitSlots.size||task.backupRefreshRules||task.productShiftLocked||task.exhaustSupport||task.ordinaryCoordination||task.preferredReplacementRestore||task.dormRecoveryRestore.length||task.arrangementRetryRoom||task.backupShiftIntent!==undefined||task.backupShiftConditions!==undefined)return
 const resources=(names:Iterable<string>)=>{
  const result=new Set<string>()
  for(const name of names){const op=data.operators[name];if(!op)continue;result.add('operator:'+name);for(const group of op.multiGroup?op.groupBindings.map(binding=>binding.group):[op.group])if(group)result.add('group:'+group)}
  return result
 }
 const involved=new Map<string,Set<string>>()
 for(const [room,row] of Object.entries(task.plan)){
  const names=new Set<string>()
  row.forEach((name,index)=>{if(name==='Current')return;names.add(name);const occupant=data.currentOperator(room,index);if(occupant)names.add(occupant.name);const owner=data.plan[room]?.[index];if(owner)names.add(owner)})
  involved.set(room,resources(names))
 }
 const blocked=new Set<string>(),related=resources(unfinished)
 for(;;){const connected=[...involved].filter(([room,names])=>!blocked.has(room)&&[...names].some(name=>related.has(name)));if(!connected.length)break;for(const [room,names] of connected){blocked.add(room);for(const name of names)related.add(name)}}
 if(!blocked.size)return
 const independent=Object.fromEntries(Object.entries(task.plan).filter(([room])=>!blocked.has(room)).map(([room,row])=>[room,[...row]]))
 if(!Object.keys(independent).length)return
 const sibling=new MowerTask({time:task.time,type:task.type,plan:independent});sibling.derivedCorrection=task.derivedCorrection;sibling.correctionSkipDorm=task.correctionSkipDorm
 task.plan=Object.fromEntries(Object.entries(task.plan).filter(([room])=>blocked.has(room)))
 task.groupShiftTransitions=mowerArrangementGroupTransitions(data,task.plan)
 pending.push(sibling)
}

export function mowerUnfinishedReturnMembers(data:MowerSchedulingData,task:MowerTask,options:MowerTaskSchedulingOptions={}):Set<string>{
 const required=new Set<string>()
 for(const [room,row] of Object.entries(task.plan))if(!room.startsWith('dorm'))row.forEach((name,index)=>{
  if(task.backupExplicitSlots.has(room+'\0'+index))return
  const op=data.operators[name];if(!op||op.room!==room||op.index!==index||op.currentRoom!==''&&!op.isResting())return
  if(op.restInFull&&!op.workaholic)required.add(name)
  if(op.group)for(const member of mowerGroupRecoveryDeadline(data,op.group).requiredNames)required.add(member)
 })
 return new Set([...required].filter(name=>!mowerRecoveryReady(data,data.operators[name],options)))
}
