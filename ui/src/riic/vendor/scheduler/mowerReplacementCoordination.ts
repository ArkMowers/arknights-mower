import {mowerDormCandidateMood} from './mowerSchedulingMood'
import {mowerUrgentRecallBlocked} from './mowerUrgentRecovery'
import {alphaPosition,mowerMatchReplacements} from './mowerAlphaDorm'
import {mowerGroupRecoveryDeadline,mowerRecoveryReady} from './mowerGroupRecovery'
import {hasObservedFullMood,mowerReplacementCandidates,rescueMoodThreshold,MowerOperatorState} from './mowerOperatorState'
import {projectMowerArrangements} from './mowerObservations'
import {alphaSupportSwapMicros,protectMowerAlphaTasks} from './mowerAlphaTaskProtection'
import {mowerWorkingReplacementApplies} from './mowerWorkingReplacement'
import {mowerPlanningWakeThreshold} from './mowerPlanningWake'
import type {MowerRestingOptions} from './mowerOrdinaryPlanning'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerRestingBindingGroups,mowerSharedReplacements,mowerSameGroupPrimaryReplacement} from './mowerSharedGroups'
import {toMowerMicros,MowerTask,MOWER_TASK_TYPES as T,type MowerTaskPlan,type MowerTaskType} from './mowerTaskQueue'

