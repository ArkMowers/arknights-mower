import {mowerPendingReturnRecoverySlots} from './mowerRetainedRecovery'
import {mowerHeldRestGroups,mowerForcedWorkGroups,mowerForcedWorkReturn} from './mowerBackupGroupTasks'
import {admitMowerDerivedTasks} from './mowerTaskDerivation'
import {generateMowerDormTasks} from './mowerDormTasks'
import {mowerDormCandidateMood,mowerSchedulingMoodObservation} from './mowerSchedulingMood'
import {restingThresholdFor,type MowerOperatorState} from './mowerOperatorState'
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
 return data.shiftGroupMembers(group).map(name=>data.operators[name]!).filter(op=>op.isHigh()&&!op.room.startsWith('dorm')&&!op.workaholic&&!op.independentRest&&(!op.shiftGroup||op.group===group)&&!data.canStandby(op)&&(op.isResting()||!op.currentRoom))
}
function completedAt(data:MowerSchedulingData,op:MowerOperatorState):number|undefined {
 if(mowerRecoveryMoodComplete(data,op)||!op.currentRoom&&!op.moodIsPrediction&&data.restMoodComplete(op.name))return data.nowMicros
 return mowerObservedRecoveryDeadline(data,op)
}
/** The extra-wait cap limits only the gap wait; explicit full recovery remains binding. */
export function mowerGroupRecoveryDeadline(data:MowerSchedulingData,group:string):{requiredNames:string[];timeMicros:number|undefined}{
 const workers=mowerGroupRecoveryWorkers(data,group),gapWorkers=workers.filter(op=>data.isGroupShiftAnchor(op,group))
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

/** Restored primary membership uses the final group's existing recovery policy and observed deadlines. */
export function mowerRestoredGroupRecoveryDeadline(actual:MowerSchedulingData,effective:MowerSchedulingData,groups:Iterable<string>,delayedGroups?:Set<string>):number|undefined {
 const deadlines:number[]=[]
 for(const group of groups){
  if(mowerForcedWorkGroups(effective).has(group))continue
  const restored=mowerGroupRecoveryWorkers(effective,group).filter(op=>{
   const previous=actual.operators[op.name]
   return previous&&(previous.isResting()||!previous.currentRoom)&&!actual.isGroupShiftAnchor(previous,group)
  })
  if(!restored.length)continue
  const recovery=mowerGroupRecoveryDeadline(effective,group)
  if(!recovery.requiredNames.length||recovery.timeMicros===undefined||recovery.timeMicros<=actual.nowMicros)continue
  if(effective.groupRecoveryFullMembers[group])actual.groupRecoveryFullMembers[group]=[...effective.groupRecoveryFullMembers[group]!]
  if(effective.groupRecoveryReturnMicros[group]!==undefined)actual.groupRecoveryReturnMicros[group]=effective.groupRecoveryReturnMicros[group]!
  delayedGroups?.add(group)
  deadlines.push(recovery.timeMicros)
 }
 return deadlines.length?Math.max(...deadlines):undefined
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

/** Split untouched ordinary rooms or slots by their shared occupants and group dependencies. */
export function splitMowerRecoveryTask(data:MowerSchedulingData,task:MowerTask,pending:MowerTask[],unfinished:Iterable<string>,splitBySlot=false):void {
 if(![T.SHIFT_ON,T.SELF_CORRECTION,T.RE_ORDER].includes(task.type)||task.metadata||task.arrangementStarted||task.backupShiftActive||task.backupExplicitSlots.size||task.backupRefreshRules||task.productShiftLocked||task.exhaustSupport||task.ordinaryCoordination||task.preferredReplacementRestore||task.dormRecoveryRestore.length||task.arrangementRetryRoom||task.backupShiftIntent!==undefined||task.backupShiftConditions!==undefined)return
 const resources=(names:Iterable<string>)=>{
  const result=new Set<string>()
  for(const name of names){const op=data.operators[name];if(!op)continue;result.add('operator:'+name);for(const group of splitBySlot&&op.isHigh()&&!op.room.startsWith('dorm')?data.shiftRequestGroups([name]):op.multiGroup?op.groupBindings.map(binding=>binding.group):[op.group])if(group)result.add('group:'+group)}
  return result
 }
 const unfinishedNames=[...unfinished]
 const involved=new Map<string,Set<string>>(),keyFor=(room:string,index:number)=>splitBySlot?room+'\0'+index:room
 for(const [room,row] of Object.entries(task.plan))row.forEach((name,index)=>{
  if(name==='Current')return
  const names=new Set([name]),occupant=data.currentOperator(room,index),owner=data.plan[room]?.[index]
  if(name==='Free')for(const actor of unfinishedNames)if(mowerPendingReturnRecoverySlots(data,task,actor).has(room+'\0'+index))names.add(actor)
  if(occupant)names.add(occupant.name)
  if(owner)names.add(owner)
  const moving=data.operators[name],sourceOwner=moving?.currentRoom&&!moving.currentRoom.startsWith('dorm')?data.plan[moving.currentRoom]?.[moving.currentIndex]:undefined
  if(sourceOwner)names.add(sourceOwner)
  const key=keyFor(room,index),related=involved.get(key)??new Set<string>()
  for(const resource of resources(names))related.add(resource)
  involved.set(key,related)
 })
 const blocked=new Set<string>(),related=resources(unfinishedNames)
 for(;;){const connected=[...involved].filter(([key,names])=>!blocked.has(key)&&[...names].some(name=>related.has(name)));if(!connected.length)break;for(const [key,names] of connected){blocked.add(key);for(const name of names)related.add(name)}}
 if(!blocked.size)return
 const part=(waiting:boolean)=>Object.fromEntries(Object.entries(task.plan).map(([room,row])=>[room,row.map((name,index)=>blocked.has(keyFor(room,index))===waiting?name:'Current')] as [string,string[]]).filter(([,row])=>row.some(name=>name!=='Current')))
 const independent=part(false)
 if(!Object.keys(independent).length)return
 const sibling=new MowerTask({time:task.time,type:task.type,plan:independent});sibling.derivedCorrection=task.derivedCorrection;sibling.correctionSkipDorm=task.correctionSkipDorm
 task.plan=part(true)
 task.groupShiftTransitions=mowerArrangementGroupTransitions(data,task.plan)
 pending.push(sibling)
}

export function mowerUnfinishedReturnMembers(data:MowerSchedulingData,task:MowerTask,options:MowerTaskSchedulingOptions={}):Set<string>{
 const required=new Set<string>()
 for(const [room,row] of Object.entries(task.plan))if(!room.startsWith('dorm'))row.forEach((name,index)=>{
  if(task.backupExplicitSlots.has(room+'\0'+index)||mowerForcedWorkReturn(data,name))return
  const op=data.operators[name];if(!op||op.room!==room||op.index!==index||op.currentRoom!==''&&!op.isResting())return
  if(op.restInFull&&!op.workaholic)required.add(name)
  if(op.group)for(const member of mowerGroupRecoveryDeadline(data,op.group).requiredNames)required.add(member)
 })
 return new Set([...required].filter(name=>!mowerRecoveryReady(data,data.operators[name],options)))
}

/** Project recovery only for the return threshold, without confirming full recovery. */
function returningMood(data:MowerSchedulingData,op:MowerOperatorState):number|undefined {
 const observation=mowerSchedulingMoodObservation(data,op.name)
 if(!observation)return
 const [mood,observedAt]=observation
 if(!op.isResting()||observedAt!==op.timeStampMicros||mood>=op.upperLimit)return mood
 const due=mowerObservedRecoveryDeadline(data,op)
 if(due===undefined||due<=observedAt)return mood
 return Math.min(op.upperLimit,mood+(op.upperLimit-mood)*(data.nowMicros-observedAt)/(due-observedAt))
}

/** Prefer an existing group return while retaining the mandatory departure as fallback. */
export function mowerMoodLimitGroupReturn(data:MowerSchedulingData,release:MowerTask,tasks:MowerTask[],options:MowerTaskSchedulingOptions={}):MowerTask|undefined {
 const untouched=(task:MowerTask)=>!task.retainsExecution&&!task.arrangementStarted&&!task.backupShiftActive&&!task.productShiftLocked&&!task.backupExplicitSlots.size&&!task.backupShiftIntent&&!task.dormRecoveryRestore.length&&!task.arrangementRetryRoom
 if(!data.alpha||release.type!==T.RELEASE_DORM||!release.strictMoodLimit||release.timeMicros>data.nowMicros||!tasks.includes(release)||!untouched(release)||release.moodLimitReturnAttempted)return
 const op=data.operators[release.metadata]
 if(!op?.isHigh()||!op.group||mowerHeldRestGroups(data).has(op.group)||op.room.startsWith('dorm')||op.workaholic||data.canStandby(op)||op.multiGroup&&!op.shiftGroup||op.independentRest||!data.groupIsResting(op.group)||!op.restMoodLimit||data.freeRoomExcluded(op.name)||release.moodLimit!==undefined&&release.moodLimit!==op.upperLimit)return
 const target=release.releaseDormTargets()[op.name]
 if(!target||target[0]!==op.currentRoom||target[1]!==op.currentIndex)return
 for(const existing of tasks){
  if(existing.type!==T.SHIFT_ON||!untouched(existing)||existing.plan[op.room]?.[op.index]!==op.name)continue
  const bed=data.getDormByName(op.name)?.[1]
  if(!bed)return
  const task=admitMowerDerivedTasks(data,tasks,generateMowerDormTasks([{timeMicros:data.nowMicros,dorms:[bed],restInFull:false}],data)).find(candidate=>candidate.plan[op.room]?.[op.index]===op.name)
  if(!task)continue
  const rooms=Object.keys(task.plan).filter(room=>!room.startsWith('dorm'))
  const duration=toMowerMicros((rooms.indexOf(op.room)+1)*Math.max(.75,options.executionMinutes??.75)/60)
  if(data.nowMicros+duration>(release.moodLimitDeadlineMicros??release.timeMicros))continue
  const returning=Object.entries(task.plan).flatMap(([room,row])=>room.startsWith('dorm')?[]:row.flatMap((name,index)=>{const member=data.operators[name];return member&&member.room===room&&member.index===index?[member]:[]}))
  const groups=new Set(returning.map(member=>member.group).filter(Boolean))
  if([...groups].some(group=>{const recovery=mowerGroupRecoveryDeadline(data,group);return recovery.requiredNames.length||recovery.timeMicros!==undefined}))continue
  if(returning.some(member=>{const mood=returningMood(data,member);const line=member.lowerLimit+(member.upperLimit-member.lowerLimit)*restingThresholdFor(member,data.policy);return member.restInFull||!member.workaholic&&!data.canStandby(member)&&(mood===undefined||mood<=(member.customMoodLimit?line:Math.floor(line)))}))continue
  release.moodLimitReturnAttempted=true
  tasks.push(task)
  return task
 }
}
