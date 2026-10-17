import {completeMowerBackupDepartureRecovery} from './mowerBackupDepartureRecovery'
import {mowerExhaustGroups} from './mowerExhaustPolicy'
import {planMowerDormIsolation} from './mowerDormIsolation'
import {inheritMowerBackupRefreshRules} from './mowerBackupRefresh'
import {normalizeMowerSharedArrangement,mowerArrangementGroupTransitions,commitMowerGroupShifts} from './mowerSharedGroups'
// Complete in-memory arrangement replay, Mower alpha b2d9ac8 (MIT).
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MowerShiftPreviewError} from './mowerNativeErrors'
import {simplifyMowerAlphaDormFill} from './mowerAlphaTaskProtection'
import {mowerAlphaFillPlan,mowerDormTaskReservations} from './mowerAlphaCandidates'
export {mowerAlphaFillPlan} from './mowerAlphaCandidates'
import {projectMowerArrangements} from './mowerObservations'
import {mowerResting,mowerTryReorder,type MowerRestingOptions} from './mowerOrdinaryPlanning'
import {mowerCorrectionPlan} from './mowerCorrection'
import {alphaPosition} from './mowerAlphaDorm'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros,type MowerTaskPlan} from './mowerTaskQueue'

export interface MowerShiftModel {
 count:number
 observationNames?:readonly string[]
 conditionObservationNames?:readonly (readonly string[])[]
 explicitTasks?:readonly MowerTaskPlan[]
 explicitSlots?(original:boolean[],conditions:boolean[]):ReadonlySet<string>
 /** Recovery retries retain discrete observation for time-dependent conditions. */
 nextConditionWakeMicros?(data:MowerSchedulingData):number|undefined
 nextIdleConditionWakeMicros?(data:MowerSchedulingData):number|undefined
 evaluate(data:MowerSchedulingData):boolean[]
 swap(data:MowerSchedulingData,conditions:boolean[]):MowerSchedulingData
 transition(previous:MowerSchedulingData,next:MowerSchedulingData,original:boolean[],conditions:boolean[],previousRecovery?:MowerSchedulingData,pendingTasks?:MowerTask[]):MowerTaskPlan
 activate(conditions:boolean[],task?:MowerTask):void
}
const same=(a:boolean[],b:boolean[])=>a.length===b.length&&a.every((v,i)=>v===b[i])
export function mergeMowerPlanOverlay(target:MowerTaskPlan,overlay:MowerTaskPlan,data:MowerSchedulingData):void{
 for(const [room,names] of Object.entries(overlay)){
  const slots=data.plan[room];if(!slots)continue
  const row=target[room]??=Array(slots.length).fill('Current')
  names.slice(0,slots.length).forEach((name,index)=>{if(name!=='Current')row[index]=name})
 }
}
export function mergeMowerShiftTransition(target:MowerTaskPlan,overlay:MowerTaskPlan,data:MowerSchedulingData):void{
 const destinations=new Map<string,string>()
 for(const [room,names] of Object.entries(overlay))names.forEach((name,index)=>{if(!['Current','Free',''].includes(name))destinations.set(name,alphaPosition(room,index))})
 for(const [room,names] of Object.entries(target))names.forEach((name,index)=>{const destination=destinations.get(name);if(destination!==undefined&&destination!==alphaPosition(room,index))names[index]='Current'})
 mergeMowerPlanOverlay(target,overlay,data)
}
export function stripMowerCurrent(plan:MowerTaskPlan):MowerTaskPlan{return Object.fromEntries(Object.entries(plan).filter(([,names])=>names.some(name=>name!=='Current')))}
const assigned=(plan:MowerTaskPlan)=>new Set(Object.entries(plan).flatMap(([room,names])=>room.startsWith('dorm')?[]:names.filter(n=>!['Current','Free',''].includes(n))))
export const cloneMowerShiftTask=(task:MowerTask):MowerTask=>Object.assign(new MowerTask({type:task.type}),task,{plan:structuredClone(task.plan),urgentRecoveryRequestNames:[...task.urgentRecoveryRequestNames],urgentRecoverySupportNames:[...task.urgentRecoverySupportNames],urgentRecoveryReservedNames:[...task.urgentRecoveryReservedNames],urgentRecoveryReservedSlots:[...task.urgentRecoveryReservedSlots],groupShiftTransitions:{...task.groupShiftTransitions},backupExplicitSlots:new Set(task.backupExplicitSlots),dormFillPlan:structuredClone(task.dormFillPlan),backupShiftIntent:task.backupShiftIntent&&structuredClone(task.backupShiftIntent),backupShiftConditions:task.backupShiftConditions&&[...task.backupShiftConditions]})

