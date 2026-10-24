import {mowerDormCandidateMood} from './mowerSchedulingMood'
import {mowerCoveredRecoveryPending} from './mowerBackupDepartureRecovery'
import {mowerAssignDormGroup} from './mowerDormAssignment'
import {projectMowerArrangements} from './mowerObservations'
import {mowerGroupRecoveryWorkers,mowerRecoveryMoodComplete} from './mowerGroupRecovery'
import {mowerDormTaskReservations} from './mowerAlphaCandidates'
import {normalizeMowerSharedArrangement,mowerSameGroupPrimaryReplacement,mowerArrangementGroupTransitions} from './mowerSharedGroups'
import {admitMowerDerivedTasks} from './mowerTaskDerivation'
import {mowerActiveUrgentRecoveryNames} from './mowerUrgentRecovery'
// Port of default agent_get_mood correction and prefer_resting_replacements.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {mowerReplacementCandidates,type MowerOperatorState} from './mowerOperatorState'
import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'
import {alphaCorrectGroupDorms,alphaPosition} from './mowerAlphaDorm'
import {MowerTask,MOWER_TASK_TYPES as T,fromMowerMicros,toMowerMicros,type MowerTaskPlan,type MowerTaskQueue} from './mowerTaskQueue'
const placeholders=new Set(['','Current','Free'])
const requested=(plan:MowerTaskPlan,room:string,index:number)=>plan[room]?.[index]??'Current'
/** Port of resting_correction.off_duty_full_recovery_members, Mower b1a7c951 (MIT). */
export function mowerOffDutyFullRecoveryMembers(data:MowerSchedulingData):Set<string> {
 return new Set(Object.values(data.operators).filter(op=>{
  if(!data.alpha||!op.isHigh()||!op.restInFull||op.workaholic||op.room.startsWith('dorm')||op.currentRoom&&!op.isResting()||data.restMoodComplete(op.name))return false
  const mood=mowerDormCandidateMood(data,op.name)
  return mood!==undefined&&mood<op.upperLimit
 }).map(op=>op.name))
}

