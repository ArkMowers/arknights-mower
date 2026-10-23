import {afterEach,describe,expect,it,vi} from 'vitest'
import * as planning from './mowerOrdinaryPlanning'
import {createDefaultWorkspace} from '../workbench/defaults'
import {createBackupPlanController} from './backupPlans'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createRosterRuntime} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
afterEach(()=>vi.restoreAllMocks())
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {MowerShiftPreviewError} from './mowerNativeErrors'
import {projectMowerArrangements} from './mowerObservations'
import {prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T} from './mowerTaskQueue'

function fixture(reenter=false){
 const make=(name:string,room:string,index:number,group='',replacement:string[]=[])=>new MowerOperatorState({name,room,index,group,replacement,currentRoom:room,currentIndex:index,mood:24,timeStampMicros:0,operatorType:room?'high':'low'})
 const operators={A:make('A','contact',0,'a',['X']),B:make('B','central',0,'b',['Y']),C:make('C','meeting',0,'c',['Z']),X:make('X','',-1),Y:make('Y','',-1),Z:make('Z','',-1),K:make('K','dormitory_1',0)}
 operators.B.mood=.5;operators.B.exhaustRequire=true
 if(reenter)operators.C.mood=0
 const initial=new MowerSchedulingData({alpha:true,nowMicros:0,plan:{contact:['A'],central:['B'],meeting:['C'],dormitory_1:['K','Free','Free','Free','Free']},operators,dorms:[1,2,3,4].map(i=>new MowerDormState(['dormitory_1',i])),planConditions:[true],policy:{restingThreshold:.65}})
 const data=projectMowerArrangements(initial,[{contact:['X'],dormitory_1:['Current','A','Current','Current','Current']}])
 const model:MowerShiftModel={count:1,evaluate:d=>[d.operators.A!.isResting()||reenter&&d.operators.C!.isResting()],swap:(d,c)=>{const next=projectMowerArrangements(d,[]);next.planConditions=[...c];next.operators.B!.exhaustRequire=!!c[0];return next},transition:()=>({}),activate:()=>{}}
 const task=new MowerTask({type:T.SHIFT_ON,plan:{contact:['A']}}),queue=new MowerTaskQueue()
 queue.tasks=[task]
 return {data,model,task,queue}
}

describe('effective-plan exhaustion reservations during full shift preview',()=>{
 it.each([-1/60,.5])('lets B rest after A returns even with an obsolete deadline at %s hours',time=>{
  const {data,model,task,queue}=fixture(),old=new MowerTask({time,type:T.EXHAUST_OFF,metadata:'B'}),unaffected=new MowerTask({time:2,type:T.EXHAUST_OFF,metadata:'A'})
  queue.tasks.push(old,unaffected)
  const observed:MowerTask[][]=[],resting=planning.mowerResting
  vi.spyOn(planning,'mowerResting').mockImplementation((d,q,o)=>{if(!d.planConditions[0])observed.push([...q.tasks]);return resting(d,q,o)})
  const original=structuredClone(old),positions=Object.values(data.operators).map(op=>[op.name,op.currentRoom,op.currentIndex])
  for(let pass=0;pass<2;pass++)prepareMowerShiftCycle(data,task,queue,model)
  const projected=projectMowerArrangements(data,[task.plan])
  expect(observed.length).toBeGreaterThan(0)
  expect(observed.every(tasks=>!tasks.some(t=>t.type===T.EXHAUST_OFF&&t.metadata==='B'))).toBe(true)
  expect(observed.every(tasks=>tasks.some(t=>t.type===T.EXHAUST_OFF&&t.metadata==='A'))).toBe(true)
  expect(projected.operators.A!.currentRoom).toBe('contact')
  expect(projected.operators.B!.isResting()).toBe(true)
  expect(task.backupShiftConditions).toEqual([false])
  expect(queue.tasks).toContain(old);expect(queue.tasks).toContain(unaffected)
  expect(structuredClone(old)).toEqual(original)
  expect(Object.values(data.operators).map(op=>[op.name,op.currentRoom,op.currentIndex])).toEqual(positions)
  expect(data.planConditions).toEqual([true])
 })
 it('keeps the old deadline excluded after another group reactivates the backup',()=>{
  const {data,model,task,queue}=fixture(true),old=new MowerTask({time:.5,type:T.EXHAUST_OFF,metadata:'B'})
  queue.tasks.push(old)
  const observed:MowerTask[][]=[],resting=planning.mowerResting
  vi.spyOn(planning,'mowerResting').mockImplementation((d,q,o)=>{observed.push([...q.tasks]);return resting(d,q,o)})
  prepareMowerShiftCycle(data,task,queue,model)
  expect(observed.every(tasks=>!tasks.some(t=>t.type===T.EXHAUST_OFF&&t.metadata==='B'))).toBe(true)
  const projected=projectMowerArrangements(data,[task.plan])
  expect(projected.operators.C!.isResting()).toBe(true)
  expect(projected.operators.B!.currentRoom).toBe('central')
  expect(task.backupShiftConditions).toEqual([true])
  expect(queue.tasks).toContain(old)
 })
})

