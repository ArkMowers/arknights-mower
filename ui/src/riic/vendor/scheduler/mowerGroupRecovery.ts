import {hasObservedFullMood,type MowerOperatorState} from './mowerOperatorState'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {toMowerMicros} from './mowerTaskQueue'
import {alphaDormMinutes} from './mowerAlphaTaskProtection'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'

/** Work primaries participating in group recovery, excluding standby and personal rest. */
export function mowerGroupRecoveryWorkers(data:MowerSchedulingData,group:string):MowerOperatorState[]{
 return data.shiftGroupMembers(group).map(name=>data.operators[name]!).filter(op=>op.isHigh()&&!op.room.startsWith('dorm')&&!op.workaholic&&!op.independentRest&&!data.canStandby(op)&&(op.isResting()||!op.currentRoom))
}
function completedAt(data:MowerSchedulingData,op:MowerOperatorState):number|undefined {
 if(hasObservedFullMood(op)||!op.currentRoom&&!op.moodIsPrediction&&data.restMoodComplete(op.name))return data.nowMicros
 return data.getDormByName(op.name)?.[1].timeMicros
}
/** The extra-wait cap limits only the gap wait; explicit full recovery remains binding. */
export function mowerGroupRecoveryDeadline(data:MowerSchedulingData,group:string):{requiredNames:string[];timeMicros:number|undefined}{
 const workers=mowerGroupRecoveryWorkers(data,group),gapWorkers=workers.filter(op=>!op.multiGroup)
 if(data.groupMoodGapExclusions.includes(group)){delete data.groupRecoveryFullMembers[group];delete data.groupRecoveryReturnMicros[group]}
 else if(data.groupRecoveryFullMembers[group])data.groupRecoveryFullMembers[group]=gapWorkers.map(op=>op.name)
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
 if(op.moodIsPrediction||op.timeStampMicros===undefined||!Number.isFinite(op.mood)||op.mood<0||op.mood>24)return false
 if(hasObservedFullMood(op)||!op.currentRoom&&data.restMoodComplete(op.name))return true
 if(!op.isResting())return false
 const bed=data.getDormByName(op.name)?.[1],due=bed?.timeMicros
 return bed?.position[0]===op.currentRoom&&bed.position[1]===op.currentIndex&&due!==undefined&&due>data.nowMicros&&due-data.nowMicros<=toMowerMicros(alphaDormMinutes(op.currentRoom,options)/60)
}
