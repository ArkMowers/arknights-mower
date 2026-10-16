import {mowerExhaustGroups} from './mowerExhaustPolicy'
import {mowerWorkingReplacementBlocked,mowerSameGroupPrimaryReplacement,mowerRestingBindingGroups,mowerSharedReplacements,normalizeMowerSharedArrangement,mowerArrangementGroupTransitions,commitMowerGroupShifts} from './mowerSharedGroups'
// Port of default plan_solver/resting/_get_resting_plan_legacy/try_reorder.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {MowerExitError} from './mowerNativeErrors'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'
import {MowerOperatorState,mowerReplacementCandidates} from './mowerOperatorState'
import {MowerDormState,type MowerSchedulingData} from './mowerSchedulingData'
import {mowerActiveHighRestingCount,mowerAvailableFree,mowerAssignDorm,mowerAssignDormGroup,mowerAverageMood,mowerStandbyCandidates} from './mowerDormAssignment'
import {planMowerMetadata} from './mowerMetadata'
import {mowerDormCandidateMood} from './mowerAlphaCandidates'
import {alphaPosition,alphaDormResidents,alphaRestoreDisplaced,alphaRestingTier,alphaSlotTakable,mowerMatchReplacements,alphaPrioritizeRecovery} from './mowerAlphaDorm'
import {MowerTask,MOWER_TASK_TYPES as T,type MowerTaskPlan,type MowerTaskQueue,fromMowerMicros,toMowerMicros} from './mowerTaskQueue'
export interface MowerRestingOptions {
 urgentExhaust?:boolean
 coordinationRates?:(data:MowerSchedulingData)=>import('./mowerReplacementCoordination').MowerCoordinationRates|undefined
 returning?:Set<string>;returningGroups?:Set<string>;tasks?:MowerTask[]
 fiaTargets?:string[];hasActiveMastery?:boolean;isMasteryBusy?:(name:string)=>boolean
 isDormReplacement?:(name:string)=>boolean;onBlocked?:(names:string[])=>void;onException?:(error:unknown)=>void
 reservedNames?:ReadonlySet<string>;reservedSlots?:ReadonlySet<string>;priorityScheduling?:MowerTaskSchedulingOptions
 dormAdmissions?:Map<string,string>
}
export function mowerGetRestingPlan(data:MowerSchedulingData,names:string[],existingReplacements:string[],plan:MowerTaskPlan,options:MowerRestingOptions={}):boolean {
 if(data.alpha)return alphaGetRestingPlan(data,names,existingReplacements,plan,options)
 const dormAgents=names.filter(name=>data.operators[name]!.room.startsWith('dorm'))
 const agents=names.filter(name=>!dormAgents.includes(name)),fia=options.fiaTargets??[]
 agents.sort((a,b)=>{
  const x=data.operators[a]!,y=data.operators[b]!
  return Number(!fia.includes(a))-Number(!fia.includes(b))||Number(['factory','train'].includes(x.currentRoom))-Number(['factory','train'].includes(y.currentRoom))||(x.currentMood(data.nowMicros)-x.lowerLimit)-(y.currentMood(data.nowMicros)-y.lowerLimit)
 })
 agents.push(...dormAgents)
 const replacements:string[]=[],next:MowerTaskPlan={}
 for(const name of agents){
  const op=data.operators[name]!
  if(!data.plan[op.room]||data.getDormByName(name))return false
  const candidate=mowerReplacementCandidates(op,data.operators,data.policy,data.nowMicros).find(candidate=>{
   const target=data.operators[candidate]!
   return !(target.currentRoom&&!target.isResting())&&!data.excludedCandidates.has(candidate)&&!options.isMasteryBusy?.(candidate)&&!existingReplacements.includes(candidate)&&!replacements.includes(candidate)&&!options.isDormReplacement?.(candidate)&&(op.room.startsWith('dorm')||target.currentRoom!==op.room)
  })
  if(candidate===undefined)return false
  if(data.adjustForRunOrders===false&&plan[op.room]&&![candidate,'Current'].includes(plan[op.room]![op.index]!))return false
  replacements.push(candidate);(next[op.room]??=Array(data.plan[op.room]!.length).fill('Current'))[op.index]=candidate
 }
 const resting=agents.filter(name=>!data.operators[name]!.workaholic&&!data.operators[name]!.room.startsWith('dorm'))
 // Selected replacements leave these physical beds in this same arrangement.
 // Reserve the complete incoming group before committing any changes.
 let departing:Set<string>|undefined
 if(data.adjustForRunOrders===false){
  departing=new Set()
  const selected=new Set([...existingReplacements,...replacements])
  for(const [room,row] of Object.entries({...plan,...next})){
   for(let index=0;index<row.length;index++){
    // A committed destination wins, exactly as in the merge below.
    const committed=plan[room]?.[index]
    const name=committed&&committed!=='Current'?committed:next[room]?.[index]??'Current'
    const target=data.operators[name]
    if(selected.has(name)&&target&&(target.currentRoom!==room||target.currentIndex!==index))departing.add(name)
   }
  }
 }
 if(mowerAssignDormGroup(data,resting,undefined,departing)===undefined)return false
 existingReplacements.push(...replacements)
 for(const [room,names] of Object.entries(next)){
  if(!plan[room]){plan[room]=names;continue}
  for(const [index,name] of names.entries())if(plan[room]![index]==='Current'&&name!=='Current')plan[room]![index]=name
 }
 return true
}
function alphaGetRestingPlan(data:MowerSchedulingData,names:string[],existing:string[],plan:MowerTaskPlan,options:MowerRestingOptions):boolean{
 if(names.some(name=>data.reservedProductReplacements.has(name))||mowerWorkingReplacementBlocked(data,names,plan))return false
 const transitions={...mowerArrangementGroupTransitions(data,plan),...Object.fromEntries(names.map(name=>data.operators[name]!).filter(op=>data.isGroupShiftAnchor(op)&&op.group).map(op=>[op.group,true]))}
 const shared=Object.values(data.operators).filter(op=>op.multiGroup),previousState=data.groupShiftState
 const previousBindings=shared.map(op=>({op,group:op.group,replacement:op.replacement}))
 try {
  if(shared.some(op=>op.groupBindings.some(binding=>binding.group in transitions))){
   data.groupShiftState={...previousState}
   commitMowerGroupShifts(data,transitions)
  }
  const agents=[...names].sort((a,b)=>{
   const x=data.operators[a]!,y=data.operators[b]!,fia=options.fiaTargets??[]
   return Number(x.room.startsWith('dorm'))-Number(y.room.startsWith('dorm'))||Number(!fia.includes(a))-Number(!fia.includes(b))||Number(['factory','train'].includes(x.currentRoom))-Number(['factory','train'].includes(y.currentRoom))||(x.currentMood(data.nowMicros)-x.lowerLimit)-(y.currentMood(data.nowMicros)-y.lowerLimit)
  })
  const choices:Record<string,string[]>={},next:MowerTaskPlan={}
  const supersededCovers=new Set(shared.flatMap(op=>{
   const previous=plan[op.room]?.[op.index]
   return previous&&op.groupBindings.some(binding=>binding.group in transitions)&&!mowerSharedReplacements(op,mowerRestingBindingGroups(data,op,transitions)).includes(previous)?[previous]:[]
  }))
  for(const name of agents){
   const op=data.operators[name]!
   if(!data.plan[op.room]||!op.multiGroup&&data.getDormByName(name))return false
   const candidates=op.multiGroup?Object.assign(new MowerOperatorState(op),{replacement:mowerSharedReplacements(op,mowerRestingBindingGroups(data,op,transitions))}):op
   if(op.room.startsWith('dorm')&&op.group&&candidates.replacement.includes('Free')){const resident=op.multiGroup?data.dorms.find(b=>b.position[0]===op.room&&b.position[1]===op.index)?.name:undefined;(next[op.room]??=Array(data.plan[op.room]!.length).fill('Current'))[op.index]=resident&&resident!==op.name?resident:'Free';continue}
   choices[name]=mowerReplacementCandidates(candidates,data.operators,data.policy,data.nowMicros).filter(n=>{
    const target=data.operators[n];if(!target)return false
    const inSlot=target.currentRoom===op.room&&target.currentIndex===op.index,sameGroup=op.multiGroup?mowerRestingBindingGroups(data,op,transitions).some(group=>mowerSameGroupPrimaryReplacement(data,op,n,group)):mowerSameGroupPrimaryReplacement(data,op,n),departing=sameGroup&&agents.includes(n)&&target.currentRoom===target.room&&target.currentIndex===target.index
    return (!target.currentRoom||target.isResting()||inSlot||departing)&&(op.room.startsWith('dorm')||!data.replacementExhausted(n))&&!data.excludedCandidates.has(n)&&!data.reservedProductReplacements.has(n)&&!options.isMasteryBusy?.(n)&&(!existing.includes(n)||supersededCovers.has(n)||plan[op.room]?.[op.index]===n)&&(!options.isDormReplacement?.(n)||inSlot||departing)&&(op.room.startsWith('dorm')||target.currentRoom!==op.room||sameGroup&&agents.includes(n)||inSlot)
   })
  }
  const match=mowerMatchReplacements(choices);if(!match)return false
  for(const [name,cover] of Object.entries(match)){const op=data.operators[name]!;(next[op.room]??=Array(data.plan[op.room]!.length).fill('Current'))[op.index]=cover}
  const combined=structuredClone(plan);for(const [room,row] of Object.entries(next)){const target=combined[room]??=Array(data.plan[room]!.length).fill('Current');row.forEach((name,index)=>{if(name!=='Current')target[index]=name})}
  if(!normalizeMowerSharedArrangement(data,combined,transitions))return false
  if(Object.values(data.operators).some(op=>op.multiGroup))Object.assign(next,combined)
  const assignedCovers=new Set(Object.values(next).flat())
  const reservedResting=new Set(options.dormAdmissions?.values())
  const previous=alphaDormResidents(data),resting=agents.filter(name=>!data.operators[name]!.workaholic&&!data.operators[name]!.room.startsWith('dorm')&&!assignedCovers.has(name)&&!data.getDormByName(name)&&!reservedResting.has(name))
  const admissions=mowerAssignDormGroup(data,resting,new Set(Object.keys(transitions).filter(group=>transitions[group])),undefined,combined,options.reservedSlots)
  if(admissions===undefined)return false
  const confirmed=new Map(options.dormAdmissions)
  for(const bed of admissions)confirmed.set(alphaPosition(...bed.position),bed.name)
  alphaRestoreDisplaced(data,previous,next,options.tasks??[],confirmed)
  if(options.dormAdmissions)for(const [position,name] of confirmed)options.dormAdmissions.set(position,name)
  existing.splice(0,existing.length,...new Set([...existing.filter(name=>!supersededCovers.has(name)),...Object.values(match)]))
  for(const [room,names] of Object.entries(next)){if(!plan[room])plan[room]=names;else names.forEach((name,index)=>{if(name!=='Current'&&(plan[room]![index]==='Current'||data.operators[data.plan[room]?.[index]??'']?.multiGroup))plan[room]![index]=name})}
  return true
 }finally{
  data.groupShiftState=previousState
  for(const {op,group,replacement} of previousBindings){op.group=group;op.replacement=replacement}
 }
}
export function mowerResting(data:MowerSchedulingData,queue:MowerTaskQueue,options:MowerRestingOptions={}):MowerTaskPlan {
 return resting(data,queue,options,false)
}
function resting(data:MowerSchedulingData,queue:MowerTaskQueue,options:MowerRestingOptions,metadataPrepared:boolean):MowerTaskPlan {
 options={...options,dormAdmissions:new Map()}
 if(data.policy.experimentalDormLogic)throw new Error('Experimental ordinary resting requires its source port')
 if(data.alpha)Object.values(data.operators).forEach(op=>data.updateStandbyLowPriority(op))
 const moods=new Map(Object.values(data.operators).map(op=>[op.name,data.alpha?mowerDormCandidateMood(data,op.name):op.currentMood(data.nowMicros)]))
 const total=Object.values(data.operators).filter(op=>(op.isHigh()||!data.alpha&&!op.currentRoom&&!op.room)&&!op.room.startsWith('dorm')&&!(op.group&&data.canStandby(op))).sort((a,b)=>data.alpha?0:a.currentMood(data.nowMicros)-b.currentMood(data.nowMicros))
 total.sort((a,b)=>Number(moods.get(a.name)===undefined)-Number(moods.get(b.name)===undefined)||((moods.get(a.name)??0)-a.lowerLimit)-((moods.get(b.name)??0)-b.lowerLimit))
 if(!metadataPrepared)planMowerMetadata(data,queue)
 const current=mowerActiveHighRestingCount(data),effective=data.dorms.filter(b=>data.effectiveFreeSlot(b)).length
 const ideal=mowerAverageMood(data)>data.policy.restingThreshold*data.policy.rescueThreshold?Math.min(4,effective):effective
 const ordinaryRequests:string[]=[],replacements:string[]=[],plan:MowerTaskPlan={},used=new Set<number>(),attempted=new Set<string>();let highDone=false
 const exhaustGroups=mowerExhaustGroups(data)
 for(const op of [...total.filter(op=>op.isHigh()),...total.filter(op=>!op.isHigh())]){
  if(data.alpha&&(moods.get(op.name)===undefined||data.reservedProductReplacements.has(op.name)||options.returning?.has(op.name)||options.returningGroups?.has(op.group)||op.group&&data.group(op.group).some(n=>options.returning?.has(n))||replacements.includes(op.name)||alphaRestingTier(data,op.name)===7))continue
  if(op.isHigh()&&!op.workshop){
   const standby=mowerStandbyCandidates(data,op.group?data.group(op.group):[op.name])
   const canPreempt=data.alpha&&alphaRestingTier(data,op.name)<=2&&data.dorms.some(b=>b.name&&alphaRestingTier(data,b.name)>alphaRestingTier(data,op.name)&&alphaSlotTakable(data,b,op.name))
   const groupBed=data.alpha&&op.group&&(data.dorms.some(b=>b.autoFree&&data.operators[data.plan[b.position[0]]?.[b.position[1]]??'']?.group===op.group)||data.groupDorms.some(b=>data.operators[data.plan[b.position[0]]?.[b.position[1]]??'']?.group===op.group))
   if(highDone&&!standby.size&&!canPreempt&&!groupBed)continue
   if(!standby.size&&!canPreempt&&!groupBed&&current+replacements.length>=ideal&&mowerAvailableFree(data)===0){highDone=true;continue}
  }else if(mowerAvailableFree(data,'low')===0)break
  if(op.multiGroup&&(!op.independentRest||mowerRestingBindingGroups(data,op).length)||op.workaholic||op.isResting()||data.isStandby(op.name)||op.currentRoom==='factory'||op.room==='factory'||options.hasActiveMastery&&[op.room,op.currentRoom].includes('train'))continue
  const mood=moods.get(op.name)!
  if((data.alpha?op.customMoodLimit:op.restMoodLimit)?mood>=op.upperLimit:op.upperLimit-mood<2)continue
  const threshold=(op.upperLimit-op.lowerLimit)*data.policy.restingThreshold+op.lowerLimit
  if(op.exhaustRequire||mood>(data.alpha&&op.customMoodLimit?threshold:Math.floor(threshold)))continue
  if(!op.isHigh()){mowerAssignDorm(data,op.name,used);continue}
  if(op.group&&exhaustGroups.has(op.group))continue
  if((data.alpha||data.adjustForRunOrders===false)&&op.group){if(attempted.has(op.group))continue;attempted.add(op.group)}
  const members=op.group?data.shiftGroupMembers(op.group):[op.name]
  if(!mowerGetRestingPlan(data,[...members],replacements,plan,{...options,tasks:queue.tasks})){
   options.onBlocked?.(members)
   if(data.alpha&&!queue.tasks.some(task=>task.type===T.EXHAUST_OFF&&members.some(name=>task.metadata.split(',').includes(name)))){
    const task=new MowerTask({type:T.EXHAUST_OFF,metadata:members.join(',')});task.ordinaryCoordination=true;task.coordinationRequestNames=[...members];task.timeMicros=data.nowMicros;queue.tasks.push(task)
   }
  }else ordinaryRequests.push(op.name)
 }
 if(Object.keys(plan).length){const task=new MowerTask({plan,type:T.SHIFT_OFF});task.ordinaryCoordination=ordinaryRequests.length>0;task.coordinationRequestNames=ordinaryRequests;task.timeMicros=data.nowMicros;queue.tasks.push(task)}
 return plan
}
export function mowerTryReorder(data:MowerSchedulingData,newPlan:MowerTaskPlan):MowerTaskPlan|undefined {
 if(data.alpha){
  const assigned=new Set(Object.values(newPlan).flat());for(const bed of data.dorms)if(assigned.has(bed.name))bed.reset()
  const transitions=mowerArrangementGroupTransitions(data,newPlan),active=new Set(Object.keys(transitions).filter(group=>transitions[group])),inactive=new Set(Object.keys(transitions).filter(group=>!transitions[group]))
  const destinations=new Set(data.dorms.filter(b=>data.effectiveFreeSlot(b,inactive,active)&&b.name).map(b=>b.position[0]+'\0'+b.position[1])),result:MowerTaskPlan={}
  for(const bed of data.dorms)if(data.effectiveFreeSlot(bed,inactive,active)&&bed.name){const op=data.operators[bed.name]!,[room,index]=bed.position;if(op.currentRoom!==room||op.currentIndex!==index){(result[room]??=Array(data.plan[room]!.length).fill('Current'))[index]=bed.name;if(data.dynamicDormPosition(op.currentRoom,op.currentIndex)&&!destinations.has(op.currentRoom+'\0'+op.currentIndex))(result[op.currentRoom]??=Array(data.plan[op.currentRoom]!.length).fill('Current'))[op.currentIndex]='Free'}}
  return alphaPrioritizeRecovery(data,result,newPlan)
 }
 if(data.policy.experimentalDormLogic)throw new Error('Experimental recovery prioritization requires its source port')
 const assigned=new Set(Object.values(newPlan).flat())
 for(const bed of data.dorms)if(assigned.has(bed.name))bed.reset()
 const dorms=data.dorms.map(b=>new MowerDormState([...b.position],b.name,b.timeMicros,b.autoFree))
 // The room picker converts full-mood non-residents to Free, so moving one by name cannot settle.
 for(const bed of dorms){const op=data.operators[bed.name];if(op&&op.mood>=op.upperLimit&&!op.room.startsWith('dorm'))bed.reset()}
 const vip=Object.keys(data.plan).filter(room=>room.startsWith('dorm')).length;if(!vip)return undefined
 const effective=dorms.map((bed,index)=>({bed,index})).filter(({bed})=>data.effectiveFreeSlot(bed)).map(({index})=>index)
 for(const [index,bed] of dorms.entries())if(!effective.includes(index))bed.reset()
 const ranking=(name:string)=>{
  const op=data.operators[name];return op?.isHigh()?op.restingPriority==='high'?'high':op.restingPriority==='standby'?'standby':'normal':'low'
 }
 const priority=data.restingPriorityNames,rank={high:priority.length,normal:priority.length+1,standby:priority.length+2,low:priority.length+3}
 const info=effective.map(index=>({name:dorms[index]!.name,time:dorms[index]!.timeMicros,index}))
 info.sort((a,b)=>{
  const p=(name:string)=>name&&priority.includes(name)?priority.indexOf(name):rank[ranking(name)]
  return p(a.name)-p(b.name)||a.index-b.index
 })
 effective.forEach((index,i)=>{dorms[index]!.name=info[i]!.name;dorms[index]!.timeMicros=info[i]!.time})
 const result:MowerTaskPlan={}
 for(const bed of dorms)if(bed.name){
  const op=data.operators[bed.name]!,[room,index]=bed.position
  if(op.currentRoom!==room||op.currentIndex!==index)(result[room]??=Array(5).fill('Current'))[index]=bed.name
 }
 return result
}
export function planMowerOrdinary(data:MowerSchedulingData,queue:MowerTaskQueue,options:MowerRestingOptions={}):MowerTaskPlan|undefined {
 let plan:MowerTaskPlan={}
 try {
  if(queue.find({type:T.SHIFT_OFF}))return undefined
  planMowerMetadata(data,queue)
  plan=resting(data,queue,options,!data.alpha)
 }catch(error){
  // Native plan_solver catches every Exception here except MowerExit, then reorders.
  if(error instanceof MowerExitError)throw error
  options.onException?.(error)
 }
 const reorder=mowerTryReorder(data,plan)
 if(reorder&&Object.keys(reorder).length){
  if(Object.keys(plan).length)for(const [room,names] of Object.entries(reorder)){
   if(!plan[room])plan[room]=names
   else for(const [index,name] of names.entries())if(name!=='Current')plan[room]![index]=name
  }else{const task=new MowerTask({plan:reorder});task.timeMicros=data.nowMicros;queue.tasks.push(task)}
 }
 return plan
}
export function mowerPlanningHasNearTask(data:MowerSchedulingData,queue:MowerTaskQueue,options:MowerTaskSchedulingOptions={}):boolean {return !!queue.find({time:fromMowerMicros(data.nowMicros+toMowerMicros(15/3600)),ignoreRunOrders:(options.adjustForRunOrders??data.adjustForRunOrders)===false})}
