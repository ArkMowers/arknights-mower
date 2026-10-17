import {describe,expect,it,vi} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {resolveOperatorCharId as id} from '../domain/operatorIdentifiers'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createBackupPlanController} from './backupPlans'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {MowerDormState} from './mowerSchedulingData'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {retainMowerFailedTask} from './mowerTaskFailure'
import {mowerVerifiedRecoveryDependencyReturn} from './mowerRecoveryDependency'
import {admitMowerDerivedTasks} from './mowerTaskDerivation'
import {planMowerMetadata} from './mowerMetadata'
import {cloneMowerShiftTask,prepareMowerShiftCycle} from './mowerShiftCycle'
import {projectMowerArrangements} from './mowerObservations'
import {commitMowerGroupShifts,normalizeMowerSharedArrangement} from './mowerSharedGroups'
import * as sharedGroups from './mowerSharedGroups'

function fixture(explicitShared=false,stableBinding=false,departureBackup=false){
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
 if(departureBackup)workspace.compatibility.backupPlans=[{name:'a resting',trigger:"op_data.operators['芬'].is_working() != True",plan:{room_2_1:{plans:[{agent:'调香师',group:'a',replacement:['斑点'],groupBindings:[{group:'b',replacement:['杜林']}]}]}}}]
 if(explicitShared){workspace.mainPlan.facilities.room_3_1.slots=[{...slot('米格鲁','a',['斑点']),groupBindings:[{groupId:'b',replacements:[id('空爆')]}]}]}
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
 const retained=new MowerTask({type:T.RE_ORDER,time:-1,plan:{room_1_1:[id('香草')],room_1_2:[id('翎羽')],dormitory_1:['Current','Current','Current',id('芬'),'Current']}})
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
  if(kind==='unchanged-backup')model.evaluate=()=>[true]
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
