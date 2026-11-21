import {isMowerDormFiller} from './mowerDormFiller'
import {mowerDormCandidateMood} from './mowerSchedulingMood'
import {mowerGroupRecoveryDeadline,mowerGroupRecoveryWorkers} from './mowerGroupRecovery'
import {mowerForcedWorkGroups} from './mowerBackupGroupTasks'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,type MowerTask,type MowerTaskPlan} from './mowerTaskQueue'
import {alphaPosition} from './mowerAlphaDorm'
import {mowerCoordinationRecoveryMembers,mowerCoordinationRequestFulfilled} from './mowerReplacementCoordination'

const unstartedFailed=(task:MowerTask)=>!!task.executionFailure&&!task.backupShiftActive&&!task.arrangementStarted&&!task.productShiftLocked&&!task.dormRecoveryRestore.length

/** Keep source identity while advancing only the unfinished work of the same request. */
export function mowerRemainingCoordinationRequests(task:MowerTask):string[]{
 const origins=task.coordinationRequestNames.length?task.coordinationRequestNames:task.type===T.EXHAUST_OFF?task.metadata.split(',').filter(Boolean):[]
 return origins.filter(name=>!(task.coordinationCompletedRequestNames??[]).includes(name))
}
/** A completed admission remains completed after that group's ordinary return. */
export function recordMowerCoordinationProgress(data:MowerSchedulingData,tasks:readonly MowerTask[]):void {
 for(const task of tasks){
  if(!task.ordinaryCoordination||task.exhaustSupport||task.arrangementStarted||task.backupShiftActive||task.productShiftLocked||task.backupExplicitSlots.size||task.backupGroupRequest||task.dormRecoveryRestore.length)continue
  const completed=mowerRemainingCoordinationRequests(task).filter(name=>mowerCoordinationRequestFulfilled(data,[name],true))
  if(completed.length)task.coordinationCompletedRequestNames=[...new Set([...(task.coordinationCompletedRequestNames??[]),...completed])]
 }
}

/** Actual recovery admission completes an ordinary request without replaying incidental moves. */
export function mowerCompletedOrdinaryRestRequest(data:MowerSchedulingData,task:MowerTask):boolean {
 if(!unstartedFailed(task)||!task.ordinaryCoordination||task.exhaustSupport||task.backupExplicitSlots.size||task.backupGroupRequest||![T.SHIFT_OFF,T.EXHAUST_OFF].includes(task.type))return false
 if(!task.coordinationRequestNames.length)return false
 const requested=mowerRemainingCoordinationRequests(task)
 if(!requested.length)return true
 if(requested.some(name=>!data.operators[name]))return false
 const required=mowerCoordinationRecoveryMembers(data,requested,true)
 return required.length>0&&required.every(op=>op.isResting()&&data.currentOperator(op.currentRoom,op.currentIndex)===op)
}

/** A failed preview's incidental bed moves do not own another group's completed recovery. */
export function mowerRetainedRecoveryMayReturn(data:MowerSchedulingData,task:MowerTask,group:string):boolean {
 if(!unstartedFailed(task))return false
 const intent=task.backupShiftIntent??task.plan,members=new Set(data.shiftGroupMembers(group))
 for(const [room,row] of Object.entries(intent))for(const [index,name] of row.entries()){
  if(['Current',''].includes(name))continue
  const op=data.operators[name],owner=data.operators[data.plan[room]?.[index]??'']
  const explicit=task.backupExplicitSlots.has(alphaPosition(room,index))
  // Actual primary shifts and explicitly requested backup positions remain owned.
  if(owner&&members.has(owner.name)&&(!room.startsWith('dorm')||owner.room===room&&owner.index===index))return false
  if(op&&members.has(op.name)&&(!room.startsWith('dorm')||explicit))return false
  if(explicit&&members.has(data.currentOperator(room,index)?.name??''))return false
 }
 return true
}

/** A failed, unstarted admission may wait for its current bed occupant's normal return. */
export function mowerRetainedBedAllowsReturn(data:MowerSchedulingData,task:MowerTask,name:string):boolean {
 if(!unstartedFailed(task))return false
 const op=data.operators[name]
 if(!op?.isHigh()||op.group||!op.room||op.room.startsWith('dorm')||!op.isResting()||op.multiGroup&&op.groupBindings.some(binding=>binding.group&&data.groupIsResting(binding.group))||name in task.releaseDormTargets())return false
 const bed=data.getDormByName(name)?.[1],target=task.plan[op.currentRoom]?.[op.currentIndex]
 if(!bed||bed.position[0]!==op.currentRoom||bed.position[1]!==op.currentIndex||!target||!data.operators[target]||target===name)return false
 return [task.backupShiftIntent??task.plan,task.plan].every(plan=>!Object.values(plan).some(row=>row.includes(name))&&(plan[op.room]?.[op.index]===undefined||plan[op.room]?.[op.index]==='Current'))
}

