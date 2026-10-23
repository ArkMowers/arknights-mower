// Ordinary cover checks follow Mower ae9fc3223 replacement_check.py (MIT).
import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerOperatorState} from './mowerOperatorState'
import type {RuntimeState} from './rosterRuntime'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {mowerDormTaskReservations} from './mowerAlphaCandidates'
import {mowerReplacementReservations} from './mowerReplacementCoordination'
import {mowerRestingBindingGroups,mowerSharedReplacements,mowerSameGroupPrimaryReplacement} from './mowerSharedGroups'
import {mowerRecoveryMoodComplete} from './mowerGroupRecovery'
import {mowerDormCandidateMood} from './mowerSchedulingMood'
import {retainMowerFailedTask} from './mowerTaskFailure'

const runners=new Set(['但书','龙舌兰','佩佩','可露希尔','U-Official'])
type Target=NonNullable<MowerTask['workingReplacementCheck']>
function candidates(data:MowerSchedulingData,owner:MowerOperatorState):string[]{
 const names=owner.multiGroup?mowerSharedReplacements(owner,mowerRestingBindingGroups(data,owner)):owner.replacement
 return [...new Set(names)].filter(name=>name!=='Free'&&!runners.has(data.operators[name]?.nativeName??name))
}
function applies(data:MowerSchedulingData,target:Target):boolean{
 const {room,index,owner,cover}=target,primary=data.operators[owner],worker=data.operators[cover]
 return !room.startsWith('dorm')&&room!=='train'&&data.plan[room]?.[index]===owner&&!!primary?.isHigh()
  &&!!worker&&!worker.isHigh()&&!worker.workaholic&&worker.currentRoom===room&&worker.currentIndex===index
  &&candidates(data,primary).includes(cover)&&candidates(data,primary).length>1
}
function reservations(data:MowerSchedulingData,queue:MowerTaskQueue,task:MowerTask){
 const pending=queue.tasks.filter(other=>other!==task),ordinary=mowerDormTaskReservations(data,pending),retained=mowerReplacementReservations(data,pending)
 return {names:new Set([...ordinary.names,...retained.reservedNames]),slots:new Set([...ordinary.slots,...retained.reservedSlots])}
}
function measured(op:MowerOperatorState|undefined,data:MowerSchedulingData):op is MowerOperatorState{
 return !!op&&!op.moodIsPrediction&&op.timeStampMicros!==undefined&&op.timeStampMicros<=data.nowMicros&&Number.isFinite(op.mood)&&op.mood>=0&&op.mood<=24
}
/** Concrete eligibility and observations release failures; elapsed time alone does not. */
export function mowerWorkingReplacementSnapshot(data:MowerSchedulingData,queue:MowerTaskQueue,task:MowerTask,state?:RuntimeState):string{
 const target=task.workingReplacementCheck!
 const owner=data.operators[target.owner],list=owner?candidates(data,owner):[]
 const relevant=[...new Set([target.owner,target.cover,...list])].sort(),reserved=reservations(data,queue,task)
 const previous=task.workingReplacementSource?JSON.parse(task.workingReplacementSource):undefined
 const card=(name:string)=>{
  const sample=data.dormMoodEstimates.get(name),op=data.operators[name]
  return sample&&Number.isFinite(sample[0])&&sample[0]>=0&&sample[0]<=24&&sample[1]<=data.nowMicros&&(!measured(op,data)||sample[1]>op.timeStampMicros!)?sample[0]:null
 }
 const previousSamples=new Map<string,unknown>((previous?.operators??[]).map((item:unknown[])=>[String(item[0]),item[3]] as [string,unknown]))
 return JSON.stringify({target,applies:applies(data,target),list,
  environment:{slots:state?.config.mowerSourcePlan?.[target.room]??data.plan[target.room],
   occupants:Object.values(data.operators).filter(op=>op.currentRoom===target.room).map(op=>[op.name,op.currentIndex]).sort(),
   product:state?.mowerFacilityProducts?.[target.room]??null,plannedProduct:state?.mowerShiftModel?.exhaustRoomContext?.(data)[target.room]??null,
   refreshDrained:(state?.config.mowerSourceRules?.refreshDrained??[]).map(name=>[name,data.operators[name]?.currentRoom,data.operators[name]?.currentIndex]).sort()},
  operators:relevant.map(name=>{const op=data.operators[name];return [name,op?.currentRoom,op?.currentIndex,measured(op,data)?[op.mood,op.depletionRate]:previousSamples.get(name)??null,op?.lowerLimit,op?.upperLimit,op?.restInFull,op?.workaholic,data.excludedCandidates.has(name),reserved.names.has(name),card(name)]}),
  slots:[...reserved.slots].filter(slot=>slot===target.room+'\0'+target.index||relevant.some(name=>{const op=data.operators[name];return slot===op?.currentRoom+'\0'+op?.currentIndex})).sort()})
}
export function syncMowerWorkingReplacementChecks(state:RuntimeState,data:MowerSchedulingData,queue:MowerTaskQueue):void{
 if(!data.alpha)return
 const targets=new Map<string,Target>(),concrete=new Set<string>()
 for(const pending of queue.tasks)if(!pending.workingReplacementCheck&&pending.timeMicros<=data.nowMicros)
  for(const [room,row] of Object.entries(pending.plan))row.forEach((name,index)=>{if(name!=='Current'&&data.currentOperator(room,index)?.name!==name)concrete.add(room+'\0'+index)})
 for(const [room,row] of Object.entries(data.plan))row.forEach((owner,index)=>{
  const cover=data.currentOperator(room,index)?.name,target={room,index,owner,cover:cover??''}
  if(cover&&applies(data,target))targets.set(JSON.stringify(target),target)
 })
 const existing=new Set<string>();let wake=false
 for(const task of [...queue.tasks]){
  if(!task.workingReplacementCheck)continue
  const key=JSON.stringify(task.workingReplacementCheck)
  if(!targets.has(key)||existing.has(key)||concrete.has(task.workingReplacementCheck.room+'\0'+task.workingReplacementCheck.index)&&!task.retainsExecution){queue.consume(task);continue}
  existing.add(key)
  const snapshot=mowerWorkingReplacementSnapshot(data,queue,task,state)
  if(task.executionFailure){
   if(snapshot===task.workingReplacementSource)continue
   delete task.executionFailure;task.executionRetained=true;task.coordinationDependencyWait=false
   wake=task.timeMicros<=data.nowMicros||wake
  }
  // New low-mood/rate evidence can advance a deadline; an ordinary reread cannot postpone it.
  if(snapshot!==task.workingReplacementSource&&!task.retainsExecution){
   const op=data.operators[task.workingReplacementCheck.cover]
   const previous=task.workingReplacementSource?JSON.parse(task.workingReplacementSource):undefined
   const old=previous?.operators?.find((item:unknown[])=>item[0]===op?.name)
   if(JSON.stringify(previous?.environment)!==JSON.stringify(JSON.parse(snapshot).environment)||measured(op,data)&&(op.mood<=op.lowerLimit||Number.isFinite(op.depletionRate)&&op.depletionRate>0&&old?.[3]?.[1]!==op.depletionRate)){
    task.timeMicros=Math.min(task.timeMicros,data.nowMicros);wake=true
   }
  }
  task.workingReplacementSource=snapshot
 }
 for(const [key,target] of targets)if(!existing.has(key)&&!concrete.has(target.room+'\0'+target.index)){
  const task=new MowerTask({metadata:'替班心情检查：'+target.cover});task.timeMicros=data.nowMicros;task.workingReplacementCheck=target
  task.workingReplacementSource=mowerWorkingReplacementSnapshot(data,queue,task,state);queue.tasks.push(task);wake=true
 }
 const source=state.mowerSource
 // Only new executable work interrupts a committed outer-run boundary.
 if(wake&&source&&!source.execution&&!source.phaseExecution)delete source.runReturn
}
export function runMowerWorkingReplacementCheck(state:RuntimeState,data:MowerSchedulingData,queue:MowerTaskQueue,task:MowerTask,read:(room:string,index:number)=>void):void{
 const target=task.workingReplacementCheck!
 if(!applies(data,target)){queue.consume(task);return}
 read(target.room,target.index)
 if(!applies(data,target)){queue.consume(task);return}
 const cover=data.operators[target.cover]!
 const retain=(reason:string,dependency=false)=>{
  task.workingReplacementSource=mowerWorkingReplacementSnapshot(data,queue,task,state)
  retainMowerFailedTask(state,data,task,reason,[target.room])
  task.coordinationDependencyWait=dependency
 }
 if(!measured(cover,data)){retain('替班心情检查未取得有效读数');return}
 if(cover.mood>cover.lowerLimit){
  if(!Number.isFinite(cover.depletionRate)||cover.depletionRate<=0){retain('替班心情仍高于下限，等待有效心情消耗观测',true);return}
  const due=data.nowMicros+toMowerMicros((cover.mood-cover.lowerLimit)/cover.depletionRate)
  if(task.retainsExecution){
   const successor=new MowerTask({metadata:task.metadata});successor.workingReplacementCheck={...target};successor.timeMicros=due
   successor.workingReplacementSource=mowerWorkingReplacementSnapshot(data,queue,successor,state);queue.consume(task);queue.tasks.push(successor)
  }else{task.timeMicros=due;task.workingReplacementSource=mowerWorkingReplacementSnapshot(data,queue,task,state)}
  return
 }
 const reserved=reservations(data,queue,task)
 if(reserved.names.has(target.cover)||reserved.slots.has(target.room+'\0'+target.index)){retain('替班岗位仍由其他任务预约');return}
 const owner=data.operators[target.owner]!
 const replacement=candidates(data,owner).find(name=>{
  const candidate=data.operators[name]
  return name!==target.cover&&measured(candidate,data)&&!reserved.names.has(name)&&!data.excludedCandidates.has(name)
   &&(!candidate.isHigh()||mowerSameGroupPrimaryReplacement(data,owner,name))&&(!candidate.currentRoom||candidate.isResting())
   &&!(candidate.isResting()&&data.dormReplacementForSlot(name,candidate.currentRoom,candidate.currentIndex))
   &&(!candidate.restInFull||!candidate.isResting()||mowerRecoveryMoodComplete(data,candidate))
   &&(candidate.workaholic||(mowerDormCandidateMood(data,name)??-1)>candidate.lowerLimit)
 })
 if(!replacement){retain('替班达到个人心情下限，尚无可用候补');return}
 const row=Array(data.plan[target.room]!.length).fill('Current');row[target.index]=replacement
 queue.tasks.push(new MowerTask({time:state.time,type:T.SELF_CORRECTION,plan:{[target.room]:row}}));queue.consume(task)
}
