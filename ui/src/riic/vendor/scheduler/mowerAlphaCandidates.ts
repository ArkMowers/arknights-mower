import {projectMowerArrangements} from './mowerObservations'
import {mowerDormIsolationCost,planMowerDormIsolation} from './mowerDormIsolation'
// Shared dorm candidates and observed-card estimates, Mower alpha b2d9ac8 (MIT).
import {orderMowerAlphaDormIndices} from './mowerDormOrder'
import {hasRestingMood,restingMood} from './mowerOperatorState'
import {alphaRestingTier,compareAlphaKeys,alphaPosition,alphaSlotTakable,alphaPrioritizeRecovery,alphaRestoreDisplaced,alphaDormResidents} from './mowerAlphaDorm'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {toMowerMicros,MowerTask,MOWER_TASK_TYPES as T,type MowerTaskPlan,type MowerTaskQueue} from './mowerTaskQueue'
import {simplifyMowerAlphaDormFill} from './mowerAlphaTaskProtection'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'
export function mowerDormCandidateMood(data:MowerSchedulingData,name:string):number|undefined {
 return mowerSchedulingMoodObservation(data,name)?.[0]
}
export function mowerSchedulingMoodObservation(data:MowerSchedulingData,name:string):[number,number]|undefined {
 const op=data.operators[name],estimate=data.dormMoodEstimates.get(name),elapsed=estimate?data.nowMicros-estimate[1]:-1
 const measured=hasRestingMood(op,data.nowMicros)&&!op!.moodIsPrediction&&op!.timeStampMicros!<=data.nowMicros
 if(estimate&&Number.isFinite(estimate[0])&&estimate[0]>=0&&estimate[0]<=24&&elapsed>=0&&elapsed<toMowerMicros(1)&&(!measured||estimate[1]>op!.timeStampMicros!))return [estimate[0],estimate[1]]
 return measured?[op!.isResting()?op!.mood:restingMood(op,data.nowMicros),op!.timeStampMicros!]:undefined
}
export function mowerAlphaDormCandidates(data:MowerSchedulingData,excluded=new Set<string>(),currentResidents=new Set<string>()){
 // Candidate state is fixed during this synchronous pass; rebuild keys on every call.
 const referenced=new Set(Object.values(data.operators).flatMap(op=>op.nativeName==='菲亚梅塔'?[]:op.replacement)),tiers=new Map<string,number>()
 const tier=(name:string):number=>{let value=tiers.get(name);if(value===undefined){value=alphaRestingTier(data,name,referenced);tiers.set(name,value)}return value}
 const support=data.currentOperator('train',0)?.name
 const eligible=Object.values(data.operators).filter(op=>!excluded.has(op.name)&&!data.busyRestingNames.has(op.name)&&op.name!==support&&(!op.isHigh()||data.isStandby(op.name))&&(!op.currentRoom||currentResidents.has(op.name)&&op.isResting())&&!data.restMoodComplete(op.name)&&tier(op.name)!==7)
 const recovering:string[]=[],full:string[]=[],unknown:string[]=[]
 for(const op of eligible){
  const mood=mowerDormCandidateMood(data,op.name)
  if(!hasRestingMood(op,data.nowMicros)){if(!op.isHigh()&&!op.restMoodLimit)unknown.push(op.name)}
  else if(!data.idleRestChecked(op.name)&&mood!==undefined&&mood<op.upperLimit)recovering.push(op.name)
  else if(!op.isHigh()&&!op.restMoodLimit)full.push(op.name)
 }
 unknown.push(...data.unregisteredIdleNames.filter(n=>!data.operators[n]&&!excluded.has(n)&&!data.freeBlacklist.includes(n)&&!data.busyRestingNames.has(n)))
 const estimates=new Map<string,[number,number]>(),recoveryKeys=new Map<string,[number,number]>()
 const estimateKey=(name:string):[number,number]=>{let key=estimates.get(name);if(!key){key=[mowerDormCandidateMood(data,name)??24,tier(name)];estimates.set(name,key)}return key}
 const recoveryKey=(name:string):[number,number]=>{let key=recoveryKeys.get(name);if(!key){key=[tier(name),(mowerDormCandidateMood(data,name)??24)-(data.operators[name]?.upperLimit??24)];recoveryKeys.set(name,key)}return key}
 const compare=(a:string,b:string)=>compareAlphaKeys(estimateKey(a),estimateKey(b))
 recovering.sort((a,b)=>compareAlphaKeys(recoveryKey(a),recoveryKey(b)));full.sort(compare);unknown.sort(compare)
 const filling=[...recovering,...full,...unknown].sort(compare),searchUnknown=unknown.filter(n=>(mowerDormCandidateMood(data,n)??0)<24)
 return {recovering,full,unknown:searchUnknown,estimatedRecovering:searchUnknown.filter(n=>{const mood=mowerDormCandidateMood(data,n);return mood!==undefined&&mood<(data.operators[n]?.upperLimit??24)}),filling}
}
export function mowerDormTaskReservations(data:MowerSchedulingData,pending:MowerTask[]){
 const names=new Set<string>(),slots=new Set<string>()
 for(const task of pending){task.urgentRecoveryReservedNames.forEach(name=>names.add(name));task.urgentRecoveryReservedSlots.forEach(slot=>slots.add(slot))}
 for(const task of pending){
  const rows=Object.values(task.plan),targets=Object.keys(task.releaseDormTargets())
  // Future ordinary releases are rebuilt from observed beds after a move.
  if(task.type===T.RELEASE_DORM&&task.timeMicros>data.nowMicros&&!task.retainsExecution&&!task.strictMoodLimit&&!task.productShiftLocked
   &&rows.length===1&&targets.length>0&&rows.flat().every(name=>name==='Current'||name==='Free')&&targets.length===rows.flat().filter(name=>name==='Free').length)continue
  for(const [room,row] of Object.entries(task.plan))row.forEach((name,index)=>{
   if(room.startsWith('dorm')&&name!=='Current')slots.add(alphaPosition(room,index))
   if(!['Current','Free',''].includes(name)&&!(task.type===T.SHIFT_ON&&data.isStandby(name)))names.add(name)
  })
 }
 return {names,slots}
}
function alphaFill(data:MowerSchedulingData,pending:MowerTask[],emptyOnly:boolean){
 const reserved=mowerDormTaskReservations(data,pending),vacancies=new Set(data.dorms.filter(b=>!b.name&&!reserved.slots.has(alphaPosition(...b.position))&&data.effectiveFreeSlot(b)&&!data.currentOperator(...b.position)).map(b=>alphaPosition(...b.position)))
 const plan:MowerTaskPlan={},residents:string[]=[]
 const priorityOnly=emptyOnly&&!vacancies.size,c=mowerAlphaDormCandidates(data,reserved.names)
 const recovering=[...new Set([...c.recovering,...c.estimatedRecovering.filter(name=>data.operators[name]&&alphaRestingTier(data,name)<=3)])]
  .filter(name=>!priorityOnly||alphaRestingTier(data,name)<=3)
  .sort((a,b)=>compareAlphaKeys([alphaRestingTier(data,a),(mowerDormCandidateMood(data,a)??24)-data.operators[a]!.upperLimit],[alphaRestingTier(data,b),(mowerDormCandidateMood(data,b)??24)-data.operators[b]!.upperLimit]))
 const recoveryNames=new Set(recovering),full=c.filling.filter(n=>!c.recovering.includes(n)&&!c.unknown.includes(n)),unknown=!!c.unknown.length&&!priorityOnly
 if(priorityOnly&&!recovering.length)return {plan,residents,vacancies}
 if(!recovering.length&&!c.filling.length)return {plan,residents,vacancies}
 const beds=orderMowerAlphaDormIndices(data).map(index=>data.dorms[index]!)
 for(const bed of beds){
  if(plan[bed.position[0]]?.[bed.position[1]]!==undefined&&plan[bed.position[0]]![bed.position[1]]!=='Current')continue
  const position=alphaPosition(...bed.position);if(reserved.slots.has(position)||!data.effectiveFreeSlot(bed))continue
  let occupant=data.operators[bed.name],incoming:string|undefined
  if(vacancies.size){if(!vacancies.has(position))continue;occupant=undefined}
  else {
   if(!occupant||occupant.currentRoom!==bed.position[0]||occupant.currentIndex!==bed.position[1]||data.freeRoomExcluded(occupant.name))continue
   const residentTier=alphaRestingTier(data,occupant.name)
   incoming=recovering.find(name=>{
    const requesterTier=alphaRestingTier(data,name),op=data.operators[name]!
    return requesterTier<residentTier&&residentTier>3&&residentTier<7
     &&(requesterTier<=3||hasRestingMood(op,data.nowMicros)&&restingMood(op,data.nowMicros)<=op.upperLimit*.8)
     &&alphaSlotTakable(data,bed,name)
   })
   if(!incoming)continue
  }
  if(incoming)recovering.splice(recovering.indexOf(incoming),1)
  else incoming=recovering.shift()
  if(!incoming&&unknown){incoming='Free';if(occupant)residents.push(occupant.name)}
  if(!incoming){incoming=full.shift();if(!incoming)break;if(data.operators[incoming])data.operators[incoming]!.dormMoodFallback=bed.position[0];else incoming='Free'}
  let selected=bed
  if(vacancies.size&&data.dormIsolation.length&&incoming!=='Free'){
   const available=data.dorms.filter(candidate=>vacancies.has(alphaPosition(...candidate.position))&&(plan[candidate.position[0]]?.[candidate.position[1]]??'Current')==='Current')
   selected=available.reduce((best,candidate)=>mowerDormIsolationCost(data,incoming!,...candidate.position,plan)<mowerDormIsolationCost(data,incoming!,...best.position,plan)?candidate:best,available[0]!)
   if(selected!==bed)beds.push(bed)
   if(!recoveryNames.has(incoming)&&data.operators[incoming])data.operators[incoming]!.dormMoodFallback=selected.position[0]
  }
  ;(plan[selected.position[0]]??=Array(data.plan[selected.position[0]]!.length).fill('Current'))[selected.position[1]]=incoming
 }
 if(Object.keys(plan).length){
  const projected=projectMowerArrangements(data,[])
  alphaRestoreDisplaced(projected,alphaDormResidents(projected),plan,pending.map(task=>Object.assign(new MowerTask({type:task.type}),task,{plan:structuredClone(task.plan)})))
 }
 return {plan,residents,vacancies}
}
export function mowerAlphaFillPlan(data:MowerSchedulingData,pending:MowerTask[]):MowerTaskPlan{const reserved=mowerDormTaskReservations(data,pending);return planMowerDormIsolation(data,alphaPrioritizeRecovery(data,alphaFill(data,pending,true).plan,{},reserved.slots,reserved.names),reserved.slots,reserved.names)}
export function planMowerAlphaDormFill(data:MowerSchedulingData,queue:MowerTaskQueue,emptyOnly=false,options:MowerTaskSchedulingOptions={}):MowerTask|undefined {
 const result=alphaFill(data,queue.tasks,emptyOnly);if(!Object.keys(result.plan).length)return
 const task=new MowerTask({type:result.vacancies.size?T.FILL_DORM:T.NOT_SPECIFIC,plan:result.plan});task.timeMicros=data.nowMicros;task.dormFillPlan=structuredClone(result.plan);task.dormMoodResidents=result.residents
 if(result.vacancies.size)simplifyMowerAlphaDormFill(task,queue.tasks,data.nowMicros,options)
 const reserved=mowerDormTaskReservations(data,queue.tasks)
 if(!task.simpleDormFill)task.plan=alphaPrioritizeRecovery(data,task.plan,{},reserved.slots,reserved.names)
 const isolated=planMowerDormIsolation(data,task.plan,reserved.slots,reserved.names)
 if(JSON.stringify(isolated)!==JSON.stringify(task.plan)){
  const filling=new Set(Object.values(task.dormFillPlan).flat().filter(name=>!['Current','Free',''].includes(name)))
  task.dormFillPlan=Object.fromEntries(Object.entries(isolated).filter(([room])=>room.startsWith('dorm')).map(([room,row])=>[room,row.map(name=>filling.has(name)||name==='Free'?name:'Current')]))
 }
 task.plan=isolated
 queue.tasks.push(task);return task
}
