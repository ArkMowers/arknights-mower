import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,MowerTaskQueue,type MowerTask} from './mowerTaskQueue'
import {mowerArrangementGroupTransitions,normalizeMowerSharedArrangement,commitMowerGroupShifts,mowerRestingBindingGroups,mowerSharedReplacements} from './mowerSharedGroups'
import {projectMowerArrangements} from './mowerObservations'
import {cloneMowerShiftTask,prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {alphaPosition} from './mowerAlphaDorm'
import {MowerShiftPreviewError} from './mowerNativeErrors'

/** Admit a due normal return only after proving the retained arrangement becomes feasible. */
export function mowerVerifiedRecoveryDependencyReturn(data:MowerSchedulingData,retained:MowerTask,candidate:MowerTask,pending:readonly MowerTask[],model:MowerShiftModel):boolean {
 if(!retained.executionFailure||retained.arrangementStarted||retained.backupShiftActive||retained.productShiftLocked||retained.dormRecoveryRestore.length||candidate.type!==T.SHIFT_ON||candidate.timeMicros>data.nowMicros)return false
 const returning=new Set(Object.entries(mowerArrangementGroupTransitions(data,candidate.plan)).filter(([group,resting])=>!resting&&data.groupIsResting(group)).map(([group])=>group))
 if(!returning.size)return false
 const blockedSlots:[string,number][]=[]
 for(const [room,row] of Object.entries(retained.plan))row.forEach((name,index)=>{
  const owner=data.operators[data.plan[room]?.[index]??'']
  if(!['Current',''].includes(name)&&owner?.group&&returning.has(owner.group)&&!room.startsWith('dorm'))blockedSlots.push([room,index])
 })
 const original=projectMowerArrangements(data,[]),failed=cloneMowerShiftTask(retained)
 const transitions=mowerArrangementGroupTransitions(original,failed.plan)
 const sharedBlockers=Object.values(original.operators).filter(op=>{
  if(!op.multiGroup||failed.backupExplicitSlots.has(alphaPosition(op.room,op.index)))return false
  if(op.index>=(failed.plan[op.room]?.length??0)&&!op.groupBindings.some(binding=>binding.group in transitions))return false
  const groups=mowerRestingBindingGroups(original,op,transitions)
  return groups.some(group=>returning.has(group))&&!mowerSharedReplacements(op,groups).length
 })
 if(!blockedSlots.length&&!sharedBlockers.length)return false
 if(normalizeMowerSharedArrangement(original,structuredClone(failed.plan),transitions,failed.backupExplicitSlots))return false
 const queue=new MowerTaskQueue();queue.tasks=pending.filter(task=>task!==retained&&task!==candidate).map(cloneMowerShiftTask)
 const next=cloneMowerShiftTask(candidate);queue.tasks.push(next)
 try {
  if(!normalizeMowerSharedArrangement(original,next.plan,undefined,next.backupExplicitSlots))return false
  next.groupShiftTransitions=mowerArrangementGroupTransitions(original,next.plan)
  prepareMowerShiftCycle(original,next,queue,model)
  const conditions=next.backupShiftConditions??original.planConditions
  let projected=model.swap(projectMowerArrangements(original,[]),conditions,next.backupGroup)
  projected=projectMowerArrangements(projected,[next.plan]);commitMowerGroupShifts(projected,next.groupShiftTransitions)
  failed.groupShiftTransitions=mowerArrangementGroupTransitions(projected,failed.plan)
  const changedOwners=JSON.stringify(conditions)!==JSON.stringify(original.planConditions)&&blockedSlots.length>0&&blockedSlots.every(([room,index])=>projected.plan[room]?.[index]!==data.plan[room]?.[index])
  const releasedBinding=sharedBlockers.some(before=>{
   const after=projected.operators[before.name]
   if(!after||projected.plan[before.room]?.[before.index]!==before.name)return false
   const previous=mowerRestingBindingGroups(original,before,transitions),remaining=mowerRestingBindingGroups(projected,after,failed.groupShiftTransitions)
   return previous.some(group=>returning.has(group)&&!remaining.includes(group)&&!projected.groupIsResting(group))&&mowerSharedReplacements(after,remaining).length>0
  })
  if(!changedOwners&&!releasedBinding)return false
  if(!normalizeMowerSharedArrangement(projected,failed.plan,failed.groupShiftTransitions,failed.backupExplicitSlots))return false
  queue.tasks=queue.tasks.filter(task=>task!==next);queue.tasks.push(failed)
  prepareMowerShiftCycle(projected,failed,queue,model)
  const finalRules=model.swap(projectMowerArrangements(projected,[]),failed.backupShiftConditions??projected.planConditions,failed.backupGroup)
  return normalizeMowerSharedArrangement(finalRules,failed.plan,failed.groupShiftTransitions,failed.backupExplicitSlots)
 }catch(error){if(error instanceof MowerShiftPreviewError)return false;throw error}
}
