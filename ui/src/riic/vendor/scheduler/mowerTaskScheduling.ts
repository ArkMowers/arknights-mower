// Port of scheduler_task.scheduling and its queue helpers.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {MOWER_TASK_TYPES as T,toMowerMicros,isMowerRunOrderTask,type MowerTask} from './mowerTaskQueue'
import {mergeMowerAlphaReleases} from './mowerDormTasks'
import {alphaSupportSwapMicros,protectMowerAlphaTasks,sortMowerAlphaDispatch} from './mowerAlphaTaskProtection'
import {advanceMowerMaintenanceOrders} from './mowerMaintenanceScheduling'
export interface MowerTaskSchedulingOptions {
 /** Ideal orders share the production clock without reserving roster execution time. */
 adjustForRunOrders?:boolean
 runOrderDelayMinutes?:number;executionMinutes?:number;configuredDelayMinutes?:number
 enableMastery?:boolean;experimental?:boolean
 alpha?:boolean;mergeIntervalMinutes?:number
 maintenance?:[startMicros:number,endMicros:number];dormDurations?:Record<string,number[]>
 /** Explicit first daily reset on the simulation clock; no daily window exists when omitted. */
 firstDailyResetMicros?:number
 /** Full announcement end for alpha support swaps; maintenance keeps its run-order window semantics. */
 maintenanceEndMicros?:number
}
const minutes=(value:number)=>toMowerMicros(value/60)
const sort=(tasks:MowerTask[])=>tasks.sort((a,b)=>a.timeMicros-b.timeMicros)
function ordinaryMinutes(task:MowerTask,execution:number):number {
 if(task.type===T.FURNITURE)return 31
 let time=Math.max(1,Object.keys(task.plan).length*execution)
 if([T.FIAMMETTA,T.CLUE_PARTY].includes(task.type))time=Math.max(time,3)
 return task.type===T.SHIFT_OFF?time*2:time
}
function estimateDorm(room:string,execution:number,options:MowerTaskSchedulingOptions):number {
 return Math.max(90,execution*60,Math.max(0,...(options.dormDurations?.[room]??[]).slice(-8))*1.2+15)/60
}
function adjustMaintenance(tasks:MowerTask[],delay:number,window:MowerTaskSchedulingOptions['maintenance']):void {
 if(!window)return
 const gap=minutes(Math.max(delay*2,10)),start=window[0]-gap,end=window[1]+gap
 const near=tasks.filter(task=>task.type===T.RUN_ORDER&&start<task.timeMicros&&task.timeMicros<end)
 sort(near)
 near.forEach((task,index)=>{task.timeMicros=start-(index+1)*1_000_000;task.adjusted=true})
}
function mergeDeferredDormSchedules(tasks:MowerTask[]):MowerTask[] {
 const mergeable=tasks.filter(task=>[T.SHIFT_OFF,T.SHIFT_ON,T.RE_ORDER].includes(task.type))
 const dormTasks=mergeable.filter(task=>Object.keys(task.plan).some(room=>room.startsWith('dormitory_')))
 if(dormTasks.length<2&&!dormTasks.some(task=>task.type===T.SHIFT_OFF))return tasks
 const merged:Record<string,string[]>={}
 const removeFromDorm=(name:string)=>{
  if(['','Current','Free'].includes(name))return
  for(const names of Object.values(merged))for(let index=0;index<names.length;index++)if(names[index]===name)names[index]='Free'
 }
 for(const task of mergeable){
  for(const [room,names] of Object.entries(task.plan))if(!room.startsWith('dormitory_'))names.forEach(removeFromDorm)
  for(const [room,names] of Object.entries(task.plan)){
   if(!room.startsWith('dormitory_'))continue
   const target=merged[room]??=Array(names.length).fill('Current')
   while(target.length<names.length)target.push('Current')
   for(const [index,name] of names.entries()){
    if(name==='Current')continue
    removeFromDorm(name);target[index]=name
   }
  }
 }
 const anchor=dormTasks.find(task=>task.type===T.SHIFT_OFF)??dormTasks[dormTasks.length-1]!
 const dormSet=new Set(dormTasks)
 for(const task of dormTasks)for(const room of Object.keys(task.plan))if(room.startsWith('dormitory_'))delete task.plan[room]
 Object.assign(anchor.plan,merged)
 const removed=new Set(dormTasks.filter(task=>task!==anchor&&task.type!==T.SHIFT_OFF&&!Object.keys(task.plan).length))
 const redundant=new Set<MowerTask>()
 for(let index=0;index<tasks.length-1;index++){
  const task=tasks[index]!,next=tasks[index+1]!
  if(removed.has(task)&&task.type===T.RE_ORDER&&!dormSet.has(next)&&next.type===T.NOT_SPECIFIC&&!Object.keys(next.plan).length&&next.timeMicros===task.timeMicros)redundant.add(next)
 }
 return tasks.filter(task=>!removed.has(task)&&!redundant.has(task))
}
function scheduleOrders(tasks:MowerTask[],now:number,delay:number,execution:number,options:MowerTaskSchedulingOptions):[MowerTask,MowerTask]|undefined {
 if(!tasks.length)return
 if(options.alpha)advanceMowerMaintenanceOrders(tasks,now,{...options,runOrderDelayMinutes:delay})
 else adjustMaintenance(tasks,delay,options.maintenance)
 sort(tasks)
 let previous:MowerTask|undefined,totalExecution=0
 for(let index=0;index<tasks.length;index++){
  const task=tasks[index]!
  if(task.type.priority===1&&now>task.timeMicros)totalExecution+=(now-task.timeMicros)/60_000_000
  if(task.type.priority===1){
   if(!options.alpha&&previous&&task.timeMicros-previous.timeMicros<minutes(delay)&&now<previous.timeMicros&&!task.adjusted)return [previous,task]
   previous=task;totalExecution=0
  }else{
   let nextIndex=-1
   for(let next=index+1;next<tasks.length;next++)if(tasks[next]!.type.priority===1){nextIndex=next;break}
   if(nextIndex<0)continue
   for(let pending=index;pending<nextIndex;pending++){
    const item=tasks[pending]!,rooms=Object.keys(item.plan)
    const fixedTime=rooms.length&&![T.FIAMMETTA,T.CLUE_PARTY].includes(item.type)?0:[T.FIAMMETTA,T.CLUE_PARTY].includes(item.type)?3:1
    let estimate=fixedTime===0?rooms.length*execution:fixedTime
    if(options.experimental&&fixedTime===0)estimate=rooms.reduce((sum,room)=>sum+(room.startsWith('dormitory_')?estimateDorm(room,execution,options):execution),0)
    if(item.type===T.FURNITURE)estimate=ordinaryMinutes(item,execution)
    if(now+minutes(totalExecution+estimate)<item.timeMicros)totalExecution=0
    else totalExecution+=estimate
   }
   const order=tasks[nextIndex]!
   if(now+minutes(totalExecution)>order.timeMicros){
    if(order.timeMicros-now>minutes(10))break
    let nextTime=order.timeMicros,pending=tasks.slice(index,nextIndex)
    if(options.experimental)pending=mergeDeferredDormSchedules(pending)
    tasks.splice(index,nextIndex-index,...pending)
    for(const item of pending){
     if(item.adjusted)continue
     item.timeMicros=nextTime+1_000_000;nextTime=item.timeMicros
    }
    break
   }
  }
 }
 sort(tasks)
}
function protectSwaps(tasks:MowerTask[],now:number,delay:number,execution:number,configuredDelay:number,adjustForRunOrders=true):[MowerTask,MowerTask]|undefined {
 const swaps=sort(tasks.filter(task=>task.type===T.SWAP_SUPPORT)),gap=minutes(Math.max(10,delay*2,configuredDelay*2))
 let conflict:[MowerTask,MowerTask]|undefined
 for(const swap of swaps){
  let orderConflict:[MowerTask,MowerTask]|undefined
  for(const task of tasks){
   if(!adjustForRunOrders||task.type!==T.RUN_ORDER||!task.metadata||Math.max(now,task.timeMicros)+gap<=swap.timeMicros||task.timeMicros>swap.timeMicros+gap)continue
   if(now+gap<swap.timeMicros)orderConflict??=[task,swap]
   else task.timeMicros=Math.max(now,swap.timeMicros)+gap+1_000_000
  }
  conflict??=orderConflict
  let cursor=now
  for(const task of sort([...tasks])){
   if([T.SWAP_SUPPORT,T.RUN_ORDER].includes(task.type)||!adjustForRunOrders&&isMowerRunOrderTask(task)||task.strictMoodLimit||task.timeMicros>swap.timeMicros)continue
   const finish=Math.max(cursor,task.timeMicros)+minutes(ordinaryMinutes(task,execution))
   if(finish>=swap.timeMicros-minutes(1))task.timeMicros=Math.max(now,swap.timeMicros)+minutes(3)
   else cursor=finish
  }
 }
 sort(tasks);return conflict
}
export function protectMowerSupportSwaps(tasks:MowerTask[],nowMicros:number,options:MowerTaskSchedulingOptions={}):[MowerTask,MowerTask]|undefined {
 if(options.alpha)return
 if(options.enableMastery===false)return
 return protectSwaps(tasks,nowMicros,options.runOrderDelayMinutes??5,options.executionMinutes??.75,options.configuredDelayMinutes??3,options.adjustForRunOrders!==false)
}
/** All mutations retain native task identities; I/O timings and maintenance are explicit inputs. */
export function scheduleMowerTasks(tasks:MowerTask[],nowMicros:number,options:MowerTaskSchedulingOptions={}):[MowerTask,MowerTask]|undefined {
 const delay=options.runOrderDelayMinutes??5,execution=options.executionMinutes??.75,enabled=options.enableMastery??true,configuredDelay=options.configuredDelayMinutes??3
 if(options.alpha){
  mergeMowerAlphaReleases(tasks,options.mergeIntervalMinutes??10,options)
  const fixed=new Set(tasks.filter(t=>t.strictMoodLimit||t.type===T.FILL_DORM||enabled&&t.type===T.SWAP_SUPPORT)),ordinary=fixed.size?tasks.filter(t=>!fixed.has(t)):tasks
  const conflict=options.adjustForRunOrders===false?undefined:scheduleOrders(ordinary,nowMicros,delay,execution,{...options,experimental:true})
  if(fixed.size){const retained=new Set(ordinary);tasks.splice(0,tasks.length,...tasks.filter(t=>fixed.has(t)||retained.has(t)))}
  protectMowerAlphaTasks(tasks,nowMicros,options)
  if(enabled&&tasks.some(t=>t.type===T.SWAP_SUPPORT&&t.timeMicros<=nowMicros+alphaSupportSwapMicros(t,options)+minutes(1)))return
  sortMowerAlphaDispatch(tasks,nowMicros,options);return conflict
 }
 const fixed=new Set(tasks.filter(task=>task.strictMoodLimit||options.experimental&&task.type===T.FILL_DORM||enabled&&task.type===T.SWAP_SUPPORT))
 const ordinary=fixed.size?tasks.filter(task=>!fixed.has(task)):tasks
 const conflict=options.adjustForRunOrders===false?undefined:scheduleOrders(ordinary,nowMicros,delay,execution,options)
 if(fixed.size&&options.experimental){const retained=new Set(ordinary);tasks.splice(0,tasks.length,...tasks.filter(task=>fixed.has(task)||retained.has(task)))}
 if(enabled){
  const swapConflict=protectSwaps(tasks,nowMicros,delay,execution,configuredDelay,options.adjustForRunOrders!==false)
  if(swapConflict)return swapConflict
  if(tasks.some(task=>task.type===T.SWAP_SUPPORT&&task.timeMicros<=nowMicros+minutes(Math.max(10,delay*2,configuredDelay*2))))return
 }
 sort(tasks);return conflict
}
