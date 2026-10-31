import {alphaPosition} from './mowerAlphaDorm'
import {mowerDormTaskReservations} from './mowerAlphaCandidates'
import {mowerAssignDormGroup} from './mowerDormAssignment'
import {MowerShiftPreviewError} from './mowerNativeErrors'
import {projectMowerArrangements} from './mowerObservations'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MowerTask,MOWER_TASK_TYPES as T,type MowerTaskPlan} from './mowerTaskQueue'

export class MowerBackupRetentionBlocked extends MowerShiftPreviewError {
 constructor(readonly names:string[],readonly rooms:string[]){super('副表宿舍保留安排尚无可用床位，保留原任务')}
}

/** Only observed occupancy, relevant reservations and the effective selection release a failed retention transition. */
export function mowerBackupRetentionFingerprint(data:MowerSchedulingData,pending:readonly MowerTask[],names:readonly string[],selection:unknown):string {
 const reserved=mowerDormTaskReservations(data,[...pending].filter(task=>task.type!==T.SHIFT_ON||task.retainsExecution||task.backupShiftActive||task.productShiftLocked||task.dormRecoveryRestore.length))
 return JSON.stringify([selection,data.planConditions,data.backupGroup,data.freeRoomExclusions,
  Object.values(data.operators).filter(op=>names.includes(op.name)||op.isResting()).map(op=>[op.name,op.room,op.index,op.currentRoom,op.currentIndex,data.freeRoomExcluded(op.name)]),
  data.dorms.map(bed=>[bed.position,bed.name,data.effectiveFreeSlot(bed),data.plan[bed.position[0]]?.[bed.position[1]]]),[...reserved.names].sort(),[...reserved.slots].sort(),[...data.reservedProductBeds],
 ])
}

/** Policy-only admissions lose their authority when the final effective policy no longer retains the actor. */
export function mowerBackupRetentionTaskPlan(next:MowerSchedulingData,task:MowerTask,source:MowerTaskPlan=task.plan,allowRetained=false):MowerTaskPlan {
 const plan=structuredClone(source)
 for(const [room,row] of Object.entries(plan))row.forEach((name,index)=>{
  const expected=task.backupRetentionEmptySlots[alphaPosition(room,index)]
  if(name===''&&expected&&(next.freeRoomExcluded(expected)||next.operators[expected]?.room||next.currentOperator(room,index)?.name!==expected))row[index]='Current'
 })
 if(task.arrangementStarted||task.backupShiftActive||task.retainsExecution&&(!allowRetained||task.executionFailure))return plan
 for(const [room,row] of Object.entries(plan))if(room.startsWith('dorm'))row.forEach((name,index)=>{
  const op=next.operators[name]
  if(task.backupRetentionAdmissions.includes(name)&&(!next.freeRoomExcluded(name)||op?.room||op?.currentRoom&&!op.isResting())&&!task.backupExplicitSlots.has(alphaPosition(room,index)))row[index]='Current'
 })
 return Object.fromEntries(Object.entries(plan).filter(([,row])=>row.some(name=>name!=='Current')))
}
export function mowerBackupRetentionPending(next:MowerSchedulingData,pending:readonly MowerTask[]):MowerTask[] {
 return pending.map(task=>Object.assign(new MowerTask(),task,{plan:mowerBackupRetentionTaskPlan(next,task),backupShiftIntent:task.backupShiftIntent&&mowerBackupRetentionTaskPlan(next,task,task.backupShiftIntent),dormFillPlan:mowerBackupRetentionTaskPlan(next,task,task.dormFillPlan)}))
}
export function cancelMowerBackupRetentionAdmissions(next:MowerSchedulingData,pending:MowerTask[]):Set<MowerTask> {
 const cancelled=new Set<MowerTask>()
 for(const task of pending){
  if(task.retainsExecution||task.arrangementStarted||task.backupShiftActive)continue
  const hadRetentionActions=task.backupRetentionAdmissions.length>0||Object.keys(task.backupRetentionEmptySlots).length>0
  task.plan=mowerBackupRetentionTaskPlan(next,task)
  if(task.backupShiftIntent)task.backupShiftIntent=mowerBackupRetentionTaskPlan(next,task,task.backupShiftIntent)
  task.dormFillPlan=mowerBackupRetentionTaskPlan(next,task,task.dormFillPlan)
  task.backupRetentionAdmissions=task.backupRetentionAdmissions.filter(name=>next.freeRoomExcluded(name)&&Object.values(task.plan).some(row=>row.includes(name)))
  if(hadRetentionActions&&!Object.keys(task.plan).length)cancelled.add(task)
 }
 return cancelled
}
export function mowerBackupRetentionReleasedNames(previous:MowerSchedulingData,next:MowerSchedulingData,explicitNames:ReadonlySet<string>=new Set()):string[] {
 return previous.freeRoomExclusions.filter(name=>previous.freeRoomExcluded(name)&&!next.freeRoomExcluded(name)&&next.operators[name]&&!next.operators[name]!.room&&!explicitNames.has(name))
}
export function recordMowerBackupRetention(previous:MowerSchedulingData,next:MowerSchedulingData,task:MowerTask,explicitNames:ReadonlySet<string>=new Set()):void {
 task.backupRetentionReleasedNames=[...new Set([...task.backupRetentionReleasedNames,...mowerBackupRetentionReleasedNames(previous,next,explicitNames)])].filter(name=>!next.freeRoomExcluded(name)&&!next.operators[name]?.room&&!explicitNames.has(name))
 for(const [room,row] of Object.entries(task.plan))if(room.startsWith('dorm'))row.forEach((name,index)=>{
  const old=previous.currentOperator(room,index)?.name
  if(name===''&&old&&task.backupRetentionReleasedNames.includes(old))task.backupRetentionEmptySlots[alphaPosition(room,index)]=old
 })
 const named=new Set(Object.entries(task.plan).flatMap(([room,row])=>room.startsWith('dorm')?row:[]))
 task.backupRetentionAdmissions=[...new Set([...task.backupRetentionAdmissions,...next.freeRoomExclusions.filter(name=>next.freeRoomExcluded(name)&&!next.operators[name]?.room&&!previous.operators[name]?.currentRoom&&named.has(name)&&!explicitNames.has(name))])]
}

