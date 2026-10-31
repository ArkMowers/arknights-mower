// Mower b2d9ac8 scheduler_task priority protection (MIT).
import {MOWER_TASK_TYPES as T,toMowerMicros,isMowerRunOrderTask,type MowerTask} from './mowerTaskQueue'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'
import {advanceMowerMaintenanceSwaps} from './mowerMaintenanceScheduling'
const minutes=(n:number)=>toMowerMicros(n/60)
export function alphaDormMinutes(room:string,options:MowerTaskSchedulingOptions={},fallback=.75):number {
 return Math.max(90,fallback*60,Math.max(0,...(options.dormDurations?.[room]??[]).slice(-8))*1.2+15)/60
}
const ordinaryMinutes=(task:MowerTask,execution=.75)=>task.type===T.FURNITURE?31:(task.type===T.SHIFT_OFF?2:1)*Math.max(1,Object.keys(task.plan).length*execution,[T.FIAMMETTA,T.CLUE_PARTY].includes(task.type)?3:0)
export function alphaSupportSwapMicros(task:MowerTask,options:MowerTaskSchedulingOptions={}):number {
 const execution=options.executionMinutes??.75
 return minutes(Math.max(ordinaryMinutes(task,execution),Object.keys(task.plan).reduce((sum,room)=>sum+(room.startsWith('dormitory_')?alphaDormMinutes(room,options,execution):execution),0)))
}
const dormOnly=(task:MowerTask)=>[T.SHIFT_OFF,T.SHIFT_ON,T.RE_ORDER,T.RELEASE_DORM,T.FILL_DORM,T.NOT_SPECIFIC].includes(task.type)&&Object.keys(task.plan).length>0&&Object.keys(task.plan).every(room=>room.startsWith('dormitory_'))
const priority=(tasks:MowerTask[],options:MowerTaskSchedulingOptions)=>tasks.filter(t=>options.adjustForRunOrders!==false&&t.type===T.RUN_ORDER||options.enableMastery!==false&&t.type===T.SWAP_SUPPORT).sort((a,b)=>a.timeMicros-b.timeMicros)
export function simplifyMowerAlphaDormFill(task:MowerTask,tasks:MowerTask[],now:number,options:MowerTaskSchedulingOptions={}):void {
 if(task.type!==T.FILL_DORM||task.simpleDormFill||task.dormRecoveryRestore.length)return
 const end=now+minutes(Math.max(10,(options.configuredDelayMinutes??3)*2))
 if(!priority(tasks,options).some(t=>t.timeMicros<=end&&(task.timeMicros<=now||task.timeMicros<=t.timeMicros)))return
 const original=Object.keys(task.dormFillPlan).length?task.dormFillPlan:task.plan
 task.plan=Object.fromEntries(Object.entries(original).filter(([room])=>room in task.plan).map(([room,row])=>[room,[...row]]));task.simpleDormFill=true
}
function dormDeadline(task:MowerTask,tasks:MowerTask[],start:number,duration:number,now:number,options:MowerTaskSchedulingOptions):MowerTask|undefined {
 if(!dormOnly(task)||task.strictMoodLimit||task.dormRecoveryRestore.length)return
 const finish=start+minutes(duration+1)
 return priority(tasks,options).find(t=>(task.timeMicros<=now||task.timeMicros<=t.timeMicros)&&finish>=t.timeMicros)
}
export function deferMowerAlphaDorm(task:MowerTask,tasks:MowerTask[],room:string,now:number,options:MowerTaskSchedulingOptions={}):boolean {
 if(!room.startsWith('dormitory_'))return false
 const deadline=dormDeadline(task,tasks,now,alphaDormMinutes(room,options),now,options)
 if(!deadline)return false
 task.timeMicros=Math.max(now,deadline.timeMicros)+1_000_000;tasks.sort((a,b)=>a.timeMicros-b.timeMicros);return true
}
export function sortMowerAlphaDispatch(tasks:MowerTask[],now:number,options:MowerTaskSchedulingOptions={}):void {
 const due=new Set(priority(tasks,options).filter(t=>t.timeMicros<=now))
 const advance=(t:MowerTask)=>options.enableMastery!==false&&t.type===T.SWAP_SUPPORT&&t.advanceSupportSwap&&t.timeMicros<=now
 tasks.sort((a,b)=>Number(!due.has(a))-Number(!due.has(b))||Number(!advance(a))-Number(!advance(b))||a.timeMicros-b.timeMicros)
}
export function protectMowerAlphaTasks(tasks:MowerTask[],now:number,options:MowerTaskSchedulingOptions={}):void {
 const execution=options.executionMinutes??.75,configured=options.configuredDelayMinutes??3
 tasks.forEach(t=>simplifyMowerAlphaDormFill(t,tasks,now,options))
 const swaps=tasks.filter(t=>options.enableMastery!==false&&t.type===T.SWAP_SUPPORT).sort((a,b)=>a.timeMicros-b.timeMicros)
 advanceMowerMaintenanceSwaps(swaps,now,options,task=>alphaSupportSwapMicros(task,options))
 for(const swap of swaps){
  const duration=alphaSupportSwapMicros(swap,options)
  for(const order of tasks.filter(t=>options.adjustForRunOrders!==false&&t.type===T.RUN_ORDER&&t.metadata).sort((a,b)=>b.timeMicros-a.timeMicros)){
   const start=Math.max(now,order.timeMicros),finish=Math.max(start,order.timeMicros+minutes(configured))+minutes(2*execution)
   if(finish<=swap.timeMicros||start>=Math.max(now,swap.timeMicros)+duration)continue
   if(swap.timeMicros>now)swap.timeMicros=Math.max(now,order.timeMicros-duration-1_000_000)
   swap.advanceSupportSwap=true
  }
  let cursor=now
  for(const task of [...tasks].sort((a,b)=>a.timeMicros-b.timeMicros)){
   if([T.SWAP_SUPPORT,T.RUN_ORDER].includes(task.type)||options.adjustForRunOrders===false&&isMowerRunOrderTask(task)||task.strictMoodLimit||task.timeMicros>swap.timeMicros)continue
   const start=Math.max(cursor,task.timeMicros)
   if(dormOnly(task)){
    const duration=Object.keys(task.plan).reduce((sum,room)=>sum+alphaDormMinutes(room,options),0)
    if(dormDeadline(task,[swap],start,duration,now,options))task.timeMicros=Math.max(now,swap.timeMicros)+1_000_000
    else cursor=start+minutes(duration)
   }else{
    const finish=start+minutes(ordinaryMinutes(task,execution))
    if(finish>=swap.timeMicros-minutes(1))task.timeMicros=Math.max(now,swap.timeMicros)+minutes(3)
    else cursor=finish
   }
  }
 }
 let cursor=now
 for(const task of [...tasks].sort((a,b)=>a.timeMicros-b.timeMicros)){
  if([T.RUN_ORDER,T.SWAP_SUPPORT].includes(task.type)||options.adjustForRunOrders===false&&isMowerRunOrderTask(task))continue
  const start=Math.max(cursor,task.timeMicros),duration=dormOnly(task)?Object.keys(task.plan).reduce((sum,room)=>sum+alphaDormMinutes(room,options),0):ordinaryMinutes(task,execution),deadline=dormDeadline(task,tasks,start,duration,now,options)
  if(deadline)task.timeMicros=Math.max(now,deadline.timeMicros)+1_000_000
  else cursor=start+minutes(duration)
 }
 const blockers=tasks.filter(t=>!t.strictMoodLimit&&(options.adjustForRunOrders!==false||!isMowerRunOrderTask(t))&&(t.type!==T.SWAP_SUPPORT||options.enableMastery!==false)).sort((a,b)=>b.timeMicros-a.timeMicros)
 const releases=tasks.filter(t=>t.strictMoodLimit&&Object.keys(t.plan).length).sort((a,b)=>(b.moodLimitDeadlineMicros??b.timeMicros)-(a.moodLimitDeadlineMicros??a.timeMicros)||b.metadata.localeCompare(a.metadata)||JSON.stringify(Object.keys(b.plan).sort()).localeCompare(JSON.stringify(Object.keys(a.plan).sort())))
 let next=Infinity
 for(const release of releases){
  release.moodLimitDeadlineMicros??=release.timeMicros
  const duration=minutes(Object.keys(release.plan).reduce((sum,room)=>sum+alphaDormMinutes(room,options),0))
  let start=Math.min(release.timeMicros,Math.min(release.moodLimitDeadlineMicros,next)-duration)
  for(const task of blockers){
   if([T.RUN_ORDER,T.SWAP_SUPPORT].includes(task.type)&&task.timeMicros<=now)continue
   const durationMinutes=task.type===T.RUN_ORDER?Math.max(options.runOrderDelayMinutes??5,configured)+2*execution:task.type===T.SWAP_SUPPORT?ordinaryMinutes(task,execution):dormOnly(task)?Object.keys(task.plan).reduce((sum,room)=>sum+alphaDormMinutes(room,options),0):ordinaryMinutes(task,execution)
   const end=Math.max(now,task.timeMicros)+minutes(durationMinutes)
   if(start<=end&&Math.max(now,start)+duration>=task.timeMicros)start=Math.min(start,task.timeMicros-duration-1_000_000)
  }
  if(start<release.timeMicros)release.timeMicros=start
  next=start
 }
 sortMowerAlphaDispatch(tasks,now,options)
}
