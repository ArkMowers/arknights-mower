/**
 * Selected default infra_main todo-task branch at alpha
 * c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88:1229-1264 (MIT, Copyright 2021 Nano).
 * Earlier task/planning phases and inner clue/reload/device flows belong to the caller.
 * Read each gate at its native position, after previous nested I/O has advanced time.
 */
import {toMowerMicros,type MowerTaskQueue} from './mowerTaskQueue'
import type {MowerNotificationFlags} from './mowerNotification'
export interface MowerTodoTaskState {
 queue:MowerTaskQueue;flags:MowerNotificationFlags
 enableParty:boolean;lastClueMicros:number|null
 droneRoom:string|null;runOrderRooms:readonly string[];droneTimeMicros:number|null;droneIntervalHours:number
 reloadRooms:readonly string[]|null;reloadTimeMicros:number|null;maaGapHours:number
}
export type MowerTodoTaskRequest=
 |{kind:'clue-new'}
 |{kind:'drone';room:string}
 |{kind:'reload';rooms:readonly string[]}
export interface MowerTodoTaskObservation {
 kind:MowerTodoTaskRequest['kind'];observedAtMicros:number
 /** For reload, value must include the actual inner reload_time snapshot, including null. */
 value:unknown
}
export interface MowerTodoTaskSeam {nowMicros():number}
export type MowerTodoTaskGenerator=Generator<MowerTodoTaskRequest,null,MowerTodoTaskObservation>
function* observed(seam:MowerTodoTaskSeam,request:MowerTodoTaskRequest):
 Generator<MowerTodoTaskRequest,unknown,MowerTodoTaskObservation>{
 const observation=yield request
 if(!observation||observation.kind!==request.kind||!Object.prototype.hasOwnProperty.call(observation,'value')||observation.value===undefined)
  throw new Error('Explicit matching todo-task observation is required; None is null')
 if(!Number.isSafeInteger(observation.observedAtMicros)||observation.observedAtMicros!==seam.nowMicros())
  throw new Error('Todo-task observation must describe the advanced scheduler wall clock')
 return observation.value
}
function noPendingTask(state:MowerTodoTaskState,seam:MowerTodoTaskSeam,minutes:number):boolean{
 return state.queue.tasks.every(task=>task.timeMicros>=seam.nowMicros()+minutes*60_000_000)
}
export function* executeMowerTodoTask(state:MowerTodoTaskState,seam:MowerTodoTaskSeam):MowerTodoTaskGenerator{
 if(state.enableParty&&(state.lastClueMicros===null||seam.nowMicros()-state.lastClueMicros>3_600_000_000)&&
  noPendingTask(state,seam,3)){
  yield* observed(seam,{kind:'clue-new'})
  state.lastClueMicros=seam.nowMicros()
 }
 if(!state.runOrderRooms.includes(state.droneRoom??'')&&
  (state.droneTimeMicros===null||state.droneTimeMicros<seam.nowMicros()-toMowerMicros(state.droneIntervalHours))&&
  state.droneRoom!==null&&noPendingTask(state,seam,2)){
  yield* observed(seam,{kind:'drone',room:state.droneRoom})
  // Native False/None returns from drone still write drone_time and continue reload.
  state.droneTimeMicros=seam.nowMicros()
 }
 if(state.reloadRooms!==null&&noPendingTask(state,seam,2)&&
  (state.reloadTimeMicros===null||state.reloadTimeMicros<seam.nowMicros()-toMowerMicros(state.maaGapHours))){
  const value=yield* observed(seam,{kind:'reload',rooms:state.reloadRooms})
  if(!value||typeof value!=='object'||!Object.prototype.hasOwnProperty.call(value,'reloadTimeMicros'))
   throw new Error('Inner reload_time observation is required; do not infer successful reload from elapsed time')
  const snapshot=(value as {reloadTimeMicros:unknown}).reloadTimeMicros
  if(snapshot!==null&&(typeof snapshot!=='number'||!Number.isSafeInteger(snapshot)))
   throw new Error('Explicit native reload_time snapshot must be null or safe microseconds')
  state.reloadTimeMicros=snapshot
 }
 state.flags.todoTask=true
 return null
}
