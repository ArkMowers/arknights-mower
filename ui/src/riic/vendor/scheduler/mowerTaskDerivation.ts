import {mowerRetainedRecoveryMayReturn} from './mowerRetainedRecovery'
// Metadata may rebuild ordinary tasks, but retained physical work owns its remaining resources.
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,type MowerTask} from './mowerTaskQueue'
import {alphaPosition} from './mowerAlphaDorm'

export type MowerDependencyReturnAdmission=(data:MowerSchedulingData,retained:MowerTask,candidate:MowerTask,pending:readonly MowerTask[])=>boolean

/** Admit only derived moves independent of failed or resumed remaining arrangements. */
export function admitMowerDerivedTasks(data:MowerSchedulingData,pending:readonly MowerTask[],candidates:MowerTask[],dependencyReturn?:MowerDependencyReturnAdmission):MowerTask[]{
 const waitingGroups=new Set([...data.waitingRecoveryNames].map(name=>data.operators[name]?.group).filter(Boolean))
 candidates=candidates.filter(task=>{
  if(task.type!==T.SHIFT_ON)return true
  for(const [room,row] of Object.entries(task.plan)){
   row.forEach((name,index)=>{const actor=name==='Free'?data.currentOperator(room,index)?.name:name;if(actor&&(data.waitingRecoveryNames.has(actor)||waitingGroups.has(data.operators[actor]?.group)))row[index]='Current'})
   if(row.every(name=>name==='Current'||name===''))delete task.plan[room]
  }
  return Object.keys(task.plan).length>0
 })
 const retained=pending.filter(task=>task.retainsExecution)
 if(!retained.length)return candidates
 const claims=retained.map(task=>{
  const names=new Set<string>(),slots=new Set<string>(),groups=new Set<string>()
  const remember=(name:string|undefined)=>{
   if(!name||['Current','Free'].includes(name))return
   names.add(name)
   const op=data.operators[name]
   for(const group of op?.multiGroup?op.groupBindings.map(binding=>binding.group):[op?.group])if(group)groups.add(group)
  }
  Object.keys(task.releaseDormTargets()).forEach(remember)
  for(const [room,row] of Object.entries(task.plan))row.forEach((name,index)=>{
   if(name==='Current'||name==='')return
   slots.add(alphaPosition(room,index));remember(name)
   remember(data.plan[room]?.[index]);remember(data.currentOperator(room,index)?.name)
  })
  for(const group of groups)for(const name of data.shiftGroupMembers(group))names.add(name)
  for(const name of names){const op=data.operators[name];if(op?.currentRoom&&op.currentIndex>=0)slots.add(alphaPosition(op.currentRoom,op.currentIndex))}
  return {task,names,slots,groups}
 })
 return candidates.filter(task=>{
  if(task.retainsExecution)return true
  const originalPlan=structuredClone(task.plan)
  const releasedDependencies=new Set(claims.filter(claim=>dependencyReturn?.(data,claim.task,task,pending)).map(claim=>claim.task))
  const releases=task.releaseDormTargets(),releasedBySlot=new Map(Object.entries(releases).map(([name,position])=>[alphaPosition(...position),name]))
  const returningGroups=[T.SHIFT_ON,T.SELF_CORRECTION].includes(task.type)?new Set(Object.entries(task.plan).flatMap(([room,row])=>row.flatMap((name,index)=>{
   const op=data.operators[name]
   return op?.group&&data.isGroupShiftAnchor(op)&&op.room===room&&op.index===index&&(task.type===T.SELF_CORRECTION||op.isResting())?[op.group]:[]
  }))):new Set<string>()
  const memberGroups=new Map<string,string[]>()
  for(const group of returningGroups)for(const name of data.shiftGroupMembers(group))memberGroups.set(name,[...(memberGroups.get(name)??[]),group])
  const blockedGroups=new Set<string>()
  for(const [room,row] of Object.entries(task.plan)){
   row.forEach((name,index)=>{
    if(name==='Current'||name==='')return
    const slot=alphaPosition(room,index),current=data.currentOperator(room,index)?.name,actor=name==='Free'?releasedBySlot.get(slot)??current:name
    const conflict=claims.some(({task:retained,names,slots,groups})=>{
     if(!(slots.has(slot)||current!==undefined&&names.has(current)||actor!==undefined&&(names.has(actor)||!!data.operators[actor]?.group&&groups.has(data.operators[actor]!.group))))return false
     if(releasedDependencies.has(retained))return false
     return !(actor!==undefined&&memberGroups.get(actor)?.some(group=>mowerRetainedRecoveryMayReturn(data,retained,group)))
    })
    if(conflict){row[index]='Current';for(const group of memberGroups.get(actor??'')??[])blockedGroups.add(group)}
   })
   if(row.every(name=>name==='Current'||name===''))delete task.plan[room]
  }
  // A partial return must not escape the same group's recovery constraints.
  if(blockedGroups.size)for(const [room,row] of Object.entries(task.plan)){
   row.forEach((name,index)=>{const actor=name==='Free'?releasedBySlot.get(alphaPosition(room,index))??data.currentOperator(room,index)?.name:name;if(actor&&memberGroups.get(actor)?.some(group=>blockedGroups.has(group)))row[index]='Current'})
   if(row.every(name=>name==='Current'||name===''))delete task.plan[room]
  }
  // The proof covers the complete candidate, so another reservation cannot trim it.
  if(releasedDependencies.size&&JSON.stringify(task.plan)!==JSON.stringify(originalPlan)){task.plan=originalPlan;return false}
  if(task.type===T.RELEASE_DORM){
   task.releaseTargets=Object.fromEntries(Object.entries(releases).filter(([, [room,index]])=>task.plan[room]?.[index]==='Free'))
   task.metadata=Object.keys(task.releaseTargets).join(',')
  }
  return Object.keys(task.plan).length>0
 })
}
