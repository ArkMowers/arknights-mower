import {describe,expect,it,vi} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {resolveOperatorCharId as id} from '../domain/operatorIdentifiers'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createBackupPlanController} from './backupPlans'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeRates} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {MowerDormState} from './mowerSchedulingData'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {retainMowerFailedTask} from './mowerTaskFailure'
import {mowerVerifiedRecoveryDependencyReturn} from './mowerRecoveryDependency'
import {admitMowerDerivedTasks} from './mowerTaskDerivation'
import {planMowerMetadata} from './mowerMetadata'
import {cloneMowerShiftTask,prepareMowerShiftCycle} from './mowerShiftCycle'
import {projectMowerArrangements} from './mowerObservations'
import {commitMowerGroupShifts,normalizeMowerSharedArrangement} from './mowerSharedGroups'
import * as sharedGroups from './mowerSharedGroups'
import {MowerBackupRetentionBlocked} from './mowerBackupRetention'

function fixture(explicitShared=false,stableBinding=false,departureBackup=false,retentionWait=false,configure?:(workspace:ReturnType<typeof createDefaultWorkspace>)=>void){
 const workspace=createDefaultWorkspace()
 const slot=(name:string,group:string,replacement:string[])=>({occupant:{kind:'operator' as const,operatorId:id(name)},groupId:group,replacements:replacement.map(id)})
 workspace.mainPlan.facilities.room_1_1.slots=[slot('芬','a',['香草'])]
 workspace.mainPlan.facilities.room_1_2.slots=[slot('克洛丝','a',['翎羽'])]
 workspace.mainPlan.facilities.room_1_3.slots=[slot('芙蓉','b',['安德切尔'])]
 workspace.mainPlan.facilities.room_2_1.slots=[{...slot('调香师','a',['安赛尔']),groupBindings:[{groupId:'b',replacements:[id('杜林')]}]}]
 workspace.mainPlan.facilities.dormitory_1.slots=Array.from({length:5},()=>({occupant:{kind:'free' as const},groupId:null,replacements:[]}))
 workspace.mainPlan.facilities.dormitory_1.slots[4]=slot('夜莺','',[])
 workspace.compatibility.backupPlans=[{name:'b resting',trigger:"op_data.operators['芙蓉'].is_working() != True",plan:{room_1_2:{plans:[{agent:'炎熔',group:'b',replacement:['翎羽']}]}}}]
 if(stableBinding)workspace.compatibility.backupPlans=[]
 if(departureBackup)workspace.compatibility.backupPlans=[{name:'a resting',trigger:"op_data.operators['芬'].is_working() != True",plan:{room_2_1:{plans:[{agent:'调香师',group:'a',replacement:['斑点'],group_bindings:[{group:'b',replacement:['杜林']}]}]}}}]
 if(retentionWait){
  workspace.mainPlan.facilities.room_1_2.slots[0]!.groupId=''
  workspace.mainPlan.facilities.room_1_2.slots[0]!.replacements.push(id('夜刀'))
  workspace.mainPlan.conf.free_room_exclusions=[id('米格鲁')]
  workspace.mainPlan.conf.resting_standby=[id('夜刀')]
  workspace.mainPlan.facilities.meeting.slots=[slot('米格鲁','',[])]
  workspace.mainPlan.facilities.room_2_2.slots=[slot('玫兰莎','',['月见夜'])]
  Object.assign(workspace.compatibility.backupPlans[0]!.plan,{
   meeting:{plans:[{agent:'卡缇',group:'',replacement:[]}]},
   dormitory_1:{plans:[{agent:'梓兰',group:'',replacement:[]},{agent:'Free',group:'',replacement:[]},{agent:'Free',group:'',replacement:[]},{agent:'Free',group:'',replacement:[]},{agent:'Current',group:'',replacement:[]}]},
  })
 }
 if(explicitShared){workspace.mainPlan.facilities.room_3_1.slots=[{...slot('米格鲁','a',['斑点']),groupBindings:[{groupId:'b',replacements:[id('空爆')]}]}]}
 configure?.(workspace)
 const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule);config.mowerAlpha=true
 const state=createRosterRuntime(config),controller=createBackupPlanController(schedule,state),model=state.mowerShiftModel!
 const initialConditions=departureBackup?[false]:stableBinding?[]:[true]
 model.activate(initialConditions)
 const source=getMowerSourceRuntime(state),data=source.data,queue=source.queue
 source.initial=false
 for(const op of Object.values(data.operators))Object.assign(op,{currentRoom:'',currentIndex:-1,mood:24,timeStampMicros:0})
 for(const [room,name] of [['room_1_1','芬'],['room_1_2','翎羽'],['room_1_3','安德切尔'],['room_2_1','杜林']] as const){data.operators[id(name)]!.setProjectedPosition(room,0);state.occupants[room+'_0']=id(name)}
 const resting=stableBinding?['芙蓉','调香师']:['芙蓉','炎熔','调香师']
 for(const [index,name] of resting.entries()){data.operators[id(name)]!.setProjectedPosition('dormitory_1',index);state.bedOccupants['dormitory_1_'+index]=id(name)}
 data.operators[id('夜莺')]!.setProjectedPosition('dormitory_1',4);state.occupants.dormitory_1_4=id('夜莺')
 if(explicitShared){data.operators[id('米格鲁')]!.setProjectedPosition('room_3_1',0);state.occupants.room_3_1_0=id('米格鲁');data.operators[id('斑点')]!.setProjectedPosition('room_2_2',0);state.occupants.room_2_2_0=id('斑点')}
 data.operators[id('芬')]!.mood=2;state.morale[id('芬')]=2
 data.dorms=Array.from({length:4},(_,index)=>new MowerDormState(['dormitory_1',index],resting[index]?id(resting[index]!):'',0))
 data.groupShiftState={a:false,b:true};data.planConditions=initialConditions
 if(retentionWait){
  data.operators[id('芬')]!.mood=20;state.morale[id('芬')]=20
  data.operators[id('夜刀')]!.mood=10;state.morale[id('夜刀')]=10
  for(const [room,name] of [['meeting','米格鲁'],['room_2_2','月见夜']] as const){data.operators[id(name)]!.setProjectedPosition(room,0);state.occupants[room+'_0']=id(name)}
  const recovering=data.operators[id('玫兰莎')]!;recovering.setProjectedPosition('dormitory_1',2);recovering.mood=12;recovering.timeStampMicros=0
  state.bedOccupants.dormitory_1_2=recovering.name;state.morale[recovering.name]=12
  data.dorms[2]=new MowerDormState(['dormitory_1',2],recovering.name,3*3_600_000_000)
 }
 const retained=new MowerTask({type:T.RE_ORDER,time:-1,plan:{room_1_1:[id('香草')],room_1_2:[id('翎羽')],dormitory_1:['Current','Current','Current',id('芬'),'Current']}})
 if(retentionWait){retained.plan.dormitory_1![1]=id('夜刀');retained.type=T.SHIFT_OFF;retained.ordinaryCoordination=true;retained.coordinationRequestNames=[id('芬')]}
 if(explicitShared){retained.plan.room_3_1=[id('安德切尔')];retained.backupExplicitSlots.add('room_3_1\0'+'0')}
 queue.tasks=[retained];retainMowerFailedTask(state,data,retained,'shared replacement conflict')
 const candidate=new MowerTask({type:T.SHIFT_ON,plan:{room_1_3:[id('芙蓉')],room_1_2:[id('炎熔')]}})
 if(stableBinding){
  data.operators[id('翎羽')]!.setProjectedPosition('',-1);data.operators[id('克洛丝')]!.setProjectedPosition('room_1_2',0);state.occupants.room_1_2_0=id('克洛丝')
  candidate.plan={room_1_3:[id('芙蓉')]}
 }
 return {state,controller,model,source,data,queue,retained,candidate}
}

