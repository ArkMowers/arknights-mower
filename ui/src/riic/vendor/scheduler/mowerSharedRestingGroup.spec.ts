import {describe,it,expect} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros,type MowerTaskPlan} from './mowerTaskQueue'
import {planMowerMetadata} from './mowerMetadata'
import {projectMowerArrangements} from './mowerObservations'

function fixture(){
 const operators={
  A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'room_1_1',currentIndex:0,group:'a',replacement:['X'],operatorType:'high',restingPriority:'high',mood:1,timeStampMicros:0}),
  B:new MowerOperatorState({name:'B',room:'room_1_2',index:0,currentRoom:'room_1_2',currentIndex:0,group:'b',replacement:['Y'],operatorType:'high',restingPriority:'high',mood:24,timeStampMicros:0}),
  S:new MowerOperatorState({name:'S',room:'room_1_3',index:0,currentRoom:'room_1_3',currentIndex:0,group:'b',replacement:['C'],groupBindings:[{group:'a',replacement:['C']},{group:'b',replacement:['C']}],operatorType:'high',restingPriority:'standby',mood:10,timeStampMicros:0}),
  X:new MowerOperatorState({name:'X',mood:24,timeStampMicros:0}),
  Y:new MowerOperatorState({name:'Y',mood:24,timeStampMicros:0}),
  C:new MowerOperatorState({name:'C',mood:24,timeStampMicros:0}),
 }
 return new MowerSchedulingData({alpha:true,plan:{room_1_1:['A'],room_1_2:['B'],room_1_3:['S'],dormitory_1:['Free']},operators,dorms:[new MowerDormState(['dormitory_1',0])],nowMicros:0,groupShiftState:{a:false,b:false}})
}

describe('shared follower resting group prediction',()=>{
 it('lets a shared standby follower leave without a bed when its new binding has a recovering anchor',()=>{
  const data=fixture(),plan:MowerTaskPlan={},state=data.groupShiftState,replacement=data.operators.S!.replacement
  expect(mowerGetRestingPlan(data,data.shiftGroupMembers('a'),[],plan)).toBe(true)
  expect(plan).toEqual({room_1_1:['X'],room_1_3:['C']})
  expect(data.groupShiftState).toBe(state);expect(state).toEqual({a:false,b:false})
  expect(data.operators.S!.group).toBe('b');expect(data.operators.S!.replacement).toBe(replacement)
  expect(data.dorms[0]!.name).toBe('A')
 })
 it('restores confirmed group state and bindings when the hypothetical shared shift cannot match a cover',()=>{
  const data=fixture(),plan:MowerTaskPlan={},state=data.groupShiftState,replacement=data.operators.S!.replacement
  data.operators.C!.currentRoom='train';data.operators.C!.currentIndex=1
  expect(mowerGetRestingPlan(data,data.shiftGroupMembers('a'),[],plan)).toBe(false)
  expect(plan).toEqual({});expect(data.dorms[0]!.name).toBe('')
  expect(data.groupShiftState).toBe(state);expect(state).toEqual({a:false,b:false})
  expect(data.operators.S!.group).toBe('b');expect(data.operators.S!.replacement).toBe(replacement)
 })
})


describe('independent shared returns use confirmed group state',()=>{
 it('waits for a future group return to execute before deriving its independent return',()=>{
  const data=fixture(),a=data.operators.A!,s=data.operators.S!
  data.plan.dormitory_1=['Free','Free']
  Object.assign(a,{currentRoom:'dormitory_1',currentIndex:0,mood:12})
  Object.assign(s,{currentRoom:'dormitory_1',currentIndex:1,mood:24,group:'',groupBindings:[{group:'',replacement:['C']},{group:'a',replacement:['C']}]})
  Object.assign(data.operators.X!,{currentRoom:'room_1_1',currentIndex:0})
  Object.assign(data.operators.C!,{currentRoom:'room_1_3',currentIndex:0})
  data.groupShiftState={a:true,b:false}
  data.dorms=[new MowerDormState(['dormitory_1',0],'A',toMowerMicros(2)),new MowerDormState(['dormitory_1',1],'S',0)]
  const future=new MowerTask({type:T.SELF_CORRECTION,time:2,plan:{room_1_1:['A']}}),queue=new MowerTaskQueue();queue.tasks=[future]
  planMowerMetadata(data,queue)
  expect(queue.tasks.some(task=>task.type===T.SHIFT_ON&&task.timeMicros<data.nowMicros+toMowerMicros(2)&&task.plan.room_1_3?.includes('S'))).toBe(false)
  expect(queue.tasks).toContain(future)
  expect(s.currentRoom).toBe('dormitory_1')
  const returned=projectMowerArrangements(data,[future.plan]);queue.tasks=[]
  planMowerMetadata(returned,queue)
  expect(queue.tasks.some(task=>task.type===T.SHIFT_ON&&task.plan.room_1_3?.includes('S'))).toBe(true)
 })
})