/** Application protection beyond pinned alpha: a canceled shift must not complete through incidental bed swaps. */
function cancelledShiftLeavesOnlyDormFill(data:MowerSchedulingData,simulation:MowerSchedulingData,task:MowerTask,intent:MowerTaskPlan,conditions:boolean[],coalesced:MowerTask[],final:MowerTaskPlan):boolean{
 if(!data.alpha||![T.SHIFT_OFF,T.EXHAUST_OFF].includes(task.type)||!same(data.planConditions,conditions)||coalesced.some(t=>t.type!==T.FILL_DORM)||Object.values(final).some(row=>row.includes('Free')||row.includes('')))return false
 const projected=projectMowerArrangements(data,[intent])
 const targets=Object.values(data.operators).filter(op=>{
  const next=projected.operators[op.name]
  return op.isHigh()&&!op.room.startsWith('dorm')&&!!op.currentRoom&&!op.isResting()&&!!next&&(!next.currentRoom||next.isResting())
 })
 if(!targets.length||targets.some(op=>{const next=simulation.operators[op.name];return !next||next.currentRoom!==op.currentRoom||next.currentIndex!==op.currentIndex}))return false
 const names=new Set([...Object.keys(data.operators),...Object.keys(simulation.operators)])
 const changes=[...names].filter(name=>{const old=data.operators[name],next=simulation.operators[name];return (old?.currentRoom??'')!==(next?.currentRoom??'')||(old?.currentIndex??-1)!==(next?.currentIndex??-1)})
 return changes.length>0&&changes.every(name=>{
  const old=data.operators[name],next=simulation.operators[name]
  return !!old&&!!next&&!old.isHigh()&&!next.isHigh()&&old.isResting()&&next.isResting()&&next.temporaryDormFill
 })
}

/** Backup rules can invalidate only part of a previously batched ordinary departure. */
function filterExhaustedOrdinaryIntent(data:MowerSchedulingData,rules:MowerSchedulingData,task:MowerTask,intent:MowerTaskPlan,transitions:Record<string,boolean>,explicitSlots:ReadonlySet<string>=task.backupExplicitSlots):boolean{
 if(!task.ordinaryCoordination||task.backupShiftActive||task.productShiftLocked)return false
 const exhausted=mowerExhaustGroups(rules),blocked=new Set<string>(),blockedGroups=new Set<string>()
 for(const name of task.coordinationRequestNames){
  const op=rules.operators[name]
  if(!op||op.multiGroup&&!op.independentRest||!op.exhaustRequire&&!exhausted.has(op.group))continue
  const members=op.group?data.shiftGroupMembers(op.group):[name]
  if(members.some(member=>{const original=data.operators[member];return !!original&&explicitSlots.has(alphaPosition(original.currentRoom,original.currentIndex))||Object.entries(intent).some(([room,row])=>row.some((assigned,index)=>assigned===member&&explicitSlots.has(alphaPosition(room,index))))}))continue
  if(op.group)blockedGroups.add(op.group)
  members.forEach(member=>blocked.add(member))
 }
 let changed=false
 const removedCovers=new Set<string>()
 for(const name of blocked){
  const op=data.operators[name]
  if(!op||!op.currentRoom||op.isResting()&&!op.room.startsWith('dorm')||op.multiGroup&&op.groupBindings.some(binding=>binding.group&&!blockedGroups.has(binding.group)&&rules.groupIsResting(binding.group)))continue
  for(const [room,row] of Object.entries(intent))if(room.startsWith('dorm'))row.forEach((resident,index)=>{if(resident===name){row[index]='Current';changed=true}})
  const row=intent[op.currentRoom]
  if(row&&row[op.currentIndex]!==undefined&&row[op.currentIndex]!=='Current'&&row[op.currentIndex]!==name){removedCovers.add(row[op.currentIndex]!);row[op.currentIndex]='Current';changed=true}
  if(op.group)delete transitions[op.group]
 }
 const retainedAssignments=new Set(Object.values(intent).flat())
 for(const [room,row] of Object.entries(intent))if(room.startsWith('dorm'))row.forEach((name,index)=>{
  const current=data.currentOperator(room,index)
  if(name==='Free'&&!explicitSlots.has(alphaPosition(room,index))&&current&&removedCovers.has(current.name)&&!retainedAssignments.has(current.name))row[index]='Current'
 })
 return changed
}

