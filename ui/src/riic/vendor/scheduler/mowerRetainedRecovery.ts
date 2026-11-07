import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,type MowerTask,type MowerTaskPlan} from './mowerTaskQueue'
import {alphaPosition} from './mowerAlphaDorm'

const unstartedFailed=(task:MowerTask)=>!!task.executionFailure&&!task.backupShiftActive&&!task.arrangementStarted&&!task.productShiftLocked&&!task.dormRecoveryRestore.length

/** Actual recovery admission completes an ordinary request without replaying incidental moves. */
export function mowerCompletedOrdinaryRestRequest(data:MowerSchedulingData,task:MowerTask):boolean {
 if(!unstartedFailed(task)||!task.ordinaryCoordination||task.exhaustSupport||task.backupExplicitSlots.size||task.backupGroupRequest||![T.SHIFT_OFF,T.EXHAUST_OFF].includes(task.type))return false
 const requested=task.coordinationRequestNames
 if(!requested.length||requested.some(name=>!data.operators[name]))return false
 const groups=new Set(data.shiftRequestGroups(requested))
 const names=new Set([...groups].flatMap(group=>data.shiftGroupMembers(group)).concat(requested.filter(name=>!data.operators[name]!.group)))
 const required=[...names].map(name=>data.operators[name]!).filter(op=>op.isHigh()&&!op.room.startsWith('dorm')&&!op.workaholic&&!data.canStandby(op)&&(!op.multiGroup||!!op.shiftGroup&&groups.has(op.shiftGroup)||requested.includes(op.name)&&op.independentRest))
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
