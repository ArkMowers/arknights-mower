import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {coalesceMowerBackupTransition,prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,type MowerTaskPlan} from './mowerTaskQueue'

function fixture(){
 const make=(name:string,room:string,index:number,group='',replacement:string[]=[])=>new MowerOperatorState({name,room,index,group,replacement,currentRoom:room,currentIndex:index,mood:4,timeStampMicros:0,operatorType:room?'high':'low'})
 const operators={A:make('A','room_1_1',0,'a',['X']),B:make('B','room_1_2',0,'b',['Y']),B2:make('B2','room_1_2',1,'b',['Z']),X:make('X','',-1),Y:make('Y','',-1),Z:make('Z','',-1),K:make('K','dormitory_1',0)}
 operators.K.mood=24
 const data=new MowerSchedulingData({alpha:true,nowMicros:0,plan:{room_1_1:['A'],room_1_2:['B','B2'],dormitory_1:['K','Free','Free','Free','Free']},operators,dorms:[1,2,3,4].map(i=>new MowerDormState(['dormitory_1',i])),planConditions:[false],policy:{restingThreshold:.65}})
 const model:MowerShiftModel={count:1,evaluate:d=>[d.operators.A!.isResting()],swap:(d,c)=>{const next=projectMowerArrangements(d,[]);next.planConditions=[...c];next.operators.B2!.exhaustRequire=!!c[0];return next},transition:()=>({}),activate:()=>{}}
 const planA:MowerTaskPlan={room_1_1:['X'],dormitory_1:['Current','A','Current','Current','Current']}
 const planB:MowerTaskPlan={room_1_2:['Y','Z'],dormitory_1:['Current','Current','B','B2','Current']}
 const ordinary=(plan:MowerTaskPlan,names:string[])=>{const task=new MowerTask({type:T.SHIFT_OFF,plan});task.ordinaryCoordination=true;task.coordinationRequestNames=names;return task}
 return {data,model,planA,planB,ordinary}
}