/** Reconcile final retention policy in a copy; existing residents never yield beds to policy-only admissions. */
export function reconcileMowerBackupRetention(previous:MowerSchedulingData,next:MowerSchedulingData,plan:MowerTaskPlan,pending:readonly MowerTask[]=[],explicitNames:ReadonlySet<string>=new Set()):MowerTaskPlan {
 const result=structuredClone(plan),projected=projectMowerArrangements(next,[result])
 const reserved=mowerDormTaskReservations(projected,mowerBackupRetentionPending(next,pending).filter(task=>task.type!==T.SHIFT_ON||task.retainsExecution||task.backupShiftActive||task.productShiftLocked||task.dormRecoveryRestore.length))
 const rooms=[...new Set(projected.dorms.map(bed=>bed.position[0]))]
 const fail=(names:string[]):never=>{throw new MowerBackupRetentionBlocked(names,rooms)}
 for(const name of mowerBackupRetentionReleasedNames(previous,next,explicitNames)){
  const op=projected.operators[name]
  if(!op||!op.isResting())continue
  const bed=projected.dorms.find(bed=>bed.position[0]===op.currentRoom&&bed.position[1]===op.currentIndex&&projected.effectiveFreeSlot(bed))
  if(!bed)continue
  const position=alphaPosition(...bed.position)
  if(reserved.names.has(name)||reserved.slots.has(position)||projected.reservedProductBeds.has(position))fail([name])
  ;(result[op.currentRoom]??=Array(projected.plan[op.currentRoom]!.length).fill('Current'))[op.currentIndex]=''
 }
 const released=projectMowerArrangements(next,[result])
 const required=next.freeRoomExclusions.filter(name=>{
  const op=released.operators[name]
  return next.freeRoomExcluded(name)&&!!op&&!op.room&&!op.currentRoom&&!explicitNames.has(name)
 })
 if(!required.length)return result
 if(required.some(name=>reserved.names.has(name)))fail(required)
 const locked=new Set([...reserved.slots,...released.reservedProductBeds.keys()])
 for(const bed of released.dorms)if(bed.name||released.currentOperator(...bed.position))locked.add(alphaPosition(...bed.position))
 for(const [room,row] of Object.entries(plan))if(room.startsWith('dorm'))row.forEach((name,index)=>{if(name!=='Current'&&name!=='Free')locked.add(alphaPosition(room,index))})
 const admissions=mowerAssignDormGroup(released,required,undefined,undefined,{},locked)
 if(!admissions||admissions.length!==required.length)fail(required)
 for(const bed of admissions){const [room,index]=bed.position;(result[room]??=Array(released.plan[room]!.length).fill('Current'))[index]=bed.name}
 return result
}