/** Reconcile only after an observed return; preserve the original task and unrelated remaining work. */
export function reconcileMowerRetainedRecovery(data:MowerSchedulingData,task:MowerTask):void {
 const failure=task.executionFailure;if(!failure)return
 const returnedGroups=new Set(Object.values(data.operators).filter(op=>{
  const previous=failure.snapshot.observations[op.name]
  return !!op.group&&data.isGroupShiftAnchor(op)&&previous?.[0].startsWith('dorm')&&op.currentRoom===op.room&&op.currentIndex===op.index&&!op.moodIsPrediction&&mowerRetainedRecoveryMayReturn(data,task,op.group)
 }).map(op=>op.group).filter(group=>data.shiftGroupMembers(group).map(name=>data.operators[name]!).filter(op=>data.isGroupShiftAnchor(op)).every(op=>op.currentRoom===op.room&&op.currentIndex===op.index&&!op.moodIsPrediction)))
 const returned=new Set([...returnedGroups].flatMap(group=>data.shiftGroupMembers(group)).filter(name=>{const op=data.operators[name]!;return !op.room.startsWith('dorm')&&op.currentRoom===op.room&&op.currentIndex===op.index&&!op.moodIsPrediction}))
 if(!returned.size)return
 const prune=(plan:MowerTaskPlan)=>{
  for(const [room,row] of Object.entries(plan))if(room.startsWith('dorm')){
   row.forEach((name,index)=>{if(returned.has(name))row[index]='Current'})
   if(row.every(name=>['Current',''].includes(name)))delete plan[room]
  }
 }
 prune(task.plan)
 if(task.backupShiftIntent)prune(task.backupShiftIntent)
 prune(task.dormFillPlan)
}

/** Restore beds for off-duty primaries still bound by explicit or active group recovery. */
export function mowerOffDutyFullRecoveryMembers(data:MowerSchedulingData):Set<string> {
 const required=new Set<string>(),forced=mowerForcedWorkGroups(data)
 if(data.alpha)for(const group of Object.keys(data.groupRecoveryFullMembers)){
  if(data.groupShiftState[group]===false||forced.has(group))continue
  mowerGroupRecoveryDeadline(data,group).requiredNames.forEach(name=>required.add(name))
 }
 return new Set(Object.values(data.operators).filter(op=>{
  if(!data.alpha||!op.isHigh()||!op.restInFull&&!required.has(op.name)||op.workaholic||op.room.startsWith('dorm')||op.currentRoom&&!op.isResting()||data.restMoodComplete(op.name))return false
  const mood=mowerDormCandidateMood(data,op.name)
  return mood!==undefined&&mood<op.upperLimit
 }).map(op=>op.name))
}


/** A normal return may use its own unfinished recovery as a prerequisite, without releasing other owners. */
export function mowerPendingReturnAllowsRecovery(data:MowerSchedulingData,task:MowerTask,name:string,recovering:ReadonlySet<string>=mowerOffDutyFullRecoveryMembers(data)):boolean {
 const request=task.backupGroupRequest,once=request?.action==='on'&&request.mode==='once'&&data.shiftGroupMembers(request.group).includes(name)
 if(!recovering.has(name)||task.type!==T.SHIFT_ON||task.metadata&&!(once&&data.operators[task.metadata]&&data.isGroupShiftAnchor(data.operators[task.metadata]!,request!.group))||task.arrangementStarted||task.backupShiftActive||task.productShiftLocked||task.strictMoodLimit||task.exhaustSupport||task.ordinaryCoordination||task.preferredReplacementRestore||task.advanceSupportSwap||request&&!once||task.fiaReturnTarget||task.backupExplicitSlots.size||task.productLockNames.size||task.productLockSlots.size||task.dormRecoveryRestore.length||task.arrangementRetryRoom!==undefined||task.arrangementRetryDueMicros!==undefined||task.arrangementRetryCount!==undefined||task.urgentRecoveryRequestNames.length||task.urgentRecoverySupportNames.length||task.urgentRecoveryReservedNames.length||task.urgentRecoveryReservedSlots.length||task.coordinationRequestNames.length||task.coordinationAdmissionPlan)return false
 const op=data.operators[name]!
 if(data.reservedProductReplacements.has(name)||op.group&&mowerForcedWorkGroups(data).has(op.group))return false
 for(const plan of [task.plan,task.backupShiftIntent])if(plan)for(const [room,row] of Object.entries(plan))for(const [index,target] of row.entries())if(target===name&&(room!==op.room||index!==op.index))return false
 const required=!!op.group&&mowerGroupRecoveryWorkers(data,op.group).some(member=>member.name===name)
 return Object.entries(task.plan).some(([room,row])=>!room.startsWith('dorm')&&row.some((target,index)=>{
  const anchor=data.operators[target]
  return !!anchor&&anchor.room===room&&anchor.index===index&&(target===name||!!op.group&&required&&data.isGroupShiftAnchor(anchor,op.group))
 }))
}

/** Only the owner's currently vacant future clear slots can host its recovery prerequisite. */
export function mowerPendingReturnRecoverySlots(data:MowerSchedulingData,task:MowerTask,name:string,recovering:ReadonlySet<string>=mowerOffDutyFullRecoveryMembers(data)):Set<string> {
 if(!mowerPendingReturnAllowsRecovery(data,task,name,recovering))return new Set()
 return new Set(data.dorms.filter(bed=>!bed.name&&data.effectiveFreeSlot(bed)&&(!data.currentOperator(...bed.position)||data.useDormFillers&&isMowerDormFiller(data.currentOperator(...bed.position)!.name))&&task.plan[bed.position[0]]?.[bed.position[1]]==='Free').map(bed=>alphaPosition(...bed.position)))
}