describe('verified normal return releases a failed backup arrangement',()=>{
 it('proves the real backup transition and then previews the original remaining work',()=>{
  const {data,model,queue,retained,candidate}=fixture()
  const before=JSON.stringify([data,retained,candidate]),time=retained.timeMicros
  expect(normalizeMowerSharedArrangement(data,structuredClone(retained.plan))).toBe(false)
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(true)
  expect(JSON.stringify([data,retained,candidate])).toBe(before)
  const returning=cloneMowerShiftTask(candidate)
  prepareMowerShiftCycle(data,returning,queue,model)
  expect(returning.backupShiftConditions).toEqual([false])
  let returned=model.swap(projectMowerArrangements(data,[]),returning.backupShiftConditions!)
  returned=projectMowerArrangements(returned,[returning.plan]);commitMowerGroupShifts(returned,returning.groupShiftTransitions)
  const remaining=cloneMowerShiftTask(retained)
  expect(normalizeMowerSharedArrangement(returned,remaining.plan)).toBe(true)
  prepareMowerShiftCycle(returned,remaining,queue,model)
  expect(remaining.plan.room_1_1).toEqual([id('香草')])
  expect(retained.timeMicros).toBe(time);expect(queue.tasks).toContain(retained)
 })
 it('preserves an explicit shared-slot override while proving the remaining conflict is released',()=>{
  const {data,model,queue,retained,candidate}=fixture(true)
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(true)
  retained.backupExplicitSlots.clear()
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(false)
 })
 it('admits the existing normal metadata return without changing the failed request',()=>{
  const {data,model,queue,retained}=fixture(),before=structuredClone(retained.plan)
  planMowerMetadata(data,queue,(d,r,c,p)=>mowerVerifiedRecoveryDependencyReturn(d,r,c,p,model))
  expect(queue.tasks.some(task=>task.type===T.SHIFT_ON&&task.plan.room_1_3?.includes(id('芙蓉')))).toBe(true)
  expect(retained.plan).toEqual(before);expect(retained.executionFailure).toBeDefined()
 })
 it('executes the admitted return and the retained departure through the runtime',()=>{
  const {state,controller,source,retained}=fixture(),rates={workRate:()=>1,recoveryRate:()=>4}
  const finished=()=>state.occupants.room_1_1_0===id('香草')&&state.occupants.room_1_3_0===id('芙蓉')&&!source.execution&&!source.queue.tasks.includes(retained)
  for(let step=0;step<50&&!finished();step++){
   settleRoster(state,rates,0,controller.evaluate)
   if(!finished())advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(finished()).toBe(true)
  expect(source.queue.tasks).not.toContain(retained)
  expect(state.time).toBeLessThan(1/10)
 })
 it('allows a different requested occupant only when the changed owner resolves the full arrangement',()=>{
  const {data,model,queue,retained,candidate}=fixture()
  retained.plan.room_1_2=[id('克洛丝')]
  expect(data.currentOperator('room_1_2',0)?.name).not.toBe(id('克洛丝'))
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(true)
  retained.plan.room_1_3=[id('安德切尔')]
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(false)
 })
 it.each(['future','started','backup-active','product-lock','restoration','unchanged-owner','unchanged-backup'])('rejects an unproven %s release',kind=>{
  const {data,model,queue,retained,candidate}=fixture()
  if(kind==='future')candidate.timeMicros=1
  if(kind==='started')retained.arrangementStarted=true
  if(kind==='backup-active')retained.backupShiftActive=true
  if(kind==='product-lock')retained.productShiftLocked=true
  if(kind==='restoration')retained.dormRecoveryRestore=['芬']
  if(kind==='unchanged-owner')retained.plan.room_1_3=[id('安德切尔')]
  if(kind==='unchanged-backup')model.select=data=>({groupId:data.backupGroup,conditions:[true]})
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(false)
 })
 it('does not retain an exemption after another retained task trims the proven return',()=>{
  const {data,state,retained,candidate}=fixture()
  const other=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_3:[id('芙蓉')]}})
  retainMowerFailedTask(state,data,other,'unrelated retained physical work');other.arrangementStarted=true
  const before=structuredClone(candidate.plan),proof=vi.fn((_d,r)=>r===retained)
  expect(admitMowerDerivedTasks(data,[retained,other],[candidate],proof)).toEqual([])
  expect(candidate.plan).toEqual(before);expect(proof).toHaveBeenCalledTimes(2)
 })
})


