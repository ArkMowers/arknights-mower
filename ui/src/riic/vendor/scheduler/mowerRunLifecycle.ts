// Port of handle_error(force=True), Mower alpha c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88.
// MIT, Copyright 2021 Nano. Clock advancement belongs to the device/controller adapter.
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,fromMowerMicros,isMowerRunOrderTask} from './mowerTaskQueue'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'
const STALE_TASK_MICROS=900_000_000
const preservedRunTypes=(alpha:boolean)=>[T.SKILL_UPGRADE,T.SWAP_SUPPORT,T.REFRESH_TIME,T.SWITCH_PRODUCT,...(alpha?[T.FIAMMETTA]:[])]

/** Skip identical zero-time error polls until a queued task or native stale rebuild can change the run. */
export function nextMowerRunRecoveryMicros(queue:MowerTaskQueue,nowMicros:number,alpha=false,options:MowerTaskSchedulingOptions={}):number {
 const preserved=preservedRunTypes(alpha)
 const deadlines=queue.tasks.filter(task=>!task.executionFailure&&(options.adjustForRunOrders!==false||!isMowerRunOrderTask(task))).flatMap(task=>[
  ...(task.timeMicros>nowMicros?[task.timeMicros]:[]),
  ...(!task.retainsExecution&&!preserved.includes(task.type)?[task.timeMicros+STALE_TASK_MICROS+1]:[]),
 ])
 return deadlines.length?Math.max(nowMicros+1,Math.min(...deadlines)):nowMicros+1
}

export function prepareMowerRunEntry(queue:MowerTaskQueue,nowMicros:number,alpha=false,options:MowerTaskSchedulingOptions={}):void {
 const now=fromMowerMicros(nowMicros)
 if(!queue.find({time:now,ignoreRunOrders:options.adjustForRunOrders===false})&&!queue.find({type:T.SKILL_UPGRADE})){const task=new MowerTask();task.timeMicros=nowMicros;queue.tasks.push(task)}
 const preserved=preservedRunTypes(alpha),future=[T.RUN_ORDER,T.FURNITURE,T.DEPOT,T.CLUE,T.WORKSHOP]
 if(alpha?queue.tasks.some(t=>!t.retainsExecution&&t.timeMicros<nowMicros-STALE_TASK_MICROS&&!preserved.includes(t.type)&&(options.adjustForRunOrders!==false||!isMowerRunOrderTask(t))):queue.tasks.some(t=>!t.retainsExecution&&t.timeMicros<nowMicros-STALE_TASK_MICROS&&(options.adjustForRunOrders!==false||!isMowerRunOrderTask(t)))){
  queue.tasks=queue.tasks.filter(task=>task.retainsExecution||preserved.includes(task.type)||alpha&&future.includes(task.type)&&task.timeMicros>nowMicros)
  const task=new MowerTask();task.timeMicros=nowMicros;queue.tasks.push(task)
 }
}
