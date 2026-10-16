// Mower alpha b2d9ac8 exhaust_replacement.plan_exhaust_support (MIT).
import {planMowerReplacementHandoff,mowerRecallCanSustain,mowerCoordinationPrimaryReplacement} from './mowerReplacementCoordination'
import {mowerGroupRecoveryDeadline,mowerRecoveryReady} from './mowerGroupRecovery'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerReplacementCandidates,MowerOperatorState} from './mowerOperatorState'
import {projectMowerArrangements} from './mowerObservations'
import {mowerGetRestingPlan,mowerTryReorder,type MowerRestingOptions} from './mowerOrdinaryPlanning'
import {alphaRebalanceClosingDorms,mowerMatchReplacements} from './mowerAlphaDorm'
import type {MowerTaskPlan} from './mowerTaskQueue'
import {mowerRestingBindingGroups,mowerSharedReplacements} from './mowerSharedGroups'

export function planMowerAlphaExhaustSupport(original:MowerSchedulingData,candidates:string[],options:MowerRestingOptions={}):MowerTaskPlan|undefined {
 const protectedNames=new Set([...original.busyRestingNames,...original.reservedProductReplacements,...options.reservedNames??[]]),required=new Set(candidates)
 const transitions=Object.fromEntries(candidates.map(n=>original.operators[n]!).filter(op=>op.group&&original.isGroupShiftAnchor(op)).map(op=>[op.group,true]))
 const replacements=(state:MowerSchedulingData,op:MowerOperatorState)=>op.multiGroup?mowerSharedReplacements(op,mowerRestingBindingGroups(state,op,required.has(op.name)?transitions:{})):op.replacement
 const covers=(state:MowerSchedulingData,op:MowerOperatorState)=>mowerReplacementCandidates(Object.assign(new MowerOperatorState(op),{replacement:replacements(state,op)}),state.operators,state.policy,state.nowMicros)
 const coverNames=new Set(candidates.flatMap(n=>replacements(original,original.operators[n]!).filter(n=>n!=='Free')))
 let plan:MowerTaskPlan=planMowerReplacementHandoff(original,candidates,options)??{},data=projectMowerArrangements(original,[plan])
 const selected=new Set<string>(),working=(op:MowerOperatorState)=>!!op.currentRoom&&!op.isResting()
 const autoFree=(op:MowerOperatorState)=>op.room.startsWith('dorm')&&!!op.group&&op.nativeName!=='菲亚梅塔'&&replacements(data,op).includes('Free')
 const eligible=(state:MowerSchedulingData,name:string,target:MowerOperatorState)=>{
  const op=state.operators[name],sameGroup=mowerCoordinationPrimaryReplacement(state,target,name,required)
  return !!op&&(!op.isHigh()||sameGroup)&&!protectedNames.has(name)&&!options.reservedSlots?.has(op.currentRoom+'\0'+op.currentIndex)&&!selected.has(name)&&(!required.has(name)||sameGroup)&&!state.excludedCandidates.has(name)&&!state.dormReplacementForSlot(name,op.currentRoom,op.currentIndex)&&(target.room.startsWith('dorm')||!state.replacementExhausted(name))&&!options.isMasteryBusy?.(name)
 }
 const available=(state:MowerSchedulingData,name:string,target:MowerOperatorState)=>{const op=state.operators[name];return !!op&&eligible(state,name,target)&&(!op.currentRoom||op.isResting()||required.has(name)&&mowerCoordinationPrimaryReplacement(state,target,name,required)&&op.currentRoom===op.room&&op.currentIndex===op.index)}
 const protectedRest=(state:MowerSchedulingData,name:string)=>{
  const op=state.operators[name]!
  if(!op.isResting())return false
  if(op.restInFull&&!mowerRecoveryReady(state,op,options.priorityScheduling))return true
  const recovery=op.group?mowerGroupRecoveryDeadline(projectMowerArrangements(state,[]),op.group):undefined
  return !!recovery?.requiredNames.length&&(recovery.requiredNames.some(member=>(!options.urgentExhaust||state.operators[member]!.restInFull)&&!mowerRecoveryReady(state,state.operators[member],options.priorityScheduling)))
 }
 const recall=(state:MowerSchedulingData,previous:MowerTaskPlan,name:string):[MowerTaskPlan,MowerSchedulingData]|undefined=>{
  const op=state.operators[name]!,members=new Set(op.group?state.group(op.group):[name])
  if(op.independentRest&&mowerRestingBindingGroups(state,op).length)return
  if([...members].some(n=>required.has(n)||protectedNames.has(n)||options.reservedSlots?.has(state.operators[n]!.room+'\0'+state.operators[n]!.index)||options.isMasteryBusy?.(n)||protectedRest(state,n)))return
  const trial=structuredClone(previous)
  for(const member of members){const worker=state.operators[member]!;if(working(worker)&&worker.currentRoom!==worker.room)return;if(worker.currentRoom!==worker.room||worker.currentIndex!==worker.index)(trial[worker.room]??=Array(state.plan[worker.room]!.length).fill('Current'))[worker.index]=member}
  const shadow=projectMowerArrangements(state,[]),recalled=alphaRebalanceClosingDorms(shadow,trial,members)
  if([...recalled].some(n=>required.has(n)||protectedNames.has(n)||options.reservedSlots?.has(state.operators[n]!.room+'\0'+state.operators[n]!.index)||options.isMasteryBusy?.(n)||protectedRest(state,n)))return
  const projected=projectMowerArrangements(original,[trial])
  if(Object.values(state.operators).some(worker=>worker.isHigh()&&worker.isResting()&&!projected.operators[worker.name]!.currentRoom&&!recalled.has(worker.name)))return
  return [trial,projected]
 }
 const ordered=[...candidates].sort((a,b)=>{const x=data.operators[a]!,y=data.operators[b]!,fia=options.fiaTargets??[];return Number(x.room.startsWith('dorm'))-Number(y.room.startsWith('dorm'))||Number(!fia.includes(a))-Number(!fia.includes(b))||Number(['factory','train'].includes(x.currentRoom))-Number(['factory','train'].includes(y.currentRoom))||(x.currentMood(data.nowMicros)-x.lowerLimit)-(y.currentMood(data.nowMicros)-y.lowerLimit)})
 const freeMatching=(allowPartial=true)=>{
  selected.clear()
  const choices=Object.fromEntries(ordered.filter(n=>!autoFree(data.operators[n]!)).map(n=>[n,covers(data,data.operators[n]!).filter(cover=>available(data,cover,data.operators[n]!))]))
  const matching=mowerMatchReplacements(choices,allowPartial);if(matching)Object.values(matching).forEach(n=>selected.add(n));return matching
 }
 let matching=freeMatching()!
 for(const name of ordered){
  const worker=data.operators[name]!;if(autoFree(worker)||name in matching)continue
  const occupied=covers(data,worker).flatMap(cover=>{
   const op=data.operators[cover];if(!op||!eligible(data,cover,worker)||!working(op)||op.currentRoom==='train')return []
   const owner=data.operators[data.plan[op.currentRoom]?.[op.currentIndex]??'']
   return owner&&!required.has(owner.name)&&!protectedNames.has(owner.name)&&!working(owner)&&replacements(data,owner).includes(cover)?[{cover,owner}]:[]
  })
  let resolved=false
  for(const {owner} of occupied){const alternate=covers(data,owner).find(n=>!coverNames.has(n)&&available(data,n,owner));if(!alternate)continue;(plan[owner.room]??=Array(data.plan[owner.room]!.length).fill('Current'))[owner.index]=alternate;data=projectMowerArrangements(original,[plan]);resolved=true;break}
  if(!resolved)for(const {cover,owner} of occupied){const result=recall(data,plan,owner.name);if(!result||!available(result[1],cover,worker))continue;[plan,data]=result;resolved=true;break}
  if(!resolved)return
  matching=freeMatching()!;if(!(name in matching))return
 }
 if(!freeMatching(false))return
 const canRest=(_state:MowerSchedulingData)=>validateMowerCoordinationSupport(original,plan,candidates,options)
 if(canRest(data))return plan
 const beds=[...data.dorms].sort((a,b)=>(data.operators[b.name]?.mood??25)-(data.operators[a.name]?.mood??25))
 for(const bed of beds){const op=data.operators[bed.name];if(!op?.isHigh()||!op.isResting()||bed.timeMicros!==undefined&&bed.timeMicros<data.nowMicros||!data.effectiveFreeSlot(bed))continue;const result=recall(data,plan,op.name);if(!result||JSON.stringify(result[0])===JSON.stringify(plan))continue;[plan,data]=result;if(canRest(data))return plan}
}

