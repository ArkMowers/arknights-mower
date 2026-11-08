import {mowerHeldRestGroups} from './mowerBackupGroupTasks'
import {mowerRestingBindingGroups} from './mowerSharedGroups'
import {mowerGroupRecoveryDeadline,mowerRecoveryMoodComplete} from './mowerGroupRecovery'
import {alphaPosition} from './mowerAlphaDorm'
import type {MowerDormBatch} from './mowerDormTasks'
import type {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'

/** Shared physical return policy for metadata and ordinary-recall forecasts. */
export function mowerAlphaRecoveryBatches(actual:MowerSchedulingData,data:MowerSchedulingData,excluded:{names:ReadonlySet<string>;groups:ReadonlySet<string>;slots:ReadonlySet<string>}={names:new Set(),groups:new Set(),slots:new Set()}):{batches:MowerDormBatch[];free:MowerDormState[]} {
 const {names,groups,slots}=excluded,now=data.nowMicros
 const waitingForActualGroup=(name:string)=>{const op=actual.operators[name];return !!op?.independentRest&&mowerRestingBindingGroups(actual,op).length>0}
 const grouped=new Map<string,MowerDormState[]>(),free:MowerDormState[]=[]
 for(const bed of data.allDorms()){
  const op=data.operators[bed.name]
  if(!op||!data.groupDorms.includes(bed)&&!data.effectiveFreeSlot(bed)||names.has(op.name)||groups.has(op.group)||slots.has(alphaPosition(...bed.position)))continue
  if(!waitingForActualGroup(op.name)&&(!op.multiGroup||op.independentRest||!!op.shiftGroup)&&(!op.group||data.isGroupShiftAnchor(op)||op.isHigh()&&!op.workaholic&&!op.room.startsWith('dorm')&&data.groupRecoveryFullMembers[op.group]?.includes(op.name)))grouped.set(op.group,[...(grouped.get(op.group)??[]),bed])
  if(data.dorms.includes(bed)&&!op.restMoodLimit&&!data.skipIdleDormRelease(op.name))free.push(bed)
 }
 const batches=new Map<number,MowerDormBatch>()
 const add=(time:number,beds:MowerDormState[],full:boolean)=>{const previous=batches.get(time);if(previous){previous.dorms.push(...beds);previous.restInFull=!!(previous.restInFull||full)}else batches.set(time,{timeMicros:time,dorms:[...beds],restInFull:full})}
 const held=mowerHeldRestGroups(data)
 for(const [group,beds] of grouped){
  if(held.has(group))continue
  const primaries=beds.filter(b=>(!data.operators[b.name]!.multiGroup||data.operators[b.name]!.independentRest||!!data.operators[b.name]!.shiftGroup)&&data.operators[b.name]!.isHigh())
  const priority=primaries.filter(b=>data.operators[b.name]!.restingPriority==='high'),ordinary=primaries.filter(b=>data.operators[b.name]!.restingPriority!=='standby')
  const high=group?(priority.length?priority:ordinary.length?ordinary:primaries.filter(b=>!data.canStandby(data.operators[b.name]!))):primaries
  if(group){
   const recovery=mowerGroupRecoveryDeadline(data,group)
   if(data.groupRecoveryFullMembers[group]&&data.groupIsResting(group)&&actual.groupIsResting(group)){actual.groupRecoveryFullMembers[group]=[...data.groupRecoveryFullMembers[group]!];if(data.groupRecoveryReturnMicros[group]!==undefined)actual.groupRecoveryReturnMicros[group]=data.groupRecoveryReturnMicros[group]!}
   if(recovery.requiredNames.length||recovery.timeMicros!==undefined){
    if(recovery.timeMicros!==undefined)add(recovery.timeMicros,high.length?high:beds.filter(b=>data.operators[b.name]!.isHigh()),true)
    continue
   }
   const nearest=high.filter(b=>b.timeMicros!==undefined).sort((a,b)=>a.timeMicros!-b.timeMicros!)[0]
   if(nearest)add(nearest.timeMicros!,high,false)
  }
  if(high.length&&!group)for(const b of high){const op=data.operators[b.name]!,completed=mowerRecoveryMoodComplete(data,op);if(b.timeMicros!==undefined||completed)add(completed?now:b.timeMicros!,[b],op.restInFull)}
 }
 return {batches:[...batches.values()],free}
}
