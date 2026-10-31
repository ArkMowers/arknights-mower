// Mower alpha b2d9ac8 exhaust_replacement.plan_exhaust_support (MIT).
import {mowerForcedGroupCoverReservations,mowerHeldRestGroups} from './mowerBackupGroupTasks'
import {mowerUrgentRecallBlocked} from './mowerUrgentRecovery'
import {planMowerReplacementHandoff,mowerRecallCanSustain,mowerRecallMoodAdmissible,mowerCoordinationPrimaryReplacement} from './mowerReplacementCoordination'
import {mowerGroupRecoveryDeadline,mowerRecoveryReady} from './mowerGroupRecovery'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerReplacementCandidates,MowerOperatorState} from './mowerOperatorState'
import {projectMowerArrangements} from './mowerObservations'
import {mowerGetRestingPlan,mowerTryReorder,type MowerRestingOptions} from './mowerOrdinaryPlanning'
import {alphaRebalanceClosingDorms,mowerMatchReplacements} from './mowerAlphaDorm'
import type {MowerTaskPlan} from './mowerTaskQueue'
import {mowerArrangementGroupTransitions,mowerRestingBindingGroups,mowerSharedReplacements,normalizeMowerSharedArrangement} from './mowerSharedGroups'

/** Search only dependencies encountered by failed admission, with fewest returned units first. */
export function planMowerAlphaExhaustSupport(original:MowerSchedulingData,candidates:string[],options:MowerRestingOptions={}):MowerTaskPlan|undefined {
 const pending:string[][]=[[]],visited=new Set([''])
 for(let cursor=0;cursor<pending.length;cursor++){
  const seeds=pending[cursor]!,dependencies=new Set<string>()
  const plan=planMowerAlphaExhaustAttempt(original,candidates,options,seeds,name=>dependencies.add(name))
  if(plan)return plan
  if(!options.urgentExhaust||mowerUrgentRecallBlocked(original,candidates,options.urgentRecoveryPendingSupporters))return
  for(const name of dependencies){
   if(seeds.includes(name))continue
   const next=[...seeds,name].sort(),key=JSON.stringify(next)
   if(!visited.has(key)){visited.add(key);pending.push(next)}
  }
 }
}
function planMowerAlphaExhaustAttempt(original:MowerSchedulingData,candidates:string[],options:MowerRestingOptions,seeds:string[],dependency:(name:string)=>void):MowerTaskPlan|undefined {
 const forced=mowerForcedGroupCoverReservations(original)
 const protectedNames=new Set([...original.busyRestingNames,...original.reservedProductReplacements,...options.reservedNames??[]]),required=new Set(candidates)
 const transitions=Object.fromEntries(candidates.map(n=>original.operators[n]!).filter(op=>op.group&&original.isGroupShiftAnchor(op)).map(op=>[op.group,true]))
 const replacements=(state:MowerSchedulingData,op:MowerOperatorState)=>op.multiGroup?mowerSharedReplacements(op,mowerRestingBindingGroups(state,op,required.has(op.name)?transitions:{})):op.replacement
 const covers=(state:MowerSchedulingData,op:MowerOperatorState)=>mowerReplacementCandidates(Object.assign(new MowerOperatorState(op),{replacement:replacements(state,op)}),state.operators,state.policy,state.nowMicros)
 const coverNames=new Set(candidates.flatMap(n=>replacements(original,original.operators[n]!).filter(n=>n!=='Free')))
 let plan:MowerTaskPlan=planMowerReplacementHandoff(original,candidates,options)??{},data=projectMowerArrangements(original,[plan])
 const selected=new Set<string>(),working=(op:MowerOperatorState)=>!!op.currentRoom&&!op.isResting()
 const requestGroups=new Set(Object.keys(transitions))
 const dependOn=(state:MowerSchedulingData,op:MowerOperatorState|undefined,group=op?.group)=>{
  if(!op)return
  if(group){
   if(requestGroups.has(group)||!state.groupIsResting(group))return
   const anchor=state.shiftGroupMembers(group).map(name=>state.operators[name]!).find(worker=>state.isGroupShiftAnchor(worker)&&worker.isResting())
   if(anchor)dependency(anchor.name)
  }else if(op.isHigh()&&op.isResting()&&!required.has(op.name))dependency(op.name)
 }
 const sharedDependencies=(state:MowerSchedulingData,trial:MowerTaskPlan)=>{
  const changes=mowerArrangementGroupTransitions(state,trial)
  for(const op of Object.values(state.operators))if(op.multiGroup){
   if(op.index>=(trial[op.room]?.length??0)&&!op.groupBindings.some(binding=>binding.group in changes))continue
   const groups=mowerRestingBindingGroups(state,op,changes)
   if(!mowerSharedReplacements(op,groups).length)for(const group of groups)dependOn(state,op,group)
  }
 }
 const replacementDependencies=(state:MowerSchedulingData,op:MowerOperatorState)=>{
  const groups=op.multiGroup?mowerRestingBindingGroups(state,op,transitions):[op.group]
  if(op.multiGroup)for(const group of groups)dependOn(state,op,group)
  const raw=op.multiGroup?groups.flatMap(group=>op.replacementsForGroup(group)):op.replacement
  for(const name of new Set(raw)){
   const cover=state.operators[name];if(!cover?.currentRoom)continue
   const owner=state.operators[state.plan[cover.currentRoom]?.[cover.currentIndex]??'']
   if(owner&&owner.name!==name&&(!owner.currentRoom||owner.isResting()))dependOn(state,owner)
  }
 }
 const autoFree=(op:MowerOperatorState)=>op.room.startsWith('dorm')&&!!op.group&&op.nativeName!=='菲亚梅塔'&&replacements(data,op).includes('Free')
 const eligible=(state:MowerSchedulingData,name:string,target:MowerOperatorState)=>{
  const op=state.operators[name],sameGroup=mowerCoordinationPrimaryReplacement(state,target,name,required)
  return !!op&&(!forced.names.has(name)||op.currentRoom===target.room&&op.currentIndex===target.index)&&(!op.isHigh()||sameGroup)&&!protectedNames.has(name)&&!options.reservedSlots?.has(op.currentRoom+'\0'+op.currentIndex)&&!selected.has(name)&&(!required.has(name)||sameGroup)&&!state.excludedCandidates.has(name)&&(op.currentRoom===target.room&&op.currentIndex===target.index||!state.dormReplacementForSlot(name,op.currentRoom,op.currentIndex))&&(target.room.startsWith('dorm')||!state.replacementExhausted(name,target))&&!options.isMasteryBusy?.(name)
 }
 const available=(state:MowerSchedulingData,name:string,target:MowerOperatorState)=>{const op=state.operators[name];return !!op&&eligible(state,name,target)&&(!op.currentRoom||op.isResting()||op.currentRoom===target.room&&op.currentIndex===target.index||required.has(name)&&mowerCoordinationPrimaryReplacement(state,target,name,required)&&op.currentRoom===op.room&&op.currentIndex===op.index)}
 const protectedRest=(state:MowerSchedulingData,name:string)=>{
  const op=state.operators[name]!
  if(!op.isResting())return false
  if(mowerHeldRestGroups(state,true).has(op.group))return true
  if(name in state.urgentRecoverySupporters)return true
  if(op.restInFull&&!mowerRecoveryReady(state,op,options.priorityScheduling))return true
  const recovery=op.group?mowerGroupRecoveryDeadline(projectMowerArrangements(state,[]),op.group):undefined
  return !!recovery?.requiredNames.length&&(recovery.requiredNames.some(member=>(!options.urgentExhaust||state.operators[member]!.restInFull)&&!mowerRecoveryReady(state,state.operators[member],options.priorityScheduling)))
 }
 const recall=(state:MowerSchedulingData,previous:MowerTaskPlan,names:string[]):[MowerTaskPlan,MowerSchedulingData]|undefined=>{
  if(mowerUrgentRecallBlocked(original,candidates,options.urgentRecoveryPendingSupporters))return
  const members=new Set(names.flatMap(name=>{const op=state.operators[name]!;return op.group?state.shiftGroupMembers(op.group):[name]}))
  if(names.some(name=>{const op=state.operators[name]!;return op.independentRest&&mowerRestingBindingGroups(state,op).length}))return
  const trial=structuredClone(previous)
  for(const member of members){
   const worker=state.operators[member]!
   if(worker.independentRest&&(!names.includes(member)||mowerRestingBindingGroups(state,worker).length))continue
   if(worker.currentRoom!==worker.room||worker.currentIndex!==worker.index)(trial[worker.room]??=Array(state.plan[worker.room]!.length).fill('Current'))[worker.index]=member
  }
  if(!normalizeMowerSharedArrangement(state,trial)){sharedDependencies(state,trial);return}
  const actualReturns=()=>new Set(Object.values(state.operators).filter(worker=>worker.isHigh()&&trial[worker.room]?.[worker.index]===worker.name&&(worker.currentRoom!==worker.room||worker.currentIndex!==worker.index)).map(worker=>worker.name))
  const returning=actualReturns()
  const blocked=(n:string)=>{
   const worker=state.operators[n]!
   const followingRequest=worker.multiGroup&&(!worker.independentRest||!worker.currentRoom&&state.canStandby(worker))&&candidates.some(other=>other!==n&&state.isGroupShiftAnchor(state.operators[other]!)&&worker.groupBindings.some(binding=>binding.group===state.operators[other]!.group))
   return required.has(n)&&!followingRequest||protectedNames.has(n)||options.reservedSlots?.has(worker.room+'\0'+worker.index)||options.isMasteryBusy?.(n)||protectedRest(state,n)||working(worker)&&worker.currentRoom!==worker.room
  }
  if([...returning].some(blocked))return
  const shadow=projectMowerArrangements(state,[])
  alphaRebalanceClosingDorms(shadow,trial,returning)
  if(!normalizeMowerSharedArrangement(state,trial)){sharedDependencies(state,trial);return}
  const recalled=actualReturns()
  if([...recalled].some(blocked)||!options.urgentExhaust&&!mowerRecallMoodAdmissible(original,recalled,candidates))return
  const projected=projectMowerArrangements(original,[trial])
  if(Object.values(state.operators).some(worker=>worker.isHigh()&&worker.isResting()&&!projected.operators[worker.name]!.currentRoom&&!recalled.has(worker.name)))return
  if(!options.urgentExhaust&&mowerCoordinationSupportOutcome(original,trial,candidates,options)===false)return
  return [trial,projected]
 }
 if(seeds.length){const seeded=recall(data,plan,seeds);if(!seeded)return;[plan,data]=seeded}
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
  if(!resolved)for(const {cover,owner} of occupied){const result=recall(data,plan,[owner.name]);if(!result||!available(result[1],cover,worker))continue;[plan,data]=result;resolved=true;break}
  if(!resolved){replacementDependencies(data,worker);return}
  matching=freeMatching()!;if(!(name in matching)){replacementDependencies(data,worker);return}
 }
 if(!freeMatching(false)){for(const name of ordered)replacementDependencies(data,data.operators[name]!);return}
 const canRest=(_state:MowerSchedulingData)=>validateMowerCoordinationSupport(original,plan,candidates,options)
 if(canRest(data))return plan
 const beds=[...data.dorms].sort((a,b)=>(data.operators[b.name]?.mood??25)-(data.operators[a.name]?.mood??25))
 for(const bed of beds){const op=data.operators[bed.name];if(op)dependOn(data,op);if(!op?.isHigh()||!op.isResting()||bed.timeMicros!==undefined&&bed.timeMicros<data.nowMicros||!data.effectiveFreeSlot(bed))continue;const result=recall(data,plan,[op.name]);if(!result||JSON.stringify(result[0])===JSON.stringify(plan))continue;[plan,data]=result;if(canRest(data))return plan}
}

