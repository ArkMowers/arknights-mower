import {prepareMowerShiftBackup} from './mowerShiftCycle'
import {projectMowerArrangements} from './mowerObservations'
import {mowerGetRestingPlan,mowerTryReorder,type MowerRestingOptions} from './mowerOrdinaryPlanning'
import {mowerDormCandidateMood} from './mowerSchedulingMood'
import {alphaSupportSwapMicros} from './mowerAlphaTaskProtection'
import {mowerRestingBindingGroups} from './mowerSharedGroups'
import {mowerExhaustGroups} from './mowerExhaustPolicy'
import {planMowerMetadata} from './mowerMetadata'
import {mowerArrangementResources} from './mowerDormTasks'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,type MowerTaskPlan} from './mowerTaskQueue'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_MOOD_CONTROL_VERSION,selectMoodControlCandidate,type MoodControlResult} from './mowerPredictiveMoodControl'

export interface MowerPredictiveEvidence {version:string;fingerprint:string;names:string[];plan:MowerTaskPlan;untilMicros:number;startMicros:number}
export interface MowerPredictiveDiagnostics {reused:boolean;candidates:number;enumeratedCandidates:number;processedNodes:number;events:number;elapsedMs:number;modelMs:number;modelCalls:number;status:string;result?:MoodControlResult}
interface Cached {fingerprint:string;result:MoodControlResult;evidence?:MowerPredictiveEvidence;wake?:number;consumed?:number}
const cache=new WeakMap<MowerSchedulingData,Cached>()
const seconds=(micros:number)=>micros/1_000_000
const requestMember=(data:MowerSchedulingData,o:MowerSchedulingData['operators'][string])=>!o.workaholic&&!o.room.startsWith('dorm')&&(!o.multiGroup||o.independentRest)&&!data.canStandby(o)
/** Observations retain their absolute timestamps: elapsed time alone does not invalidate a suggestion. */
export function mowerMoodControlFingerprint(data:MowerSchedulingData,tasks:readonly MowerTask[]):string {
 return JSON.stringify([MOWER_MOOD_CONTROL_VERSION,data.plan,data.planConditions,data.backupGroup,data.policy,data.dormIsolation,data.groupShiftState,data.groupRecoveryFullMembers,data.groupRecoveryReturnMicros,[...data.busyRestingNames],[...data.excludedCandidates],[...data.reservedProductReplacements],[...data.reservedProductBeds],data.allDorms().map(b=>[b.position,b.name,b.timeMicros]),Object.values(data.operators).map(o=>[o.name,o.room,o.index,o.currentRoom,o.currentIndex,o.group,o.groupBindings,o.replacement,o.mood,o.timeStampMicros,o.depletionRate,o.upperLimit,o.lowerLimit,o.exhaustRequire,o.restInFull,o.workaholic,o.restingPriority]),tasks.filter(t=>!t.moodControlEvent).map(t=>[t.type.key,t.timeMicros,t.plan,t.executionFailure,t.arrangementStarted,t.productShiftLocked])])
}
export function completeMowerPredictivePlan(data:MowerSchedulingData,names:string[],options:MowerRestingOptions):MowerTaskPlan|undefined {
 const shadow=projectMowerArrangements(data,[]),plan:MowerTaskPlan={}
 if(!mowerGetRestingPlan(shadow,names,[],plan,{...options,dormAdmissions:new Map()}))return
 const reorder=mowerTryReorder(shadow,plan)
 if(reorder)for(const [room,row] of Object.entries(reorder)){const target=plan[room]??=Array(data.plan[room]!.length).fill('Current');row.forEach((name,index)=>{if(name!=='Current')target[index]=name})}
 const projected=projectMowerArrangements(data,[plan])
 if(names.some(name=>{const o=projected.operators[name]!;return !o.room.startsWith('dorm')&&!o.workaholic&&!o.isResting()&&!data.canStandby(o)}))return
 return plan
}
/** Advance old staffing before applying a handoff; rates are recomputed at every skill boundary. */
function advance(data:MowerSchedulingData,time:number,options:MowerRestingOptions):boolean {
 let remaining=time-data.nowMicros,steps=0
 while(remaining>0){
  if(++steps>64)return false
  const rates=options.coordinationRates?.(data);if(!rates)return false
  let dt=remaining
  const velocities=new Map<string,number>()
  for(const o of Object.values(data.operators))if(o.currentRoom){
   const rate=o.isResting()?rates.recovery[o.name]:rates.work[o.name]
   if(rate===undefined||!Number.isFinite(rate))return false
   const v=o.isResting()?rate:-rate;velocities.set(o.name,v)
   if(v)for(const boundary of [0,4,8,12,16,18,20,24,o.lowerLimit,o.upperLimit])if(v>0?boundary>o.mood+1e-8:boundary<o.mood-1e-8)dt=Math.min(dt,Math.ceil((boundary-o.mood)/v*3_600_000_000))
  }
  if(dt<=0)return false
  for(const [name,v] of velocities){const o=data.operators[name]!;o.mood=Math.max(0,Math.min(24,o.mood+v*dt/3_600_000_000));o.timeStampMicros=data.nowMicros+dt;o.depletionRate=0}
  data.nowMicros+=dt;remaining-=dt
 }
 return true
}
interface Unit {id:string;names:string[];exhaust:boolean;lowerAt:number;softAt:number}
interface DynamicResult {complete:boolean;score:number[];events:import('./mowerPredictiveMoodControl').MoodControlEvent[];firstPlan?:MowerTaskPlan;exhausted:boolean;nodes:number}
/** Independent rollouts use the native matcher and native recovery metadata at each event. */
function dynamicRollout(initial:MowerSchedulingData,tasks:readonly MowerTask[],units:Unit[],early:Unit|undefined,start:number,horizon:number,options:MowerRestingOptions):DynamicResult {
 const nodeLimit=Math.min(64,Math.max(1,options.predictiveMaxEvents??64))
 let state=projectMowerArrangements(initial,[]),nodes=0,exhausted=false,firstPlan:MowerTaskPlan|undefined
 for(const o of Object.values(state.operators)){const mood=options.predictiveCurrentMoods?.[o.name]??mowerDormCandidateMood(initial,o.name);if(mood!==undefined){o.mood=mood;o.timeStampMicros=state.nowMicros;o.depletionRate=0}}
 const queue=new MowerTaskQueue();queue.tasks=tasks.filter(t=>!t.moodControlEvent).map(t=>Object.assign(new MowerTask(),t,{plan:structuredClone(t.plan)}))
 const safeTypes=[T.CLUE,T.CLUE_PARTY,T.MAA_MALL,T.RECRUIT,T.SKLAND,T.REFRESH_TIME,T.DEPOT,T.FURNITURE]
 const service=(t:MowerTask)=>!Object.keys(t.plan).length&&!t.retainsExecution&&safeTypes.includes(t.type)
 const unknown=(t:MowerTask)=>!t.executionFailure&&![T.SHIFT_ON,T.RELEASE_DORM].includes(t.type)&&!([T.NOT_SPECIFIC,T.EXHAUST_OFF].includes(t.type)&&!Object.keys(t.plan).length)&&!service(t)
 let serviceRelease:number|undefined
 const events:DynamicResult['events']=[],score=[0,0,0,0],departed=new Set<string>(),returned=new Set<string>()
 const positions=Object.values(initial.operators).filter(o=>o.isHigh()&&!o.room.startsWith('dorm')&&!o.workaholic).map(o=>({room:o.room,index:o.index,name:o.name}))
 const tick=(until:number):boolean=>{
  // Integrate scores through skill and personal-limit boundaries using old staffing.
  while(state.nowMicros<until){
   if(++nodes>nodeLimit){exhausted=true;return false}
   const rates=options.coordinationRates?.(state);if(!rates)return false
   let dt=until-state.nowMicros
   for(const o of Object.values(state.operators))if(o.currentRoom){const rate=o.isResting()?rates.recovery[o.name]:rates.work[o.name];if(rate===undefined||!Number.isFinite(rate))return false;const v=o.isResting()?rate:-rate;if(v)for(const boundary of [0,4,8,12,16,18,20,24,o.lowerLimit,o.upperLimit])if(v>0?boundary>o.mood+1e-8:boundary<o.mood-1e-8)dt=Math.min(dt,Math.ceil((boundary-o.mood)/v*3_600_000_000))}
   for(const unit of units)if(!departed.has(unit.id)&&unit.names.some(n=>{const o=state.operators[n]!;return requestMember(state,o)&&o.currentRoom&&!o.isResting()&&o.mood<=o.lowerLimit+1e-8}))score[0]!+=dt/1_000_000
   for(const position of positions){const o=state.currentOperator(position.room,position.index);if(!o||!o.workaholic&&o.mood<=1e-8)score[1]!+=dt/1_000_000}
   if(!advance(state,state.nowMicros+dt,options))return false
  }
  return true
 }
 const apply=(plan:MowerTaskPlan,type:typeof T.SHIFT_OFF,group:string):boolean=>{
  const roomDurations=Object.entries(plan).map(([room,row])=>({room,row,duration:options.predictiveOperationMicros?.(room,type)??alphaSupportSwapMicros(new MowerTask({type,plan:{[room]:row}}),options.priorityScheduling)})),finish=state.nowMicros+roomDurations.reduce((sum,r)=>sum+r.duration,0)
  if(finish>horizon*1_000_000||queue.tasks.some(t=>unknown(t)&&t.timeMicros<finish))return false
  const overlaps=queue.tasks.filter(t=>service(t)&&t.timeMicros<finish&&state.nowMicros<t.timeMicros+alphaSupportSwapMicros(t,options.priorityScheduling))
  if(overlaps.length){serviceRelease=Math.max(...overlaps.map(t=>t.timeMicros+alphaSupportSwapMicros(t,options.priorityScheduling)));return false}
  const resources=mowerArrangementResources(plan),res=[...resources.names,...resources.slots],begin=seconds(state.nowMicros)
  events.push({time:begin,type:type===T.SHIFT_OFF?'departure-start':'return-start',group,resources:res})
  for(const {room,row,duration} of roomDurations){
   if(++nodes>nodeLimit){exhausted=true;return false}
   if(state.nowMicros+duration>horizon*1_000_000||!tick(state.nowMicros+duration))return false
   state=projectMowerArrangements(state,[{[room]:row}])
  }
  events.push({time:seconds(state.nowMicros),type:type===T.SHIFT_OFF?'departure-complete':'return-complete',group,resources:res});score[2]!++
  return true
 }
 rolloutLoop: while(state.nowMicros<horizon*1_000_000){
  serviceRelease=undefined
  const model=options.predictiveShiftModel
  if(model?.count){
   const selection=model.select?.(state),conditions=selection?.conditions??model.evaluate(state)
   if(JSON.stringify(conditions)!==JSON.stringify(state.planConditions)||selection&&selection.groupId!==state.backupGroup){
    if(++nodes>nodeLimit){exhausted=true;break}
    const transition=new MowerTask({type:T.SELF_CORRECTION,plan:{}})
    try{prepareMowerShiftBackup(state,transition,model,queue.tasks)}catch{return {complete:false,score,events,firstPlan,exhausted,nodes}}
    state=model.swap(state,transition.backupShiftConditions??conditions,transition.backupGroup??selection?.groupId)
    if(units.some(unit=>unit.names.some(name=>{const before=initial.operators[name]!,after=state.operators[name];return !after||after.room!==before.room||after.index!==before.index||after.group!==before.group})||unit.id.startsWith('group:')&&JSON.stringify(state.shiftGroupMembers(unit.id.slice(6)))!==JSON.stringify(unit.names)))return {complete:false,score,events,firstPlan,exhausted,nodes}
    if(Object.keys(transition.plan).length&&!apply(transition.plan,T.SHIFT_ON,'backup'))break
    continue
   }
  }
  const now=seconds(state.nowMicros),rates=options.coordinationRates?.(state);if(!rates)break
  // Physical dorm deadlines are refreshed from the current arrangement and skills.
  for(const bed of state.allDorms())if(bed.name){const o=state.operators[bed.name],rate=rates.recovery[bed.name];if(o&&rate!==undefined&&rate>0)bed.timeMicros=state.nowMicros+Math.ceil(Math.max(0,o.upperLimit-o.mood)/rate*3_600_000_000)}
  planMowerMetadata(state,queue,options.dependencyReturn)
  queue.sort()
  const due=queue.tasks.find(t=>!t.executionFailure&&t.timeMicros<=state.nowMicros&&[T.SHIFT_ON,T.RELEASE_DORM].includes(t.type))
  if(due){
   const owners=units.filter(u=>departed.has(u.id)&&u.names.some(n=>Object.values(due.plan).some(row=>row.includes(n))))
   if(!apply(due.plan,T.SHIFT_ON,owners[0]?.id??'existing-return')){if(serviceRelease!==undefined&&tick(Math.min(serviceRelease,horizon*1_000_000)))continue;break}
   owners.filter(u=>u.names.every(name=>{const o=state.operators[name]!;return o.currentRoom===o.room&&o.currentIndex===o.index})).forEach(u=>returned.add(u.id));queue.consume(due);continue
  }
  const candidates=units.filter(u=>!departed.has(u.id)).sort((a,b)=>Number(b.lowerAt<=now)-Number(a.lowerAt<=now)||a.lowerAt-b.lowerAt||units.indexOf(a)-units.indexOf(b))
  let action=false,next=Infinity
  for(const unit of candidates){
   let at=Infinity
   for(const name of unit.names){const o=state.operators[name]!;if(!requestMember(state,o))continue
    const rate=rates.work[name];if(rate===undefined||rate<=0)continue
    const soft=o.customMoodLimit?o.lowerLimit+(o.upperLimit-o.lowerLimit)*state.policy.restingThreshold:Math.floor(o.lowerLimit+(o.upperLimit-o.lowerLimit)*state.policy.restingThreshold)
    const limit=unit.exhaust?o.lowerLimit:soft
    at=Math.min(at,now+Math.max(0,o.mood-limit)/rate*3600)
   }
   if(unit===early&&!unit.exhaust)at=Math.min(at,start)
   if(unit===early&&at<unit.softAt&&candidates.some(other=>other!==unit&&other.names.some(n=>{const o=state.operators[n]!;return requestMember(state,o)&&o.mood<=o.lowerLimit+1e-8})))continue
   if(at>now+1e-6){next=Math.min(next,at);continue}
   // An exhausted group never obtains an early exemption through another member.
   if(unit.exhaust&&unit.names.some(n=>{const o=state.operators[n]!;return o.exhaustRequire&&o.mood>o.lowerLimit+1e-8}))continue
   const plan=completeMowerPredictivePlan(state,unit.names,options);if(!plan)continue
   departed.add(unit.id)
   if(!apply(plan,T.SHIFT_OFF,unit.id)){departed.delete(unit.id);if(serviceRelease!==undefined&&tick(Math.min(serviceRelease,horizon*1_000_000)))continue rolloutLoop;return {complete:false,score,events,firstPlan,exhausted,nodes}}
   if(unit===early&&now<unit.softAt)score[3]!+=unit.softAt-now
   if(!firstPlan)firstPlan=structuredClone(plan)
   action=true;break
  }
  if(action)continue
  // Known tasks constrain the execution window. Only native recovery actions release resources.
  const scheduled=queue.tasks.filter(t=>!t.executionFailure&&t.timeMicros>state.nowMicros).map(t=>seconds(t.timeMicros))
  next=Math.min(next,...scheduled,horizon)
  const boundary=Object.values(state.operators).flatMap(o=>{if(!o.currentRoom)return [];const rate=o.isResting()?rates.recovery[o.name]:rates.work[o.name];if(!rate||!Number.isFinite(rate))return [];const v=o.isResting()?rate:-rate;return [0,4,8,12,16,18,20,24,o.lowerLimit,o.upperLimit].filter(b=>v>0?b>o.mood+1e-8:b<o.mood-1e-8).map(b=>now+(b-o.mood)/v*3600)})
  next=Math.min(next,...boundary)
  if(!Number.isFinite(next)||next<=now||!tick(Math.min(horizon*1_000_000,Math.ceil(next*1_000_000))))break
  // Critical tasks have their own executor. Do not invent their physical completion.
  if(queue.tasks.some(t=>unknown(t)&&t.timeMicros<=state.nowMicros))break
 }
 return {complete:!exhausted&&state.nowMicros>=horizon*1_000_000&&units.every(u=>departed.has(u.id)&&returned.has(u.id))&&!queue.tasks.some(t=>unknown(t)&&t.timeMicros<=horizon*1_000_000),score,events,firstPlan,exhausted,nodes}
}
/** Batch initial deadlines on unchanged staffing, including shared mood-skill boundaries. */
function initialDeadlines(initial:MowerSchedulingData,targets:Map<string,{soft:number;lower:number}>,options:MowerRestingOptions):Map<string,{softAt:number;lowerAt:number}> {
 const result=new Map<string,{softAt:number;lowerAt:number}>();let state=projectMowerArrangements(initial,[])
 for(const o of Object.values(state.operators)){const mood=options.predictiveCurrentMoods?.[o.name]??mowerDormCandidateMood(initial,o.name);if(mood!==undefined){o.mood=mood;o.timeStampMicros=state.nowMicros;o.depletionRate=0}}
 for(let step=0;step<64;step++){
  const rates=options.coordinationRates?.(state);if(!rates)break
  let dt=Infinity
  for(const [name,target] of targets){
   const o=state.operators[name]!,entry=result.get(name)??{softAt:Infinity,lowerAt:Infinity}
   if(o.mood<=target.soft+1e-8)entry.softAt=Math.min(entry.softAt,seconds(state.nowMicros))
   if(o.mood<=target.lower+1e-8)entry.lowerAt=Math.min(entry.lowerAt,seconds(state.nowMicros))
   result.set(name,entry)
   const rate=rates.work[name]
   if(rate!==undefined&&rate>0)for(const threshold of [target.soft,target.lower])if(threshold<o.mood-1e-8)dt=Math.min(dt,Math.ceil((o.mood-threshold)/rate*3_600_000_000))
  }
  if([...result.values()].every(e=>Number.isFinite(e.lowerAt)))break
  for(const o of Object.values(state.operators))if(o.currentRoom){const rate=o.isResting()?rates.recovery[o.name]:rates.work[o.name];if(rate===undefined||!rate)continue;const v=o.isResting()?rate:-rate;for(const boundary of [0,4,8,12,16,18,20,24,o.lowerLimit,o.upperLimit])if(v>0?boundary>o.mood+1e-8:boundary<o.mood-1e-8)dt=Math.min(dt,Math.ceil((boundary-o.mood)/v*3_600_000_000))}
  if(!Number.isFinite(dt)||dt<=0||state.nowMicros+dt-initial.nowMicros>240*3_600_000_000||!advance(state,state.nowMicros+dt,options))break
 }
 return result
}
export function planMowerPredictiveDeparture(data:MowerSchedulingData,queue:MowerTaskQueue,options:MowerRestingOptions):MowerPredictiveEvidence|undefined {
 if(!data.alpha||!data.policy.predictiveMoodControl||!options.coordinationRates)return
 const started=performance.now(),fingerprint=mowerMoodControlFingerprint(data,queue.tasks),previous=cache.get(data)
 if(previous?.fingerprint===fingerprint){options.onPredictiveDiagnostics?.({reused:true,candidates:0,enumeratedCandidates:0,processedNodes:0,events:0,elapsedMs:performance.now()-started,modelMs:0,modelCalls:0,status:previous.result.status});return previous.evidence&&previous.evidence.startMicros<=data.nowMicros&&previous.evidence.untilMicros>=data.nowMicros?previous.evidence:undefined}
 let modelMs=0,modelCalls=0
 const forecast=options.coordinationRates
 options={...options,coordinationRates:state=>{const before=performance.now();modelCalls++;try{return forecast(state)}finally{modelMs+=performance.now()-before}}}
 const rates=options.coordinationRates!(data);if(!rates)return
 const targets=new Map<string,{soft:number;lower:number}>()
 for(const m of Object.values(data.operators))if(m.currentRoom&&!m.isResting()&&!m.workaholic){const soft=m.customMoodLimit?m.lowerLimit+(m.upperLimit-m.lowerLimit)*data.policy.restingThreshold:Math.floor(m.lowerLimit+(m.upperLimit-m.lowerLimit)*data.policy.restingThreshold);targets.set(m.name,{soft,lower:m.lowerLimit})}
 const deadlines=initialDeadlines(data,targets,options)
 const units:Unit[]=[],seen=new Set<string>(),now=seconds(data.nowMicros),exhausted=mowerExhaustGroups(data)
 for(const o of Object.values(data.operators)){
  const independent=o.isHigh()&&o.independentRest&&!mowerRestingBindingGroups(data,o).length&&!o.workaholic&&!data.canStandby(o)
  if(!data.isGroupShiftAnchor(o)&&!independent||o.currentRoom!==o.room||o.currentIndex!==o.index||['train','factory'].includes(o.room)||data.busyRestingNames.has(o.name))continue
  const id=o.group?'group:'+o.group:'operator:'+o.name;if(seen.has(id))continue;seen.add(id)
  const names=o.group?data.shiftGroupMembers(o.group):[o.name]
  if(names.some(n=>!data.operators[n]||options.isMasteryBusy?.(n)))continue
  let lowerAt=Infinity,softAt=Infinity
  for(const name of names){const m=data.operators[name]!;if(!requestMember(data,m))continue
   const mood=options.predictiveCurrentMoods?.[name]??mowerDormCandidateMood(data,name),rate=rates.work[name];if(mood===undefined||rate===undefined||rate<=0)continue
   lowerAt=Math.min(lowerAt,deadlines.get(name)?.lowerAt??Infinity);softAt=Math.min(softAt,deadlines.get(name)?.softAt??Infinity)
  }
  if(Number.isFinite(lowerAt))units.push({id,names,lowerAt,softAt,exhaust:o.exhaustRequire||!!o.group&&exhausted.has(o.group)})
 }
 if(!units.length)return
 const horizon=Math.min(now+240*3600,Math.max(...units.map(u=>u.lowerAt))+24*3600)
 const boundaries=[...queue.tasks.map(t=>seconds(t.timeMicros)),...units.flatMap(u=>[u.softAt,u.lowerAt])]
 const choice=selectMoodControlCandidate(now,units,boundaries,candidate=>dynamicRollout(data,queue.tasks,units,units.find(u=>u.id===candidate.group),candidate.start??now,horizon,options),16,Math.min(64,Math.max(1,options.predictiveMaxEvents??64)))
 const {best,candidates,enumeratedCandidates,processedNodes,events:eventCount,maxCandidateNodes,exhausted:budget}=choice,selected=units.find(u=>u.id===choice.selected?.group)
 const result:MoodControlResult={decision:selected?.id??null,status:budget?'budget-exhausted':best.complete?'feasible':'insufficient',score:best.score,events:best.events,candidates,enumeratedCandidates,processedNodes,eventCount,maxCandidateNodes,nextWake:best.events.find(e=>e.time>now)?.time??null}
 let evidence:MowerPredictiveEvidence|undefined
 const first=best.events.find(e=>e.type==='departure-start')
 if(selected&&first?.group===selected.id&&best.firstPlan)evidence={version:MOWER_MOOD_CONTROL_VERSION,fingerprint,names:selected.names,plan:best.firstPlan,startMicros:Math.round(first.time*1_000_000),untilMicros:Math.round(first.time*1_000_000)}
 cache.set(data,{fingerprint,result,evidence,wake:first&&first.time>now?first.time:undefined})
 options.onPredictiveDiagnostics?.({reused:false,candidates,enumeratedCandidates,processedNodes,events:eventCount,elapsedMs:performance.now()-started,modelMs,modelCalls,status:result.status,result})
 return evidence&&evidence.startMicros<=data.nowMicros?evidence:undefined
}
export function mowerPredictiveEvidenceValid(data:MowerSchedulingData,task:MowerTask,tasks:readonly MowerTask[]):boolean {
 const proof=task.moodControlEvidence
 return !!proof&&data.policy.predictiveMoodControl&&proof.version===MOWER_MOOD_CONTROL_VERSION&&proof.untilMicros>=data.nowMicros&&proof.fingerprint===mowerMoodControlFingerprint(data,tasks.filter(t=>t!==task))
}

/** One memory-only wake, without reserving a bed, operator or physical room. */
export function syncMowerPredictiveWake(data:MowerSchedulingData,queue:MowerTaskQueue):void {
 const entry=cache.get(data)
 if(queue.tasks.some(t=>t.moodControlEvent))queue.tasks=queue.tasks.filter(t=>!t.moodControlEvent)
 if(!data.policy.predictiveMoodControl||!entry?.wake||entry.wake*1_000_000<=data.nowMicros||entry.consumed===entry.wake)return
 const task=new MowerTask({type:T.NOT_SPECIFIC});task.timeMicros=Math.round(entry.wake*1_000_000);task.moodControlEvent={fingerprint:entry.fingerprint,timeMicros:task.timeMicros};queue.tasks.push(task)
}
export function consumeMowerPredictiveWake(data:MowerSchedulingData,task:MowerTask):void {
 const entry=cache.get(data);if(entry&&task.moodControlEvent?.fingerprint===entry.fingerprint){entry.consumed=task.timeMicros/1_000_000;if(data.nowMicros>task.timeMicros)cache.delete(data)}
}
