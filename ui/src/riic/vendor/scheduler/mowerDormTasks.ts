import {commitMowerGroupShifts,mowerArrangementGroupTransitions,mowerRestingBindingGroups,normalizeMowerSharedArrangement} from './mowerSharedGroups'
// Port of generate_plan_by_drom and merge_release_dorm, default Mower alpha.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {MOWER_TASK_TYPES as T,MowerTask,toMowerMicros,isMowerRunOrderTask,type MowerTaskPlan} from './mowerTaskQueue'
import type {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'
import {projectMowerArrangements} from './mowerObservations'
import {alphaPosition,alphaRebalanceClosingDorms} from './mowerAlphaDorm'
export interface MowerDormBatch {timeMicros:number;dorms:MowerDormState[];restInFull:boolean|null}
export type MowerReturnTargets=Record<string,[string,number]>
export function mergeMowerReleaseDorm(tasks:MowerTask[],intervalMinutes:number):void {
 for(let idx=2;idx<=tasks.length;idx++){
  const index=tasks.length-idx,task=tasks[index]!;if(task.type!==T.RELEASE_DORM||task.strictMoodLimit)continue
  let lastNotRelease:MowerTask|undefined
  for(let previous=idx+1;previous<=tasks.length;previous++){const other=tasks[tasks.length-previous]!;if(other.type!==T.RELEASE_DORM&&other.timeMicros>task.timeMicros-toMowerMicros(1/60))lastNotRelease=other}
  if(lastNotRelease)continue
  const next=tasks[index+1]!;if(task.timeMicros+toMowerMicros(intervalMinutes/60)>next.timeMicros){task.timeMicros=next.timeMicros+toMowerMicros(1/3600);tasks[index]=next;tasks[index+1]=task}
 }
}
export function generateMowerDormTasks(batches:MowerDormBatch[],data:MowerSchedulingData,existingTargets:MowerReturnTargets={},pending:MowerTask[]=[]):MowerTask[] {
 if(data.alpha)return generateAlphaDormTasks(batches,data,existingTargets,pending)
 if(!batches.length)return []
 if(data.policy.experimentalDormLogic)throw new Error('Experimental deferred arrangements require their source port')
 const ordered=[...batches].sort((a,b)=>a.timeMicros-b.timeMicros),result:MowerTask[]=[],planned=new Set<string>(),now=data.nowMicros
 for(const batch of ordered){
  let time=batch.timeMicros,exhaustExists=false;const plan:MowerTaskPlan={}
  for(const bed of batch.dorms){
   if(!bed.name||!data.operators[bed.name]||planned.has(bed.name))continue
   const op=data.operators[bed.name]!;if(op.exhaustRequire)exhaustExists=true
   if(!op.isHigh()){
    if(batch.restInFull===null&&data.skipIdleDormRelease(op.name))continue
    if(!data.plan[op.currentRoom]||op.currentIndex<0||op.currentIndex>=data.plan[op.currentRoom]!.length)continue
    ;(plan[op.currentRoom]??=Array(data.plan[op.currentRoom]!.length).fill('Current'))[op.currentIndex]='Free'
   }else{
    const agents=op.group?data.group(op.group):[op.name]
    for(const agent of agents){
     const member=data.operators[agent]!;let room=member.room,index=member.index
     const old=existingTargets[agent]
     if(old){const [oldRoom,oldIndex]=old;const slots=data.plan[oldRoom];if(slots&&oldIndex<slots.length&&(!plan[oldRoom]||['Current',agent].includes(plan[oldRoom]![oldIndex]!))){const native=slots[oldIndex];if(native===agent||!batch.dorms.some(d=>d.name===native)){room=oldRoom;index=oldIndex}}}
     const slots=plan[room]??=Array(data.plan[room]!.length).fill('Current')
     if(!['Current',agent].includes(slots[index]!)){room=member.room;index=member.index;plan[room]??=Array(data.plan[room]!.length).fill('Current')}
     plan[room]![index]=agent;planned.add(agent)
    }
   }
  }
  if(!Object.keys(plan).length)continue
  // rebalance_closing_dorm_slots is an identity operation in the default branch.
  if(batch.restInFull){time=exhaustExists?Math.max(time,now):Math.max(time-toMowerMicros(8/60),now);const task=new MowerTask({plan,type:T.SHIFT_ON});task.timeMicros=time;result.push(task)}
  else{
   if(batch.restInFull===null&&!data.freeRoom)continue
   const kind=batch.restInFull===null?T.RELEASE_DORM:T.SHIFT_ON;let added=false
   for(let index=result.length-1;index>=0;index--){const other=result[index]!;if(other.timeMicros<time)break;if(other.type===kind){const task=new MowerTask({plan,type:kind});task.timeMicros=Math.max(other.timeMicros,now-toMowerMicros(1/3600));result.splice(index,0,task);added=true;break}}
   if(!added){const task=new MowerTask({plan,type:kind});task.timeMicros=Math.max(batch.restInFull===null?time:time-toMowerMicros(8/60),now-toMowerMicros(1/3600));result.push(task)}
  }
 }
 mergeMowerReleaseDorm(result,data.mergeIntervalMinutes);return result
}

export function mowerArrangementResources(plan:MowerTaskPlan):{names:Set<string>;slots:Set<string>} {
 return {names:new Set(Object.values(plan).flat().filter(n=>!['Current','Free',''].includes(n))),slots:new Set(Object.entries(plan).flatMap(([room,row])=>row.flatMap((name,index)=>name!=='Current'?[alphaPosition(room,index)]:[])))}
}
export function mowerAfterPendingArrangements(plan:MowerTaskPlan,pending:MowerTask[]):number {
 const resources=mowerArrangementResources(plan)
 return Math.max(-Infinity,...pending.filter(task=>{const other=mowerArrangementResources(task.plan);return [...resources.names].some(n=>other.names.has(n))||[...resources.slots].some(s=>other.slots.has(s))}).map(task=>task.timeMicros+1_000_000))
}
function generateAlphaDormTasks(batches:MowerDormBatch[],data:MowerSchedulingData,existing:MowerReturnTargets,pending:MowerTask[]):MowerTask[] {
 if(!batches.length)return []
 const shadow=projectMowerArrangements(data,[]),ordered=batches.map(b=>({...b,dorms:b.dorms.map(d=>({...d,position:[...d.position] as [string,number]}))})).sort((a,b)=>a.timeMicros-b.timeMicros)
 const result:MowerTask[]=[],planned=new Set<string>(),now=data.nowMicros
 const add=(plan:MowerTaskPlan,type:typeof T.SHIFT_ON,time:number,metadata='')=>{const task=new MowerTask({plan,type,metadata});task.timeMicros=time;result.push(task)}
 for(const batch of ordered){
  const plan:MowerTaskPlan={}
  for(const bed of batch.dorms){
   const op=shadow.operators[bed.name];if(!bed.name||!op||planned.has(op.name))continue
   if(!op.isHigh()||batch.restInFull===null){
    if(batch.restInFull===null&&shadow.skipIdleDormRelease(op.name))continue
    if(!shadow.plan[op.currentRoom]||op.currentIndex<0||op.currentIndex>=shadow.plan[op.currentRoom]!.length)continue
    const projected=shadow.dorms.find(d=>d.name===op.name);if(!projected)continue
    const [room,index]=projected.position;projected.reset()
    const row=Array(shadow.plan[room]!.length).fill('Current');row[index]='Free'
    if(batch.restInFull===null){
     if(shadow.freeRoom){const releasePlan={[room]:row};add(releasePlan,T.RELEASE_DORM,Math.max(batch.timeMicros,now-1_000_000,mowerAfterPendingArrangements(releasePlan,pending)),op.name);if(!op.isHigh())planned.add(op.name)}
     continue
    }
    ;(plan[room]??=Array(row.length).fill('Current'))[index]='Free'
   }else for(const name of op.group?shadow.shiftGroupMembers(op.group):[op.name]){
    const member=shadow.operators[name]!
    if(member.independentRest&&(name!==op.name||mowerRestingBindingGroups(shadow,member).length))continue
    let room=member.room,index=member.index
    const old=existing[name]
    if(old){const [r,i]=old,native=shadow.plan[r]?.[i];if(native!==undefined&&(!plan[r]||['Current',name].includes(plan[r]![i]!))&&(native===name||!batch.dorms.some(d=>d.name===native))){room=r;index=i}}
    const row=plan[room]??=Array(shadow.plan[room]!.length).fill('Current')
    if(!['Current',name].includes(row[index]!)){room=member.room;index=member.index;plan[room]??=Array(shadow.plan[room]!.length).fill('Current')}
    plan[room]![index]=name;planned.add(name)
   }
  }
  if(!Object.keys(plan).length)continue
  if(batch.restInFull!==null){
   const transitions=mowerArrangementGroupTransitions(shadow,plan)
   if(!normalizeMowerSharedArrangement(shadow,plan,transitions))continue
   for(const op of Object.values(shadow.operators))if(op.multiGroup&&mowerRestingBindingGroups(shadow,op,transitions).length)planned.delete(op.name)
   commitMowerGroupShifts(shadow,transitions)
   alphaRebalanceClosingDorms(shadow,plan,planned).forEach(n=>planned.add(n))
  }
  const earliest=mowerAfterPendingArrangements(plan,pending)
  if(batch.restInFull){add(plan,T.SHIFT_ON,Math.max(batch.timeMicros,now,earliest));continue}
  if(batch.restInFull===null&&!shadow.freeRoom)continue
  const type=batch.restInFull===null?T.RELEASE_DORM:T.SHIFT_ON
  let inserted=false
  for(let index=result.length-1;index>=0;index--){const next=result[index]!;if(next.timeMicros<batch.timeMicros)break;if(next.type===type){const task=new MowerTask({plan,type});task.timeMicros=Math.max(next.timeMicros,now-1_000_000,earliest);result.splice(index,0,task);inserted=true;break}}
  if(!inserted)add(plan,type,Math.max(batch.timeMicros-(batch.restInFull===null?0:toMowerMicros(8/60)),now-1_000_000,earliest))
 }
 return result.sort((a,b)=>a.timeMicros-b.timeMicros)
}

/** Merge only ordinary releases, keeping each resident's original identity and bed. */
export function mergeMowerAlphaReleases(tasks:MowerTask[],intervalMinutes:number,options:MowerTaskSchedulingOptions={}):void {
 const orders=options.adjustForRunOrders===false?tasks.filter(isMowerRunOrderTask):[]
 const mergeable=orders.length?tasks.filter(t=>!isMowerRunOrderTask(t)):tasks
 mergeable.sort((a,b)=>a.timeMicros-b.timeMicros)
 const chunks:MowerTask[][]=[],rooms=new Map<string,MowerTask>();let latest:number|undefined
 const flush=()=>{if(!rooms.size)return;const chunk=[...rooms].sort(([a],[b])=>a.localeCompare(b)).map(([,task])=>task);for(const task of chunk){task.releaseStartMicros??=task.timeMicros;task.timeMicros=latest!}chunks.push(chunk);rooms.clear()}
 for(const task of [...mergeable].reverse()){
  const targets=task.releaseDormTargets(),entries=Object.entries(targets),rowEntries=Object.entries(task.plan)
  const ordinary=task.type===T.RELEASE_DORM&&!task.strictMoodLimit&&!task.productShiftLocked&&rowEntries.length===1&&entries.length>0&&Object.values(task.plan).flat().every(n=>['Current','Free'].includes(n))&&entries.length===Object.values(task.plan).flat().filter(n=>n==='Free').length
  if(!ordinary){flush();chunks.push([task]);latest=undefined;continue}
  const start=task.releaseStartMicros??task.timeMicros,room=rowEntries[0]![0];let batch=rooms.get(room),existing=batch?.releaseDormTargets()??{}
  if(rooms.size&&(latest!==start&&latest!-start>=toMowerMicros(intervalMinutes/60)||entries.some(([name,position])=>existing[name]||Object.values(existing).some(p=>alphaPosition(...p)===alphaPosition(...position))))){flush();latest=undefined;batch=undefined;existing={}}
  if(!rooms.size)latest=task.timeMicros
  if(!batch){rooms.set(room,task);continue}
  task.plan[room]!.forEach((name,index)=>{if(name==='Free')batch!.plan[room]![index]=name})
  batch.releaseTargets={...targets,...existing};batch.metadata=Object.keys(batch.releaseTargets).join(',');batch.releaseStartMicros=Math.min(start,batch.releaseStartMicros??batch.timeMicros)
 }
 flush();tasks.splice(0,tasks.length,...chunks.reverse().flat(),...orders)
 if(orders.length)tasks.sort((a,b)=>a.timeMicros-b.timeMicros)
}
