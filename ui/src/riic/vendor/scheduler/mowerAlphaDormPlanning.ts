// Unified pre-dispatch empty-bed entry, Mower b2d9ac8 (MIT).
import type {MowerSchedulingData} from './mowerSchedulingData'
import {mowerDormTaskReservations,planMowerAlphaDormFill} from './mowerAlphaCandidates'
import {alphaPosition} from './mowerAlphaDorm'
import {planMowerOrdinary,type MowerRestingOptions} from './mowerOrdinaryPlanning'
import {MOWER_TASK_TYPES as T,type MowerTaskQueue} from './mowerTaskQueue'
export function fillMowerAlphaEmptyDorms(data:MowerSchedulingData,queue:MowerTaskQueue,options:MowerRestingOptions={},primaryPlanned=false):boolean {
 const vacant=(reserved=new Set<string>())=>data.dorms.some(b=>!b.name&&!reserved.has(alphaPosition(...b.position))&&data.effectiveFreeSlot(b)&&!data.currentOperator(...b.position))
 const fills=queue.tasks.filter(t=>t.type===T.FILL_DORM&&t.timeMicros<=data.nowMicros&&!t.arrangementRetryRoom&&!t.dormRecoveryRestore.length&&!t.productShiftLocked&&!t.backupShiftActive&&!t.strictMoodLimit&&JSON.stringify(Object.keys(t.plan).sort())===JSON.stringify(Object.keys(t.dormFillPlan).sort()))
 if(!fills.length&&!vacant())return false
 if(!primaryPlanned){
  if(queue.tasks.some(t=>[T.SHIFT_OFF,T.EXHAUST_OFF].includes(t.type)||t.type===T.FILL_DORM&&!fills.includes(t)||t.timeMicros<=data.nowMicros&&[T.SHIFT_ON,T.FIAMMETTA,T.SELF_CORRECTION,T.RE_ORDER].includes(t.type)||t.type===T.NOT_SPECIFIC&&Object.keys(t.plan).some(r=>r.startsWith('dorm'))))return false
  queue.tasks=queue.tasks.filter(t=>!fills.includes(t))
  if(!fills.length&&!vacant(mowerDormTaskReservations(data,queue.tasks).slots))return false
  let superseded=false
  try {
   planMowerOrdinary(data,queue,options)
   if(queue.tasks.some(t=>t.timeMicros<=data.nowMicros&&([T.SHIFT_ON,T.SHIFT_OFF].includes(t.type)||Object.keys(t.plan).some(r=>r.startsWith('dorm'))))){superseded=true;return false}
  }finally{if(!superseded)queue.tasks.push(...fills.filter(t=>!queue.tasks.includes(t)))}
  if(fills.length)return false
 }
 return !!planMowerAlphaDormFill(data,queue,true,options.priorityScheduling)
}
