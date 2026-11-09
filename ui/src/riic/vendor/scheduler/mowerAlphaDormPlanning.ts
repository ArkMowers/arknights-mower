// Unified pre-dispatch empty-bed entry, Mower b2d9ac8 (MIT).
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerDormTaskReservations,planMowerAlphaDormFill} from './mowerAlphaCandidates'
import {alphaPosition} from './mowerAlphaDorm'
import {planMowerOrdinary,type MowerRestingOptions} from './mowerOrdinaryPlanning'
import {MOWER_TASK_TYPES as T,MowerTaskQueue,type MowerTask} from './mowerTaskQueue'
import {projectMowerArrangements} from './mowerObservations'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'
import {protectMowerAlphaTasks} from './mowerAlphaTaskProtection'
export function fillMowerAlphaEmptyDorms(data:MowerSchedulingData,queue:MowerTaskQueue,options:MowerRestingOptions={},primaryPlanned=false):boolean {
 const vacant=(reserved=new Set<string>())=>data.dorms.some(b=>!b.name&&!reserved.has(alphaPosition(...b.position))&&data.effectiveFreeSlot(b)&&!data.currentOperator(...b.position))
 const fills=queue.tasks.filter(t=>!t.retainsExecution&&t.type===T.FILL_DORM&&t.timeMicros<=data.nowMicros&&!t.arrangementRetryRoom&&!t.dormRecoveryRestore.length&&!t.productShiftLocked&&!t.backupShiftActive&&!t.strictMoodLimit&&JSON.stringify(Object.keys(t.plan).sort())===JSON.stringify(Object.keys(t.dormFillPlan).sort()))
 if(!fills.length&&!vacant())return false
 if(!primaryPlanned){
  if(queue.tasks.some(t=>!t.executionFailure&&([T.SHIFT_OFF,T.EXHAUST_OFF].includes(t.type)||t.type===T.FILL_DORM&&!fills.includes(t)||t.timeMicros<=data.nowMicros&&[T.SHIFT_ON,T.FIAMMETTA,T.SELF_CORRECTION,T.RE_ORDER].includes(t.type)||t.type===T.NOT_SPECIFIC&&Object.keys(t.plan).some(r=>r.startsWith('dorm')))))return false
  queue.tasks=queue.tasks.filter(t=>!fills.includes(t))
  if(!fills.length&&!vacant(mowerDormTaskReservations(data,queue.tasks).slots))return false
  let superseded=false
  try {
   const reserved=mowerDormTaskReservations(data,queue.tasks)
   planMowerOrdinary(data,queue,{...options,
    reservedNames:new Set([...options.reservedNames??[],...reserved.names]),
    reservedSlots:new Set([...options.reservedSlots??[],...reserved.slots])})
   if(queue.tasks.some(t=>!t.executionFailure&&t.timeMicros<=data.nowMicros&&([T.SHIFT_ON,T.SHIFT_OFF].includes(t.type)||Object.keys(t.plan).some(r=>r.startsWith('dorm'))))){superseded=true;return false}
  }finally{if(!superseded)queue.tasks.push(...fills.filter(t=>!queue.tasks.includes(t)))}
  if(fills.length)return false
 }
 return !!planMowerAlphaDormFill(data,queue,true,options.priorityScheduling)
}

/** Re-admit an unstarted ordinary fill against reservations created while it waited. */
export function prepareMowerAlphaDormFill(data:MowerSchedulingData,task:MowerTask,pending:MowerTask[],options:MowerTaskSchedulingOptions={},waiting:MowerTask[]=[]):boolean {
 if(!data.alpha||![T.NOT_SPECIFIC,T.FILL_DORM].includes(task.type)||!Object.keys(task.dormFillPlan).length||task.retainsExecution||task.arrangementStarted||task.arrangementRetryRoom||task.dormRecoveryRestore.length||task.productShiftLocked||task.backupShiftActive||task.backupExplicitSlots.size||task.strictMoodLimit)return false
 const projected=projectMowerArrangements(data,[]),planning=new MowerTaskQueue()
 planning.tasks=[...new Set(pending)].filter(other=>other!==task)
 const reservedNames=new Set<string>(),reservedSlots=new Set<string>()
 for(const other of waiting)if(other!==task)for(const name of Object.values(other.plan).flat()){
  const op=projected.operators[name];if(!op)continue
  reservedNames.add(name)
  if(op.currentRoom)reservedSlots.add(alphaPosition(op.currentRoom,op.currentIndex))
 }
 const updated=planMowerAlphaDormFill(projected,planning,false,options,{reservedNames,reservedSlots})
 task.plan=updated?.plan??{}
 if(updated)task.type=updated.type
 task.dormFillPlan=updated?.dormFillPlan??{}
 task.dormMoodResidents=updated?.dormMoodResidents??[]
 task.simpleDormFill=updated?.simpleDormFill??false
 for(const [room,row] of Object.entries(task.plan))if(room.startsWith('dorm'))for(const name of row){const op=data.operators[name];if(op)op.dormMoodFallback=projected.operators[name]!.dormMoodFallback?room:''}
 return !!updated
}

/** Native priority protection budgets retained copies without merging unrelated tasks. */
export function protectMowerAlphaDormFillDispatch(queue:MowerTaskQueue,now:number,options:MowerTaskSchedulingOptions={}):void {
 const waiting=queue.tasks.filter(task=>task.executionFailure),originals=new Map<MowerTask,MowerTask>()
 const active=queue.tasks.filter(task=>!task.executionFailure).map(task=>{
  if(!task.retainsExecution)return task
  const projected=Object.assign(Object.create(Object.getPrototypeOf(task)) as MowerTask,task,{plan:structuredClone(task.plan)})
  originals.set(projected,task);return projected
 })
 protectMowerAlphaTasks(active,now,options)
 queue.tasks=[...active.map(task=>originals.get(task)??task),...waiting]
}