describe('shared binding dependency without a changed primary configuration',()=>{
 it('admits the recovered prerequisite while the retained departure still needs a retention bed',()=>{
  const {data,model,queue,retained,candidate}=fixture(false,true,true,true)
  const waits:MowerBackupRetentionBlocked[]=[],transition=model.transition
  model.transition=(...args)=>{try{return transition(...args)}catch(error){if(error instanceof MowerBackupRetentionBlocked)waits.push(error);throw error}}
  const before=JSON.stringify([data,retained,candidate]),time=retained.timeMicros
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(true)
  expect(waits.length).toBeGreaterThan(0);expect(waits[0]!.names).toEqual([id('米格鲁')])
  expect(JSON.stringify([data,retained,candidate])).toBe(before)
  planMowerMetadata(data,queue,(d,r,c,p)=>mowerVerifiedRecoveryDependencyReturn(d,r,c,p,model))
  expect(queue.tasks.some(task=>task.type===T.SHIFT_ON&&task.plan.room_1_3?.includes(id('芙蓉')))).toBe(true)
  expect(queue.tasks).toContain(retained);expect(retained.timeMicros).toBe(time);expect(retained.executionFailure).toBeDefined()
 })
 it('dispatches the recovered prerequisite while preserving the successor and its unresolved bed wait',()=>{
  const {state,controller,source,retained,data,queue,model}=fixture(false,true,true,true),rates:RuntimeRates={workRate:()=>1,recoveryRate:()=>4},time=retained.timeMicros
  planMowerMetadata(data,queue,(d,r,c,p)=>mowerVerifiedRecoveryDependencyReturn(d,r,c,p,model))
  const returned=()=>state.occupants.room_1_3_0===id('芙蓉')&&!source.execution&&retained.executionFailure?.reason==='副表宿舍保留安排尚无可用床位，保留原任务'
  for(let step=0;step<60&&!returned();step++){
   settleRoster(state,rates,0,controller.evaluate)
   if(!returned())advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(returned()).toBe(true);expect(state.time).toBeLessThan(1/10)
  expect(source.data.groupIsResting('b')).toBe(false)
  expect(source.queue.tasks).toContain(retained);expect(retained.timeMicros).toBe(time)
  expect(state.occupants.room_1_1_0).toBe(id('芬'))
  const pages=['INFRA_DETAILS','INFRA_CONFIDENTIAL','INFRA_CONFIDENTIAL','INFRA_CONFIDENTIAL','CLUE_GIVE_AWAY','INFRA_DETAILS'],clueRequests:string[]=[]
  rates.mowerClueIO=(request,current)=>({delayMicros:0,observe:()=>{
   clueRequests.push(request.kind)
   return {kind:request.kind,observedAtMicros:toMowerMicros(current.time),value:request.kind==='scene'?pages.shift()??'INFRA_DETAILS':null}
  }})
  const failure=retained.executionFailure,independent=new MowerTask({time:state.time,type:T.CLUE})
  source.queue.tasks.push(independent)
  for(let repeat=0;repeat<6;repeat++)settleRoster(state,rates,0,controller.evaluate)
  expect(source.queue.tasks).not.toContain(independent)
  expect(source.trace.some(entry=>entry.type==='CLUE')).toBe(true)
  expect(clueRequests).toContain('read-time');expect(clueRequests).not.toContain('save-exception')
  expect(source.queue.tasks).toContain(retained);expect(retained.timeMicros).toBe(time);expect(retained.executionFailure).toBe(failure)
 })
 it('admits a recovered group whose return releases the incompatible shared cover',()=>{
  const {data,model,queue,retained,candidate}=fixture(false,true)
  const before=JSON.stringify([data,retained,candidate]),time=retained.timeMicros
  expect(model.count).toBe(0)
  expect(normalizeMowerSharedArrangement(data,structuredClone(retained.plan))).toBe(false)
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(true)
  expect(JSON.stringify([data,retained,candidate])).toBe(before)
  expect(retained.timeMicros).toBe(time);expect(queue.tasks).toEqual([retained])
  expect(admitMowerDerivedTasks(data,queue.tasks,[candidate],(d,r,c,p)=>mowerVerifiedRecoveryDependencyReturn(d,r,c,p,model))).toEqual([candidate])
 })
 it('executes the recovered group return before completing the retained shared departure',()=>{
  const {state,controller,source,retained,data,queue,model}=fixture(false,true),rates={workRate:()=>1,recoveryRate:()=>4}
  planMowerMetadata(data,queue,(d,r,c,p)=>mowerVerifiedRecoveryDependencyReturn(d,r,c,p,model))
  const finished=()=>state.occupants.room_1_1_0===id('香草')&&state.occupants.room_1_3_0===id('芙蓉')&&!source.execution&&!source.queue.tasks.includes(retained)
  for(let step=0;step<50&&!finished();step++){
   settleRoster(state,rates,0,controller.evaluate)
   if(!finished())advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(finished()).toBe(true);expect(state.time).toBeLessThan(1/10)
 })
 it('validates the remaining departure under its newly activated backup configuration',()=>{
  const {data,model,queue,retained,candidate}=fixture(false,true,true)
  const checks:{replacement:string[],target:string|undefined}[]=[],normalize=sharedGroups.normalizeMowerSharedArrangement
  const spy=vi.spyOn(sharedGroups,'normalizeMowerSharedArrangement').mockImplementation((rules,plan,...rest)=>{
   checks.push({replacement:[...rules.operators[id('调香师')]!.replacementsForGroup('a')],target:plan.room_2_1?.[0]})
   return normalize(rules,plan,...rest)
  })
  try{
   expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(true)
   expect(checks[checks.length-1]?.replacement).toEqual([id('斑点')])
   expect(data.planConditions).toEqual([false]);expect(data.operators[id('调香师')]!.replacementsForGroup('a')).toEqual([id('安赛尔')])
  }finally{spy.mockRestore()}
 })
 it('does not admit a return when the original request would immediately displace that group again',()=>{
  const {data,model,queue,retained,candidate}=fixture(false,true)
  retained.plan.room_1_3=[id('安德切尔')]
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(false)
 })
 it('keeps a proven binding release blocked by another retained physical arrangement',()=>{
  const {data,state,model,retained,candidate}=fixture(false,true)
  const other=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_3:[id('芙蓉')]}})
  retainMowerFailedTask(state,data,other,'remaining physical work');other.arrangementStarted=true
  const pending=[retained,other],before=structuredClone(candidate.plan)
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,pending,model)).toBe(true)
  expect(admitMowerDerivedTasks(data,pending,[candidate],(d,r,c,p)=>mowerVerifiedRecoveryDependencyReturn(d,r,c,p,model))).toEqual([])
  expect(candidate.plan).toEqual(before)
 })
})

