import {mowerForcedWorkGroups} from './mowerBackupGroupTasks'
import {mowerCoordinationRequestFulfilled} from './mowerReplacementCoordination'
import {restingThresholdFor} from './mowerOperatorState'
// Preserve native group exhaustion admission (Mower e6c06a5b1, MIT).
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerDormCandidateMood} from './mowerAlphaCandidates'
import {alphaRestingTier} from './mowerAlphaDorm'
import {MOWER_TASK_TYPES as T,type MowerTask} from './mowerTaskQueue'

/** Exhaustion changes ordinary eligibility for the whole anchored group. */
export function mowerExhaustGroups(data:MowerSchedulingData):Set<string> {
 return new Set(Object.values(data.operators).filter(op=>op.exhaustRequire&&op.group&&(!op.multiGroup||!!op.shiftGroup)&&!op.room.startsWith('dorm')).map(op=>op.group))
}

/** Revalidate an ordinary request after a backup change or an observed charge. */
export function mowerOrdinaryCoordinationNeeded(data:MowerSchedulingData,names:readonly string[]):boolean {
 const exhausted=new Set([...mowerExhaustGroups(data),...mowerForcedWorkGroups(data)])
 const eligible=(name:string)=>{
  const op=data.operators[name]
  if(!op||!op.isHigh()||op.multiGroup&&!op.independentRest&&!op.shiftGroup||op.group&&!data.isGroupShiftAnchor(op)||op.isResting()||data.isStandby(name)||['factory','train'].includes(op.room)||['factory','train'].includes(op.currentRoom)||data.busyRestingNames.has(name)||data.reservedProductReplacements.has(name)||op.exhaustRequire||exhausted.has(op.group)||alphaRestingTier(data,name)===7)return false
  const mood=mowerDormCandidateMood(data,name),threshold=op.lowerLimit+(op.upperLimit-op.lowerLimit)*restingThresholdFor(op,data.policy)
  return mood!==undefined&&mood<op.upperLimit&&mood<=(op.customMoodLimit?threshold:Math.floor(threshold))&&(op.customMoodLimit||op.upperLimit-mood>=2)
 }
 const units=new Map<string,{requestNames:string[];members:string[]}>()
 for(const name of names){
  const op=data.operators[name]
  if(!op||!op.isHigh()||op.room.startsWith('dorm')||op.workaholic)continue
  if(op.multiGroup&&!op.shiftGroup&&!op.independentRest)continue
  const key=op.group?'group:'+op.group:'operator:'+name,previous=units.get(key)
  if(previous)previous.requestNames.push(name)
  else units.set(key,{requestNames:[name],members:op.group?data.shiftGroupMembers(op.group):[name]})
 }
 const pending=[...units.values()].filter(unit=>!mowerCoordinationRequestFulfilled(data,unit.requestNames))
 return pending.length>0&&pending.every(unit=>unit.members.some(eligible))
}

/** Retained failures still own their request; dispatch visibility is unrelated. */
export function mowerPendingExhaust(tasks:readonly MowerTask[],name:string):MowerTask|undefined {
 return tasks.find(task=>task.type===T.EXHAUST_OFF&&task.metadata.split(',').includes(name))
}

/** A concrete departure owns a request only when it covers every recovery-requiring member. */
export function mowerPendingExhaustDeparture(data:MowerSchedulingData,tasks:readonly MowerTask[],candidates:readonly string[],requestNames:readonly string[]=candidates):MowerTask|undefined {
 const requestGroups=new Set(data.shiftRequestGroups(requestNames)),members=candidates.map(name=>data.operators[name]!).filter(op=>!op.room.startsWith('dorm')&&!op.workaholic&&(!op.multiGroup||requestGroups.has(op.shiftGroup??'')||requestNames.includes(op.name)&&op.independentRest))
 if(!members.length)return
 return tasks.find(task=>{
  if(task.type!==T.SHIFT_OFF)return false
  const resting=new Set(Object.entries(task.plan).flatMap(([room,row])=>room.startsWith('dorm')?row.filter(name=>!['','Current','Free'].includes(name)):[])),working=new Set(Object.entries(task.plan).flatMap(([room,row])=>room.startsWith('dorm')?[]:row))
  for(const member of members)if(member.isResting()){
   const target=task.plan[member.currentRoom]
   if(target===undefined||member.currentIndex>=0&&['Current',member.name].includes(target[member.currentIndex]??''))resting.add(member.name)
  }
  return members.every(member=>resting.has(member.name)&&!working.has(member.name))
 })
}
