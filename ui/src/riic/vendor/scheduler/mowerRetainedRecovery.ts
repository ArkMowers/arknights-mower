import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerTask,MowerTaskPlan} from './mowerTaskQueue'
import {alphaPosition} from './mowerAlphaDorm'

/** A failed preview's incidental bed moves do not own another group's completed recovery. */
export function mowerRetainedRecoveryMayReturn(data:MowerSchedulingData,task:MowerTask,group:string):boolean {
 if(!task.executionFailure||task.backupShiftActive||task.arrangementStarted||task.productShiftLocked||task.dormRecoveryRestore.length)return false
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