describe('retention-bed dependency release protections',()=>{
 function observeRetentionWait(model:ReturnType<typeof fixture>['model']){
  const waits:MowerBackupRetentionBlocked[]=[],transition=model.transition
  model.transition=(...args)=>{try{return transition(...args)}catch(error){if(error instanceof MowerBackupRetentionBlocked)waits.push(error);throw error}}
  return waits
 }
 it('keeps a newly activated explicit departure of the returning group binding',()=>{
  const {data,model,queue,retained,candidate}=fixture(false,true,true,true,workspace=>{
   workspace.compatibility.backupPlans[0]!.task={room_1_3:['安德切尔']}
  })
  const waits=observeRetentionWait(model),before=JSON.stringify([data,retained,candidate])
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(false)
  expect(waits.length).toBeGreaterThan(0)
  expect(JSON.stringify([data,retained,candidate])).toBe(before)
 })
 it('rejects a new shared-cover conflict in the successor backup despite its separate bed wait',()=>{
  const {data,model,queue,retained,candidate}=fixture(false,true,true,true)
  const swap=model.swap
  model.swap=(...args)=>{const rules=swap(...args);if(args[1][0])rules.excludedCandidates.add(id('斑点'));return rules}
  const waits=observeRetentionWait(model),before=JSON.stringify([data,retained,candidate])
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toBe(false)
  expect(waits.length).toBeGreaterThan(0)
  expect(JSON.stringify([data,retained,candidate])).toBe(before)
 })
 it('propagates an unexpected successor calculation exception',()=>{
  const {data,model,queue,retained,candidate}=fixture(false,true,true,true),transition=model.transition
  const failure=new Error('unexpected successor calculation exception'),before=JSON.stringify([data,retained,candidate])
  model.transition=(...args)=>{if(args[3][0])throw failure;return transition(...args)}
  expect(()=>mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,queue.tasks,model)).toThrow(failure)
  expect(JSON.stringify([data,retained,candidate])).toBe(before)
 })
 it('keeps another retained physical arrangement authoritative after the bed-wait proof',()=>{
  const {state,data,model,retained,candidate}=fixture(false,true,true,true)
  const other=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_3:[id('芙蓉')]}})
  retainMowerFailedTask(state,data,other,'remaining physical work');other.arrangementStarted=true
  const pending=[retained,other],waits=observeRetentionWait(model),before=JSON.stringify([data,retained,candidate,other])
  expect(mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,pending,model)).toBe(true)
  expect(waits.length).toBeGreaterThan(0)
  expect(admitMowerDerivedTasks(data,pending,[candidate],(d,r,c,p)=>mowerVerifiedRecoveryDependencyReturn(d,r,c,p,model))).toEqual([])
  expect(JSON.stringify([data,retained,candidate,other])).toBe(before)
 })
})