describe('ordinary departure honors exhaustion enabled inside the full preview',()=>{
 it.each([false,true])('keeps B working when A departure activates B exhaustion, coalesced=%s',coalesced=>{
  const {data,model,planA,planB,ordinary}=fixture(),queue=new MowerTaskQueue()
  const task=ordinary(coalesced?planA:{...planA,room_1_2:planB.room_1_2!,dormitory_1:['Current','A','B','B2','Current']},coalesced?['A']:['A','B'])
  queue.tasks=[task];if(coalesced)queue.tasks.push(ordinary(planB,['B']))
  prepareMowerShiftCycle(data,task,queue,model)
  const projected=projectMowerArrangements(data,[task.plan])
  expect(projected.operators.A!.isResting()).toBe(true)
  expect(projected.operators.B!.currentRoom).toBe('room_1_2')
  expect(projected.operators.B2!.currentRoom).toBe('room_1_2')
  expect(task.backupShiftConditions).toEqual([true])
  expect(data.operators.A!.currentRoom).toBe('room_1_1')
 })
 it('rejects the stale ordinary intent when A was already resting before preview',()=>{
  const {data,model,planA,planB,ordinary}=fixture(),observed=projectMowerArrangements(data,[planA]),task=ordinary(planB,['B']),queue=new MowerTaskQueue()
  queue.tasks=[task]
  prepareMowerShiftCycle(observed,task,queue,model)
  const projected=projectMowerArrangements(observed,[task.plan])
  expect(projected.operators.B!.currentRoom).toBe('room_1_2')
  expect(projected.operators.B2!.currentRoom).toBe('room_1_2')
  expect(task.backupShiftConditions).toEqual([true])
 })
 it('keeps the shared follower resting with A after only B departure is canceled',()=>{
  const {data,model,ordinary}=fixture(),queue=new MowerTaskQueue()
  data.plan.room_1_3=['F']
  data.operators.F=new MowerOperatorState({name:'F',room:'room_1_3',index:0,currentRoom:'room_1_3',currentIndex:0,mood:4,timeStampMicros:0,operatorType:'high',groupBindings:[{group:'a',replacement:['R']},{group:'b',replacement:['R']}]})
  data.operators.R=new MowerOperatorState({name:'R',mood:24,timeStampMicros:0})
  const task=ordinary({room_1_1:['X'],room_1_2:['Y','Z'],room_1_3:['R'],dormitory_1:['Current','A','B','B2','F']},['A','B'])
  task.groupShiftTransitions={a:true,b:true};queue.tasks=[task]
  prepareMowerShiftCycle(data,task,queue,model)
  const projected=projectMowerArrangements(data,[task.plan])
  expect(projected.operators.F!.isResting()).toBe(true)
  expect(projected.currentOperator('room_1_3',0)?.name).toBe('R')
  expect(projected.operators.B!.currentRoom).toBe('room_1_2')
  expect(task.groupShiftTransitions.b).not.toBe(true)
 })
 it('restores a fixed dorm resident when its group ordinary departure is canceled',()=>{
  const {data,model,planA,ordinary}=fixture(),observed=projectMowerArrangements(data,[planA]),queue=new MowerTaskQueue()
  observed.operators.K!.group='b';observed.operators.K!.groupBindings=[{group:'b',replacement:['B']}]
  observed.operators.K!.replacement=['B'];observed.operators.B!.replacement=['K']
  const task=ordinary({room_1_2:['K','Z'],dormitory_1:['B','Current','B2','Current','Current']},['B'])
  queue.tasks=[task];prepareMowerShiftCycle(observed,task,queue,model)
  const projected=projectMowerArrangements(observed,[task.plan])
  expect(projected.currentOperator('dormitory_1',0)?.name).toBe('K')
  expect(projected.operators.B!.currentRoom).toBe('room_1_2')
  expect(projected.operators.B2!.currentRoom).toBe('room_1_2')
 })
 it('does not cancel genuine exhaustion when an ordinary duplicate is coalesced',()=>{
  const {data,model,planA,planB,ordinary}=fixture(),observed=projectMowerArrangements(data,[planA]),queue=new MowerTaskQueue()
  observed.operators.B2!.mood=0
  const task=new MowerTask({type:T.EXHAUST_OFF,plan:structuredClone(planB)})
  queue.tasks=[task,ordinary(planB,['B'])]
  prepareMowerShiftCycle(observed,task,queue,model)
  const projected=projectMowerArrangements(observed,[task.plan])
  expect(projected.operators.B!.isResting()).toBe(true)
  expect(projected.operators.B2!.isResting()).toBe(true)
 })
 it('drops an obsolete ordinary departure when merging a newly activated backup transition',()=>{
  const {data,planB,ordinary}=fixture()
  data.operators.B2!.exhaustRequire=true
  const task=ordinary(planB,['B']),before=structuredClone(task.plan)
  const result=coalesceMowerBackupTransition(data,{dormitory_1:['Current','Current','Free','Current','Current']},[task])
  expect(result.consumed).toEqual([task])
  expect(result.plan.room_1_2).toBeUndefined()
  expect(result.plan.dormitory_1).not.toContain('B')
  expect(result.plan.dormitory_1).not.toContain('B2')
  expect(task.plan).toEqual(before)
 })
 it('preserves an explicit backup departure even when it overlaps ordinary work',()=>{
  const {data,model,planA,planB,ordinary}=fixture(),observed=projectMowerArrangements(data,[planA]),queue=new MowerTaskQueue()
  const task=ordinary(planB,['B']);task.backupExplicitSlots.add('room_1_2\0'+'0');queue.tasks=[task]
  prepareMowerShiftCycle(observed,task,queue,model)
  const projected=projectMowerArrangements(observed,[task.plan])
  expect(projected.operators.B!.isResting()).toBe(true)
  expect(projected.operators.B2!.isResting()).toBe(true)
 })
 it('keeps a canceled departure cover in its existing dorm bed',()=>{
  const {data,model,planA,planB,ordinary}=fixture(),observed=projectMowerArrangements(data,[planA]),queue=new MowerTaskQueue()
  Object.assign(observed.operators.Y!,{currentRoom:'dormitory_1',currentIndex:4})
  observed.dorms.find(b=>b.position[1]===4)!.name='Y'
  const task=ordinary({...planB,dormitory_1:['Current','Current','B','B2','Free']},['B'])
  queue.tasks=[task];prepareMowerShiftCycle(observed,task,queue,model)
  const projected=projectMowerArrangements(observed,[task.plan])
  expect(projected.operators.Y!.currentRoom).toBe('dormitory_1')
  expect(projected.operators.Y!.currentIndex).toBe(4)
  expect(task.plan.dormitory_1?.[4]).not.toBe('Free')
 })
 it('preserves genuine exhaustion and a departure already in progress',()=>{
  for(const started of [false,true]){
   const {data,model,planA,planB,ordinary}=fixture(),observed=projectMowerArrangements(data,[planA]),task=ordinary(planB,['B']),queue=new MowerTaskQueue()
   task.ordinaryCoordination=started;task.backupShiftActive=started
   if(!started){task.type=T.EXHAUST_OFF;observed.operators.B2!.mood=0}
   queue.tasks=[task];prepareMowerShiftCycle(observed,task,queue,model)
   const projected=projectMowerArrangements(observed,[task.plan])
   expect(projected.operators.B!.isResting()).toBe(true)
   expect(projected.operators.B2!.isResting()).toBe(true)
  }
 })
})
