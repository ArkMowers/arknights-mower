// Shared group followers and fixed-primary swaps, Mower alpha ab0a4e5 (MIT).
import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerOperatorState} from './mowerOperatorState'
import type {MowerTaskPlan} from './mowerTaskQueue'
import {mowerMatchReplacements,alphaPosition} from './mowerAlphaDorm'

export type MowerGroupTransitions=Record<string,boolean>
export function mowerArrangementGroupTransitions(data:MowerSchedulingData,plan:MowerTaskPlan):MowerGroupTransitions {
 const transitions:MowerGroupTransitions={}
 for(const [room,row] of Object.entries(plan))row.forEach((name,index)=>{
  const op=data.operators[data.plan[room]?.[index]??'']
  if(!op?.group||!data.isGroupShiftAnchor(op)||['','Current','Free'].includes(name))return
  if(name===op.name)transitions[op.group]=false
  else if(op.replacement.includes(name))transitions[op.group]??=true
 })
 return transitions
}
export function mowerRestingBindingGroups(data:MowerSchedulingData,op:MowerOperatorState,transitions:MowerGroupTransitions={}):string[]{
 return op.groupBindings.filter(binding=>transitions[binding.group]??data.groupIsResting(binding.group)).map(binding=>binding.group)
}
export function mowerSharedReplacements(op:MowerOperatorState,groups:string[]):string[]{
 return groups.length?op.replacementsForGroup(groups[0]!).filter(name=>groups.slice(1).every(group=>op.replacementsForGroup(group).includes(name))):[...op.replacement]
}
export function mowerSameGroupPrimaryReplacement(data:MowerSchedulingData,op:MowerOperatorState,name:string,group=op.group):boolean {
 const cover=data.operators[name]
 return !!group&&op.name!==name&&op.isHigh()&&!!cover?.isHigh()&&(cover.multiGroup?cover.groupBindings.some(binding=>binding.group===group):cover.group===group)&&op.replacementsForGroup(group).includes(name)
}
export function commitMowerGroupShifts(data:MowerSchedulingData,transitions:MowerGroupTransitions):void {
 const groups=new Set(Object.values(data.operators).flatMap(op=>op.multiGroup?op.groupBindings.map(binding=>binding.group):[op.group]).filter(Boolean))
 for(const group of groups)data.groupShiftState[group]??=data.groupIsResting(group)
 for(const [group,resting] of Object.entries(transitions))if(data.groupShiftState[group]!==resting)delete data.groupRecoveryFullMembers[group]
 Object.assign(data.groupShiftState,transitions)
 for(const op of Object.values(data.operators))if(op.multiGroup){
  const resting=mowerRestingBindingGroups(data,op)
  if(resting.length){op.group=resting.includes(op.group)?op.group:resting[0]!;op.replacement=[...op.replacementsForGroup(op.group)]}
 }
}
/** A primary covering another group's working slot cannot leave until that slot is released. */
export function mowerWorkingReplacementBlocked(data:MowerSchedulingData,names:Iterable<string>,plan:MowerTaskPlan={}):boolean {
 const departing=new Set(names)
 for(const name of departing){
  const op=data.operators[name];if(!op?.currentRoom||op.isResting()||op.currentRoom===op.room&&op.currentIndex===op.index)continue
  const target=plan[op.currentRoom]?.[op.currentIndex]
  if(target&&target!=='Current'&&target!==name)continue
  const owner=data.operators[data.plan[op.currentRoom]?.[op.currentIndex]??'']
  if(owner&&!departing.has(owner.name)&&mowerSameGroupPrimaryReplacement(data,owner,name))return true
 }
 return false
}
/** Mutates only the caller's plan, and only after every shared cover has a matching. */
export function normalizeMowerSharedArrangement(data:MowerSchedulingData,plan:MowerTaskPlan,transitions=mowerArrangementGroupTransitions(data,plan),explicitSlots:ReadonlySet<string>=new Set()):boolean {
 const shifting=Object.entries(transitions).flatMap(([group,resting])=>resting?data.shiftGroupMembers(group):[])
 if(mowerWorkingReplacementBlocked(data,shifting,plan))return false
 const followers=Object.values(data.operators).filter(op=>op.multiGroup&&!explicitSlots.has(alphaPosition(op.room,op.index))&&(op.index<(plan[op.room]?.length??0)||op.groupBindings.some(binding=>binding.group in transitions)))
 if(!followers.length)return true
 const managed=new Set(followers.map(op=>op.room+'\0'+op.index))
 const reserved=new Set([...data.reservedProductReplacements,...data.excludedCandidates,...Object.entries(plan).flatMap(([room,row])=>row.filter((name,index)=>!managed.has(room+'\0'+index)&&!['','Current','Free'].includes(name)))])
 const departing=new Set(followers.filter(op=>op.currentRoom===op.room&&op.currentIndex===op.index&&mowerRestingBindingGroups(data,op,transitions).length).map(op=>op.name))
 const changes:Record<string,string>={},options:Record<string,string[]>={}
 for(const op of followers){
  const groups=mowerRestingBindingGroups(data,op,transitions),target=plan[op.room]?.[op.index],actual=data.currentOperator(op.room,op.index)
  if(!groups.length){if(op.groupBindings.some(binding=>binding.group in transitions))changes[op.name]=op.name;continue}
  const candidates=mowerSharedReplacements(op,groups)
  if(!candidates.length)return false
  if(candidates.includes('Free')&&op.room.startsWith('dorm')){
   let desired=target&&![op.name,'Current'].includes(target)?target:actual&&actual.name!==op.name?actual.name:'Free'
   if((!target||[op.name,'Current'].includes(target))&&actual&&Object.entries(plan).some(([room,row])=>row.some((name,index)=>name===actual.name&&(room!==op.room||index!==op.index))))desired='Free'
   if(!['','Current','Free'].includes(desired))options[op.name]=reserved.has(desired)?[]:[desired]
   else changes[op.name]=desired
   continue
  }
  options[op.name]=[...new Set([actual?.name,target,...candidates])].filter((name):name is string=>!!name&&candidates.includes(name)).filter(name=>{
   const cover=data.operators[name];if(reserved.has(name)||!cover)return false
   const released=plan[cover.currentRoom]?.[cover.currentIndex]
   return actual?.name===name||!cover.currentRoom||cover.isResting()&&!data.dormReplacementForSlot(name,cover.currentRoom,cover.currentIndex)||!!released&&!['Current',name].includes(released)||(departing.has(name)||Object.values(plan).some(row=>row.includes(name)))&&groups.some(group=>mowerSameGroupPrimaryReplacement(data,op,name,group))
  })
 }
 const matched=mowerMatchReplacements(options);if(!matched)return false
 Object.assign(changes,matched)
 for(const [name,target] of Object.entries(changes)){
  const op=data.operators[name]!,desired=data.currentOperator(op.room,op.index)?.name===target?'Current':target
  if(desired!=='Current'||plan[op.room])(plan[op.room]??=Array(data.plan[op.room]!.length).fill('Current'))[op.index]=desired
 }
 for(const [room,row] of Object.entries(plan))if(row.every(name=>name==='Current'))delete plan[room]
 return true
}