/** Complete departed recovery in an isolated projection; never commit a partial bed assignment. */
function completeMowerDepartedRecovery(data:MowerSchedulingData,plan:MowerTaskPlan,names:ReadonlySet<string>,pending:readonly MowerTask[],reservedSlots:ReadonlySet<string>=new Set()):boolean {
 const projected=projectMowerArrangements(data,[plan])
 const missing=[...names].filter(name=>{
  const op=projected.operators[name]!
  if(op.workaholic||op.room.startsWith('dorm')||op.currentRoom||projected.restMoodComplete(name))return false
  const mood=mowerDormCandidateMood(projected,name)
  return mood===undefined||mood<op.upperLimit
 })
 if(!missing.length)return true
 const reserved=mowerDormTaskReservations(projected,[...pending])
 if(missing.some(name=>reserved.names.has(name)))return false
 reservedSlots.forEach(slot=>reserved.slots.add(slot))
 for(const [room,row] of Object.entries(plan))if(room.startsWith('dorm'))row.forEach((name,index)=>{if(name!=='Current')reserved.slots.add(alphaPosition(room,index))})
 const beds=mowerAssignDormGroup(projected,missing,new Set(missing.map(name=>projected.operators[name]!.group)),undefined,plan,reserved.slots)
 if(!beds)return false
 for(const bed of beds){const [room,index]=bed.position;(plan[room]??=Array(projected.plan[room]!.length).fill('Current'))[index]=bed.name}
 return true
}
export function mowerNotValid(data:MowerSchedulingData,op:MowerOperatorState):boolean {
 if(!op.isHigh())return false
 if(data.alpha&&op.isResting()){const mood=mowerDormCandidateMood(data,op.name);if(mood!==undefined&&mood<op.upperLimit)return false}
 if(mowerCoveredRecoveryPending(data,op))return false
 if(op.workaholic)return op.currentRoom!==op.room||op.currentIndex!==op.index
 if(!op.room.startsWith('dorm')&&op.isResting())return op.mood===-1||op.mood===24
 return op.needToRefresh(data.nowMicros,2.5)||op.currentRoom!==op.room||op.currentIndex!==op.index
}
export function mowerIsDormReplacement(data:MowerSchedulingData,name:string):boolean {
 const op=data.operators[name]!;if(!op.currentRoom.startsWith('dorm'))return false
 if(data.alpha)return data.dormReplacementForSlot(name,op.currentRoom,op.currentIndex)
 const residentName=data.plan[op.currentRoom]?.[op.currentIndex],resident=residentName?data.operators[residentName]:undefined
 return !!resident?.group&&resident.nativeName!=='菲亚梅塔'&&resident.replacement.includes(name)
}
export function preferMowerRestingReplacements(data:MowerSchedulingData,plan:MowerTaskPlan):void {
 if(!Object.keys(plan).length)return
 const ends=new Map(data.allDorms().filter(b=>b.name).map(b=>[b.name,b.timeMicros])),resting=new Set<string>(),groups=new Set<string>()
 for(const op of Object.values(data.operators)){
  if(!op.isHigh()||op.workaholic||op.room.startsWith('dorm')||!op.isResting()&&!mowerCoveredRecoveryPending(data,op))continue
  const end=ends.get(op.name),mood=data.alpha?mowerDormCandidateMood(data,op.name):op.mood,unfinished=end!==undefined?end>data.nowMicros:mood!==undefined&&mood>=0&&mood<op.upperLimit
  if(unfinished){resting.add(op.name);if(op.group&&(!data.alpha||data.isGroupShiftAnchor(op)))groups.add(op.group)}
 }
 for(const group of groups){
  const members=(data.alpha?data.shiftGroupMembers(group):data.group(group)).map(n=>data.operators[n]!).filter(op=>!op.room.startsWith('dorm')&&!op.workaholic)
  if(members.some(op=>(!data.alpha||data.isGroupShiftAnchor(op))&&!op.isResting()&&!(!op.currentRoom&&(data.canStandby(op)||data.alpha&&data.restMoodComplete(op.name)||op.timeStampMicros!==undefined&&op.mood>=op.upperLimit))))data.group(group).forEach(n=>{if(!mowerCoveredRecoveryPending(data,data.operators[n]!))resting.delete(n)})
  else members.forEach(op=>resting.add(op.name))
 }
 const protectedRecovery=data.alpha?mowerActiveUrgentRecoveryNames(data):new Set<string>()
 mowerOffDutyFullRecoveryMembers(data).forEach(name=>protectedRecovery.add(name))
 if(data.alpha)for(const group of new Set(Object.values(data.operators).flatMap(op=>op.multiGroup?op.groupBindings.map(binding=>binding.group):[op.group]).filter(Boolean))){
  const workers=mowerGroupRecoveryWorkers(data,group)
  if(workers.some(op=>op.isResting())&&workers.some(op=>op.restInFull&&(op.moodIsPrediction||!mowerRecoveryMoodComplete(data,op)&&!(!op.currentRoom&&data.restMoodComplete(op.name)))))for(const member of data.shiftGroupMembers(group)){
   const op=data.operators[member]!
   if(!op.room.startsWith('dorm')&&!op.workaholic)protectedRecovery.add(member)
  }
 }
 for(const name of [...protectedRecovery]){
  const op=data.operators[name]!
  if(op.group&&data.isGroupShiftAnchor(op))for(const member of data.shiftGroupMembers(op.group))if(!data.operators[member]!.room.startsWith('dorm')&&!data.operators[member]!.workaholic)protectedRecovery.add(member)
 }
 protectedRecovery.forEach(name=>resting.add(name))
 if(!resting.size)return
 const original=structuredClone(plan),reserved=new Set(Object.values(plan).flat().filter(n=>!placeholders.has(n)&&!resting.has(n)))
 for(const op of Object.values(data.operators))if(op.currentRoom&&!op.isResting()){
  const target=requested(original,op.currentRoom,op.currentIndex)
  if(target==='Current'||target===op.name||resting.has(target)&&data.operators[target]!.replacement.includes(op.name))reserved.add(op.name)
 }
 const recall=new Set<string>()
 for(const [room,names] of Object.entries(plan)){
  if(room.startsWith('dorm'))continue
  for(const [index,name] of names.entries()){
   if(!resting.has(name))continue
   const op=data.operators[name]!;if(room!==op.room||index!==op.index)continue
   const actual=data.currentRoom(room,true)![index]
   if(actual===name||actual&&op.replacement.includes(actual)&&!data.excludedCandidates.has(actual)){names[index]='Current';continue}
   const candidate=mowerReplacementCandidates(op,data.operators,data.policy,data.nowMicros).find(n=>{
    const cover=data.operators[n];if(!cover||cover.isHigh()&&(!data.alpha||!mowerSameGroupPrimaryReplacement(data,op,n))||reserved.has(n)||resting.has(n)||data.excludedCandidates.has(n)||mowerIsDormReplacement(data,n)||data.busyRestingNames.has(n)||data.alpha&&data.replacementExhausted(n,op))return false
    if(!cover.currentRoom||cover.isResting()||cover.currentRoom===room)return true
    const replacement=requested(original,cover.currentRoom,cover.currentIndex)
    return !placeholders.has(replacement)&&!resting.has(replacement)&&replacement!==cover.name
   })
   if(candidate){names[index]=candidate;reserved.add(candidate)}else if(protectedRecovery.has(name))names[index]='Current';else if(op.group&&(!data.alpha||data.isGroupShiftAnchor(op)))recall.add(op.group);else if(data.alpha&&op.exhaustRequire&&op.restInFull)names[index]='Current'
  }
 }
 for(const group of recall)for(const name of data.group(group)){const op=data.operators[name]!;if(!op.room.startsWith('dorm'))(plan[op.room]??=Array(data.plan[op.room]!.length).fill('Current'))[op.index]=name}
 for(const [room,names] of Object.entries(plan)){
  names.forEach((name,index)=>{if(!placeholders.has(name)&&data.currentRoom(room,true)![index]===name&&!(data.alpha&&data.operators[name]?.needToRefresh(data.nowMicros,2.5)))names[index]='Current'})
  if(names.every(n=>n==='Current'))delete plan[room]
 }
}
export function mowerCorrectionPlan(data:MowerSchedulingData,skipDorm=false,explicitSlots:ReadonlySet<string>=new Set(),pending:readonly MowerTask[]=[],currentTask?:MowerTask):MowerTaskPlan {
 const plan:MowerTaskPlan={}
 const admitted=()=>admitMowerDerivedTasks(data,pending.filter(task=>task!==currentTask),[new MowerTask({type:T.SELF_CORRECTION,plan})])[0]?.plan??{}
 const set=(room:string,index:number,name:string)=>{(plan[room]??=Array(data.plan[room]!.length).fill('Current'))[index]=name}
 for(const [room,names] of Object.entries(data.plan))for(const [index,name] of names.entries()){
  if(data.waitingRecoveryNames.has(name)||data.alpha&&room.startsWith('dorm')&&name==='Free')continue
  const actual=data.currentRoom(room,true)![index],op=data.operators[name]
  if(!actual){set(room,index,name);continue}
  if(name==='Free')continue
  if(actual!==name&&!(op?.replacement.includes(actual)&&!data.excludedCandidates.has(actual)))set(room,index,name)
 }
 const miss=Object.values(data.operators).filter(op=>!data.waitingRecoveryNames.has(op.name)&&mowerNotValid(data,op)&&!(data.alpha&&op.multiGroup)&&!(op.group&&op.room.startsWith('dorm'))&&!data.isStandby(op.name)&&!data.busyRestingNames.has(op.name))
 for(const op of miss){
  const peers=op.group?data.group(op.group).map(n=>data.operators[n]!):[]
  if(op.group&&(data.alpha?data.groupIsResting(op.group):peers.some(peer=>!peer.room.startsWith('dorm')&&!mowerNotValid(data,peer)&&peer.isResting()))&&(op.workaholic||data.alpha&&data.restMoodComplete(op.name)||op.timeStampMicros!==undefined&&(op.currentMood(data.nowMicros)>=op.upperLimit||op.mood>=op.upperLimit)))continue
  for(const peer of peers)if((!data.alpha||op.currentRoom!==op.room||op.currentIndex!==op.index)&&!data.waitingRecoveryNames.has(peer.name)&&!mowerCoveredRecoveryPending(data,peer)&&(!data.alpha||data.isGroupShiftAnchor(op))&&!peer.room.startsWith('dorm')&&(peer.currentRoom!==peer.room||peer.currentIndex!==peer.index))set(peer.room,peer.index,peer.name)
  set(op.room,op.index,op.name)
  if(op.currentIndex!==-1&&op.currentIndex!==op.index||op.currentRoom&&op.currentRoom!==op.room)set(op.currentRoom,op.currentIndex,data.plan[op.currentRoom]![op.currentIndex]!)
 }
 const groups=new Set(Object.values(data.operators).map(op=>op.group).filter(Boolean))
 for(const group of groups){
  if(data.group(group).some(name=>mowerCoveredRecoveryPending(data,data.operators[name]!)))continue
  const peers=data.group(group).map(n=>data.operators[n]!).filter(op=>!data.waitingRecoveryNames.has(op.name)&&!mowerCoveredRecoveryPending(data,op)&&!op.room.startsWith('dorm')&&(!data.alpha||!op.multiGroup&&!op.workaholic&&!data.canStandby(op)))
  if(peers.some(op=>op.currentRoom&&!op.isResting())&&peers.some(op=>!op.currentRoom||op.isResting()))for(const op of peers)if(!op.currentRoom||op.isResting())set(op.room,op.index,op.name)
 }
 for(const [room,names] of Object.entries(plan))if(skipDorm&&room.startsWith('dorm')&&names.every(n=>n==='Free'||n==='Current'))delete plan[room]
 for(const op of Object.values(data.operators))if(data.busyRestingNames.has(op.name)&&op.room==='train')delete plan.train
 preferMowerRestingReplacements(data,plan)
 if(data.alpha){
  alphaCorrectGroupDorms(data,plan)
  for(const [room,names] of Object.entries(plan))if(room.startsWith('dorm')){
   names.forEach((name,index)=>{if(data.restMoodComplete(name)&&data.currentOperator(room,index)?.name!==name)names[index]='Current'})
   if(names.every(n=>n==='Current'))delete plan[room]
  }
  // Explicit backup positions retain physical occupancy through correction.
  // Source: 3de2b2ac agent_get_mood and _merge_shift_transition (MIT).
  const explicit:{room:string;index:number;name:string}[]=[],destinations=new Map<string,string>()
  for(const [room,names] of Object.entries(data.plan))names.forEach((_,index)=>{
   if(!explicitSlots.has(alphaPosition(room,index)))return
   const name=data.currentOperator(room,index)?.name??'Free'
   explicit.push({room,index,name});if(!placeholders.has(name))destinations.set(name,alphaPosition(room,index))
  })
  for(const [room,names] of Object.entries(plan))names.forEach((name,index)=>{
   const destination=destinations.get(name)
   if(destination!==undefined&&destination!==alphaPosition(room,index))names[index]='Current'
  })
  for(const {room,index,name} of explicit)set(room,index,name)
  // Same-slot rereads remain in the correction but do not change group duty.
  const moving=Object.fromEntries(Object.entries(plan).map(([room,row])=>[room,row.map((name,index)=>data.currentOperator(room,index)?.name===name?'Current':name)]))
  if(!normalizeMowerSharedArrangement(data,plan,mowerArrangementGroupTransitions(data,moving),explicitSlots))return {}
  for(const [room,names] of Object.entries(plan))if(names.every(n=>n==='Current'))delete plan[room]
  const displaced=Object.values(data.operators).filter(op=>op.isHigh()&&op.isResting()&&!op.room.startsWith('dorm')&&!op.workaholic&&!data.busyRestingNames.has(op.name)&&!data.getDormByName(op.name)&&mowerDormCandidateMood(data,op.name)!==undefined&&mowerDormCandidateMood(data,op.name)!<op.upperLimit&&![undefined,'Current',op.name].includes(plan[op.currentRoom]?.[op.currentIndex]))
  const departed=new Set([...mowerOffDutyFullRecoveryMembers(data),...Object.values(data.operators).filter(op=>mowerCoveredRecoveryPending(data,op)).map(op=>op.name),...displaced.map(op=>op.name)].filter(name=>!data.busyRestingNames.has(name)))
  for(const [room,row] of Object.entries(plan))if(!room.startsWith('dorm'))row.forEach((name,index)=>{if(departed.has(name))row[index]='Current'})
  const completed=structuredClone(plan)
  if(completeMowerDepartedRecovery(data,completed,departed,pending.filter(task=>task!==currentTask),explicitSlots)){for(const room of Object.keys(plan))delete plan[room];Object.assign(plan,completed)}
  else for(const op of displaced)set(op.currentRoom,op.currentIndex,'Current')
  return admitted()
 }
 for(const group of groups){
  const members=data.group(group),residents=members.map(n=>data.operators[n]!).filter(op=>op.room.startsWith('dorm'))
  const recalling=members.some(n=>{const op=data.operators[n]!;return !op.room.startsWith('dorm')&&!op.workaholic&&requested(plan,op.room,op.index)===n})
  const resting=data.groupIsResting(group)&&!recalling
  const changes:{room:string;index:number;name:string}[]=[]
  for(const op of residents){
   const actual=data.currentOperator(op.room,op.index);let desired=op.name
   if(resting){
    const candidates=mowerReplacementCandidates(op,data.operators,data.policy,data.nowMicros)
    if(actual&&candidates.includes(actual.name)){candidates.splice(candidates.indexOf(actual.name),1);candidates.unshift(actual.name)}
    const reserved=new Set([...Object.entries(plan).flatMap(([room,names])=>names.filter((_,index)=>room!==op.room||index!==op.index)),...changes.map(c=>c.name)])
    desired=candidates.find(n=>{const cover=data.operators[n]!;return !data.excludedCandidates.has(n)&&!reserved.has(n)&&!data.busyRestingNames.has(n)&&!cover.isHigh()&&(actual?.name===n||!mowerIsDormReplacement(data,n)&&(!cover.currentRoom||cover.isResting()))})??op.name
   }
   changes.push({room:op.room,index:op.index,name:desired})
  }
  for(const {room,index,name} of changes){const actual=data.currentOperator(room,index);if(!plan[room]&&actual?.name===name)continue;set(room,index,actual?.name===name?'Current':name)}
 }
 for(const [room,names] of Object.entries(plan))if(names.every(n=>n==='Current'))delete plan[room]
 return admitted()
}
export function planMowerCorrection(data:MowerSchedulingData,queue:MowerTaskQueue,force=false,currentTask?:MowerTask,skipDorm=false,onSkip?:()=>void,options:MowerTaskSchedulingOptions={}):MowerTask|undefined {
 if(queue.tasks.some(task=>task.backupShiftActive))return undefined
 const plan=mowerCorrectionPlan(data,skipDorm,new Set(),queue.tasks,currentTask);if(!Object.keys(plan).length)return undefined
 const next=queue.find({ignoreRunOrders:(options.adjustForRunOrders??data.adjustForRunOrders)===false}),off=queue.find({type:T.SHIFT_OFF})
 if(!force&&next&&Object.keys(plan).length*toMowerMicros(45/3600)>next.timeMicros-data.nowMicros||off&&!(force&&off===currentTask)){onSkip?.();return undefined}
 const duplicate=queue.tasks.find(task=>task!==currentTask&&task.type===T.SELF_CORRECTION&&Object.keys(task.plan).length===Object.keys(plan).length&&Object.entries(plan).every(([room,row])=>task.plan[room]?.length===row.length&&row.every((name,index)=>task.plan[room]![index]===name)))
 if(duplicate)return duplicate
 const task=new MowerTask({plan,type:T.SELF_CORRECTION,time:fromMowerMicros(data.nowMicros)});task.derivedCorrection=true;task.correctionSkipDorm=skipDorm;queue.tasks.push(task);return task
}

