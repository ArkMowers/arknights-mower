import {MowerShiftPreviewError} from './mowerNativeErrors'
import {mowerDormIsolationCost} from './mowerDormIsolation'
import { orderMowerAlphaDormIndices } from './mowerDormOrder'
import {mowerRestingBindingGroups,mowerSharedReplacements,mowerSameGroupPrimaryReplacement,mowerArrangementGroupTransitions} from './mowerSharedGroups'
// October 3 alpha b2d9ac85fe070e805aadf0d5f44fc095c1e95253 (Mower, MIT).
// Shared identity, takeover and displacement rules; actual room I/O stays in the adapter.
import {mowerReplacementCandidates,restingMood,hasRestingMood} from './mowerOperatorState'
import type {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {MOWER_TASK_TYPES as T,type MowerTask,type MowerTaskPlan} from './mowerTaskQueue'

export const alphaPosition=(room:string,index:number)=>room+'\0'+index
export function alphaRestingTier(data:MowerSchedulingData,name:string,referencedReplacements?:ReadonlySet<string>):number{
 const op=data.operators[name]
 if(data.freeBlacklist.includes(name)||op?.workaholic)return 7
 if(data.restingPriorityNames.includes(name))return 0
 const replacement=data.priorityReplacement.includes(name)?3:5
 if(op){
  if(op.room==='train'&&op.index===0||op.currentRoom==='train'&&op.currentIndex===0)return replacement
  if(op.isHigh())return op.restingPriority==='standby'&&op.standbyLowPriority?2:{high:1,low:2,standby:4}[op.restingPriority]
  if(op.restingFromTrain)return replacement
 }
 return (referencedReplacements?.has(name)??Object.values(data.operators).some(owner=>owner.nativeName!=='菲亚梅塔'&&owner.replacement.includes(name)))?replacement:6
}
export function alphaRestingKey(data:MowerSchedulingData,name:string):[number,number]{return [alphaRestingTier(data,name),restingMood(data.operators[name],data.nowMicros)-(data.operators[name]?.upperLimit??24)]}
export const compareAlphaKeys=(a:readonly number[],b:readonly number[])=>a[0]!-b[0]!||a[1]!-b[1]!

/** Native augmenting-path matching retains feasible earlier preferences. */
export function mowerMatchReplacements(options:Record<string,string[]>,allowPartial=false):Record<string,string>|undefined{
 const owners=new Map<string,string>()
 const reserve=(name:string,seen:Set<string>):boolean=>{
  for(const cover of options[name]!)if(!owners.has(cover)){owners.set(cover,name);return true}
  for(const cover of options[name]!){if(seen.has(cover))continue;seen.add(cover);if(reserve(owners.get(cover)!,seen)){owners.set(cover,name);return true}}
  return false
 }
 for(const name of Object.keys(options))if(!reserve(name,new Set())&&!allowPartial)return undefined
 return Object.fromEntries([...owners].map(([cover,name])=>[name,cover]))
}
export function alphaDormResidents(data:MowerSchedulingData):Map<string,string>{return new Map(data.dorms.map(b=>{
 const op=data.currentOperator(...b.position)
 return [alphaPosition(...b.position),b.name||(op&&data.recoveryDorm(b,op.name)?op.name:'')]
}))}
/** Mandatory members losing a bed recall their whole group; standby retains its anchor. */
export function alphaRestoreDisplaced(data:MowerSchedulingData,previous:Map<string,string>,plan:MowerTaskPlan,tasks:MowerTask[],admissions:ReadonlyMap<string,string>=new Map()):Set<string>{
 const current=alphaDormResidents(data)
 for(const bed of data.dorms){
  const key=alphaPosition(...bed.position),name=plan[bed.position[0]]?.[bed.position[1]]
  if(name!==undefined&&name!=='Current'&&!(['Free',''].includes(name)&&bed.name!==previous.get(key)&&bed.name))current.set(key,['Free',''].includes(name)?'':name)
 }
 for(const [position,name] of admissions)current.set(position,name)
 const retained=new Set(current.values()),recalled=new Set<string>()
 for(const [position,name] of previous){
  if(!name||name===current.get(position)||retained.has(name))continue
  const op=data.operators[name];if(!op?.isHigh()||!data.plan[op.room])continue
  if(op.multiGroup||op.group&&!data.isGroupShiftAnchor(op))continue
  const members=op.group?data.shiftGroupMembers(op.group):[name],completed=!!op.group&&hasRestingMood(op,data.nowMicros)&&restingMood(op,data.nowMicros)>=op.upperLimit
  if((completed||data.canStandby(op))&&Object.values(data.operators).some(anchor=>retained.has(anchor.name)&&data.isGroupShiftAnchor(anchor)&&(data.canStandby(op)&&alphaRestingTier(data,anchor.name)<=3||!data.canStandby(anchor)&&!(hasRestingMood(anchor,data.nowMicros)&&restingMood(anchor,data.nowMicros)>=anchor.upperLimit))&&(!op.group||members.includes(anchor.name))))continue
  for(const member of members)recalled.add(member)
 }
 const transitions=mowerArrangementGroupTransitions(data,plan)
 for(const name of recalled){const op=data.operators[name]!;if(op.group&&!op.multiGroup)transitions[op.group]=false}
 for(const name of [...recalled]){const op=data.operators[name]!;if(op.multiGroup&&mowerRestingBindingGroups(data,op,transitions).length)recalled.delete(name)}
 for(const name of [...recalled]){
  const op=data.operators[name]!,target=plan[op.room]?.[op.index]
  if(target&&!['Current','Free','',name].includes(target)||Object.entries(plan).some(([room,row])=>row.some((target,index)=>target===name&&(room!==op.room||index!==op.index)))){recalled.delete(name);continue}
  ;(plan[op.room]??=Array(data.plan[op.room]!.length).fill('Current'))[op.index]=name
 }
 for(const bed of data.dorms)if(recalled.has(bed.name)){
  if(recalled.has(current.get(alphaPosition(...bed.position))??''))(plan[bed.position[0]]??=Array(data.plan[bed.position[0]]!.length).fill('Current'))[bed.position[1]]='Free'
  bed.reset()
 }
 const changed=new Set(data.dorms.filter(b=>previous.get(alphaPosition(...b.position))!==current.get(alphaPosition(...b.position))).map(b=>alphaPosition(...b.position)))
 for(const task of [...tasks]){
  if(task.plan===plan||![T.SHIFT_ON,T.RELEASE_DORM].includes(task.type))continue
  for(const [room,names] of Object.entries(task.plan)){
   names.forEach((name,index)=>{if(task.type===T.SHIFT_ON&&recalled.has(name)||task.type===T.RELEASE_DORM&&changed.has(alphaPosition(room,index)))names[index]='Current'})
   if(names.every(name=>name==='Current'))delete task.plan[room]
  }
  if(!Object.keys(task.plan).length)tasks.splice(tasks.indexOf(task),1)
 }
 return recalled
}
export function alphaSlotTakable(data:MowerSchedulingData,bed:MowerDormState,requester?:string,activeGroups?:Set<string>):boolean{
 const owner=data.operators[data.plan[bed.position[0]]?.[bed.position[1]]??''],groups=owner?.multiGroup?mowerRestingBindingGroups(data,owner,Object.fromEntries([...(activeGroups??[])].map(group=>[group,true]))):[]
 if(!data.effectiveFreeSlot(bed)&&!(bed.autoFree&&(owner?.multiGroup?groups.length>0&&mowerSharedReplacements(owner,groups).includes('Free'):activeGroups?.has(owner?.group??''))))return false
 const reserved=data.reservedProductBeds.get(alphaPosition(...bed.position));if(reserved&&requester!==reserved&&(!requester||![3,5,6].includes(alphaRestingTier(data,requester))))return false
 const actual=data.currentOperator(...bed.position),name=bed.name||(actual&&data.recoveryDorm(bed,actual.name)?actual.name:'')
 if(!name)return true
 const op=data.operators[name]
 if(!op||data.freeRoomExcluded(name)||op.currentRoom!==bed.position[0]||op.currentIndex!==bed.position[1]||!requester)return false
 return alphaRestingTier(data,requester)<alphaRestingTier(data,name)||data.emergencyDormAgents.has(name)&&(op.index<2||alphaRestingTier(data,requester)===alphaRestingTier(data,name))&&hasRestingMood(op,data.nowMicros)&&!op.moodIsPrediction&&op.mood>=op.upperLimit
}
export function alphaFindDormSlot(data:MowerSchedulingData,name:string,used:Set<number>,activeGroups?:Set<string>,plan:MowerTaskPlan={},reservedSlots:ReadonlySet<string>=new Set()):number|undefined{
 if(data.restMoodComplete(name)||alphaRestingTier(data,name)===7)return undefined
 const vip=Object.keys(data.plan).filter(room=>room.startsWith('dorm')).length,indices=orderMowerAlphaDormIndices(data,activeGroups)
 const order=alphaRestingTier(data,name)<=1||data.dormOrder.some(value=>value.endsWith('_low'))?indices:[...indices.slice(vip),...indices.slice(0,vip)]
 const candidates=order.filter(i=>!used.has(i)&&!reservedSlots.has(alphaPosition(...data.dorms[i]!.position))&&alphaSlotTakable(data,data.dorms[i]!,name,activeGroups))
 const cost=(i:number)=>{const bed=data.dorms[i]!,isolation=mowerDormIsolationCost(data,name,...bed.position,plan);if(!bed.name)return [0,0,0,isolation];const [tier,mood]=alphaRestingKey(data,bed.name);return [1,-tier,isolation,-mood]}
 candidates.sort((a,b)=>{const x=cost(a),y=cost(b);return x[0]!-y[0]!||x[1]!-y[1]!||x[2]!-y[2]!||x[3]!-y[3]!})
 return candidates[0]
}
/** Only new arrivals compete for each room's first dynamic recovery position. */
export function alphaPrioritizeRecovery(data:MowerSchedulingData,plan:MowerTaskPlan,preceding:MowerTaskPlan={},reservedSlots=new Set<string>()):MowerTaskPlan{
 if(!Object.keys(plan).length)return plan
 const projected=projectMowerArrangements(data,[preceding,plan]),explicit=new Set(Object.values(plan).flat()),lockedRooms=new Set<string>()
 for(const slot of [...reservedSlots,...data.reservedProductBeds.keys()])lockedRooms.add(slot.split('\0')[0]!)
 for(const bed of data.dorms){const op=data.operators[bed.name];if(op&&!explicit.has(op.name)&&(op.currentRoom!==bed.position[0]||op.currentIndex!==bed.position[1]))lockedRooms.add(bed.position[0])}
 const beds=projected.dorms.filter(b=>projected.effectiveFreeSlot(b)&&!lockedRooms.has(b.position[0]))
 const arrivals=beds.flatMap(b=>{const op=data.operators[b.name];return op&&explicit.has(op.name)&&!data.dynamicDormPosition(op.currentRoom,op.currentIndex)?[op.name]:[]})
 if(!arrivals.length)return plan
 arrivals.sort((a,b)=>compareAlphaKeys(alphaRestingKey(data,a),alphaRestingKey(data,b)))
 const targets=new Map<string,MowerDormState>();for(const b of beds)if(!targets.has(b.position[0]))targets.set(b.position[0],b)
 const result=structuredClone(plan)
 for(const name of arrivals){
  const source=beds.find(b=>b.name===name)!
  for(const target of targets.values()){
   if(target===source)break
   if(target.name&&compareAlphaKeys(alphaRestingKey(data,source.name),alphaRestingKey(data,target.name))>=0)continue
   ;[source.name,target.name]=[target.name,source.name]
   for(const bed of [source,target])(result[bed.position[0]]??=Array(data.plan[bed.position[0]]!.length).fill('Current'))[bed.position[1]]=bed.name||'Free'
   if(!source.name)break
  }
 }
 return result
}
export function alphaCorrectGroupDorms(data:MowerSchedulingData,plan:MowerTaskPlan,positions?:Set<string>):void{
 for(const group of new Set(Object.values(data.operators).map(op=>op.group).filter(Boolean))){
  const members=data.group(group),residents=members.map(n=>data.operators[n]!).filter(op=>!op.multiGroup&&op.room.startsWith('dorm')&&(!positions||positions.has(alphaPosition(op.room,op.index))))
  if(!residents.length)continue
  const recalling=members.some(n=>{const op=data.operators[n]!;return !op.room.startsWith('dorm')&&!op.workaholic&&plan[op.room]?.[op.index]===n}),resting=data.groupIsResting(group)&&!recalling,changes=new Map<string,string>()
  for(const op of residents){
   const actual=data.currentOperator(op.room,op.index);let desired=op.name
   if(resting){
    if(op.replacement.includes('Free')&&op.nativeName!=='菲亚梅塔')desired=actual&&actual.name!==op.name?actual.name:'Free'
    else{
     const candidates=mowerReplacementCandidates(op,data.operators,data.policy,data.nowMicros)
     if(actual&&candidates.includes(actual.name)){candidates.splice(candidates.indexOf(actual.name),1);candidates.unshift(actual.name)}
     const reserved=new Set([...Object.entries(plan).flatMap(([room,names])=>names.filter((_,index)=>room!==op.room||index!==op.index)),...changes.values()])
     desired=candidates.find(n=>{const cover=data.operators[n];return !!cover&&!data.excludedCandidates.has(n)&&!reserved.has(n)&&!data.busyRestingNames.has(n)&&(!cover.isHigh()||mowerSameGroupPrimaryReplacement(data,op,n))&&(actual?.name===n||!data.dormReplacementForSlot(n,cover.currentRoom,cover.currentIndex)&&(!cover.currentRoom||cover.isResting()))})??op.name
    }
   }
   changes.set(alphaPosition(op.room,op.index),desired)
  }
  for(const op of residents){const name=changes.get(alphaPosition(op.room,op.index))!,actual=data.currentOperator(op.room,op.index);if(!plan[op.room]&&actual?.name===name)continue;(plan[op.room]??=Array(data.plan[op.room]!.length).fill('Current'))[op.index]=actual?.name===name?'Current':name}
 }
 for(const [room,names] of Object.entries(plan))if(names.every(n=>n==='Current'))delete plan[room]
}
type MigrationCandidate={name:string;order:number;time?:number;position:[string,number]}
function alphaNativeReturn(data:MowerSchedulingData,plan:MowerTaskPlan,names:Iterable<string>):void {
 for(const name of names){const op=data.operators[name];if(!op?.room||!data.plan[op.room])continue;const row=plan[op.room]??=Array(data.plan[op.room]!.length).fill('Current');if(['Current',name].includes(row[op.index]!))row[op.index]=name}
}
function alphaRecoveryAssignments(data:MowerSchedulingData,beds:MowerDormState[],candidates:MigrationCandidate[],clear=true){
 const protectedNames=new Set(candidates.filter(c=>{const op=data.operators[c.name]!;return !!op.dormRecoveryRoom&&op.currentRoom===op.dormRecoveryRoom&&op.currentIndex===op.dormRecoveryIndex}).map(c=>c.name))
 const kept=candidates.slice(0,beds.length)
 for(const candidate of candidates.slice(beds.length))if(protectedNames.has(candidate.name)){
  const reverse=[...kept].reverse().findIndex(other=>!protectedNames.has(other.name)&&alphaRestingTier(data,candidate.name)<=alphaRestingTier(data,other.name))
  if(reverse>=0)kept[kept.length-1-reverse]=candidate
 }
 kept.sort((a,b)=>candidates.indexOf(a)-candidates.indexOf(b))
 const available=[...beds],assignments=new Map<string,MigrationCandidate>()
 const assign=(bed:MowerDormState,c:MigrationCandidate)=>{assignments.set(alphaPosition(...bed.position),c);available.splice(available.indexOf(bed),1)}
 for(const c of kept)if(protectedNames.has(c.name)){const op=data.operators[c.name]!,same=available.filter(b=>b.position[0]===op.dormRecoveryRoom),bed=same.find(b=>b.position[0]===op.currentRoom&&b.position[1]===op.currentIndex)??same[0];if(bed)assign(bed,c)}
 for(const c of kept)if(![...assignments.values()].includes(c)){const bed=available.find(b=>alphaPosition(...b.position)===alphaPosition(...c.position));if(bed)assign(bed,c)}
 for(const c of kept)if(![...assignments.values()].includes(c)&&available[0])assign(available[0],c)
 if(clear)for(const name of protectedNames){const op=data.operators[name]!,destination=[...assignments].find(([,c])=>c.name===name)?.[0];if(destination!==alphaPosition(op.currentRoom,op.currentIndex))op.clearDormRecovery()}
 const keptNames=new Set(kept.map(c=>c.name))
 return {assignments,dropped:candidates.filter(c=>!keptNames.has(c.name))}
}
/** Preserve valid beds; rank only decides who fits after capacity changes. */
export function alphaRebalanceDorms(data:MowerSchedulingData,previous:MowerDormState[],reserved=new Set<string>(),reservedSlots:ReadonlySet<string>=new Set()):MowerTaskPlan {
 const unique=new Map<string,MigrationCandidate>()
 previous.forEach((bed,order)=>{if(bed.name&&data.operators[bed.name]&&!reserved.has(bed.name)&&!unique.has(bed.name))unique.set(bed.name,{name:bed.name,order,time:bed.timeMicros,position:bed.position})})
 if(!unique.size)return {}
 const candidates=[...unique.values()].sort((a,b)=>compareAlphaKeys(alphaRestingKey(data,a.name),alphaRestingKey(data,b.name))||a.order-b.order),beds=data.dorms.filter(b=>data.effectiveFreeSlot(b)&&!reservedSlots.has(alphaPosition(...b.position)))
 const {assignments,dropped}=alphaRecoveryAssignments(data,beds,candidates),plan:MowerTaskPlan={},destinations=new Set<string>()
 for(const c of dropped){
  const op=data.operators[c.name]!;if(!op.isHigh())continue
  const recalling=op.group?data.group(op.group):[op.name]
  if(recalling.some(name=>{const member=data.operators[name]!;return reserved.has(name)||reservedSlots.has(alphaPosition(member.room,member.index))}))throw new MowerShiftPreviewError('宿舍迁移召回与已确认换人冲突，暂缓切表')
  alphaNativeReturn(data,plan,recalling)
 }
 for(const bed of beds){const c=assignments.get(alphaPosition(...bed.position));if(!c)continue;destinations.add(alphaPosition(...bed.position));if(data.currentOperator(...bed.position)?.name!==c.name)(plan[bed.position[0]]??=Array(data.plan[bed.position[0]]!.length).fill('Current'))[bed.position[1]]=c.name;bed.name=c.name;bed.timeMicros=c.time}
 const effective=new Set(beds.map(b=>alphaPosition(...b.position)))
 for(const c of candidates)if(!destinations.has(alphaPosition(...c.position))&&!reservedSlots.has(alphaPosition(...c.position))&&data.plan[c.position[0]]?.[c.position[1]]!==undefined)(plan[c.position[0]]??=Array(data.plan[c.position[0]]!.length).fill('Current'))[c.position[1]]=effective.has(alphaPosition(...c.position))?'Free':data.plan[c.position[0]]![c.position[1]]!
 for(const bed of data.dorms)if(!destinations.has(alphaPosition(...bed.position))&&!reservedSlots.has(alphaPosition(...bed.position)))bed.reset()
 return Object.fromEntries(Object.entries(plan).filter(([,names])=>names.some(n=>n!=='Current')))
}
/** Closing a temporary group bed recalls every member of a displaced main group. */
export function alphaRebalanceClosingDorms(data:MowerSchedulingData,plan:MowerTaskPlan,initial:Iterable<string>):Set<string> {
 const closing=new Set(Object.entries(plan).flatMap(([room,row])=>row.flatMap((name,index)=>!['Current','Free',''].includes(name)&&data.dorms.some(b=>b.position[0]===room&&b.position[1]===index&&b.autoFree)&&data.plan[room]?.[index]===name?[alphaPosition(room,index)]:[])))
 const recalled=new Set(initial)
 if(!closing.size)return recalled
 const original=data.dorms.flatMap((bed,order)=>bed.name&&data.operators[bed.name]?[{name:bed.name,order,time:bed.timeMicros,position:bed.position}]:[])
 const inactive=new Set([...recalled].map(name=>data.operators[name]?.group??'').filter(Boolean))
 let beds:MowerDormState[]=[],candidates:MigrationCandidate[]=[]
 for(;;){
  beds=data.dorms.filter(b=>!closing.has(alphaPosition(...b.position))&&data.effectiveFreeSlot(b,inactive))
  const seen=new Set<string>()
  candidates=original.filter(c=>{const op=data.operators[c.name]!;if(seen.has(c.name)||recalled.has(c.name)||op.group&&inactive.has(op.group))return false;seen.add(c.name);return true}).sort((a,b)=>compareAlphaKeys(alphaRestingKey(data,a.name),alphaRestingKey(data,b.name))||a.order-b.order)
  const {dropped}=alphaRecoveryAssignments(data,beds,candidates,false)
  const groups=new Set(dropped.map(c=>data.operators[c.name]!).filter(op=>op.isHigh()&&op.group&&!inactive.has(op.group)).map(op=>op.group))
  if(!groups.size)break
  for(const group of groups){const members=data.group(group);members.forEach(name=>recalled.add(name));inactive.add(group);alphaNativeReturn(data,plan,members);for(const name of members){const op=data.operators[name]!;if(data.dorms.some(b=>b.position[0]===op.room&&b.position[1]===op.index&&b.autoFree))closing.add(alphaPosition(op.room,op.index))}}
 }
 const {assignments}=alphaRecoveryAssignments(data,beds,candidates)
 for(const bed of data.dorms){
  if(closing.has(alphaPosition(...bed.position))){bed.reset();continue}
  const c=assignments.get(alphaPosition(...bed.position)),desired=c?.name??''
  if(bed.name!==desired)(plan[bed.position[0]]??=Array(data.plan[bed.position[0]]!.length).fill('Current'))[bed.position[1]]=desired||'Free'
  bed.name=desired;bed.timeMicros=c?.time
 }
 return recalled
}
