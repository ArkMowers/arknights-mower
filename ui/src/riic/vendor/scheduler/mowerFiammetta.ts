// Source plan_fia target selection. Physical charging and restoration are task I/O.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88; shared-follower priority: e470bb9be1 (MIT, Copyright 2021 Nano).
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerDormCandidateMood} from './mowerSchedulingMood'
export function selectMowerFiaTarget(data:MowerSchedulingData,targets:string[],fool:boolean,threshold=.9):string|undefined {
 for(const name of targets){
  const op=data.operators[name]!,mood=op.currentMood(data.nowMicros)
  if(mood>=24||mood>threshold*24||op.restInFull&&op.exhaustRequire&&!op.isResting())continue
  if(op.group&&data.group(op.group).some(member=>{
   if(member===name)return false
   const peer=data.operators[member]!
   if(peer.multiGroup||peer.room.startsWith('dorm')||peer.workaholic&&!targets.includes(member))return false
   return peer.currentMood(data.nowMicros)-peer.lowerLimit<mood-op.lowerLimit
  }))continue
  return name
 }
 if(fool||!targets.length)return undefined
 let target:string|undefined,mood=24
 for(const name of targets){
  const op=data.operators[name]!,current=op.currentMood(data.nowMicros)
  if(op.restInFull&&op.exhaustRequire&&!op.isResting())continue
  if(current<mood){target=name;mood=current}
 }
 return target
}

/** planning uses saved mood and a future saved timestamp; only otherwise reads the UI timer. */
export function mowerFiaReadyMicros(op:import('./mowerOperatorState').MowerOperatorState,nowMicros:number,readTimer:()=>number):number {
 if(op.mood===24)return nowMicros
 if(op.timeStampMicros!==undefined&&op.timeStampMicros>nowMicros)return op.timeStampMicros
 return readTimer()
}

/** 未知心情不能判为满；这里只排除实际 24 点，不使用个人回满上限。 */
export function mowerFiaTargetsFull(data:MowerSchedulingData,targets:readonly string[]):boolean {
 return targets.length>0&&targets.every(name=>mowerDormCandidateMood(data,name)===24)
}
