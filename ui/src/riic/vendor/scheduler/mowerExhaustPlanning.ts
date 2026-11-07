// Port of default exhaust_replacement.plan_exhaust_support.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerReplacementCandidates} from './mowerOperatorState'
import {projectMowerArrangements} from './mowerObservations'
import {mowerGetRestingPlan,type MowerRestingOptions} from './mowerOrdinaryPlanning'
import {mowerIsDormReplacement} from './mowerCorrection'
import type {MowerTaskPlan} from './mowerTaskQueue'
import {planMowerAlphaExhaustSupport} from './mowerAlphaExhaustSupport'
export function planMowerExhaustSupport(original:MowerSchedulingData,candidates:string[],options:MowerRestingOptions={}):MowerTaskPlan|undefined {
 if(original.alpha)return planMowerAlphaExhaustSupport(original,candidates,options)
 const protectedNames=original.busyRestingNames,required=new Set(candidates)
 const coverNames=new Set(candidates.flatMap(n=>original.operators[n]!.replacement.filter(n=>n!=='Free')))
 let plan:MowerTaskPlan={},data=projectMowerArrangements(original,[])
 const selected=new Set<string>()
 const eligible=(state:MowerSchedulingData,name:string)=>{
  const op=state.operators[name];return !!op&&!op.isHigh()&&!protectedNames.has(name)&&!selected.has(name)&&!required.has(name)&&!state.excludedCandidates.has(name)&&!mowerIsDormReplacement(state,name)&&!options.isMasteryBusy?.(name)
 }
 const available=(state:MowerSchedulingData,name:string)=>eligible(state,name)&&(!state.operators[name]!.currentRoom||state.operators[name]!.isResting())
 const working=(state:MowerSchedulingData,name:string)=>!!state.operators[name]!.currentRoom&&!state.operators[name]!.isResting()
 const protectedRest=(state:MowerSchedulingData,name:string)=>{
  const op=state.operators[name]!
  const group=op.group?state.group(op.group).map(n=>state.operators[n]!):[]
  return op.isResting()&&(op.restInFull&&op.exhaustRequire||!!op.group&&group.some(o=>o.restInFull)&&group.some(o=>o.exhaustRequire))
 }
 const recall=(state:MowerSchedulingData,previous:MowerTaskPlan,name:string):[MowerTaskPlan,MowerSchedulingData]|undefined=>{
  const op=state.operators[name]!,members=op.group?state.group(op.group):[name]
  if(members.some(n=>required.has(n)||protectedNames.has(n)||options.isMasteryBusy?.(n)||protectedRest(state,n)))return undefined
  const trial=structuredClone(previous)
  for(const member of members){
   const worker=state.operators[member]!
   if(working(state,member)&&worker.currentRoom!==worker.room)return undefined
   if(worker.currentRoom!==worker.room||worker.currentIndex!==worker.index)(trial[worker.room]??=Array(state.plan[worker.room]!.length).fill('Current'))[worker.index]=member
  }
  const projected=projectMowerArrangements(original,[trial])
  if(Object.values(state.operators).some(worker=>worker.isHigh()&&worker.isResting()&&!projected.operators[worker.name]!.currentRoom&&!members.includes(worker.name)))return undefined
  return [trial,projected]
 }
 const ordered=[...candidates].sort((a,b)=>{
  const x=data.operators[a]!,y=data.operators[b]!,fia=options.fiaTargets??[]
  return Number(x.room.startsWith('dorm'))-Number(y.room.startsWith('dorm'))||Number(!fia.includes(a))-Number(!fia.includes(b))||Number(['factory','train'].includes(x.currentRoom))-Number(['factory','train'].includes(y.currentRoom))||(x.currentMood(data.nowMicros)-x.lowerLimit)-(y.currentMood(data.nowMicros)-y.lowerLimit)
 })
 for(const name of ordered){
  const worker=data.operators[name]!,covers=mowerReplacementCandidates(worker,data.operators,data.policy,data.nowMicros)
  const free=covers.find(n=>available(data,n));if(free){selected.add(free);continue}
  const occupied=covers.flatMap(cover=>{
   if(!eligible(data,cover)||!working(data,cover)||data.operators[cover]!.currentRoom==='train')return []
   const op=data.operators[cover]!,ownerName=data.plan[op.currentRoom]?.[op.currentIndex],owner=ownerName?data.operators[ownerName]:undefined
   return owner&&!required.has(owner.name)&&!protectedNames.has(owner.name)&&!working(data,owner.name)&&owner.replacement.includes(cover)?[{cover,owner}]:[]
  })
  let resolved=false
  for(const {cover,owner} of occupied){
   const alternate=mowerReplacementCandidates(owner,data.operators,data.policy,data.nowMicros).find(n=>!coverNames.has(n)&&available(data,n))
   if(!alternate)continue
   (plan[owner.room]??=Array(data.plan[owner.room]!.length).fill('Current'))[owner.index]=alternate
   data=projectMowerArrangements(original,[plan]);selected.add(cover);resolved=true;break
  }
  if(!resolved)for(const {cover,owner} of occupied){
   const result=recall(data,plan,owner.name);if(!result||!available(result[1],cover))continue
   ;[plan,data]=result;selected.add(cover);resolved=true;break
  }
  if(!resolved)return undefined
 }
 selected.clear()
 for(const name of ordered){
  const cover=mowerReplacementCandidates(data.operators[name]!,data.operators,data.policy,data.nowMicros).find(n=>available(data,n))
  if(!cover)return undefined;selected.add(cover)
 }
 const canRest=(state:MowerSchedulingData)=>{
  const trial=projectMowerArrangements(state,[]),result:MowerTaskPlan={}
  mowerGetRestingPlan(trial,[...candidates],[],result,options);return Object.keys(result).length>0
 }
 if(canRest(data))return plan
 const beds=[...data.dorms].sort((a,b)=>(data.operators[b.name]?.mood??25)-(data.operators[a.name]?.mood??25))
 for(const bed of beds){
  const op=data.operators[bed.name]
  if(!op?.isHigh()||!op.isResting()||bed.timeMicros!==undefined&&bed.timeMicros<data.nowMicros||!data.effectiveFreeSlot(bed))continue
  const result=recall(data,plan,op.name);if(!result||JSON.stringify(result[0])===JSON.stringify(plan))continue
  ;[plan,data]=result;if(canRest(data))return plan
 }
 return undefined
}