function cancelIncidentalGroupReturns(data:MowerSchedulingData,intent:MowerTaskPlan,explicitSlots:ReadonlySet<string>):void {
 const explicit:MowerTaskPlan={}
 for(const [room,row] of Object.entries(intent))explicit[room]=row.map((name,index)=>explicitSlots.has(alphaPosition(room,index))?name:'Current')
 const departing=new Set(Object.entries(mowerArrangementGroupTransitions(data,explicit)).filter(([,resting])=>resting).map(([group])=>group))
 if(!departing.size)return
 for(const [room,row] of Object.entries(intent))row.forEach((name,index)=>{
  const op=data.operators[name]
  if(op&&departing.has(op.group)&&op.room===room&&op.index===index&&!explicitSlots.has(alphaPosition(room,index)))row[index]='Current'
 })
}

/** Reproject ordinary migrations from physical state; retain only explicit tasks triggered in this preview. */
export function prepareMowerShiftBackup(data:MowerSchedulingData,task:MowerTask,model:MowerShiftModel,pendingTasks?:MowerTask[]):void{
 delete task.previewReturnVeto
 data.backupExplicitTasks=model.explicitTasks??data.backupExplicitTasks
 if(!model.count||task.backupShiftActive||task.arrangementStarted||![T.SHIFT_ON,T.SHIFT_OFF,T.EXHAUST_OFF,T.SELF_CORRECTION,T.RE_ORDER].includes(task.type))return
 const intent=structuredClone(task.backupShiftIntent??task.plan),original=[...data.planConditions],entrySlots=new Set(task.backupExplicitSlots)
 let transitions=task.productShiftLocked?{...task.groupShiftTransitions}:mowerArrangementGroupTransitions(data,intent)
 const returning=new Set(Object.entries(transitions).filter(([group,resting])=>!resting&&data.groupIsResting(group)).map(([group])=>group))
 let seed=projectMowerArrangements(data,[intent])
 commitMowerGroupShifts(seed,transitions)
 let conditions=model.evaluate(seed);const seen=new Set<string>()
 for(let pass=0;pass<64;pass++){
  const key=JSON.stringify([conditions,intent]);if(seen.has(key))throw new MowerShiftPreviewError('上下班副表推演出现循环，保留原任务，暂不执行换人');seen.add(key)
  const simulation=model.swap(projectMowerArrangements(seed,[]),conditions)
  if(filterExhaustedOrdinaryIntent(data,simulation,task,intent,transitions,entrySlots)){seed=projectMowerArrangements(data,[intent]);commitMowerGroupShifts(seed,transitions);conditions=model.evaluate(seed);continue}
  const transition=model.transition(data,simulation,original,conditions,seed,pendingTasks),entry:MowerTaskPlan={}
  for(const slot of model.explicitSlots?.(original,conditions)??[]){
   const [room,index]=slot.split('\0'),name=transition[room!]?.[Number(index)]
   if(name===undefined||name==='Current')continue
   ;(entry[room!]??=Array(simulation.plan[room!]!.length).fill('Current'))[Number(index)]=name;entrySlots.add(slot)
  }
  if(Object.keys(entry).length){
   for(const [condition,active] of conditions.entries())if(active&&!original[condition]&&model.conditionObservationNames?.[condition]?.length){
    const specified=model.explicitTasks?.[condition]??{}
    const explicit=Object.fromEntries(Object.entries(specified).map(([room,row])=>[room,row.map((name,index)=>entry[room]?.[index]===name?name:'Current')]))
    if(Object.entries(mowerArrangementGroupTransitions(simulation,explicit)).some(([group,resting])=>resting&&returning.has(group))){
     const proof=task.previewReturnVeto??={conditions:[],names:[]}
     proof.conditions=[...new Set([...proof.conditions,condition])];proof.names=[...new Set([...proof.names,...model.conditionObservationNames[condition]!])]
    }
   }
   mergeMowerShiftTransition(intent,entry,simulation)
   cancelIncidentalGroupReturns(simulation,intent,entrySlots)
   transitions=task.productShiftLocked?{...task.groupShiftTransitions,...mowerArrangementGroupTransitions(simulation,intent)}:mowerArrangementGroupTransitions(simulation,intent)
   seed=projectMowerArrangements(data,[intent]);commitMowerGroupShifts(seed,transitions)
  }
  const merged=structuredClone(intent)
  mergeMowerShiftTransition(merged,transition,simulation)
  const effective=model.swap(projectMowerArrangements(data,[]),conditions),reserved=mowerDormTaskReservations(effective,pendingTasks??[])
  const completed=completeMowerBackupDepartureRecovery(effective,merged,entrySlots,reserved.slots,pendingTasks,false,true)
  if(!completed)throw new MowerShiftPreviewError('副表下班干员尚无可用恢复床位，保留原任务')
  for(const [room,row] of Object.entries(completed))if(room.startsWith('dorm'))row.forEach((name,index)=>{
   const op=effective.operators[name]
   if(!op||!entrySlots.has(alphaPosition(op.room,op.index))||!op.replacement.includes(merged[op.room]?.[op.index]??'')||merged[room]?.[index]===name)return
   ;(intent[room]??=Array(effective.plan[room]!.length).fill('Current'))[index]=name;entrySlots.add(alphaPosition(room,index))
  })
  for(const room of Object.keys(merged))delete merged[room]
  Object.assign(merged,completed)
  const projected=projectMowerArrangements(effective,[merged]),next=model.evaluate(projected)
  if(same(next,conditions)){
   task.groupShiftTransitions=task.productShiftLocked?{...task.groupShiftTransitions,...mowerArrangementGroupTransitions(simulation,merged)}:mowerArrangementGroupTransitions(simulation,merged)
   task.backupExplicitSlots=entrySlots
   if(same(conditions,original)&&JSON.stringify(merged)===JSON.stringify(intent)){task.plan=intent;delete task.backupShiftIntent;delete task.backupShiftConditions;return}
   task.backupShiftIntent=intent;task.backupShiftConditions=[...conditions];task.plan=stripMowerCurrent(merged);return
  }
  conditions=next
 }
 throw new MowerShiftPreviewError('上下班副表推演未收敛，保留原任务，暂不执行换人')
}