/** Recheck the final support after backup convergence, before any physical arrangement. */
export function validateMowerCoordinationSupport(original:MowerSchedulingData,plan:MowerTaskPlan,candidates:readonly string[],options:MowerRestingOptions={}):boolean {
 const state=projectMowerArrangements(original,[plan]),trial=projectMowerArrangements(state,[]),result:MowerTaskPlan={}
 if(candidates.some(name=>!state.operators[name]))return false
 mowerGetRestingPlan(trial,[...candidates],[],result,{...options,onBlocked:undefined})
 if(!Object.keys(result).length)return false
 const reorder=mowerTryReorder(trial,result);if(reorder)Object.assign(result,reorder)
 const protectedNames=new Set([...original.busyRestingNames,...original.reservedProductReplacements,...options.reservedNames??[]])
 for(const proposal of [plan,result])for(const [room,row] of Object.entries(proposal))if(row.some((name,index)=>name!=='Current'&&(options.reservedSlots?.has(room+'\0'+index)||protectedNames.has(name))))return false
 const admitted=projectMowerArrangements(state,[result]),recalled=new Set(Object.values(original.operators).filter(op=>op.isHigh()&&op.isResting()&&admitted.operators[op.name]?.currentRoom===op.room&&!op.room.startsWith('dorm')).map(op=>op.name))
 return !recalled.size||mowerRecallCanSustain(original,admitted,recalled,candidates,options)
}
