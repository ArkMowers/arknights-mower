import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,type MowerTask} from './mowerTaskQueue'

export type MowerExhaustRoomContext=Readonly<Record<string,readonly unknown[]>>

/** Mower ae9fc322: dynamic deadlines depend on effective roles, never observations. */
export function mowerExhaustTaskSignatures(data:MowerSchedulingData,tasks:readonly MowerTask[],rooms:MowerExhaustRoomContext={}):Map<MowerTask,string>{
 const signatures=new Map<MowerTask,string>()
 for(const task of tasks){
  if(task.type!==T.EXHAUST_OFF||task.backupGroupRequest||Object.keys(task.plan).length||task.retainsExecution)continue
  const names=new Set(task.metadata.split(','))
  for(const name of [...names]){const op=data.operators[name];if(op?.group)data.group(op.group).forEach(member=>names.add(member))}
  signatures.set(task,JSON.stringify([...names].sort().map(name=>{
   const op=data.operators[name]
   return op?[name,op.room,op.index,op.group,op.replacement,op.isHigh(),op.exhaustRequire,op.workaholic,op.restInFull,op.lowerLimit,op.upperLimit,rooms[op.room]??null]:[name,null]
  })))
 }
 return signatures
}

/** Mutate only the caller's queue view; retained failures keep their original identity. */
export function invalidateMowerExhaustTasks(data:MowerSchedulingData,tasks:MowerTask[],previous:ReadonlyMap<MowerTask,string>,rooms:MowerExhaustRoomContext={}):void{
 const current=mowerExhaustTaskSignatures(data,tasks,rooms)
 for(let index=tasks.length-1;index>=0;index--){
  const task=tasks[index]!,before=previous.get(task),after=current.get(task)
  if(before!==undefined&&after!==undefined&&before!==after)tasks.splice(index,1)
 }
}
