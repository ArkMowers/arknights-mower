import {completeMowerBackupDepartureRecovery,mowerCoveredRecoveryPending} from './mowerBackupDepartureRecovery'
import {describe,it,expect} from 'vitest'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {MowerOperatorState} from './mowerOperatorState'
import {mowerCorrectionPlan} from './mowerCorrection'
import {mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {projectMowerArrangements} from './mowerObservations'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,type MowerTaskPlan} from './mowerTaskQueue'

function fixture(beds=2){
 const operators:Record<string,MowerOperatorState>={}
 for(const [name,room,index,currentRoom,currentIndex,group,replacement,mood] of [
  ['A','central',0,'central',0,'g',['R'],0],
  ['B','meeting',0,'meeting',0,'g',['S'],24],
  ['R','',-1,'',-1,'',[],24],['S','',-1,'',-1,'',[],24],
  ['K','dormitory_1',0,'dormitory_1',0,'',[],24],
 ] as const)operators[name]=new MowerOperatorState({name,room,index,currentRoom,currentIndex,group,replacement:[...replacement],mood,timeStampMicros:0,operatorType:room?'high':'low'})
 operators.A!.exhaustRequire=true
 const data=new MowerSchedulingData({alpha:true,plan:{central:['A'],meeting:['B'],dormitory_1:['K',...Array(beds).fill('Free')]},operators,dorms:Array.from({length:beds},(_,i)=>new MowerDormState(['dormitory_1',i+1])),nowMicros:0,planConditions:[false],groupShiftState:{g:false},backupExplicitTasks:[{central:['R']}]} )
 const model:MowerShiftModel={count:1,explicitTasks:[{central:['R']}],evaluate:d=>[d.operators.A!.currentRoom==='central'&&d.operators.A!.mood<10],swap:(d,c)=>{const next=projectMowerArrangements(d,[]);next.planConditions=[...c];return next},transition:(_old,_next,original,conditions):MowerTaskPlan=>conditions[0]&&!original[0]?{central:['R']}:{},explicitSlots:(original,conditions)=>new Set(conditions[0]&&!original[0]?['central\0'+0]:[]),activate:()=>{}}
 const task=new MowerTask({type:T.SELF_CORRECTION,plan:{central:['A']}}),queue=new MowerTaskQueue();queue.tasks=[task]
 return {data,model,task,queue}
}
describe('backup departure recovery completion',()=>{
 it('completes a self-deactivating explicit departure with a bed without departing the untouched peer',()=>{
  const {data,model,task,queue}=fixture()
  prepareMowerShiftCycle(data,task,queue,model)
  const projected=projectMowerArrangements(data,[task.plan])
  expect(projected.operators.A!.isResting()).toBe(true)
  expect(projected.currentOperator('central',0)?.name).toBe('R')
  expect(projected.currentOperator('meeting',0)?.name).toBe('B')
  expect(data.currentOperator('central',0)?.name).toBe('A')
  expect(Object.values(mowerCorrectionPlan(projected)).flat()).not.toContain('A')
 })
 it('rejects the complete preview atomically when the departing member has no bed',()=>{
  const {data,model,task,queue}=fixture(0)
  expect(()=>prepareMowerShiftCycle(data,task,queue,model)).toThrow()
  expect(data.currentOperator('central',0)?.name).toBe('A')
  expect(queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(0)
 })
 it('repairs an already idle covered group member instead of recalling it at zero mood',()=>{
  const {data}=fixture()
  data.operators.A!.currentRoom='';data.operators.A!.currentIndex=-1
  data.operators.R!.currentRoom='central';data.operators.R!.currentIndex=0;data.operators.R!.mood=0
  data.groupShiftState.g=true
  const plan=mowerCorrectionPlan(data),projected=projectMowerArrangements(data,[plan])
  expect(plan.central??[]).not.toContain('A')
  expect(projected.operators.A!.isResting()).toBe(true)
  expect(projected.currentOperator('meeting',0)?.name).toBe('B')
 })
 it('does not recall recovered peers while an explicit partial departure is still recovering',()=>{
  const {data}=fixture(),op=data.operators.A!
  op.currentRoom='dormitory_1';op.currentIndex=1;op.mood=3;data.dorms[0]!.name='A';data.dorms[0]!.timeMicros=3_600_000_000
  data.operators.R!.currentRoom='central';data.operators.R!.currentIndex=0
  data.operators.C=new MowerOperatorState({name:'C',room:'room_1_1',index:0,currentRoom:'dormitory_1',currentIndex:2,group:'g',replacement:['S'],mood:24,timeStampMicros:0,operatorType:'high'})
  data.plan.room_1_1=['C'];data.dorms[1]!.name='C';data.dorms[1]!.timeMicros=0
  data.operators.S!.currentRoom='room_1_1';data.operators.S!.currentIndex=0;data.groupShiftState.g=true
  const future=new MowerTask({time:1,type:T.SHIFT_ON,plan:{central:['A'],meeting:['B'],room_1_1:['C']}})
  for(let repeat=0;repeat<3;repeat++)expect(mowerCorrectionPlan(data,false,new Set(),[future])).toEqual({})
  expect(future.timeMicros).toBe(3_600_000_000)
  data.backupExplicitTasks=[]
  expect(mowerCorrectionPlan(data).room_1_1).toContain('C')
 })
 it('does not suppress an ordinary idle-primary correction without a resting-group intent',()=>{
  const {data}=fixture()
  data.operators.A!.currentRoom='';data.operators.A!.currentIndex=-1
  expect(mowerCorrectionPlan(data).central).toContain('A')
 })
 it('allows an exhausted cover to remain in its correct slot while completing admission',()=>{
  const {data}=fixture()
  data.operators.A!.currentRoom='';data.operators.A!.currentIndex=-1
  data.operators.R!.currentRoom='central';data.operators.R!.currentIndex=0;data.operators.R!.mood=0
  const plan:MowerTaskPlan={}
  expect(mowerGetRestingPlan(data,['A'],[],plan)).toBe(true)
  expect(plan.central).toEqual(['R'])
 })
 it('still rejects a newly selected exhausted replacement',()=>{
  const {data}=fixture();data.operators.R!.mood=0;data.operators.A!.replacement.push('S');data.operators.S!.mood=0
  expect(mowerGetRestingPlan(data,['A'],[],{})).toBe(false)
 })
 it('does not convert a work transfer into recovery',()=>{
  const {data,model,task,queue}=fixture()
  task.plan={central:['R'],meeting:['A']};task.backupExplicitSlots=new Set(['central\0'+0,'meeting\0'+0])
  model.evaluate=()=>[false]
  prepareMowerShiftCycle(data,task,queue,model)
  expect(Object.entries(task.plan).filter(([room])=>room.startsWith('dorm')).flatMap(([,names])=>names)).not.toContain('A')
 })
 it.each(['exhaustSupport','productShiftLocked'] as const)('completes recovery through the %s preflight branch',flag=>{
  const {data,model,task,queue}=fixture();task[flag]=true
  prepareMowerShiftCycle(data,task,queue,model)
  expect(projectMowerArrangements(data,[task.plan]).operators.A!.isResting()).toBe(true)
  expect(task.backupExplicitSlots).toContain('dormitory_1\0'+task.plan.dormitory_1!.indexOf('A'))
 })
 it('does not convert an explicit trade runner visit into a recovery shift',()=>{
  const {data}=fixture();data.operators.A!.replacement=['但书']
  data.operators['但书']=new MowerOperatorState({name:'但书',mood:24,timeStampMicros:0})
  expect(completeMowerBackupDepartureRecovery(data,{central:['但书']},new Set(['central\0'+0]))).toEqual({central:['但书']})
 })
 it('preserves authored off-duty intent after the mood observation is invalidated',()=>{
  const {data}=fixture();const op=data.operators.A!
  op.currentRoom='';op.currentIndex=-1;op.timeStampMicros=undefined;op.mood=-1
  data.operators.R!.currentRoom='central';data.operators.R!.currentIndex=0;data.groupShiftState.g=true
  const plan=mowerCorrectionPlan(data)
  expect(plan.central??[]).not.toContain('A')
  expect(projectMowerArrangements(data,[plan]).operators.A!.isResting()).toBe(true)
 })
 it('keeps ordinary mixed-group correction without an authored backup departure',()=>{
  const {data}=fixture();data.backupExplicitTasks=[]
  data.operators.A!.currentRoom='';data.operators.A!.currentIndex=-1
  data.operators.R!.currentRoom='central';data.operators.R!.currentIndex=0;data.groupShiftState.g=true
  expect(mowerCorrectionPlan(data).central).toContain('A')
 })
 it('does not invent a recovery admission for a same-position explicit reread',()=>{
  const {data}=fixture()
  expect(completeMowerBackupDepartureRecovery(data,{central:['A']},new Set(['central\0'+0]))).toEqual({central:['A']})
 })
 it('preserves optional standby admission when its anchor occupies the available bed',()=>{
  const {data}=fixture(1),op=data.operators.A!,anchor=data.operators.B!
  op.exhaustRequire=false;op.restingPriority='standby'
  anchor.mood=2
  const result=completeMowerBackupDepartureRecovery(data,{central:['R'],meeting:['S']},new Set(['central\0'+0,'meeting\0'+0]))
  expect(result?.dormitory_1).toContain('B')
  expect(result?.dormitory_1).not.toContain('A')
 })
 it('requires the effective intersection for a multi-bound owner',()=>{
  const {data}=fixture(),op=data.operators.A!
  op.groupBindings=[{group:'g',replacement:['R']},{group:'h',replacement:['S']}]
  op.currentRoom='';op.currentIndex=-1
  data.operators.R!.currentRoom='central';data.operators.R!.currentIndex=0;data.groupShiftState={g:true,h:true}
  expect(mowerCoveredRecoveryPending(data,op)).toBe(false)
 })
 it('applies the native sole ordinary replacement, dormitory and workaholic exemptions',()=>{
  const {data}=fixture();data.operators.R!.mood=0
  expect(data.replacementExhausted('R',data.operators.A)).toBe(false)
  data.operators.A!.replacement.push('S')
  expect(data.replacementExhausted('R',data.operators.A)).toBe(true)
  expect(data.replacementExhausted('R',data.operators.K)).toBe(false)
  data.operators.R!.workaholic=true
  expect(data.replacementExhausted('R')).toBe(false)
 })
 it('respects a reserved recovery bed without changing the physical occupants',()=>{
  const {data}=fixture(1)
  expect(completeMowerBackupDepartureRecovery(data,{central:['R']},new Set(['central\0'+0]),new Set(['dormitory_1\0'+1]))).toBeUndefined()
  expect(data.currentOperator('central',0)?.name).toBe('A')
 })

})

import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {toMowerMicros} from './mowerTaskQueue'
import {resumeMowerPreviewRecovery} from './mowerPreviewRecoveryWait'
function blockedRuntime(){
 const config:RuntimeConfig={mowerAlpha:true,positions:[{id:'central_0',roomId:'central',primary:'A',candidates:['R'],group:'g'}, {id:'meeting_0',roomId:'meeting',primary:'B',candidates:['S'],group:'h'}, {id:'dormitory_1_0',roomId:'dormitory_1',primary:'K',candidates:[],dormitory:true,permanent:true}],beds:[{id:'dormitory_1_1',roomId:'dormitory_1',vip:true}],initialMorale:{A:0,B:2,R:24,S:24,K:24},idleOperators:['Idle'],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerTaskScheduling:{adjustForRunOrders:false},mowerSourcePlan:{central:[{agent:'A',group:'g',replacement:['R']}],meeting:[{agent:'B',group:'h',replacement:['S']}],dormitory_1:[{agent:'K',group:'',replacement:[]},{agent:'Free',group:'',replacement:[]}]},mowerSourceRules:{workaholic:[],exhaustRequire:['A'],restInFull:['B'],lowPriority:[],refreshDrained:[],lingMode:0}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 const {model}=fixture();state.mowerShiftModel=model;source.initial=false;source.firstInit=false
 state.occupants.meeting_0='S';state.bedOccupants.dormitory_1_1='B'
 for(const op of Object.values(data.operators)){op.currentRoom='';op.currentIndex=-1;op.timeStampMicros=0;op.depletionRate=0}
 for(const [slot,name] of Object.entries({...state.occupants,...state.bedOccupants})){const op=data.operators[name]!;op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1));op.mood=state.morale[name]??24}
 data.operators.B!.restingPriority='high';data.dorms[0]!.name='B';data.dorms[0]!.timeMicros=toMowerMicros(5.5);data.groupShiftState.h=true
 const task=new MowerTask({type:T.SELF_CORRECTION,plan:{central:['A']}});source.queue.tasks=[task]
 return {state,source,data,task}
}
describe('backup bed dependencies through real dispatch',()=>{
 it('preserves an unexecuted task while waiting on a measured bed and resumes the same request after recovery',()=>{
  const {state,source,data,task}=blockedRuntime(),rates={workRate:()=>1,recoveryRate:()=>4}
  settleRoster(state,rates)
  expect(source.waitingRecovery?.map(wait=>wait.task)).toContain(task)
  expect(task.executionFailure).toBeUndefined()
  expect(task.timeMicros).toBe(0)
  expect(state.occupants.central_0).toBe('A')
  const trace=source.trace.length
  for(let i=0;i<3;i++)settleRoster(state,rates)
  expect(source.trace.length).toBe(trace)
  expect(state.diagnostics.filter(entry=>entry.code==='mower-task-exception')).toEqual([])
  data.operators.B!.mood=24;data.operators.B!.timeStampMicros=1;state.morale.B=24
  data.operators.B!.currentRoom='meeting';data.operators.B!.currentIndex=0;data.operators.S!.currentRoom='';data.operators.S!.currentIndex=-1;state.occupants.meeting_0='B';delete state.bedOccupants.dormitory_1_1;data.dorms[0]!.reset()
  expect(resumeMowerPreviewRecovery(source)).toBe(true)
  expect(source.queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(0)
  for(let i=0;i<20&&!Object.values(state.bedOccupants).includes('A');i++){settleRoster(state,rates);if(Object.values(state.bedOccupants).includes('A'))break;const next=nextRosterActionHours(state,rates);expect(Number.isFinite(next)).toBe(true);advanceRoster(state,Math.max(next,1/3_600_000_000),rates)}
  expect(state.occupants.central_0).toBe('R')
  expect(Object.values(state.bedOccupants)).toContain('A')
 })
 it('wakes a waiting departure when a relevant reservation changes',()=>{
  const {state,source,data,task}=blockedRuntime(),reservation=new MowerTask({time:10,type:T.SHIFT_ON,plan:{dormitory_1:['Current','B']}})
  source.queue.tasks.push(reservation)
  settleRoster(state,{workRate:()=>1,recoveryRate:()=>4})
  expect(source.waitingRecovery?.map(wait=>wait.task)).toContain(task)
  source.queue.tasks=source.queue.tasks.filter(candidate=>candidate!==reservation)
  expect(resumeMowerPreviewRecovery(source)).toBe(true)
  expect(source.queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(0)
  expect(data.currentOperator('central',0)?.name).toBe('A')
 })
 it('waits without an error when an empty bed is reserved, then releases on cancellation',()=>{
  const {state,source,data,task}=blockedRuntime()
  data.operators.B!.currentRoom='meeting';data.operators.B!.currentIndex=0;data.operators.S!.currentRoom='';data.operators.S!.currentIndex=-1;state.occupants.meeting_0='B';delete state.bedOccupants.dormitory_1_1;data.dorms[0]!.reset()
  const reservation=new MowerTask({time:10,type:T.SHIFT_OFF,plan:{dormitory_1:['Current','B']}});source.queue.tasks.push(reservation)
  settleRoster(state,{workRate:()=>1,recoveryRate:()=>4})
  expect(source.waitingRecovery?.map(wait=>wait.task)).toContain(task)
  expect(task.executionFailure).toBeUndefined()
  expect(state.diagnostics.filter(entry=>entry.code==='mower-task-exception')).toEqual([])
  source.queue.tasks=source.queue.tasks.filter(candidate=>candidate!==reservation)
  expect(resumeMowerPreviewRecovery(source)).toBe(true)
  expect(source.queue.tasks).toContain(task);expect(task.timeMicros).toBe(0)
 })

})
