// Port of default agent_arrange / infra_main arrangement handling in Mower alpha.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import type {BackupTiming} from './backupPlans'
import {MowerRoomArrangementDeferred} from './mowerNativeErrors'
import {MOWER_TASK_TYPES as T,MowerTask,isMowerRunOrderTask,type MowerTaskQueue,type MowerTaskPlan} from './mowerTaskQueue'
export interface MowerBackupResult {changed:boolean;generated:MowerTask[]}
export interface MowerTaskExecutionHooks {
 /** Enable the alpha complete-arrangement boundary in the application adapter. */
 protectShift?:boolean
 alpha?:boolean
 adjustForRunOrders?:boolean
 /** changed is the source solver's new_task result, not any plan-condition change. */
 backup:(phase:BackupTiming,task:MowerTask,context:{appendEmptyTask:boolean;restoreOnDeactivate:boolean;customTimeMicros?:number})=>MowerBackupResult
 /** Physical I/O adapter; this core removes the successfully committed room from the task. */
 arrangeRoom:(room:string,names:string[],getTime:boolean,task:MowerTask,restoration:MowerTaskPlan)=>MowerTaskPlan|void|Generator<MowerRoomReturn,MowerTaskPlan|void,void>
 /** prepare_release_dorm validates identity/cap and clears stale plans. */
 prepareRelease?:(task:MowerTask)=>boolean
 /** A critical task may postpone the remaining dorm rooms without ending this shift. */
 deferRoom?:(room:string,task:MowerTask)=>boolean
 metadata:()=>void
 corrections?:()=>MowerTask[]
 skip?:()=>void
}
function enqueueGenerated(queue:MowerTaskQueue,generated:MowerTask[]):void {for(const task of generated)if(!queue.tasks.includes(task))queue.tasks.push(task)}
function rosterHead(queue:MowerTaskQueue,hooks:MowerTaskExecutionHooks):MowerTask|undefined {return queue.find({ignoreRunOrders:hooks.adjustForRunOrders===false})}
function enterPhase(phase:'BEFORE_WORK'|'BEFORE_DORM',task:MowerTask,queue:MowerTaskQueue,hooks:MowerTaskExecutionHooks):boolean {
 if(task.backupShiftActive)return false
 const result=hooks.backup(phase,task,{appendEmptyTask:false,restoreOnDeactivate:true,customTimeMicros:task.timeMicros-1})
 enqueueGenerated(queue,result.generated)
 if(!result.changed)return false
 const generated=new Set(result.generated),others=queue.tasks.filter(t=>!generated.has(t)&&(hooks.adjustForRunOrders!==false||!isMowerRunOrderTask(t)))
 const anchor=others.length?Math.min(...others.map(t=>t.timeMicros)):task.timeMicros
 // Reverse enumeration gives the first generated task the earliest microsecond.
 for(const [offset,t] of [...result.generated].reverse().entries())t.timeMicros=anchor-offset-1
 if(phase==='BEFORE_WORK'){
  for(const generated of result.generated)for(const [room,names] of Object.entries(generated.plan)){
   const pending=task.plan[room];if(!pending)continue
   for(const [index,name] of names.entries())if(index<pending.length&&name!=='Current')pending[index]='Current'
  }
  for(const [room,names] of Object.entries(task.plan))if(names.every(name=>name==='Current'))delete task.plan[room]
 }else{
  for(const generated of result.generated)for(const room of Object.keys(generated.plan))if(room.startsWith('dormitory_')&&room in task.plan)delete task.plan[room]
 }
 return true
}
/** Returns false only for a deferred original task. Its identity and remaining plan survive. */
export interface MowerRoomReturn {room:string;delayMicros:number;nativeRunOrderIO?:true;returnsInfraMain?:true}
/** Device back(0.5) is a source I/O boundary, including an exact Current no-op. */
export function* executeMowerTaskArrangementSteps(task:MowerTask,queue:MowerTaskQueue,hooks:MowerTaskExecutionHooks):Generator<MowerRoomReturn,boolean,void> {
 if(task.type===T.RUN_ORDER)throw new Error('理想跑单任务仅用于唤醒，不支持实体换人')
 // Native infra_main enters the arrangement branch before preview. A preview that
 // removes every physical move must still unlock the shift and rebuild metadata.
 if(!Object.keys(task.plan).length&&!task.backupShiftActive){queue.consume(task);if(rosterHead(queue,hooks)?.type===T.SHIFT_ON){const result=hooks.backup('AFTER_PLANNING',task,{appendEmptyTask:true,restoreOnDeactivate:false});enqueueGenerated(queue,result.generated)}return true}
 const protectedShift=task.backupShiftActive||!!hooks.protectShift&&Object.keys(task.plan).length>0&&task.type!==T.FIAMMETTA&&task.type!==T.RELEASE_DORM
 if(protectedShift)task.backupShiftActive=true
 let retainedLock=false
 try {
 let getTime=task.type===T.SHIFT_OFF||protectedShift&&(hooks.alpha||Object.keys(task.plan).some(room=>room.startsWith('dormitory_')))||!!hooks.alpha&&[T.SELF_CORRECTION,T.RE_ORDER,T.FILL_DORM,T.NOT_SPECIFIC].includes(task.type)
 if(task.type===T.RELEASE_DORM){if(!hooks.prepareRelease)throw new Error('Mower release requires the identity and mood-limit validation adapter');getTime=hooks.prepareRelease(task)}
 const rooms=Object.keys(task.plan).sort((a,b)=>Number(a.startsWith('dormitory_'))-Number(b.startsWith('dormitory_'))||(a.startsWith('dormitory_')&&b.startsWith('dormitory_')?Number(a.split('_')[1])-Number(b.split('_')[1]):0))
 let beforeWork=false,beforeDorm=false;const restoration:MowerTaskPlan={}
 for(const room of rooms){
  if(!room.startsWith('dormitory_')&&!beforeWork){beforeWork=true;if(enterPhase('BEFORE_WORK',task,queue,hooks)){if(!Object.keys(task.plan).length)queue.consume(task);return false}}
  if(room.startsWith('dormitory_')&&!beforeDorm){beforeDorm=true;if(enterPhase('BEFORE_DORM',task,queue,hooks)){if(!Object.keys(task.plan).length)queue.consume(task);return false}}
  const names=task.plan[room];if(!names)continue
  if(hooks.alpha&&hooks.deferRoom?.(room,task)){retainedLock=true;return false}
  const arrangement=hooks.arrangeRoom(room,names,getTime,task,restoration)
  const additional=arrangement&&'next' in arrangement&&typeof arrangement.next==='function'?yield* (arrangement as Generator<MowerRoomReturn,MowerTaskPlan|void,void>):arrangement
  if(additional)Object.assign(restoration,additional)
  if(task.arrangementRetryRoom===room){delete task.arrangementRetryRoom;delete task.arrangementRetryCount}
  delete task.plan[room];task.dormRecoveryRestore=task.dormRecoveryRestore.filter(r=>r!==room);yield {room,delayMicros:500_000}
 }
 const restoreRooms=Object.keys(restoration)
 if(restoreRooms.length>1){
  queue.tasks.push(new MowerTask({time:rosterHead(queue,hooks)?.time??task.time,plan:restoration,type:T.FIAMMETTA}))
  hooks.skip?.()
 }
 task.backupShiftActive=false
 if(getTime){
  const result=hooks.backup('BEFORE_PLANNING',task,{appendEmptyTask:true,restoreOnDeactivate:false});enqueueGenerated(queue,result.generated)
  if(!result.changed)hooks.metadata()
  else if(result.generated.length){
   if(!hooks.corrections)throw new Error('Mower backup after a downshift requires the correction adapter')
   const previous=new Set(queue.tasks),created=hooks.corrections();enqueueGenerated(queue,created)
   const corrections=queue.tasks.filter(t=>!previous.has(t)&&t.type===T.SELF_CORRECTION)
   const anchor=Math.min(...result.generated.map(t=>t.timeMicros))
   for(const [offset,correction] of corrections.entries())correction.timeMicros=anchor-offset-1
  }
 }
 queue.consume(task)
 // Ideal order wakes do not hide the first retained roster task.
 if(rosterHead(queue,hooks)?.type===T.SHIFT_ON){const result=hooks.backup('AFTER_PLANNING',task,{appendEmptyTask:true,restoreOnDeactivate:false});enqueueGenerated(queue,result.generated)}
 return true
 }catch(error){if(hooks.alpha&&error instanceof MowerRoomArrangementDeferred)retainedLock=true;throw error}
 finally{if(protectedShift&&!retainedLock)task.backupShiftActive=false}
}

/** Pure decision replay: the caller owns its clock and may drain all device boundaries. */
export function executeMowerTaskArrangement(task:MowerTask,queue:MowerTaskQueue,hooks:MowerTaskExecutionHooks):boolean {
 const steps=executeMowerTaskArrangementSteps(task,queue,hooks)
 let next=steps.next();while(!next.done)next=steps.next()
 return next.value
}
