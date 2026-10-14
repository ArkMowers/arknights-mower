/**
 * Native notification branch (1265-1273), todo_list (4244-4265), and run flag reset
 * (400-402), alpha c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88.
 * MIT, Copyright 2021 Nano. This core does not execute earlier infra_main phases.
 * The caller must dispatch the notification branch only after those phases.
 * Todo bill collection is a bulk button; native todo_list does not call accept_order.
 */
import type {MowerTaskQueue} from './mowerTaskQueue'
export interface MowerNotificationFlags {todoTask:boolean;collectNotification:boolean;planned:boolean}
export interface MowerNotificationState {
 queue:MowerTaskQueue;flags:MowerNotificationFlags;lastTodoMicros:number|null
 /** Recycle extension from alpha 9091f2b; omitted for frozen legacy replays. */
 collectRecycle?:boolean
}
type CollectResource='bill'|'factory'|'trust'|'recycle'
export type MowerNotificationRequest=
 |{kind:'detect-notification'}
 |{kind:'sleep';seconds:1}
 |{kind:'tap-notification';target:unknown}
 |{kind:'find-collect';resource:CollectResource;name:`infra_collect_${CollectResource}`}
 |{kind:'tap-collect';resource:CollectResource;target:unknown}
 |{kind:'tap-close-todo';target:[1840,140]}
export interface MowerNotificationObservation {
 kind:MowerNotificationRequest['kind'];observedAtMicros:number;value:unknown
}
export interface MowerNotificationSeam {nowMicros():number}
export type MowerNotificationGenerator=Generator<MowerNotificationRequest,null,MowerNotificationObservation>
function* observed(seam:MowerNotificationSeam,request:MowerNotificationRequest):
 Generator<MowerNotificationRequest,unknown,MowerNotificationObservation>{
 const observation=yield request
 if(!observation||observation.kind!==request.kind||!Object.prototype.hasOwnProperty.call(observation,'value')||observation.value===undefined)
  throw new Error('Explicit matching notification observation is required; None is null')
 if(!Number.isSafeInteger(observation.observedAtMicros)||observation.observedAtMicros!==seam.nowMicros())
  throw new Error('Notification observation must describe the advanced scheduler wall clock')
 return observation.value
}
function nativeTruthy(value:unknown):boolean{
 if(value===null||value===false||value===0||value==='')return false
 if(Array.isArray(value))return value.length!==0
 if(typeof value==='object')return Object.keys(value).length!==0
 return true
}
export function resetMowerRunFlags(flags:MowerNotificationFlags):void{
 flags.todoTask=false;flags.collectNotification=false;flags.planned=false
}
/** Selected infra_main notification branch, not a replacement for the preceding stages. */
export function* collectMowerInfraNotification(state:MowerNotificationState,seam:MowerNotificationSeam):MowerNotificationGenerator{
 // Native no_pending_task(1) uses strict time < now+one minute, with no task type filter.
 if(state.queue.tasks.every(task=>task.timeMicros>=seam.nowMicros()+60_000_000)){
  let notification=yield* observed(seam,{kind:'detect-notification'})
  if(notification===null){
   yield* observed(seam,{kind:'sleep',seconds:1})
   notification=yield* observed(seam,{kind:'detect-notification'})
  }
  if(notification!==null)yield* observed(seam,{kind:'tap-notification',target:notification})
 }
 state.flags.collectNotification=true
 return null
}
/** Scene.INFRA_TODOLIST dispatch; no_pending_task gating is not present in this method. */
export function* collectMowerTodoList(state:MowerNotificationState,seam:MowerNotificationSeam):MowerNotificationGenerator{
 let tapped=false
 if(state.lastTodoMicros===null||(state.collectRecycle?state.lastTodoMicros<=seam.nowMicros()-900_000_000:state.lastTodoMicros<seam.nowMicros()-900_000_000)){
  const resources:CollectResource[]=state.collectRecycle?['bill','factory','trust','recycle']:['bill','factory','trust']
  for(const resource of resources){
   const target=yield* observed(seam,{kind:'find-collect',resource,name:`infra_collect_${resource}`})
   if(nativeTruthy(target)){
    yield* observed(seam,{kind:'tap-collect',resource,target})
    tapped=true
    // Source breaks after the first tap per resource; no additional find in this invocation.
   }
  }
  state.lastTodoMicros=seam.nowMicros()
 }
 if(!tapped){
  yield* observed(seam,{kind:'tap-close-todo',target:[1840,140]})
  state.flags.todoTask=true
 }
 return null
}
