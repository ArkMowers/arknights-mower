// Mower alpha 80c97ee604375af144090656ef84b083acd6dc7f restored group members (MIT).
import {alphaPosition} from './mowerAlphaDorm'
import {mowerDormTaskReservations} from './mowerAlphaCandidates'
import {preserveMowerBackupReplacements} from './mowerBackupReplacements'
import {mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {projectMowerArrangements} from './mowerObservations'
import type {MowerOperatorState} from './mowerOperatorState'
import type {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,type MowerTask,type MowerTaskPlan} from './mowerTaskQueue'

export function mowerPrimaryJoinsRestingGroup(previous:MowerSchedulingData,next:MowerSchedulingData,owner:MowerOperatorState,protectedNames:ReadonlySet<string>):boolean {
 const old=previous.operators[owner.name]
 return (!old?.isHigh()||old.group!==owner.group)&&next.isGroupShiftAnchor(owner)&&!!owner.group&&next.groupIsResting(owner.group)&&
  (!owner.currentRoom||owner.isResting())&&!protectedNames.has(owner.name)
}

/** Match covers and admit missing members in a private projection before changing the final arrangement. */
export function preserveMowerBackupRestingJoins(data:MowerSchedulingData,plan:MowerTaskPlan,positions:[string,number][],previousDorms:MowerDormState[],joining:ReadonlySet<string>,tasks:MowerTask[],protectedNames:ReadonlySet<string>):boolean {
 const reserved=mowerDormTaskReservations(data,tasks.filter(task=>task.type!==T.SHIFT_ON||task.productShiftLocked))
 const explicitNames=new Set(Object.values(plan).flat().filter(name=>!['','Current','Free'].includes(name)))
 for(const [room,row] of Object.entries(plan))if(room.startsWith('dorm'))row.forEach((name,index)=>{if(name!=='Current')reserved.slots.add(alphaPosition(room,index))})
 const projection=projectMowerArrangements(data,[]),pending=structuredClone(plan)
 projection.reservedProductReplacements=new Set([...projection.reservedProductReplacements,...reserved.names,...protectedNames])
 projection.reservedProductBeds=new Map(projection.reservedProductBeds)
 if(!preserveMowerBackupReplacements(projection,pending,positions,previousDorms))return false
 const simulation=projectMowerArrangements(projection,[pending])
 const missing=[...joining].sort().filter(name=>{
  const op=simulation.operators[name]!
  return !!op.group&&simulation.groupIsResting(op.group)&&!explicitNames.has(name)&&!simulation.getDormByName(name)&&
   !(!op.currentRoom&&op.timeStampMicros!==undefined&&op.mood>=op.upperLimit)
 })
 if(missing.some(name=>reserved.names.has(name)||reserved.slots.has(alphaPosition(simulation.operators[name]!.room,simulation.operators[name]!.index))))return false
 if(missing.length){
  const assigned=Object.values(pending).flat().filter(name=>!['','Current','Free'].includes(name))
  if(!mowerGetRestingPlan(simulation,missing,assigned,pending,{isMasteryBusy:name=>protectedNames.has(name)||simulation.busyRestingNames.has(name),reservedSlots:reserved.slots}))return false
  for(const bed of simulation.allDorms())if(missing.includes(bed.name))(pending[bed.position[0]]??=Array(data.plan[bed.position[0]]!.length).fill('Current'))[bed.position[1]]=bed.name
 }
 for(const room of Object.keys(plan))delete plan[room]
 Object.assign(plan,pending)
 return true
}