export interface MowerCoordinationRates {work:Readonly<Record<string,number>>;recovery:Readonly<Record<string,number>>}
export interface MowerRecallRecheckWindow {untilMicros?:number;notBeforeMicros:number;observation?:{timeMicros:number;limits:Readonly<Record<string,number>>}}
function replacements(data:MowerSchedulingData,op:MowerOperatorState,required:ReadonlySet<string>=new Set()):string[]{
 const transitions=Object.fromEntries([...required].map(name=>data.operators[name]!).filter(worker=>worker.group&&data.isGroupShiftAnchor(worker)).map(worker=>[worker.group,true]))
 return op.multiGroup?mowerSharedReplacements(op,mowerRestingBindingGroups(data,op,transitions)):op.replacement
}
/** Keep the native same-group primary exception; unrelated primaries remain unavailable. */
export function mowerCoordinationPrimaryReplacement(data:MowerSchedulingData,owner:MowerOperatorState,name:string,required:ReadonlySet<string>):boolean {
 const transitions=Object.fromEntries([...required].map(id=>data.operators[id]!).filter(op=>op?.group&&data.isGroupShiftAnchor(op)).map(op=>[op.group,true]))
 return (owner.multiGroup?mowerRestingBindingGroups(data,owner,transitions):[owner.group]).some(group=>mowerSameGroupPrimaryReplacement(data,owner,name,group))
}
function eligible(data:MowerSchedulingData,name:string,owner:MowerOperatorState,options:MowerRestingOptions,required:ReadonlySet<string>=new Set()):boolean {
 const cover=data.operators[name]
 return !!cover&&(!cover.isHigh()||mowerCoordinationPrimaryReplacement(data,owner,name,required))&&!data.busyRestingNames.has(name)&&!options.reservedNames?.has(name)&&!data.reservedProductReplacements.has(name)&&!data.excludedCandidates.has(name)&&!options.isMasteryBusy?.(name)&&!data.dormReplacementForSlot(name,cover.currentRoom,cover.currentIndex)&&!options.reservedSlots?.has(alphaPosition(cover.currentRoom,cover.currentIndex))&&(owner.room.startsWith('dorm')||!data.replacementExhausted(name,owner))
}
function coveredOwner(data:MowerSchedulingData,name:string):MowerOperatorState|undefined {
 const cover=data.operators[name]
 if(!cover?.currentRoom||cover.isResting()||cover.currentRoom==='train')return
 const owner=data.operators[data.plan[cover.currentRoom]?.[cover.currentIndex]??'']
 if(owner&&owner.name!==name&&(!owner.currentRoom||owner.isResting())&&!data.busyRestingNames.has(owner.name))return owner
}
/** Include every resting owner reached through a shared cover, not only the first conflict. */
export function planMowerReplacementHandoff(data:MowerSchedulingData,candidates:string[],options:MowerRestingOptions={}):MowerTaskPlan|undefined {
 const required=new Set(candidates),owners=new Map<string,MowerOperatorState>(),choices:Record<string,string[]>={}
 const visit=(name:string):void=>{
  if(owners.has(name))return
  const owner=data.operators[name];if(!owner||!data.plan[owner.room]||options.reservedNames?.has(name)||options.reservedSlots?.has(alphaPosition(owner.room,owner.index)))return
  owners.set(name,owner)
  const raw=replacements(data,owner,required)
  if(owner.room.startsWith('dorm')&&raw.includes('Free')){choices[name]=[];return}
  const ranked=mowerReplacementCandidates(new MowerOperatorState({...owner,replacement:raw}),data.operators,data.policy,data.nowMicros)
  choices[name]=ranked.filter(cover=>{
   const sameGroup=mowerCoordinationPrimaryReplacement(data,owner,cover,required)
   if(required.has(cover)&&!sameGroup||!eligible(data,cover,owner,options,required))return false
   const worker=data.operators[cover]!
   if(!worker.currentRoom||worker.isResting()||sameGroup&&required.has(cover)&&worker.currentRoom===worker.room&&worker.currentIndex===worker.index)return true
   const occupant=coveredOwner(data,cover)
   if(!occupant||options.reservedSlots?.has(alphaPosition(occupant.room,occupant.index))||!replacements(data,occupant,required).includes(cover))return false
   visit(occupant.name);return true
  })
 }
 candidates.forEach(visit)
 // Existing owners keep their preferred choices unless a constrained requester needs them.
 const ordered=Object.fromEntries([...owners].filter(([,op])=>!(op.room.startsWith('dorm')&&replacements(data,op,required).includes('Free'))).sort(([a],[b])=>Number(required.has(a))-Number(required.has(b))).map(([name])=>[name,choices[name]!]))
 if(candidates.some(name=>!owners.has(name)))return
 const matching=mowerMatchReplacements(ordered)
 if(!matching)return
 const plan:MowerTaskPlan={}
 for(const [name,cover] of Object.entries(matching))if(!required.has(name)){
  const owner=owners.get(name)!
  if(data.currentOperator(owner.room,owner.index)?.name!==cover)(plan[owner.room]??=Array(data.plan[owner.room]!.length).fill('Current'))[owner.index]=cover
 }
 return plan
}
/** Restore preferences from the effective plan only; never move a working preferred cover. */
export function planMowerPreferredReplacementRestore(data:MowerSchedulingData,protectedNames:ReadonlySet<string>=new Set(),protectedSlots:ReadonlySet<string>=new Set()):MowerTaskPlan {
 const plan:MowerTaskPlan={};let state=data,changed=true
 while(changed){
  changed=false
  for(const owner of Object.values(state.operators)){
   if(!owner.isHigh()||owner.room.startsWith('dorm')||owner.currentRoom&&!owner.isResting()||protectedNames.has(owner.name)||state.busyRestingNames.has(owner.name)||protectedSlots.has(alphaPosition(owner.room,owner.index)))continue
   const current=state.currentOperator(owner.room,owner.index),ordered=replacements(state,owner),index=current?ordered.indexOf(current.name):-1
   if(index<=0||!current||protectedNames.has(current.name)||!eligible(state,current.name,owner,{}))continue
   const preferred=ordered.slice(0,index).find(name=>!protectedNames.has(name)&&eligible(state,name,owner,{reservedSlots:protectedSlots})&&(!state.operators[name]!.currentRoom||state.operators[name]!.isResting()))
   if(!preferred)continue
   ;(plan[owner.room]??=Array(state.plan[owner.room]!.length).fill('Current'))[owner.index]=preferred
   state=projectMowerArrangements(data,[plan]);changed=true
  }
 }
 return plan
}
/** A cover/bed conflict connects all group peers and all owners sharing any candidate. */
export function mowerReplacementDependencyNames(data:MowerSchedulingData,seeds:Iterable<string>):Set<string>{
 const names=new Set(seeds);let changed=true
 while(changed){
  changed=false
  const add=(name:string)=>{if(name&&!names.has(name)){names.add(name);changed=true}}
  for(const op of Object.values(data.operators)){
   const covers=replacements(data,op),peers=op.group?data.shiftGroupMembers(op.group):[]
   if(names.has(op.name)||covers.some(name=>names.has(name))||peers.some(name=>names.has(name))){add(op.name);covers.filter(name=>name!=='Free').forEach(add);peers.forEach(add)}
  }
 }
 return names
}
function recallMood(data:MowerSchedulingData,op:MowerOperatorState):number|undefined {
 return mowerDormCandidateMood(data,op.name)
}
/** Ordinary recall starts at the requester's rescue line and requires observed target mood for its endurance forecast. */
export function mowerRecallMoodAdmissible(data:MowerSchedulingData,recalled:ReadonlySet<string>,candidates:readonly string[]):boolean {
 const anchor=(op:MowerOperatorState)=>op.isHigh()&&!op.room.startsWith('dorm')&&!op.workaholic&&!data.canStandby(op)&&(!op.multiGroup||candidates.length===1&&op.independentRest)
 const requesters=candidates.map(name=>data.operators[name]).filter((op):op is MowerOperatorState=>!!op&&anchor(op)&&!!op.currentRoom&&!op.isResting())
 const reached=(op:MowerOperatorState,limit:number)=>{const mood=recallMood(data,op);return mood!==undefined&&mood<=limit}
 if(!requesters.some(op=>reached(op,rescueMoodThreshold(op,data.policy))))return false
 return [...recalled].map(name=>data.operators[name]).every(op=>{
  if(!op)return false
  if(!anchor(op))return true
  const mood=recallMood(data,op)
  return mood!==undefined
 })
}
/** Existing dispatch opportunities bound ordinary recall without creating a new timer. */
export function mowerRecallRecheckWindow(data:MowerSchedulingData,admitted:MowerSchedulingData,support:MowerTaskPlan,admission:MowerTaskPlan,options:MowerRestingOptions):MowerRecallRecheckWindow {
 const duration=(plan:MowerTaskPlan,type:MowerTaskType)=>Object.keys(plan).length?alphaSupportSwapMicros(new MowerTask({type,plan}),options.priorityScheduling):0
 const notBeforeMicros=data.nowMicros+duration(support,T.SELF_CORRECTION)+duration(admission,T.SHIFT_OFF)
 const dispatch=(options.tasks??[]).filter(task=>!task.executionFailure).map(task=>Object.assign(new MowerTask({type:task.type}),structuredClone(task),{type:task.type}))
 protectMowerAlphaTasks(dispatch,notBeforeMicros,options.priorityScheduling)
 const next=dispatch.filter(task=>task.timeMicros>data.nowMicros&&!task.moodControlEvent&&(
  task.type===T.RUN_ORDER&&!!task.metadata&&!Object.keys(task.plan).length&&(task.wakeOnlyCompletion||Number.isSafeInteger(task.observedOrderDueMicros))||!!task.workingReplacementCheck&&mowerWorkingReplacementApplies(data,task.workingReplacementCheck)&&mowerWorkingReplacementApplies(admitted,task.workingReplacementCheck)||task.type===T.NOT_SPECIFIC&&!task.metadata&&!Object.keys(task.plan).length&&!task.workingReplacementCheck
 )).sort((a,b)=>a.timeMicros-b.timeMicros)[0]
 const observed=options.coordinationRecheck
 const observationLimits:Record<string,number>={}
 if(observed&&Number.isSafeInteger(observed.timeMicros)&&observed.timeMicros>data.nowMicros&&observed.timeMicros<(next?.timeMicros??Infinity)&&materializeCoordinationMoods(data,admitted)){
  const rates=options.coordinationRates?.(admitted)
  for(const name of observed.names){
   const before=data.operators[name],after=admitted.operators[name]
   if(!before?.currentRoom||before.isResting()||!after||after.currentRoom!==before.currentRoom||after.currentIndex!==before.currentIndex)continue
   const limit=mowerPlanningWakeThreshold(admitted,after),rate=rates?.work[name]
   if(limit===undefined||after.mood<=limit||rate===undefined||!Number.isFinite(rate)||rate<=0)continue
   if(data.nowMicros+Math.ceil((after.mood-limit)/rate*3_600_000_000)<=observed.timeMicros)observationLimits[name]=limit
  }
 }
 const planningWake=Object.keys(observationLimits).length>0
 const recheckMicros=planningWake?observed!.timeMicros:next?.timeMicros
 if(recheckMicros===undefined)return {notBeforeMicros:data.nowMicros}
 const recheckDuration=alphaSupportSwapMicros(planningWake?new MowerTask():next!,options.priorityScheduling)
 let cursor=notBeforeMicros
 for(const queued of dispatch){
  if(queued===next&&!planningWake||queued.timeMicros>recheckMicros)break
  cursor=Math.max(cursor,queued.timeMicros)+alphaSupportSwapMicros(queued,options.priorityScheduling)
 }
 const startMicros=Math.max(cursor,recheckMicros)
 return {notBeforeMicros,untilMicros:startMicros+recheckDuration,observation:planningWake?{timeMicros:startMicros,limits:observationLimits}:undefined}
}
function materializeCoordinationMoods(original:MowerSchedulingData,shadow:MowerSchedulingData):boolean {
 for(const op of Object.values(shadow.operators)){
  const source=original.operators[op.name]
  const mood=source?mowerDormCandidateMood(original,source.name):undefined
  if(op.currentRoom&&mood===undefined)return false
  op.mood=mood??op.mood;op.timeStampMicros=shadow.nowMicros;op.depletionRate=0
 }
 return true
}
/** Keep connected workers above their floors until an existing recheck or complete recovery. */
export function mowerRecallCanSustain(original:MowerSchedulingData,admitted:MowerSchedulingData,recalled:ReadonlySet<string>,candidates:readonly string[],options:MowerRestingOptions,untilMicros?:number,notBeforeMicros=original.nowMicros,observation?:MowerRecallRecheckWindow['observation']):boolean {
 if(recalled.size&&(mowerUrgentRecallBlocked(original,candidates,options.urgentRecoveryPendingSupporters)||[...recalled].some(name=>name in original.urgentRecoverySupporters)))return false
 for(const name of recalled){
  const op=original.operators[name];if(!op||!op.isResting())continue
  if(op.restInFull&&!mowerRecoveryReady(original,op,options.priorityScheduling))return false
  if(op.group){const recovery=mowerGroupRecoveryDeadline(projectMowerArrangements(original,[]),op.group);if(recovery.requiredNames.length&&(recovery.requiredNames.some(member=>(!options.urgentExhaust||original.operators[member]!.restInFull)&&!mowerRecoveryReady(original,original.operators[member],options.priorityScheduling))))return false}
 }
 if(options.urgentExhaust)return true
 if(!mowerRecallMoodAdmissible(original,recalled,candidates))return false
 if(!options.coordinationRates)return false
 let connected=mowerReplacementDependencyNames(original,[...candidates,...recalled])
 // Beds are shared resources too; do not assume an unrelated resident releases a bed early.
 for(const bed of admitted.allDorms())if(bed.name&&admitted.operators[bed.name]?.isHigh())connected.add(bed.name)
 connected=mowerReplacementDependencyNames(original,connected)
 const shadow=projectMowerArrangements(admitted,[])
 if(!materializeCoordinationMoods(original,shadow))return false
 const waiting=[...connected].map(name=>shadow.operators[name]).filter((op):op is MowerOperatorState=>!!op?.isHigh()&&op.isResting()&&!op.workaholic&&!op.room.startsWith('dorm'))
 if(!waiting.length)return false
 // Fixed staffing is deliberately conservative: no hypothetical future rescue is credited.
 // Every physical actor participates in mood boundaries because global skills affect rates.
 const actors=Object.values(shadow.operators).filter(op=>op.currentRoom)
 const working=actors.filter(op=>connected.has(op.name)&&!op.isResting()&&!op.workaholic)
 const boundaries=(op:MowerOperatorState)=>[0,4,8,12,16,18,20,24,op.lowerLimit,op.upperLimit]
 for(let step=0;step<actors.length*16+1;step++){
  if(working.some(op=>op.mood<=op.lowerLimit+1e-8))return false
  const recovered=waiting.every(op=>op.mood>=op.upperLimit-1e-8)
  if(observation&&shadow.nowMicros>=observation.timeMicros){
   if(!Object.entries(observation.limits).some(([name,limit])=>shadow.operators[name]!.mood<=limit+1e-8))untilMicros=undefined
   observation=undefined
  }
  if(shadow.nowMicros>=notBeforeMicros&&(recovered||untilMicros!==undefined&&shadow.nowMicros>=untilMicros))return true
  const rates=options.coordinationRates(shadow);if(!rates)return false
  let hours=untilMicros===undefined?Infinity:(untilMicros-shadow.nowMicros)/3_600_000_000
  if(observation)hours=Math.min(hours,(observation.timeMicros-shadow.nowMicros)/3_600_000_000)
  if(recovered)hours=Math.min(hours,(notBeforeMicros-shadow.nowMicros)/3_600_000_000)
  const velocities=new Map<string,number>()
  for(const op of actors){
   const rate=op.isResting()?rates.recovery[op.name]:rates.work[op.name]
   if(rate===undefined||!Number.isFinite(rate)||op.isResting()&&rate<0)return false
   const velocity=op.isResting()?rate:-rate;velocities.set(op.name,velocity)
   if(velocity===0)continue
   const next=boundaries(op).filter(value=>velocity>0?value>op.mood+1e-8:value<op.mood-1e-8)
   for(const value of next)hours=Math.min(hours,(value-op.mood)/velocity)
  }
  if(!Number.isFinite(hours)||hours<=0)return false
  for(const op of actors){op.mood=Math.max(0,Math.min(24,op.mood+velocities.get(op.name)!*hours));op.timeStampMicros=shadow.nowMicros+toMowerMicros(hours)}
  shadow.nowMicros+=toMowerMicros(hours)
 }
 return false
}

