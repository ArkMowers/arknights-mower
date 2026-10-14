// Mower b2d9ac8 scheduler_task.plan_metadata; recovery gap updated to ab0a4e5 (MIT, Copyright 2021 Nano).
import {hasObservedFullMood,hasRestingMood} from './mowerOperatorState'
import {projectMowerArrangements} from './mowerObservations'
import {alphaPosition,alphaRebalanceClosingDorms} from './mowerAlphaDorm'
import {generateMowerDormTasks,mergeMowerAlphaReleases,mowerArrangementResources,mowerAfterPendingArrangements,type MowerDormBatch,type MowerReturnTargets} from './mowerDormTasks'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros,type MowerTaskQueue,type MowerTaskPlan} from './mowerTaskQueue'
import type {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'

export function planMowerAlphaMetadata(actual:MowerSchedulingData,queue:MowerTaskQueue,limited:MowerTask[]):void {
 actual.refreshIdleDormSearch()
 const locked=queue.tasks.filter(t=>t.productShiftLocked),names=new Set(locked.flatMap(t=>[...t.productLockNames])),slots=new Set(locked.flatMap(t=>[...t.productLockSlots]))
 const groups=new Set([...names].map(n=>actual.operators[n]?.group??'').filter(Boolean)),existing:MowerReturnTargets={}
 if(actual.planConditions.some(Boolean))for(const task of queue.tasks)if(task.type===T.SHIFT_ON)for(const [room,row] of Object.entries(task.plan))row.forEach((name,index)=>{if(!['Current','Free',''].includes(name))existing[name]=[room,index]})
 queue.removeDerived(true)
 const reserved=new Set(queue.tasks.filter(t=>t.type!==T.FILL_DORM).flatMap(t=>[...mowerArrangementResources(t.plan).slots].filter(s=>s.startsWith('dorm'))))
 const vacancies=new Set(actual.dorms.filter(b=>!b.name&&!reserved.has(alphaPosition(...b.position))&&actual.effectiveFreeSlot(b)&&!actual.currentOperator(...b.position)).map(b=>alphaPosition(...b.position)))
 queue.tasks=queue.tasks.filter(t=>{if(t.type!==T.FILL_DORM||t.productShiftLocked||t.dormRecoveryRestore.length)return true;const resources=mowerArrangementResources(t.dormFillPlan&&Object.keys(t.dormFillPlan).length?t.dormFillPlan:t.plan);return resources.slots.size>0&&[...resources.slots].every(s=>vacancies.has(s))})
 const pending=queue.tasks.filter(t=>[T.SELF_CORRECTION,T.RE_ORDER].includes(t.type)&&!t.productShiftLocked&&Object.keys(t.plan).length).sort((a,b)=>a.timeMicros-b.timeMicros)
 const data=projectMowerArrangements(actual,pending.map(t=>t.plan)),now=data.nowMicros
 let minimum=Infinity
 for(const op of Object.values(data.operators))if(op.isHigh()&&!op.multiGroup&&(!op.group||data.isGroupShiftAnchor(op))&&!op.room.startsWith('dorm')&&!op.isResting()&&!data.isStandby(op.name))minimum=Math.min(minimum,Math.max(op.predictExhaust(now),now+toMowerMicros(.5)))
 const grouped=new Map<string,MowerDormState[]>(),free:MowerDormState[]=[]
 for(const bed of data.allDorms()){
  const op=data.operators[bed.name]
  if(!op||!data.groupDorms.includes(bed)&&!data.effectiveFreeSlot(bed)||names.has(op.name)||groups.has(op.group)||slots.has(alphaPosition(...bed.position)))continue
  if(!op.multiGroup&&(!op.group||data.isGroupShiftAnchor(op)))grouped.set(op.group,[...(grouped.get(op.group)??[]),bed])
  if(data.dorms.includes(bed)&&!op.restMoodLimit&&!data.skipIdleDormRelease(op.name))free.push(bed)
 }
 const batches=new Map<number,MowerDormBatch>(),releases=new Map<number,MowerDormBatch>()
 const add=(time:number,beds:MowerDormState[],full:boolean)=>{const previous=batches.get(time);if(previous){previous.dorms.push(...beds);previous.restInFull=!!(previous.restInFull||full)}else batches.set(time,{timeMicros:time,dorms:[...beds],restInFull:full})}
 for(const [group,beds] of grouped){
  const priority=beds.filter(b=>!data.operators[b.name]!.multiGroup&&data.operators[b.name]!.isHigh()&&data.operators[b.name]!.restingPriority==='high'),ordinary=beds.filter(b=>!data.operators[b.name]!.multiGroup&&data.operators[b.name]!.isHigh()&&data.operators[b.name]!.restingPriority!=='standby')
  const high=priority.length?priority:ordinary.length?ordinary:beds.filter(b=>!data.operators[b.name]!.multiGroup&&data.operators[b.name]!.isHigh()&&!(group&&data.canStandby(data.operators[b.name]!))),full=high.filter(b=>data.operators[b.name]!.restInFull)
  if(high.length&&group){
   let maximum:number|undefined,moodGap=false;const early=!data.operators[high[0]!.name]!.exhaustRequire
   const recoveryTimes=high.flatMap(b=>b.timeMicros===undefined?[]:[b.timeMicros])
   if(data.groupRestInFullOnMoodGap&&recoveryTimes.length>1&&!full.length){
    const latest=Math.max(...recoveryTimes),earliest=Math.min(...recoveryTimes)
    if(latest-earliest>toMowerMicros(data.groupMoodGapThresholdMinutes/60)){maximum=latest;moodGap=true}
   }
   if(full.length){const times=full.flatMap(b=>b.timeMicros===undefined?[]:[b.timeMicros]);maximum=times.length?Math.max(...times):undefined}
   const nearest=high.filter(b=>b.timeMicros!==undefined).sort((a,b)=>a.timeMicros!-b.timeMicros!)[0]
   let time:number
   if(maximum!==undefined){time=maximum-(early?toMowerMicros(.4*high.length/60):0);if(moodGap&&data.groupMoodGapMaxExtraWaitHours>0&&nearest){const normal=Math.min(nearest.timeMicros!,minimum);time=Math.max(normal,Math.min(time,normal+toMowerMicros(data.groupMoodGapMaxExtraWaitHours)))}}
   else if(nearest)time=Math.min(nearest.timeMicros!,minimum)
   else continue
   add(time,high,full.length>0)
  }
  if(high.length&&!group)for(const b of high)if(b.timeMicros!==undefined){const full=data.operators[b.name]!.restInFull;add(full?b.timeMicros:Math.min(b.timeMicros,minimum),[b],full)}
 }
 if(data.freeRoom)for(const b of free){const op=data.operators[b.name]!,observed=hasObservedFullMood(op);if(b.timeMicros===undefined&&!observed)continue;const time=observed?now:b.timeMicros!,previous=releases.get(time);if(previous)previous.dorms.push(b);else releases.set(time,{timeMicros:time,dorms:[b],restInFull:null})}
 const generated=generateMowerDormTasks([...batches.values(),...releases.values()],data,existing,pending);queue.tasks.push(...generated)
 const returning=new Set(generated.flatMap(t=>Object.values(t.plan).flat()))
 for(const op of Object.values(data.operators)){
  if(!op.isHigh()||op.multiGroup||op.room.startsWith('dorm')||op.currentRoom||op.group&&data.canStandby(op)||!data.restMoodComplete(op.name))continue
  const members=op.group?data.group(op.group):[op.name]
  if(groups.has(op.group)||members.some(n=>returning.has(n)||names.has(n)||data.busyRestingNames.has(n)))continue
  const workers=members.map(n=>data.operators[n]!).filter(o=>!o.room.startsWith('dorm')&&!o.workaholic&&!(o.group&&data.canStandby(o)))
  if(!workers.every(o=>!o.currentRoom&&(data.canStandby(o)||hasRestingMood(o,now)&&o.currentMood(now)>=o.upperLimit)))continue
  const plan:MowerTaskPlan={}
  for(const name of members){const member=data.operators[name]!;if(member.room&&data.plan[member.room]){const row=plan[member.room]??=Array(data.plan[member.room]!.length).fill('Current');if(['Current',name].includes(row[member.index]!))row[member.index]=name}}
  const recalled=alphaRebalanceClosingDorms(projectMowerArrangements(data,[]),plan,members),resources=mowerArrangementResources(plan)
  if([...recalled].some(n=>names.has(n)||data.busyRestingNames.has(n))||[...resources.slots].some(s=>slots.has(s)))continue
  const task=new MowerTask({type:T.SHIFT_ON,plan});task.timeMicros=Math.max(now,mowerAfterPendingArrangements(plan,pending));queue.tasks.push(task);[...members,...recalled].forEach(n=>returning.add(n))
 }
 queue.tasks.push(...limited);mergeMowerAlphaReleases(queue.tasks,data.mergeIntervalMinutes,{adjustForRunOrders:actual.adjustForRunOrders})
}
