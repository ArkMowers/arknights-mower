import {mowerCoordinationReturn} from './mowerCoordinationReturn'
import {mowerForcedGroupCoverReservations,mowerHeldRestGroups} from './mowerBackupGroupTasks'
import {mowerDormCandidateMood} from './mowerSchedulingMood'
import {mowerUrgentRecallBlocked} from './mowerUrgentRecovery'
import {alphaPosition,mowerMatchReplacements} from './mowerAlphaDorm'
import {mowerGroupRecoveryDeadline,mowerRecoveryReady} from './mowerGroupRecovery'
import {hasObservedFullMood,mowerReplacementCandidates,rescueMoodThreshold,MowerOperatorState} from './mowerOperatorState'
import {projectMowerArrangements} from './mowerObservations'
import type {MowerRestingOptions} from './mowerOrdinaryPlanning'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerRestingBindingGroups,mowerSharedReplacements,mowerSameGroupPrimaryReplacement} from './mowerSharedGroups'
import {toMowerMicros,MowerTask,type MowerTaskPlan} from './mowerTaskQueue'

export interface MowerCoordinationRates {work:Readonly<Record<string,number>>;recovery:Readonly<Record<string,number>>}
function replacements(data:MowerSchedulingData,op:MowerOperatorState,required:ReadonlySet<string>=new Set(),requestNames:readonly string[]=[...required]):string[]{
 const transitions=Object.fromEntries(data.shiftRequestGroups(requestNames).map(group=>[group,true]))
 return op.multiGroup?mowerSharedReplacements(op,mowerRestingBindingGroups(data,op,transitions)):op.replacement
}
/** Keep the native same-group primary exception; unrelated primaries remain unavailable. */
export function mowerCoordinationPrimaryReplacement(data:MowerSchedulingData,owner:MowerOperatorState,name:string,required:ReadonlySet<string>,requestNames:readonly string[]=[...required]):boolean {
 const transitions=Object.fromEntries(data.shiftRequestGroups(requestNames).map(group=>[group,true]))
 return (owner.multiGroup?mowerRestingBindingGroups(data,owner,transitions):[owner.group]).some(group=>mowerSameGroupPrimaryReplacement(data,owner,name,group))
}
function eligible(data:MowerSchedulingData,name:string,owner:MowerOperatorState,options:MowerRestingOptions,required:ReadonlySet<string>=new Set()):boolean {
 const cover=data.operators[name]
 return !!cover&&(!mowerForcedGroupCoverReservations(data).names.has(name)||cover.currentRoom===owner.room&&cover.currentIndex===owner.index)&&(!cover.isHigh()||mowerCoordinationPrimaryReplacement(data,owner,name,required,options.requestNames))&&!data.busyRestingNames.has(name)&&!options.reservedNames?.has(name)&&!data.reservedProductReplacements.has(name)&&!data.excludedCandidates.has(name)&&!options.isMasteryBusy?.(name)&&!data.dormReplacementForSlot(name,cover.currentRoom,cover.currentIndex)&&!options.reservedSlots?.has(alphaPosition(cover.currentRoom,cover.currentIndex))&&(owner.room.startsWith('dorm')||!data.replacementExhausted(name,owner))
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
  const raw=replacements(data,owner,required,options.requestNames)
  if(owner.room.startsWith('dorm')&&raw.includes('Free')){choices[name]=[];return}
  const ranked=mowerReplacementCandidates(new MowerOperatorState({...owner,replacement:raw}),data.operators,data.policy,data.nowMicros)
  choices[name]=ranked.filter(cover=>{
   const sameGroup=mowerCoordinationPrimaryReplacement(data,owner,cover,required,options.requestNames)
   if(required.has(cover)&&!sameGroup||!eligible(data,cover,owner,options,required))return false
   const worker=data.operators[cover]!
   if(!worker.currentRoom||worker.isResting()||sameGroup&&required.has(cover)&&worker.currentRoom===worker.room&&worker.currentIndex===worker.index)return true
   const occupant=coveredOwner(data,cover)
   if(!occupant||options.reservedSlots?.has(alphaPosition(occupant.room,occupant.index))||!replacements(data,occupant,required,options.requestNames).includes(cover))return false
   visit(occupant.name);return true
  })
 }
 candidates.forEach(visit)
 // Existing owners keep their preferred choices unless a constrained requester needs them.
 const ordered=Object.fromEntries([...owners].filter(([,op])=>!(op.room.startsWith('dorm')&&replacements(data,op,required,options.requestNames).includes('Free'))).sort(([a],[b])=>Number(required.has(a))-Number(required.has(b))).map(([name])=>[name,choices[name]!]))
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
   const preferred=ordered.slice(0,index).find(name=>!protectedNames.has(name)&&eligible(state,name,owner,{reservedSlots:protectedSlots})&&(!state.operators[name]!.currentRoom||state.operators[name]!.isResting()&&(mowerDormCandidateMood(state,name)??-Infinity)>=(state.operators[name]!.restInFull?state.operators[name]!.upperLimit:rescueMoodThreshold(state.operators[name]!,state.policy))))
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
export function mowerRecallMoodAdmissible(data:MowerSchedulingData,recalled:ReadonlySet<string>,candidates:readonly string[],requestNames:readonly string[]=candidates):boolean {
 const anchor=(op:MowerOperatorState)=>data.isGroupShiftAnchor(op)||requestNames.includes(op.name)&&op.isHigh()&&op.independentRest&&!op.workaholic&&!op.room.startsWith('dorm')&&!data.canStandby(op)
 const requestGroups=new Set(data.shiftRequestGroups(requestNames))
 const requesters=candidates.map(name=>data.operators[name]).filter((op):op is MowerOperatorState=>!!op&&anchor(op)&&(!op.group||requestGroups.has(op.group))&&!!op.currentRoom&&!op.isResting())
 const reached=(op:MowerOperatorState,limit:number)=>{const mood=recallMood(data,op);return mood!==undefined&&mood<=limit}
 if(!requesters.some(op=>reached(op,rescueMoodThreshold(op,data.policy))))return false
 return [...recalled].map(name=>data.operators[name]).every(op=>{
  if(!op)return false
  if(!anchor(op))return true
  const mood=recallMood(data,op)
  return mood!==undefined
 })
}
function materializeCoordinationMoods(original:MowerSchedulingData,shadow:MowerSchedulingData,knownMoods?:Readonly<Record<string,number>>):boolean {
 shadow.calculatedMoodSnapshot=undefined
 for(const op of Object.values(shadow.operators)){
  const source=original.operators[op.name]
  const mood=knownMoods?.[op.name]??(source?mowerDormCandidateMood(original,source.name):undefined)
  if(op.currentRoom&&(mood===undefined||!Number.isFinite(mood)||mood<0||mood>24))return false
  op.calculatedMoodSnapshot=undefined
  op.mood=mood??op.mood;op.timeStampMicros=shadow.nowMicros;op.depletionRate=0
 }
 return true
}
/** Keep dependent workers above their floors until the requesting units can legally return. */
export function mowerRecallCanSustain(original:MowerSchedulingData,admitted:MowerSchedulingData,recalled:ReadonlySet<string>,candidates:readonly string[],options:MowerRestingOptions):boolean {
 if(recalled.size&&(mowerUrgentRecallBlocked(original,candidates,options.urgentRecoveryPendingSupporters)||[...recalled].some(name=>name in original.urgentRecoverySupporters)))return false
 for(const name of recalled){
  const op=original.operators[name];if(!op||!op.isResting())continue
  if(mowerHeldRestGroups(original,true).has(op.group))return false
  if(op.restInFull&&!mowerRecoveryReady(original,op,options.priorityScheduling))return false
  if(op.group){const recovery=mowerGroupRecoveryDeadline(projectMowerArrangements(original,[]),op.group);if(recovery.requiredNames.length&&(recovery.requiredNames.some(member=>original.operators[member]!.restInFull&&!mowerRecoveryReady(original,original.operators[member],options.priorityScheduling))))return false}
 }
 if(options.urgentExhaust)return true
 if(!mowerRecallMoodAdmissible(original,recalled,candidates,options.requestNames))return false
 if(!options.coordinationRates)return false
 const connected=mowerReplacementDependencyNames(original,[...candidates,...recalled])
 let shadow=projectMowerArrangements(admitted,[])
 if(!materializeCoordinationMoods(original,shadow,options.coordinationMoods))return false
 const requestNames=options.requestNames??candidates,groups=original.shiftRequestGroups(requestNames)
 const units: string[][]=groups.map(group=>original.shiftGroupMembers(group).filter(name=>original.isGroupShiftAnchor(original.operators[name]!,group)))
 for(const name of requestNames){const op=original.operators[name];if(op?.isHigh()&&!op.workaholic&&!op.room.startsWith('dorm')&&!original.canStandby(op)&&(!op.group||op.independentRest)&&!units.some(unit=>unit.includes(name)))units.push([name])}
 if(!units.length||units.some(names=>!names.length||names.some(name=>!shadow.operators[name]?.isResting())))return false
 const remaining=new Set(units.map((_,index)=>index))
 const boundaries=(op:MowerOperatorState)=>[0,4,8,12,16,18,20,24,op.lowerLimit,op.upperLimit]
 // Each completed unit changes staffing at most once. Between returns every
 // actor traverses the same finite mood boundaries as the fixed-staffing forecast.
 const maximumSteps=(units.length+1)*(Object.keys(shadow.operators).length*16+1)+units.length
 for(let step=0;step<maximumSteps;step++){
  // All physical actors still contribute global skill and recovery boundaries.
  const actors=Object.values(shadow.operators).filter(op=>op.currentRoom)
  const working=actors.filter(op=>connected.has(op.name)&&!op.isResting()&&!op.workaholic)
  if(working.some(op=>op.mood<=op.lowerLimit+1e-8))return false
  const rates=options.coordinationRates(shadow);if(!rates)return false
  const velocities=new Map<string,number>()
  for(const op of actors){
   const rate=op.isResting()?rates.recovery[op.name]:rates.work[op.name]
   if(rate===undefined||!Number.isFinite(rate)||op.isResting()&&rate<0)return false
   velocities.set(op.name,op.isResting()?rate:-rate)
  }
  const activeIndices=[...remaining],activeUnits=activeIndices.map(index=>units[index]!)
  const returning=mowerCoordinationReturn(shadow,activeUnits,rates,options)
  if(returning&&returning.task.timeMicros<=shadow.nowMicros){
   const next=projectMowerArrangements(shadow,[returning.task.plan])
   if(Object.values(next.operators).some(op=>connected.has(op.name)&&op.currentRoom&&!op.isResting()&&!op.workaholic&&op.mood<=op.lowerLimit+1e-8))return false
   for(const index of returning.units)remaining.delete(activeIndices[index]!)
   if(!remaining.size)return true
   shadow=next
   continue
  }
  let hours=returning?(returning.task.timeMicros-shadow.nowMicros)/3_600_000_000:Infinity
  for(const op of actors){
   const velocity=velocities.get(op.name)!
   if(velocity===0)continue
   for(const value of boundaries(op).filter(value=>velocity>0?value>op.mood+1e-8:value<op.mood-1e-8))hours=Math.min(hours,(value-op.mood)/velocity)
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
 const groups=new Set(data.shiftRequestGroups(names))
 const requested=[...new Set(names.flatMap(name=>{const op=data.operators[name];return op?.group?groups.has(op.group)?data.shiftGroupMembers(op.group):[]:op?[name]:[]}))]
 const anchors=requested.map(name=>data.operators[name]!).filter(op=>op.isHigh()&&!op.room.startsWith('dorm')&&!op.workaholic&&(!op.multiGroup||op.independentRest||!!op.shiftGroup&&groups.has(op.shiftGroup)))
 return anchors.length>0&&anchors.every(op=>op.isResting()||data.isStandby(op.name)||!op.currentRoom&&hasObservedFullMood(op))
}