/** Port of _prepare_correction_recovery: a saved ordinary recall must first restore unfinished recovery. */
export function prepareMowerCorrectionRecovery(data:MowerSchedulingData,task:MowerTask,pending:readonly MowerTask[]):boolean {
 if(!data.alpha||task.type!==T.SELF_CORRECTION||!task.derivedCorrection||task.metadata||task.arrangementStarted||task.backupShiftActive||task.backupExplicitSlots.size||task.productShiftLocked||task.exhaustSupport||task.ordinaryCoordination||task.preferredReplacementRestore||task.dormRecoveryRestore.length)return false
 const names=new Set([...mowerOffDutyFullRecoveryMembers(data)].filter(name=>{
  const op=data.operators[name]!,row=task.plan[op.room]
  return !data.busyRestingNames.has(name)&&row!==undefined&&op.index<row.length&&row[op.index]!=='Current'
 }))
 if(!names.size)return false
 const previous=JSON.stringify(task.plan)
 preferMowerRestingReplacements(data,task.plan)
 completeMowerDepartedRecovery(data,task.plan,names,pending.filter(other=>other!==task))
 if(JSON.stringify(task.plan)===previous)return false
 delete task.backupShiftIntent;delete task.backupShiftConditions
 task.groupShiftTransitions={};task.dormFillPlan={}
 return true
}

/** New observations invalidate a derived correction, but never an explicit or started arrangement. */
export function refreshMowerDerivedCorrection(data:MowerSchedulingData,task:MowerTask,pending:readonly MowerTask[]):boolean {
 if(!task.derivedCorrection||task.type!==T.SELF_CORRECTION||task.arrangementStarted||task.backupShiftActive||task.backupShiftIntent||task.backupShiftConditions||task.backupRefreshRules||task.backupExplicitSlots.size||task.productShiftLocked||task.productLockNames.size||task.productLockSlots.size||task.exhaustSupport||task.ordinaryCoordination||task.preferredReplacementRestore||task.dormRecoveryRestore.length||task.coordinationRequestNames.length||task.strictMoodLimit||task.advanceSupportSwap||task.arrangementRetryDueMicros!==undefined||task.arrangementRetryRoom!==undefined||task.arrangementRetryCount!==undefined||task.metadata)return false
 task.plan=mowerCorrectionPlan(data,task.correctionSkipDorm,new Set(),pending,task)
 task.groupShiftTransitions={};task.dormFillPlan={}
 delete task.previewReturnVeto
 return true
}