/** Active explicit arrangements and product reservations take precedence over coordination. */
export function mowerReplacementReservations(data:MowerSchedulingData,tasks:readonly MowerTask[],ownRecovery:readonly string[]=[]):{reservedNames:Set<string>;reservedSlots:Set<string>}{
 const reservedNames=new Set([...data.busyRestingNames,...data.reservedProductReplacements]),reservedSlots=new Set(data.reservedProductBeds.keys())
 for(const task of tasks){
  if(!ownRecovery.length||task.urgentRecoveryRequestNames.length!==ownRecovery.length||!task.urgentRecoveryRequestNames.every(name=>ownRecovery.includes(name))){
   task.urgentRecoveryReservedNames.forEach(name=>reservedNames.add(name))
   task.urgentRecoveryReservedSlots.forEach(slot=>reservedSlots.add(slot))
  }
  if(task.productShiftLocked){task.productLockNames.forEach(name=>reservedNames.add(name));task.productLockSlots.forEach(slot=>reservedSlots.add(slot))}
  if(task.backupShiftActive||task.dormRecoveryRestore.length){
   task.dormRecoveryRestore.forEach(name=>reservedNames.add(name))
   for(const [room,row] of Object.entries(task.plan))row.forEach((name,index)=>{if(name!=='Current'){reservedSlots.add(alphaPosition(room,index));if(data.operators[name])reservedNames.add(name)}})
  }
  if(task.backupShiftActive)task.backupExplicitSlots.forEach(slot=>{reservedSlots.add(slot);const [room,index]=slot.split('\0'),name=task.plan[room!]?.[Number(index)];if(name&&data.operators[name])reservedNames.add(name)})
 }
 return {reservedNames,reservedSlots}
}

/** Another committed shift can satisfy a retained request before its own task resumes. */
export function mowerCoordinationRequestFulfilled(data:MowerSchedulingData,names:readonly string[]):boolean {
 const requested=[...new Set(names.flatMap(name=>{const op=data.operators[name];return op?.group?data.shiftGroupMembers(op.group):op?[name]:[]}))]
 const anchors=requested.map(name=>data.operators[name]!).filter(op=>op.isHigh()&&!op.room.startsWith('dorm')&&!op.workaholic&&(!op.multiGroup||op.independentRest))
 return anchors.length>0&&anchors.every(op=>op.isResting()||data.isStandby(op.name)||!op.currentRoom&&hasObservedFullMood(op))
}
