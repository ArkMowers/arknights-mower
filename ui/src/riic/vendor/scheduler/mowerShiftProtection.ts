// Complete-task protection follows Mower alpha's backup_shift_active boundary.
// Upstream: b2d9ac85fe070e805aadf0d5f44fc095c1e95253 (MIT, Copyright 2021 Nano).
// Bed repair is an application preflight over the existing default dorm rules.
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerFindDormSlot} from './mowerDormAssignment'
import {projectMowerArrangements} from './mowerObservations'
import {alphaDormResidents,alphaRestoreDisplaced} from './mowerAlphaDorm'
import {MOWER_TASK_TYPES as T,toMowerMicros,type MowerTask,type MowerTaskPlan} from './mowerTaskQueue'

export function mowerProtectedShift(task:MowerTask):boolean {
 return [T.SHIFT_OFF,T.SHIFT_ON,T.EXHAUST_OFF,T.SELF_CORRECTION,T.RE_ORDER,T.FILL_DORM,T.NOT_SPECIFIC].includes(task.type)&&Object.keys(task.plan).length>0
}
export type MowerShiftBedPreparation=
 | {ready:true;plan:MowerTaskPlan;relocated:string[]}
 | {ready:false;names:string[];retryAtMicros:number}

/** Preflight only: preserve unfinished primaries evicted by explicit dorm tasks.
 * The physical adapter still owns every room commit and recovery observation. */
export function prepareMowerShiftBeds(data:MowerSchedulingData,task:MowerTask,pending:MowerTask[]):MowerShiftBedPreparation {
 const plan=structuredClone(task.plan)
 if(data.alpha){const copy=projectMowerArrangements(data,[]);alphaRestoreDisplaced(copy,alphaDormResidents(copy),plan,pending.filter(t=>t!==task).map(t=>Object.assign(Object.create(Object.getPrototypeOf(t)),t,{plan:structuredClone(t.plan)})));return {ready:true,plan,relocated:[]}}
 if(!Object.keys(plan).some(room=>room.startsWith('dorm')))return {ready:true,plan,relocated:[]}
 // A partial physical arrangement vacates trailing slots; do not project them as Current.
 const projection=Object.fromEntries(Object.entries(plan).map(([room,names])=>[room,room.startsWith('dorm')?[...names,...Array(Math.max(0,(data.plan[room]?.length??names.length)-names.length)).fill('Free')]:names]))
 let projected=projectMowerArrangements(data,[projection])
 const displaced=Object.values(data.operators).filter(op=>{
  if(!op.isHigh()||op.workaholic||op.room.startsWith('dorm')||!op.isResting())return false
  const bed=data.getDormByName(op.name)?.[1],unfinished=bed?.timeMicros!==undefined?bed.timeMicros>data.nowMicros:op.mood>=0&&op.mood<op.upperLimit
  const after=projected.operators[op.name]!
  return unfinished&&!after.currentRoom&&!projected.isStandby(op.name)
 })
 if(!displaced.length)return {ready:true,plan,relocated:[]}
 const used=new Set<number>()
 // Respect both this task's destinations and other queued explicit assignments.
 for(const intent of [projection,...pending.filter(t=>t!==task).map(t=>t.plan)])for(const [room,names] of Object.entries(intent))if(room.startsWith('dorm'))for(const [index,name] of names.entries())if(name!=='Current'){
  const bedIndex=projected.dorms.findIndex(b=>b.position[0]===room&&b.position[1]===index)
  if(bedIndex>=0)used.add(bedIndex)
 }
 const relocated:string[]=[]
 for(const op of displaced){
  const bedIndex=mowerFindDormSlot(projected,op.name,used,!!op.group)
  if(bedIndex===undefined){
   const times=[...data.dorms,...projected.dorms].flatMap(b=>b.timeMicros!==undefined&&b.timeMicros>data.nowMicros?[b.timeMicros]:[])
   const retry=times.length?Math.min(...times)+toMowerMicros(1/3600):data.nowMicros+toMowerMicros(.5)
   return {ready:false,names:displaced.map(member=>member.name),retryAtMicros:Math.max(data.nowMicros+toMowerMicros(1/60),retry)}
  }
  used.add(bedIndex)
  const [room,index]=projected.dorms[bedIndex]!.position
  const names=plan[room]??=Array(data.plan[room]!.length).fill('Current')
  names[index]=op.name
  const move=Array(data.plan[room]!.length).fill('Current');move[index]=op.name
  projected=projectMowerArrangements(projected,[{[room]:move}])
  relocated.push(op.name)
 }
 return {ready:true,plan,relocated}
}
