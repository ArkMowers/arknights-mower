import {mowerRestingBindingGroups,mowerSharedReplacements,mowerSameGroupPrimaryReplacement} from './mowerSharedGroups'
// Decision state for the pinned Mower port. Reservations do not imply physical occupancy.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {MowerOperatorState,hasRestingMood,restingMood,type MowerMoodPolicy} from './mowerOperatorState'
import {toMowerMicros} from './mowerTaskQueue'
export interface MowerDateTimeValue {timeMicros:number}
export class MowerDormState {
 constructor(public position:[string,number],public name='',public timeMicros?:number,public autoFree=false){}
 reset(){this.name='';this.timeMicros=undefined}
}
export interface MowerSchedulingDataOptions {
 adjustForRunOrders?:boolean
 dormIsolation?:string[][]
 alpha?:boolean;priorityReplacement?:string[];freeRoomExclusions?:string[];dormOrder?:string[];standbyNames?:string[]
 plan:Record<string,string[]>;operators:Record<string,MowerOperatorState>;dorms:MowerDormState[];nowMicros:number;partyTime?:MowerDateTimeValue|boolean|null;runOrderRooms?:Record<string,Record<string,never>>
 policy?:Partial<MowerMoodPolicy>;freeRoom?:boolean;powerPlantCount?:number;planConditions?:boolean[]
 groupRecoveryFullMembers?:Record<string,string[]>
 groupDorms?:MowerDormState[]
 pendingGroupTransitions?:Record<string,boolean>;groupShiftState?:Record<string,boolean>;groupMoodGapThresholdMinutes?:number
 groupRestInFullOnMoodGap?:boolean;groupMoodGapMaxExtraWaitHours?:number;mergeIntervalMinutes?:number
 busyRestingNames?:Set<string>;excludedCandidates?:Set<string>;restingPriorityNames?:string[];freeBlacklist?:string[]
 recentShiftOnByRestUnit?:Map<string,number>
 unregisteredIdleNames?:string[];dormMoodEstimates?:Map<string,[number,number]>;idleDormSearchExhausted?:boolean;idleDormSearchStoppedAtMicros?:number
 reservedProductReplacements?:Set<string>;reservedProductBeds?:Map<string,string>;emergencyDormAgents?:Set<string>
}
export class MowerSchedulingData {
 adjustForRunOrders:boolean|undefined
 /** Runtime uses October 3 alpha; frozen September fixtures retain their source contract. */
 dormIsolation:string[][]
 alpha:boolean;priorityReplacement:string[];freeRoomExclusions:string[];dormOrder:string[]
 standbyNames:string[]
 plan:Record<string,string[]>;operators:Record<string,MowerOperatorState>;dorms:MowerDormState[];nowMicros:number;partyTime?:MowerDateTimeValue|boolean|null;runOrderRooms:Record<string,Record<string,never>>
 recoveryOrderVersion=0
 policy:MowerMoodPolicy;freeRoom:boolean;powerPlantCount:number;planConditions:boolean[]
 groupRecoveryFullMembers:Record<string,string[]>
 groupDorms:MowerDormState[]
 pendingGroupTransitions:Record<string,boolean>;groupShiftState:Record<string,boolean>;groupMoodGapThresholdMinutes:number
 groupRestInFullOnMoodGap:boolean;groupMoodGapMaxExtraWaitHours:number;mergeIntervalMinutes:number
 busyRestingNames:Set<string>;excludedCandidates:Set<string>;restingPriorityNames:string[];freeBlacklist:string[]
 recentShiftOnByRestUnit:Map<string,number>
 unregisteredIdleNames:string[];dormMoodEstimates:Map<string,[number,number]>;idleDormSearchExhausted:boolean;idleDormSearchStoppedAtMicros:number|undefined
 reservedProductReplacements:Set<string>;reservedProductBeds:Map<string,string>;emergencyDormAgents:Set<string>
 constructor(o:MowerSchedulingDataOptions){
  this.dormIsolation=(o.dormIsolation??[]).map(group=>[...group])
  this.adjustForRunOrders=o.adjustForRunOrders
  this.alpha=o.alpha??false;this.priorityReplacement=o.priorityReplacement??[];this.freeRoomExclusions=o.freeRoomExclusions??[];this.dormOrder=o.dormOrder??[]
  this.standbyNames=o.standbyNames??[];Object.values(o.operators).forEach(op=>{op.alpha=this.alpha})
  this.plan=o.plan;this.operators=o.operators;this.dorms=o.dorms;this.nowMicros=o.nowMicros;this.partyTime=o.partyTime;this.runOrderRooms=o.runOrderRooms??{}
  this.policy={restingThreshold:.65,rescueThreshold:.75,experimentalDormLogic:false,...o.policy,alpha:this.alpha}
  this.freeRoom=o.freeRoom??false;this.powerPlantCount=o.powerPlantCount??2;this.planConditions=o.planConditions??[]
  this.groupRecoveryFullMembers=Object.fromEntries(Object.entries(o.groupRecoveryFullMembers??{}).map(([group,names])=>[group,[...names]]))
  this.groupDorms=o.groupDorms??Object.values(this.operators).filter(op=>op.room.startsWith('dorm')&&op.group&&(op.multiGroup?op.groupBindings:[{group:op.group,replacement:op.replacement}]).some(binding=>!binding.replacement.includes('Free')&&binding.replacement.some(name=>mowerSameGroupPrimaryReplacement(this,op,name,binding.group)&&!this.operators[name]!.room.startsWith('dorm')))).map(op=>new MowerDormState([op.room,op.index]))
  this.pendingGroupTransitions={...o.pendingGroupTransitions};this.groupShiftState={...o.groupShiftState};this.groupMoodGapThresholdMinutes=o.groupMoodGapThresholdMinutes??75
  this.groupRestInFullOnMoodGap=o.groupRestInFullOnMoodGap??true
  this.groupMoodGapMaxExtraWaitHours=o.groupMoodGapMaxExtraWaitHours??0;this.mergeIntervalMinutes=o.mergeIntervalMinutes??10
  this.busyRestingNames=o.busyRestingNames??new Set();this.excludedCandidates=o.excludedCandidates??new Set()
  this.restingPriorityNames=o.restingPriorityNames??[];this.freeBlacklist=o.freeBlacklist??[]
  this.recentShiftOnByRestUnit=o.recentShiftOnByRestUnit??new Map()
  this.unregisteredIdleNames=o.unregisteredIdleNames??[];this.dormMoodEstimates=new Map(o.dormMoodEstimates);this.idleDormSearchExhausted=o.idleDormSearchExhausted??false;this.idleDormSearchStoppedAtMicros=o.idleDormSearchStoppedAtMicros
  this.reservedProductReplacements=o.reservedProductReplacements??new Set();this.reservedProductBeds=o.reservedProductBeds??new Map();this.emergencyDormAgents=o.emergencyDormAgents??new Set()
 }
 /** ab0a4e5 execution semantics; stored autoFree beds enumerate potential capacity. */
 autoFreeDormSlot(room:string,index:number):boolean {
  const owner=this.operators[this.plan[room]?.[index]??'']
  if(!room.startsWith('dorm')||!owner?.group||!owner.room.startsWith('dorm')||owner.nativeName==='菲亚梅塔')return false
  const replacements=owner.multiGroup?mowerSharedReplacements(owner,mowerRestingBindingGroups(this,owner,this.pendingGroupTransitions)):owner.replacement
  return replacements.includes('Free')
 }
 dynamicDormPosition(room:string,index:number,name?:string):boolean {
  const resident=this.plan[room]?.[index]
  if(resident==='Free')return true
  if(this.alpha)return this.autoFreeDormSlot(room,index)&&(name===undefined||name!==resident&&name!=='Current')
  return !!this.policy.experimentalDormLogic&&this.dorms.some(b=>b.position[0]===room&&b.position[1]===index&&b.autoFree)
 }
 dormReplacementForSlot(name:string,room:string,index:number):boolean {
  const owner=this.operators[this.plan[room]?.[index]??'']
  return room.startsWith('dorm')&&!!owner?.group&&owner.nativeName!=='菲亚梅塔'&&!(this.alpha&&this.autoFreeDormSlot(room,index))&&(owner.replacement.includes(name)||this.alpha&&owner.groupBindings.some(binding=>binding.replacement.includes(name)))
 }
 group(name:string):string[]{return Object.values(this.operators).filter(op=>op.group===name).map(op=>op.name)}
 currentOperator(room:string,index:number):MowerOperatorState|undefined{return Object.values(this.operators).find(op=>op.currentRoom===room&&op.currentIndex===index)}
 /** Native get_current_room uses a last-write map; get_current_operator remains first-match. */
 currentRoom(room:string,bypass=false,indexes?:number[]):string[]|undefined {
  const coordinates=new Map(Object.values(this.operators).filter(op=>op.currentRoom===room).map(op=>[op.currentIndex,op.name]))
  const names=Array.from({length:room==='train'?2:this.plan[room]!.length},(_,index)=>coordinates.get(index)??'')
  return !bypass&&names.some((name,index)=>!name&&(indexes===undefined||indexes.includes(index)))?undefined:names
 }
 canStandby(op:MowerOperatorState):boolean{return op.isHigh()&&!!(this.alpha||op.group||this.policy.experimentalDormLogic)&&op.restingPriority==='standby'&&!op.room.startsWith('dorm')&&!op.workaholic&&!op.exhaustRequire&&!op.restInFull&&!!(this.alpha||this.policy.experimentalDormLogic||!op.workshop)}
 getDormByName(name:string):[number,MowerDormState]|undefined {
  const op=this.operators[name];if(!op)return undefined
  const beds=this.allDorms(),index=beds.findIndex(bed=>bed.position[0]===op.currentRoom&&bed.position[1]===op.currentIndex&&this.recoveryDorm(bed,name))
  return index<0?undefined:[index,beds[index]!]
 }
 isStandby(name:string):boolean {
  const op=this.operators[name];if(!op||!this.canStandby(op)||op.currentRoom)return false
  const cover=this.currentOperator(op.room,op.index);if(!cover||!op.replacement.includes(cover.name)||this.excludedCandidates.has(cover.name))return false
  const anchors=op.group?this.group(op.group).map(name=>this.operators[name]!):Object.values(this.operators)
  return anchors.some(other=>other.isHigh()&&(this.alpha?!this.canStandby(other):other.restingPriority==='high')&&!other.room.startsWith('dorm')&&!other.workaholic&&(this.alpha||this.policy.experimentalDormLogic||!other.workshop)&&other.isResting()&&!!this.getDormByName(other.name))
 }
 isGroupShiftAnchor(op:MowerOperatorState):boolean{return op.isHigh()&&!op.multiGroup&&!op.workaholic&&!op.room.startsWith('dorm')&&!this.canStandby(op)}
 shiftGroupMembers(group:string):string[]{return Object.values(this.operators).filter(op=>op.multiGroup?op.groupBindings.some(binding=>binding.group===group):op.group===group).map(op=>op.name)}
 groupIsResting(group:string):boolean{return this.groupShiftState[group]??this.group(group).some(name=>{const op=this.operators[name]!;return this.isGroupShiftAnchor(op)&&op.isResting()})}
 effectiveFreeSlot(bed:MowerDormState,inactiveGroups=new Set<string>(),activeGroups=new Set<string>()):boolean {
  const [room,index]=bed.position,slots=this.plan[room];if(!slots||index<0||index>=slots.length)return false
  const name=slots[index];if(name==='Free')return true;if(!bed.autoFree)return false
  const resident=name?this.operators[name]:undefined;if(!resident)return false
  const groups=resident.multiGroup?resident.groupBindings.map(binding=>binding.group):[resident.group]
  const resting=groups.filter(group=>group&&!inactiveGroups.has(group)&&(activeGroups.has(group)||(this.pendingGroupTransitions[group]??this.groupIsResting(group))))
  if(resting.length)return resting.every(group=>resident.replacementsForGroup(group).includes('Free'))
  return !!resident.group&&resident.replacement.includes('Free')&&!groups.some(group=>inactiveGroups.has(group))&&!!bed.name&&bed.name!==resident.name
 }
 allDorms():MowerDormState[]{return [...this.dorms,...this.groupDorms]}
 recoveryDorm(bed:MowerDormState,name:string):boolean {if(this.groupDorms.includes(bed)){const owner=this.operators[this.plan[bed.position[0]]?.[bed.position[1]]??''],cover=this.operators[name];if(!owner||!cover||cover.room.startsWith('dorm'))return false;const groups=owner.multiGroup?mowerRestingBindingGroups(this,owner,this.pendingGroupTransitions):[owner.group];if(owner.multiGroup&&!groups.length)groups.push(owner.group);return !mowerSharedReplacements(owner,groups).includes('Free')&&groups.some(group=>mowerSameGroupPrimaryReplacement(this,owner,name,group))}if(!this.dorms.includes(bed))return false;const [room,index]=bed.position,native=this.plan[room]?.[index];return native==='Free'||bed.autoFree&&name!==native&&(!this.operators[native??'']?.multiGroup||this.effectiveFreeSlot(bed))}
 restMoodComplete(name:string):boolean {const op=this.operators[name];return !!op&&op.restMoodLimit&&hasRestingMood(op,this.nowMicros)&&(restingMood(op,this.nowMicros)>=op.upperLimit||this.alpha&&!op.currentRoom&&op.restMoodReleaseLimit===op.upperLimit)}
 freeRoomExcluded(name:string):boolean {const op=this.operators[name];return this.alpha&&this.freeRoom&&this.freeRoomExclusions.includes(name)&&!!op&&!op.workaholic&&!this.freeBlacklist.includes(name)&&!this.restMoodComplete(name)}
 replacementExhausted(name:string):boolean{const op=this.operators[name];return !!op&&hasRestingMood(op,this.nowMicros)&&restingMood(op,this.nowMicros)<=op.lowerLimit}
 updateStandbyLowPriority(op:MowerOperatorState,returnedToPost=false):void {
  if(!this.standbyNames.includes(op.name)||returnedToPost)op.standbyLowPriority=false
  else if(restingMood(op,this.nowMicros)<op.lowerLimit+(op.upperLimit-op.lowerLimit)*this.policy.restingThreshold*this.policy.rescueThreshold)op.standbyLowPriority=true
 }
 idleRestChecked(name:string):boolean {const op=this.operators[name],checked=op?.idleRestCheck;return !!op&&!op.currentRoom&&!!checked&&checked[0]>=op.upperLimit&&checked[1]===op.mood&&checked[2]===op.timeStampMicros}
 stopIdleDormSearch():void {if(!this.idleDormSearchExhausted){this.idleDormSearchExhausted=true;this.idleDormSearchStoppedAtMicros=this.nowMicros}}
 refreshIdleDormSearch(reason?:string,names?:Set<string>):boolean {
  if(!reason&&(!this.idleDormSearchExhausted||this.idleDormSearchStoppedAtMicros===undefined||this.nowMicros-this.idleDormSearchStoppedAtMicros<toMowerMicros(1)))return false
  this.idleDormSearchExhausted=false;this.idleDormSearchStoppedAtMicros=undefined
  if(!names)this.dormMoodEstimates.clear()
  for(const name of names??Object.keys(this.operators)){this.dormMoodEstimates.delete(name);const op=this.operators[name];if(op){op.dormMoodFallback='';op.dormMoodPeers={};op.idleRestCheck=undefined}}
  return true
 }
 skipIdleDormRelease(name:string):boolean {
  if(this.alpha){const op=this.operators[name];return this.freeRoomExcluded(name)||!!(this.freeRoom&&op?.isResting()&&op.dormMoodFallback===op.currentRoom&&!this.freeBlacklist.includes(name)&&!op.workaholic&&hasRestingMood(op,this.nowMicros)&&restingMood(op,this.nowMicros)>=op.upperLimit&&!op.restMoodLimit)}
  if(this.policy.experimentalDormLogic)throw new Error('Experimental dorm exclusions are not yet ported');return false
 }
}
