import {mowerHeldRestGroups} from './mowerBackupGroupTasks'
import {planMowerPreferredReplacementRestore,mowerReplacementDependencyNames,mowerReplacementReservations} from './mowerReplacementCoordination'
import {mowerRestingBindingGroups,normalizeMowerSharedArrangement} from './mowerSharedGroups'
import {mowerGroupRecoveryDeadline} from './mowerGroupRecovery'
import {admitMowerDerivedTasks,type MowerDependencyReturnAdmission} from './mowerTaskDerivation'
// Mower b2d9ac8 scheduler_task.plan_metadata; recovery gap updated to ab0a4e5 (MIT, Copyright 2021 Nano).
import {hasObservedFullMood,hasRestingMood} from './mowerOperatorState'
import {projectMowerArrangements} from './mowerObservations'
import {alphaPosition,alphaRebalanceClosingDorms} from './mowerAlphaDorm'
import {generateMowerDormTasks,mergeMowerAlphaReleases,mowerArrangementResources,mowerAfterPendingArrangements,type MowerDormBatch,type MowerReturnTargets} from './mowerDormTasks'
import {MowerTask,MOWER_TASK_TYPES as T,type MowerTaskQueue,type MowerTaskPlan} from './mowerTaskQueue'
import type {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'

export function planMowerAlphaMetadata(actual:MowerSchedulingData,queue:MowerTaskQueue,limited:MowerTask[],dependencyReturn?:MowerDependencyReturnAdmission):void {
 for(const group of actual.groupMoodGapExclusions){delete actual.groupRecoveryFullMembers[group];delete actual.groupRecoveryReturnMicros[group]}
 actual.refreshIdleDormSearch()
 const locked=queue.tasks.filter(t=>t.productShiftLocked),names=new Set(locked.flatMap(t=>[...t.productLockNames])),slots=new Set(locked.flatMap(t=>[...t.productLockSlots]))
 const groups=new Set([...names].map(n=>actual.operators[n]?.group??'').filter(Boolean)),existing:MowerReturnTargets={}
 if(actual.planConditions.some(Boolean))for(const task of queue.tasks)if(task.type===T.SHIFT_ON)for(const [room,row] of Object.entries(task.plan))row.forEach((name,index)=>{if(!['Current','Free',''].includes(name))existing[name]=[room,index]})
 queue.removeDerived(true)
 const reserved=new Set(queue.tasks.filter(t=>t.type!==T.FILL_DORM).flatMap(t=>[...mowerArrangementResources(t.plan).slots].filter(s=>s.startsWith('dorm'))))
 const vacancies=new Set(actual.dorms.filter(b=>!b.name&&!reserved.has(alphaPosition(...b.position))&&actual.effectiveFreeSlot(b)&&!actual.currentOperator(...b.position)).map(b=>alphaPosition(...b.position)))
 queue.tasks=queue.tasks.filter(t=>{if(t.type!==T.FILL_DORM||t.productShiftLocked||t.dormRecoveryRestore.length)return true;const resources=mowerArrangementResources(t.dormFillPlan&&Object.keys(t.dormFillPlan).length?t.dormFillPlan:t.plan);return resources.slots.size>0&&[...resources.slots].every(s=>vacancies.has(s))})
 const pending=queue.tasks.filter(t=>[T.SELF_CORRECTION,T.RE_ORDER].includes(t.type)&&!t.executionFailure&&!t.productShiftLocked&&Object.keys(t.plan).length).sort((a,b)=>a.timeMicros-b.timeMicros)
 const data=projectMowerArrangements(actual,pending.map(t=>t.plan)),now=data.nowMicros

 const waitingForActualGroup=(name:string)=>{const op=actual.operators[name];return !!op?.independentRest&&mowerRestingBindingGroups(actual,op).length>0}
 const grouped=new Map<string,MowerDormState[]>(),free:MowerDormState[]=[]
 for(const bed of data.allDorms()){
  const op=data.operators[bed.name]
  if(!op||!data.groupDorms.includes(bed)&&!data.effectiveFreeSlot(bed)||names.has(op.name)||groups.has(op.group)||slots.has(alphaPosition(...bed.position)))continue
  if(!waitingForActualGroup(op.name)&&(!op.multiGroup||op.independentRest)&&(!op.group||data.isGroupShiftAnchor(op)||op.isHigh()&&!op.workaholic&&!op.room.startsWith('dorm')&&data.groupRecoveryFullMembers[op.group]?.includes(op.name)))grouped.set(op.group,[...(grouped.get(op.group)??[]),bed])
  if(data.dorms.includes(bed)&&!op.restMoodLimit&&!data.skipIdleDormRelease(op.name))free.push(bed)
 }
 const batches=new Map<number,MowerDormBatch>(),releases=new Map<number,MowerDormBatch>()
 const add=(time:number,beds:MowerDormState[],full:boolean)=>{const previous=batches.get(time);if(previous){previous.dorms.push(...beds);previous.restInFull=!!(previous.restInFull||full)}else batches.set(time,{timeMicros:time,dorms:[...beds],restInFull:full})}
 const held=mowerHeldRestGroups(data)
 for(const [group,beds] of grouped){
  if(held.has(group))continue
  const priority=beds.filter(b=>(!data.operators[b.name]!.multiGroup||data.operators[b.name]!.independentRest)&&data.operators[b.name]!.isHigh()&&data.operators[b.name]!.restingPriority==='high'),ordinary=beds.filter(b=>(!data.operators[b.name]!.multiGroup||data.operators[b.name]!.independentRest)&&data.operators[b.name]!.isHigh()&&data.operators[b.name]!.restingPriority!=='standby')
  const high=priority.length?priority:ordinary.length?ordinary:beds.filter(b=>(!data.operators[b.name]!.multiGroup||data.operators[b.name]!.independentRest)&&data.operators[b.name]!.isHigh()&&!(group&&data.canStandby(data.operators[b.name]!)))
  if(group){
   const recovery=mowerGroupRecoveryDeadline(data,group)
   if(data.groupRecoveryFullMembers[group]&&data.groupIsResting(group)&&actual.groupIsResting(group)){actual.groupRecoveryFullMembers[group]=[...data.groupRecoveryFullMembers[group]!];if(data.groupRecoveryReturnMicros[group]!==undefined)actual.groupRecoveryReturnMicros[group]=data.groupRecoveryReturnMicros[group]!}
   if(recovery.requiredNames.length||recovery.timeMicros!==undefined){
    if(recovery.timeMicros!==undefined)add(recovery.timeMicros,high.length?high:beds.filter(b=>data.operators[b.name]!.isHigh()),true)
    continue
   }
   const nearest=high.filter(b=>b.timeMicros!==undefined).sort((a,b)=>a.timeMicros!-b.timeMicros!)[0]
   if(nearest)add(nearest.timeMicros!,high,false)
  }
  if(high.length&&!group)for(const b of high)if(b.timeMicros!==undefined){const full=data.operators[b.name]!.restInFull;add(b.timeMicros,[b],full)}
 }
 if(data.freeRoom)for(const b of free){const op=data.operators[b.name]!,observed=hasObservedFullMood(op);if(b.timeMicros===undefined&&!observed)continue;const time=observed?now:b.timeMicros!,previous=releases.get(time);if(previous)previous.dorms.push(b);else releases.set(time,{timeMicros:time,dorms:[b],restInFull:null})}
 const generated=admitMowerDerivedTasks(actual,queue.tasks,generateMowerDormTasks([...batches.values(),...releases.values()],data,existing,pending),dependencyReturn);queue.tasks.push(...generated)
 const returning=new Set(generated.flatMap(t=>Object.values(t.plan).flat()))
 for(const op of Object.values(data.operators)){
  if(!op.isHigh()||held.has(op.group)||waitingForActualGroup(op.name)||op.multiGroup&&(!op.independentRest||mowerRestingBindingGroups(data,op).length)||op.room.startsWith('dorm')||op.currentRoom||op.group&&data.canStandby(op))continue
  const recovery=op.group?mowerGroupRecoveryDeadline(data,op.group):undefined
  const strict=!!recovery?.requiredNames.length||recovery?.timeMicros!==undefined
  const recoveredPrimaryGroup=!!op.group&&data.groupRestInFullOnMoodGap&&data.groupIsResting(op.group)&&hasObservedFullMood(op)&&!op.moodIsPrediction
  if(!(recoveredPrimaryGroup||data.restMoodComplete(op.name)||op.independentRest&&hasRestingMood(op,now)&&op.currentMood(now)>=op.upperLimit||strict&&hasObservedFullMood(op)))continue
  if(op.group&&data.groupRecoveryFullMembers[op.group]&&data.groupIsResting(op.group)&&actual.groupIsResting(op.group)){actual.groupRecoveryFullMembers[op.group]=[...data.groupRecoveryFullMembers[op.group]!];if(data.groupRecoveryReturnMicros[op.group]!==undefined)actual.groupRecoveryReturnMicros[op.group]=data.groupRecoveryReturnMicros[op.group]!}
  if(strict&&recovery!.timeMicros===undefined)continue
  const members=op.group?data.shiftGroupMembers(op.group).filter(name=>!data.operators[name]!.independentRest):[op.name]
  if(groups.has(op.group)||members.some(n=>returning.has(n)||names.has(n)||data.busyRestingNames.has(n)))continue
  const workers=members.map(n=>data.operators[n]!).filter(o=>!o.multiGroup&&!o.room.startsWith('dorm')&&!o.workaholic&&!(o.group&&data.canStandby(o)))
  if(!strict&&!workers.every(o=>!o.currentRoom&&(data.canStandby(o)||hasRestingMood(o,now)&&o.currentMood(now)>=o.upperLimit)))continue
  const plan:MowerTaskPlan={}
  for(const name of members){const member=data.operators[name]!;if(member.room&&data.plan[member.room]){const row=plan[member.room]??=Array(data.plan[member.room]!.length).fill('Current');if(['Current',name].includes(row[member.index]!))row[member.index]=name}}
  if(!normalizeMowerSharedArrangement(data,plan))continue
  const participants=members.filter(name=>Object.values(plan).some(row=>row.includes(name)))
  const recalled=alphaRebalanceClosingDorms(projectMowerArrangements(data,[]),plan,participants),resources=mowerArrangementResources(plan)
  if([...recalled].some(n=>names.has(n)||data.busyRestingNames.has(n))||[...resources.slots].some(s=>slots.has(s)))continue
  const task=new MowerTask({type:T.SHIFT_ON,plan});task.timeMicros=Math.max(recovery?.timeMicros??now,mowerAfterPendingArrangements(plan,pending));queue.tasks.push(...admitMowerDerivedTasks(actual,queue.tasks,[task],dependencyReturn));[...participants,...recalled].forEach(n=>returning.add(n))
 }
 // A due coordination intent owns its cover dependency until the physical handoff finishes.
 const coordinationReservations=mowerReplacementReservations(actual,queue.tasks)
 const protectedNames=new Set([...names,...coordinationReservations.reservedNames]),protectedSlots=new Set([...slots,...coordinationReservations.reservedSlots])
 for(const task of queue.tasks)if(task.timeMicros<=now&&![T.SHIFT_ON,T.RELEASE_DORM].includes(task.type)){
  const resources=mowerArrangementResources(task.plan)
  resources.names.forEach(name=>protectedNames.add(name));resources.slots.forEach(slot=>protectedSlots.add(slot))
  if(task.type===T.EXHAUST_OFF)mowerReplacementDependencyNames(data,task.metadata.split(',')).forEach(name=>protectedNames.add(name))
 }
 const restore=planMowerPreferredReplacementRestore(actual,protectedNames,protectedSlots)
 if(Object.keys(restore).length){const task=new MowerTask({type:T.SELF_CORRECTION,plan:restore});task.timeMicros=now;task.exhaustSupport=true;task.preferredReplacementRestore=true;queue.tasks.push(task)}
 queue.tasks.push(...admitMowerDerivedTasks(actual,queue.tasks,limited,dependencyReturn))
 const retained=queue.tasks.filter(task=>task.retainsExecution),active=queue.tasks.filter(task=>!task.retainsExecution)
 mergeMowerAlphaReleases(active,data.mergeIntervalMinutes,{adjustForRunOrders:actual.adjustForRunOrders});queue.tasks=[...active,...retained]
}
