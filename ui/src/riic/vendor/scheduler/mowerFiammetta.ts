// Source plan_fia target selection. Physical charging and restoration are task I/O.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88; shared-follower priority: e470bb9be1 (MIT, Copyright 2021 Nano).
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerDormCandidateMood} from './mowerSchedulingMood'
import {MowerTask,MOWER_TASK_TYPES as T,type MowerTaskQueue} from './mowerTaskQueue'
import {mowerArrangementGroupTransitions,normalizeMowerSharedArrangement,commitMowerGroupShifts} from './mowerSharedGroups'
import {alphaRebalanceClosingDorms} from './mowerAlphaDorm'
import {projectMowerArrangements} from './mowerObservations'
import {mowerGroupRecoveryDeadline,mowerObservedRecoveryDeadline,mowerRecoveryMoodComplete} from './mowerGroupRecovery'
import {MowerResourceWaitError} from './mowerNativeErrors'

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


/** A confirmed exchange keeps its return obligation after restoring the original roster. */
export function queueMowerFiaReturn(data:MowerSchedulingData,queue:MowerTaskQueue,charge:MowerTask):void {
 const target=charge.fiaReturnTarget,op=target?data.operators[target]:undefined
 if(!op||!charge.fiaChargeConfirmed||charge.fiaReturnQueued||charge.fiaReturnMicros===undefined)return
 const members=op.group?data.shiftGroupMembers(op.group):[op.name],plan:Record<string,string[]>={},projected=projectMowerArrangements(data,[])
 for(const name of members){const member=data.operators[name]!;if(member.room&&data.plan[member.room])(plan[member.room]??=Array(data.plan[member.room]!.length).fill('Current'))[member.index]=name}
 if(!normalizeMowerSharedArrangement(projected,plan,mowerArrangementGroupTransitions(projected,plan)))return
 commitMowerGroupShifts(projected,mowerArrangementGroupTransitions(projected,plan))
 alphaRebalanceClosingDorms(projected,plan,members)
 if(!Object.keys(plan).length)return
 const task=new MowerTask({type:T.SHIFT_ON,plan});task.timeMicros=charge.fiaReturnMicros
 task.fiaReturnTarget=target;task.fiaReturnMicros=task.timeMicros;task.executionRetained=true
 queue.tasks.push(task);charge.fiaReturnQueued=true
}

/** Explicit full recovery and a latched group wait remain binding on a charging return. */
export function prepareMowerFiaReturn(data:MowerSchedulingData,task:MowerTask):void {
 if(task.type!==T.SHIFT_ON)return
 const op=task.fiaReturnTarget?data.operators[task.fiaReturnTarget]:undefined
 if(!op||task.arrangementStarted||task.fiaReturnMicros===undefined)return
 const recovery=op.group?mowerGroupRecoveryDeadline(data,op.group):{requiredNames:op.restInFull?[op.name]:[],timeMicros:undefined}
 const capped=!!op.group&&data.groupRecoveryReturnMicros[op.group]!==undefined&&data.groupMoodGapMaxExtraWaitHours>0
 const unknown=recovery.requiredNames.filter(name=>!mowerRecoveryMoodComplete(data,data.operators[name])&&mowerObservedRecoveryDeadline(data,data.operators[name]!)===undefined&&(data.operators[name]!.restInFull||!capped))
 if(unknown.length)throw new MowerResourceWaitError('肥鸭回班等待有效恢复观测：'+unknown.join('、'))
 task.timeMicros=Math.max(task.fiaReturnMicros,recovery.timeMicros!==undefined&&recovery.timeMicros>data.nowMicros?recovery.timeMicros:task.fiaReturnMicros)
}
