import {restingThresholdFor} from './mowerOperatorState'
import {admitMowerDerivedTasks,type MowerDependencyReturnAdmission} from './mowerTaskDerivation'
// Port of default plan_metadata and plan_mood_limit_releases, Mower alpha.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {MOWER_TASK_TYPES as T,MowerTask,toMowerMicros,type MowerTaskQueue,type MowerTaskPlan} from './mowerTaskQueue'
import {hasRestingMood} from './mowerOperatorState'
import type {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {generateMowerDormTasks,type MowerDormBatch,type MowerReturnTargets} from './mowerDormTasks'
import {planMowerAlphaMetadata} from './mowerAlphaMetadata'

export const mowerRestUnitKey=(op:{group:string;name:string})=>op.group?'group:'+op.group:'operator:'+op.name
const recentlyReturned=(data:MowerSchedulingData,key:string)=>{
 const last=data.recentShiftOnByRestUnit.get(key)
 return last!==undefined&&data.nowMicros>=last&&data.nowMicros-last<=toMowerMicros(10/60)
}
/** The pinned Mower return rule can create a rapid ON/OFF cycle in the fast-I/O
 * simulator. Only after observing that cycle, postpone the next return until the
 * whole rest unit is above the downshift threshold. Normal returns keep source timing. */
function stableGroupReturnMicros(data:MowerSchedulingData,beds:MowerDormState[]):number {
 let ready=data.nowMicros
 for(const bed of beds){
  const op=data.operators[bed.name]
  if(!op?.isHigh()||op.workaholic||op.group&&data.canStandby(op)||op.exhaustRequire||['dorm','factory','train'].some(room=>op.room.startsWith(room)))continue
  const mood=op.currentMood(data.nowMicros)
  const threshold=op.restMoodLimit?op.upperLimit:Math.min(op.upperLimit,Math.floor((op.upperLimit-op.lowerLimit)*restingThresholdFor(op,data.policy)+op.lowerLimit)+.125)
  if(mood>=threshold)continue
  if(bed.timeMicros===undefined||bed.timeMicros<=data.nowMicros||mood>=op.upperLimit){ready=Math.max(ready,data.nowMicros+toMowerMicros(.5));continue}
  const fraction=(threshold-mood)/(op.upperLimit-mood)
  ready=Math.max(ready,data.nowMicros+Math.ceil((bed.timeMicros-data.nowMicros)*fraction))
 }
 return ready
}
export function planMowerMoodLimitReleases(data:MowerSchedulingData,previousTasks:MowerTask[]=[]):MowerTask[] {
 const result:MowerTask[]=[]
 for(const bed of data.dorms){
  const op=data.operators[bed.name];if(!op?.restMoodLimit||data.freeRoomExcluded(op.name))continue
  const [room,index]=bed.position;if(op.currentRoom!==room||op.currentIndex!==index||!data.recoveryDorm(bed,op.name))continue
  const due=data.restMoodComplete(op.name)?data.nowMicros:bed.timeMicros===undefined?undefined:Math.max(data.nowMicros,bed.timeMicros);if(due===undefined)continue
  const names=Array(data.plan[room]!.length).fill('Current');names[index]='Free'
  const task=new MowerTask({plan:{[room]:names},type:T.RELEASE_DORM,metadata:op.name,strictMoodLimit:true,moodLimit:op.upperLimit});task.timeMicros=due
  task.moodLimitSource=JSON.stringify([bed.timeMicros,op.upperLimit,data.restMoodComplete(op.name)])
  const previous=previousTasks.find(old=>old.strictMoodLimit&&old.metadata===op.name&&old.moodLimitSource===task.moodLimitSource&&JSON.stringify(old.plan)===JSON.stringify(task.plan))
  result.push(previous??task)
 }
 return result
}
export function planMowerMetadata(data:MowerSchedulingData,queue:MowerTaskQueue,dependencyReturn?:MowerDependencyReturnAdmission):void {
 for(const task of [...queue.tasks])if(task.type===T.RELEASE_DORM){
  for(const name of Object.keys(task.releaseDormTargets()))if(data.freeRoomExcluded(name))task.removeReleaseDormOperator(name)
  if(!Object.keys(task.plan).length)queue.consume(task)
 }
 if(queue.tasks.some(task=>task.backupShiftActive))return
 if(data.alpha){planMowerAlphaMetadata(data,queue,planMowerMoodLimitReleases(data,queue.tasks),dependencyReturn);return}
 if(data.policy.experimentalDormLogic)throw new Error('Experimental product locks and dorm projection require their source port')
 const existingTargets:MowerReturnTargets={}
 if(data.planConditions.some(Boolean))for(const task of queue.tasks)if(task.type===T.SHIFT_ON)for(const [room,names] of Object.entries(task.plan))for(const [index,name] of names.entries())if(!['Current','Free',''].includes(name))existingTargets[name]=[room,index]
 queue.removeDerived()
 const limited=planMowerMoodLimitReleases(data),now=data.nowMicros
 let minimumRest=Infinity
 const agents=Object.values(data.operators).filter(op=>op.isHigh()&&!op.room.startsWith('dorm')&&!op.isResting()&&!(op.group&&data.canStandby(op))&&!data.isStandby(op.name)).sort((a,b)=>(a.currentMood(now)-a.lowerLimit)-(b.currentMood(now)-b.lowerLimit))
 for(const agent of agents)minimumRest=Math.min(minimumRest,Math.max(agent.predictExhaust(now),now+toMowerMicros(.5)))
 const grouped=new Map<string,MowerDormState[]>(),freeRooms:MowerDormState[]=[]
 for(const bed of data.dorms){
  if(!data.effectiveFreeSlot(bed))continue
  const op=data.operators[bed.name];if(!bed.name||!op)continue
  grouped.set(op.group,[...(grouped.get(op.group)??[]),bed])
  if(!op.isHigh()&&!op.restMoodLimit&&!data.skipIdleDormRelease(op.name))freeRooms.push(bed)
 }
 const newTasks=new Map<number,MowerDormBatch>()
 const add=(timeMicros:number,dorms:MowerDormState[],restInFull:boolean)=>{const previous=newTasks.get(timeMicros);if(previous){previous.dorms.push(...dorms);previous.restInFull=!!(previous.restInFull||restInFull)}else newTasks.set(timeMicros,{timeMicros,dorms:[...dorms],restInFull})}
 for(const [group,dorms] of grouped){
  const highPriority=dorms.filter(b=>data.operators[b.name]!.isHigh()&&data.operators[b.name]!.restingPriority==='high')
  const ordinary=dorms.filter(b=>data.operators[b.name]!.isHigh()&&data.operators[b.name]!.restingPriority!=='standby')
  const high=highPriority.length?highPriority:ordinary.length?ordinary:dorms.filter(b=>data.operators[b.name]!.isHigh()&&!(group&&data.canStandby(data.operators[b.name]!)))
  const full=high.filter(b=>data.operators[b.name]!.restInFull)
  if(high.length&&group){
   const baseTime=high[0]!.timeMicros,needEarly=!data.operators[high[0]!.name]!.exhaustRequire
   let maximumFull:number|undefined,moodGap=false
   if(data.groupRestInFullOnMoodGap&&!data.groupMoodGapExclusions.includes(group)&&baseTime!==undefined&&!full.length)for(const bed of high.slice(1))if(bed.timeMicros!==undefined&&baseTime-bed.timeMicros>toMowerMicros(data.powerPlantCount===2?1.5:1)){maximumFull=baseTime;moodGap=true}
   if(full.length){const times=full.flatMap(b=>b.timeMicros===undefined?[]:[b.timeMicros]);maximumFull=times.length?Math.max(...times):undefined}
   const known=high.filter(b=>b.timeMicros!==undefined).sort((a,b)=>a.timeMicros!-b.timeMicros!),nearest=known[0]
   let time:number
   if(maximumFull!==undefined){
    time=maximumFull-(needEarly?toMowerMicros(.4*high.length/60):0)
    if(moodGap&&data.groupMoodGapMaxExtraWaitHours>0&&nearest){const normal=Math.min(nearest.timeMicros!,minimumRest);time=Math.max(normal,Math.min(time,normal+toMowerMicros(data.groupMoodGapMaxExtraWaitHours)))}
   }else if(nearest)time=Math.min(nearest.timeMicros!,minimumRest)
   else continue
   if(recentlyReturned(data,'group:'+group)){
    // generateMowerDormTasks starts ordinary returns eight minutes before time.
    const stable=stableGroupReturnMicros(data,dorms)
    if(stable>data.nowMicros)time=Math.max(time,stable+toMowerMicros(8/60))
   }
   add(time,high,full.length>0)
  }
  if(high.length&&!group)for(const bed of high)if(bed.timeMicros!==undefined&&bed.name){
   const full=data.operators[bed.name]!.restInFull
   let time=full?bed.timeMicros:Math.min(bed.timeMicros,minimumRest)
   if(recentlyReturned(data,'operator:'+bed.name)){
    const stable=stableGroupReturnMicros(data,[bed])
    if(stable>data.nowMicros)time=Math.max(time,stable+toMowerMicros(8/60))
   }
   add(time,[bed],full)
  }
 }
 const releases=new Map<number,MowerDormBatch>()
 if(data.freeRoom)for(const bed of freeRooms){
  if(minimumRest!==Infinity)minimumRest+=toMowerMicros(10/3600)
  if(bed.timeMicros===undefined||!bed.name)continue
  const time=Math.min(bed.timeMicros,minimumRest);if(time<now)continue
  const previous=releases.get(time);if(previous)previous.dorms.push(bed);else releases.set(time,{timeMicros:time,dorms:[bed],restInFull:null})
 }
 const generated=admitMowerDerivedTasks(data,queue.tasks,generateMowerDormTasks([...newTasks.values(),...releases.values()],data,existingTargets),dependencyReturn);queue.tasks.push(...generated)
 const returning=new Set(generated.flatMap(t=>Object.values(t.plan).flat())),busy=data.busyRestingNames
 for(const op of Object.values(data.operators)){
  if(!op.isHigh()||op.room.startsWith('dorm')||op.currentRoom||op.group&&data.canStandby(op)||!data.restMoodComplete(op.name))continue
  const members=op.group?data.group(op.group):[op.name]
  if(members.some(name=>returning.has(name)||busy.has(name)))continue
  const workers=members.map(name=>data.operators[name]!).filter(worker=>!worker.room.startsWith('dorm')&&!worker.workaholic&&!(worker.group&&data.canStandby(worker)))
  if(!workers.every(worker=>!worker.currentRoom&&(data.canStandby(worker)||hasRestingMood(worker,now)&&worker.currentMood(now)>=worker.upperLimit)))continue
  const plan:MowerTaskPlan={}
  for(const name of members){const member=data.operators[name]!;if(!member.room||!data.plan[member.room])continue;const slots=plan[member.room]??=Array(data.plan[member.room]!.length).fill('Current');if(['Current',name].includes(slots[member.index]!))slots[member.index]=name}
  const task=new MowerTask({type:T.SHIFT_ON,plan});task.timeMicros=now;queue.tasks.push(...admitMowerDerivedTasks(data,queue.tasks,[task],dependencyReturn));members.forEach(name=>returning.add(name))
 }
 queue.tasks.push(...admitMowerDerivedTasks(data,queue.tasks,limited,dependencyReturn))
}