export function recordMowerDormAdmissions(data:MowerSchedulingData,step:MowerTask,previous:Map<string,[string,number]>):void{
 for(const [room,names] of Object.entries(step.plan))if(room.startsWith('dorm'))names.forEach((name,index)=>{
  const op=data.operators[name],old=previous.get(name);if(!op||!old||!['Free',op.name].includes(step.plan[room]?.[index]??''))return
  const ordinary=step.dormFillPlan[room]?.[index]
  if([T.FILL_DORM,T.RELEASE_DORM].includes(step.type)||Object.values(step.dormFillPlan).some(row=>row.includes(name))||ordinary===name||ordinary==='Free'||step.simpleDormFill){
   if((old[0]!==room||old[1]!==index)&&!old[0].startsWith('dorm')&&!op.isHigh()&&data.dynamicDormPosition(room,index))op.temporaryDormFill=true
  }else if([T.SHIFT_OFF,T.EXHAUST_OFF].includes(step.type))op.temporaryDormFill=false
 })
}
export function prepareMowerShiftCycle(data:MowerSchedulingData,task:MowerTask,queue:MowerTaskQueue,model:MowerShiftModel,options:MowerRestingOptions={}):void{
 delete task.previewReturnVeto
 if(task.backupShiftActive||task.arrangementStarted)return
 if(task.exhaustSupport){prepareMowerShiftBackup(data,task,model,queue.tasks.filter(t=>t!==task));return}
 const probe=new MowerTask({time:data.nowMicros/3_600_000_000,type:T.FILL_DORM});simplifyMowerAlphaDormFill(probe,queue.tasks,data.nowMicros,options.priorityScheduling)
 if(probe.simpleDormFill||task.productShiftLocked||queue.tasks.some(t=>t!==task&&(t.type===T.FIAMMETTA&&t.timeMicros<=data.nowMicros||t.backupShiftActive||t.productShiftLocked))){
  prepareMowerShiftBackup(data,task,model,queue.tasks.filter(t=>t!==task))
  const reserved=mowerDormTaskReservations(data,queue.tasks.filter(t=>t!==task&&t.type!==T.SHIFT_ON))
  task.plan=planMowerDormIsolation(data,task.plan,new Set([...reserved.slots,...task.backupExplicitSlots]),reserved.names);return
 }
 const ordinary=[T.SHIFT_ON,T.SHIFT_OFF,T.EXHAUST_OFF,T.SELF_CORRECTION,T.RE_ORDER,T.FILL_DORM]
 const candidates=queue.tasks.filter(t=>t!==task&&!t.retainsExecution&&!t.arrangementStarted&&!t.exhaustSupport&&!t.urgentRecoveryRequestNames.length&&ordinary.includes(t.type)&&Object.keys(t.plan).length&&t.timeMicros<=data.nowMicros&&!t.strictMoodLimit&&!t.dormRecoveryRestore.length),coalesced:MowerTask[]=[]
 let intent=structuredClone(task.backupShiftIntent??task.plan),explicitSlots=new Set(task.backupExplicitSlots)
 const explicitPlan=(plan:MowerTaskPlan,slots:ReadonlySet<string>)=>Object.fromEntries(Object.entries(plan).map(([room,row])=>[room,row.map((name,index)=>slots.has(alphaPosition(room,index))?name:'Current')]))
 for(const queued of [...candidates].sort((a,b)=>a.timeMicros-b.timeMicros)){
  if(queued.type!==T.FILL_DORM){
   const combined=structuredClone(intent),explicit=explicitPlan(intent,explicitSlots),combinedSlots=new Set([...explicitSlots,...queued.backupExplicitSlots])
   mergeMowerShiftTransition(combined,queued.backupShiftIntent??queued.plan,data)
   mergeMowerShiftTransition(explicit,explicitPlan(queued.plan,queued.backupExplicitSlots),data)
   mergeMowerShiftTransition(combined,explicit,data)
   if(!normalizeMowerSharedArrangement(data,combined,undefined,combinedSlots))continue
   intent=combined;explicitSlots=combinedSlots
  }
  coalesced.push(queued)
 }
 const pending=queue.tasks.filter(t=>t!==task&&!coalesced.includes(t)),returning=new Set<string>(),unresolved=new Set<string>(),ordinaryUnknown=new Set<string>(),seen=new Set<string>()
 let simulation=projectMowerArrangements(data,[]),step=new MowerTask({type:task.type,plan:intent})
 step.groupShiftTransitions=mowerArrangementGroupTransitions(data,intent)
 const returningGroups=new Set<string>()
 const sources=[task,...coalesced],required=new Set<string>()
 for(const source of sources)if(!source.ordinaryCoordination&&[T.SHIFT_OFF,T.EXHAUST_OFF].includes(source.type))for(const [room,row] of Object.entries(source.plan))if(room.startsWith('dorm'))for(const name of row){const op=data.operators[name];if(op&&!op.isResting())required.add(op.group?'group:'+op.group:'operator:'+name)}
 step.coordinationRequestNames=[...new Set(sources.filter(candidate=>candidate.ordinaryCoordination).flatMap(candidate=>candidate.coordinationRequestNames))].filter(name=>{const op=data.operators[name];return !required.has(op?.group?'group:'+op.group:'operator:'+name)})
 step.ordinaryCoordination=step.coordinationRequestNames.length>0
 const ordinaryRequests=new Set(step.coordinationRequestNames)
 step.backupExplicitSlots=new Set(explicitSlots)
 step.dormFillPlan=structuredClone(task.dormFillPlan)
 for(let pass=0;pass<64;pass++){
  prepareMowerShiftBackup(simulation,step,model,pending)
  if(pass===0){intent=structuredClone(step.backupShiftIntent??step.plan);task.previewReturnVeto=step.previewReturnVeto}
  const conditions=step.backupShiftConditions??simulation.planConditions
  simulation=model.swap(simulation,conditions)
  for(const [group,resting] of Object.entries(step.groupShiftTransitions))if(!resting&&simulation.groupIsResting(group))returningGroups.add(group)
  commitMowerGroupShifts(simulation,step.groupShiftTransitions)
  step.backupExplicitSlots.forEach(slot=>explicitSlots.add(slot))
  const reserved=mowerDormTaskReservations(simulation,pending.filter(t=>t.type!==T.SHIFT_ON||t.backupShiftActive||t.productShiftLocked||t.dormRecoveryRestore.length))
  const completed=completeMowerBackupDepartureRecovery(simulation,step.plan,explicitSlots,reserved.slots,pending,false,true)
  if(!completed)throw new MowerShiftPreviewError('副表下班干员尚无可用恢复床位，保留原任务')
  step.plan=planMowerDormIsolation(simulation,completed,new Set([...reserved.slots,...explicitSlots]),reserved.names)
  if(!normalizeMowerSharedArrangement(simulation,step.plan,undefined,explicitSlots))throw new MowerShiftPreviewError('绑组共享替班冲突，保留原任务并等待岗位释放')
  for(const name of assigned(step.plan)){const op=simulation.operators[name];if(op&&(!op.currentRoom||op.isResting()))returning.add(name)}
  const positions=new Map(Object.values(simulation.operators).map(op=>[op.name,[op.currentRoom,op.currentIndex] as [string,number]]))
  for(const [group,resting] of Object.entries(mowerArrangementGroupTransitions(simulation,step.plan)))if(!resting&&simulation.groupIsResting(group))returningGroups.add(group)
  simulation=projectMowerArrangements(simulation,[step.plan]);recordMowerDormAdmissions(simulation,step,positions)
  for(const [room,names] of Object.entries(step.plan))names.forEach((name,index)=>{
   const key=alphaPosition(room,index)
   if(name==='Free'){unresolved.add(key);if(step.dormFillPlan[room]?.[index]==='Free')ordinaryUnknown.add(key);else ordinaryUnknown.delete(key)}
   else if(name!=='Current'){unresolved.delete(key);ordinaryUnknown.delete(key)}
  })
  const key=JSON.stringify([conditions,[...explicitSlots].sort(),[...unresolved].sort(),Object.values(simulation.operators).map(op=>[op.name,op.currentRoom,op.currentIndex])])
  if(seen.has(key))throw new MowerShiftPreviewError('完整换班预演出现循环，保留原任务，暂不执行换人');seen.add(key)
  const localQueue=new MowerTaskQueue();localQueue.tasks=pending.map(cloneMowerShiftTask)
  const existingLocalTasks=new Set(localQueue.tasks)
  const rest=mowerResting(simulation,localQueue,{...options,returning,returningGroups,isDormReplacement:name=>{const op=simulation.operators[name];return !!op&&op.currentRoom.startsWith('dorm')&&simulation.dormReplacementForSlot(name,op.currentRoom,op.currentIndex)},isMasteryBusy:name=>simulation.busyRestingNames.has(name)}),reorder=mowerTryReorder(simulation,rest)
  if(reorder)mergeMowerPlanOverlay(rest,reorder,simulation)
  let next=stripMowerCurrent(rest),fill:MowerTaskPlan={}
  if(!Object.keys(next).length){next=mowerCorrectionPlan(simulation,false,explicitSlots,pending,step);for(const [room,names] of Object.entries(next))names.forEach((name,index)=>{if(simulation.currentOperator(room,index)?.name===name)names[index]='Current'});next=stripMowerCurrent(next)}
  if(!Object.keys(next).length){fill=mowerAlphaFillPlan(simulation,pending.map(cloneMowerShiftTask));next=structuredClone(fill)}
  for(const [room,names] of Object.entries(next))names.forEach((name,index)=>{if(name==='Free'&&unresolved.has(alphaPosition(room,index)))names[index]='Current'})
  next=stripMowerCurrent(next)
  if(Object.keys(next).length){
   step=new MowerTask({type:T.SHIFT_OFF,plan:next})
   const ordinaryTasks=localQueue.tasks.filter(candidate=>!existingLocalTasks.has(candidate)&&candidate.ordinaryCoordination&&Object.keys(candidate.plan).length)
   step.ordinaryCoordination=ordinaryTasks.length>0;step.coordinationRequestNames=[...new Set(ordinaryTasks.flatMap(candidate=>candidate.coordinationRequestNames))]
   step.coordinationRequestNames.forEach(name=>ordinaryRequests.add(name));step.backupExplicitSlots=new Set(explicitSlots);step.dormFillPlan=fill;continue
  }
  const final:MowerTaskPlan={}
  for(const [room,names] of Object.entries(simulation.plan))names.forEach((_,index)=>{const old=data.currentOperator(room,index)?.name??'',name=simulation.currentOperator(room,index)?.name??'';if(old!==name||unresolved.has(alphaPosition(room,index)))(final[room]??=Array(names.length).fill('Current'))[index]=name||'Free'})
  if(cancelledShiftLeavesOnlyDormFill(data,simulation,task,intent,conditions,coalesced,final))throw new MowerShiftPreviewError('原下班意图被完全取消，仅剩普通填床换位，保留原任务，暂不执行换人')
  task.groupShiftTransitions=Object.fromEntries(Object.entries(simulation.groupShiftState).filter(([group,resting])=>data.groupIsResting(group)!==resting))
  task.coordinationRequestNames=[...ordinaryRequests].filter(name=>!data.operators[name]?.isResting()&&simulation.operators[name]?.isResting());task.ordinaryCoordination=task.coordinationRequestNames.length>0
  task.backupExplicitSlots=explicitSlots
  task.backupShiftIntent=intent;task.backupShiftConditions=[...conditions];task.plan=final
  inheritMowerBackupRefreshRules(task,coalesced)
  task.dormFillPlan=Object.fromEntries(Object.entries(final).filter(([room])=>room.startsWith('dorm')).map(([room,names])=>[room,names.map((name,index)=>simulation.operators[name]?.temporaryDormFill||ordinaryUnknown.has(alphaPosition(room,index))?name:'Current')]))
  queue.tasks=queue.tasks.filter(t=>!coalesced.includes(t))
  for(const [room,names] of Object.entries(final))if(room.startsWith('dorm'))for(const name of names)if(data.operators[name])data.operators[name]!.dormMoodFallback=simulation.operators[name]!.dormMoodFallback
  return
 }
 throw new MowerShiftPreviewError('完整换班预演未收敛，保留原任务，暂不执行换人')
}

