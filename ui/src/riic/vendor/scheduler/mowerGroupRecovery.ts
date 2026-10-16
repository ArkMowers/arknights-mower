import {hasObservedFullMood,type MowerOperatorState} from './mowerOperatorState'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {toMowerMicros} from './mowerTaskQueue'

/** Workers participating in this named group's recovery, excluding personal rest. */
export function mowerGroupRecoveryWorkers(data:MowerSchedulingData,group:string):MowerOperatorState[]{
 return data.shiftGroupMembers(group).map(name=>data.operators[name]!).filter(op=>op.isHigh()&&!op.room.startsWith('dorm')&&!op.workaholic&&(op.isResting()||!op.currentRoom&&(!data.canStandby(op)||data.groupRecoveryFullMembers[group]?.includes(op.name))))
}
function completedAt(data:MowerSchedulingData,op:MowerOperatorState):number|undefined {
 if(hasObservedFullMood(op))return data.nowMicros
 return data.getDormByName(op.name)?.[1].timeMicros
}
/** Full-rest requirements are cumulative; a triggered gap persists for this rest cycle. */
export function mowerGroupRecoveryDeadline(data:MowerSchedulingData,group:string):{requiredNames:string[];timeMicros:number|undefined}{
 const workers=mowerGroupRecoveryWorkers(data,group)
 if(data.groupRecoveryFullMembers[group])data.groupRecoveryFullMembers[group]=workers.map(op=>op.name)
 if(data.groupRestInFullOnMoodGap&&!data.groupRecoveryFullMembers[group]){
  const times=workers.flatMap(op=>{const time=completedAt(data,op);return time===undefined?[]:[time]})
  if(times.length>1&&Math.max(...times)-Math.min(...times)>toMowerMicros(data.groupMoodGapThresholdMinutes/60))data.groupRecoveryFullMembers[group]=workers.map(op=>op.name)
 }
 const requiredNames=[...new Set([...workers.filter(op=>op.restInFull).map(op=>op.name),...data.groupRecoveryFullMembers[group]??[]])]
 if(!requiredNames.length)return {requiredNames,timeMicros:undefined}
 const times=requiredNames.map(name=>{const op=data.operators[name];return op?completedAt(data,op):undefined})
 return {requiredNames,timeMicros:times.some(time=>time===undefined)?undefined:Math.max(data.nowMicros,...times as number[])}
}
