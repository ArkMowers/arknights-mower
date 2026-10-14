// Port of dorm_recovery.py and default ensure_dorm_recovery_order, Mower alpha.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {MowerArrangementError} from './mowerArrangementError'
import {hasRestingMood,restingMood,type MowerOperatorState,type MowerRecoveryManager} from './mowerOperatorState'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,type MowerTask,type MowerTaskQueue} from './mowerTaskQueue'
export function mowerRecoveryManagers(data:MowerSchedulingData,room:string,names:string[]):MowerRecoveryManager[]{
 return names.length!==data.plan[room]?.length?[]:names.slice(0,2).flatMap((name,index)=>data.operators[name]?.singleRecoveryManager?[[name,index,data.operators[name]!.dormPositionVersion] as MowerRecoveryManager]:[])
}
export function mowerRecoveryTarget(data:MowerSchedulingData,room:string,names:string[]):MowerOperatorState|undefined {
 if(!room.startsWith('dorm')||names.length!==data.plan[room]?.length)return undefined
 const index=names.findIndex((_,i)=>data.dynamicDormPosition(room,i))
 const target=data.operators[names[index]??'']
 return target&&target.mood<24&&!target.room.startsWith('dorm')?target:undefined
}
const sameManagers=(a:MowerRecoveryManager[],b:MowerRecoveryManager[])=>a.length===b.length&&a.every((x,i)=>x.every((v,j)=>v===b[i]![j]))
function active(op:MowerOperatorState,room:string,index:number){return op.dormRecoveryRoom===room&&op.dormRecoveryIndex===index&&op.currentRoom===room&&op.currentIndex===index}
function tier(data:MowerSchedulingData,name:string):number {
 const op=data.operators[name]!
 if(data.freeBlacklist.includes(name)||op.workaholic)return 7
 if(data.restingPriorityNames.includes(name))return 0
 if(op.room==='train'&&op.index===0||op.currentRoom==='train'&&op.currentIndex===0)return 5
 if(op.isHigh())return op.restingPriority==='high'?1:op.restingPriority==='low'?2:4
 if(op.restingFromTrain)return 5
 return Object.values(data.operators).some(owner=>owner.nativeName!=='菲亚梅塔'&&owner.replacement.includes(name))?5:6
}
/** Known full padding only; unregistered UI candidates cannot confirm a 24-mood cache. */
function fullPadding(data:MowerSchedulingData,excluded:Set<string>,room:string):string[] {
 const residents=new Set(data.currentRoom(room,true)),support=data.currentOperator('train',0)?.name
 return Object.values(data.operators).filter(op=>{
  if(excluded.has(op.name)||data.busyRestingNames.has(op.name)||op.name===support||op.isHigh()||op.currentRoom&&!(residents.has(op.name)&&op.isResting())||data.restMoodComplete(op.name)||tier(data,op.name)===7)return false
  const checked=data.policy.experimentalDormLogic&&!op.currentRoom&&op.idleRestCheck!==undefined&&op.idleRestCheck[0]>=op.upperLimit&&op.idleRestCheck[1]===op.mood&&op.idleRestCheck[2]===op.timeStampMicros
  if(!checked&&restingMood(op,data.nowMicros)<op.upperLimit)return false
  return !op.restMoodLimit&&hasRestingMood(op,data.nowMicros)&&restingMood(op,data.nowMicros)>=24
 }).sort((a,b)=>restingMood(a,data.nowMicros)-restingMood(b,data.nowMicros)||tier(data,a.name)-tier(data,b.name)).map(op=>op.name)
}
export function mowerRecoveryOrderPlan(data:MowerSchedulingData,room:string,names:string[],reserved:string[]=[]):string[]|undefined {
 const target=mowerRecoveryTarget(data,room,names);if(!target)return undefined
 const managers=mowerRecoveryManagers(data,room,names);if(!managers.length)return undefined
 const index=names.indexOf(target.name)
 if(active(target,room,index)&&sameManagers(target.dormRecoveryFixed,managers)&&managers.every(([name,i])=>data.operators[name]!.currentRoom===room&&data.operators[name]!.currentIndex===i))return undefined
 const managerNames=new Set(managers.map(([name])=>name)),retained:string[]=[]
 for(const [index,name] of names.entries()){
  if(name===target.name||managerNames.has(name)){retained.push(name);continue}
  if(data.dynamicDormPosition(room,index)){retained.push('');continue}
  const op=data.operators[name]
  if(data.dormReplacementForSlot(name,room,index)&&(!op||op.timeStampMicros===undefined||op.mood<24)){retained.push('');continue}
  if(['','Free','Current'].includes(name))return undefined
  retained.push(name)
 }
 while(retained.length&&!retained[retained.length-1])retained.pop()
 if(retained.includes('')){
  const padding=fullPadding(data,new Set([...names,...reserved]),room)
  for(const [index,name] of retained.entries())if(!name){const next=padding.shift();if(!next)return undefined;retained[index]=next}
 }
 return retained
}
export function ensureMowerDormRecovery(data:MowerSchedulingData,queue:MowerTaskQueue,task:MowerTask,room:string,names:string[],hooks:{arrangeTemporary:(names:string[])=>void}):boolean {
 if(!room.startsWith('dorm')||task.type===T.FIAMMETTA)return false
 const pending=task.dormRecoveryRestore,reserved=queue.tasks.flatMap(t=>Object.entries(t.plan).flatMap(([r,n])=>t!==task||r!==room?n:[]))
 const retained=mowerRecoveryOrderPlan(data,room,names,reserved)
 if(!retained)return pending.includes(room)
 const target=mowerRecoveryTarget(data,room,names)!,index=names.indexOf(target.name)
 if(queue.tasks.some(t=>{const upcoming=t.plan[room];return t!==task&&t.timeMicros>=task.timeMicros&&t.timeMicros<=task.timeMicros+1_000_000&&upcoming&&upcoming.length>index&&!['Current','Free','',target.name].includes(upcoming[index]!)}))return pending.includes(room)
 if(!pending.includes(room))pending.push(room)
 const expected=[...retained,...Array(names.length-retained.length).fill('')]
 let current=data.currentRoom(room,true)!
 if(!expected.every((name,index)=>name===current[index])){
  hooks.arrangeTemporary([...retained]);current=data.currentRoom(room,true)!
  if(!expected.every((name,index)=>name===current[index]))throw new MowerArrangementError('Mower dorm recovery ordering observation failed '+JSON.stringify({room,expected,current}))
 }
 if(!names.every((name,index)=>name===current[index])){
  const bed=data.getDormByName(target.name)?.[1]
  if(bed?.name===target.name)bed.timeMicros=undefined
 }
 const padding=retained.filter(name=>!names.includes(name))
 if(padding.some(name=>data.operators[name]!.mood<24)){target.clearDormRecovery();data.recoveryOrderVersion++;return true}
 if(target.mood<24){target.dormRecoveryRoom=room;target.dormRecoveryIndex=index;target.dormRecoveryFixed=mowerRecoveryManagers(data,room,names)}
 else target.clearDormRecovery()
 data.recoveryOrderVersion++
 return true
}
/** Confirmed entry order for the physical recovery adapter; invalid markers fall back to explicit game modeling. */
export function mowerConfirmedRecoveryTarget(data:MowerSchedulingData,room:string,provider:string):string|undefined {
 for(const op of Object.values(data.operators)){
  if(!active(op,room,op.dormRecoveryIndex)||!op.dormRecoveryFixed.some(([name])=>name===provider))continue
  if(op.dormRecoveryFixed.every(([name,index,version])=>{const manager=data.operators[name];return !!manager&&manager.currentRoom===room&&manager.currentIndex===index&&manager.dormPositionVersion===version}))return op.name
 }
 return undefined
}
/** Resolve every confirmed provider in one pass for a shared rate evaluation. */
export function mowerConfirmedRecoveryTargets(data:MowerSchedulingData):Map<string,Map<string,string>> {
 const rooms=new Map<string,Map<string,string>>()
 for(const op of Object.values(data.operators)){
  const room=op.dormRecoveryRoom,index=op.dormRecoveryIndex
  if(!room||!active(op,room,index)||!op.dormRecoveryFixed.length)continue
  if(!op.dormRecoveryFixed.every(([name,position,version])=>{
   const manager=data.operators[name]
   return !!manager&&manager.currentRoom===room&&manager.currentIndex===position&&manager.dormPositionVersion===version
  }))continue
  let targets=rooms.get(room)
  if(!targets){targets=new Map();rooms.set(room,targets)}
  for(const [provider] of op.dormRecoveryFixed)if(!targets.has(provider))targets.set(provider,op.name)
 }
 return rooms
}
