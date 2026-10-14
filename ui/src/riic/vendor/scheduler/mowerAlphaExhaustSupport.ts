// Mower alpha b2d9ac8 exhaust_replacement.plan_exhaust_support (MIT).
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerReplacementCandidates,type MowerOperatorState} from './mowerOperatorState'
import {projectMowerArrangements} from './mowerObservations'
import {mowerGetRestingPlan,type MowerRestingOptions} from './mowerOrdinaryPlanning'
import {alphaRebalanceClosingDorms,mowerMatchReplacements} from './mowerAlphaDorm'
import type {MowerTaskPlan} from './mowerTaskQueue'

export function planMowerAlphaExhaustSupport(original:MowerSchedulingData,candidates:string[],options:MowerRestingOptions={}):MowerTaskPlan|undefined {
 const protectedNames=new Set([...original.busyRestingNames,...original.reservedProductReplacements]),required=new Set(candidates),coverNames=new Set(candidates.flatMap(n=>original.operators[n]!.replacement.filter(n=>n!=='Free')))
 let plan:MowerTaskPlan={},data=projectMowerArrangements(original,[])
 const selected=new Set<string>(),working=(op:MowerOperatorState)=>!!op.currentRoom&&!op.isResting()
 const autoFree=(op:MowerOperatorState)=>op.room.startsWith('dorm')&&!!op.group&&op.nativeName!=='菲亚梅塔'&&op.replacement.includes('Free')
 const eligible=(state:MowerSchedulingData,name:string,target:MowerOperatorState)=>{
  const op=state.operators[name]
  return !!op&&!op.isHigh()&&!protectedNames.has(name)&&!selected.has(name)&&!required.has(name)&&!state.excludedCandidates.has(name)&&!state.dormReplacementForSlot(name,op.currentRoom,op.currentIndex)&&(target.room.startsWith('dorm')||!state.replacementExhausted(name))&&!options.isMasteryBusy?.(name)
 }
 const available=(state:MowerSchedulingData,name:string,target:MowerOperatorState)=>eligible(state,name,target)&&(!state.operators[name]!.currentRoom||state.operators[name]!.isResting())
 const protectedRest=(state:MowerSchedulingData,name:string)=>{
  const op=state.operators[name]!,group=op.group?state.group(op.group).map(n=>state.operators[n]!):[]
  return op.isResting()&&(op.restInFull&&op.exhaustRequire||!!op.group&&group.some(o=>o.restInFull)&&group.some(o=>o.exhaustRequire))
 }
 const recall=(state:MowerSchedulingData,previous:MowerTaskPlan,name:string):[MowerTaskPlan,MowerSchedulingData]|undefined=>{
  const op=state.operators[name]!,members=new Set(op.group?state.group(op.group):[name])
  if([...members].some(n=>required.has(n)||protectedNames.has(n)||options.isMasteryBusy?.(n)||protectedRest(state,n)))return
  const trial=structuredClone(previous)
  for(const member of members){const worker=state.operators[member]!;if(working(worker)&&worker.currentRoom!==worker.room)return;if(worker.currentRoom!==worker.room||worker.currentIndex!==worker.index)(trial[worker.room]??=Array(state.plan[worker.room]!.length).fill('Current'))[worker.index]=member}
  const shadow=projectMowerArrangements(state,[]),recalled=alphaRebalanceClosingDorms(shadow,trial,members)
  if([...recalled].some(n=>required.has(n)||protectedNames.has(n)||options.isMasteryBusy?.(n)||protectedRest(state,n)))return
  const projected=projectMowerArrangements(original,[trial])
  if(Object.values(state.operators).some(worker=>worker.isHigh()&&worker.isResting()&&!projected.operators[worker.name]!.currentRoom&&!recalled.has(worker.name)))return
  return [trial,projected]
 }
 const ordered=[...candidates].sort((a,b)=>{const x=data.operators[a]!,y=data.operators[b]!,fia=options.fiaTargets??[];return Number(x.room.startsWith('dorm'))-Number(y.room.startsWith('dorm'))||Number(!fia.includes(a))-Number(!fia.includes(b))||Number(['factory','train'].includes(x.currentRoom))-Number(['factory','train'].includes(y.currentRoom))||(x.currentMood(data.nowMicros)-x.lowerLimit)-(y.currentMood(data.nowMicros)-y.lowerLimit)})
 const freeMatching=(allowPartial=true)=>{
  selected.clear()
  const choices=Object.fromEntries(ordered.filter(n=>!autoFree(data.operators[n]!)).map(n=>[n,mowerReplacementCandidates(data.operators[n]!,data.operators,data.policy,data.nowMicros).filter(cover=>available(data,cover,data.operators[n]!))]))
  const matching=mowerMatchReplacements(choices,allowPartial);if(matching)Object.values(matching).forEach(n=>selected.add(n));return matching
 }
 let matching=freeMatching()!
 for(const name of ordered){
  const worker=data.operators[name]!;if(autoFree(worker)||name in matching)continue
  const occupied=mowerReplacementCandidates(worker,data.operators,data.policy,data.nowMicros).flatMap(cover=>{
   const op=data.operators[cover];if(!op||!eligible(data,cover,worker)||!working(op)||op.currentRoom==='train')return []
   const owner=data.operators[data.plan[op.currentRoom]?.[op.currentIndex]??'']
   return owner&&!required.has(owner.name)&&!protectedNames.has(owner.name)&&!working(owner)&&owner.replacement.includes(cover)?[{cover,owner}]:[]
  })
  let resolved=false
  for(const {owner} of occupied){const alternate=mowerReplacementCandidates(owner,data.operators,data.policy,data.nowMicros).find(n=>!coverNames.has(n)&&available(data,n,owner));if(!alternate)continue;(plan[owner.room]??=Array(data.plan[owner.room]!.length).fill('Current'))[owner.index]=alternate;data=projectMowerArrangements(original,[plan]);resolved=true;break}
  if(!resolved)for(const {cover,owner} of occupied){const result=recall(data,plan,owner.name);if(!result||!available(result[1],cover,worker))continue;[plan,data]=result;resolved=true;break}
  if(!resolved)return
  matching=freeMatching()!;if(!(name in matching))return
 }
 if(!freeMatching(false))return
 const canRest=(state:MowerSchedulingData)=>{const trial=projectMowerArrangements(state,[]),result:MowerTaskPlan={};mowerGetRestingPlan(trial,[...candidates],[],result,options);return !!Object.keys(result).length}
 if(canRest(data))return plan
 const beds=[...data.dorms].sort((a,b)=>(data.operators[b.name]?.mood??25)-(data.operators[a.name]?.mood??25))
 for(const bed of beds){const op=data.operators[bed.name];if(!op?.isHigh()||!op.isResting()||bed.timeMicros!==undefined&&bed.timeMicros<data.nowMicros||!data.effectiveFreeSlot(bed))continue;const result=recall(data,plan,op.name);if(!result||JSON.stringify(result[0])===JSON.stringify(plan))continue;[plan,data]=result;if(canRest(data))return plan}
}
