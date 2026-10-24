import {isTradeRunOrderOperator} from '../domain/shiftRunPolicy'
import {MowerShiftPreviewError} from './mowerNativeErrors'
import {mowerStandbyCandidates} from './mowerDormAssignment'
import {mowerRestingBindingGroups,mowerSharedReplacements} from './mowerSharedGroups'
import {mowerAssignDormGroup} from './mowerDormAssignment'
import {hasRestingMood,restingMood,type MowerOperatorState} from './mowerOperatorState'
import {projectMowerArrangements} from './mowerObservations'
import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerTask,MowerTaskPlan} from './mowerTaskQueue'

export class MowerBackupRecoveryBlocked extends MowerShiftPreviewError {
 constructor(readonly names:string[],readonly projection:MowerSchedulingData,readonly explicitSlots:ReadonlySet<string>,readonly reservedSlots:ReadonlySet<string>){super('副表下班干员尚无可用恢复床位，保留原任务')}
}

/** A concrete cover and resting-group intent distinguish interrupted recovery from an ordinary idle primary. */
const replacements=(data:MowerSchedulingData,op:MowerOperatorState)=>op.multiGroup?mowerSharedReplacements(op,mowerRestingBindingGroups(data,op)):op.replacement
export function mowerCoveredRecoveryPending(data:MowerSchedulingData,op:MowerOperatorState):boolean {
 if(!data.alpha||!op.isHigh()||op.workaholic||op.room.startsWith('dorm')||op.currentRoom&&!op.isResting()||!op.group||!data.groupIsResting(op.group)||hasRestingMood(op,data.nowMicros)&&restingMood(op,data.nowMicros)>=op.upperLimit||data.restMoodComplete(op.name))return false
 const cover=data.currentOperator(op.room,op.index)
 return !!cover&&!isTradeRunOrderOperator(cover.name)&&replacements(data,op).includes(cover.name)&&!data.excludedCandidates.has(cover.name)&&data.backupExplicitTasks.some(plan=>plan[op.room]?.[op.index]===cover.name&&!Object.entries(plan).some(([room,row])=>!room.startsWith('dorm')&&row.includes(op.name)))
}

/** Complete only concrete primary-to-cover departures; transfers and untouched group members retain their own intent. */
export function completeMowerBackupDepartureRecovery(data:MowerSchedulingData,plan:MowerTaskPlan,explicitSlots:ReadonlySet<string>=new Set(),reservedSlots:ReadonlySet<string>=new Set(),_pending:readonly MowerTask[]=[],repairIdle=false,blockOnMissingBed=false,displaced:readonly string[]=[]):MowerTaskPlan|undefined {
 if(!data.alpha)return structuredClone(plan)
 const projected=projectMowerArrangements(data,[plan]),required=new Set<string>()
 for(const slot of explicitSlots){
  const [room,indexText]=slot.split('\0'),index=Number(indexText)
  if(!room||room.startsWith('dorm'))continue
  const primary=data.operators[data.plan[room]?.[index]??''],target=plan[room]?.[index],next=primary&&projected.operators[primary.name]
  if(!primary||!primary.isHigh()||primary.workaholic||primary.room!==room||primary.index!==index||!target||isTradeRunOrderOperator(target)||!replacements(projected,next??primary).includes(target)||!next||next.currentRoom||projected.restMoodComplete(primary.name))continue
  if(primary.currentRoom===room&&primary.currentIndex===index||mowerCoveredRecoveryPending(data,primary))required.add(primary.name)
 }
 if(repairIdle)for(const op of Object.values(data.operators))if(!op.currentRoom&&mowerCoveredRecoveryPending(data,op)&&!projected.operators[op.name]!.currentRoom)required.add(op.name)
 for(const name of displaced)if(!projected.operators[name]?.currentRoom)required.add(name)
 if(!required.size)return structuredClone(plan)
 const combined=structuredClone(plan)
 const admissions=mowerAssignDormGroup(projected,[...required],new Set([...required].map(name=>projected.operators[name]!.group).filter(Boolean)),undefined,{},new Set([...reservedSlots,...explicitSlots]))
 if(admissions===undefined){if(blockOnMissingBed)throw new MowerBackupRecoveryBlocked([...required],projected,new Set(explicitSlots),new Set(reservedSlots));return undefined}
 for(const bed of admissions){const [room,index]=bed.position;(combined[room]??=Array(projected.plan[room]!.length).fill('Current'))[index]=bed.name}
 const final=projectMowerArrangements(data,[combined]),optional=mowerStandbyCandidates(projected,[...required])
 if([...required].some(name=>!optional.has(name)&&!final.operators[name]!.isResting()&&!final.restMoodComplete(name)))return undefined
 for(const slot of explicitSlots){const [room,index]=slot.split('\0');if(plan[room!]?.[Number(index)]!==combined[room!]?.[Number(index)])return undefined}
 return combined
}