function activationFixture(product=false){
 const workspace=createDefaultWorkspace()
 workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:null,replacements:['char_240_wyvern']}]
 workspace.mainPlan.facilities.room_1_2.slots=[{occupant:{kind:'operator',operatorId:'char_502_nblade'},groupId:null,replacements:['char_500_noirc']}]
 workspace.compatibility.backupPlans=[product?{name:'product',trigger:'True',plan:{room_1_1:{product:'exp3',plans:[{agent:'Current'}]}}}:{name:'exhaust',trigger:'True',conf:{exhaust_require:['芬']}}]
 if(product){workspace.mainPlan.facilities.room_1_1.type='manufacture';workspace.mainPlan.facilities.room_1_1.product='gold'}
 const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule)
 config.mowerAlpha=true
 const state=createRosterRuntime(config),controller=createBackupPlanController(schedule,state),source=getMowerSourceRuntime(state)
 return {state,controller,source}
}
describe('effective-plan exhaustion reservations at actual activation',()=>{
 it.each([false,true])('invalidates only changed dynamic reservations and preserves unfinished work, product=%s',product=>{
  const {state,source}=activationFixture(product),changed=new MowerTask({time:3,type:T.EXHAUST_OFF,metadata:'char_123_fang'}),unaffected=new MowerTask({time:4,type:T.EXHAUST_OFF,metadata:'char_502_nblade'})
  const concrete=new MowerTask({time:5,type:T.EXHAUST_OFF,metadata:'char_123_fang',plan:{room_1_1:['char_240_wyvern']}})
  const retained=new MowerTask({time:6,type:T.EXHAUST_OFF,metadata:'char_123_fang'});retained.executionRetained=true
  source.queue.tasks=[changed,unaffected,concrete,retained]
  state.mowerShiftModel!.activate([true])
  expect(source.queue.tasks).not.toContain(changed)
  expect(source.queue.tasks).toEqual([unaffected,concrete,retained])
  if(!product)expect(source.data.operators.char_123_fang!.exhaustRequire).toBe(true)
  else expect(source.data.operators.char_123_fang!.room).toBe('room_1_1')
  expect(unaffected.time).toBe(4);expect(concrete.time).toBe(5);expect(retained.time).toBe(6)
 })
})

it('retains the live queue and observations when the filtered preview fails',()=>{
 const {data,model,task,queue}=fixture(),old=new MowerTask({time:.5,type:T.EXHAUST_OFF,metadata:'B'})
 queue.tasks.push(old)
 const original=structuredClone(old)
 vi.spyOn(planning,'mowerResting').mockImplementation((_data,local)=>{
  expect(local.tasks.some(t=>t.type===T.EXHAUST_OFF&&t.metadata==='B')).toBe(false)
  throw new MowerShiftPreviewError('stop preview')
 })
 expect(()=>prepareMowerShiftCycle(data,task,queue,model)).toThrow('stop preview')
 expect(queue.tasks).toEqual([task,old]);expect(structuredClone(old)).toEqual(original)
 expect(data.planConditions).toEqual([true]);expect(data.operators.A!.isResting()).toBe(true)
})
