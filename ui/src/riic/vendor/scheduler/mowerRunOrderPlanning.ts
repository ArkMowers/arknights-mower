/**
 * Ideal order observations and deadline wakes, adapted from Mower alpha.
 * Source c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
 * Production owns the order clock; these tasks never arrange runners or spend drones.
 */
import {MOWER_TASK_TYPES as T,MowerTask,MowerTaskQueue,toMowerMicros} from './mowerTaskQueue'
import {scheduleMowerTasks,type MowerTaskSchedulingOptions} from './mowerTaskScheduling'

export interface RunOrderPlanSlot {replacement:readonly string[]}
export interface RunOrderPlanningState {
 plan:Readonly<Record<string,readonly RunOrderPlanSlot[]>>
 runOrderRooms:readonly string[]
 queue:MowerTaskQueue
 configuredDelayMinutes:number
 droneRoom:string|null
 flags:{planned:boolean;todoTask:boolean;collectNotification:boolean}
}
export type RunOrderIORequest=
 |{kind:'enter-room';room:string}
 |{kind:'wait-interface';room:string;requestedIntervalMicros:1_000_000}
 |{kind:'read-order';room:string;useDigitReader:true}
 |{kind:'return-main';room:string}
export interface RunOrderIOObservation {
 observedAtMicros:number
 absoluteDueMicros?:number
}
export interface RunOrderPlanningSeam {
 nowMicros():number
 currentDormOccupants(room:string):readonly string[]|undefined
 scheduling:MowerTaskSchedulingOptions
 onScheduling?(conflict:[MowerTask,MowerTask]|undefined):void
}
export type RunOrderGenerator<T>=Generator<RunOrderIORequest,T,RunOrderIOObservation>
function* step(seam:RunOrderPlanningSeam,request:RunOrderIORequest):RunOrderGenerator<RunOrderIOObservation>{
 const observation=yield request
 if(!Number.isSafeInteger(observation.observedAtMicros)||observation.observedAtMicros!==seam.nowMicros())
  throw new Error('Observation must describe the advanced scheduler wall clock')
 return observation
}
export function* observeNativeRunOrderTime(state:RunOrderPlanningState,seam:RunOrderPlanningSeam,room:string):RunOrderGenerator<number>{
 yield* step(seam,{kind:'enter-room',room})
 yield* step(seam,{kind:'wait-interface',room,requestedIntervalMicros:1_000_000})
 const read=yield* step(seam,{kind:'read-order',room,useDigitReader:true})
 if(read.absoluteDueMicros===undefined||!Number.isSafeInteger(read.absoluteDueMicros))
  throw new Error('Native absolute order deadline observation is required')
 const executeTime=read.absoluteDueMicros-toMowerMicros(state.configuredDelayMinutes/60)
 yield* step(seam,{kind:'return-main',room})
 return executeTime
}
export function* planDefaultRunOrder(state:RunOrderPlanningState,seam:RunOrderPlanningSeam,room:string):RunOrderGenerator<MowerTask|undefined>{
 if(state.queue.find({type:T.RUN_ORDER,metadata:room}))return
 if(!state.plan[room])throw new Error('Native run-order room is absent from the plan: '+room)
 const timeMicros=yield* observeNativeRunOrderTime(state,seam,room)
 const dueMicros=timeMicros+toMowerMicros(state.configuredDelayMinutes/60)
 // A ready order or a full queue has no future completion to wake for. Leave
 // its collection/resource dependency to production and the notification phase.
 if(dueMicros<=seam.nowMicros())return
 const task=new MowerTask({type:T.RUN_ORDER,metadata:room})
 task.timeMicros=timeMicros
 task.observedOrderDueMicros=dueMicros
 state.queue.tasks.push(task)
 return task
}
export function* runDefaultTradeSegment(state:RunOrderPlanningState,seam:RunOrderPlanningSeam):RunOrderGenerator<{tailShouldRun:true}>{
 if(state.runOrderRooms.length){
  const valid=Object.keys(state.plan).filter(room=>room.includes('dormitory')).every(room=>{
   const occupants=seam.currentDormOccupants(room)
   return occupants!==undefined&&occupants.length===5
  })
  if(valid){
   for(const room of state.runOrderRooms)yield* planDefaultRunOrder(state,seam,room)
   const conflict=scheduleMowerTasks(state.queue.tasks,seam.nowMicros(),{
    ...seam.scheduling,configuredDelayMinutes:state.configuredDelayMinutes,experimental:false,
   })
   seam.onScheduling?.(conflict)
  }
 }
 return {tailShouldRun:true}
}
export function* dispatchDefaultRefreshTime(state:RunOrderPlanningState,seam:RunOrderPlanningSeam,task:MowerTask):RunOrderGenerator<void>{
 yield* planDefaultRunOrder(state,seam,task.metadata)
 state.flags.todoTask=true
 state.flags.collectNotification=true
 state.queue.consume(task)
}