/** Recheck the final support after backup convergence, before any physical arrangement. */
export function validateMowerCoordinationSupport(original:MowerSchedulingData,plan:MowerTaskPlan,candidates:readonly string[],options:MowerRestingOptions={}):boolean {
 return mowerCoordinationSupportOutcome(original,plan,candidates,options)===true
}
/** Incomplete admission may still need another recall; completed unsafe admission must try another candidate. */
function mowerCoordinationSupportOutcome(original:MowerSchedulingData,plan:MowerTaskPlan,candidates:readonly string[],options:MowerRestingOptions):boolean|undefined {
 const forced=mowerForcedGroupCoverReservations(original)
 for(const [room,row] of Object.entries(plan))if(row.some((name,index)=>name!=='Current'&&(forced.slots.has(room+'\0'+index)||forced.names.has(name))&&original.currentOperator(room,index)?.name!==name))return false
 const state=projectMowerArrangements(original,[plan]),trial=projectMowerArrangements(state,[]),result:MowerTaskPlan={}
 if(candidates.some(name=>!state.operators[name]))return false
 mowerGetRestingPlan(trial,[...candidates],[],result,{...options,onBlocked:undefined,isDormReplacement:name=>{
  const before=original.operators[name],after=trial.operators[name]
  if(!after)return false
  const projected=trial.dormReplacementForSlot(name,after.currentRoom,after.currentIndex)
  return before&&(before.currentRoom!==after.currentRoom||before.currentIndex!==after.currentIndex)?projected:options.isDormReplacement?.(name)??projected
 }})
 if(!Object.keys(result).length)return
 const reorder=mowerTryReorder(trial,result);if(reorder)Object.assign(result,reorder)
 const protectedNames=new Set([...original.busyRestingNames,...original.reservedProductReplacements,...options.reservedNames??[]])
 for(const proposal of [plan,result])for(const [room,row] of Object.entries(proposal))if(row.some((name,index)=>name!=='Current'&&(options.reservedSlots?.has(room+'\0'+index)||protectedNames.has(name)||(forced.slots.has(room+'\0'+index)||forced.names.has(name))&&original.currentOperator(room,index)?.name!==name)))return false
 const admitted=projectMowerArrangements(state,[result]),recalled=new Set(Object.values(original.operators).filter(op=>op.isHigh()&&op.isResting()&&admitted.operators[op.name]?.currentRoom===op.room&&!op.room.startsWith('dorm')).map(op=>op.name))
 if(!recalled.size)return true
 return mowerRecallCanSustain(original,admitted,recalled,candidates,options)
}