/** New backup intent supersedes overlapping due tasks, including transitive overlap. */
export function coalesceMowerBackupTransition(data:MowerSchedulingData,transition:MowerTaskPlan,tasks:MowerTask[]):{plan:MowerTaskPlan;consumed:MowerTask[]}{
 const footprint=(plan:MowerTaskPlan)=>({names:new Set(Object.values(plan).flat().filter(n=>!['Current','Free',''].includes(n))),slots:new Set(Object.entries(plan).flatMap(([r,names])=>names.flatMap((n,i)=>!['Current',''].includes(n)?[alphaPosition(r,i)]:[])))})
 const affected=footprint(transition),consumed:MowerTask[]=[]
 let remaining=tasks.filter(t=>!t.retainsExecution&&!t.arrangementStarted&&!t.exhaustSupport&&!t.urgentRecoveryRequestNames.length&&[T.SHIFT_ON,T.SHIFT_OFF,T.SELF_CORRECTION,T.RE_ORDER,T.NOT_SPECIFIC,T.FILL_DORM].includes(t.type)&&Object.keys(t.plan).length&&Math.min(t.timeMicros,t.arrangementRetryDueMicros??t.timeMicros)<=data.nowMicros+toMowerMicros(1/60)&&!t.strictMoodLimit&&!t.dormRecoveryRestore.length)
 while(remaining.length){let matched=false;for(const t of [...remaining]){const f=footprint(t.plan);if(![...f.names].some(n=>affected.names.has(n))&&![...f.slots].some(s=>affected.slots.has(s)))continue;matched=true;consumed.push(t);f.names.forEach(n=>affected.names.add(n));f.slots.forEach(s=>affected.slots.add(s));remaining=remaining.filter(v=>v!==t)}if(!matched)break}
 if(!consumed.length)return {plan:transition,consumed}
 const plan:MowerTaskPlan={}
 for(const task of [...consumed].sort((a,b)=>a.timeMicros-b.timeMicros)){const intent=structuredClone(task.plan);filterExhaustedOrdinaryIntent(data,data,task,intent,{...task.groupShiftTransitions});mergeMowerShiftTransition(plan,intent,data)}
 mergeMowerShiftTransition(plan,transition,data)
 return {plan:stripMowerCurrent(plan),consumed}
}
