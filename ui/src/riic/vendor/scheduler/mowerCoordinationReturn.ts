import {mowerAlphaRecoveryBatches} from './mowerAlphaRecovery'
import {alphaPosition} from './mowerAlphaDorm'
import {mowerForcedGroupCoverReservations} from './mowerBackupGroupTasks'
import {generateMowerDormTasks} from './mowerDormTasks'
import {mowerRefreshDormTime,projectMowerArrangements} from './mowerObservations'
import {mowerUnfinishedReturnMembers} from './mowerGroupRecovery'
import {admitMowerDerivedTasks} from './mowerTaskDerivation'
import {MOWER_TASK_TYPES as T,toMowerMicros,MowerTask} from './mowerTaskQueue'
import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerRestingOptions} from './mowerOrdinaryPlanning'
import type {MowerCoordinationRates} from './mowerReplacementCoordination'

/** Forecast only real complete returns of the requesting rest units. */
export function mowerCoordinationReturn(data:MowerSchedulingData,units:readonly (readonly string[])[],rates:MowerCoordinationRates,options:MowerRestingOptions):{task:MowerTask;units:number[]}|undefined {
 const trial=projectMowerArrangements(data,[])
 for(const bed of trial.allDorms()){
  const op=trial.operators[bed.name]
  if(!op?.isResting())continue
  const rate=rates.recovery[op.name]
  if(rate===undefined||!Number.isFinite(rate)||rate<0)return
  // These are virtual observations of the current projected staffing, not old
  // recovery timers from before the recall changed the room's skills.
  bed.timeMicros=undefined
  op.timeStampMicros=trial.nowMicros
  op.dormRecoveryObservation=undefined
  if(op.mood>=op.upperLimit)bed.timeMicros=trial.nowMicros
  else if(rate>0)mowerRefreshDormTime(trial,op.currentRoom,op.currentIndex,op.name,trial.nowMicros+toMowerMicros((24-op.mood)/rate))
 }
 const protectedNames=new Set([...trial.busyRestingNames,...trial.reservedProductReplacements,...options.reservedNames??[]])
 const slots=new Set([...trial.reservedProductBeds.keys(),...options.reservedSlots??[]])
 const groups=new Set([...protectedNames].flatMap(name=>trial.operators[name]?.group?[trial.operators[name]!.group]:[]))
 const {batches}=mowerAlphaRecoveryBatches(trial,trial,{names:protectedNames,groups,slots})
 // Preserve the same automatic group-wait latch as real metadata across the
 // forecast's rate boundaries; a new rate must not restart its extra-wait cap.
 data.groupRecoveryFullMembers=structuredClone(trial.groupRecoveryFullMembers)
 data.groupRecoveryReturnMicros={...trial.groupRecoveryReturnMicros}
 const pending=(options.tasks??options.retainedTasks??[]).map(task=>Object.assign(new MowerTask(),structuredClone(task),{type:task.type}))
 const tasks=admitMowerDerivedTasks(trial,pending,generateMowerDormTasks(batches,trial),options.dependencyReturn)
 const forced=mowerForcedGroupCoverReservations(trial)
 for(const task of tasks.filter(task=>task.type===T.SHIFT_ON).sort((a,b)=>a.timeMicros-b.timeMicros)){
  if(Object.entries(task.plan).some(([room,row])=>row.some((name,index)=>name!=='Current'&&(protectedNames.has(name)||slots.has(alphaPosition(room,index))||(forced.names.has(name)||forced.slots.has(alphaPosition(room,index)))&&trial.currentOperator(room,index)?.name!==name))))continue
  const projected=projectMowerArrangements(trial,[task.plan])
  const completed=units.flatMap((names,index)=>names.length&&names.every(name=>{
   const op=projected.operators[name]
   return !!op&&op.currentRoom===op.room&&op.currentIndex===op.index
  })?[index]:[])
  if(!completed.length)continue
  if(task.timeMicros<=data.nowMicros&&mowerUnfinishedReturnMembers(trial,task,options.priorityScheduling).size)continue
  return {task,units:completed}
 }
}
